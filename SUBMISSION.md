# Submission

- Transcript (file or link): transcript.jsonl
- `make demo` output:
  - king@Mac 01-campaign-audit % make demo
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
- `make test` output:
  - PYTHONPATH=src python3 -m unittest discover -s tests -v
test_four_missing_key_forms_resolve_to_four_companies (test_acceptance.AC1RepresentationIndependence.test_four_missing_key_forms_resolve_to_four_companies)... ok
test_non_string_key_is_treated_as_missing (test_acceptance.AC1RepresentationIndependence.test_non_string_key_is_treated_as_missing) ... ok
test_keyed_rows_still_merge (test_acceptance.AC2KeylessRowsNeverMerge.test_keyed_rows_still_merge) ... ok
test_two_nulls_and_two_empties_are_four_companies (test_acceptance.AC2KeylessRowsNeverMerge.test_two_nulls_and_two_empties_are_four_companies) ... ok
test_no_deliverable_in_either_fixture_carries_a_stand_in (test_acceptance.AC3NoFabricatedIdentifiers.test_no_deliverable_in_either_fixture_carries_a_stand_in) ... ok
test_provisional_deliverables_carry_an_explicit_null (test_acceptance.AC3NoFabricatedIdentifiers.test_provisional_deliverables_carry_an_explicit_null) ... ok
test_counts (test_acceptance.AC4BothShippedFixtures.test_counts) ... ok
test_counts_do_not_move_with_page_size (test_acceptance.AC5PageSizeInvariance.test_counts_do_not_move_with_page_size) ... ok
test_campaigned_and_merged_partition_the_upload (test_acceptance.AC6EveryUploadedRowAccountedFor.test_campaigned_and_merged_partition_the_upload) ... ok
test_absorbed_row_is_named (test_acceptance.AC7TraceabilityThroughAMerge.test_absorbed_row_is_named) ... ok
test_every_deliverable_cites_an_uploaded_row (test_acceptance.AC7TraceabilityThroughAMerge.test_every_deliverable_cites_an_uploaded_row) ... ok
test_both_sides_of_the_pair_are_flagged (test_acceptance.AmbiguousIdentityIsFlagged.test_both_sides_of_the_pair_are_flagged)
Not just the later row. Nothing says which one is wrong. ... ok
test_flag_uses_every_row_not_just_the_surviving_one (test_acceptance.AmbiguousIdentityIsFlagged.test_flag_uses_every_row_not_just_the_surviving_one)
company-copperline-energy resolves to copperline-energy.example but ... ok
test_list_one_flags_four_domains_and_eight_companies (test_acceptance.AmbiguousIdentityIsFlagged.test_list_one_flags_four_domains_and_eight_companies) ... ok
test_list_two_needs_no_ambiguity_band (test_acceptance.AmbiguousIdentityIsFlagged.test_list_two_needs_no_ambiguity_band) ... ok
test_review_flag_does_not_withhold_the_campaign (test_acceptance.AmbiguousIdentityIsFlagged.test_review_flag_does_not_withhold_the_campaign) ... ok
test_check_does_not_take_the_plan_at_its_word (test_checker.TheCheckCatchesABrokenPlan.test_check_does_not_take_the_plan_at_its_word)
A plan built from half the upload, checked against all of it. ... ok
test_dropped_company_fails (test_checker.TheCheckCatchesABrokenPlan.test_dropped_company_fails) ... ok
test_duplicated_asset_type_fails (test_checker.TheCheckCatchesABrokenPlan.test_duplicated_asset_type_fails)
A set comparison would miss this. A sorted-list comparison does not. ... ok
test_empty_plan_fails (test_checker.TheCheckCatchesABrokenPlan.test_empty_plan_fails)
The regression that motivated all of this. ... ok
test_fabricated_company_id_fails (test_checker.TheCheckCatchesABrokenPlan.test_fabricated_company_id_fails)
What a reintroduced str(company_id) would produce. ... ok
test_incomplete_scan_fails (test_checker.TheCheckCatchesABrokenPlan.test_incomplete_scan_fails) ... ok
test_missing_asset_type_fails (test_checker.TheCheckCatchesABrokenPlan.test_missing_asset_type_fails) ... ok
test_silently_dropped_row_fails (test_checker.TheCheckCatchesABrokenPlan.test_silently_dropped_row_fails)
A row that is neither campaigned nor recorded as merged. ... ok
test_spuriously_flagged_company_fails (test_checker.TheCheckCatchesABrokenPlan.test_spuriously_flagged_company_fails) ... ok
test_unflagged_ambiguous_company_fails (test_checker.TheCheckCatchesABrokenPlan.test_unflagged_ambiguous_company_fails)
The plan must flag what the upload implies, not fewer. ... ok
test_untraceable_deliverable_fails (test_checker.TheCheckCatchesABrokenPlan.test_untraceable_deliverable_fails) ... ok
test_wrong_brand_kit_fails (test_checker.TheCheckCatchesABrokenPlan.test_wrong_brand_kit_fails) ... ok
test_wrong_template_fails (test_checker.TheCheckCatchesABrokenPlan.test_wrong_template_fails) ... ok
test_baseline (test_checker.TheCheckPassesACorrectPlan.test_baseline) ... ok
test_replaying_loader_matches_the_clean_read (test_sources.ScanRecoversFromARetriedPage.test_replaying_loader_matches_the_clean_read) ... ok
test_cycling_loader_is_incomplete (test_sources.ScanRefusesWhatItCannotRead.test_cycling_loader_is_incomplete) ... ok
test_none_of_them_exhaust_the_source_page_budget (test_sources.ScanRefusesWhatItCannotRead.test_none_of_them_exhaust_the_source_page_budget)
sources.py raises RuntimeError at 400 pages. Reaching that would ... ok
test_stalling_loader_is_incomplete (test_sources.ScanRefusesWhatItCannotRead.test_stalling_loader_is_incomplete) ... ok
test_truncated_without_cursor_is_incomplete (test_sources.ScanRefusesWhatItCannotRead.test_truncated_without_cursor_is_incomplete) ... ok
test_an_independent_copy_of_the_upload_rejects_it (test_sources.ShortReadIsNotDetectableFromThePagingInterface.test_an_independent_copy_of_the_upload_rejects_it) ... ok
test_silently_short_loader_looks_fine_to_the_scan (test_sources.ShortReadIsNotDetectableFromThePagingInterface.test_silently_short_loader_looks_fine_to_the_scan) ... ok
test_the_published_plan_covers_the_upload (test_visible.SuppliedEvaluatorSmokeTest.test_the_published_plan_covers_the_upload) ... ok

----------------------------------------------------------------------
Ran 38 tests in 0.055s

OK
- The one thing you found yourself rather than took from the agent:
  -   Widening the ambiguity rule. The roadmap named four rows and the agent implemented exactly those. Naming only the later row of each pair assumes the later row is the mistake, and nothing in the upload supports that. Separately, the agent wrote that `SilentlyShortLoader` leaves 103 rows unread, I traced the stop condition by hand and it is 98.
- The claim in this submission you are least sure of, and how you checked it:
  -   That the six keyless rows are six distinct companies rather than duplicates of rows already present under another name. I checked that none of their names or domains collides with any other row in either list. They ship under a key that cannot merge, so the error would surface as a duplicate campaign rather than a silent omission, which is the direction I would
  rather be wrong in.
- Anything a reviewer should know before opening the repository:
  - I tend to utilize agents in a create-delete-recreate pipeline, which looks to have the agent finish implementing the entire roadmap, before I manually start reviews and changes on a per-commit basis. So each commit is more so an organizational decision as opposed to a linear set of commits. I find that this method of iterating works best because it allows the agent to work top down, giving it a better perspective than tunnel visioning on one specific feature and having to work with tech debt when a new feature is introduced.
