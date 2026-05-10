# RW Semantic Filter Architecture

Verdict: `guarded_exec_ready_with_model_debt`.

The report is now guarded against the major executive-flow failure: page-level Motion slicers are not allowed. ARR and Renewal ACV measures enforce motion at the DAX layer, so Motion belongs in labeled visual axes, not global page filters.

## Page Filter Contract

| Page | Motion contract | Page slicers | Rationale |
| --- | --- | --- | --- |
| VP Ops Scorecard | `cross_motion_labeled` | `Close FQ`, `Region` | Region and close-quarter context only; ARR and Renewal ACV measures stay separated. |
| What Changed | `land_expand_arr` | `Close FQ`, `Region` | Region and close-quarter context keep the 7-day movement window readable without a conflicting Motion slicer. |
| Forecast | `cross_motion_labeled` | `Close FQ`, `Region` | Region and close-quarter context; motion comparison is handled by the labeled Stage x Motion matrix. |
| Stage Hygiene | `process` | `Close FQ`, `Region` | Region and close-quarter context define the selected opportunity cohort; transition-window measures remain explicit. |
| Renewals | `renewal_acv` | `Close FQ`, `Region` | Region and close-quarter context only; Renewal ACV measures enforce Renewal motion. |
| Growth Mix | `land_expand_arr` | `Close FQ`, `Region` | Region and close-quarter context only; Land/Expand mix is shown through separate ARR measures. |
| RW KPI Explorer | `explorer` | `Close FQ`, `Region`, `Stage` | Region, close quarter, and current stage for interactive slicing; motion appears as visual columns, not a page slicer. |

## Findings

| Severity | Area | Finding | Impact | Next action |
| --- | --- | --- | --- | --- |
| `medium` | stage order | f_stage_transition has numeric stage fields, but f_opportunity currently exposes stage_name without a semantic d_stage dimension. | Opportunity-stage visuals can only use label sorting until the model grows a canonical stage order that places 1-6, Opt-out, Won in the business sequence. | Add d_stage and join opportunity/stage-transition facts through canonical stage keys. |
| `medium` | date roles | f_stage_transition.transition_at has no direct calendar role. | A close-quarter slicer selects the opportunity cohort, not the exact transition period. That is acceptable when labeled Close FQ, but not good enough for a future transition-period executive toggle. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |
| `medium` | date roles | f_forecast_transition.transition_at has no direct calendar role. | A close-quarter slicer selects the opportunity cohort, not the exact transition period. That is acceptable when labeled Close FQ, but not good enough for a future transition-period executive toggle. | Add role-specific transition-date semantics before introducing Stage Move FQ or Forecast Move FQ slicers. |

## Relationship Flow

| Relationship | From | To | Behavior | Active |
| --- | --- | --- | --- | --- |
| `rel_opp_account` | `f_opportunity.account_id` | `d_account.account_id` | `oneDirection` | `True` |
| `rel_opp_user` | `f_opportunity.owner_id` | `d_user.user_id` | `oneDirection` | `True` |
| `rel_opp_region` | `f_opportunity.region` | `d_region.region` | `oneDirection` | `True` |
| `rel_opp_close_date` | `f_opportunity.close_date` | `d_calendar.date` | `oneDirection` | `True` |
| `rel_opp_created_date` | `f_opportunity.created_date` | `d_calendar.date` | `oneDirection` | `False` |
| `rel_forecast_opp` | `f_forecast_transition.opp_id` | `f_opportunity.opp_id` | `oneDirection` | `True` |
| `rel_stage_opp` | `f_stage_transition.opp_id` | `f_opportunity.opp_id` | `oneDirection` | `True` |

## Stage Model

- Has `d_stage`: `False`
- `f_opportunity` stage columns: `stage_name`
- `f_stage_transition` stage columns: `days_in_prior_stage`, `from_stage_name`, `from_stage_num`, `from_stage_raw`, `to_stage_name`, `to_stage_num`, `to_stage_raw`

The next semantic-model upgrade is a canonical `d_stage` table plus explicit transition-date roles. Until then, the report should keep Close FQ labeling and avoid transition-period slicers.
