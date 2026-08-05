from __future__ import annotations

import json
import unittest
from pathlib import Path

from repair_lab import (
    TargetAccountTool,
    build_campaign_plan,
    evaluate_campaign_coverage,
)


class SuppliedEvaluatorSmokeTest(unittest.TestCase):
    """The test that shipped with the starter, pointed at the real question.

    It used to assert that `evaluate_campaign_coverage` returned True, which it
    did for every input including an empty plan. It now asserts the customer's
    request was met: every company in the upload, campaigned once, in the brand
    they chose.
    """

    def test_the_published_plan_covers_the_upload(self) -> None:
        accounts = json.loads(
            Path("fixtures/target_accounts.json").read_text()
        )
        request = json.loads(Path("fixtures/request.json").read_text())
        brand_kit_id = request["brand_kit"]["id"]
        template_id = request["template"]["id"]

        plan = build_campaign_plan(
            TargetAccountTool(accounts),
            brand_kit_id=brand_kit_id,
            template_id=template_id,
        )
        result = evaluate_campaign_coverage(
            plan,
            accounts,
            brand_kit_id=brand_kit_id,
            template_id=template_id,
        )
        self.assertTrue(result.passed, result.failures)


if __name__ == "__main__":
    unittest.main()
