# RW Dashboard KPI Intelligence

Generated from `scripts/sales/rw_kpi_graph.py`, `rw_page_kpi_contract.py`, and the local semantic-model definition.

## Rollup

- Total RW KPIs: 31
- Surfaced cleanly on dashboard pages: 14
- Surfaced but still partial: 6
- Model-available but not clearly surfaced: 3
- Partial data or measure gap: 3
- Source-data gap: 5

Cardinal rule: ARR is Land+Expand only; Renewal ACV is Renewal only. The only cross-motion value measure remains `Total Open Pipeline Value`.

`KG Source Status` comes from the canonical RW KPI graph. `Dashboard Status` reflects the deployed model measures and current page contract.

## Immediate Upgrade Lanes

Fast page-only upgrades; the model already has the measure, but the dashboard does not clearly surface it:
- `sales_cycle_length`: Add to Stage Hygiene as cycle-time companion to time-in-stage.
- `closed_won_avg_deal_size`: Add to Growth Mix as value-tier / deal-size strip.
- `lost_arr_quarterly`: Add to Renewals as loss waterfall / reason table.

Semantic/model upgrades; a page exists or the KPI is close, but the current visual is still proxy/incomplete:
- `pipeline_coverage_3x`: Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `stage3_approvals_compliance`: Add Commercial Approval compliance measure; current Stage Hygiene page only shows Stage 3 flow proxies.
- `forecast_accuracy`: Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `existing_arr_run_rate`: Needs Asset/Subscription base; keep as Renewals caveat until staged.
- `indexation_arr_growth`: Needs indexation/contract uplift field; keep as Renewals caveat until staged.
- `synergy_deals_won`: Needs synergy flag; current Growth Mix page uses Land won count as a proxy.
- `synergy_deals_pipe`: Needs synergy flag; then add open/won synergy strip to Growth Mix.
- `business_at_risk`: Needs account/subscription health flag; then add to Renewals.
- `saas_arr_yoy_growth`: Needs SaaS deployment field; likely Product/Pricing future page.

Source-data upgrades; these need ETL/source-field work before a real dashboard visual can be trusted:
- `closed_won_value_tier`: Add DAX value-tier measures or a calculated tier column, then surface on Growth Mix.
- `commercial_approval_to_close_time`: Needs Commercial Approval date in ETL; then add to Stage Hygiene.
- `cross_sell_to_acquired`: Needs Axioma/acquired-account flag; then add to Growth Mix.
- `one_off_revenues`: Needs one-off/PS product fields; likely Product/Pricing future page.
- `ps_arr_attach`: Needs PS/license product split; likely Product/Pricing future page.

## KPI Matrix

