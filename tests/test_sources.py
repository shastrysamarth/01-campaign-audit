"""The paging shapes the account service has actually produced.

`src/sources.py` says anything reading the uploaded list is expected to cope
with all of them, and to be honest about the ones where the correct answer is
that the list cannot be read completely. These tests fix which is which.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from repair_lab import (
    TargetAccountTool,
    build_campaign_plan,
    evaluate_campaign_coverage,
)
from sources import (
    CyclingLoader,
    ReplayingLoader,
    SilentlyShortLoader,
    StallingLoader,
    TruncatedWithoutCursorLoader,
)

REQUEST = json.loads(Path("fixtures/request.json").read_text())
BRAND_KIT = REQUEST["brand_kit"]["id"]
TEMPLATE = REQUEST["template"]["id"]
ACCOUNTS = json.loads(Path("fixtures/target_accounts.json").read_text())


def plan_from(loader, page_size: int = 25) -> dict:
    return build_campaign_plan(
        loader,
        brand_kit_id=BRAND_KIT,
        template_id=TEMPLATE,
        page_size=page_size,
    )


def check(plan: dict):
    return evaluate_campaign_coverage(
        plan, ACCOUNTS, brand_kit_id=BRAND_KIT, template_id=TEMPLATE
    )


class ScanRefusesWhatItCannotRead(unittest.TestCase):
    """These three contradict themselves in the paging metadata, so the scan
    catches them on its own and produces no deliverables."""

    def test_stalling_loader_is_incomplete(self) -> None:
        plan = plan_from(StallingLoader(ACCOUNTS))

        self.assertFalse(plan["complete"])
        self.assertIn("without advancing", plan["incomplete_reason"])
        self.assertEqual(plan["deliverables"], [])
        self.assertFalse(check(plan).passed)

    def test_cycling_loader_is_incomplete(self) -> None:
        plan = plan_from(CyclingLoader(ACCOUNTS))

        self.assertFalse(plan["complete"])
        self.assertIn("without advancing", plan["incomplete_reason"])
        self.assertEqual(plan["deliverables"], [])

    def test_truncated_without_cursor_is_incomplete(self) -> None:
        plan = plan_from(TruncatedWithoutCursorLoader(ACCOUNTS))

        self.assertFalse(plan["complete"])
        self.assertIn("supplied no cursor", plan["incomplete_reason"])
        self.assertEqual(plan["deliverables"], [])

    def test_none_of_them_exhaust_the_source_page_budget(self) -> None:
        """sources.py raises RuntimeError at 400 pages. Reaching that would
        mean the scan spun instead of noticing."""
        for loader_cls in (StallingLoader, CyclingLoader):
            with self.subTest(loader=loader_cls.__name__):
                plan = plan_from(loader_cls(ACCOUNTS))
                self.assertLess(plan["diagnostics"]["pages_fetched"], 400)


class ScanRecoversFromARetriedPage(unittest.TestCase):
    """A replayed page is a transport artefact, not a second company."""

    def test_replaying_loader_matches_the_clean_read(self) -> None:
        replayed = plan_from(ReplayingLoader(ACCOUNTS))
        clean = plan_from(TargetAccountTool(ACCOUNTS))

        self.assertTrue(replayed["complete"])
        self.assertGreater(replayed["diagnostics"]["rows_replayed"], 0)
        self.assertEqual(
            replayed["diagnostics"]["companies"],
            clean["diagnostics"]["companies"],
        )
        self.assertEqual(
            len(replayed["deliverables"]), len(clean["deliverables"])
        )
        self.assertTrue(check(replayed).passed)


class ShortReadIsNotDetectableFromThePagingInterface(unittest.TestCase):
    """A source that stops early and reports success emits the same page
    sequence as one that reached the end, so no reader can tell them apart.

    The second test below only passes because it hands the checker an
    independent full copy of the upload, read from disk rather than through the
    loader. Fed from the same paginated source the plan was built from, the
    checker would be short by exactly the same rows and would agree. This is a
    property of how the test is wired, not a capability of the check. See
    DECISIONS.md."""

    def test_silently_short_loader_looks_fine_to_the_scan(self) -> None:
        plan = plan_from(SilentlyShortLoader(ACCOUNTS))

        self.assertTrue(plan["complete"])
        self.assertLess(plan["diagnostics"]["rows_read"], len(ACCOUNTS))

    def test_an_independent_copy_of_the_upload_rejects_it(self) -> None:
        plan = plan_from(SilentlyShortLoader(ACCOUNTS))
        result = check(plan)

        self.assertFalse(result.passed)
        self.assertIn(
            "have no deliverables", " | ".join(result.failures)
        )


if __name__ == "__main__":
    unittest.main()
