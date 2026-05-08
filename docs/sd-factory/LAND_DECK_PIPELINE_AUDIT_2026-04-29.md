# LAND Deck Pipeline — Deep Audit (2026-04-29)

End-to-end review of the Sales Director Monthly LAND review pipeline.
Verifies the schedule, locks the data contract, identifies gaps against
the requirements ("monthly auto-kickoff first of every month, deck +
memo/action-item queue per region, think-cell integration").

---

## TL;DR — Status by Requirement

| Requirement                                    | Status              | Gap                                                         |
| ---------------------------------------------- | ------------------- | ----------------------------------------------------------- |
| Monthly auto-kickoff on the 1st of every month | ✅ verified         | None at the schedule layer                                  |
| Auto-create the deck (PPTX)                    | ⚠️ partial          | Cron only runs ETL; deck must be triggered manually         |
| Memo / action-item queue per **region**        | ❌ missing          | Per-director risks exist, no region-level rollup or memo    |
| think-cell linking Excel data → PowerPoint     | ❌ not integrated   | Decks are agent-generated PPTX (no live Excel link)         |
| Lock the format                                | ⚠️ partial          | Slide structure is in the agent prompt, not a hard contract |
| Lock the data                                  | ✅ schema_version=1 | Pydantic `extra=forbid` on the endpoint validates the input |

---

## 1. Schedule — VERIFIED LOCKED

**File:** `~/Library/LaunchAgents/com.simcorp.sales-ops-copilot.land-monthly.plist`

```xml
<key>StartCalendarInterval</key>
<dict>
  <key>Day</key><integer>1</integer>
  <key>Hour</key><integer>6</integer>
  <key>Minute</key><integer>0</integer>
</dict>
```

Fires at **06:00 local on the 1st of every month**. `launchctl list` confirms it's loaded (status 0). Last successful run: 2026-04-28 (manual reload during today's session — but the schedule itself is correct).

**What it runs:**

```bash
cd /Users/test/code/apps/sales-ops-copilot \
  && .venv/bin/python3 scripts/forecast_backtest.py --quarters-back 4 \
  && .venv/bin/python3 scripts/land_brief.py \
       --all-directors \
       --period $(date +%Y)-Q$(echo "scale=0; ($(date +%-m)-1)/3+1" | bc)
```

**Period auto-computation:**
`($(date +%-m)-1)/3+1` → calendar quarter from today's month. April → Q2, July → Q3, etc.
On the 1st of January, this fires for Q1 of the current year. Correct for retrospective monthly reviews.

**Logs:**

- `state/land-monthly-cron.log` — append-only stdout
- `state/land-monthly-stdout.log` / `state/land-monthly-stderr.log` — launchd captures

---

## 2. ETL Pipeline — Per-Director Outputs

For each of the 9 MD-1 directors, the cron produces:

```
state/<period>/<director-slug>/
├── trends.json   ← canonical envelope, schema_version=1
├── brief.md      ← markdown memo (highlights + risks + KPIs + forecast backtest)
└── land.xlsx     ← 15-sheet Excel companion
```

**The 9 MD-1 directors** (from `scripts/_directors.py`):

| Director          | Scope                  |
| ----------------- | ---------------------- |
| Megan Miceli      | Canada                 |
| Patrick Gaughan   | NA Asset Management    |
| Jesper Tyrer      | APAC                   |
| Sarah Pittroff    | Central Europe         |
| Francois Thaury   | Southern Europe        |
| Dan Peppett       | UK & Ireland           |
| Christian Ebbesen | NL & Nordics           |
| Mourad            | Middle East & Africa   |
| Adam Steinhouse   | US Pension & Insurance |

Each director has a SOQL `where_clause` over `Account.{Region__c, BillingCountry, Industry}` — verified canonical scope per `feedback_sf_director_scope_via_account_region.md` memory.

---

## 3. Data Contract — LOCKED

### `trends.json` envelope

**Top-level keys** (verified from `state/2026-Q2/Adam-Steinhouse/trends.json`):

```json
{
  "schema_version": 1,
  "director": {...},
  "period": "2026-Q2",
  "period_end": "2026-06-30",
  "currency": "EUR",
  "currency_format": "...",
  "kpis": [...],          // list of {name, value, unit, priority, ...}
  "highlights": [...],    // rule-based, from derive_highlights_risks
  "risks": [...],         // rule-based, from derive_highlights_risks
  "context_quotes": [...],
  "edge_case_flags": [...]
}
```

