"""The check has to be able to fail.

The shipped check returned True for every input, including a plan with no
deliverables at all. Each test here breaks one thing and asserts the failure is
caught, which is the only evidence that a green run means anything.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import unittest
from pathlib import Path

from repair_lab import (
    TargetAccountTool,
    build_campaign_plan,
    evaluate_campaign_coverage,
)

REQUEST = json.loads(Path("fixtures/request.json").read_text())
BRAND_KIT = REQUEST["brand_kit"]["id"]
TEMPLATE = REQUEST["template"]["id"]
ACCOUNTS = json.loads(Path("fixtures/target_accounts.json").read_text())


def good_plan() -> dict:
    return build_campaign_plan(
        TargetAccountTool(ACCOUNTS),
        brand_kit_id=BRAND_KIT,
        template_id=TEMPLATE,
    )


def check(plan: dict, accounts: list[dict] | None = None):
    return evaluate_campaign_coverage(
        plan,
        ACCOUNTS if accounts is None else accounts,
        brand_kit_id=BRAND_KIT,
        template_id=TEMPLATE,
    )


def failure_text(result) -> str:
    return " | ".join(result.failures)


class TheCheckPassesACorrectPlan(unittest.TestCase):
    def test_baseline(self) -> None:
        result = check(good_plan())
        self.assertTrue(result.passed, result.failures)
        self.assertEqual(result.failures, ())


class TheCheckCatchesABrokenPlan(unittest.TestCase):
    def test_empty_plan_fails(self) -> None:
        """The regression that motivated all of this."""
        plan = good_plan()
        plan["deliverables"] = []
        plan["companies"] = []

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("no deliverables", failure_text(result))

    def test_incomplete_scan_fails(self) -> None:
        plan = good_plan()
        plan["complete"] = False
        plan["incomplete_reason"] = "source stalled"

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("scan did not complete", failure_text(result))

    def test_dropped_company_fails(self) -> None:
        plan = good_plan()
        dropped = plan["companies"][0].identity
        plan["deliverables"] = [
            d
            for d in plan["deliverables"]
            if d["company_identity"] != dropped
        ]

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("have no deliverables", failure_text(result))

    def test_missing_asset_type_fails(self) -> None:
        plan = good_plan()
        plan["deliverables"] = plan["deliverables"][1:]

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("wrong asset set", failure_text(result))

    def test_duplicated_asset_type_fails(self) -> None:
        """A set comparison would miss this. A sorted-list comparison does not."""
        plan = good_plan()
        extra = copy.deepcopy(plan["deliverables"][0])
        plan["deliverables"].append(extra)

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("wrong asset set", failure_text(result))

    def test_wrong_brand_kit_fails(self) -> None:
        plan = good_plan()
        plan["deliverables"][0] = copy.deepcopy(plan["deliverables"][0])
        plan["deliverables"][0]["brand_kit_id"] = "brand-kit-2019-legacy"

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("brand kit other than", failure_text(result))

    def test_wrong_template_fails(self) -> None:
        plan = good_plan()
        plan["deliverables"][0] = copy.deepcopy(plan["deliverables"][0])
        plan["deliverables"][0]["template_id"] = "template-legacy-blast"

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("template other than", failure_text(result))

    def test_fabricated_company_id_fails(self) -> None:
        """What a reintroduced str(company_id) would produce."""
        for stand_in in ("None", "", "null", "   "):
            with self.subTest(stand_in=stand_in):
                plan = good_plan()
                provisional = next(
                    i
                    for i, d in enumerate(plan["deliverables"])
                    if d["company_id"] is None
                )
                plan["deliverables"][provisional] = copy.deepcopy(
                    plan["deliverables"][provisional]
                )
                plan["deliverables"][provisional]["company_id"] = stand_in

                result = check(plan)
                self.assertFalse(result.passed)
                self.assertIn("fabricated company id", failure_text(result))

    def test_untraceable_deliverable_fails(self) -> None:
        plan = good_plan()
        plan["deliverables"][0] = copy.deepcopy(plan["deliverables"][0])
        plan["deliverables"][0]["source_row_id"] = "row-does-not-exist"

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("not in the upload", failure_text(result))

    def test_silently_dropped_row_fails(self) -> None:
        """A row that is neither campaigned nor recorded as merged."""
        plan = good_plan()
        plan["companies"] = plan["companies"][:-1]
        last = plan["companies"][-1].identity if plan["companies"] else None
        plan["deliverables"] = [
            d for d in plan["deliverables"] if d["company_identity"] != last
        ]

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("neither campaigned nor recorded as merged",
                      failure_text(result))

    def test_unflagged_ambiguous_company_fails(self) -> None:
        """The plan must flag what the upload implies, not fewer."""
        plan = good_plan()
        plan["companies"] = [
            dataclasses.replace(c, shared_domains=())
            for c in plan["companies"]
        ]

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("not flagged for review", failure_text(result))

    def test_spuriously_flagged_company_fails(self) -> None:
        plan = good_plan()
        clean = next(
            i for i, c in enumerate(plan["companies"]) if not c.needs_review
        )
        plan["companies"][clean] = dataclasses.replace(
            plan["companies"][clean], shared_domains=("invented.example",)
        )

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("without sharing a domain", failure_text(result))

    def test_check_does_not_take_the_plan_at_its_word(self) -> None:
        """A plan built from half the upload, checked against all of it."""
        plan = build_campaign_plan(
            TargetAccountTool(ACCOUNTS[:100]),
            brand_kit_id=BRAND_KIT,
            template_id=TEMPLATE,
        )
        self.assertTrue(plan["complete"])

        result = check(plan)
        self.assertFalse(result.passed)
        self.assertIn("have no deliverables", failure_text(result))


if __name__ == "__main__":
    unittest.main()
