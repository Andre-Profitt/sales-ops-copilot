# RW Power BI Knowledge Graph

Generated: `2026-05-10T22:25:41Z`
Source: `path`
Verdict: `needs_source_or_model_work`

This graph connects the actual Power BI report artifact to the RW KPI contract, semantic model, visual bindings, and cleanup gates. It is the current map of what each tab does and what still needs tightening.

## Executive Read

- Pages: `8`
- Visuals: `180` (basicShape=54, card=39, clusteredBarChart=3, pivotTable=5, slicer=17, tableEx=14, textbox=48)
- Semantic model: `9` tables, `124` measures, `11` relationships
- Used on BI surface: `53` measures, `19` columns
- RW KPI contract: `29` KPIs placed from `31` canonical RW KPIs
- Cleanup findings: `9` (info=0, low=0, medium=5, high=4, critical=0)
- Graph size: `472` nodes, `1082` edges
- Machine graph: `output/rw_dashboard_harness/pbi_knowledge_graph/shared_chrome.pbi_knowledge_graph.json`

## Enterprise Standard Snapshot

- Enterprise verdict: `not_enterprise_ready`
- Enterprise counts: `{'info': 0, 'low': 0, 'medium': 1, 'high': 1, 'critical': 0}`

| Page | Decision visuals | Zebra-native | Coverage |
| --- | ---: | ---: | ---: |
| VP Ops Scorecard | 11 | 10 | 91% |
| What Changed | 3 | 3 | 100% |
| Forecast | 9 | 9 | 100% |
| Stage Hygiene | 9 | 9 | 100% |
| Renewals | 9 | 9 | 100% |
| Product Retention | 8 | 8 | 100% |
| Growth Mix | 8 | 8 | 100% |
| RW KPI Explorer | 4 | 4 | 100% |

## Tab Map

| Tab | Executive question | Visuals | Measures | KPIs | Cleanup |
| --- | --- | ---: | ---: | ---: | --- |
| Stage Hygiene | Which stage is slowing or reversing Land + Expand opportunities, and is the Stage 3/4 control point healthy? | 25 | 11 | 5 | clear |
| Forecast | Can the quarter still land, and is forecast movement disciplined enough to trust? | 20 | 7 | 4 | high=2 |
| Growth Mix | Is growth coming from the right Land, Expand, partner, source, and new-customer mix? | 23 | 11 | 11 | high=1 |
| Renewals | How much Renewal ACV is exposed, retained, or lost, and where is the pressure? | 23 | 9 | 6 | clear |
| What Changed | What materially changed in the last operating window, and which open opportunities need inspection? | 13 | 12 | 4 | clear |
| VP Ops Scorecard | Where is RW off plan right now, and which lane needs executive action first? | 31 | 15 | 6 | clear |
| RW KPI Explorer | - | 21 | 17 | 0 | clear |
| Product Retention | Which product, segment, and region combinations carry active-base ARR retention or churn risk? | 24 | 5 | 3 | clear |

## Per-Tab Graph

### Stage Hygiene

- Question: Which stage is slowing or reversing Land + Expand opportunities, and is the Stage 3/4 control point healthy?
- Motion basis: `process`
- Visual mix: `{'basicShape': 7, 'card': 7, 'slicer': 2, 'tableEx': 2, 'textbox': 7}`
- KPIs served: `commercial_approval_to_close_time`, `sales_cycle_length`, `stage3_approvals_compliance`, `stage_conversion`, `time_in_stage`
- Measures used: `f_opportunity.Avg Sales Cycle Days`, `f_opportunity.Commercial Approval Compliance Pct`, `f_opportunity.Commercial Approval To Close Days`, `f_opportunity.Land Avg Sales Cycle Days`, `f_stage_transition.Avg Days In Prior Stage (LE)`, `f_stage_transition.Avg Days In Stage 4`, `f_stage_transition.Stage 4 Forward Pct`, `f_stage_transition.Stage Backward Pct (LE)`, `f_stage_transition.Stage Forward Pct (LE)`, `f_stage_transition.Stage Moves ARR 7d`, `f_stage_transition.Total Stage Transitions`