**Schema is enforced** in `brand-deck-agent-py/agent/land_input_schema.py` as a Pydantic model with `extra=forbid` — i.e., the deck endpoint **rejects** envelopes with unknown keys. This is the data lock.

### `land.xlsx` — 15 sheets (in this order)

|   # | Sheet                 | Purpose                            |
| --: | --------------------- | ---------------------------------- |
|   1 | Cover                 | Director / period / scope identity |
|   2 | Pipeline_Total        | Total open ARR + ACV               |
|   3 | Pipeline_By_Stage     | 8-stage breakdown                  |
|   4 | Top_Deals_Land        | Largest Land + Expand opps         |
|   5 | Top_Deals_Expand      | (separate sheet)                   |
|   6 | Wins_Losses_QTD       | This-Q closed                      |
|   7 | ARR_Roll              | Booked vs forecast roll            |
|   8 | Retention             | GRR / NRR-proxy                    |
|   9 | Forecast_Backtest     | Stage-conversion forward rates     |
|  10 | At_Risk_Renewals      | Renewal exposure                   |
|  11 | Competitive_Pressure  | Lost-to-competitor records         |
|  12 | Territory_Performance | Director-scope vs org              |
|  13 | Trend_MoM             | Month-over-month                   |
|  14 | Trend_QoQ             | Quarter-over-quarter               |
|  15 | Methodology           | KPI definitions + caveats          |

This **is** the data contract for any think-cell datalink design (see §6). Every chart in the deck should reference one of these named sheets.

### `brief.md` — markdown memo

Currently has these sections (per `render_director_brief` in `scripts/land_brief.py:250`):

- `# <director> — <period> LAND review`
- `## Highlights` (rule-based, max 5)
- `## Risks` (rule-based, max 5)
- `## Forecast backtest` (table)
- `## KPIs` (table)

**No "Action Items" section.** No "Memo to <director>". No "What to do this month".

---

## 4. Deck Generation — PARTIALLY AUTOMATED

**The cron runs ETL only.** `run_land_to_deck.py` (the bridge to the deck endpoint) is **NOT** invoked from launchd. Decks must be triggered manually:

```bash
python3 scripts/run_land_to_deck.py --director "Adam Steinhouse" --period 2026-Q2
```

**One PPTX exists in the org**: `state/2026-Q2/Adam-Steinhouse/Adam-Steinhouse-2026-Q2-LAND.pptx` (8.8MB, 21 slides, generated 2026-04-28 14:57 manually).

**Slide structure (verified from the existing PPTX):**

```
[ 1] LAND Review (cover)
[ 2] Agenda
[ 3] Highlights
[ 4] 01 (section divider)
[ 5] Total Pipeline Stands at 0.57 mEUR ARR Across 10 Deals
[ 6] Discovery Stage Concentrates 65% of ARR at 0.37 mEUR
[ 7] Discovery and Contracting Drive 93% of Total ARR
[ 8] Discovery Holds Two Thirds of All Pipeline ARR Value
[ 9] Mid-Stage ARR Drops to Zero Creating a Conversion Gap
[10] 02 (section divider)
[11] Renewal ACV Registers at Zero for Q2 2026 Period
[12] NRR and GRR Cannot Be Calculated With Zero Renewals
[13] Back-Test Shows Stage 6 Converts at 87% Forward Rate
[14] 03 (section divider)
[15] Book code P&I is the sole territory for this director
[16] Market Position Analysis
[17] No lost-to-competitor records in Q2 2026 for P&I US
[18] 04 (section divider)
[19] Late-Stage Concentration Falls Below the 30% Threshold
[20] Late-Stage Concentration
[21] Advisory output only. Not the sole basis for commercial decisions (compliance footer)
```

**21 slides, not 19** as documented in the LAND prompt — the agent generated 2 extra (probably consolidating or expanding a section). **The slide outline is in the prompt, not the contract.** That's not a hard format-lock.

### Deck endpoint (Plan B) — feature-complete on branch

`brand-deck-agent-py` branch `feat/land-endpoint`:

