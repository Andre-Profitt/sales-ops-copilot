# Codex deep-analysis handoff — sales-ops-copilot LAND-monthly pipeline

**Date:** 2026-04-30 evening · **Branch:** `main` (29 commits ahead of `origin/main`)
**Repo:** `~/code/apps/sales-ops-copilot/` · **Companion repo:** `~/projects/brand-deck-agent-py/` (`feat/land-endpoint`)
**Operator:** Andre (apro@simcorp.com — SimCorp Sales Director monthly review owner)

## TL;DR

The pipeline ingests Salesforce data for 9 SimCorp MD-1 directors, produces per-director auditable Excel models + a SimCorp-branded 28-slide PowerPoint template, and is positioned to wire think-cell datalinks for monthly refresh. Every analytical KPI in the model now traces through Excel formulas back to one of four raw data tables. This session locked in:

- **29-sheet `land.model.xlsx`** with `tblData` + 3 closed-history tables (`tblClosedCFQ`, `tblClosedWon6mo`, `tblRenewals12mo`), all SUMIFS/COUNTIFS-driven
- **28-slide template** (`assets/LAND_template.pptx`) aligned to the canonical 20-slide LAND outline plus 3 Tier-A insight slides (Sales Velocity, Account Expansion, Pipeline Creation Velocity)
- **`feedback_simcorp_enterprise_claude_per_deal_2026-04-30`** memory: per-deal data is allowed throughout (xlsx, envelope, LLM narrative, deck) under SimCorp's enterprise Claude contract
- Schema version drift fixed (was `"1.0"`-string → `2`-int; now `"2.0"` end-to-end)
- think-cell brand style file (`assets/SimCorp-thinkcell-style.xml`) forked from the bundled showcase + ready to embed

## Mission for you

Do a **deep code review** focused on:

1. **Correctness** — formulas resolve to the right numbers; SOQL is FX-correct; no edge cases that break recalc
2. **Robustness** — what breaks if a director has 0 opps in some category, weird Unicode account names, missing fields
3. **Architecture clarity** — is the two-workbook split the right call, or should we collapse into one?
4. **Performance** — `pull_director_snapshot` runs ~12 SOQL queries per director × 9 directors = 108 queries per cron run. Is this efficient?
5. **Test coverage** — `tests/test_land_brief_contract.py` has 5 tests. What's missing? Where would silent regressions hide?
6. **Phase 2 priorities** — given everything below, which deferred items have the highest impact-per-hour ratio?

End with a **concrete punch list** you'd ship next, ranked.

## Reading order (top to bottom)

1. **`docs/ARCHITECTURE.md`** — start here, 2054-word overview of the whole pipeline. 9 sections, written by an audit agent that grepped + read everything.
2. **`scripts/land_brief.py`** (~1240 lines) — orchestrator. SOQL pulls + snapshot dict + `build_trends_envelope` + `derive_action_items` + `render_director_brief`. Read top docstring + the function signatures + scan the `pull_director_snapshot` body.
3. **`scripts/excel_model.py`** (~2280 lines) — formula-driven workbook generator. Read the docstring + `build_director_model` (the orchestrator function) + 1-2 of the `_build_*` analytical sheet functions to understand the formula pattern.
4. **`scripts/excel_companion.py`** (~1380 lines) — legacy precomputed companion. Read top docstring + `SHEET_NAMES` list. Most analytical content is now in the model; this carries named-account list sheets + org-wide external reports.
5. **`scripts/sales_process_graph.py`** (~750 lines) — typed knowledge graph (8 stages, 5 gates, 3 motions, 9 metrics, 8 rules, 25 qualifiers). Cross-project-importable.
6. **`scripts/model_recalc.py`** — Python-only formula evaluator using `formulas` lib. The CI gate.
7. **`scripts/build_land_template.py`** — 28-slide template generator with placeholder rectangles telling humans where to bind think-cell.
8. **`assets/LAND_template.pptx`** — the SimCorp-branded deck (visual inspection in PowerPoint helps)
9. **`assets/SimCorp-thinkcell-style.xml`** — brand style file forked from think-cell's bundled showcase
10. **`docs/THINKCELL_SETUP.md`** — slide-by-slide click-by-click runbook, 28 rows
11. **`docs/SALES_PROCESS_GRAPH.md`** — knowledge-graph design rationale
12. `~/projects/brand-deck-agent-py/agent/land_system_prompt.py` — LLM-side contract (parked; unparks when Foundry → enterprise Claude swap happens)
13. `~/projects/brand-deck-agent-py/agent/land_input_schema.py` — Pydantic envelope schema, `extra=forbid`. Has new `NamedDeal` model + 3 per-deal arrays.