| Visual | Type | Fields |
| --- | --- | --- |
| Forward % (count, Land + Expand) | `card` | `M:f_stage_transition.Stage Forward Pct (LE)` |
| Backward % (count, Land + Expand) | `card` | `M:f_stage_transition.Stage Backward Pct (LE)` |
| Stage days (Land + Expand) | `card` | `M:f_stage_transition.Avg Days In Prior Stage (LE)` |
| Land cycle days | `card` | `M:f_opportunity.Land Avg Sales Cycle Days` |
| Land + Expand cycle days | `card` | `M:f_opportunity.Avg Sales Cycle Days` |
| Stage | Forward % (count, Land + Expand) | Backward % (count, Land + Expand) | Avg days | Move count | 7d ARR moved (Land + Expand) | `tableEx` | `C:f_stage_transition.from_stage_name`, `M:f_stage_transition.Stage Forward Pct (LE)`, `M:f_stage_transition.Stage Backward Pct (LE)`, `M:f_stage_transition.Avg Days In Prior Stage (LE)`, `M:f_stage_transition.Total Stage Transitions`, `M:f_stage_transition.Stage Moves ARR 7d` |
| Approval % (count) | `card` | `M:f_opportunity.Commercial Approval Compliance Pct` |
| Approval-close days | `card` | `M:f_opportunity.Commercial Approval To Close Days` |
- Cleanup: clear at current graph gates.

### Forecast

- Question: Can the quarter still land, and is forecast movement disciplined enough to trust?
- Motion basis: `cross_motion_labeled`
- Visual mix: `{'basicShape': 3, 'card': 7, 'pivotTable': 1, 'slicer': 2, 'tableEx': 1, 'textbox': 6}`
- KPIs served: `forecast_accuracy`, `forecast_closed_won`, `pipeline_coverage_3x`, `stage3_acv_value`
- Measures used: `f_forecast_transition.Avg Days In Forecast Category`, `f_forecast_transition.Forecast Slip Pct`, `f_forecast_transition.Forecast Slips`, `f_forecast_transition.Forecast Upgrades`, `f_opportunity.Days Remaining In FQ`, `f_opportunity.Total Closed Won ARR`, `f_opportunity.Total Open Pipeline Value`

| Visual | Type | Fields |
| --- | --- | --- |
| Days Remaining (FQ) | `card` | `M:f_opportunity.Days Remaining In FQ` |
| Open Value (ARR+ACV) | `card` | `M:f_opportunity.Total Open Pipeline Value` |
| Closed won ARR (Land + Expand) | `card` | `M:f_opportunity.Total Closed Won ARR` |
| Stage | Motion | Open value (ARR+ACV) | `pivotTable` | `C:f_opportunity.stage_name`, `C:f_opportunity.motion_type`, `M:f_opportunity.Total Open Pipeline Value` |
| Slip % (count proxy) | `card` | `M:f_forecast_transition.Forecast Slip Pct` |
| Slip count (proxy) | `card` | `M:f_forecast_transition.Forecast Slips` |
| Upgrade count (qtr) | `card` | `M:f_forecast_transition.Forecast Upgrades` |
| Avg days/category | `card` | `M:f_forecast_transition.Avg Days In Forecast Category` |

| Severity | Source | Finding | Next action |
| --- | --- | --- | --- |
| `high` | `data_surface` | Pipeline Value / Pipeline Coverage is surfaced_partial. | Add quota denominator and true 3x coverage ratio; current Forecast page shows the open-pipeline numerator. |
| `high` | `data_surface` | Forecast Accuracy is surfaced_partial. | Add real ForecastingItem/snapshot accuracy; current Forecast page only shows slips/upgrades movement proxies. |

### Growth Mix

- Question: Is growth coming from the right Land, Expand, partner, source, and new-customer mix?
- Motion basis: `land_expand_arr`
- Visual mix: `{'basicShape': 6, 'card': 5, 'clusteredBarChart': 1, 'slicer': 2, 'tableEx': 2, 'textbox': 7}`
- KPIs served: `alf_arr_pipeline`, `closed_won_avg_deal_size`, `closed_won_value_tier`, `cross_sell_to_acquired`, `ilf_arr_pipeline`, `new_customer_reporting`, `opp_source_effectiveness`, `partner_opps_pct`, `ps_arr_attach`, `saas_arr_yoy_growth`, `synergy_deals_won`
- Measures used: `f_opportunity.Avg Deal Size Won`, `f_opportunity.Closed Won Deals Count`, `f_opportunity.Cross Sell To Acquired ARR`, `f_opportunity.Open Expand ARR`, `f_opportunity.Open Land ARR`, `f_opportunity.PS ARR Attach Pct`, `f_opportunity.Partner ARR`, `f_opportunity.Partner Pct`, `f_opportunity.SaaS YoY Growth Pct`, `f_opportunity.Total Land Won Count`, `f_opportunity.Total Open Pipeline ARR`

