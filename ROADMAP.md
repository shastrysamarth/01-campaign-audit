# ROADMAP

Written before any source or test edit. Everything below is derived from
reading `src/`, `fixtures/`, `demo.py`, `tests/`, and from read-only probes run
against the shipped code. No repository file has been modified.

**The three answers this document exists to give:**

| Question | Answer | Where |
|---|---|---|
| What went wrong, and how do we know? | Seven defects, five of them root causes, each with a reproduction | §2, §3 |
| How many logical companies is this upload? | **209** (203 keyed + 6 provisional), all campaigned; 99 for list 2 | §4 |
| What does "complete" mean? | **Definition in §5**, decomposed into six enforceable conditions | §5 |

---

## 1. Where this starts

The customer says the run is wrong and the check that agreed with it is not
trustworthy. Both are correct. The starter reports success on this upload, and
`make demo`, `make verify` and `make test` are all green on arrival.

Baseline, `make demo` on `fixtures/target_accounts.json` (223 rows):

```
                                  page_size=10    page_size=25   page_size=100
rows campaigned                            214             214             211
deliverables                               856             856             844
distinct company_id in plan                204             204             204
complete flag                             True            True            True

deliverables by brand kit (page_size=25):
  brand-kit-2019-legacy                36
  brand-kit-meridian-2026             820

shipped check returned        : True
```

Baseline, `make verify` on `fixtures/second_list.json` (115 rows):

```
                                  page_size=10    page_size=25   page_size=100
rows campaigned                            103             100              98
deliverables                               412             400             392
distinct company_id in plan                 98              98              98
complete flag                             True            True            True

shipped check returned        : True
```

The row count is a function of the page size. The page size is a transport
parameter. That alone establishes the answer is not a property of the upload.

---

## 2. Evidence gathered before planning

Read-only. Nothing in the repo was changed to produce any of this.

**2.1 — The shipped check ignores the upload.** I called
`evaluate_campaign_coverage` with a plan built from a loader that returns
nothing, passing three different values for its `accounts` argument:

```
accounts = the real 223-row list    -> (True, 'all 0 campaigned rows have the requested asset types')
accounts = an empty list            -> (True, 'all 0 campaigned rows have the requested asset types')
accounts = a list of garbage        -> (True, 'all 0 campaigned rows have the requested asset types')
```

Byte-identical. The parameter is declared and never read.

**2.2 — A plan with zero deliverables passes.** Same function, five loaders,
including two written for this probe:

```
loader                                 rows   deliv   complete   check
TargetAccountTool  (all 223 rows)       214     856       True    True
SilentlyShortLoader(serves 125/223)     116     464       True    True
ReplayingLoader    (each page 2x)       428    1712       True    True
OneRowLoader       (1 of 223)             1       4       True    True
EmptyLoader        (0 of 223)             0       0       True    True
```

The system cannot distinguish campaigning everything from campaigning nothing.

**2.3 — `complete` has one producer and it is a literal.**

```
src/repair_lab.py:124:        "complete": True,
src/repair_lab.py:145:    if plan.get("complete") is not True:
```

No arithmetic, no cursor state, no row tally. Any plan the function returns
carries `True`; the only other outcome is an exception.

**2.4 — The recorded incident matches.** `fixtures/failure-traces.jsonl`,
trace `t-9f21`: three pages of 25 + 25 + 17 = 67 rows, then
`"complete":true,"source_row_count":209`, then `evaluation passed:true`. A run
that read 67 rows claimed 209 and was certified. Trace `t-77b3` shows
`next_cursor:"25"` returned twice followed by `worker_timeout` at 90s, which is
the rerun the customer says never came back. `t-4c08` (image_search timeout,
template cache cold start) is unrelated noise and will not be repaired.

---

## 3. Findings

### D1 — Deduplication is scoped to a page, not to the plan  *(root cause)*

`_collapse_page` builds its `seen` set inside the function
([repair_lab.py:62](src/repair_lab.py:62)) and is called once per page from the
scan loop ([repair_lab.py:112](src/repair_lab.py:112)). It resets at every
boundary. Two rows for the same company collapse only if they happen to land in
the same page.

Five pairs in list 1 sit 90-110 rows apart and clear every tested page size:

```
kestrel-dynamics   111 <-> 218      harbor-group       122 <-> 219
ironwood-logistics 132 <-> 220      vantage-networks   142 <-> 221
tessellate-energy  183 <-> 222
```

Those ten rows are the doubles the customer found by hand. List 2 degrades in
three steps rather than two because its pairs straddle different boundaries:
`bramble`(19,20), `kestrel2`(29,30), `cinder3`(79,80) split at page_size 10 but
not 25; `straddle-works`(23,24,51) and the blank-id pair split at 10 and 25 but
not 100.

The collapse is also lossy and unrecorded. It keeps the first row and discards
the rest with no trace. Every duplicate group in both fixtures disagrees on at
least one field, so the discarded row was never redundant:

```
company-alder-health      row-1017 'Alder Health'  kept
                          row-1201 'ALDER HEALTH'  dropped, no deliverable
company-kestrel-robotics  row-1066 kestrel-robotics.example  kept
                          row-1216 kestrel-group.example     dropped
```

Nine uploaded rows in list 1 (twelve at page_size 100) produce no deliverable
and appear nowhere in `source_row_ids`. Which name and domain ship is decided
by file order. This violates the traceability constraint in TASK.md.

**Structural statement:** identity resolution runs inside the transport loop, so
a paging parameter is an input to a semantic decision.

### D2 — The identity key is `str(company_id)` and nothing else  *(root cause)*

[repair_lab.py:64](src/repair_lab.py:64). Six rows carry
`"company_id": null`; `str(None)` is `"None"`, so six unrelated businesses key
to one company:

```
row-2401 Halverson Freight       row-2404 Northgate Tutoring
row-2402 Pell & Sons Ironworks   row-2405 Riverbend Cold Storage
row-2403 Cobalt Ridge Dental     row-2406 Aster Point Realty
```

Six names, six domains, five segments. At page_size 10/25 they survive as six
copies of a company that does not exist. At page_size 100, indices 12/37/61/98
share page 0 and three real companies are dropped from the campaign entirely
(214 to 211, 856 to 844). List 2 does the same with `""` on `srow-1114` /
`srow-1115`.

The same six lines both fail to merge real duplicates and merge non-duplicates.

`domain` and `company_name` are carried into deliverables and never consulted.
Section 4 records why neither is a safe substitute.

### D3 — `complete` is a hardcoded literal  *(root cause)*

Section 2.3. The field carries zero bits. The gate at
[repair_lab.py:145](src/repair_lab.py:145) can never fire.

### D4 — The scan trusts the source's paging self-report  *(root cause)*

The loop exits on `not page.truncated` ([repair_lab.py:113](src/repair_lab.py:113))
with no row tally, no expected total, and no cursor-monotonicity check. Every
class in [src/sources.py](src/sources.py) is an instance of this one missing
check:

How much each one withholds depends on the page size, so the figures below are
stated at page_size 25 to match the probe in section 2.2.

| Loader | Lie | Current outcome |
|---|---|---|
| `SilentlyShortLoader` | `truncated=False` after serving 125 of 223 rows at page_size 25, leaving 98 never served | short plan, `complete: True` |
| `StallingLoader` | cursor never advances | spins to `PAGE_BUDGET`, RuntimeError |
| `CyclingLoader` | cursor wraps to 0 | spins to `PAGE_BUDGET`, RuntimeError |
| `TruncatedWithoutCursorLoader` | `truncated=True, next_cursor=None` | line 115 sets `cursor=None`, restarts at 0 forever |
| `ReplayingLoader` | serves each page twice | every row emitted twice; per-page collapse is structurally blind to it |

For three of these the correct result is not a plan at all. There is currently
no way for the function to say so.

### D5 — The shipped check is a tautology  *(root cause)*

`evaluate_campaign_coverage` ([repair_lab.py:128](src/repair_lab.py:128)) has
two gates. The per-row gate compares the observed asset set against
`REQUIRED_ASSET_TYPES`, which `_make_deliverables` emits for every row by
construction ([repair_lab.py:87](src/repair_lab.py:87)). The second gate reads
the literal from D3. Its universe is `plan["source_row_ids"]`, so rows the
collapse dropped are not in the set being checked. It never reads `accounts`.

There is no input on which it returns `False`. `make test` asserts exactly this
([test_visible.py:28](tests/test_visible.py:28)), so green means only that a
constant-valued function returned its constant.