## Memories that locked in policy this session

- `~/.claude/projects/-Users-test/memory/feedback_simcorp_enterprise_claude_per_deal_2026-04-30.md` — per-deal data allowed throughout
- `~/.claude/projects/-Users-test/memory/feedback_deck_llm_substrate_2026-04-29.md` — Foundry deferred, swap to enterprise Claude later
- `~/.claude/projects/-Users-test/memory/feedback_sf_multi_currency_aggregation.md` — SOQL aggregate `convertCurrency` silently does NOT FX-convert; per-record only
- `~/.claude/intel/simcorp-sales-process-2026-04.md` — handbook canonical (8 stages + 5 gates + 3 motions)
- `~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md` — what Claude is licensed for at SimCorp

## Locked contracts (don't restructure without bumping schema_version)

| Contract                                                       | File                                             | Line refs            |
| -------------------------------------------------------------- | ------------------------------------------------ | -------------------- |
| `trends.json` schema (Pydantic, `extra=forbid`)                | `brand-deck-agent-py/agent/land_input_schema.py` | TrendsEnvelope L62   |
| `tblData` columns + named ranges                               | `excel_model.py` `DATA_COLUMNS`                  | L65-83               |
| `tblClosedCFQ` / `tblClosedWon6mo` / `tblRenewals12mo` columns | `excel_model.py` `CLOSED_HISTORY_COLUMNS`        | L371-383             |
| 8-stage process / 5 gates / 3 motions                          | `sales_process_graph.py` `GRAPH`                 | L160+                |
| 9 directors + scope where_clauses                              | `_directors.py`                                  | L25                  |
| 28-slide template structure                                    | `build_land_template.py` `SLIDES`                | L53+                 |
| Slide-to-range bindings                                        | `docs/THINKCELL_SETUP.md`                        | slide-by-slide table |

If you change any of these, every downstream consumer needs review.

## Specific areas for deep analysis

### 1. `pull_director_snapshot` — SOQL query inventory + FX correctness

Around L153-720 in `land_brief.py`. The function fires roughly:

- `detail_q` — open opps in CFQ (Land/Expand/Renewal)
- `beyond_q` — open Land+Expand beyond CFQ
- `wl_q` — closed-this-Q opps
- `roll_q` — closed-won Land+Expand last 180d
- `ret_q` — closed Renewal opps last 365d
- 5 sub-queries inside `pull_org_benchmarks` (regional, win-rate, discount)

**Verify:**

- Every `convertCurrency()` is in the `SELECT` clause (per-record), never inside `SUM()` aggregate (per `feedback_sf_multi_currency_aggregation`)
- All queries scope to the director's `where_clause` correctly
- `THIS_QUARTER` use is intentional (audit-doc finding: `--period` arg is NOT plumbed through to SOQL — TODO at L178)
- No N+1 query anti-patterns inside loops

### 2. `excel_model.py` formula correctness

Especially the new sheets added today (commits `8030f2e`, `310c634`):

- `_build_sales_velocity` (L~1976) — does B5's `=AVERAGE(ClosedWon6mo_CloseDate)-AVERAGE(ClosedWon6mo_CreatedDate)` actually compute days correctly when the AVERAGE picks up dates as Excel serial numbers? Edge case: if `ClosedWon6mo` is empty, does `IFERROR` correctly catch the div-by-zero in B6?
- `_build_account_expansion` (L~2055) — top-15 accounts seeded by Python from `raw_opps`. If the same account name appears with slight whitespace variation, does the SUMIFS still match?
- `_build_pipeline_creation_velocity` (L~2161) — 12-week DATE() bounds. Bug magnet for week-boundary off-by-one.
- `_build_pipe_movement` (L~565-664) — bridge formula `=B6-B2+B4+B5` (closing - opening + won + lost = residual). Verify this is the right algebra: opening + new - won - lost = closing → new = closing - opening + won + lost. ✓ but worth double-checking sign conventions when opening > closing.

