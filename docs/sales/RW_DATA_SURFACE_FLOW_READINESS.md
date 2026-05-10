# RW Data-to-Surface Flow Readiness

Verdict: `not_exec_complete`.

No, the dashboard is not fully done yet. It is guarded and inspectable, but the data/schema-to-BI flow is not complete enough to call it a finished executive operating system.

## What We Have

- Canonical KPI graph: `31` RW KPIs.
- Cleanly surfaced KPIs: `17`.
- Surfaced partial/proxy KPIs: `6`.
- Model/measure gaps: `3`.
- Source-data gaps: `5`.
- Semantic model: `7` tables, `106` measures, `7` relationships.
- Page contract: `6` executive pages covering `23` KPI IDs.
- Unit policy: `EUR M`; visual display-unit scaling is forbidden.
- Guardrails: ARR/Renewal ACV separation, page-specific slicer policy, unit policy, visual QA, semantic-filter audit, Zebra visual/schema benchmarks.

## What Is Still Necessary

| Lane | Need | Why |
| --- | --- | --- |
| unit policy | Keep every monetary visual on EUR M; forbid visual/theme display-unit scaling. | Mixed K/M/MM/BMM labels make executive reads look ungoverned and can double-scale values. |
| semantic model | Add canonical d_stage and stage keys/order. | Stage visuals need business-order semantics, not label sorting. |
| semantic model | Add transition-date roles for stage and forecast movements. | Close FQ is a cohort selector; it is not the same as movement-period filtering. |
| target/plan data | Stage quota/target denominator for Pipeline Coverage Ratio. | Open pipeline numerator is surfaced, but 3x coverage cannot be executive-grade without quota. |
| forecast data | Stage ForecastingItem/snapshot history for true forecast accuracy. | Current Forecast page uses slip/upgrade proxies, not accuracy versus submitted forecast. |
| approval/process data | Stage Commercial Approval status/date from Apttus or the approved SimCorp source. | Stage 3/approval KPIs are proxy-only without the actual approval event. |
| renewal base data | Stage Asset/Subscription base, existing ARR run-rate, and indexation/uplift fields. | Renewal page can show ACV exposure, but not full renewal economics or retained base quality. |
| growth segmentation | Stage Axioma/acquired, synergy, SaaS, product/PS, and one-off revenue flags. | Growth Mix is credible for Land/Expand/partner today, but not yet the full RW segmentation agenda. |
| BI surface | Add controlled drill paths from Scorecard -> exception ledger -> owner/account/opportunity detail. | The pages answer executive questions, but the action flow is not yet as strong as a boardroom operating review. |

## High-Impact Blockers

| KPI | Status | Pages | Measures present | Missing | Next action |
| --- | --- | --- | --- | --- | --- |
| `pipeline_coverage_3x` | surfaced_partial | Forecast | `Total Open Pipeline ARR` | `Pipeline Coverage Ratio` | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| `commercial_approval_to_close_time` | source_data_gap | - | - | `Commercial Approval To Close Days` | Needs Commercial Approval date in ETL; then add to Stage Hygiene. |
| `forecast_accuracy` | surfaced_partial | Forecast | `Forecast Slip Pct`, `Forecast Slips`, `Forecast Upgrades` | `Forecast Accuracy` | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |
| `existing_arr_run_rate` | surfaced_partial | Renewals | - | `Existing ARR Run Rate` | Needs Asset/Subscription base; keep as Renewals caveat until staged. |
| `cross_sell_to_acquired` | source_data_gap | - | - | `Cross Sell To Acquired ARR` | Needs Axioma/acquired-account flag; then add to Growth Mix. |
| `synergy_deals_won` | surfaced_partial | Growth Mix | `Total Land Won Count` | `Synergy Deals Won` | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |
| `business_at_risk` | partial_data_or_measure_gap | - | - | `Business At Risk ARR` | Needs account/subscription health flag; then add to Renewals. |
| `saas_arr_yoy_growth` | partial_data_or_measure_gap | - | - | `SaaS ARR YoY Growth` | Needs SaaS deployment field; likely Product/Pricing future page. |

## Medium Flow Gaps

| KPI | Status | Next action |
| --- | --- | --- |
| `closed_won_value_tier` | source_data_gap | Add DAX value-tier measures or a calculated tier column, then surface on Growth Mix. |
| `synergy_deals_pipe` | partial_data_or_measure_gap | Needs synergy flag; then add open/won synergy strip to Growth Mix. |
| `one_off_revenues` | source_data_gap | Needs one-off/PS product fields; likely Product/Pricing future page. |
| `ps_arr_attach` | source_data_gap | Needs PS/license product split; likely Product/Pricing future page. |

## Definition Of Done

1. No critical/high semantic-filter findings.
2. No high-impact RW KPI remains proxy-only unless explicitly descoped in the exec narrative.
3. `d_stage` and transition-date semantics exist before adding richer stage/forecast period flows.
4. Forecast, approval, renewal-base, and growth-segmentation source gaps are either staged or clearly excluded from the dashboard scope.
5. Unit audit has zero high/critical findings; every monetary measure reads in one unit.
6. The BI surface supports an action flow from headline exception to account/opportunity detail without ARR/ACV blending.