- 7 commits ahead of `main`
- Tagged `phase-1.5-plan-b-feature-complete`
- `/api/generate-land-deck` endpoint validates the trends.json envelope (Pydantic `extra=forbid`), dispatches `AgentLoop` with `LAND_REVIEW_PROFILE` audience, returns a download URL for the PPTX
- **Not pushed, not merged** — awaits Andre's real-Foundry e2e call

---

## 5. Memo / Action-Item Queue — MISSING

### Current state

`derive_highlights_risks()` (in `scripts/land_brief.py:201`) is a **rule-based** generator with two rules:

1. **Late-stage concentration > 70%** → highlight ("strong near-term close potential")
2. **Late-stage concentration < 30%** → risk ("quarter coverage at risk")
3. **renewal_acv < 100K** → risk ("verify renewal-eligible accounts")

That's it. No coverage rule. No zombie rule. No approval-gap rule. No activity-drought rule. No competitive-pressure rule. No region rollup.

### What's needed to meet the "memo / action-item queue per region" requirement

A new **Regional Memo** layer that:

1. **Aggregates directors into regions.** The 9 MD-1 directors fan out across territories — but there's no explicit region grouping. Either we treat each MD-1 as their own "region" (cleanest given the existing scope) **or** we roll up into ~4-5 super-regions (NA, EMEA, APAC, P&I).

2. **Produces a per-region memo** (markdown / PDF) that lists:
   - The top 3-5 action items for that region this month, ranked
   - Each tied to: a metric, a delta from last month, and a specific deal-or-account-named follow-up
   - Owner of each action (the MD-1 director or a named rep)
   - Due date (typically the next month)

3. **Syncs to the deck** — each director's deck should end with an "Action Items" slide that lists their personal queue, derived from the memo.

### Proposed action-item rule set (extending the current 2 rules)

| Rule                                                        | Threshold      | Action                                                            |
| ----------------------------------------------------------- | -------------- | ----------------------------------------------------------------- |
| Zombie ARR (>730d open, no activity 60d)                    | > EUR 5M       | "Review zombies with each rep, decide close/disqualify"           |
| Coverage Gap (Tier-1 accts no open opp 90d)                 | > 5 accounts   | "Assign account ownership review for Tier-1 accounts"             |
| Approval Gap (Stage 3+ Land ≥$500k, no Commercial Approval) | any            | "Submit for Commercial Approval before EOM"                       |
| SimCorp One pipeline share                                  | < 30% of total | "Discuss platform-led selling motion in next pipeline review"     |
| Late-stage concentration                                    | < 30%          | "Schedule Stage 3 → 4 progression workshops with reps"            |
| Renewal ACV at risk (90d window)                            | > EUR 1M       | "Engage CSM team on renewal cadence for at-risk accounts"         |
| Slipped opps (CFQ, ≥1 push)                                 | > 10 deals     | "1:1 with each rep on slipped deals; reset close-date discipline" |
| Activity drought (CFQ opps, no activity 30d)                | > 25% of book  | "Activity-tracking review with reps; set 14d touch SLA"           |

These map to **reports we already have live** — Cockpit_Zombie, Cockpit_CoverageGap, Approval Gap, FA · Slippage, Activity Drought, etc. The action-item generator becomes a small `derive_action_items(envelope, alerts) -> list[Action]` function in `scripts/land_brief.py`.

---

## 6. think-cell Integration — RESEARCH PENDING

A separate research agent is reviewing think-cell's 2024-2026 programmatic capabilities (datalinks, JSON chart embedding, server/API options, Mac compatibility, licensing). I'll fold those findings into this audit as an addendum — for now, the design space:

### Plausible think-cell architectures (to evaluate against research findings)

**Option A — Pure datalinks (manual template + per-director Excel swap)**

- Build one master `LAND_template.pptx` with think-cell charts pre-linked to a fixed Excel layout (uses the 15 sheets in `land.xlsx`)
- Monthly automation: ETL writes `land.xlsx` → analyst opens template → think-cell "Update charts now" → save as `<director>-<period>-LAND.pptx`
- Pro: cheapest think-cell integration. Pro: WYSIWYG live-link (no agent hallucinations on numbers). Con: requires a per-director template instance; per-director chart manual setup.

