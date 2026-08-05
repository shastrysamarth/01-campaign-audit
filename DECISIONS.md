# Decisions

Short notes are fine. Fill this in before you submit.

- Time actually spent:
- How many logical companies this upload represents, and why that number and
not a neighbouring one:
- What changed between your roadmap and what you shipped:
  - Sequencing. ROADMAP.md section 6 orders the work W1 first, so that a check
    able to fail would measure every fix after it. That is not how it ran. W2
    was done on its own, then W1 and W3-W6 were implemented in a single pass.
    The per-fix commits in this repository were produced afterwards by a
    create-delete-recreate pipeline: the finished files were copied aside, the
    tree was reset to the pre-fix state, and each W was recreated and committed
    in dependency order (W2, W4, W3, W5, W1, W6) so that each fix has its own
    rollback point. The commits are a reconstruction of the work, not a
    recording of it. Every commit was run before it was made and its output is
    quoted in its message, but no intermediate state was reached independently,
    and the mutation testing that justifies the fixes was run once against the
    finished code rather than per fix.
  - The ambiguity band. ROADMAP.md section 4 ships 209 with four rows flagged
    for human resolution (row-1213, row-1214, row-1215, row-1217) and predicts
    a 199/4/6 split. What shipped flags **8 companies across 4 domains**, and
    the split is reported as 203 keyed + 6 provisional with 8 of the 209
    needing review. The rule is: any domain carrying more than one resolved
    identity flags every identity on it. Naming only the later row of each pair
    assumed the later row was the mistake, and nothing in the upload supports
    that - on `copperline-group.example` either `company-copperline-group` or
    `company-copperline-energy` could be the error. Both are flagged and a
    person decides.
  - The first implementation of W1-W6 omitted the band entirely and reported
    only keyed and provisional, which dropped one of the customer's three named
    complaints. It was added afterwards in commit d4be890 and is not covered by
    the roadmap's acceptance criteria, which predate it.
- What you had the coding agent do, and where you overrode it:
- What your change guarantees, and what it only makes more likely:
  - Completeness is not expressible in this protocol, and no amount of care in
    the reader fixes that. `ToolPage` carries `rows`, `next_cursor` and
    `truncated`. A source that stops early and reports success emits exactly
    the same page sequence as one that reached the end of the list: a final
    page with `truncated=False` and no cursor. There is nothing to probe past
    and nothing to contradict. `SilentlyShortLoader` returns 125 of 223 rows
    and is indistinguishable from a clean read. So `complete: True` is a claim
    no loader in `src/sources.py` can support, and no reader built on this
    interface can verify.
  - What the scan does guarantee is narrower and stated as such: a cursor that
    advances, a source claiming more rows supplying a way to ask for them, and
    termination. Those catch `StallingLoader`, `CyclingLoader` and
    `TruncatedWithoutCursorLoader`, because each contradicts itself in the
    metadata. A short read contradicts nothing.
  - `evaluate_campaign_coverage` appears to catch the short read, and an
    earlier version of its docstring claimed it did. That claim was wrong and
    has been corrected. It only catches it because `demo.py` and the tests hand
    it the uploaded JSON read from disk, independently of the loader. Fed from
    the same paginated source the plan was built from, both sides of the
    comparison would be short by the same rows and the check would agree with
    the lie. Requiring `plan["complete"]` is a consistency check on the scan's
    own findings, not independent evidence.
  - What would fix it: a `total_rows` field on `ToolPage`, declared by the
    source on every page. The scan could then assert that the rows it
    accumulated match the total the source declared, and a short read would
    become a detectable contradiction rather than a silent one. That is a
    change to the account service's contract, not to this repository, so it is
    out of scope here and recorded as the thing that would make completeness
    auditable.