### 3. Schema-version reconciliation

Just fixed in commit `310c634`/`b2b392a` (string `"2.0"` end-to-end), but verify:

- `build_trends_envelope` writes `"2.0"` (L805ish)
- `derive_action_items` no longer overwrites (L1234ish)
- Pydantic `TrendsEnvelope.schema_version: Literal["2.0"]` (`brand-deck-agent-py/agent/land_input_schema.py:92`)
- Run a Pydantic round-trip on a Jesper envelope to confirm validation passes

### 4. The two-workbook split — should we collapse?

Currently:

- **`land.model.xlsx`** (29 sheets, formula-driven) — the auditable analytical model
- **`land.xlsx`** (27 sheets, precomputed) — named-account lists (Top_Deals, Pending_Approval, At_Risk_Renewals, Action_Items) + org-wide external reports (Discount_Analysis, Regional_Benchmarks, Region_Trend_8Q)

The deck binds slides 7/8/9/11 to legacy and the rest to model. **Argument FOR collapsing:** single source of truth, no two-workbook gotcha for stakeholders. **Argument AGAINST:** named-account lists are pre-sorted top-N selections that don't fit a SUMIFS pattern cleanly; the org-wide reports come from external SF reports (not raw_opps).

What would you do?

### 5. think-cell datalink stability

The whole monthly refresh story depends on stakeholders not breaking the named-range / sheet-position contract. If someone:

- Renames a sheet
- Inserts a row in `tblData`
- Drops a named range
- Moves the Pipeline_Total!B2 cell

…what breaks? Should we have a contract validator that runs as a CI gate? Look at `model_recalc.py` — does it verify named-range presence in addition to recompute?

### 6. Test coverage

`tests/test_land_brief_contract.py` (5 tests) — what's covered:

1. `test_envelope_has_required_kpis` — total_pipeline_arr + total_renewal_acv present
2. `test_envelope_excludes_blended_kpi` — no `total_blended_pipeline` (the cardinal ARR/ACV-don't-blend rule)
3. `test_envelope_carries_named_per_deal_arrays` — top_deals_named / pending_commercial_approval_named / at_risk_renewals_named present
4. `test_highlights_derived_from_late_stage_concentration` — rule wiring
5. `test_action_items_sorted_by_priority` — high → medium → low ordering

**What's NOT tested:**

- The new analytical sheets in `excel_model.py` (29 sheets, 0 unit tests)
- `model_recalc.py` against synthetic xlsx with errors
- Director scope where_clauses (verified once 2026-04-28, not regression-protected)
- Pydantic round-trip on the envelope
- think-cell named range presence in the model

What test set would you add?

### 7. Compliance posture verification

Per the new memory: per-deal data is allowed everywhere because SimCorp pays for enterprise Claude. Do a sanity check on:

- The disclaimer language across artifacts is consistent (cover sheets, footers, brief.md, agent prompt closing slide)
- The Pydantic schema's `extra=forbid` is genuinely there for hygiene, not as a privacy boundary anymore (i.e., adding fields shouldn't trigger compliance review)
- Hard rules that DO still apply (advisory only, no people-decisions, no regulated work) are surfaced

## Phase 2 backlog (deferred)

Ordered by audit-pass priority:

1. **think-cell wire-once** — open `LAND_template.pptx` in PowerPoint, embed `SimCorp-thinkcell-style.xml`, work through `docs/THINKCELL_SETUP.md` slide-by-slide on Jesper's data (~30 min). Then "Switch to alternate data sources" fan-out for the other 8 directors (~10 min total).
2. **Distribution layer** — SharePoint upload via Graph API (`upload_to_sharepoint.py`). Stakeholders see the deck without manual file-share.
3. **Failure alerts on launchd** — currently logs to `state/land-monthly-cron.log`; nobody knows if the cron silently failed.
4. **`--period` plumbed to SOQL** — currently `THIS_QUARTER` literal. Affects historical reruns.
5. **OFH-driven Pipe_Movement decomposition** — current bridge has a residual "New + Advanced" bucket. OpportunityFieldHistory unblocks proper New / Advanced / Slipped split.
6. **`Competitive_Pressure` SOQL extension** — needs `Lost_to_Competitor__r.Name` in `wl_q`.
7. **True NRR / cohort retention** — needs `Pipeline_Snapshot__c` accumulating 12+ months of historical snapshots (admin-pending deploy).
8. **Action-item close-the-loop ledger** — `state/action_items_history.jsonl` so next month's brief says "5 of 8 last-month HIGH actions resolved."
9. **Migrate remaining legacy sheets to model** — Top_Deals_Land/Expand, Pending_Commercial_Approval, At_Risk_Renewals as named-list-with-formulas pattern; would let us delete `land.xlsx` entirely.

