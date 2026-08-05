# Decisions

Short notes are fine. Fill this in before you submit.

- Time actually spent: 2.5 Hrs
- How many logical companies this upload represents, and why that number and not a neighbouring one:
  - 209 (203 keyed + 6 provisional); 99 for list 2. Rule: `company_id` where present, no synthesised key where absent. The file disproves the alternatives, `copperline-group.example` carries two company_ids while `company-kestrel-robotics` spans two domains, so domain both false-merges and false-splits. Exact names split `SABLE WORKS` from `Sable Works`. Not 204: `str(None)` fabricates one company from six and drops three at page_size 100. Not 206: nothing merges the `-emea` rows without also merging Copperline Energy into Copperline Group, short of special-casing a token.
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
  - The agent read and implemented. I held it to no edits through the investigation and re-ran every claim. Mine: the `complete: True` constant, put to it as a hypothesis
  to confirm. The dependency graph that exposed the pattern under all seven defects, requiring a row pair as disproof for each candidate key. Overrode it on rule 5 condition 4's "reported exception" loophole, which reintroduced the shipped check's
  tautology into my own spec. Overrode rule 4 shipping 209 while quarantining six companies, the
  103-versus-98 figure, a missing definition of complete, the dropped ambiguity band which I widened from 4 rows to 8 companies, and the checker's short-read claim.
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
  - Cause: W2 takes identity resolution out of the paging loop, so page size no longer feeds a semantic decision. W3 makes the key explicit and never invents one. W4 derives `complete` from the scan. W5 makes the request win. W1 gives the check an
  oracle it can fail against. Symptom: `needs_review` surfaces the eight ambiguous companies without resolving them, and re-flags them every run. `MAX_CURSOR_SERVINGS = 2` tolerates one replay because `ReplayingLoader` does one fitted to an observed shape, and the one fixture-shaped constant here. The roadmap
  pre-registered the plan-level dedup shortcut and the diff shows I did not take it.
- For at least one defect: the command that demonstrated it, pasted with its
output, before your fix and after:
  - Pasted below, the make demo command initially demonstrating erroneous results per page_size, along with incorrectly returning `complete: True`. The after not only ensures page_size invariant results, but also accurate completion checks.
- What you chose not to fix:
  - `t-4c08` — image_search timeout, cache cold start. Ties to nothing the customer reported, so it stays. Fuzzy resolution is rejected because its error mode is over-merge. 
  Other items not touched: 
  - the mirror of the ambiguity rule, which flags one domain carrying two identities but not one
  identity spanning two domains. 
  - Per-merge field conflicts, so the customer can see
  that `ALDER HEALTH` beat `Alder Health` on file order alone
- What you are still unsure about, including anything that came up during the
session and stayed open:
  - 209 versus 206. If the customer treats regional entities as one account, my default is wrong for them, which is why the band is reported rather than resolved. Also the six provisional companies are campaigned under a key that cannot merge, which is a refusal to guess, not an identification.



### Initial Run:

king@Samarths-MacBook-Pro 01-campaign-audit % make demo

PYTHONPATH=src python3 [demo.py](http://demo.py)

list                          : fixtures/target_accounts.json

uploaded rows                 : 223

brand kit selected on request : brand-kit-meridian-2026

template selected on request  : template-abm-q3

```
                              page_size=10    page_size=25   page_size=100
```

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

```
                              page_size=10    page_size=25   page_size=100
```

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

---

Ran 1 test in 0.006s

OK

king@Samarths-MacBook-Pro 01-campaign-audit % 

### Final Run:

king@Mac 01-campaign-audit % make demo
PYTHONPATH=src python3 demo.py
list                          : fixtures/target_accounts.json
uploaded rows                 : 223
brand kit selected on request : brand-kit-meridian-2026
template selected on request  : template-abm-q3

```
                              page_size=10    page_size=25   page_size=100
```

companies campaigned                       209             209             209
  of which keyed                           203             203             203
  of which provisional                       6               6               6
  of which need review                       8               8               8
deliverables                               836             836             836
rows read                                  223             223             223
rows merged into another                    14              14              14
complete flag                             True            True            True

identical at every page size  : True

deliverables by brand kit (page_size=25):
  brand-kit-meridian-2026             836

identity model for this list:
  domains carrying more than one identity : 4
  companies flagged needs_review          : 8
    copperline-group.example
      company_id:company-copperline-energy                 Copperline Energy
      company_id:company-copperline-group                  Copperline Group
    northwind-energy.example
      company_id:company-northwind-energy                  Northwind Energy
      company_id:company-northwind-energy-emea             Northwind Energy EMEA
    sable-fitness.example
      company_id:company-sable-fitness                     Sable Fitness
      company_id:company-sable-fitness-emea                Sable Fitness EMEA
    tessellate-capital.example
      company_id:company-tessellate-capital                Tessellate Capital
      company_id:company-tessellate-capital-emea           Tessellate Capital EMEA

rows carrying a stored brand override, ignored: 9
  row-1014, row-1213, row-1082, row-1084, row-1123, row-1140, ... (+3 more)

coverage check returned       : True
coverage check said           : 209 logical companies in the upload (203 keyed, 6 provisional, 8 needing review); 836 deliverables in the plan
king@Mac 01-campaign-audit % make verify
PYTHONPATH=src python3 demo.py --list fixtures/second_list.json
list                          : fixtures/second_list.json
uploaded rows                 : 115
brand kit selected on request : brand-kit-meridian-2026
template selected on request  : template-abm-q3

```
                              page_size=10    page_size=25   page_size=100
```

companies campaigned                        99              99              99
  of which keyed                            97              97              97
  of which provisional                       2               2               2
  of which need review                       0               0               0
deliverables                               396             396             396
rows read                                  115             115             115
rows merged into another                    16              16              16
complete flag                             True            True            True

identical at every page size  : True

deliverables by brand kit (page_size=25):
  brand-kit-meridian-2026             396

identity model for this list:
  domains carrying more than one identity : 0
  companies flagged needs_review          : 0
    none - every domain in this list resolves to one company,
    so this list needs no ambiguity band at all

rows carrying a stored brand override, ignored: 0

coverage check returned       : True
coverage check said           : 99 logical companies in the upload (97 keyed, 2 provisional, 0 needing review); 396 deliverables in the plan