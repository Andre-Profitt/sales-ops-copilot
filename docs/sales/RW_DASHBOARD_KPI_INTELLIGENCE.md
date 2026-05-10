# RW Dashboard KPI Intelligence

Generated from `scripts/sales/rw_kpi_graph.py`, `rw_page_kpi_contract.py`, and the local semantic-model definition.

## Rollup

- Total RW KPIs: 31
- Surfaced cleanly on dashboard pages: 25
- Surfaced but still partial: 4
- Model-available but not clearly surfaced: 0
- Partial data or measure gap: 1
- Source-data gap: 1

Cardinal rule: ARR is Land + Expand only; Renewal ACV is Renewal only. The only cross-motion value measure remains `Total Open Pipeline Value`.

`KG Source Status` comes from the canonical RW KPI graph. `Dashboard Status` reflects the deployed model measures and current page contract.

## Immediate Upgrade Lanes

Fast page-only upgrades; the model already has the measure, but the dashboard does not clearly surface it:
- None.

Semantic/model upgrades; a page exists or the KPI is close, but the current visual is still proxy/incomplete:
- `pipeline_coverage_3x`: Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `forecast_accuracy`: Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `indexation_arr_growth`: Needs indexation/contract uplift field; keep as Renewals caveat until staged.
- `synergy_deals_won`: Needs synergy flag; current Growth Mix page uses Land won count as a proxy.
- `synergy_deals_pipe`: Needs synergy flag; then add open/won synergy strip to Growth Mix.

Source-data upgrades; these need ETL/source-field work before a real dashboard visual can be trusted:
- `one_off_revenues`: Needs one-off/PS product fields; likely Product/Pricing future page.

## Slice/Dice Explorer

The generated report also includes a native `RW KPI Explorer` page for interactive analysis outside the executive narrative tabs.

- Executive page slicers: Region and Close FQ. Motion is not a page slicer because ARR/Renewal ACV measures enforce motion in DAX.
- Explorer-only slicer: Stage. Motion appears as visual columns where comparison is explicit.
- Explorer views: Land + Expand ARR mix, Renewal ACV exposure, Stage conversion diagnostics, Growth mix and new-customer signal.
- ARR and Renewal ACV remain separate in the explorer; it does not use `Total Open Pipeline Value`.

## Page Decision Target Map

The page contract is executable via `scripts/sales/rw_page_kpi_contract.py`; tests fail if a required KPI loses its page, visual role, motion guardrail, or proxy/gap label.

### VP Ops Scorecard

- Executive question: Where is RW off plan right now, and which lane needs executive action first?
- Primary KPIs: `forecast_closed_won`, `opp_win_rate`, `stage_conversion`, `renewal_retention_rate`
- Secondary diagnostics: `time_in_stage`, `new_opps_by_region`
- Required motion guardrail: `cross_motion_labeled`
- Caveat: Renewal retention is displayed beside ARR KPIs but not blended into ARR.

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `forecast_closed_won` | `Total Closed Won ARR` | hero KPI | `land_expand_arr` | clean | Closed won ARR (Land + Expand) |
| `opp_win_rate` | `Win Rate ARR` | hero KPI | `land_expand_arr` | clean | Win rate (ARR-wtd) |
| `stage_conversion` | `Stage Forward Pct (LE)` | variance table | `land_expand_arr` | partial | Stage hygiene (count rates, Land + Expand) |
| `renewal_retention_rate` | `Renewal Retention Pct (Period)` | hero KPI | `renewal_acv` | partial | Retention % (ACV-wtd) |
| `time_in_stage` | `Avg Days In Prior Stage (LE)` | variance table | `land_expand_arr` | partial | Stage hygiene (count rates, Land + Expand) |
| `new_opps_by_region` | `New Opps Count 7d` | RAG card | `land_expand_arr` | clean | New opp count 7d |

### What Changed