| Visual | Type | Fields |
| --- | --- | --- |
| Open Land ARR | `card` | `M:f_opportunity.Open Land ARR` |
| Open Expand ARR | `card` | `M:f_opportunity.Open Expand ARR` |
| Avg won ARR (Land + Expand) | `card` | `M:f_opportunity.Avg Deal Size Won` |
| Partner ARR (Land + Expand) | `card` | `M:f_opportunity.Partner ARR` |
| Partner % ARR share | `card` | `M:f_opportunity.Partner Pct` |
| Region | Open ARR (Land + Expand) | `clusteredBarChart` | `C:d_region.region`, `M:f_opportunity.Total Open Pipeline ARR` |
| Region | Open Land ARR | Open Expand ARR | Open ARR (Land + Expand) | Avg won ARR (Land + Expand) | Partner ARR (Land + Expand) | Partner % ARR | Land won count | `tableEx` | `C:d_region.region`, `M:f_opportunity.Open Land ARR`, `M:f_opportunity.Open Expand ARR`, `M:f_opportunity.Total Open Pipeline ARR`, `M:f_opportunity.Avg Deal Size Won`, `M:f_opportunity.Partner ARR`, `M:f_opportunity.Partner Pct`, `M:f_opportunity.Total Land Won Count` |
| Won tier | Won deal count | Axioma ARR (Land + Expand) | SaaS ARR YoY % | PS attach % (ACV/ARR) | `tableEx` | `C:f_opportunity.won_value_tier`, `M:f_opportunity.Closed Won Deals Count`, `M:f_opportunity.Cross Sell To Acquired ARR`, `M:f_opportunity.SaaS YoY Growth Pct`, `M:f_opportunity.PS ARR Attach Pct` |

| Severity | Source | Finding | Next action |
| --- | --- | --- | --- |
| `high` | `data_surface` | Synergy deals close won is surfaced_partial. | Needs synergy flag; current Growth Mix page uses Land won count as a proxy. |

### Renewals

- Question: How much Renewal ACV is exposed, retained, or lost, and where is the pressure?
- Motion basis: `renewal_acv`
- Visual mix: `{'basicShape': 6, 'card': 7, 'clusteredBarChart': 1, 'slicer': 2, 'tableEx': 1, 'textbox': 6}`
- KPIs served: `business_at_risk`, `existing_arr_run_rate`, `indexation_arr_growth`, `lost_arr_quarterly`, `renewal_retention_rate`, `renewals_mom_trend`
- Measures used: `f_asset_line_item.Business At Risk ARR`, `f_asset_line_item.Business At Risk Pct`, `f_asset_line_item.Existing ARR Expiring In Period`, `f_asset_line_item.Existing ARR Run Rate`, `f_opportunity.Renewal Retention Pct (Period)`, `f_opportunity.Total Open Renewal ACV`, `f_opportunity.Total Renewal ACV Due`, `f_opportunity.Total Renewal ACV Lost`, `f_opportunity.Total Renewal ACV Won`

| Visual | Type | Fields |
| --- | --- | --- |
| Open renewal ACV | `card` | `M:f_opportunity.Total Open Renewal ACV` |
| Due renewal ACV | `card` | `M:f_opportunity.Total Renewal ACV Due` |
| Retention % (ACV-wtd) | `card` | `M:f_opportunity.Renewal Retention Pct (Period)` |
| Won renewal ACV | `card` | `M:f_opportunity.Total Renewal ACV Won` |
| Lost renewal ACV | `card` | `M:f_opportunity.Total Renewal ACV Lost` |
| Active-base ARR | `card` | `M:f_asset_line_item.Existing ARR Run Rate` |
| At-risk base ARR | `card` | `M:f_asset_line_item.Business At Risk ARR` |
| Region | At-risk base ARR | `clusteredBarChart` | `C:d_region.region`, `M:f_asset_line_item.Business At Risk ARR` |
- Cleanup: clear at current graph gates.

### What Changed