### D6 — Row-level `saved_brand_kit_id` overrides the customer's selection  *(root cause)*

[repair_lab.py:81-86](src/repair_lab.py:81):
`account.get("saved_brand_kit_id", brand_kit_id)`. Nine list-1 rows carry
`brand-kit-2019-legacy` / `template-legacy-blast`, producing 36 deliverables in
a brand the customer did not choose. All nine are singleton rows, so this count
is stable across page sizes; the brand defect and the dedup defect do not
interact. List 2 has no `saved_*` keys at all, which is one reason the two lists
do not produce the same shape of answer.

Latent, not triggered by either fixture: `.get(key, default)` returns `None`
when the key is present with a null value, which would stamp the string `"None"`
as a brand kit id.

### D7 — Reporting artefacts  *(symptom only)*

`distinct company_id in plan` counts the null bucket as one company and counts
same-domain siblings as separate; it is not a company count in either
direction. The check's message counts `len(observed_rows)`, a set, so it would
understate a plan with repeated row ids. `demo.py` runs the check against a
separate default-page-size plan ([demo.py:70](demo.py:70)), which is why it
reports 214 while the page_size=100 column shows 211. `README.md:20` says 217
rows; the file has 223, and 223 minus the 6 null-id rows is 217, which suggests
the README quotes a count taken after those rows were already lost. Noted, not
proven.

---

## 4. How many logical companies this upload represents

**209 logical companies, all 209 campaigned**, reported as
`209 = 203 keyed + 6 provisional`, with 4 of the 203 carrying an open merge
question.

Two questions have to be kept apart here, and an earlier draft of this roadmap
conflated them:

- **Which rows are the same company?** Answerable for all 223 rows.
- **Does that company have a stable external key?** No, for 6 of them.

A missing `company_id` is a missing *key*, not an unresolved *identity*. Each of
the six keyless rows is unique in the upload on name and on domain, and collides
with no other row on either:

```
row-2401  Halverson Freight      / halverson-freight.example
row-2402  Pell & Sons Ironworks  / pellsons.example
row-2403  Cobalt Ridge Dental    / cobaltridge.example
row-2404  Northgate Tutoring     / northgate-tutoring.example
row-2405  Riverbend Cold Storage / riverbend-cold.example
row-2406  Aster Point Realty     / asterpoint.example
```

So they are unambiguously six distinct companies and they get campaigned. What
they do not get is a fabricated `company_id`. That is the actual defect in D2:
not that the rows were campaigned, but that `str(None)` invented a shared key
for them. The remedy is to stop inventing the key, not to refuse the work.

```
203  distinct non-null company_id values
+ 6  rows with no company_id, each a distinct business by name and domain
= 209
```

Every field in the fixture was tested as a candidate key. Each one fails, and
each failure is demonstrated by rows in the file:

| Field | Failure | Proof |
|---|---|---|
| `id` | false split | row-1017 / row-1201: same company_id, same domain, two ids |
| `company_id` | false merge | six `null` rows collapse to `"None"` |
| `company_id` | false split | row-1020 / row-1213 share `northwind-energy.example`, two ids |
| `company_name` exact | false split | row-1092 / row-1204 / row-1205: `Sable Works` / `SABLE WORKS` / `SABLE WORKS Inc` |
| `company_name` normalized | fragile | `Copperline Group` strips to `copperline`, the prefix shared by 10 distinct copperline-* companies |
| `domain` | false merge | `copperline-group.example` carries `company-copperline-group` (row-1093, row-1206) and `company-copperline-energy` (row-1217) |
| `domain` | false split | row-1066 / row-1216 share `company-kestrel-robotics` across `kestrel-robotics.example` and `kestrel-group.example` |
| `segment` | not identity | 12 values across 223 rows |
| `saved_*` | not identity | campaign config; 214 rows share its absence |

Normalized name was not disproved by any row pair in this file, and I will not
claim it was. It is rejected on structure: twenty token families exist where the
legal name ends in what a normalizer treats as a suffix, sitting beside 9-14
siblings that share the leading token. It survives this file by luck of which
names are present.

**The rule:** `company_id` is authoritative where present, and is the only field
permitted to merge two rows. Where it is absent, no key may be synthesised and
no merge may occur: the row stands as its own company under a provisional
identity derived from the row itself, and its deliverables carry
`company_id: null` explicitly rather than any stand-in value. Provisional
identity is scoped to this upload. It is sufficient to campaign the row and
insufficient to de-duplicate it against a future one, and the report says so.