- Executive question: What materially changed in the last operating window, and which open opportunities need inspection?
- Primary KPIs: `new_opps_by_region`, `stage_conversion`, `opp_age`, `forecast_closed_won`
- Secondary diagnostics: None
- Required motion guardrail: `land_expand_arr`
- Caveat: None

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `opp_age` | `At Risk Opps ARR` | exception ledger | `land_expand_arr` | clean | At-risk ARR (Land + Expand) |
| `opp_age` | `Watch Opps ARR` | exception ledger | `land_expand_arr` | clean | Watch ARR (Land + Expand) |
| `stage_conversion` | `Stage Moves ARR 7d` | movement ledger | `land_expand_arr` | clean | Stage ARR (Land + Expand) |
| `new_opps_by_region` | `New Opps Count 7d` | movement ledger | `land_expand_arr` | clean | New opp count |
| `forecast_closed_won` | `Closed Won Count 7d` | movement ledger | `land_expand_arr` | clean | Won count |
| `opp_age` | `Total Open Pipeline ARR` | detail table | `land_expand_arr` | clean | Top Open ARR (Land + Expand) Movement Queue |

### Forecast

- Executive question: Can the quarter still land, and is forecast movement disciplined enough to trust?
- Primary KPIs: `forecast_closed_won`, `pipeline_coverage_3x`, `forecast_accuracy`
- Secondary diagnostics: `stage3_acv_value`
- Required motion guardrail: `cross_motion_labeled`
- Caveat: Total Open Pipeline Value is the only explicit cross-motion value measure.

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `pipeline_coverage_3x` | `Total Open Pipeline Value` | hero KPI | `cross_motion_labeled` | partial | Open Value (ARR+ACV, cross-motion) |
| `forecast_closed_won` | `Total Closed Won ARR` | hero KPI | `land_expand_arr` | clean | Closed won ARR (Land + Expand) |
| `pipeline_coverage_3x` | `Total Open Pipeline Value` | variance table | `cross_motion_labeled` | partial | Stage x Motion Open Value (ARR+ACV) |
| `forecast_accuracy` | `Forecast Slip Pct` | RAG card | `land_expand_arr` | proxy | Slip % (count proxy) |
| `forecast_accuracy` | `Forecast Slips` | RAG card | `land_expand_arr` | proxy | Slip count proxy |
| `stage3_acv_value` | `Total Open Pipeline Value` | detail table | `cross_motion_labeled` | partial | Late-Stage Commit Risk |

### Stage Hygiene

- Executive question: Which stage is slowing or reversing Land + Expand opportunities, and is the Stage 3/4 control point healthy?
- Primary KPIs: `stage_conversion`, `time_in_stage`, `sales_cycle_length`
- Secondary diagnostics: `stage3_approvals_compliance`, `commercial_approval_to_close_time`
- Required motion guardrail: `process`
- Caveat: Stage 3 and Stage 4 are the control points for approval friction and late-funnel slippage.

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `stage_conversion` | `Stage Forward Pct (LE)` | hero KPI | `land_expand_arr` | partial | Forward % (count, Land + Expand) |
| `stage_conversion` | `Stage Backward Pct (LE)` | hero KPI | `land_expand_arr` | partial | Backward % (count, Land + Expand) |
| `time_in_stage` | `Avg Days In Prior Stage (LE)` | hero KPI | `land_expand_arr` | partial | Stage days (Land + Expand) |
| `sales_cycle_length` | `Land Avg Sales Cycle Days` | hero KPI | `land_expand_arr` | clean | Land cycle days |
| `sales_cycle_length` | `Avg Sales Cycle Days` | hero KPI | `land_expand_arr` | clean | Land + Expand cycle days |
| `stage_conversion` | `Stage Forward Pct (LE)` | variance table | `land_expand_arr` | partial | Stage Conversion Matrix (count, Land + Expand) |
| `stage3_approvals_compliance` | `Commercial Approval Compliance Pct` | RAG card | `land_expand_arr` | clean | Approval % (count) |
| `commercial_approval_to_close_time` | `Commercial Approval To Close Days` | RAG card | `land_expand_arr` | clean | Approval-close days |

### Renewals

