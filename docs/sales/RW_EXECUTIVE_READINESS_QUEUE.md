# RW Executive Readiness Queue

Last refreshed: 2026-05-11 from the live Fabric report, KPI contract, PBI graph, enterprise gate, and parallel heatmap/churn audits.

## Verdict

The dashboard is inspectable and structurally coherent, but it is not executive-complete yet.

What works:

- The tab architecture mostly makes sense as an RW operating review: control room, movement, forecast, stage hygiene, renewals, product retention, growth mix, and explorer.
- The hard guardrails are in place: ARR is Land + Expand only, Renewal ACV is Renewal only, omitted pipeline is excluded from open/current pipeline, and `Total Open Pipeline Value` is the only labeled cross-motion measure.
- Current live validation is clean for report structure, measure references, visual QA, unit policy, metric-basis labels, and zero-value audit.
- KPI coverage is broad: 26 / 31 RW KPIs cleanly surfaced, 30 / 31 usable including partial/proxy coverage.

What does not work yet:

- Forecast is not executive-grade until `Pipeline Coverage Ratio` and true `Forecast Accuracy` exist.
- Growth Mix is not fully strategic until Synergy won/pipe use a trusted source flag instead of proxy logic.
- Product Retention shows current active-base exposure/risk, not true churn/NRR.
- Several heatmap-labeled visuals are still `tableEx`/data-bar substitutes, not true native matrix heatmaps in Desktop.
- Stage and forecast movement analytics need transition-date roles before richer period slicing is trustworthy.
- The dashboard still lacks a strong action path: Scorecard -> exception ledger -> account/opportunity detail.

## Gate Evidence

| Gate | Result | Meaning |
| --- | --- | --- |
| `rw_validate --live` | passed | 8 sections, 245 visual containers, all measure refs resolve. |
| `visual-qa --source live --fail-on medium` | 0 findings | Current visible layout passes the automated clipping/density/card/table gate. |
| `audit --source live` | no findings | No basic visual finish findings. |
| `unit-policy --source live --fail-on-high` | 0 high/critical | Monetary visuals are governed to EUR M and visual display-unit scaling is blocked. |
| `metric-basis --source live --fail-on high` | 0 findings | Labels expose basis cleanly enough for current pages. |
| `zero-values` | 0 medium/high/critical | No current high-severity source zero-value blocker. |
| `semantic-filter --source live --fail-on high` | medium=2 | Guarded, but stage/forecast transition date roles still need model work. |
| `data-surface-flow --source live` | high=3, medium=1 | Not executive-complete; three high-impact KPI flows remain incomplete. |
| `enterprise-standard --source live` | high=1, medium=1 | Not enterprise-ready because data-to-surface flow is incomplete. |
| `pbi-graph --source live` | high=4, medium=4 | Graph confirms source/model work remains the blocker. |

## Page Read

| Page | Does it answer an executive question? | Current read | Unfinished work |
| --- | --- | --- | --- |
| VP Ops Scorecard | Yes | Strong control-room frame. | Rebuild into a true driver tree after forecast/target gaps close; add controlled drill path. |
| What Changed | Yes | Clear movement and exception ledger. | Add richer change/risk classification and movement-window handling after date roles exist. |
| Forecast | Partial | Correct question, incomplete answer. | Add quota denominator, submitted-forecast snapshots, `Pipeline Coverage Ratio`, `Forecast Accuracy`, and scenario spine. |
| Stage Hygiene | Yes | Clear bottleneck/control-point tab. | Add transition-date role and movement-period semantics; preserve real SimCorp stage order. |
| Renewals | Yes | Renewal ACV and active-base ARR are separated. | Add indexation/uplift source and active-base bridge. |
| Product Retention | Yes, scoped | Current active-base exposure/risk by product/region/segment. | Convert to true heatmaps; add separate Churn/NRR experimental page from historical assets. |
| Growth Mix | Partial | Land, Expand, partner, Axioma, SaaS, PS, one-off are present. | Add trusted Synergy flag, true heatmaps, contribution bridge, and remove proxy status. |
| RW KPI Explorer | Not an exec tab | Useful governed slice-and-dice page. | Add explicit explorer contract or keep it clearly non-executive. |

## Long-Running Queue

### P0. Finish Shared Chrome / Clipping

Status: in flight and published for inspection.

Work:

- Expanded shared page chrome from 84px to 104px.
- Increased title/action/subtitle/nav textbox heights.
- Shifted non-slicer content below the expanded header.
- Adjusted KPI strip label/card spacing so labels do not clip or collide.

Acceptance:

- No non-slicer content starts under the 104px chrome band.
- Chrome textboxes are at least 22px tall.
- Live `visual-qa --fail-on medium` remains 0 findings.

### P0. Replace Fake Heatmaps With Real Native Matrices

Status: not done.

Current issue:

- Product Retention, Growth Mix, and Renewals use `tableEx` visuals with data bars where Desktop should show true heatmap matrices.

Implementation target:

- Convert heatmap surfaces to native `pivotTable`/matrix visuals with row/column axes and field-value cell backgrounds.
- Keep detail ledgers as `tableEx`.
- Preserve ARR/ACV guardrails and do not introduce `Total Open Pipeline Value`.

Files:

- `scripts/sales/rw_compose_product_retention.py`
- `scripts/sales/rw_compose_growth_mix.py`
- `scripts/sales/rw_compose_renewals.py`
- `scripts/sales/rw_zebra_kg_ibcs_synth.py`
- `scripts/sales/rw_native_visual_upgrade_audit.py`
- `tests/sales/test_rw_page_kpi_contract.py`
- `tests/sales/test_rw_zebra_kg_ibcs_synth.py`
- `tests/sales/test_rw_native_visual_upgrade_audit.py`

Acceptance:

- Heatmap visuals are `pivotTable`, not `tableEx`.
- Heatmaps use product/region/segment/risk axes and field-value background color measures.
- Data bars are not counted as heatmaps.
- Visual QA, native visual-upgrade, unit policy, and metric-basis gates stay clean.

### P0. Build Churn / NRR Experimental Tab

Status: not done.

Current issue:

- Product Retention uses current active-base asset data. It does not yet compute longitudinal churn, GRR, or NRR.

Implementation target:

- Build an active-base ARR retention fact at `period_end_date + account_id + product_id`.
- Use asset/effective-dated history, not opportunity ARR and not Renewal ACV.
- Add an experimental tab after Product Retention.

Source:

- `Apttus_Config2__AssetLineItem__c` as primary source.
- `Apttus_Config2__AssetLineItem__History` for audit/reconciliation, not primary ARR math.

Measures:

- `Starting Active-Base ARR`
- `Ending Active-Base ARR`
- `Retained Active-Base ARR`
- `Churn / Downsell ARR`
- `Expansion / Cross-Sell ARR`
- `Net Active-Base ARR Delta`
- `GRR Pct (Experimental)`
- `NRR Pct (Experimental)`
- `Churn / Downsell Pct`

Acceptance:

- Current-period ending active-base ARR ties to existing `Existing ARR Run Rate` within tolerance.
- Tab labels basis as active-base ARR only.
- No `f_opportunity` ARR/ACV measures appear on the churn tab.
- Churn/downsell/expansion/cross-sell classifications are fixture-tested.

### P0. Close Forecast Executive Blockers

Status: not done.

Current issue:

- Forecast shows open ARR numerator and slip proxies, not true coverage/accuracy.

Implementation target:

- Stage quota/target denominator.
- Stage ForecastingItem or forecast snapshots.
- Create `Pipeline Coverage Ratio`.
- Create true `Forecast Accuracy`.
- Rebuild Forecast as scenario spine: closed ARR, open ARR, target/plan, submitted forecast, coverage gap, accuracy.

Acceptance:

- `pipeline_coverage_3x` is clean, not partial.
- `forecast_accuracy` is clean, not proxy.
- Renewal ACV remains separate from Land + Expand ARR.

### P0. Close Growth Mix Synergy Blockers

Status: not done.

Current issue:

- Synergy won/pipe are still proxy/model debt.

Implementation target:

- Stage trusted Synergy flag.
- Create `Synergy Deals Won` and `Synergy Deals Pipeline`.
- Rebuild Growth Mix strategic segmentation with real Synergy rows and contribution bridge.

Acceptance:

- `synergy_deals_won` and `synergy_deals_pipe` are no longer proxy/model gaps.
- Growth Mix does not blend Land + Expand ARR with Renewal ACV or one-off revenue.

### P1. Add Transition-Date Roles

Status: not done.

Current issue:

- `f_stage_transition.transition_at` and `f_forecast_transition.transition_at` have no direct calendar role.
- Close FQ is a cohort selector, not a movement-period selector.

Acceptance:

- Semantic-filter audit has zero medium transition-date findings.
- Movement-period slicers are added only after the model roles exist.

### P1. Upgrade Renewals To Active-Base Bridge

Status: not done.

Current issue:

- Renewals is readable, but it still lacks the Zebra-style base movement story.

Implementation target:

- Active-base ARR -> expiring base -> at-risk base -> won/lost renewal ACV -> retained base.
- Add indexation/uplift only after a populated source exists.

Acceptance:

- Renewal ACV and active-base ARR remain visibly distinct.
- Indexation/uplift is either real or explicitly absent.

### P1. Build Drill / Action Flow

Status: not done.

Implementation target:

- Scorecard lane -> page-level exception ledger -> account/opportunity detail.
- Do not leave pages as disconnected static tabs.

Acceptance:

- Each scorecard decision lane has a deterministic detail target.
- Detail ledgers preserve owner/account/opportunity/product context.

### P1. Recompose VP Ops Scorecard As Driver Tree

Status: not done.

Implementation target:

- Outcome -> gap -> driver lane -> exception queue.
- Cards summarize; bridge/variance tables explain.

Acceptance:

- Scorecard reaches 100% Zebra-native decision-visual coverage.
- Page makes the next management action obvious without reading every tab.

### P2. Contract The Explorer

Status: not done.

Implementation target:

- Mark RW KPI Explorer as governed slice-and-dice, not an executive narrative tab.
- Document allowed slicers and blocked blended measures.

Acceptance:

- Explorer contract exists and is tested.
- Explorer remains free of unlabeled cross-motion values.

## Current Completion Cut

Ready for inspection:

- Shared chrome / banner clipping fix.
- Existing pages as guarded visual review artifacts.

Not ready to call finished:

- Forecast executive truth.
- Growth Mix Synergy truth.
- True heatmaps.
- Churn / NRR.
- Transition-date movement semantics.
- Drill/action flow.
