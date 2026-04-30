# CODEX review — 2026-04-30

Scope: `sales-ops-copilot` only, with targeted validation against the current `brand-deck-agent-py` consumer schema and the generated `state/2026-Q2/Jesper-Tyrer/` artifacts.

## FX addendum

Post-review live probes against Salesforce changed one important conclusion:

- `APTS_Opportunity_ARR__c` is **not** stored in EUR at the record level. Example from `2026-04-30`: APAC opp `CIC - F2M` carries `CurrencyIsoCode=USD`, `APTS_Opportunity_ARR__c=2,151,608.60`, `convertCurrency(...)=1,875,448.77`.
- `APTS_Renewal_ACV__c` is also **not** stored in EUR at the record level. Example: renewal `ATP - Renewal 2026 EMIR` carries `CurrencyIsoCode=DKK`, `APTS_Renewal_ACV__c=1,479,431`, `convertCurrency(...)=198,022.60`.
- However, on the live probes I ran in this org on `2026-04-30`, `SUM(APTS_Opportunity_ARR__c)` and `SUM(APTS_Renewal_ACV__c)` matched the EUR-converted totals, not the raw transactional-currency sums. So the broad claim "headline SOQL SUM is definitely FX-wrong" is **not supported by current evidence in this org**.
- The remaining live FX bug is still real in **filter logic**, not headline summation: `WHERE APTS_Opportunity_ARR__c >= 500000` misclassifies non-EUR Expand deals against a EUR-denominated approval threshold, and `convertCurrency(...)` cannot be used in the `WHERE` clause.

## Findings

### Block — the repo's own contract layer is still pinned to schema v1, so the current smoke gate is red

- **Refs:** `scripts/land_brief.py:806-835`, `scripts/schema.py:43-54`, `tests/test_land_brief_contract.py:30`, `tests/test_land_brief_contract.py:116-125`
- **What is wrong:** `build_trends_envelope()` emits schema `"2.0"` plus v2 fields (`scope_label`, `display_label`, `action_items`, named per-deal arrays), but the in-repo Pydantic mirror still accepts only `"1.0"`, and the contract tests still assert `"1.0"`. On the current repo state, `python3 -m pytest tests/test_land_brief_contract.py -v` fails 2 of 5 tests for that reason.
- **Why it matters:** the main local regression gate is already broken, so future schema drift will be hard to distinguish from known red noise. This is a release blocker for anything that depends on contract confidence.
- **Suggested fix:** either update `scripts/schema.py` to the real v2 contract or delete the duplicate mirror and import the consumer schema directly in tests. Then change the tests to validate the live v2 envelope, not the retired v1 shape.
- **Verification note:** the current consumer-side schema in `brand-deck-agent-py` now round-trips successfully after its `2026-04-30 12:42` fix; the remaining drift is local to this repo.

### High — two action-item rules never execute in production because the SOQL is invalid, and the run degrades silently

- **Refs:** `scripts/land_brief.py:898-915`, `scripts/land_brief.py:1015-1038`, `scripts/land_brief.py:1041-1064`
- **What is wrong:** both `_pull_zombie_for_director()` and `_pull_activity_drought_for_director()` use `Id NOT IN (SELECT WhatId FROM Task ...)` / `Event ...` semi-joins. Salesforce rejects these with `MALFORMED_QUERY: Entity 'Task' is not supported for semi join inner selects`. `pull_director_action_data()` catches the exception, logs a warning, and continues, so the deck is generated with incomplete `action_items`.
- **Why it matters:** the generated monthly action queue is missing exactly the stale-pipeline rules that are supposed to surface zombie deals and activity drought. This is silent under-reporting, not a cosmetic warning.
- **Suggested fix:** replace the Task/Event semi-join with a supported approach:
  1. query candidate opp IDs first, then subtract recent Task/Event `WhatId`s in Python, or
  2. pull a supported last-activity field into `Data` and drive both rules from that.
  Also mark skipped rules explicitly in the envelope/brief or fail the run if a rule cannot execute.
- **Evidence:** the Salesforce-backed Jesper smoke run succeeded only with warnings, and direct query replay reproduced the `MALFORMED_QUERY`.