- What you fixed at the cause, and what you only stopped from showing:
- For at least one defect: the command that demonstrated it, pasted with its
output, before your fix and after:
- What you chose not to fix:
  - **The mirror ambiguity case.** `needs_review` flags a domain carrying more
    than one identity. It does not flag one identity spanning more than one
    domain. `company-kestrel-robotics` holds row-1066 on
    `kestrel-robotics.example` and row-1216 on `kestrel-group.example` and is
    campaigned unflagged; `company-copperline-energy` has the same shape but is
    caught incidentally by the domain rule. One real company in list 1 is
    silently merged across two domains. This is the single most valuable thing
    left undone - it is the same complaint from the other side, and the fix is
    an `identities_spanning_domains()` mirroring `ambiguous_domains()`.
  - **`total_rows` on `ToolPage`.** See the completeness note above. Would turn
    a short read from undetectable into a contradiction.
  - **Merge conflict reporting.** Every duplicate group in both fixtures
    disagrees on a field, and the surviving row's values win silently.
    `merged_row_ids` records which rows were absorbed but not what was
    discarded - `ALDER HEALTH` vs `Alder Health`, `kestrel-group.example` vs
    `kestrel-robotics.example`. A per-merge field-conflict list would let the
    customer see what the system chose on their behalf.
  - **A review decision file.** `needs_review` is computed and printed on every
    run, but a human answer cannot be recorded and replayed. Without it the
    same 8 companies are re-flagged forever and the band never converges. A
    decisions file mapping identity pairs to merge/keep, applied after
    resolution and asserted by the check, closes the loop.
  - **Row-id uniqueness is assumed, not enforced at build time.**
    `_drop_replayed_rows` and the `row:{id}` provisional identity both depend on
    unique row ids. The check reports duplicates, the builder does not. Two
    keyless rows sharing an id would merge into one company before the check
    ever saw them.
  - **Deliverables have no stable identifier and no provisional marker.** A
    consumer must infer provisional status from `company_id is None`, and there
    is no `deliverable_id` for idempotent republishing.
  - **An incomplete scan discards everything it read.** For `StallingLoader` the
    100 rows already retrieved are thrown away. Returning them as an explicitly
    unpublishable partial would let a person decide.
  - **`MAX_CURSOR_SERVINGS = 2` is an unexamined policy constant.** It tolerates
    exactly one replay because `ReplayingLoader` does exactly one. A source that
    retried twice would be rejected as stalled. It should be a named argument
    with the trade-off stated, not a module constant.
- What you are still unsure about, including anything that came up during the
session and stayed open:



### Issues:  
  

king@Samarths-MacBook-Pro 01-campaign-audit % make demo

PYTHONPATH=src python3 [demo.py](http://demo.py)

list                          : fixtures/target_accounts.json

uploaded rows                 : 223

brand kit selected on request : brand-kit-meridian-2026

template selected on request  : template-abm-q3

                                  page_size=10    page_size=25   page_size=100

rows campaigned                            214             214             211

deliverables                               856             856             844

distinct company_id in plan                204             204             204

complete flag                             True            True            True

deliverables by brand kit (page_size=25):

  brand-kit-2019-legacy                36

  brand-kit-meridian-2026             820

shipped check returned        : True

shipped check said            : all 214 campaigned rows have the requested asset types

king@Samarths-MacBook-Pro 01-campaign-audit % make verify

PYTHONPATH=src python3 [demo.py](http://demo.py) --list fixtures/second_list.json

list                          : fixtures/second_list.json

uploaded rows                 : 115

brand kit selected on request : brand-kit-meridian-2026

template selected on request  : template-abm-q3

                                  page_size=10    page_size=25   page_size=100

rows campaigned                            103             100              98

deliverables                               412             400             392

distinct company_id in plan                 98              98              98

complete flag                             True            True            True

deliverables by brand kit (page_size=25):

  brand-kit-meridian-2026             400

shipped check returned        : True

shipped check said            : all 100 campaigned rows have the requested asset types

king@Samarths-MacBook-Pro 01-campaign-audit % make test

PYTHONPATH=src python3 -m unittest discover -s tests -v

test_supplied_evaluator_accepts_the_published_plan (test_visible.SuppliedEvaluatorSmokeTest.test_supplied_evaluator_accepts_the_published_plan) ... ok

----------------------------------------------------------------------

Ran 1 test in 0.006s

OK

king@Samarths-MacBook-Pro 01-campaign-audit % 