**Why not a neighbouring number:**

- not 204 (today's `distinct company_id`) — counts the null bucket as one and loses five
- not 207 (domain alone) — merges Copperline Energy into Copperline Group, splits Kestrel Robotics
- not 206 (merge the three `-emea` pairs into their parents) — each carries its own company_id, its own name, and one carries its own brand kit; a shared domain is weak evidence against three explicit identifiers
- not 205 (206 plus the copperline domain link) — row-1217 is a data error, not a merge signal

Defensible band 205-209. I ship 209, all campaigned, with four rows flagged for
human resolution (row-1213, row-1214, row-1215, row-1217) and six carrying
provisional identity (row-2401 through row-2406). Nothing is withheld from the
customer on the grounds of a null field.

`fixtures/failure-traces.jsonl` line 4 records `"source_row_count": 209` from a
prior run. Suggestive corroboration; the same trace also claims completion after
reading 67 rows, so it is not treated as evidence.

**Second list, same rule:** 97 distinct non-blank `company_id` + 2 blank-id rows
= **99**, all campaigned, 97 keyed and 2 provisional (`srow-1114`, `srow-1115`,
both unique on name and domain). No domain there carries two company_ids and no
row carries a `saved_brand_kit_id`, so list 2 needs the provisional-identity
path but neither the ambiguity band nor the brand caveat. That is why the two lists do not produce the same
shape of answer, and the check must be able to say so without either list being
special-cased.

---

## 5. Definition of "complete"

> **A request is complete when the scan is provably terminal, and the plan
> covers every logical company in the upload exactly once, with the four
> required asset types, in the brand kit and template named on the request, with
> every deliverable traceable to an uploaded row and no fabricated identifiers.
> If any part of that cannot be established, the outcome is `incomplete` with a
> reason — never a plan that reports success.**

Today `complete` is a property the plan asserts about itself. It must become a
relation between the plan and the upload, checkable by a function that reads
both. The definition above decomposes into six conditions, each enforceable
independently:

1. **The scan is terminal.** The source proved it reached the end: cursors
   strictly advanced, no page was served twice, and the final page reported not
   truncated. If any of these cannot be established, the outcome is
   `incomplete` with a reason, not a plan.
2. **Every logical company is present exactly once**, under the identity rule in
   section 4, where "logical company" is computed from the accumulated rows, not
   from a page. This means all 209 for list 1 and all 99 for list 2. A company
   whose rows carry no `company_id` is still a logical company and is still
   covered; a missing key is never grounds for omitting it.
3. **Every company has exactly the four required asset types**, checked against
   the resolved company set rather than against whatever the plan happens to
   contain.
4. **Every deliverable carries the brand kit and template named on the
   request.** No exceptions. `saved_brand_kit_id` and `saved_template_id` on an
   uploaded row never take effect. The check asserts equality against
   `request.brand_kit.id` and `request.template.id` for every deliverable and
   fails on any mismatch. Rows carrying a stored override are counted and named
   in the report as a data-quality observation; being reported does not make an
   override permissible, and there is no path by which one passes the check.
5. **Every deliverable traces to at least one uploaded row**, and every uploaded
   row is accounted for as campaigned, or merged into another row (naming the
   survivor and the reason).
6. **No deliverable carries a fabricated identifier.** A row with no
   `company_id` is campaigned under a provisional identity and its deliverables
   record `company_id: null` explicitly. `str(None)`, `""` and any other
   stand-in are failures. The report states how many companies hold provisional
   identity and that those cannot be de-duplicated against a future upload.

Conditions 1-6 are enforceable without knowing anything about these two files.

---

## 6. Work plan

Ordered by evidence value per unit of time. Each item is labelled for whether it
removes a cause or hides a symptom.

**W1 — Make the check read the upload.** *(removes cause: D5)*
Rewrite `evaluate_campaign_coverage` against conditions 2-6. It already has
`accounts` in its signature, so this needs no new plumbing. Expected result:
`make test` turns red on the unmodified plan builder. That red run is the first
real evidence in the repository and goes into DECISIONS.md with its output.
Doing this first means every later fix is measured by a check that can fail.

**W2 — Move identity resolution out of the paging loop.** *(removes cause: D1)*
Accumulate raw rows during the scan; resolve identity once over the full set
afterwards. Expected result: rows campaigned becomes identical at page_size 10,
25 and 100 for both lists. This is the check the customer can run themselves.

**W3 — Make the key explicit and refuse to invent one.** *(removes cause: D2)*
Merge only on `company_id`. Rows without one are campaigned as their own company
under a provisional identity and are never merged with anything, including each
other. Deliverables for those rows record `company_id: null` rather than a
stand-in. Merges record the surviving row and the absorbed rows so every
uploaded row is accounted for.

**The two fixtures disagree on how a missing key is written, and neither
contains the other's form:**

```
fixtures/target_accounts.json : {'null': 6}
fixtures/second_list.json     : {'empty string': 2}
```

A fix that handles `null` passes `make demo` and silently fabricates a key on
`make verify`. A fix that handles `""` does the reverse. A fix that enumerates
exactly those two forms is a fit to these two files and violates the
no-special-casing constraint in TASK.md. So the criterion is not a value list,
it is a predicate.

**Predicate.** A row has a usable key if and only if `company_id` is present,
is a string, and is non-empty after stripping whitespace. Everything else —
absent key, `null`, `""`, whitespace-only, non-string — is *no key*, handled by
one branch with no per-form logic.

**Acceptance criteria for W3.** Each is an assertion, not an observation. All
run through the `AccountPageLoader` interface, several against loaders the test
supplies itself, which TASK.md permits.

- **AC1 — Representation independence.** A synthetic single-page list of four
  rows whose `company_id` values are, respectively, absent, `null`, `""`, and
  `"   "`, with four distinct names and domains, resolves to **4 companies, 4
  provisional, 16 deliverables**. Failing on any one form fails AC1. This list
  is built in the test; it is not added to `fixtures/`, and it deliberately
  contains two forms that appear in neither shipped fixture.

- **AC2 — Keyless rows never merge.** In AC1's list, no two of the four rows
  share a resolved identity. Extended case: two rows with `null` and two with
  `""`, all four distinct on name and domain, resolve to 4 companies, not 1 and
  not 2. This is the assertion that fails today, where `str(None)` and `str("")`
  each collapse their group.

- **AC3 — No fabricated identifier reaches output.** For every deliverable in
  every plan built in the suite, `company_id` is either a non-empty stripped
  string or explicitly `null`. It is never `"None"`, `""`, `"null"`, `"nan"`, or
  whitespace. This is the assertion that catches a reintroduced `str()` call
  even if the counts happen to come out right.

- **AC4 — Both shipped fixtures, one code path.** No branch anywhere keys on
  filename, row count, or a literal from either file.

  | list | companies | keyed | provisional | rows accounted for |
  |---|---|---|---|---|
  | `target_accounts.json` | 209 | 203 | 6 | 223 / 223 |
  | `second_list.json` | 99 | 97 | 2 | 115 / 115 |

- **AC5 — Page-size invariance.** For both fixtures, at page_size 1, 10, 25,
  100 and 1000, the company count, the provisional count and the deliverable
  count are identical. page_size 1 is included deliberately: it puts every row
  in its own page, so any surviving page-scoped merge logic produces the maximum
  possible duplicate count and cannot pass by luck.

- **AC6 — Every uploaded row accounted for.** The campaigned set and the merged
  set are disjoint and their union has exactly `len(accounts)` members. No row
  is absent from both. This is what today's collapse violates silently, losing 9
  rows on list 1 at page_size 25 and 12 at page_size 100.

- **AC7 — Traceability holds through a merge.** Every deliverable's
  `source_row_id` is a row id from the upload, and for every merged group the
  report names the surviving row and each absorbed row. A merge that discards
  `row-1201` must still be able to say `row-1201` was absorbed into `row-1017`.

**Mutation check.** Reintroducing `str(row["company_id"])` must fail AC2 and
AC3. Restoring the page-scoped `seen` set must fail AC5 and AC6. If a change can
be reverted without turning the suite red, the criterion above it is not doing
any work and should be rewritten rather than kept for appearance.

**W4 — Derive `complete` from the scan.** *(removes cause: D3, D4)*
Track cursor monotonicity, repeated pages, and the terminal condition inside the
loop. Return an explicit incomplete outcome with a reason instead of a plan when
the list cannot be read. Cover all five classes in `src/sources.py`, asserting
`incomplete` for `SilentlyShort`, `Stalling`, `Cycling` and
`TruncatedWithoutCursor`, and a correct de-duplicated plan for `Replaying`.

**W5 — Make the request's brand kit and template win, unconditionally.**
*(removes cause: D6)*
Drop the `account.get("saved_brand_kit_id", brand_kit_id)` fallback entirely.
Every deliverable is stamped from the request. The nine rows carrying
`brand-kit-2019-legacy` are named in the report as a data-quality observation
with no effect on output. Expected result on list 1: the brand-kit breakdown
becomes a single line, `brand-kit-meridian-2026` for every deliverable, and the
36 wrong-brand deliverables go to zero. If the product later decides a stored
override should win, that is a change to the request contract and to the check
together, not a silent per-row fallback.

**W6 — Report the shape, not one integer.** *(removes cause: D7 in part)*
`make demo` and `make verify` report companies campaigned, of which keyed and
provisional, plus rows merged, rows carrying a stored brand override, and the
completeness verdict with its reason. Keep both commands working, as TASK.md
requires.

**If time runs out**, W1 and W2 are the minimum defensible submission: a check
that can fail, and a count that stops moving with page size. W5 and W6 are the
first things I cut. I would rather ship four items with evidence than six
without.

**Explicitly a symptom fix if done alone:** globally de-duplicating the finished
plan without moving resolution out of the loop would stabilise the numbers while
leaving identity coupled to transport. It would look like W2 in the demo output
and is not the same change. If time forces that shortcut, it will be described
as what it is.

---

## 7. Why this holds for the next list

Nothing above keys on a value that appears in either fixture. No count is
hardcoded. The identity rule is stated as a policy about fields, not about
names. `make verify` exists to catch a fit to one file, and W2 has a prediction
that either list can falsify: the campaigned count must not vary with page size.
List 2 is the useful control precisely because its duplicates straddle different
boundaries and it has no `saved_*` fields, so a fix tuned to list 1's shape will
show up there as a difference.

The two lists are expected to report different shapes, and the check must state
that difference rather than smooth it over: list 1 as 209 campaigned (203 keyed,
6 provisional, 4 flagged for the merge question, 9 rows carrying a stored brand
override that was ignored), list 2 as 99 campaigned (97 keyed, 2 provisional, 0
flagged, 0 overrides).

---

## 8. Uncertain, and out of scope

**Uncertain.**

- Whether the three `-emea` rows are subsidiaries or regional duplicates. I
  count them as separate and flag them. This is the 209-versus-206 question and
  it is a customer decision, not a code decision.
- Whether row-1217 (`Copperline Energy` on `copperline-group.example`) is a typo
  in the domain or in the company_id. Flagged, not resolved.
- Whether a row-level `saved_brand_kit_id` was ever meant to win. I have decided
  it does not: the customer selected a brand kit on the request and nine rows
  quietly overrode it, which is one of the three things they complained about.
  If product disagrees, that is a deliberate change to the request contract and
  to condition 4 together.
- The external identity of the six keyless rows. They are campaigned as six
  distinct companies on the strength of unique name and unique domain within
  this upload. That is enough to produce their creative and not enough to
  recognise them in the customer's next upload. The customer has to supply a
  `company_id` for the deliverables to be attributable beyond this run.
- One rule would flip the six from campaigned to withheld: a product constraint
  that no deliverable may ship without a CRM key. Nothing in `TASK.md`,
  `fixtures/request.json` or the customer's note states such a rule, and the
  request says "every company in the uploaded list", so I campaign them. This is
  the single decision in this roadmap most likely to be wrong, and it moves six
  companies.

**Out of scope.**

- `t-4c08` in the failure traces: an `image_search` timeout and a template cache
  cold start, unrelated to anything the customer reported. TASK.md says not to
  repair behaviour that cannot be tied to the complaint.
- Fuzzy or probabilistic entity resolution. Section 4 shows normalized names are
  unsafe here, and a scoring model is not defensible in the time available or
  auditable by the customer.
- The `README.md:20` row-count discrepancy: recorded in D7, not investigated.
- Concurrency, retry policy, and anything about how the real service pages. The
  constraint is that whatever is built copes with all five recorded shapes; it
  is not to fix the service.