- Executive question: How much Renewal ACV is exposed, retained, or lost, and where is the pressure?
- Primary KPIs: `renewal_retention_rate`, `renewals_mom_trend`, `lost_arr_quarterly`
- Secondary diagnostics: `business_at_risk`, `existing_arr_run_rate`, `indexation_arr_growth`
- Required motion guardrail: `renewal_acv`
- Caveat: Renewal opportunity ACV and active-base ARR are separated. Land and Expand new-business ARR are excluded from this page.

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `renewals_mom_trend` | `Total Open Renewal ACV` | hero KPI | `renewal_acv` | clean | Open renewal ACV |
| `renewal_retention_rate` | `Renewal Retention Pct (Period)` | hero KPI | `renewal_acv` | partial | Retention % (ACV-wtd) |
| `renewals_mom_trend` | `Total Renewal ACV Won` | hero KPI | `renewal_acv` | clean | Won renewal ACV |
| `lost_arr_quarterly` | `Total Renewal ACV Lost` | hero KPI | `renewal_acv` | partial | Lost renewal ACV |
| `existing_arr_run_rate` | `Existing ARR Run Rate` | hero KPI | `renewal_base_arr` | clean | Active-base ARR |
| `business_at_risk` | `Business At Risk ARR` | hero KPI | `renewal_base_arr` | clean | At-risk base ARR |
| `business_at_risk` | `Business At Risk ARR` | bridge/waterfall | `renewal_base_arr` | clean | At-risk active-base ARR by Region |
| `existing_arr_run_rate` | `Existing ARR Expiring In Period` | detail table | `renewal_base_arr` | clean | Active-base ARR Detail |
| `indexation_arr_growth` | `Indexation ARR Growth` | detail table | `renewal_acv` | missing source data | Indexation ARR Growth |

### Growth Mix

- Executive question: Is growth coming from the right Land, Expand, partner, source, and new-customer mix?
- Primary KPIs: `ilf_arr_pipeline`, `alf_arr_pipeline`, `new_customer_reporting`, `closed_won_avg_deal_size`, `partner_opps_pct`
- Secondary diagnostics: `opp_source_effectiveness`, `closed_won_value_tier`, `cross_sell_to_acquired`, `ps_arr_attach`, `saas_arr_yoy_growth`, `synergy_deals_won`
- Required motion guardrail: `land_expand_arr`
- Caveat: Land and Expand ARR stay separate from Renewal ACV. SaaS and PS use their own source fields; Synergy remains proxy-only until the source flag exists.

| KPI | Measure | Role | Motion | Data status | Label |
| --- | --- | --- | --- | --- | --- |
| `alf_arr_pipeline` | `Open Land ARR` | hero KPI | `land_expand_arr` | partial | Open Land ARR |
| `ilf_arr_pipeline` | `Open Expand ARR` | hero KPI | `land_expand_arr` | partial | Open Expand ARR |
| `closed_won_avg_deal_size` | `Avg Deal Size Won` | hero KPI | `land_expand_arr` | partial | Avg won ARR (Land + Expand) |
| `partner_opps_pct` | `Partner ARR` | hero KPI | `land_expand_arr` | clean | Partner ARR (Land + Expand) |
| `partner_opps_pct` | `Partner Pct` | hero KPI | `land_expand_arr` | clean | Partner % ARR share |
| `alf_arr_pipeline` | `Total Open Pipeline ARR` | bridge/waterfall | `land_expand_arr` | partial | Open Land + Expand ARR by Region |
| `new_customer_reporting` | `Total Land Won Count` | detail table | `land_expand_arr` | clean | Land won count |
| `opp_source_effectiveness` | `Partner ARR` | detail table | `land_expand_arr` | clean | Strategic Mix Detail |
| `closed_won_value_tier` | `Closed Won Deals Count` | detail table | `land_expand_arr` | clean | Won value tier |
| `cross_sell_to_acquired` | `Cross Sell To Acquired ARR` | detail table | `land_expand_arr` | clean | Axioma ARR (Land + Expand) |
| `ps_arr_attach` | `PS ARR Attach Pct` | detail table | `land_expand_arr` | clean | PS attach % (ACV/ARR) |
| `saas_arr_yoy_growth` | `SaaS YoY Growth Pct` | detail table | `process` | clean | SaaS ARR YoY % |
| `synergy_deals_won` | `Total Land Won Count` | detail table | `land_expand_arr` | proxy | Land count proxy |

## KPI Matrix