### High — the Commercial Approval action rule is FX-incorrect for non-EUR books

- **Refs:** `scripts/land_brief.py:952-970`
- **What is wrong:** `_pull_approval_gap_for_director()` filters on `APTS_Opportunity_ARR__c >= 500000` in SOQL, then sums `convertCurrency(APTS_Opportunity_ARR__c)` after the fact. The threshold is a EUR business rule, but the filter is applied in each opportunity's transactional currency.
- **Why it matters:** APAC, UKI, Canada, MEA, Nordics, and other non-EUR books can over- or under-include Expand deals around the `EUR 500k` gate. That makes the action queue policy-incorrect even though the monetary totals are FX-correct.
- **Suggested fix:** query the stage-qualified population with `convertCurrency(APTS_Opportunity_ARR__c) arr_fx` and apply the `>= 500000` threshold in Python on `arr_fx`, matching the safer pattern already used in `pending_commercial_approval`.

### High — `Sales_Velocity` mixes Renewal outcomes into the win-rate input while the rest of the KPI is Land+Expand-specific

- **Refs:** `scripts/excel_model.py:2004-2068`
- **What is wrong:** row `B2` counts open Land+Expand opps, row `B4` averages closed-won Land+Expand ARR, and row `B5` measures Land+Expand cycle days, but row `B3` computes win rate from all `ClosedCFQ_IsWon` outcomes without a `Type IN (Land, Expand)` filter. The note at `2034-2035` explicitly says it includes Renewal.
- **Why it matters:** directors with renewal-heavy closed-Q activity get a velocity coefficient that is mathematically mixing two different motions with different denominators and cycle shapes.
- **Suggested fix:** add `ClosedCFQ_Type` criteria to row `B3` so the win-rate component uses Land+Expand only, or split the KPI into explicit new-business and renewal velocity metrics.

### High — the think-cell/template contract is out of sync with the live workbook, so several slides will be wired to the wrong shape or wrong meaning

- **Refs:** `scripts/build_land_template.py:201-216`, `scripts/build_land_template.py:266-295`, `scripts/build_land_template.py:332-382`, `docs/THINKCELL_SETUP.md:71-84`, `scripts/excel_model.py:1642-1684`, `scripts/excel_model.py:1691-1735`, `scripts/excel_model.py:1919-1973`, `scripts/excel_model.py:2004-2068`, `scripts/excel_model.py:2105-2188`, `scripts/excel_model.py:2323-2388`
- **What is wrong:** multiple placeholder/runbook ranges no longer match the workbook they tell the operator to bind:
  - Slide 12 expects `Retention!A1:C5` with NRR, GRR, churn, expansion, and net change, but the actual `Retention` sheet is a 2-column GRR-proxy block only.
  - Slide 17 expects `Territory_Performance` to expose `Country / # Opps / ARR / % of book`, but the actual sheet is `# / Country / # Opps / Open ARR`.
  - Slide 18 describes `Wins_Losses_QTD` column D as `Avg cycle days`, but the actual sheet uses column D for Renewal ACV.
  - Slide 23 expects `Sales_Velocity!B7` delta and swaps the meaning of `B3` and `B4`; the actual sheet has no `B7`.
  - Slide 24 expects `Account_Expansion!A1:E16`, but the actual sheet has 6 columns including rank.
  - Slide 22 describes stale activity as "no logged activity in 60d", while the model sheet is explicitly a `CreatedDate > 60` proxy.
- **Why it matters:** this is the monthly refresh path. Right now a careful operator following the runbook can still wire the wrong chart, and a fast operator almost certainly will.
- **Suggested fix:** choose one truth source and reconcile to it immediately:
  1. either change the workbook to match the published deck contract, or
  2. rewrite the template placeholders and runbook to match the workbook exactly.
  Then add a validator that asserts sheet names, headers, and expected bindable ranges before shipping artifacts.

### Medium — `--period` is still not plumbed into the Salesforce extraction path, so historical reruns are not reproducible