- Question: What materially changed in the last operating window, and which open opportunities need inspection?
- Motion basis: `land_expand_arr`
- Visual mix: `{'basicShape': 3, 'slicer': 2, 'tableEx': 3, 'textbox': 5}`
- KPIs served: `forecast_closed_won`, `new_opps_by_region`, `opp_age`, `stage_conversion`
- Measures used: `f_opportunity.At Risk Opps ARR`, `f_opportunity.At Risk Opps Count`, `f_opportunity.Closed Lost Count 7d`, `f_opportunity.Closed Won Count 7d`, `f_opportunity.Healthy Moves ARR`, `f_opportunity.Healthy Moves Count`, `f_opportunity.New Opps Count 7d`, `f_opportunity.Total Open Pipeline ARR`, `f_opportunity.Watch Opps ARR`, `f_opportunity.Watch Opps Count`, `f_stage_transition.Stage Moves ARR 7d`, `f_stage_transition.Stage Moves Count 7d`

| Visual | Type | Fields |
| --- | --- | --- |
| At-risk opp count | At-risk ARR (Land + Expand) | Watch opp count | Watch ARR (Land + Expand) | Healthy move count | Healthy ARR (Land + Expand) | `tableEx` | `M:f_opportunity.At Risk Opps Count`, `M:f_opportunity.At Risk Opps ARR`, `M:f_opportunity.Watch Opps Count`, `M:f_opportunity.Watch Opps ARR`, `M:f_opportunity.Healthy Moves Count`, `M:f_opportunity.Healthy Moves ARR` |
| Stage move count | Stage ARR (Land + Expand) | New opp count | Won count | Lost count | `tableEx` | `M:f_stage_transition.Stage Moves Count 7d`, `M:f_stage_transition.Stage Moves ARR 7d`, `M:f_opportunity.New Opps Count 7d`, `M:f_opportunity.Closed Won Count 7d`, `M:f_opportunity.Closed Lost Count 7d` |
| Opp | Account | Region | Stage | Open ARR (Land + Expand) | Last Stage Move | `tableEx` | `C:f_opportunity.opp_name`, `C:f_opportunity.account_name`, `C:f_opportunity.region`, `C:f_opportunity.stage_name`, `M:f_opportunity.Total Open Pipeline ARR`, `C:f_opportunity.last_stage_change_date` |
- Cleanup: clear at current graph gates.

### VP Ops Scorecard

- Question: Where is RW off plan right now, and which lane needs executive action first?
- Motion basis: `cross_motion_labeled`
- Visual mix: `{'basicShape': 15, 'card': 8, 'clusteredBarChart': 1, 'pivotTable': 1, 'slicer': 2, 'tableEx': 1, 'textbox': 3}`
- KPIs served: `forecast_closed_won`, `new_opps_by_region`, `opp_win_rate`, `renewal_retention_rate`, `stage_conversion`, `time_in_stage`
- Measures used: `f_opportunity.At Risk Opps ARR`, `f_opportunity.Closed Won Count 7d`, `f_opportunity.Exception ARR`, `f_opportunity.Exception Opps Count`, `f_opportunity.New Opps Count 7d`, `f_opportunity.Renewal Retention Pct (Period)`, `f_opportunity.Total Closed Won ARR`, `f_opportunity.Total Open Pipeline ARR`, `f_opportunity.Watch Opps ARR`, `f_opportunity.Win Rate ARR`, `f_stage_transition.Avg Days In Prior Stage (LE)`, `f_stage_transition.Backward Moves Count 7d`, `f_stage_transition.Stage Backward Pct (LE)`, `f_stage_transition.Stage Forward Pct (LE)`, `f_stage_transition.Stage Moves ARR 7d`

| Visual | Type | Fields |
| --- | --- | --- |
| Closed won ARR (Land + Expand) | `card` | `M:f_opportunity.Total Closed Won ARR` |
| Win rate (ARR-wtd) | `card` | `M:f_opportunity.Win Rate ARR` |
| Exception ARR (Land + Expand) | `card` | `M:f_opportunity.Exception ARR` |
| Retention % (ACV-wtd) | `card` | `M:f_opportunity.Renewal Retention Pct (Period)` |
| Region | Exception ARR (Land + Expand) | Opp count | At-risk ARR (Land + Expand) | Watch ARR (Land + Expand) | `tableEx` | `C:d_region.region`, `M:f_opportunity.Exception ARR`, `M:f_opportunity.Exception Opps Count`, `M:f_opportunity.At Risk Opps ARR`, `M:f_opportunity.Watch Opps ARR` |
| Stage | Open ARR (Land + Expand) | `clusteredBarChart` | `C:f_opportunity.stage_name`, `M:f_opportunity.Total Open Pipeline ARR` |
| Stage | Forward % (count, Land + Expand) | Backward % (count, Land + Expand) | Avg days | 7d ARR moved (Land + Expand) | `pivotTable` | `C:f_stage_transition.from_stage_name`, `M:f_stage_transition.Stage Forward Pct (LE)`, `M:f_stage_transition.Stage Backward Pct (LE)`, `M:f_stage_transition.Avg Days In Prior Stage (LE)`, `M:f_stage_transition.Stage Moves ARR 7d` |
| New opp count 7d | `card` | `M:f_opportunity.New Opps Count 7d` |
- Cleanup: clear at current graph gates.