**Option B — JSON chart embedding (if think-cell exposes it)**

- Generate think-cell JSON chart spec from each director's land.xlsx via Python
- Embed JSON in slide notes or placeholder shapes; think-cell picks it up on open
- Pro: full automation. Pro: same trends.json drives both python-pptx structure AND think-cell charts. Con: if the JSON spec doesn't exist in current think-cell, this is roadmap-only.

**Option C — Hybrid: Plan B agent for narrative, think-cell for charts**

- Agent generates the narrative slide titles + bullets (today's behavior)
- Agent emits a `chart_spec` referencing think-cell-friendly Excel ranges
- The deck assembler creates a python-pptx skeleton with placeholder shapes
- think-cell reads the chart_spec from each shape on first open and renders
- Pro: best of both. Con: relies on think-cell JSON being available + stable.

**The decision gate is whether think-cell ships a programmatic chart-generation path that doesn't require Windows Office.** That's what the research agent is verifying.

---

## 7. Identified Gaps — Punch List

### Format

- [G1] **Slide outline lives only in the agent prompt** (`agent/land_system_prompt.py`). No machine-readable contract. If the agent drifts (today's deck has 21 slides instead of 19), nothing catches it.
- [G2] **No "Action Items" slide** in the agent's slide outline.
- [G3] **No region-level deck or memo** — only per-director artifacts.
- [G4] **No deck-level QA pass** — slides like "Renewal ACV Registers at Zero" + "NRR and GRR Cannot Be Calculated With Zero Renewals" pad the deck for sparse-data directors. A pre-filter ("if renewal_acv == 0, skip the renewal section") would tighten the output.

### Data

- [D1] **`trends.json` doesn't include today's new SF signals**: zombie book, coverage gap, SimCorp One pipeline, approval gap, slippage. These are live in the morning brief but not in the LAND envelope.
- [D2] **No QoQ delta in trends.json** — `Trend_QoQ` is in the xlsx but the JSON envelope doesn't have it, so the agent can't reference it as locked numbers.
- [D3] **`schema_version` is `1`** — when we add new KPIs, version-bump and migrate.

### Schedule

- [S1] **Cron does NOT run `run_land_to_deck.py`** — only ETL fires monthly. Decks are manual.
- [S2] **No "deck successfully generated" alert** — if the deck endpoint is down, the cron silently produces no PPTX with no notification.
- [S3] **No `RunAtLoad: true`** — if the Mac is asleep at 06:00 on the 1st, the cron may miss the window. macOS launchd does coalesce missed StartCalendarInterval events on wake, but worth verifying it caught the last few firings.

### Region rollup

- [R1] **No `pull_region_summary()` function** — there's no aggregation of the 9 director envelopes into regional groups.
- [R2] **No `regional_memo.md`** output.
- [R3] **No "memo to MD-1 group leadership"** consumer — the 9 directors get individual decks but Hanen Borchani (or whoever runs the regional review) has no consolidated view.

### think-cell

- [T1] **Zero references to think-cell anywhere in either repo.** Greenfield decision.

---

## 8. Recommended Target Architecture

```
                         ┌──────────────────────┐
                         │  launchd 1st-of-mo   │
                         │  06:00 local         │
                         └──────────┬───────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  ▼                 ▼                  ▼
        ┌─────────────────┐  ┌────────────┐   ┌──────────────────┐
        │ forecast_       │  │ land_brief │   │ regional_memo.py │
        │ backtest.py     │  │  --all-    │   │  --aggregate     │
        │  (4 quarters)   │  │  directors │   │     (NEW)        │
        └─────────────────┘  └─────┬──────┘   └────────┬─────────┘
                                   │                    │
                        per-director artifacts:    per-region memos:
                        trends.json + brief.md +  state/<period>/__regional__/
                        land.xlsx                  {NA,EMEA,APAC,P&I}.md
                                   │                    │
                                   ▼                    ▼
                        ┌──────────────────────────────────┐
                        │  run_land_to_deck.py             │
                        │  --all-directors  (NEW invoke)   │
                        │  POSTs trends.json → deck endpoint│
                        │  Downloads PPTX                  │
                        └──────────┬───────────────────────┘
                                   │
                                   ▼
                ┌─────────────────────────────────────┐
                │  PPTX (per director)                │
                │  ── narrative slides via agent      │
                │  ── chart slides via think-cell      │
                │     (if research confirms feasibility)│
                │  ── final "Action Items" slide       │
                │     fed from action_items in trends  │
                └──────────┬──────────────────────────┘
                           │
                           ▼
                ┌─────────────────────────────────────┐
                │  SharePoint upload                  │
                │  (M365 MCP or graph API)            │
                │  Path: /Sales Director Reviews/<period>/│
                └─────────────────────────────────────┘
```

### Concrete additions

1. **`scripts/regional_memo.py`** — aggregates the 9 director envelopes into ~4 regional buckets, runs the action-item rule set per region, writes `state/<period>/__regional__/<region>.md`.
2. **Extend `derive_highlights_risks()` → `derive_highlights_risks_actions()`** with the 8-rule action-item generator from §5.
3. **Add `action_items: list[ActionItem]` to `trends.json` schema_version=2**.
4. **Update `land_system_prompt.py` slide outline** to end with an "Action Items" slide (slide 19 or 20 — make it real, not implicit).
5. **Wire `run_land_to_deck.py --all-directors` into the launchd cron** so decks fire monthly.
6. **Wire SharePoint upload** (existing `simcorp-presentation-style` skill / sd-monthly skill has a working M365 MCP path).
7. **think-cell decision** after the research lands.

### Format lock — the canonical contract

Once the action-items addition is done, the format lock looks like:

| Layer         | Contract                                                                                                                                                  |
| ------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `trends.json` | Pydantic schema_version=2, `extra=forbid`, KPIs + highlights + risks + **action_items** + edge_case_flags                                                 |
| `land.xlsx`   | 15 named sheets, fixed order, fixed column structure (this IS the data contract)                                                                          |
| `brief.md`    | Highlights / Risks / **Action Items** / Forecast backtest / KPIs (5 fixed sections)                                                                       |
| Slide outline | 19 slides, slide_index → required_content (cover / agenda / highlights / 4 sections × 4 slides + section dividers / **action items** / compliance footer) |
| Regional memo | (NEW) one file per region, top 3-5 actions, owner + due date + supporting metric                                                                          |

---

## 9. Recommended Next Steps (in execution order)

1. **(now, 30 min)** Extend `derive_highlights_risks()` to produce `action_items` per the 8-rule set in §5. Add to `trends.json` envelope. schema_version → 2.
2. **(now, 30 min)** Add `regional_memo.py` that fans the 9 director envelopes into regional buckets and writes per-region memos.
3. **(now, 15 min)** Wire `run_land_to_deck.py --all-directors` into the launchd cron after `land_brief.py`. Add a "deck generation failed" stderr alarm pattern.
4. **(after think-cell research lands)** Decide on think-cell integration path. Write a plan (no code yet).
5. **(deferred, Andre's call)** Real-Foundry e2e validation of `/api/generate-land-deck`. Merge `feat/land-endpoint`. Push.
6. **(deferred)** SharePoint upload of monthly PPTX batch via M365 MCP.

---

## Appendix — File / ID Reference

| Artifact                     | Path or ID                                                                |
| ---------------------------- | ------------------------------------------------------------------------- |
| launchd plist                | `~/Library/LaunchAgents/com.simcorp.sales-ops-copilot.land-monthly.plist` |
| ETL driver                   | `scripts/land_brief.py` (~12.5K, 6 functions)                             |
| Deck bridge                  | `scripts/run_land_to_deck.py` (~6K)                                       |
| Director scope module        | `scripts/_directors.py` (9 directors)                                     |
| Excel companion builder      | `scripts/excel_companion.py`                                              |
| LAND endpoint (deck side)    | `~/projects/brand-deck-agent-py/agent/api/...`                            |
| LAND system prompt           | `~/projects/brand-deck-agent-py/agent/land_system_prompt.py`              |
| LAND input schema            | `~/projects/brand-deck-agent-py/agent/land_input_schema.py`               |
| Per-director outputs         | `state/2026-Q2/<slug>/{trends.json,brief.md,land.xlsx,*.pptx}`            |
| Brand-deck branch (unmerged) | `feat/land-endpoint` @ `phase-1.5-plan-b-feature-complete`                |
