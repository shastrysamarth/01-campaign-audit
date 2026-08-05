from __future__ import annotations

import argparse
import json
from pathlib import Path

from repair_lab import (
    TargetAccountTool,
    build_campaign_plan,
    evaluate_campaign_coverage,
)

PAGE_SIZES = (10, 25, 100)


def _run(accounts: list[dict], request: dict, page_size: int) -> dict:
    plan = build_campaign_plan(
        TargetAccountTool(accounts),
        brand_kit_id=request["brand_kit"]["id"],
        template_id=request["template"]["id"],
        page_size=page_size,
    )
    diagnostics = plan["diagnostics"]
    kits: dict[str, int] = {}
    for item in plan["deliverables"]:
        kit = str(item["brand_kit_id"])
        kits[kit] = kits.get(kit, 0) + 1
    return {
        "companies campaigned": diagnostics["companies"],
        "  of which keyed": diagnostics["keyed"],
        "  of which provisional": diagnostics["provisional"],
        "  of which need review": diagnostics["needs_review"],
        "deliverables": len(plan["deliverables"]),
        "rows read": diagnostics["rows_read"],
        "rows merged into another": diagnostics["rows_merged"],
        "complete flag": plan["complete"],
        "_kits": kits,
        "_overrides": diagnostics["brand_overrides_ignored"],
        "_plan": plan,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", default="fixtures/target_accounts.json")
    args = parser.parse_args()

    accounts = json.loads(Path(args.list).read_text())
    request = json.loads(Path("fixtures/request.json").read_text())
    brand_kit_id = request["brand_kit"]["id"]
    template_id = request["template"]["id"]

    results = {size: _run(accounts, request, size) for size in PAGE_SIZES}

    print(f"list                          : {args.list}")
    print(f"uploaded rows                 : {len(accounts)}")
    print(f"brand kit selected on request : {brand_kit_id}")
    print(f"template selected on request  : {template_id}")
    print()

    header = "".join(f"{f'page_size={s}':>16}" for s in PAGE_SIZES)
    print(f"{'':30}{header}")
    for field in (
        "companies campaigned",
        "  of which keyed",
        "  of which provisional",
        "  of which need review",
        "deliverables",
        "rows read",
        "rows merged into another",
        "complete flag",
    ):
        cells = "".join(f"{str(results[s][field]):>16}" for s in PAGE_SIZES)
        print(f"{field:30}{cells}")

    stable = {
        field: len({results[s][field] for s in PAGE_SIZES}) == 1
        for field in ("companies campaigned", "deliverables")
    }
    print()
    print(f"identical at every page size  : {all(stable.values())}")

    print()
    print("deliverables by brand kit (page_size=25):")
    for kit, count in sorted(results[25]["_kits"].items()):
        print(f"  {kit:32} {count:>6}")

    plan = results[25]["_plan"]
    shared = plan["diagnostics"]["ambiguous_domains"]
    print()
    print("identity model for this list:")
    print(f"  domains carrying more than one identity : {len(shared)}")
    print(f"  companies flagged needs_review          : "
          f"{plan['diagnostics']['needs_review']}")
    if shared:
        for domain, identities in shared.items():
            print(f"    {domain}")
            for identity in identities:
                company = next(
                    c for c in plan["companies"] if c.identity == identity
                )
                print(f"      {identity:52} {company.company_name}")
    else:
        print("    none - every domain in this list resolves to one company,")
        print("    so this list needs no ambiguity band at all")

    overrides = results[25]["_overrides"]
    print()
    print(f"rows carrying a stored brand override, ignored: {len(overrides)}")
    if overrides:
        shown = ", ".join(overrides[:6])
        if len(overrides) > 6:
            shown += f", ... (+{len(overrides) - 6} more)"
        print(f"  {shown}")

    result = evaluate_campaign_coverage(
        plan,
        accounts,
        brand_kit_id=brand_kit_id,
        template_id=template_id,
    )
    print()
    print(f"coverage check returned       : {result.passed}")
    print(f"coverage check said           : {result.summary}")
    for failure in result.failures:
        print(f"  FAIL: {failure}")


if __name__ == "__main__":
    main()