### RW KPI Explorer

- Question: Not contracted.
- Motion basis: `n/a`
- Visual mix: `{'basicShape': 7, 'pivotTable': 1, 'slicer': 3, 'tableEx': 3, 'textbox': 7}`
- KPIs served: -
- Measures used: `f_opportunity.Avg Deal Size Won`, `f_opportunity.Open Expand ARR`, `f_opportunity.Open Land ARR`, `f_opportunity.Partner ARR`, `f_opportunity.Partner Pct`, `f_opportunity.Renewal Retention Pct (Period)`, `f_opportunity.Total Closed Won ARR`, `f_opportunity.Total Land Won Count`, `f_opportunity.Total Open Pipeline ARR`, `f_opportunity.Total Open Renewal ACV`, `f_opportunity.Total Renewal ACV Lost`, `f_opportunity.Total Renewal ACV Won`, `f_opportunity.Win Rate ARR`, `f_stage_transition.Avg Days In Prior Stage (LE)`, `f_stage_transition.Stage Backward Pct (LE)`, `f_stage_transition.Stage Forward Pct (LE)`
- Additional measures: `1`

| Visual | Type | Fields |
| --- | --- | --- |
| Region | Motion | Open ARR (Land + Expand) | Won ARR (Land + Expand) | Win rate (ARR-wtd) | `pivotTable` | `C:d_region.region`, `C:f_opportunity.motion_type`, `M:f_opportunity.Total Open Pipeline ARR`, `M:f_opportunity.Total Closed Won ARR`, `M:f_opportunity.Win Rate ARR` |
| Region | Open renewal ACV | Retention % (ACV-wtd) | Won renewal ACV | Lost renewal ACV | `tableEx` | `C:d_region.region`, `M:f_opportunity.Total Open Renewal ACV`, `M:f_opportunity.Renewal Retention Pct (Period)`, `M:f_opportunity.Total Renewal ACV Won`, `M:f_opportunity.Total Renewal ACV Lost` |
| Stage | Forward % (count, Land + Expand) | Backward % (count, Land + Expand) | Avg days | 7d ARR moved (Land + Expand) | `tableEx` | `C:f_stage_transition.from_stage_name`, `M:f_stage_transition.Stage Forward Pct (LE)`, `M:f_stage_transition.Stage Backward Pct (LE)`, `M:f_stage_transition.Avg Days In Prior Stage (LE)`, `M:f_stage_transition.Stage Moves ARR 7d` |
| Region | Open Land ARR | Open Expand ARR | Avg won ARR (Land + Expand) | Partner ARR (Land + Expand) | Partner % ARR | Land won count | `tableEx` | `C:d_region.region`, `M:f_opportunity.Open Land ARR`, `M:f_opportunity.Open Expand ARR`, `M:f_opportunity.Avg Deal Size Won`, `M:f_opportunity.Partner ARR`, `M:f_opportunity.Partner Pct`, `M:f_opportunity.Total Land Won Count` |
- Cleanup: clear at current graph gates.

### Product Retention

- Question: Which product, segment, and region combinations carry active-base ARR retention or churn risk?
- Motion basis: `renewal_base_arr`
- Visual mix: `{'basicShape': 7, 'card': 5, 'pivotTable': 2, 'slicer': 2, 'tableEx': 1, 'textbox': 7}`
- KPIs served: `business_at_risk`, `existing_arr_run_rate`, `indexation_arr_growth`
- Measures used: `f_asset_line_item.Active Asset Line Count`, `f_asset_line_item.Business At Risk ARR`, `f_asset_line_item.Business At Risk Pct`, `f_asset_line_item.Existing ARR Expiring In Period`, `f_asset_line_item.Existing ARR Run Rate`

