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

# Shapes a stringified empty key takes. Used only to assert that none of them
# ever reaches a deliverable; nothing keys on them.
FABRICATED_IDS = frozenset({"none", "null", "nan", "nil", "undefined"})


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
            )
        )
    return resolved


def _make_deliverables(
    companies: list[ResolvedCompany],
    *,
    brand_kit_id: str,
    template_id: str,
) -> list[dict[str, Any]]:
    """One set of required assets per company, in the requested brand.

    The brand kit and template come from the request and nowhere else. A row
    carrying `saved_brand_kit_id` or `saved_template_id` does not override the
    customer's selection; those rows are reported instead.
    """
    deliverables: list[dict[str, Any]] = []
    for company in companies:
        for asset_type in REQUIRED_ASSET_TYPES:
            deliverables.append(
                {
                    "source_row_id": company.source_row_id,
                    "company_identity": company.identity,
                    "company_id": company.company_id,
                    "company_name": company.company_name,
                    "asset_type": asset_type,
                    "brand_kit_id": brand_kit_id,
                    "template_id": template_id,
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
            companies=0,
            keyed=0,
            provisional=0,
            rows_merged=0,
            brand_overrides_ignored=[],
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
    overrides = [
        str(row["id"])
        for row in rows
        if "saved_brand_kit_id" in row or "saved_template_id" in row
    ]
    diagnostics.update(
        companies=len(companies),
        keyed=sum(1 for c in companies if not c.provisional),
        provisional=sum(1 for c in companies if c.provisional),
        rows_merged=sum(len(c.merged_row_ids) for c in companies),
        brand_overrides_ignored=overrides,
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


# --------------------------------------------------------------------------
# Checking the campaign against the upload
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CoverageResult:
    passed: bool
    summary: str
    failures: tuple[str, ...]


def _sample(items: list[str], limit: int = 3) -> str:
    shown = ", ".join(sorted(items)[:limit])
    if len(items) > limit:
        shown += f", ... (+{len(items) - limit} more)"
    return shown


def evaluate_campaign_coverage(
    plan: dict[str, Any],
    accounts: list[dict[str, Any]],
    *,
    brand_kit_id: str,
    template_id: str,
) -> CoverageResult:
    """Check the plan against the list the customer uploaded.

    This resolves `accounts` itself and compares. It does not take the plan's
    word for how many companies there were, how many rows were read, or whether
    the scan finished. The plan's own `complete` flag is required to be True,
    but it is never sufficient: a source that stopped early and reported
    success still fails here, because the companies it never read are missing
    from the deliverables.
    """
    failures: list[str] = []

    row_ids = [str(row["id"]) for row in accounts]
    if len(row_ids) != len(set(row_ids)):
        repeated = [r for r, n in collections.Counter(row_ids).items() if n > 1]
        failures.append(
            f"uploaded rows do not have unique ids ({_sample(repeated)}); "
            f"identity cannot be established"
        )
    upload_row_ids = set(row_ids)

    expected = resolve_companies(accounts)
    expected_identities = {company.identity for company in expected}
    keyed = sum(1 for c in expected if not c.provisional)
    provisional = len(expected) - keyed

    deliverables = plan.get("deliverables", [])

    # 1. the scan has to have finished
    if plan.get("complete") is not True:
        failures.append(
            f"scan did not complete: {plan.get('incomplete_reason')}"
        )

    # 2. every logical company, exactly once
    by_identity: dict[str, list[str]] = collections.defaultdict(list)
    for item in deliverables:
        by_identity[str(item.get("company_identity"))].append(
            str(item.get("asset_type"))
        )

    missing = sorted(expected_identities - set(by_identity))
    unexpected = sorted(set(by_identity) - expected_identities)
    if missing:
        failures.append(
            f"{len(missing)} logical companies have no deliverables "
            f"({_sample(missing)})"
        )
    if unexpected:
        failures.append(
            f"{len(unexpected)} deliverable identities are not in the upload "
            f"({_sample(unexpected)})"
        )

    # 3. exactly the required assets, once each. Comparing sorted lists rather
    #    than sets so a duplicated asset fails too.
    wrong_assets = [
        identity
        for identity in sorted(expected_identities & set(by_identity))
        if sorted(by_identity[identity]) != sorted(REQUIRED_ASSET_TYPES)
    ]
    if wrong_assets:
        failures.append(
            f"{len(wrong_assets)} companies have the wrong asset set "
            f"({_sample(wrong_assets)})"
        )

    # 4. the request's brand kit and template, with no exceptions
    wrong_brand = {
        str(i.get("company_identity"))
        for i in deliverables
        if i.get("brand_kit_id") != brand_kit_id
    }
    wrong_template = {
        str(i.get("company_identity"))
        for i in deliverables
        if i.get("template_id") != template_id
    }
    if wrong_brand:
        failures.append(
            f"{len(wrong_brand)} companies carry a brand kit other than "
            f"{brand_kit_id!r} ({_sample(sorted(wrong_brand))})"
        )
    if wrong_template:
        failures.append(
            f"{len(wrong_template)} companies carry a template other than "
            f"{template_id!r} ({_sample(sorted(wrong_template))})"
        )

    # 5. traceability, in both directions
    untraceable = sorted(
        {
            str(i.get("source_row_id"))
            for i in deliverables
            if str(i.get("source_row_id")) not in upload_row_ids
        }
    )
    if untraceable:
        failures.append(
            f"{len(untraceable)} deliverables cite a row that is not in the "
            f"upload ({_sample(untraceable)})"
        )

    accounted: set[str] = set()
    for company in plan.get("companies", []):
        accounted.add(company.source_row_id)
        accounted.update(company.merged_row_ids)
    unaccounted = sorted(upload_row_ids - accounted)
    if unaccounted:
        failures.append(
            f"{len(unaccounted)} uploaded rows are neither campaigned nor "
            f"recorded as merged ({_sample(unaccounted)})"
        )

    # 6. no fabricated identifier reaches a deliverable
    fabricated = sorted(
        {
            repr(i.get("company_id"))
            for i in deliverables
            if i.get("company_id") is not None
            and (
                not isinstance(i.get("company_id"), str)
                or not str(i.get("company_id")).strip()
                or str(i.get("company_id")).strip().lower() in FABRICATED_IDS
            )
        }
    )
    if fabricated:
        failures.append(
            f"{len(fabricated)} deliverables carry a fabricated company id "
            f"({_sample(fabricated)})"
        )

    summary = (
        f"{len(expected)} logical companies in the upload "
        f"({keyed} keyed, {provisional} provisional); "
        f"{len(deliverables)} deliverables in the plan"
    )
    if failures:
        return CoverageResult(False, summary, tuple(failures))
    return CoverageResult(True, summary, ())
