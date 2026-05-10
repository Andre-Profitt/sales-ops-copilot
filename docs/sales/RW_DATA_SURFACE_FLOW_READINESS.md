# RW Data-to-Surface Flow Readiness

Verdict: `not_exec_complete`.

No, the dashboard is not fully done yet. It is guarded and inspectable, but the data/schema-to-BI flow is not complete enough to call it a finished executive operating system.

## What We Have

- Canonical KPI graph: `31` RW KPIs.
- Cleanly surfaced KPIs: `26`.
- Surfaced partial/proxy KPIs: `4`.
- Model/measure gaps: `1`.
- Source-data gaps: `0`.
- Semantic model: `9` tables, `127` measures, `11` relationships.
- Page contract: `7` executive pages covering `30` KPI IDs.
- Unit policy: `EUR M`; visual display-unit scaling is forbidden.
- Guardrails: ARR/Renewal ACV separation, page-specific slicer policy, unit policy, visual QA, semantic-filter audit, Zebra visual/schema benchmarks.

## What Is Still Necessary

| Lane | Need | Why |
| --- | --- | --- |
| unit policy | Keep every monetary visual on EUR M; forbid visual/theme display-unit scaling. | Mixed K/M/MM/BMM labels make executive reads look ungoverned and can double-scale values. |
| semantic model | Add transition-date roles for stage and forecast movements. | Close FQ is a cohort selector; it is not the same as movement-period filtering. |
| target/plan data | Stage quota/target denominator for Pipeline Coverage Ratio. | Open pipeline numerator is surfaced, but 3x coverage cannot be executive-grade without quota. |
| forecast data | Stage ForecastingItem/snapshot history for true forecast accuracy. | Current Forecast page uses slip/upgrade proxies, not accuracy versus submitted forecast. |
| renewal base data | Find and stage a populated indexation/uplift source. | Active-base ARR and active-base risk are now modeled from asset line items; indexation/uplift remains unpopulated. |
| growth segmentation | Stage a trusted Synergy flag. | Axioma, SaaS, PS attach, and one-off/non-recurring revenue are now modeled; Synergy remains report/name-filter only. |
| BI surface | Add controlled drill paths from Scorecard -> exception ledger -> owner/account/opportunity detail. | The pages answer executive questions, but the action flow is not yet as strong as a boardroom operating review. |

## High-Impact Blockers

| KPI | Status | Pages | Measures present | Missing | Next action |
| --- | --- | --- | --- | --- | --- |
| `pipeline_coverage_3x` | surfaced_partial | Forecast | `Total Open Pipeline ARR` | `Pipeline Coverage Ratio` | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| `forecast_accuracy` | surfaced_partial | Forecast | `Forecast Slip Pct`, `Forecast Slips`, `Forecast Upgrades` | `Forecast Accuracy` | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |
| `synergy_deals_won` | surfaced_partial | Growth Mix | `Total Land Won Count` | `Synergy Deals Won` | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |

## Medium Flow Gaps

| KPI | Status | Next action |
| --- | --- | --- |
| `synergy_deals_pipe` | partial_data_or_measure_gap | Needs synergy flag; then add open/won synergy strip to Growth Mix. |

## Definition Of Done

1. No critical/high semantic-filter findings.
2. No high-impact RW KPI remains proxy-only unless explicitly descoped in the exec narrative.
3. Transition-date semantics exist before adding richer stage/forecast period flows.
4. Forecast, indexation/uplift, and Synergy gaps are either staged or clearly excluded from the dashboard scope.
5. Unit audit has zero high/critical findings; every monetary measure reads in one unit.
6. The BI surface supports an action flow from headline exception to account/opportunity detail without ARR/ACV blending.
