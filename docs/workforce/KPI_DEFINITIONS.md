# Workforce — KPI Definitions

What each metric means. Phase 1 surfaces all of these via `wf.py`.

## Core units

**Effort units** — weighted-event proxy for time-tracked effort. No
clock data exists in SimCorp's exports, so each event is multiplied by
its process family weight:

| Process family                     | Weight | Rationale                                                       |
| ---------------------------------- | -----: | --------------------------------------------------------------- |
| Opportunities                      |    1.0 | Baseline                                                        |
| Quotes & Proposals                 |    2.0 | More work per event than an Opp update                          |
| KYC                                |    3.0 | Highest-friction process; snapshot-only data so this is a proxy |
| Activities (calls/emails/meetings) |    0.5 | Lowest-effort-per-event                                         |

Sum of `effort_units` across a person × week is the headline workload.

## Per-person metrics (in `weekly_person_kpis`)

| Metric                          | Definition                                                                                               |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `actions`                       | Raw event count this person × week                                                                       |
| `actions_adj`                   | Actions adjusted for leave (excludes leave weeks from denominators)                                      |
| `effort_units`                  | Weighted-event sum                                                                                       |
| `effort_adj`                    | Effort adjusted for leave                                                                                |
| `availability_factor`           | Fraction of the week the person was available (1.0 = full week, 0.0 = on leave)                          |
| `available_days` / `leave_days` | Component days                                                                                           |
| `utilization_index_p75`         | `actions / avg-actions-per-avail-week-among-team-p75`. Index where 1.0 = at team's 75th percentile pace. |
| `utilization_p75_4w_avg`        | 4-week rolling average of the above                                                                      |

**Load-state interpretation** (used by `wf.py team-week`):

- `util_p75 > 1.5` → **OVERLOADED** (running >150% of team P75 pace)
- `util_p75 < 0.5` → **UNDERLOADED**
- otherwise → normal

## Coverage concentration (`coverage_concentration`)

Per `segment × process_family`:

- `total_effort` — sum of effort units across all contributors
- `effective_contributors` — Herfindahl-style count of "real" contributors after effort weighting
- `top1_share` — fraction of total effort done by the single biggest contributor (0.0-1.0)
- `top1_person_name` — name of that contributor

**Read:** `top1_share > 0.5` means a single rep is doing >50% of that segment-process work — single-point-of-failure risk if they leave or go on leave.

Live as of Phase 1 ingest (2025-12-15 snapshot):

- SimCorp KYC: Ronald Jimena 100% (single point of failure)
- SimCorp Quotes & Proposals: Maria Sabiniewicz 56%
- Axioma KYC: Ronald Jimena 100%
- Axioma Quotes & Proposals: Andre Profitt 19% (healthy, distributed)

## Anomalies (`anomalies_log`)

Pre-computed z-scored weeks where total effort deviates from the
8-week rolling average. Each row:

- `week_start` — the anomalous week
- `effort` — actual effort that week
- `effort_roll8` — 8-week rolling baseline
- `z_score` — standardized deviation (>2.0 = significant)

5 logged anomalies in the static pack. All `z>2`, all spikes (effort
above baseline). No anomalous drops detected.

## Forecast (`forecast_output` + `forecast_backtest_metrics`)

48 weeks of forward-looking team capacity by `process_family`:

- `p10`, `p50`, `p90` — capacity prediction percentiles
- Backtest metrics: MAE, MAPE, RMSE, Bias, P10_P90_Coverage. Per family.

These exist as data but are not surfaced in `wf.py` Phase 1 — Phase 2/3 will visualize the forecast curve.

## What NOT to compute (deliberately)

- **Per-rep performance ranking with AI inference** — prohibited per AI Code of Conduct §8 (no people-related decision-making by AI). Use the raw numbers, draw your own conclusions.
- **Predicted future per-rep performance** — same constraint. Forecast is at process-family granularity, not individual.
- **"Recommendation to fire X" or "promote Y"** — explicitly out of scope.
- **Comparisons to non-SimCorp benchmarks** — there are no benchmark data in the static pack.

## Caveats

1. Roster is INFERRED, not authoritative. ~Some `actor_name_raw` values in fact_activity_clean don't appear in `dim_people` (orphans). Phase 2 should swap in an authoritative `dim_people` from Workday once CA-block is resolved.
2. KYC is snapshot-only — one row per account with last-modified date — so KYC effort and cycle time are approximations.
3. Axioma quotes lack `quote_id`; record_id is approximated as `AXQ|<oppId>`.
4. Sales hierarchy table is empty in this snapshot.
5. Data ends 2025-12-15. The 4-month gap to today (2026-04-29) closes when Phase 2 (live SF refresh) ships.