- **Refs:** `scripts/land_brief.py:179`, `scripts/land_brief.py:195-197`, `scripts/land_brief.py:274-277`, `scripts/land_brief.py:390-392`, `scripts/land_brief.py:594-596`, `scripts/land_brief.py:1030-1032`
- **What is wrong:** the workbook formulas respect the requested quarter via `period_start` / `period_end`, but the source data pull still uses `THIS_QUARTER`, `LAST_N_DAYS:180`, `LAST_N_DAYS:365`, and action-rule windows relative to today.
- **Why it matters:** rerunning `--period 2025-Q4` on April 30, 2026 does not reconstruct a 2025-Q4 snapshot; it reconstructs today's snapshot and labels it as 2025-Q4. That is an audit problem, not just a backlog nicety.
- **Suggested fix:** derive absolute date bounds from `period` once and reuse them in every SOQL query and every date-driven sheet that currently calls `date.today()`.

### Medium — `Account_Expansion` is vulnerable to account-name normalization drift

- **Refs:** `scripts/excel_model.py:2141-2178`
- **What is wrong:** the top-15 seed and all downstream `SUMIFS` use exact `AccountName` string equality. Any trailing whitespace, doubled spacing, or Salesforce name variant splits the same account into multiple rows.
- **Why it matters:** this is exactly the kind of quiet bad math that will survive formula recalc and look plausible in the deck.
- **Suggested fix:** normalize account keys once on ingest (`strip`, collapse internal whitespace, optionally casefold) and use the normalized key consistently for ranking plus `SUMIFS`-compatible helper columns.

### Low — disclaimer text is no longer internally consistent about AI usage

- **Refs:** `scripts/excel_model.py:206-214`, `scripts/land_brief.py:1248-1250`, `agent/land_system_prompt.py:50-56`
- **What is wrong:** the workbook cover says "no AI processing of client data", while the prompt and architecture docs correctly state that per-deal data is allowed in the LLM-bound envelope under the enterprise Claude contract.
- **Why it matters:** if anyone reads across artifacts, the policy story is contradictory.
- **Suggested fix:** change the cover copy to say the workbook itself is formula-driven and local, while the broader pipeline may route per-deal context through approved enterprise Claude surfaces.

## Architecture take

Do **not** collapse the two-workbook split yet.

The query volume is acceptable for a monthly job: the current design is roughly 11 director-scoped queries plus 3 shared report pulls, which is not the pressing problem. The real issue is contract instability. Until the named-account slides either migrate cleanly into `land.model.xlsx` or the legacy/model boundary gets a validator, collapsing the workbooks just increases blast radius.

The right move is:

1. fix correctness and contract drift first,
2. add a workbook/deck validator,
3. then decide whether the remaining legacy sheets are worth migrating.

## Ranked punch list

1. Fix the local schema mirror/tests to the real v2 envelope and make the round-trip gate green again.
2. Replace the invalid Task/Event semi-join rules and fail loud if an action rule is skipped.
3. Make the Commercial Approval threshold FX-correct by evaluating the `EUR 500k` rule on converted values.
4. Reconcile `build_land_template.py` + `docs/THINKCELL_SETUP.md` against the actual workbook ranges and metric semantics.
5. Plumb `--period` into every SOQL date window and remove `date.today()` from any sheet meant to be historically reproducible.
6. Fix `Sales_Velocity` so every component is Land+Expand-only.
7. Normalize account keys before ranking or `SUMIFS`-based expansion analysis.
8. Add tests for:
   - v2 envelope round-trip,
   - action-rule query validity,
   - workbook header/range contract for bindable sheets,
   - named-range presence in `land.model.xlsx`,
   - one end-to-end Jesper smoke artifact check.

## Verification run

- `./.venv/bin/python scripts/model_recalc.py state/2026-Q2/Jesper-Tyrer/land.model.xlsx` → passed, 3596 computed cells, no formula errors.
- `python3 -m pytest tests/test_land_brief_contract.py -v` → failed (`2` of `5`) on stale schema v1 assertions.
- `./.venv/bin/python scripts/build_land_template.py` → rebuilt `assets/LAND_template.pptx` with `28` slides.
- `./.venv/bin/python scripts/land_brief.py --director "Jesper Tyrer" --period 2026-Q2` → succeeded only after unsandboxed Salesforce access; emitted warnings for the broken zombie/activity-drought rules above.
