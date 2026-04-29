# AP RW (Workforce Intelligence) — Phase 1 Implementation Plan

**Status:** dedicated session (planning complete, not yet executed)
**Author:** Claude Opus 4.7 (1M context) + Andre, 2026-04-29
**Source artifacts:** `~/Downloads/SalesOps_Workforce_Intelligence_v2_artifacts.zip` + sister CSVs
**Repo location (target):** `~/code/apps/sales-ops-copilot/scripts/workforce/` + `workforce/state/wf.duckdb` + `docs/workforce/`
**Track namespace:** `track:workforce` (NEW — third track alongside `track:cockpit` and `track:sf-audit`)

---

## 0. Why this exists (mission)

The cockpit and sf-audit tracks answer **pipeline questions** ("how big is the book, what's stuck, who's the concentration risk on opps"). They don't answer **workforce questions** ("who's overloaded, what's eating the team's effort, which accounts are starved for attention, are there activity anomalies").

The AP/RW (Accounts Producing / Reps Working) layer answers those questions, using a **weighted-event proxy** for effort (no time-tracking exists in SimCorp's exports). It's the third leg of the Sales Ops analytics stool: pipeline (✓ done) + governance (✓ done in alerts) + workforce (this plan).

**Decision-grade questions this enables:**

| Question                                            | Answered by                                                   |
| --------------------------------------------------- | ------------------------------------------------------------- |
| Who's overloaded vs. underloaded this week?         | `weekly_person_kpis` × `dim_leave` (availability-adjusted)    |
| What process is consuming the team's effort?        | `weekly_process_kpis` (Opps / Quotes / KYC / Activities)      |
| Which accounts are starving for attention?          | `coverage_concentration`                                      |
| Which deals have an activity drought vs. deal size? | join `fact_activity` to `Opportunity.APTS_Opportunity_ARR__c` |
| Is team capacity matched to next-quarter commit?    | `forecast_output` × `weekly_team_kpis`                        |
| Are there anomalies (sudden drop, sudden spike)?    | `anomalies_log` + forward-looking detection                   |

---

## 1. Phasing (3 phases — Phase 1 is this plan)

| Phase | What                                                                                 | Effort | Status                           |
| ----- | ------------------------------------------------------------------------------------ | ------ | -------------------------------- |
| **1** | Static-pack ingest into DuckDB + read-only `wf.py` CLI                               | ~3h    | **planned (this doc)**           |
| **2** | Live SF refresh (replicate dim/fact build from live SF queries; nightly via launchd) | ~1d    | outlined here, separate session  |
| **3** | Workforce dashboard or TUI surfacing the same KPIs                                   | TBD    | outlined here, separate decision |

Phase 1 = static frozen snapshot. Phase 2 closes the 4-month staleness gap (data ends 2025-12-15, today is 2026-04-29). Phase 3 is the consumer surface.

This document is **the Phase 1 plan**. Phases 2 + 3 have outlines at the bottom for context but aren't executed here.

---

## 2. Architecture decisions

### 2.1 Why DuckDB (not SQLite, not Postgres)

- **DuckDB is columnar, optimized for analytical aggregation queries** — exactly the shape of workforce queries (rollups by week × person × process).
- **Single-file, file-based, zero-config** — same operational model as SQLite.
- **First-class CSV/parquet/xlsx ingest** — `read_csv_auto`, `read_xlsx`, `from_arrow`. Saves writing custom parsers.
- **Native `WINDOW` and time-bucket functions** — needed for week-over-week deltas, anomaly detection.
- **Already used elsewhere in Andre's stack** (per memory `project_kaggle_nemotron_canonical_pipeline` — DuckDB shows up in adjacent labs).

The HANDOFF doc explicitly recommends DuckDB. Following the recommendation.

**Install:** `pip install duckdb` (single dependency, ~50 MB).

### 2.2 File layout

```
~/code/apps/sales-ops-copilot/
├── scripts/
│   └── workforce/                          # NEW track
│       ├── __init__.py
│       ├── wf.py                           # CLI entry (team-week, person, anomalies, coverage, process-mix)
│       ├── ingest.py                       # one-shot static-pack loader → DuckDB
│       ├── schema.sql                      # canonical DuckDB DDL (one file, executable)
│       ├── queries.py                      # parameterized analytic queries (used by wf.py)
│       ├── _effort.py                      # weighted-event constants + helpers (Opps=1, Quotes=2, KYC=3, Acts=0.5)
│       └── tests/
│           ├── test_ingest.py              # row counts vs README expectations
│           ├── test_dim_leave.py           # Andre paternity leave 2025-04-14→2025-09-14 sentinel
│           └── test_queries.py             # smoke tests of each CLI verb
├── workforce/
│   ├── raw/                                # extracted zip contents (gitignored)
│   │   ├── SalesOps_Workforce_Intelligence_v2.xlsx
│   │   ├── SalesOps_Workforce_Intelligence_v2.pptx
│   │   ├── fact_activity_unified_all_dedup.csv.gz
│   │   ├── fact_activity_salesops_dedup_adj.csv.gz
│   │   └── README_Workforce_Intelligence_v2.txt
│   └── state/
│       └── wf.duckdb                       # canonical store (gitignored)
└── docs/
    ├── workforce/                          # NEW track docs
    │   ├── DATA_MODEL.md                   # tables + columns + business rules (cribbed from README + extended)
    │   ├── KPI_DEFINITIONS.md              # what each metric means
    │   └── COMPLIANCE.md                   # Code of Conduct constraints + how this design respects them
    └── plans/
        └── 2026-04-29-ap-rw-phase1-plan.md # THIS file
```

### 2.3 Track namespace

Add `track:workforce` to `docs/AGENT_COORDINATION.md`. Files under `scripts/workforce/`, `workforce/`, `docs/workforce/` are workforce-track-owned. **No agent from cockpit or sf-audit tracks should touch these paths.** Commit prefix: `feat(track:workforce): ...`.

Conversely, the workforce track must NOT touch:

- `scripts/alerts.py`, `brief.py`, `agent.py`, `cockpit.py` (cockpit lane)
- `scripts/sf_audit/*`, `docs/sf_audit/*` (sf-audit lane)
- `sf_dashboard/cockpit/*` (cockpit dashboard lane)
- The `Sales Ops Commercial Health` SF reports folder

The workforce track is **read-only against Salesforce** in Phase 1 (static pack only). Phase 2 introduces live SF reads but still no writes.

### 2.4 Effort weights (per HANDOFF doc + README)

Baseline weighted-event proxy for effort:

```python
EFFORT_WEIGHTS = {
    "Opportunities": 1.0,
    "Quotes & Proposals": 2.0,   # SimCorp + Axioma
    "KYC": 3.0,                  # snapshot-only, treated as proxy (caveat noted)
    "Activities": 0.5,
}
```

Rationale: Quotes are heavier work than Opps; KYC is highest-friction; Activities (calls/emails/meetings) are lowest-effort-per-event. These weights are spec'd, not learned. Should be tunable (env var override) for future calibration.

### 2.5 The roster problem (inferred, not authoritative)

Per README: "Sales Ops roster: inferred from high-volume quote editors (>=700 quote events) + Andre + Ronald + Jimena (per spec). If a roster image exists, replace inference with authoritative dim_people roster + effective dates."

**Plan:** Phase 1 uses `dim_people` from the xlsx as-is (763 rows). Phase 2 swap-in path:

- Add an env var `WORKFORCE_ROSTER_FILE` pointing to an authoritative CSV
- If set, ingest reads that CSV instead of `dim_people` from xlsx
- Otherwise fall back to inferred roster

Document this in `KPI_DEFINITIONS.md` so users know which roster they're querying against.

---

## 3. Phase 1 — detailed task plan

Total estimated effort: **3 hours**, broken into 6 tasks of 20-40 min each. Executable in a single dedicated session.

### Task 1 — Scaffold + extract (20 min)

**What:**

1. Create directory tree per §2.2.
2. Add `workforce/` to repo `.gitignore` (raw + state are local-only; ~22MB raw + ~50-100MB DuckDB).
3. Extract zip:
   ```bash
   unzip -d workforce/raw/ ~/Downloads/SalesOps_Workforce_Intelligence_v2_artifacts.zip
   ```
4. Verify: 5 files in `workforce/raw/` matching README sizes.
5. Add `pyproject.toml` dep: `duckdb>=1.0.0`.
6. Update `docs/AGENT_COORDINATION.md` with `track:workforce` row + active claim while editing shared files.

**Verify:**

```bash
ls -la workforce/raw/ | wc -l   # 5 + . + .. = 7 lines
duckdb --version                 # any 1.x
```

### Task 2 — Schema + ingest the xlsx (45 min)

**What:**

1. Write `scripts/workforce/schema.sql` defining tables for each xlsx sheet. The 15 sheets (per HANDOFF doc + README inspection):

| Sheet                     | Table                       | Estimated rows | Notes                                                    |
| ------------------------- | --------------------------- | -------------- | -------------------------------------------------------- |
| dim_people                | `dim_people`                | 763            | inferred roster; PK = person_id                          |
| dim_leave                 | `dim_leave`                 | 2              | Andre paternity 2025-04-14→2025-09-14 + likely one other |
| dim_process               | `dim_process`               | 5              | process families (Opps, Quotes, KYC, Activities, ??)     |
| fact_activity_clean       | `fact_activity_clean`       | 43,127 × 17    | the canonical fact table (cleaned + deduped)             |
| weekly_team_kpis          | `weekly_team_kpis`          | 401 × 9        | team-level rollups by week                               |
| weekly_person_kpis        | `weekly_person_kpis`        | 3,101 × 16     | per-person × week (this is the MAIN scorecard table)     |
| weekly_process_kpis       | `weekly_process_kpis`       | TBD            | per process family × week                                |
| forecast_output           | `forecast_output`           | TBD            | forward-looking team capacity model                      |
| forecast_backtest_metrics | `forecast_backtest_metrics` | TBD            | backtest scoring of the forecast                         |
| coverage_matrix           | `coverage_matrix`           | TBD            | who-touched-which-account                                |
| coverage_concentration    | `coverage_concentration`    | TBD            | account starvation analysis                              |
| anomalies_log             | `anomalies_log`             | TBD            | flagged anomalies with explanations                      |
| (4 others)                | TBD                         | TBD            | inspect + decide on first run                            |

2. Write `scripts/workforce/ingest.py`:
   - Connects to DuckDB at `workforce/state/wf.duckdb`
   - For each sheet, runs `CREATE TABLE … AS SELECT * FROM read_xlsx(…, sheet='…')`
   - Idempotent: drops + recreates tables on every run (Phase 1 is static; no incremental)
   - Logs row counts per table

3. Run ingest. Compare row counts to README expectations.

**Verify:**

```bash
python3 scripts/workforce/ingest.py
duckdb workforce/state/wf.duckdb "SELECT table_name, estimated_size FROM duckdb_tables() ORDER BY table_name;"
# Spot-check: dim_people=763, fact_activity_clean=43127, weekly_person_kpis=3101
```

### Task 3 — Schema + ingest the CSVs (30 min)

**What:**

1. Load `fact_activity_unified_all_dedup.csv.gz` → table `fact_activity_unified` (~43k+ rows, all actors including non-sales).
2. Load `fact_activity_salesops_dedup_adj.csv.gz` → table `fact_activity_salesops` (filtered + adjusted to sales-ops only).
3. Both via `read_csv_auto` with explicit type coercion for `event_ts` (datetime), `effort_units` (double), `record_id` (varchar), etc.
4. Verify row counts vs the size of the .gz files (rough sanity).

**Verify:**

```sql
SELECT COUNT(*) FROM fact_activity_unified;     -- expect tens of thousands
SELECT COUNT(*) FROM fact_activity_salesops;    -- expect smaller subset
SELECT MIN(event_ts), MAX(event_ts) FROM fact_activity_unified;
-- expect 2023-01-01 → 2025-12-15 per README
```

### Task 4 — Sentinel checks + integrity tests (30 min)

**What:** Phase 1's correctness gate. Five tests in `scripts/workforce/tests/`:

1. **Andre paternity leave test:** `dim_leave` should contain a row for Andre Profitt with `start_date = 2025-04-14` and `end_date = 2025-09-14`. If not, fail loudly — ingest broke.

2. **Date range test:** `MIN(event_ts) = 2023-01-01` and `MAX(event_ts) = 2025-12-15` in the unified fact. If different, the README contract is violated and we have wrong data.

3. **Cross-table integrity:** every distinct person_id in `fact_activity_clean` should exist in `dim_people`. If orphans, dim_people is incomplete (likely the inferred-roster gap).

4. **Effort sum sanity:** `SUM(effort_units) FROM fact_activity_salesops` should yield a non-zero, non-negative number. Order of magnitude check: ~10K-100K (not millions, not zero).

5. **Process family coverage:** `SELECT DISTINCT process_family FROM fact_activity_salesops` should return exactly the families in `dim_process` (Opps / Quotes & Proposals / KYC / Activities, plus possibly one more).

If any test fails, ingest halts and emits a remediation suggestion.

**Verify:**

```bash
pytest scripts/workforce/tests/ -v
```

### Task 5 — `wf.py` CLI (45 min)

**What:** Single-entry CLI with five verbs. Read-only against the DuckDB store. Output is plain text tables (not JSON) by default — meant to be human-eyeballed in a terminal.

```
wf.py team-week [--week YYYY-Www]      # team rollup for given week (default: most recent)
wf.py person <name> [--weeks N]        # one rep, last N weeks (default: 8)
wf.py anomalies [--since YYYY-MM-DD]   # flagged anomalies + new detections
wf.py coverage [--top N]               # account starvation: which accts had zero touches in last 4w
wf.py process-mix [--week YYYY-Www]    # effort allocation across 4 process families
```

Each verb is one parameterized SQL query in `queries.py`. The CLI is thin — it just dispatches and renders.

**Sample query — `team-week`:**

```sql
SELECT
  person_id,
  person_name,
  week,
  total_events,
  effort_units,
  avg_events_per_week_4w,
  pct_vs_avg_4w,
  CASE
    WHEN pct_vs_avg_4w > 1.5 THEN 'OVERLOADED'
    WHEN pct_vs_avg_4w < 0.5 THEN 'UNDERLOADED'
    ELSE 'normal'
  END AS load_state
FROM weekly_person_kpis
WHERE week = ?
ORDER BY effort_units DESC;
```

**Verify:**

```bash
python3 scripts/workforce/wf.py team-week           # most recent week
python3 scripts/workforce/wf.py person "Andre Profitt"
python3 scripts/workforce/wf.py anomalies
python3 scripts/workforce/wf.py coverage --top 20
python3 scripts/workforce/wf.py process-mix
```

Each command should produce a non-empty, sensible table (or a clean "no rows" message).

### Task 6 — Documentation (15 min)

**What:**

1. Write `docs/workforce/DATA_MODEL.md` — table-by-table column reference, derived from the xlsx schema + README contract. This is the source-of-truth for any future modification.

2. Write `docs/workforce/KPI_DEFINITIONS.md` — what each metric means (effort units, load state thresholds, anomaly definitions, coverage definitions). This is the "what does this number mean" reference.

3. Write `docs/workforce/COMPLIANCE.md` — Code of Conduct + AI Whitelist constraints applied to workforce data. Specifically:
   - Workforce data is more sensitive than pipeline data (per-rep performance details)
   - **No AI inference / no LLM coaching suggestions in Phase 1** — CLI is purely SQL aggregations
   - "People-related decision-making is PROHIBITED" per AI Code of Conduct § governance.md — the wf.py CLI is descriptive, not prescriptive
   - All data is local-only on Andre's device; no upload, no sharing
   - DuckDB file is gitignored; raw exports are gitignored

4. Update `~/.claude/projects/-Users-test/memory/MEMORY.md` with a pointer entry: `[Workforce Phase 1](project_workforce_phase1.md)`.

---

## 4. Phase 2 outline (deferred — separate session)

**Goal:** close the 4-month staleness gap. Replicate `dim_*` and `fact_*` tables from live Salesforce queries on a nightly cadence.

**Scope:**

- New module `scripts/workforce/refresh.py`
- Reads live SF: `TaskAndEvent`, `Quote`, `Proposal__c` (or `Apttus_Proposal__Proposal__c`), `OpportunityHistory`, `Opportunity`
- Maps each to the `fact_activity_*` shape using the same dedup/effort-unit rules from the static pack
- Writes to a sibling DuckDB `wf_live.duckdb` (so static + live can coexist for trust comparisons)
- launchd plist `com.simcorp.workforce.nightly` (per `project_ai_os_daemon_env.md` env requirements)
- Estimated effort: **1 full day** (data mapping is the hard part — many SF objects, many edge cases)

**Phase 2 success gate:**

- `wf.py refresh` completes without error against live SF
- `SELECT COUNT(*) FROM fact_activity_clean WHERE event_ts > '2025-12-15'` returns a non-zero number (i.e., post-static-pack data has flowed in)
- Re-running `wf.py team-week` shows current-week data, not 18-week-old data

---

## 5. Phase 3 outline (deferred — separate decision)

**Question:** dashboard or TUI?

The static pack already includes a 112-slide PPTX (`SalesOps_Workforce_Intelligence_v2.pptx`) that visualizes the data. Phase 3's job is to make those visualizations LIVE — refreshing as `wf.duckdb` updates.

**Three options:**

| Option                        | Stack                                                     | Pros                                                                                                   | Cons                                                                                                                        |
| ----------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| **A. SF Lightning Dashboard** | wf.duckdb → CSV upload to SF custom object → SF dashboard | Native to SimCorp's BI stack; consistent with cockpit + sf-audit                                       | Brittle CSV pipeline; loses per-week trend granularity in SF reporting; requires SF admin permissions for the custom object |
| **B. Power BI / Fabric**      | DuckDB → parquet → Fabric workspace → PowerBI dashboard   | Andre has Fabric capacity already (PP3 + F64); per-rep / per-account dashboards are PowerBI's strength | Extra infra; Fabric workspace setup cost; PowerBI license dependency for viewers                                            |
| **C. Local TUI (Textual)**    | wf.duckdb → Python Textual app                            | Fast iteration, no auth complexity, mirrors `cockpit.py` pattern                                       | Single-user (Andre only); not shareable with directors                                                                      |

**Recommendation:** **Option B (Fabric)** is the most strategic — the workforce KPIs are exactly what Fabric is for, and Andre's PP3 capacity is currently underutilized for Sales Ops use cases. But **Option C (TUI)** is the fastest-to-ship MVP. Decide based on whether Andre wants this for his eyes only (TUI) or for sharing with directors (Fabric).

This decision is OUTSIDE Phase 1 scope. Document the trade-off, defer.

---

## 6. Compliance gates

Per `~/.claude/skills/simcorp-org-wrap/governance.md` and `~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md`:

**Hard rules from the SimCorp AI Code of Conduct that constrain this design:**

1. **People-related decision-making PROHIBITED through AI** — § governance rule 8. The wf.py CLI is **descriptive, not prescriptive**: it shows numbers, never recommends actions like "fire person X" or "give person Y a bonus."

2. **No content-level audit visibility on Claude** — § whitelist note. Therefore: NO LLM ingestion of workforce data in Phase 1. SQL aggregations only. If we ever feed this to an LLM (e.g., for synthesis), it must be aggregate-level (team rollups), never per-person.

3. **Strictly confidential / IP / third-party data is LIMITED** — § whitelist. Workforce data is internal personal/performance data, falls under "personal data" (which is YES allowed) but trips "people-related decision-making" if used to make decisions about identifiable individuals. Decision-grade output is ALLOWED for the human (Andre) to act on; AI-driven decisions on identifiable individuals are NOT.

4. **Cowork extra restriction:** "client services / sensitive client data / regulated work" forbidden in Cowork. Workforce data is internal — not client-facing — so Cowork is technically allowed, but per `~/.claude/intel/simcorp-claude-cowork-policy-2026-04-28.md`, Cowork "should not be used for compliance-critical, regulated, confidential, or audit-sensitive activities." Workforce performance data is at least "confidential" in spirit; **avoid Cowork for this work, prefer Claude Code + Codex CLI**.

5. **Data residency:** all DuckDB storage is on Andre's local Mac. No cloud upload. No third-party APIs see the data.

`docs/workforce/COMPLIANCE.md` formalizes these as rules the wf.py CLI must respect; tests should verify (e.g., assert no LLM call in any Phase 1 code path).

---

## 7. Risks + mitigations

| Risk                                                                 | Severity | Mitigation                                                                                                                          |
| -------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 4-month staleness gap (data ends 2025-12-15)                         | High     | Phase 2 closes it. Phase 1 explicitly labels every output with `as_of=2025-12-15` so users see the freshness.                       |
| Inferred roster misses people / includes wrong people                | Medium   | Roster swap-in path (env var) for Phase 2. Phase 1 flag: "roster is inferred — see KPI_DEFINITIONS.md."                             |
| KYC snapshot-only inflates KYC effort                                | Medium   | Treat KYC effort + cycle-time as PROXY only. Document in COMPLIANCE.md + KPI_DEFINITIONS.md.                                        |
| Effort weights (1/2/3/0.5) are guesses, not measured                 | Medium   | Make tunable via env var. Phase 2 calibration loop: compare effort-unit predictions to time-tracked alternatives if/when available. |
| AI Code of Conduct violation if anyone runs LLM over per-person data | High     | Phase 1 has ZERO LLM calls. Test asserts no `import openai` / no `AzureOpenAI` import in any wf.py code path.                       |
| DuckDB version drift (< 1.0 has breaking changes)                    | Low      | Pin `duckdb>=1.0.0,<2.0.0` in pyproject.toml.                                                                                       |
| Other Claude session edits same files (cockpit + sf-audit precedent) | Medium   | Track `track:workforce` is registered in AGENT_COORDINATION.md; other agents don't touch `scripts/workforce/`.                      |
| User runs `wf.py` from wrong directory                               | Low      | All paths resolved relative to `__file__`, not cwd.                                                                                 |

---

## 8. Test/verification protocol

**Phase 1 is "done" when ALL of:**

- [ ] All 5 raw files extracted to `workforce/raw/`
- [ ] `pyproject.toml` has `duckdb>=1.0.0`
- [ ] `wf.duckdb` exists and `duckdb wf.duckdb ".tables"` shows ≥15 tables
- [ ] All 5 sentinel tests in `scripts/workforce/tests/` pass
- [ ] All 5 CLI verbs (`team-week`, `person`, `anomalies`, `coverage`, `process-mix`) produce non-empty output
- [ ] `docs/AGENT_COORDINATION.md` updated with `track:workforce`
- [ ] `docs/workforce/{DATA_MODEL,KPI_DEFINITIONS,COMPLIANCE}.md` written
- [ ] Memory pointer added to MEMORY.md
- [ ] One commit landed: `feat(track:workforce): Phase 1 — static pack ingest + read-only wf.py CLI`

---

## 9. Open questions for Andre (decide before execution)

1. **Phase 3 surface:** dashboard (Fabric) vs TUI vs continue using the existing 112-slide PPTX as the consumer artifact? Affects Phase 2 design.

2. **Roster source:** should I try to find an authoritative `dim_people` from Workday (if/when CA-block is resolved per `feedback_simcorp_entra_ca_blocks_cli.md`) or accept the inferred roster for both Phase 1 + 2?

3. **Compliance posture:** does Group Compliance (Konrad Torun + Emilie Terney Bech) need to review this before Phase 1 lands? My read of the whitelist is "yes for Claude" but "personal data permitted" — the workforce angle is more nuanced. Defaulting to: **no review needed for Phase 1** because Phase 1 has zero AI involvement; **review before Phase 3** when consumers see the data.

4. **Effort weights:** keep the 1/2/3/0.5 baseline or recalibrate? Phase 1 uses spec defaults; Phase 2 could calibrate against any time-tracking proxy if one becomes available.

5. **Refresh cadence (Phase 2):** nightly (07:00, same as morning brief) or weekly (Monday 06:00)? Daily is more responsive but 7× the SF API cost.

6. **Naming:** `track:workforce` (descriptive) vs `track:rw-ap` (acronym-aligned with HANDOFF doc)? Going with `workforce` for clarity unless overridden.

---

## 10. Concrete Day-1 task checklist

When this Phase 1 session starts, work the list top-to-bottom. Each item is ≤30 min, the whole list ≈ 3 hours.

```
[ ] (5 min)  Read this plan top to bottom + AGENT_COORDINATION.md
[ ] (10 min) Create scripts/workforce/, workforce/raw/, workforce/state/, docs/workforce/
[ ] (5 min)  Add workforce/ to .gitignore (raw + state subdirs only; the scripts dir tracks)
[ ] (5 min)  Extract zip; verify 5 files
[ ] (5 min)  Add duckdb>=1.0.0 to pyproject.toml; pip install
[ ] (15 min) Write schema.sql with table DDL for 15 sheets + 2 csvs
[ ] (20 min) Write ingest.py + run; verify row counts vs README
[ ] (15 min) Write 5 sentinel tests in scripts/workforce/tests/; run; all pass
[ ] (10 min) Write _effort.py with weight constants
[ ] (15 min) Write queries.py with 5 parameterized analytic queries
[ ] (15 min) Write wf.py CLI dispatching to those queries
[ ] (15 min) Smoke-test all 5 CLI verbs against live DuckDB
[ ] (15 min) Write DATA_MODEL.md (cribbed from README + DuckDB \\d output)
[ ] (10 min) Write KPI_DEFINITIONS.md (per-metric meaning)
[ ] (10 min) Write COMPLIANCE.md (Code of Conduct mapping)
[ ] (5 min)  Update docs/AGENT_COORDINATION.md with track:workforce row
[ ] (5 min)  Add MEMORY.md pointer
[ ] (5 min)  Commit: feat(track:workforce): Phase 1 — static pack ingest + wf.py CLI
[ ] (5 min)  Verify: re-run all CLI verbs on the just-committed state
```

---

## 11. Coordination notes for future agents (Claude or Codex)

- **Read AGENTS.md (`~/.codex/AGENTS.md`) first** — it has the SimCorp tier-1 rules (ARR/ACV split, multi-currency, etc.) that apply to ALL Sales Ops work, not just the cockpit/sf-audit tracks.
- **The workforce track is read-only against SF in Phase 1.** No PATCH calls. No SF report creation. No SF dashboard creation.
- **Do not extend Phase 1 scope.** Forecasting, prediction, ML — all deferred to Phase 2+. Phase 1 = ingest + read-only CLI. Period.
- **Coordinate via this file.** If you need to extend the schema, add a section "## Schema extensions" with date + rationale; don't silently mutate.

---

**End of plan.** Total session estimate: 3 hours executable. All artifacts referenced above are stable and verified as of 2026-04-29.
