# RW Enterprise Zebra Standard

Verdict: `not_enterprise_ready`.

This is the governing standard for getting the RW Power BI dashboard to Zebra-native, consultant-grade, data-engineering quality. It intentionally combines visual polish with semantic and source-data readiness; visual polish alone is not enough.

## Current State

- Visual QA counts: `{'info': 0, 'low': 0, 'medium': 0, 'high': 0, 'critical': 0}`
- Unit policy counts: `{'info': 0, 'low': 0, 'medium': 0, 'high': 0, 'critical': 0}`
- Semantic/filter counts: `{'info': 0, 'low': 0, 'medium': 3, 'high': 0, 'critical': 0}`
- Data-surface verdict: `not_exec_complete`
- KPI rollup: `17` clean, `6` partial/proxy, `3` model gaps, `5` source gaps out of `31` RW KPIs.
- Zebra schema benchmark: `20` templates, `133` relationships, `130` single-direction relationships.

## Standard

1. Every page answers one explicit executive question from the KPI contract.
2. ARR and Renewal ACV stay separated; only `Total Open Pipeline Value` may cross motions and it must be labeled.
3. Monetary values use `EUR M`; visual/theme display-unit scaling is forbidden.
4. Executive pages use governed slicers only: Region and Close FQ unless a page-specific contract allows more.
5. Primary decision visuals use Zebra-derived native grammar or a documented native equivalent.
6. Stage, movement-date, forecast, renewal-base, and segmentation semantics exist before the page claims those decisions.
7. Visual QA has zero medium/high/critical findings before Desktop review.

## Findings

| Severity | Lane | Page | Finding | Next action |
| --- | --- | --- | --- | --- |
| `medium` | semantic/filter architecture | - | Semantic/filter flow is guarded but still has model debt. | Add d_stage and explicit transition-date roles. |
| `high` | data-to-surface flow | - | Data-surface verdict is not_exec_complete; 8 high-impact KPI flows are incomplete. | Close or explicitly descope the high-impact KPI flow blockers before production deployment. |
| `high` | zebra visual grammar | Forecast | Forecast has no Zebra-native lineage on decision visuals. | Apply Zebra-derived native table/card/chart grammar to the page's primary decision visual before calling it enterprise-grade. |
| `high` | zebra visual grammar | Renewals | Renewals has no Zebra-native lineage on decision visuals. | Apply Zebra-derived native table/card/chart grammar to the page's primary decision visual before calling it enterprise-grade. |
| `high` | zebra visual grammar | Growth Mix | Growth Mix has no Zebra-native lineage on decision visuals. | Apply Zebra-derived native table/card/chart grammar to the page's primary decision visual before calling it enterprise-grade. |

## Zebra-Native Page Coverage

| Page | Decision visuals | Zebra-native visuals | Coverage |
| --- | ---: | ---: | ---: |
| VP Ops Scorecard | 11 | 10 | 91% |
| What Changed | 3 | 3 | 100% |
| Forecast | 9 | 0 | 0% |
| Stage Hygiene | 9 | 9 | 100% |
| Renewals | 6 | 0 | 0% |
| Growth Mix | 7 | 0 | 0% |

## Systematic Upgrade Backlog

| # | Lane | Work | Why |
| ---: | --- | --- | --- |
| 1 | semantic spine | Add canonical d_stage plus stage sort/key relationships. | Stage visuals need business-order semantics and reusable stage governance. |
| 2 | movement dates | Add stage-transition and forecast-transition date roles. | Close FQ is cohort context; movement-period slicing needs separate transition dates. |
| 3 | source data | Stage quota, forecast snapshots, Commercial Approval, renewal base, and segmentation flags. | The remaining high-impact RW KPIs are data/model blockers, not layout blockers. |
| 4 | page: Forecast | Rebuild primary visuals with Zebra-native helper grammar and IBCS table/chart ordering. | Current Zebra-native decision-visual coverage is 0/9. |
| 5 | page: Renewals | Rebuild primary visuals with Zebra-native helper grammar and IBCS table/chart ordering. | Current Zebra-native decision-visual coverage is 0/6. |
| 6 | page: Growth Mix | Rebuild primary visuals with Zebra-native helper grammar and IBCS table/chart ordering. | Current Zebra-native decision-visual coverage is 0/7. |
| 7 | target/plan data | Stage quota/target denominator for Pipeline Coverage Ratio. | Open pipeline numerator is surfaced, but 3x coverage cannot be executive-grade without quota. |
| 8 | forecast data | Stage ForecastingItem/snapshot history for true forecast accuracy. | Current Forecast page uses slip/upgrade proxies, not accuracy versus submitted forecast. |
| 9 | approval/process data | Stage Commercial Approval status/date from Apttus or the approved SimCorp source. | Stage 3/approval KPIs are proxy-only without the actual approval event. |
| 10 | renewal base data | Stage Asset/Subscription base, existing ARR run-rate, and indexation/uplift fields. | Renewal page can show ACV exposure, but not full renewal economics or retained base quality. |
| 11 | growth segmentation | Stage Axioma/acquired, synergy, SaaS, product/PS, and one-off revenue flags. | Growth Mix is credible for Land/Expand/partner today, but not yet the full RW segmentation agenda. |
| 12 | BI surface | Add controlled drill paths from Scorecard -> exception ledger -> owner/account/opportunity detail. | The pages answer executive questions, but the action flow is not yet as strong as a boardroom operating review. |

## Publish Rule

Do not call the RW dashboard production-ready until this audit returns `enterprise_ready` or the remaining findings are explicitly documented as out of scope for the release.