| KPI | Impact | Motion | KG Source Status | Dashboard Status | Pages | Measures | Next Action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `forecast_closed_won` | HIGH | land_expand | exists | surfaced | VP Ops Scorecard, What Changed, Forecast | Total Closed Won ARR, Closed Won ARR YoY Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `pipeline_coverage_3x` | HIGH | land_expand | partial | surfaced_partial | Forecast | Total Open Pipeline ARR (missing: Pipeline Coverage Ratio) | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| `opp_win_rate` | HIGH | land_expand | exists | surfaced | VP Ops Scorecard | Win Rate ARR, Win Rate Count | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `stage_conversion` | HIGH | land_expand | partial | surfaced | VP Ops Scorecard, What Changed, Stage Hygiene | Stage Forward Pct (LE), Stage Backward Pct (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `opp_age` | MEDIUM | land_expand | exists | surfaced | What Changed | Avg Open Opp Age Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `opp_source_effectiveness` | MEDIUM | land_expand | exists | surfaced | Growth Mix | Source ARR Won, Source Win Rate | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `sales_cycle_length` | HIGH | land_expand | exists | surfaced | Stage Hygiene | Avg Sales Cycle Days, Land Avg Sales Cycle Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `time_in_stage` | MEDIUM | land_expand | missing | surfaced | VP Ops Scorecard, Stage Hygiene | Avg Days In Prior Stage (LE) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `closed_won_avg_deal_size` | HIGH | land_expand | exists | surfaced | Growth Mix | Avg Deal Size Won | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `closed_won_value_tier` | MEDIUM | land_expand | exists | surfaced | Growth Mix | Closed Won Deals Count | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `new_opps_by_region` | MEDIUM | land_expand | missing | surfaced | VP Ops Scorecard, What Changed | New Opps Created, New Opps Count 7d | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `stage3_approvals_compliance` | MEDIUM | land_expand | exists | surfaced | Stage Hygiene | Commercial Approval Compliance Pct, Stage 3 Forward Pct, Avg Days In Stage 3 | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `stage3_acv_value` | MEDIUM | land_expand | exists | surfaced | Forecast | Stage 3 Plus ARR, S3 Plus Open ACV | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `commercial_approval_to_close_time` | HIGH | land_expand | exists | surfaced | Stage Hygiene | Commercial Approval To Close Days | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `forecast_accuracy` | HIGH | land_expand | exists | surfaced_partial | Forecast | Forecast Slip Pct, Forecast Slips, Forecast Upgrades (missing: Forecast Accuracy) | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |
| `partner_opps_pct` | MEDIUM | land_expand | exists | surfaced | Growth Mix | Partner ARR, Partner Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `renewal_retention_rate` | HIGH | renewal | partial | surfaced | VP Ops Scorecard, Renewals | Renewal Retention Pct (Period) | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `renewals_mom_trend` | HIGH | renewal | exists | surfaced | Renewals | Total Open Renewal ACV, Total Renewal ACV Won | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `existing_arr_run_rate` | HIGH | renewal | exists | surfaced | Renewals | Existing ARR Run Rate | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `indexation_arr_growth` | MEDIUM | renewal | missing | surfaced_partial | Renewals | - (missing: Indexation ARR Growth) | Needs indexation/contract uplift field; keep as Renewals caveat until staged. |
| `ilf_arr_pipeline` | HIGH | land_expand | partial | surfaced | Growth Mix | Open Expand ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `alf_arr_pipeline` | HIGH | land_expand | partial | surfaced | Growth Mix | Open Land ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `new_customer_reporting` | HIGH | land_expand | exists | surfaced | Growth Mix | Total Land Won Count, Total Land Won ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `cross_sell_to_acquired` | HIGH | land_expand | exists | surfaced | Growth Mix | Cross Sell To Acquired ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `synergy_deals_won` | HIGH | land_expand | partial | surfaced_partial | Growth Mix | Total Land Won Count (missing: Synergy Deals Won) | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |
| `synergy_deals_pipe` | MEDIUM | land_expand | partial | partial_data_or_measure_gap | - | - (missing: Synergy Deals Pipeline) | Needs synergy flag; then add open/won synergy strip to Growth Mix. |
| `lost_arr_quarterly` | HIGH | renewal | exists | surfaced | Renewals | Total Renewal ACV Lost | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `business_at_risk` | HIGH | renewal | exists | surfaced | Renewals | Business At Risk ARR | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `one_off_revenues` | MEDIUM | all | missing | source_data_gap | - | - (missing: One Off Revenues) | Needs one-off/PS product fields; likely Product/Pricing future page. |
| `ps_arr_attach` | MEDIUM | land_expand | exists | surfaced | Growth Mix | PS ARR Attach Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |
| `saas_arr_yoy_growth` | HIGH | all | exists | surfaced | Growth Mix | SaaS YoY Growth Pct | Keep in page QA; tighten visual treatment if Desktop review flags it. |

## High-Impact Follow-Up Queue

- `pipeline_coverage_3x`: Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator.
- `forecast_accuracy`: Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies.
- `synergy_deals_won`: Needs synergy flag; current Growth Mix page uses Land won count as a proxy.
