# Handoff — RW/AP Workforce Intelligence Track

**Status:** unstarted in this repo (verified 2026-04-28). Andre asked another agent to take it; no commits found yet.
**For:** the next agent picking this up.

---

## What this is

A "Reps Working / Accounts Producing" (RW/AP) workforce-intelligence layer for Sales Ops. Goes beyond pipeline analytics — answers "who is doing what work, at what intensity, on which accounts, with what effectiveness." This is **a third workstream**, distinct from the cockpit and sf-audit tracks already running in this repo.

## Source artifacts (ready to ingest)

All in `~/Downloads/`:

| File                                               | What's in it                                                                                                                                                                                                                                                                                  |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `SalesOps_Workforce_Intelligence_v2_artifacts.zip` | The canonical pack — 5 files inside (extract first)                                                                                                                                                                                                                                           |
| `SalesOps_Workforce_Intelligence_v2.xlsx`          | 15 sheets: dim_people (763r), dim_leave (2r), dim_process (5r), fact_activity_clean (43,127r × 17c), weekly_team_kpis (401r × 9c), weekly_person_kpis (3,101r × 16c), weekly_process_kpis, forecast_output, forecast_backtest_metrics, coverage_matrix, coverage_concentration, anomalies_log |
| `SalesOps_Workforce_Intelligence_v2.pptx`          | Pre-rendered chart deck — 112-slide                                                                                                                                                                                                                                                           |
| `fact_activity_unified_all_dedup.csv.gz`           | All-actors fact table (~12MB compressed)                                                                                                                                                                                                                                                      |
| `fact_activity_salesops_dedup_adj.csv.gz`          | Sales-Ops-only fact (the workforce subject)                                                                                                                                                                                                                                                   |
| `README_Workforce_Intelligence_v2.txt`             | The data-model contract (read first)                                                                                                                                                                                                                                                          |
| `SalesOps_Operational_Pulse_FY25.pptx`             | Sister Operational Pulse FY25 deck                                                                                                                                                                                                                                                            |
| `SalesOps_Work_Analytics_*.{xlsx,pptx}`            | 5 supporting work-analytics outputs (Daily / TimeSeries / WITH_CHARTS / FINAL / Plain)                                                                                                                                                                                                        |

Data coverage: **2023-01-01 → 2025-12-15** (covers Andre's paternity leave 2025-04-14 → 2025-09-14, already factored in).

## Data model (from README)

- **Effort units** — no time-tracking exists; metrics use weighted events. Baseline weights: Opps=1, Quotes & Proposals=2, KYC=3, Activities=0.5.
- **Process families** — Opportunities · Quotes & Proposals (SimCorp + Axioma) · KYC · Activities
- **Sales Ops roster** — inferred from quote editors (≥700 quote events) + Andre + Ronald + Jimena. Replace with authoritative dim_people if a roster source emerges.
- **Sales hierarchy** — rep→manager→region NOT in source. Coverage analysis uses Opportunity Owner / Account Owner only.

## Known gaps (don't fake these)

1. **KYC export is snapshot-like** — one row per account with last-modified date. Treat KYC workload + cycle time as proxy.
2. **Axioma quotes lack quote_id** — record_id approximated at Opportunity level (`AXQ|<oppId>`).
3. **No real time-tracking** — effort units are a weighted-event proxy, not hours.
4. **Roster inferred** — replace with authoritative source when available.

## What "done" looks like

The objective is a workforce/RW-AP intelligence layer that answers:

| Question                                                    | Decided by                                             |
| ----------------------------------------------------------- | ------------------------------------------------------ |
| Who's overloaded vs underloaded this week?                  | weekly_person_kpis × dim_leave (availability-adjusted) |
| What process is consuming the team's effort?                | weekly_process_kpis                                    |
| Which accounts are starving for attention?                  | coverage_concentration                                 |
| Which deals have an activity drought relative to deal size? | join fact_activity to Opportunity ARR                  |
| Is the team's capacity matched to next-quarter commit?      | forecast_output × weekly_team_kpis                     |
| Are there anomalies (sudden drop, sudden spike)?            | anomalies_log + forward-looking detection              |

## Path of least resistance (suggested)

1. **Phase 1 — Ingest the static pack** as-is. Land the xlsx + csvs into a SQLite or DuckDB at `~/code/apps/sales-ops-copilot/workforce/state/wf.duckdb`. Build a small read-only CLI: `wf.py team-week`, `wf.py person <name>`, `wf.py anomalies`. ~2-3 hours.
2. **Phase 2 — Live SF refresh** — replicate the dim*/fact* build from live SF queries (TaskAndEvent, OpportunityHistory, Quote/Proposal). Ship a `wf_refresh.py` that rebuilds the local store nightly via launchd. ~1 day.
3. **Phase 3 — Workforce dashboard** — build a SF Lightning Dashboard mirroring the pptx insights, OR (per the cockpit-vs-sf-audit philosophy debate) build a Textual TUI / web view. Probably belongs in **a third track** (`track:workforce`), not in cockpit or sf-audit.

## Track ownership rules

`docs/AGENT_COORDINATION.md` partitions this repo into `track:cockpit` and `track:sf-audit`. RW/AP is **outside both lanes** — it's a third domain (workforce activity vs pipeline). Recommend creating a new `track:workforce` namespace:

- Files under `scripts/workforce/`, `docs/workforce/`, `workforce/state/`
- Commit-tag prefix `feat(track:workforce): ...`
- Don't touch `scripts/alerts.py`, `brief.py`, `agent.py`, `cockpit.py`, anything in `sf_dashboard/cockpit/`, anything in `scripts/sf_audit/` or `docs/sf_audit/`
- Update `docs/AGENT_COORDINATION.md` to register this track

## Hard rules (inherited from repo CLAUDE.md + memories)

- ARR for Land+Expand · ACV for Renewals · NEVER blend
- No client-level data through any LLM beyond aggregates
- GPT-5.x rejects non-default `temperature`
- The static pack covers thru 2025-12-15. **Andre's session today is 2026-04-28** — there's a 4-month gap between the source data and current org state. Phase 2 (live refresh) closes the gap; Phase 1 is a frozen snapshot.

## Verification before claiming any phase done

1. Phase 1: `python3 scripts/workforce/wf.py team-week` returns weekly_team_kpis with real numbers from the xlsx
2. Phase 2: `python3 scripts/workforce/wf_refresh.py` runs end-to-end against live SF without error
3. Phase 3: dashboard / TUI surfaces real numbers matching the local store
4. `docs/AGENT_COORDINATION.md` updated with the new track lane

## Open question for Andre

The pptx in the pack already has a 112-slide visualization layer. **Is that the deliverable you wanted, or is the dashboard the deliverable?** If the pptx is enough for now, Phase 3 is optional and the workforce track collapses to "ingest + live refresh."

## Pointer files

- `~/code/apps/sales-ops-copilot/HANDOFF.md` — repo-level handoff (cockpit track)
- `~/code/apps/sales-ops-copilot/docs/AGENT_COORDINATION.md` — track partition
- `~/.claude/projects/-Users-test/memory/MEMORY.md` — Andre's persistent memory index