## Smoke-test recipe (how to verify the state yourself)

```bash
cd ~/code/apps/sales-ops-copilot
source .venv/bin/activate

# 1. Regenerate Jesper APAC artifacts
python3 scripts/land_brief.py --director "Jesper Tyrer" --period 2026-Q2

# 2. Verify recalc + headline KPIs
python3 scripts/model_recalc.py state/2026-Q2/Jesper-Tyrer/land.model.xlsx

# 3. Inspect formula cells (should be formulas, not literals)
python3 -c "
from openpyxl import load_workbook
wb = load_workbook('state/2026-Q2/Jesper-Tyrer/land.model.xlsx')
for sheet, cell in [('Pipeline_Total','B2'), ('Sales_Velocity','B5'),
                    ('Forecast_Category','B2'), ('Account_Expansion','B2'),
                    ('Pipeline_Creation_Velocity','B2')]:
    print(f'{sheet}!{cell} = {wb[sheet][cell].value}')
"

# 4. Pydantic round-trip on the envelope
python3 -c "
import sys, json
sys.path.insert(0, '/Users/test/projects/brand-deck-agent-py')
from agent.land_input_schema import TrendsEnvelope
env = json.load(open('state/2026-Q2/Jesper-Tyrer/trends.json'))
TrendsEnvelope.model_validate(env)
print('Pydantic OK')
"

# 5. Run the contract tests
python3 -m pytest tests/test_land_brief_contract.py -v

# 6. Build the template
python3 scripts/build_land_template.py
```

## Out of scope for this review

- Daily brief (`scripts/brief.py`) — separate Azure-OpenAI-using pipeline, different compliance constraints
- Workforce track (`scripts/workforce/`) — track:workforce, separate concern
- `~/code/apps/RevOps-Hub`, `~/crm-analytics` — adjacent repos; ignore for this analysis

## How to deliver your analysis

A markdown report at `~/code/apps/sales-ops-copilot/docs/CODEX_REVIEW_2026-04-30.md` with:

1. Findings (graded by severity: Block / High / Medium / Low / Nit)
2. For each finding: file:line, what's wrong, suggested fix
3. Concrete punch list of next moves, ranked by impact-per-hour
4. Any architecture-level concerns or contrarian takes

Don't commit code changes. Read-only review; we'll triage the findings together.

## Recent commit history (this session, top-of-stack first)

```
b2b392a fix: schema_version Literal["1.0"] -> Literal["2.0"]   (brand-deck-agent-py)
310c634 fix: schema_version drift + ForecastCategoryName flow + CreatedDate in closed-history
7b2be88 docs: lock-in architecture overview
1d56aa7 feat(deck): 28-slide canonical-aligned LAND template
8030f2e feat(model): 7 new analytical sheets — single-source-of-truth lock-in
53cad32 fix: agent prompt + Pydantic schema permit per-deal data per enterprise Claude
0e71da9 fix: envelope + agent prompt now permit per-deal data per enterprise Claude contract
05c12ef docs: reframe code-of-conduct in LAND prompt for internal deck reality (now reversed)
3181c57 docs: reframe code-of-conduct disclaimer for internal-deck reality (now reversed)
1702af2 feat(deck): waterfall + mekko + harvey balls patterns (17 slides)
1f21b61 fix(model): closed-history raw sheets + 5 analytical migrations to formulas
413dc75 feat(deck): named-account enrichments matching Rebekka-approved 2026-04-10 format
```

Branch is `main`, 29 commits ahead of `origin/main`. Not pushed (per existing handoff discipline; will push once the wire-up pass is done).

— end of handoff —