| KPI | Impact | Motion | KG Source Status | Dashboard Status | Pages | Measures | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `forecast_closed_won` | HIGH | land_expand | exists | surfaced | VP Ops Scorecard, What Changed, Forecast | Total Closed Won ARR, Closed Won ARR YoY Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `pipeline_coverage_3x` | HIGH | land_expand | partial | surfaced_partial | Forecast | Total Open Pipeline ARR (missing: Pipeline Coverage Ratio) | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| `opp_win_rate` | HIGH | land_expand | exists | surfaced | VP Ops Scorecard | Win Rate ARR, Win Rate Count | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `stage_conversion` | HIGH | land_expand | partial | surfaced | VP Ops Scorecard, What Changed, Stage Hygiene | Stage Forward Pct (LE), Stage Backward Pct (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `opp_age` | MEDIUM | land_expand | missing | surfaced | What Changed | Avg Open Opp Age Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `opp_source_effectiveness` | MEDIUM | land_expand | missing | surfaced | Growth Mix | Source ARR Won, Source Win Rate | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `sales_cycle_length` | HIGH | land_expand | exists | model_available_not_surfaced | - | Avg Sales Cycle Days, Land Avg Sales Cycle Days | Add to Stage Hygiene as cycle-time companion to time-in-stage. |
| `time_in_stage` | MEDIUM | land_expand | missing | surfaced | VP Ops Scorecard, Stage Hygiene | Avg Days In Prior Stage (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `closed_won_avg_deal_size` | HIGH | land_expand | partial | model_available_not_surfaced | - | Avg Deal Size Won | Add to Growth Mix as value-tier / deal-size strip. |
| `closed_won_value_tier` | MEDIUM | land_expand | missing | source_data_gap | - | - | Add DAX value-tier measures or a calculated tier column, then surface on Growth Mix. |
| `new_opps_by_region` | MEDIUM | land_expand | missing | surfaced | VP Ops Scorecard, What Changed | New Opps Created, New Opps Count 7d | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `stage3_approvals_compliance` | MEDIUM | land_expand | partial | surfaced_partial | Stage Hygiene | Stage 3 Forward Pct, Avg Days In Stage 3 (missing: Commercial Approval Compliance Pct) | Add Commercial Approval compliance measure; current Stage Hygiene page only shows Stage 3 flow proxies. |
| `stage3_acv_value` | MEDIUM | land_expand | missing | surfaced | Forecast | Stage 3 Plus ARR, S3 Plus Open ACV | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `commercial_approval_to_close_time` | HIGH | land_expand | missing | source_data_gap | - | - (missing: Commercial Approval To Close Days) | Needs Commercial Approval date in ETL; then add to Stage Hygiene. |
| `forecast_accuracy` | HIGH | land_expand | exists | surfaced_partial | Forecast | Forecast Slip Pct, Forecast Slips, Forecast Upgrades (missing: Forecast Accuracy) | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |
| `partner_opps_pct` | MEDIUM | land_expand | missing | surfaced | Growth Mix | Partner ARR, Partner Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `renewal_retention_rate` | HIGH | renewal | partial | surfaced | VP Ops Scorecard, Renewals | Renewal Retention Pct (Period) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `renewals_mom_trend` | HIGH | renewal | exists | surfaced | Renewals | Total Open Renewal ACV, Total Renewal ACV Won | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `existing_arr_run_rate` | HIGH | renewal | missing | surfaced_partial | Renewals | - (missing: Existing ARR Run Rate) | Needs Asset/Subscription base; keep as Renewals caveat until staged. |
| `indexation_arr_growth` | MEDIUM | renewal | missing | surfaced_partial | Renewals | - (missing: Indexation ARR Growth) | Needs indexation/contract uplift field; keep as Renewals caveat until staged. |
| `ilf_arr_pipeline` | HIGH | land_expand | partial | surfaced | Growth Mix | Open Expand ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `alf_arr_pipeline` | HIGH | land_expand | partial | surfaced | Growth Mix | Open Land ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `new_customer_reporting` | HIGH | land_expand | missing | surfaced | Growth Mix | Total Land Won Count, Total Land Won ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `cross_sell_to_acquired` | HIGH | land_expand | missing | source_data_gap | - | - (missing: Cross Sell To Acquired ARR) | Needs Axioma/acquired-account flag; then add to Growth Mix. |
| `synergy_deals_won` | HIGH | land_expand | partial | surfaced_partial | Growth Mix | Total Land Won Count (missing: Synergy Deals Won) | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |
| `synergy_deals_pipe` | MEDIUM | land_expand | partial | partial_data_or_measure_gap | - | - (missing: Synergy Deals Pipeline) | Needs synergy flag; then add open/won synergy strip to Growth Mix. |
| `lost_arr_quarterly` | HIGH | renewal | partial | model_available_not_surfaced | - | Total Renewal ACV Lost | Add to Renewals as loss waterfall / reason table. |
| `business_at_risk` | HIGH | renewal | partial | partial_data_or_measure_gap | - | - (missing: Business At Risk ARR) | Needs account/subscription health flag; then add to Renewals. |
| `one_off_revenues` | MEDIUM | all | missing | source_data_gap | - | - (missing: One Off Revenues) | Needs one-off/PS product fields; likely Product/Pricing future page. |
| `ps_arr_attach` | MEDIUM | land_expand | missing | source_data_gap | - | - (missing: PS ARR Attach Pct) | Needs PS/license product split; likely Product/Pricing future page. |
| `saas_arr_yoy_growth` | HIGH | all | partial | partial_data_or_measure_gap | - | - (missing: SaaS ARR YoY Growth) | Needs SaaS deployment field; likely Product/Pricing future page. |

## High-Impact Follow-Up Queue

- `pipeline_coverage_3x`: Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `sales_cycle_length`: Add to Stage Hygiene as cycle-time companion to time-in-stage.
- `closed_won_avg_deal_size`: Add to Growth Mix as value-tier / deal-size strip.
- `commercial_approval_to_close_time`: Needs Commercial Approval date in ETL; then add to Stage Hygiene.
- `forecast_accuracy`: Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `existing_arr_run_rate`: Needs Asset/Subscription base; keep as Renewals caveat until staged.
- `cross_sell_to_acquired`: Needs Axioma/acquired-account flag; then add to Growth Mix.
- `synergy_deals_won`: Needs synergy flag; current Growth Mix page uses Land won count as a proxy.
- `lost_arr_quarterly`: Add to Renewals as loss waterfall / reason table.
- `business_at_risk`: Needs account/subscription health flag; then add to Renewals.
- `saas_arr_yoy_growth`: Needs SaaS deployment field; likely Product/Pricing future page.
