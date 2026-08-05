from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import Any, Protocol


REQUIRED_ASSET_TYPES = (
    "landing_page",
    "linkedin_ad_1",
    "linkedin_ad_2",
    "linkedin_ad_3",
)

# The account service has been seen to replay a page after retrying an upstream
# read, so serving one cursor twice is tolerated. A third serving of the same
# cursor is not a retry; it is a source that is not advancing.
MAX_CURSOR_SERVINGS = 2

# Backstop for a source that keeps advancing but never terminates.
MAX_PAGES = 1000


@dataclass(frozen=True)
class ToolPage:
    rows: list[dict[str, Any]]
    next_cursor: str | None
    truncated: bool


class AccountPageLoader(Protocol):
    def load_page(
        self,
        *,
        cursor: str | None = None,
        page_size: int = 25,
    ) -> ToolPage: ...


class TargetAccountTool:
    """Deterministic stand-in for the paginated uploaded-account service."""

    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        self._accounts = [dict(account) for account in accounts]

    def load_page(
        self,
        *,
        cursor: str | None = None,
        page_size: int = 25,
    ) -> ToolPage:
        start = int(cursor or "0")
        rows = self._accounts[start : start + page_size]
        next_index = start + len(rows)
        next_cursor = (
            str(next_index) if next_index < len(self._accounts) else None
        )
        return ToolPage(
            rows=rows,
            next_cursor=next_cursor,
            truncated=next_cursor is not None,
        )


@dataclass(frozen=True)
class ScanResult:
    """What a full pass over the account service produced.

    `complete` is not the source's word for it. It is False whenever the paging
    metadata contradicted itself or the scan had to give up.
    """

    rows: list[dict[str, Any]]
    complete: bool
    reason: str | None
    pages_fetched: int


def scan_accounts(
    tool: AccountPageLoader,
    *,
    page_size: int = 25,
) -> ScanResult:
    """Read every page the source will serve, checking it as we go.

    Three things can be established from paging metadata alone, and all three
    are checked here: that a cursor advances, that a source claiming more rows
    supplies a way to ask for them, and that the scan terminates.

    One thing cannot be established here. A source that stops early and reports
    itself finished, with no cursor to probe past, is indistinguishable through
    this interface from one that genuinely reached the end. Catching that needs
    a check that reads the uploaded list, which arrives in W1.
    """
    rows: list[dict[str, Any]] = []
    servings: collections.Counter[str] = collections.Counter()
    cursor: str | None = None
    pages = 0

    while True:
        token = "<start>" if cursor is None else cursor
        servings[token] += 1
        if servings[token] > MAX_CURSOR_SERVINGS:
            return ScanResult(
                rows=rows,
                complete=False,
                reason=(
                    f"source served cursor {token!r} {servings[token]} times "
                    f"without advancing"
                ),
                pages_fetched=pages,
            )

        page = tool.load_page(cursor=cursor, page_size=page_size)
        pages += 1
        rows.extend(page.rows)

        if not page.truncated:
            return ScanResult(
                rows=rows, complete=True, reason=None, pages_fetched=pages
            )
        if page.next_cursor is None:
            return ScanResult(
                rows=rows,
                complete=False,
                reason=(
                    "source reported more rows remained but supplied no cursor"
                ),
                pages_fetched=pages,
            )
        if pages >= MAX_PAGES:
            return ScanResult(
                rows=rows,
                complete=False,
                reason=(
                    f"page budget of {MAX_PAGES} exhausted before the source "
                    f"terminated"
                ),
                pages_fetched=pages,
            )
        cursor = page.next_cursor


def _drop_replayed_rows(
    rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Discard rows the source served more than once.

    A repeated row id is the same row arriving twice, not a second row, so it
    is dropped before anything counts it. This is transport de-duplication and
    is deliberately separate from deciding which rows name the same company.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row["id"])
        if row_id in seen:
            continue
        seen.add(row_id)
        unique.append(row)
    return unique, len(rows) - len(unique)


def _collapse_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows that name the same company.

    The uploaded list can name a company more than once, so the list is
    reduced to one row per company before anything downstream sees it.

    This runs once over every row the scan accumulated, never over a single
    page. Which rows survive is a property of the upload, not of the page size
    the source happened to serve.
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        company_id = str(row["company_id"])
        if company_id in seen:
            continue
        seen.add(company_id)
        kept.append(row)
    return kept


def _make_deliverables(
    accounts: list[dict[str, Any]],
    *,
    brand_kit_id: str,
    template_id: str,
) -> list[dict[str, str]]:
    deliverables: list[dict[str, str]] = []
    for account in accounts:
        effective_brand_kit = str(
            account.get("saved_brand_kit_id", brand_kit_id)
        )
        effective_template = str(
            account.get("saved_template_id", template_id)
        )
        for asset_type in REQUIRED_ASSET_TYPES:
            deliverables.append(
                {
                    "source_row_id": str(account["id"]),
                    "company_id": str(account["company_id"]),
                    "company_name": str(account["company_name"]),
                    "asset_type": asset_type,
                    "brand_kit_id": effective_brand_kit,
                    "template_id": effective_template,
                }
            )
    return deliverables


def build_campaign_plan(
    tool: AccountPageLoader,
    *,
    brand_kit_id: str,
    template_id: str,
    page_size: int = 25,
) -> dict[str, Any]:
    scan = scan_accounts(tool, page_size=page_size)
    rows, replayed = _drop_replayed_rows(scan.rows)

    diagnostics: dict[str, Any] = {
        "rows_read": len(scan.rows),
        "rows_unique": len(rows),
        "rows_replayed": replayed,
        "pages_fetched": scan.pages_fetched,
    }

    if not scan.complete:
        return {
            "complete": False,
            "incomplete_reason": scan.reason,
            "source_row_ids": [str(row["id"]) for row in rows],
            "deliverables": [],
            "diagnostics": diagnostics,
        }

    rows = _collapse_rows(rows)

    return {
        "complete": True,
        "incomplete_reason": None,
        "source_row_ids": [str(row["id"]) for row in rows],
        "deliverables": _make_deliverables(
            rows,
            brand_kit_id=brand_kit_id,
            template_id=template_id,
        ),
        "diagnostics": diagnostics,
    }


def evaluate_campaign_coverage(
    plan: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> tuple[bool, str]:
    """The currently deployed check. The customer disputes its result."""
    observed_rows = {str(value) for value in plan.get("source_row_ids", [])}
    deliverables = plan.get("deliverables", [])

    for row_id in sorted(observed_rows):
        observed_types = {
            str(item.get("asset_type"))
            for item in deliverables
            if str(item.get("source_row_id")) == row_id
        }
        if observed_types != set(REQUIRED_ASSET_TYPES):
            return False, f"source row {row_id} has the wrong asset set"

    if plan.get("complete") is not True:
        return False, "campaign did not declare completion"
    return True, f"all {len(observed_rows)} campaigned rows have the requested asset types"
