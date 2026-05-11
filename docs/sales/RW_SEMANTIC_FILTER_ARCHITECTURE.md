# RW Semantic Filter Architecture

Verdict: `guarded_exec_ready_with_model_debt`.

The report is now guarded against the major executive-flow failure: page-level Motion slicers are not allowed. ARR and Renewal ACV measures enforce motion at the DAX layer, so Motion belongs in labeled visual axes, not global page filters.

## Page Filter Contract

| Page | Motion contract | Page slicers | Rationale |
| --- | --- | --- | --- |
| VP Ops Scorecard | `cross_motion_labeled` | `Close FQ`, `Region` | Region and close-quarter context only; ARR and Renewal ACV measures stay separated. |
| What Changed | `land_expand_arr` | `Close FQ`, `Region` | Region and close-quarter context keep the 7-day movement window readable without a conflicting Motion slicer. |
| Forecast | `process` | `Close FQ`, `Region` | Region and close-quarter context; motion comparison is handled by the labeled Stage x Motion matrix. |
| Stage Hygiene | `process` | `Close FQ`, `Region` | Region and close-quarter context define the selected opportunity cohort; transition-window measures remain explicit. |
| Renewals | `renewal_acv` | `Close FQ`, `Region` | Region and close-quarter context only; Renewal ACV measures enforce Renewal motion. |
| Product Retention | `renewal_base_arr` | `Close FQ`, `Region` | Region and asset end-quarter context for active-base ARR; churn snapshots remain explicit when added. |
| Growth Mix | `land_expand_arr` | `Close FQ`, `Region` | Region and close-quarter context only; Land + Expand mix is shown through separate ARR measures. |
| RW KPI Explorer | `explorer` | `Close FQ`, `Region`, `Stage` | Region, close quarter, and current stage for interactive slicing; motion appears as visual columns, not a page slicer. |

## Findings

| Severity | Area | Finding | Impact | Next action |
| --- | --- | --- | --- | --- |
| `medium` | date roles | f_stage_transition.transition_at has no direct calendar role. | A close-quarter slicer selects the opportunity cohort, not the exact transition period. That is acceptable when labeled Close FQ, but not good enough for a future transition-period executive toggle. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |
| `medium` | date roles | f_forecast_transition.transition_at has no direct calendar role. | A close-quarter slicer selects the opportunity cohort, not the exact transition period. That is acceptable when labeled Close FQ, but not good enough for a future transition-period executive toggle. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |

## Zebra Schema Benchmark

These checks are informed by the Zebra schema corpus, not just local RW preference.

- Templates mined: `20`
- Relationships mined: `133`
- Single-direction relationships: `130`
- Bidirectional relationships: `3`
- Inactive relationships: `7`
- Templates with role-playing dimensions: `2`
- Templates with ordered dimensions: `2`
- Templates with scenario columns: `12`

| Zebra pattern | Evidence | RW application |
| --- | --- | --- |
| `single_direction_star` | 130/133 relationships use single-direction filtering. | Keep RW relationships conservative and do not introduce bidirectional filters to make slicers feel easier. |
| `role_playing_dates` | 2/20 schemas use role-playing dimensions and 7 inactive relationships exist in the corpus. | Add explicit transition-date roles before exposing Stage Move FQ or Forecast Move FQ slicers. |
| `ordered_dimensions` | 2/20 schemas carry sort/order/rank columns on dimensions. | Promote stage order into a canonical d_stage dimension instead of relying on label sorting. |
| `scenario_as_axis` | 12/20 schemas carry scenario/version as data columns, while only 1 use scenario dimensions. | Treat Motion as a labeled analytic axis or explicit measure family, not a universal page slicer. |
| `kpi_dictionary` | 13/20 schemas include KPI/table metadata; sales-funnel uses KPI_ID with an inactive KPI relationship. | Keep RW KPI/page contracts executable and consider a future d_kpi metadata table for governed explorer behavior. |

## Relationship Flow

| Relationship | From | To | Behavior | Active |
| --- | --- | --- | --- | --- |
| `rel_opp_account` | `f_opportunity.account_id` | `d_account.account_id` | `oneDirection` | `True` |
| `rel_opp_user` | `f_opportunity.owner_id` | `d_user.user_id` | `oneDirection` | `True` |
| `rel_opp_region` | `f_opportunity.region` | `d_region.region` | `oneDirection` | `True` |
| `rel_opp_stage` | `f_opportunity.stage_order` | `d_stage.stage_order` | `oneDirection` | `True` |
| `rel_opp_close_date` | `f_opportunity.close_date` | `d_calendar.date` | `oneDirection` | `True` |
| `rel_opp_created_date` | `f_opportunity.created_date` | `d_calendar.date` | `oneDirection` | `False` |
| `rel_asset_account` | `f_asset_line_item.account_id` | `d_account.account_id` | `oneDirection` | `True` |
| `rel_asset_region` | `f_asset_line_item.region` | `d_region.region` | `oneDirection` | `True` |
| `rel_asset_end_date` | `f_asset_line_item.asset_end_date` | `d_calendar.date` | `oneDirection` | `True` |
| `rel_forecast_opp` | `f_forecast_transition.opp_id` | `f_opportunity.opp_id` | `oneDirection` | `True` |
| `rel_stage_opp` | `f_stage_transition.opp_id` | `f_opportunity.opp_id` | `oneDirection` | `True` |

## Stage Model

- Has `d_stage`: `True`
- `f_opportunity` stage columns: `stage_name`, `stage_order`
- `f_stage_transition` stage columns: `days_in_prior_stage`, `from_stage_display`, `from_stage_name`, `from_stage_num`, `from_stage_order`, `from_stage_raw`, `to_stage_display`, `to_stage_name`, `to_stage_num`, `to_stage_order`, `to_stage_raw`

Canonical `d_stage` and stage sort keys are present. Opportunity-stage and transition-stage visuals should sort by business order rather than labels.
