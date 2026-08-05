"""Acceptance criteria AC1-AC7 from ROADMAP.md section 6, W3.

Several of these build their own account lists rather than reading a fixture.
That is deliberate: the two shipped uploads spell a missing company_id
differently (`target_accounts.json` uses null, `second_list.json` uses ""), so a
suite that only reads them cannot tell a general rule from a fit to two files.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from repair_lab import (
    REQUIRED_ASSET_TYPES,
    FABRICATED_IDS,
    TargetAccountTool,
    ambiguous_domains,
    build_campaign_plan,
    evaluate_campaign_coverage,
    resolve_companies,
)

REQUEST = json.loads(Path("fixtures/request.json").read_text())
BRAND_KIT = REQUEST["brand_kit"]["id"]
TEMPLATE = REQUEST["template"]["id"]

LIST_ONE = "fixtures/target_accounts.json"
LIST_TWO = "fixtures/second_list.json"


def load(path: str) -> list[dict]:
    return json.loads(Path(path).read_text())


def plan_for(accounts: list[dict], page_size: int = 25) -> dict:
    return build_campaign_plan(
        TargetAccountTool(accounts),
        brand_kit_id=BRAND_KIT,
        template_id=TEMPLATE,
        page_size=page_size,
    )


def check(plan: dict, accounts: list[dict]):
    return evaluate_campaign_coverage(
        plan, accounts, brand_kit_id=BRAND_KIT, template_id=TEMPLATE
    )


def row(row_id: str, name: str, **extra) -> dict:
    base = {
        "id": row_id,
        "company_name": name,
        "domain": f"{row_id}.example",
        "segment": "software",
    }
    base.update(extra)
    return base


class AC1RepresentationIndependence(unittest.TestCase):
    """Every spelling of "no company_id" takes the same path."""

    def test_four_missing_key_forms_resolve_to_four_companies(self) -> None:
        accounts = [
            row("r1", "Absent Key"),  # field not present at all
            row("r2", "Null Key", company_id=None),
            row("r3", "Empty Key", company_id=""),
            row("r4", "Whitespace Key", company_id="   "),
        ]
        plan = plan_for(accounts)

        self.assertEqual(plan["diagnostics"]["companies"], 4)
        self.assertEqual(plan["diagnostics"]["provisional"], 4)
        self.assertEqual(plan["diagnostics"]["keyed"], 0)
        self.assertEqual(len(plan["deliverables"]), 16)
        self.assertTrue(check(plan, accounts).passed)

    def test_non_string_key_is_treated_as_missing(self) -> None:
        accounts = [row("r1", "Numeric Key", company_id=17)]
        self.assertTrue(resolve_companies(accounts)[0].provisional)


class AC2KeylessRowsNeverMerge(unittest.TestCase):
    """The assertion that fails against the original str(company_id)."""

    def test_two_nulls_and_two_empties_are_four_companies(self) -> None:
        accounts = [
            row("r1", "Alpha", company_id=None),
            row("r2", "Beta", company_id=None),
            row("r3", "Gamma", company_id=""),
            row("r4", "Delta", company_id=""),
        ]
        companies = resolve_companies(accounts)

        self.assertEqual(len(companies), 4)
        self.assertEqual(len({c.identity for c in companies}), 4)
        for company in companies:
            self.assertTrue(company.provisional)
            self.assertEqual(company.merged_row_ids, ())

    def test_keyed_rows_still_merge(self) -> None:
        accounts = [
            row("r1", "Alpha", company_id="c-1"),
            row("r2", "Alpha Inc", company_id="c-1"),
            row("r3", "Beta", company_id="c-2"),
        ]
        companies = resolve_companies(accounts)

        self.assertEqual(len(companies), 2)
        self.assertEqual(companies[0].source_row_id, "r1")
        self.assertEqual(companies[0].merged_row_ids, ("r2",))


class AC3NoFabricatedIdentifiers(unittest.TestCase):
    """No stringified null ever reaches a deliverable."""

    def test_provisional_deliverables_carry_an_explicit_null(self) -> None:
        accounts = [row("r1", "Nameless", company_id=None)]
        plan = plan_for(accounts)

        for item in plan["deliverables"]:
            self.assertIsNone(item["company_id"])

    def test_no_deliverable_in_either_fixture_carries_a_stand_in(self) -> None:
        for path in (LIST_ONE, LIST_TWO):
            with self.subTest(path=path):
                for item in plan_for(load(path))["deliverables"]:
                    company_id = item["company_id"]
                    if company_id is None:
                        continue
                    self.assertIsInstance(company_id, str)
                    self.assertTrue(company_id.strip())
                    self.assertNotIn(company_id.strip().lower(), FABRICATED_IDS)


class AC4BothShippedFixtures(unittest.TestCase):
    """One code path, two differently shaped uploads."""

    EXPECTED = {
        LIST_ONE: {"rows": 223, "companies": 209, "keyed": 203, "prov": 6},
        LIST_TWO: {"rows": 115, "companies": 99, "keyed": 97, "prov": 2},
    }

    def test_counts(self) -> None:
        for path, want in self.EXPECTED.items():
            with self.subTest(path=path):
                accounts = load(path)
                self.assertEqual(len(accounts), want["rows"])

                plan = plan_for(accounts)
                diagnostics = plan["diagnostics"]
                self.assertEqual(diagnostics["companies"], want["companies"])
                self.assertEqual(diagnostics["keyed"], want["keyed"])
                self.assertEqual(diagnostics["provisional"], want["prov"])
                self.assertEqual(
                    len(plan["deliverables"]),
                    want["companies"] * len(REQUIRED_ASSET_TYPES),
                )

                result = check(plan, accounts)
                self.assertTrue(result.passed, result.failures)


class AmbiguousIdentityIsFlagged(unittest.TestCase):
    """The customer's "entries I cannot tell apart" complaint.

    Any domain carrying more than one resolved identity flags every identity on
    it, because nothing in the upload says which one is the mistake.
    """

    def test_list_one_flags_four_domains_and_eight_companies(self) -> None:
        accounts = load(LIST_ONE)
        shared = ambiguous_domains(accounts)

        self.assertEqual(len(shared), 4)
        self.assertEqual(
            sorted(shared),
            [
                "copperline-group.example",
                "northwind-energy.example",
                "sable-fitness.example",
                "tessellate-capital.example",
            ],
        )
        flagged = [c for c in resolve_companies(accounts) if c.needs_review]
        self.assertEqual(len(flagged), 8)

    def test_list_two_needs_no_ambiguity_band(self) -> None:
        accounts = load(LIST_TWO)

        self.assertEqual(ambiguous_domains(accounts), {})
        self.assertEqual(
            [c for c in resolve_companies(accounts) if c.needs_review], []
        )

    def test_both_sides_of_the_pair_are_flagged(self) -> None:
        """Not just the later row. Nothing says which one is wrong."""
        companies = {c.identity: c for c in resolve_companies(load(LIST_ONE))}

        for identity in (
            "company_id:company-northwind-energy",
            "company_id:company-northwind-energy-emea",
        ):
            self.assertTrue(companies[identity].needs_review, identity)

    def test_flag_uses_every_row_not_just_the_surviving_one(self) -> None:
        """company-copperline-energy resolves to copperline-energy.example but
        has a second row on copperline-group.example. Looking only at the row
        whose values were kept would miss it."""
        companies = {c.identity: c for c in resolve_companies(load(LIST_ONE))}
        energy = companies["company_id:company-copperline-energy"]

        self.assertEqual(energy.domain, "copperline-energy.example")
        self.assertTrue(energy.needs_review)
        self.assertIn("copperline-group.example", energy.shared_domains)

    def test_review_flag_does_not_withhold_the_campaign(self) -> None:
        accounts = load(LIST_ONE)
        plan = plan_for(accounts)
        flagged = [c for c in plan["companies"] if c.needs_review]

        served = {
            d["company_identity"]
            for d in plan["deliverables"]
        }
        for company in flagged:
            self.assertIn(company.identity, served)


class AC5PageSizeInvariance(unittest.TestCase):
    """page_size 1 is included on purpose: it puts every row in its own page,
    so any surviving page-scoped merge produces the maximum duplicate count and
    cannot pass by coincidence."""

    PAGE_SIZES = (1, 10, 25, 100, 1000)

    def test_counts_do_not_move_with_page_size(self) -> None:
        for path in (LIST_ONE, LIST_TWO):
            with self.subTest(path=path):
                accounts = load(path)
                shapes = {
                    size: (
                        plan_for(accounts, size)["diagnostics"]["companies"],
                        plan_for(accounts, size)["diagnostics"]["provisional"],
                        len(plan_for(accounts, size)["deliverables"]),
                    )
                    for size in self.PAGE_SIZES
                }
                self.assertEqual(len(set(shapes.values())), 1, shapes)


class AC6EveryUploadedRowAccountedFor(unittest.TestCase):
    def test_campaigned_and_merged_partition_the_upload(self) -> None:
        for path in (LIST_ONE, LIST_TWO):
            with self.subTest(path=path):
                accounts = load(path)
                plan = plan_for(accounts)

                campaigned = {c.source_row_id for c in plan["companies"]}
                merged: set[str] = set()
                for company in plan["companies"]:
                    merged.update(company.merged_row_ids)

                self.assertEqual(campaigned & merged, set())
                self.assertEqual(
                    campaigned | merged, {str(r["id"]) for r in accounts}
                )


class AC7TraceabilityThroughAMerge(unittest.TestCase):
    def test_absorbed_row_is_named(self) -> None:
        accounts = load(LIST_ONE)
        plan = plan_for(accounts)

        alder = next(
            c
            for c in plan["companies"]
            if c.company_id == "company-alder-health"
        )
        self.assertEqual(alder.source_row_id, "row-1017")
        self.assertIn("row-1201", alder.merged_row_ids)

    def test_every_deliverable_cites_an_uploaded_row(self) -> None:
        for path in (LIST_ONE, LIST_TWO):
            with self.subTest(path=path):
                accounts = load(path)
                upload_ids = {str(r["id"]) for r in accounts}
                for item in plan_for(accounts)["deliverables"]:
                    self.assertIn(item["source_row_id"], upload_ids)


if __name__ == "__main__":
    unittest.main()
