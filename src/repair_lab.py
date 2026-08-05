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


def company_key(row: dict[str, Any]) -> str | None:
    """The row's external company key, or None when it has none.

    A key is usable only when it is a non-empty string. An absent field, a
    null, an empty or whitespace-only string, and a non-string value are all
    the same condition: the upload does not key this row. They share one branch
    on purpose, so that no upload's particular spelling of "missing" gets code
    of its own. `target_accounts.json` writes it as null and `second_list.json`
    writes it as "", and neither is named anywhere in this module.
    """
    value = row.get("company_id")
    if not isinstance(value, str):
        return None
    return value.strip() or None


@dataclass(frozen=True)
class ResolvedCompany:
    """One logical company, and every uploaded row that resolved to it."""

    identity: str
    company_id: str | None
    company_name: str
    domain: str | None
    source_row_id: str
    merged_row_ids: tuple[str, ...]
    saved_brand_kit_id: str | None
    saved_template_id: str | None

    @property
    def provisional(self) -> bool:
        """True when this company has no external key.

        A provisional company can be campaigned: it is distinguishable from
        every other row in this upload. It cannot be recognised in the next
        upload, because there is no key to recognise it by.
        """
        return self.company_id is None


def resolve_companies(
    rows: list[dict[str, Any]],
) -> list[ResolvedCompany]:
    """Group uploaded rows into logical companies.

    `company_id` is the only field permitted to merge two rows. Domain and
    company name are carried through but never merge anything: the upload
    contains one domain shared by two real companies and one company_id spread
    across two domains, so neither field decides identity.

    A row without a key stands as its own company. It is never merged, with
    anything, including another keyless row.

    This runs once over every row the scan accumulated, never over a single
    page. Which rows survive is a property of the upload, not of the page size
    the source happened to serve.
    """
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        key = company_key(row)
        identity = f"company_id:{key}" if key else f"row:{row['id']}"
        if identity not in groups:
            groups[identity] = []
            order.append(identity)
        groups[identity].append(row)

    resolved: list[ResolvedCompany] = []
    for identity in order:
        members = groups[identity]
        primary = members[0]
        resolved.append(
            ResolvedCompany(
                identity=identity,
                company_id=company_key(primary),
                company_name=str(primary.get("company_name", "")),
                domain=primary.get("domain"),
                source_row_id=str(primary["id"]),
                merged_row_ids=tuple(str(m["id"]) for m in members[1:]),
                saved_brand_kit_id=primary.get("saved_brand_kit_id"),
                saved_template_id=primary.get("saved_template_id"),
            )
        )
    return resolved


def _make_deliverables(
    companies: list[ResolvedCompany],
    *,
    brand_kit_id: str,
    template_id: str,
) -> list[dict[str, Any]]:
    deliverables: list[dict[str, Any]] = []
    for company in companies:
        effective_brand_kit = company.saved_brand_kit_id or brand_kit_id
        effective_template = company.saved_template_id or template_id
        for asset_type in REQUIRED_ASSET_TYPES:
            deliverables.append(
                {
                    "source_row_id": company.source_row_id,
                    "company_identity": company.identity,
                    "company_id": company.company_id,
                    "company_name": company.company_name,
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
        diagnostics.update(
            companies=0, keyed=0, provisional=0, rows_merged=0
        )
        return {
            "complete": False,
            "incomplete_reason": scan.reason,
            "companies": [],
            "source_row_ids": [str(row["id"]) for row in rows],
            "deliverables": [],
            "diagnostics": diagnostics,
        }

    companies = resolve_companies(rows)
    diagnostics.update(
        companies=len(companies),
        keyed=sum(1 for c in companies if not c.provisional),
        provisional=sum(1 for c in companies if c.provisional),
        rows_merged=sum(len(c.merged_row_ids) for c in companies),
    )

    return {
        "complete": True,
        "incomplete_reason": None,
        "companies": companies,
        "source_row_ids": [str(row["id"]) for row in rows],
        "deliverables": _make_deliverables(
            companies,
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