| Visual | Type | Fields |
| --- | --- | --- |
| Active-base ARR | `card` | `M:f_asset_line_item.Existing ARR Run Rate` |
| Expiring active-base ARR | `card` | `M:f_asset_line_item.Existing ARR Expiring In Period` |
| At-risk active-base ARR | `card` | `M:f_asset_line_item.Business At Risk ARR` |
| Risk % of active base | `card` | `M:f_asset_line_item.Business At Risk Pct` |
| Active asset line count | `card` | `M:f_asset_line_item.Active Asset Line Count` |
| Product family | Region | Active-base ARR | At-risk active-base ARR | `pivotTable` | `C:f_asset_line_item.product_family`, `C:d_region.region`, `M:f_asset_line_item.Existing ARR Run Rate`, `M:f_asset_line_item.Business At Risk ARR` |
| Product family | Segment | Risk % of base | Expiring active-base ARR | `pivotTable` | `C:f_asset_line_item.product_family`, `C:f_asset_line_item.industry`, `M:f_asset_line_item.Business At Risk Pct`, `M:f_asset_line_item.Existing ARR Expiring In Period` |
| Account | Region | Segment | Product family | Product area | Start date | End date | Active-base ARR | At-risk active-base ARR | Risk % of base | `tableEx` | `C:f_asset_line_item.account_name`, `C:f_asset_line_item.region`, `C:f_asset_line_item.industry`, `C:f_asset_line_item.product_family`, `C:f_asset_line_item.product_area`, `C:f_asset_line_item.asset_start_date`, `C:f_asset_line_item.asset_end_date`, `M:f_asset_line_item.Existing ARR Expiring In Period` |
- Cleanup: clear at current graph gates.

## Cross-Report Cleanup Queue

| Severity | Source | Lane/KPI | Finding | Next action |
| --- | --- | --- | --- | --- |
| `high` | `enterprise_standard` | `data-to-surface flow` | Data-surface verdict is not_exec_complete; 3 high-impact KPI flows are incomplete. | Close or explicitly descope the high-impact KPI flow blockers before production deployment. |
| `medium` | `data_surface` | `one_off_revenues` | One Off Revenues by Quarter is source_data_gap. | Needs one-off/PS product fields; likely Product/Pricing future page. |
| `medium` | `data_surface` | `synergy_deals_pipe` | Synergy deals in pipe is partial_data_or_measure_gap. | Needs synergy flag; then add open/won synergy strip to Growth Mix. |
| `medium` | `enterprise_standard` | `semantic/filter architecture` | Semantic/filter flow is guarded but still has model debt. | Add explicit stage/forecast transition-date roles. |
| `medium` | `semantic_filter` | `date roles` | f_forecast_transition.transition_at has no direct calendar role. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |
| `medium` | `semantic_filter` | `date roles` | f_stage_transition.transition_at has no direct calendar role. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |

## Upgrade Backlog

| # | Lane | Work | Why |
| ---: | --- | --- | --- |
| 1 | movement dates | Add stage-transition and forecast-transition date roles. | Close FQ is cohort context; movement-period slicing needs separate transition dates. |
| 2 | source data | Stage quota, forecast snapshots, renewal base/indexation, Synergy, and one-off revenue sources. | The remaining high-impact RW KPIs are data/model blockers, not layout blockers. |
| 3 | target/plan data | Stage quota/target denominator for Pipeline Coverage Ratio. | Open pipeline numerator is surfaced, but 3x coverage cannot be executive-grade without quota. |
| 4 | forecast data | Stage ForecastingItem/snapshot history for true forecast accuracy. | Current Forecast page uses slip/upgrade proxies, not accuracy versus submitted forecast. |
| 5 | renewal base data | Stage Asset/Subscription base, existing ARR run-rate, indexation/uplift fields, and active-base risk. | Renewal page now shows open ACV risk, but not full active-base renewal economics or retained base quality. |
| 6 | growth segmentation | Stage a trusted Synergy flag and one-off/non-recurring revenue source. | Axioma, SaaS, and PS attach are now modeled; Synergy and one-off revenue remain the Growth Mix gaps. |
| 7 | BI surface | Add controlled drill paths from Scorecard -> exception ledger -> owner/account/opportunity detail. | The pages answer executive questions, but the action flow is not yet as strong as a boardroom operating review. |

## Guardrails

- ARR means Land + Expand only.
- Renewal ACV means Renewal only.
- `Total Open Pipeline Value` is the only cross-motion value measure and must stay visibly labeled ARR+ACV.
- Monetary visuals stay on `EUR M`; K/MM/BMM/$ visual labels or display-unit overrides are blocked.
- Proxy KPIs are tracked as debt, not counted as clean executive metrics.
