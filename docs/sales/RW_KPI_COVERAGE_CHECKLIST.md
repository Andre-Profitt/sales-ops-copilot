# RW KPI Coverage Checklist

Generated from `scripts/sales/rw_kpi_graph.py`, `rw_dashboard_intelligence.py`, and the executable page KPI contract.

## Coverage Answer

- RW expected KPIs: 31
- Cleanly covered on BI: 26 / 31
- Usable on BI including partial/proxy coverage: 30 / 31
- Not dependable yet: 1 / 31
- Model/measure gaps: 1
- Source-data gaps: 0

Cardinal guardrail: ARR is Land + Expand only; Renewal ACV is Renewal only. Total Open Pipeline Value is the only explicitly labeled cross-motion value.

Checklist legend: `[x]` covered, `[~]` partial/proxy on BI, `[ ]` not dependable yet.

## Master Checklist

| Check | KPI | RW expects | Impact | Motion | BI coverage | Pages | Measure evidence | Gap / next action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [x] | `forecast_closed_won` | Forecast & Closed Won; target Baseline +10% YoY | HIGH | land_expand | Covered | VP Ops Scorecard, What Changed, Forecast | Total Closed Won ARR, Closed Won ARR YoY Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [~] | `pipeline_coverage_3x` | Pipeline Value / Pipeline Coverage; target 3x Coverage | HIGH | land_expand | Partial/proxy on BI | Forecast | Total Open Pipeline ARR; missing: Pipeline Coverage Ratio | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| [x] | `opp_win_rate` | Opportunity Win Rate (Close Rate); target >25% | HIGH | land_expand | Covered | VP Ops Scorecard | Win Rate ARR, Win Rate Count | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `stage_conversion` | Opportunity Stage Conversion Rate; target >70% stage-to-stage | HIGH | land_expand | Covered | VP Ops Scorecard, What Changed, Stage Hygiene | Stage Forward Pct (LE), Stage Backward Pct (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `opp_age` | Opportunity Age / Stale Opportunities; target <120 days avg | MEDIUM | land_expand | Covered | What Changed | Avg Open Opp Age Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `opp_source_effectiveness` | Opportunity Source Effectiveness; target Track & Optimize | MEDIUM | land_expand | Covered | Growth Mix | Source ARR Won, Source Win Rate | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `sales_cycle_length` | Sales Cycle Length (Avg Time to Close); target <90 days | HIGH | land_expand | Covered | Stage Hygiene | Avg Sales Cycle Days, Land Avg Sales Cycle Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `time_in_stage` | Time deals spent in each stage; target Baseline & Optimize | MEDIUM | land_expand | Covered | VP Ops Scorecard, Stage Hygiene | Avg Days In Prior Stage (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `closed_won_avg_deal_size` | Closed Won Average Deal Size by month; target >$500K | HIGH | land_expand | Covered | Growth Mix | Avg Deal Size Won | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `closed_won_value_tier` | Number of close won deals by value tier; target Track distribution | MEDIUM | land_expand | Covered | Growth Mix | Closed Won Deals Count | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `new_opps_by_region` | Number of New opportunities created by region; target 100/month | MEDIUM | land_expand | Covered | VP Ops Scorecard, What Changed | New Opps Created, New Opps Count 7d | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `stage3_approvals_compliance` | Stage 3 approvals by month; target 100% compliance | MEDIUM | land_expand | Covered | Stage Hygiene | Commercial Approval Compliance Pct, Stage 3 Forward Pct, Avg Days In Stage 3 | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `stage3_acv_value` | ACV of Stage 3 approvals; target Track & Monitor | MEDIUM | land_expand | Covered | Forecast | Stage 3 Plus ARR, S3 Plus Open ACV | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `commercial_approval_to_close_time` | Commercial approval to close time; target <30 days | HIGH | land_expand | Covered | Stage Hygiene | Commercial Approval To Close Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [~] | `forecast_accuracy` | Forecast Accuracy; target ±5% | HIGH | land_expand | Partial/proxy on BI | Forecast | Forecast Slip Pct, Forecast Slips, Forecast Upgrades; missing: Forecast Accuracy | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |
| [x] | `partner_opps_pct` | Partner Opportunities; target 20% of pipeline | MEDIUM | land_expand | Covered | Growth Mix | Partner ARR, Partner Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `renewal_retention_rate` | Renewals per quarter detailing term length; target 95% retention | HIGH | renewal | Covered | VP Ops Scorecard, Renewals | Renewal Retention Pct (Period) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `renewals_mom_trend` | Renewals by month over year; target Track & Trend | HIGH | renewal | Covered | Renewals | Total Open Renewal ACV, Total Renewal ACV Won | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `existing_arr_run_rate` | Existing ARR (Run Rate) Indexed; target Track & Monitor | HIGH | renewal | Covered | Renewals, Product Retention | Existing ARR Run Rate | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [~] | `indexation_arr_growth` | ARR growth attributed to indexation by Quarter; target 2-3% annually | MEDIUM | renewal | Partial/proxy on BI | Renewals, Product Retention | missing: Indexation ARR Growth | Needs indexation/contract uplift field; keep as Renewals caveat until staged. |
| [x] | `ilf_arr_pipeline` | ILF ARR Pipes By Quarter; target $X Million | HIGH | land_expand | Covered | Growth Mix | Open Expand ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `alf_arr_pipeline` | ALF ARR By Quarter; target $X Million | HIGH | land_expand | Covered | Growth Mix | Open Land ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `new_customer_reporting` | New Customer reporting amount by month and value and region; target Track & Report | HIGH | land_expand | Covered | Growth Mix | Total Land Won Count, Total Land Won ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `cross_sell_to_acquired` | ARR from Cross Selling to Acquired Business; target $X Million | HIGH | land_expand | Covered | Growth Mix | Cross Sell To Acquired ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [~] | `synergy_deals_won` | Synergy deals close won; target 10 deals/quarter | HIGH | land_expand | Partial/proxy on BI | Growth Mix | Total Land Won Count; missing: Synergy Deals Won | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |
| [ ] | `synergy_deals_pipe` | Synergy deals in pipe; target 30 deals/quarter | MEDIUM | land_expand | Model/measure gap | - | missing: Synergy Deals Pipeline | Needs synergy flag; then add open/won synergy strip to Growth Mix. |
| [x] | `lost_arr_quarterly` | Lost ARR By Quarter (with reason); target <5% annually | HIGH | renewal | Covered | Renewals | Total Renewal ACV Lost | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `business_at_risk` | Business At Risk By Quarter; target <10% of ARR | HIGH | renewal | Covered | Renewals, Product Retention | Business At Risk ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `one_off_revenues` | One Off Revenues by Quarter; target Track & Monitor | MEDIUM | all | Covered | Growth Mix | One Off Revenues | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `ps_arr_attach` | PS ARR by Quarter; target 15% attach rate | MEDIUM | land_expand | Covered | Growth Mix | PS ARR Attach Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| [x] | `saas_arr_yoy_growth` | SaaS ARR by Quarter; target Growth >20% YoY | HIGH | all | Covered | Growth Mix | SaaS YoY Growth Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |

## High-Impact Gap Queue

- `pipeline_coverage_3x` (HIGH, land_expand): Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `forecast_accuracy` (HIGH, land_expand): Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `synergy_deals_won` (HIGH, land_expand): Needs synergy flag; current Growth Mix page uses Land won count as a proxy.

## Partial/Proxy BI Coverage

- `pipeline_coverage_3x` (HIGH, land_expand): Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `forecast_accuracy` (HIGH, land_expand): Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `indexation_arr_growth` (MEDIUM, renewal): Needs indexation/contract uplift field; keep as Renewals caveat until staged.
- `synergy_deals_won` (HIGH, land_expand): Needs synergy flag; current Growth Mix page uses Land won count as a proxy.

## Model/Measure Gaps

- `synergy_deals_pipe` (MEDIUM, land_expand): Needs synergy flag; then add open/won synergy strip to Growth Mix.

## Source-Data Gaps

- None.
