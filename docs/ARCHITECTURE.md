# LAND-monthly review pipeline — architecture

Authoritative architecture overview for the Sales Director Monthly LAND review pipeline. Reads in 10 minutes; covers data flow, the two-workbook split, the auditability contract, compliance posture, and what's locked vs. deferred.

## 1. One-paragraph summary

Every month, this pipeline produces a per-director pipeline-and-retention review for each of the 9 SimCorp MD-1 sales directors (Canada, NA AM, APAC, CE, SE, UKI, NL+Nordics, MEA, P&I US). It pulls each director's open Salesforce pipeline + closed-won + closed-renewal history scoped to their territory, FX-converts to EUR per-record (never via SOQL aggregate), bundles the snapshot into a Pydantic-validated `trends.json` envelope (schema_version=2), and writes two Excel workbooks plus a markdown brief into `state/<period>/<director-slug>/`. The director (or their PM) opens a SimCorp-branded `.pptx` in PowerPoint; think-cell datalinks bind chart cells to the workbooks. Subsequent months refresh in two clicks. Output audience: the 9 MD-1 directors and the Sales Ops team that reviews them. Output artifacts: `trends.json`, `brief.md`, `land.xlsx` (legacy precomputed), `land.model.xlsx` (formula-driven), and per-director PPTX (manual today, automated post-Claude-swap).

## 2. Data flow

```
Salesforce (preprod, simcorp.my.salesforce.com, API v66.0)
        │   sf CLI as apro@simcorp.com
        ▼
land_brief.py::pull_director_snapshot(director, period)            [land_brief.py:153]
   ├─ SOQL #1: open opps   (Type, Stage, dates, ARR_FX, ACV_FX, owner, account, risk)
   ├─ SOQL #2: closed CFQ  (won + lost this quarter)
   ├─ SOQL #3: closed-won 6-month roll
   ├─ SOQL #4: closed-renewals 12-month (GRR proxy)
   └─ Org-wide benchmarks via Reports REST (FX-correct s!field aggregates)
        │
        ▼
snapshot dict
   ├─ totals               (new_business_arr_open_this_quarter, renewal_acv_open_this_quarter, …)
   ├─ new_business_by_stage / renewals_by_stage
   ├─ raw_opps             (single seed for Data sheet — ID, Type, Stage, dates, owner, account, ARR_EUR, ACV_EUR)
   ├─ closed_cfq_rows      (Wins_Losses_QTD seed)
   ├─ closed_won_6mo_rows  (ARR_Roll + Trend_MoM/QoQ seed)
   ├─ closed_renewals_12mo_rows (Retention seed)
   ├─ top_deals_land / top_deals_expand    (named-account arrays)
   ├─ pending_commercial_approval          (named)
   └─ at_risk_renewals                     (named)
        │
        ▼
land_brief.py::build_trends_envelope(snapshot, director, period, backtest=…)  [land_brief.py:727]
   → trends.json (Pydantic-validated, extra=forbid, schema_version=2)
   → schema_version is bumped to 2 inside derive_action_items     [land_brief.py:1234]
        │
        ├─────────────► excel_model.py::build_director_model()    [excel_model.py:106]
        │                  → land.model.xlsx (formula-driven)
        │
        ├─────────────► excel_companion.py::build_director_excel()
        │                  → land.xlsx (legacy precomputed; named-account lists + org-wide reports)
        │
        └─────────────► render_director_brief() → brief.md
        │
        ▼
Human opens assets/LAND_template.pptx → Save-As <Director>-<Period>.pptx
think-cell binds chart cells to model.xlsx + legacy.xlsx (per docs/THINKCELL_SETUP.md)
        │
        ▼
Subsequent months: re-run land_brief; "Update charts now" or "Switch to alternate
data source" for the 9-director fan-out.
```

`run_land_to_deck.py --all-directors` is wired into the cron but is best-effort and skipped during the LLM-substrate park (per `feedback_deck_llm_substrate_2026-04-29.md`); ETL artifacts are produced regardless.

## 3. The two-workbook split — what's where, why

Two workbooks ship per director, in the same directory. Slides bind to whichever exposes the data.

### `land.model.xlsx` — formula-driven (single source of truth)

Built by `excel_model.py::build_director_model` ([excel_model.py:106](../scripts/excel_model.py)). Every analytical cell is `SUMIFS`/`COUNTIFS`/`SUMPRODUCT`/`INDEX-MATCH` against three input sheets: `Data` (one row per open opp), `Data_ClosedCFQ`/`Data_ClosedWon6mo`/`Data_Renewals12mo` (closed history), and `Parameters` (thresholds + period bounds, workbook-scoped named ranges). Stage labels live in `Stages`, sourced from `sales_process_graph.GRAPH.stages` so the workbook can never drift from the canonical knowledge graph.

Cell colors follow the FAST/ICAEW convention so stakeholders moving between Anthropic xlsx-Skill workbooks and ours see one auditability scheme: blue (input/hardcoded), black (formula on same sheet), green (formula crossing sheets), red (formula crossing workbooks — never used here).

| Category             | Sheets                                                                                                                                                      |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Identity / inputs    | Cover, Parameters, Stages                                                                                                                                   |
| Raw data (INPUT)     | Data, Data_ClosedCFQ, Data_ClosedWon6mo, Data_Renewals12mo                                                                                                  |
| Headline KPIs        | Pipeline_Total, Pipe_Movement                                                                                                                               |
| Analytical (formula) | Pipeline_By_Stage, Pipeline_Aging, By_Owner, Pivots, Velocity, Concentration, Weighted_Forecast, ARR_Roll, Trend_MoM, Trend_QoQ, Retention, Wins_Losses_QTD |
| Documentation        | Methodology                                                                                                                                                 |

Pivots ([excel_model.py:886](../scripts/excel_model.py)) carries five pre-built cross-tabs (Stage × Industry being the one bound by slide 12's Mekko). Verified sheet count: **22** (19 direct `wb.create_sheet` calls + 3 invocations of the closed-history helper).

Planned analytical sheets (still in legacy today, migration to model in flight): Forecast_Category, Top_Accounts, Territory_Performance, Sales_Velocity, Account_Expansion, Pipeline_Creation_Velocity, Stale_Activity.

### `land.xlsx` — legacy precomputed (named lists + org-wide reports)

Built by `excel_companion.py::build_director_excel`. **Every cell is a constant**; the audit trail goes back through Python, not formulas. Status flagged "legacy/knowledge-artifact" in the docstring ([excel_companion.py:1-25](../scripts/excel_companion.py)). Stays the source for sheets that don't fit a SUMIFS pattern:

- **Named-account lists**: Top_Deals_Land, Top_Deals_Expand, Pending_Commercial_Approval, At_Risk_Renewals
- **Org-wide pulls**: Discount_Analysis, Regional_Benchmarks, Region_Trend_8Q (FX-correct via SF Report `s!field` aggregates)
- **Action_Items** rule outputs (8 rules from `sales_process_graph.GRAPH.rules`)

`SHEET_NAMES` constant in [excel_companion.py:86](../scripts/excel_companion.py) lists the full 27-entry order for the legacy companion.

### Slide-to-workbook binding

Per [docs/THINKCELL_SETUP.md](THINKCELL_SETUP.md) §"two-workbook split":

| Slides                     | Source               | Why                                                         |
| -------------------------- | -------------------- | ----------------------------------------------------------- |
| 2, 3, 4, 5, 11, 12, 13, 14 | `land.model.xlsx`    | Formula-traceable headline + analytical KPIs                |
| 6, 7, 8, 9, 10, 15         | `land.xlsx` (legacy) | Named-account tables + org-wide reports + Action_Items      |
| 1, 16, 17                  | n/a (text/narrative) | Cover, Risks prose pasted from brief.md, closing disclaimer |

## 4. Auditability — click-trace recipe

Take the headline KPI on slide 2: **closeable Land+Expand ARR for the period**, bound to `Pipeline_Total!B2`. A stakeholder asks "where does that number come from?" Walk:

| Click | Cell / range                                | Formula bar shows                                                                                                                                                                                                            | What it means                                                                                            |
| ----- | ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| 1     | `Pipeline_Total!B2`                         | `=SUMIFS(Data_ARR_EUR, Data_Type, "Land", Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end) + SUMIFS(Data_ARR_EUR, Data_Type, "Expand", Data_CloseDate, ">="&period_start, Data_CloseDate, "<"&period_end)` | Sum of two motions, period-windowed                                                                      |
| 2     | `period_start`, `period_end` (named ranges) | Defined as `Parameters!$B$2` and `Parameters!$B$3`                                                                                                                                                                           | Workbook-scoped names; single edit propagates                                                            |
| 3     | `Parameters!B2`                             | `2026-04-01` (blue INPUT)                                                                                                                                                                                                    | First day of the review period (inclusive)                                                               |
| 4     | `Data_ARR_EUR` (named range)                | Defined as `Data!$K$2:$K$N` over the Excel Table `tblData`                                                                                                                                                                   | Auto-extends as opps are added                                                                           |
| 5     | `Data!K42` (any sample cell)                | `1842373.21` (blue INPUT)                                                                                                                                                                                                    | One opp's `convertCurrency(APTS_Opportunity_ARR__c)` value, FX-converted to EUR by Salesforce per-record |

Five clicks — input value to headline. No Python in the loop. The same pattern works for every other formula sheet: a stage row in `Pipeline_By_Stage` walks back through `tblData[StageName]`; a row in `Pipeline_Aging` walks through `tblData[CreatedDate]`; the `Weighted_Forecast` block layers `Stages` × `Pipeline_By_Stage!ARR` × `Weighted_Forecast!ForwardRate` (forward rates are blue inputs from `forecast_backtest.py`, editable to test sensitivity).

## 5. Compliance posture

Per `feedback_simcorp_enterprise_claude_per_deal_2026-04-30.md`:

- **Consent basis**: SimCorp's enterprise Anthropic Claude contract carries data residency + no-training-on-customer-data + audit logs. This satisfies the SimCorp AI Code of Conduct §8 "explicit consent for client data" requirement.
- **Per-deal context flows freely** through `trends.json` (`top_deals_named`, `pending_commercial_approval_named`, `at_risk_renewals_named`), through both xlsx workbooks, through LLM-generated narrative, and through chart bindings. Reference accounts by name when it sharpens the message — "Lembaga Tabung Haji's ILF deal slipped from Q2 to Q3" beats "one APAC deal slipped".
- **Hard rules that DO still apply**:
  - Outputs are advisory, never the sole basis for commercial / financial / legal decisions.
  - No people-related decision-making (CV, performance, etc.).
  - No regulated / compliance-relevant work via Claude.
  - Not for redistribution outside SimCorp.

The earlier "aggregate-only / no client-level data" framing in CLAUDE.md and HANDOFF.md was over-restrictive; this memory supersedes it. Cover-sheet text in the model workbook ([excel_model.py:191](../scripts/excel_model.py)) and the LAND system prompt ([brand-deck-agent-py/agent/land_system_prompt.py:50-56](../../brand-deck-agent-py/agent/land_system_prompt.py)) both reflect the new framing.

## 6. Schedule + automation

| Item                 | Value                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------- |
| launchd label        | `com.simcorp.sales-ops-copilot.land-monthly`                                                                  |
| Schedule             | 06:00 local on the 1st of each month                                                                          |
| What it runs         | `forecast_backtest.py --quarters-back 4` then `land_brief.py --all-directors --period <auto-Q>`               |
| Period auto-compute  | `($(date +%-m)-1)/3+1` — calendar quarter from today's month                                                  |
| Per-director outputs | `state/<period>/<director-slug>/{trends.json, brief.md, land.xlsx, land.model.xlsx}`                          |
| Logs                 | `state/land-monthly-cron.log` (append stdout), `state/land-monthly-stderr.log` (launchd capture)              |
| Failure alert        | **None today** — Phase 2 backlog (cron silently produces no PPTX if deck endpoint is down)                    |
| Env block            | Explicit PATH + HOME per `project_ai_os_daemon_env.md` (without it, claude/codex CLIs fall through to Ollama) |

The deck-generation step (`run_land_to_deck.py --all-directors`) is wired but best-effort during the LLM-substrate park; failures log to `state/land-monthly-deck-gen.log` without halting ETL.

## 7. Locked artifacts (what doesn't move)

| Artifact                          | Owner / source                                                                                                           | Why locked                                                                                                              |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **8-stage SimCorp sales process** | `sales_process_graph.GRAPH.stages`                                                                                       | Verbatim from the SimCorp Commercial Handbook 2026-04                                                                   |
| **5 governance gates**            | `sales_process_graph.GRAPH.gates`                                                                                        | Commercial Approval, Margin Review, Deal Services Design, Deal Review, Due Diligence                                    |
| **3 motions**                     | `sales_process_graph.GRAPH.motions`                                                                                      | LAND, EXPAND, RENEWAL — different ARR/ACV fields, different processes                                                   |
| **ARR vs ACV separation**         | Fields `APTS_Opportunity_ARR__c` (L+E) vs `APTS_Renewal_ACV__c` (Renewal)                                                | SimCorp cardinal rule (`feedback_simcorp_arr_acv_separation.md`) — never sum or blend, never use `Opportunity.Amount`   |
| **FX correctness**                | Per-record `convertCurrency()` in SOQL SELECT                                                                            | SOQL `SUM(convertCurrency(...))` silently returns raw multi-currency sums (`feedback_sf_multi_currency_aggregation.md`) |
| **Pydantic envelope**             | `brand-deck-agent-py/agent/land_input_schema.py`, `extra=forbid`                                                         | Hard schema lock at the deck endpoint boundary; downstream LLM input shape pinned                                       |
| **20-slide LAND outline**         | `brand-deck-agent-py/agent/land_system_prompt.py:71-94`                                                                  | schema_version=2                                                                                                        |
| **8-rule action-item set**        | `sales_process_graph.GRAPH.rules`                                                                                        | Rule semantics + thresholds + suggested actions documented in graph                                                     |
| **9 MD-1 director scope**         | `_directors.py` (Account.Region\_\_c + BillingCountry + Industry per `feedback_sf_director_scope_via_account_region.md`) | Sales_Director_Book\_\_c does NOT exist on Account                                                                      |

## 8. Phase 2 backlog

| #   | Item                                  | Notes                                                                                                                                                                       |
| --- | ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | think-cell deck wiring                | Manual one-time per director → automated refresh thereafter (`docs/THINKCELL_SETUP.md`)                                                                                     |
| 2   | Style file embed in master template   | `assets/SimCorp-thinkcell-style.xml` exists; Mac `LoadStyle` is Windows-only                                                                                                |
| 3   | Distribution layer                    | SharePoint upload via M365 MCP / Graph (existing skill: `simcorp-presentation-style`)                                                                                       |
| 4   | Failure alerts on launchd             | Stderr-pattern alarm; no email/Teams alert today                                                                                                                            |
| 5   | `--period` parameterization           | `pull_director_snapshot` hardcodes `CloseDate = THIS_QUARTER` ([land_brief.py:179](../scripts/land_brief.py)); explicit period bounds need to flow through                  |
| 6   | OFH-driven waterfall decomposition    | `Pipe_Movement` New+Advanced bucket is currently a residual; needs `OpportunityFieldHistory` mining                                                                         |
| 7   | Competitive_Pressure SOQL extension   | Needs `Lost_to_Competitor__r.Name` on the open-pipe query before the formula sheet can be wired                                                                             |
| 8   | True NRR / cohort retention           | Today's GRR is a proxy (won ACV / (won + lost ACV) of CLOSED Renewals); needs `Pipeline_Snapshot__c` populated for cohort math                                              |
| 9   | Action-item close-the-loop ledger     | Today's actions surface monthly but don't track resolution across periods                                                                                                   |
| 10  | LAND endpoint LLM swap                | `feat/land-endpoint` parked at tag `phase-1.5-plan-b-feature-complete`; swap Foundry → enterprise Claude in `agent/loop.py` per `feedback_deck_llm_substrate_2026-04-29.md` |
| 11  | Migrate named-account tables to model | Eliminate the legacy companion; everything reads from `land.model.xlsx`                                                                                                     |

## 9. Key files map

| Path                                                         | Role                                                                                                                                                                               |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/land_brief.py` (1417 lines)                         | Orchestrator: SOQL pulls → snapshot → envelope → brief.md + both workbooks                                                                                                         |
| `scripts/excel_model.py` (1861 lines)                        | Formula-driven `land.model.xlsx` generator (22 sheets)                                                                                                                             |
| `scripts/excel_companion.py` (1384 lines)                    | Legacy precomputed `land.xlsx` (named lists + org-wide; `SHEET_NAMES`)                                                                                                             |
| `scripts/sales_process_graph.py` (739 lines)                 | Typed knowledge graph — 8 stages, 5 gates, 3 motions, 9 metrics, 8 rules, 25 qualifiers; cross-project import root                                                                 |
| `scripts/build_land_template.py` (387 lines)                 | One-time SimCorp-branded PPTX template builder; `SLIDES` list = **17 entries** (note: docstring says 28, code says 17 — the locked LAND outline in `land_system_prompt.py` has 20) |
| `scripts/model_recalc.py` (163 lines)                        | Python-only formula evaluator + audit gate — verifies model.xlsx formulas resolve before downstream consumers see it                                                               |
| `scripts/regional_memo.py` (215 lines)                       | NA / EMEA / APAC / P&I rollups across the 9 directors                                                                                                                              |
| `scripts/_directors.py` (119 lines)                          | 9 MD-1 directors + `where_clause` scope (Account.Region\_\_c + BillingCountry + Industry)                                                                                          |
| `scripts/run_land_to_deck.py`                                | Bridge from `trends.json` → `/api/generate-land-deck` (parked until Claude swap)                                                                                                   |
| `scripts/forecast_backtest.py`                               | Org-wide stage forward rates from `OpportunityFieldHistory`; feeds `Weighted_Forecast`                                                                                             |
| `assets/LAND_template.pptx`                                  | SimCorp-branded template (17 slides today; outline target is 20)                                                                                                                   |
| `assets/SimCorp-thinkcell-style.xml`                         | Brand style file for think-cell `Change Style` (Mac-compatible path)                                                                                                               |
| `docs/THINKCELL_SETUP.md`                                    | Wiring runbook + slide-to-range binding table                                                                                                                                      |
| `docs/SALES_PROCESS_GRAPH.md`                                | Knowledge graph design + cross-project usage patterns                                                                                                                              |
| `docs/LAND_DECK_PIPELINE_AUDIT_2026-04-29.md`                | Deep audit; punch list of gaps; target architecture                                                                                                                                |
| `~/projects/brand-deck-agent-py/agent/land_system_prompt.py` | LLM system prompt; locked 20-slide outline (schema_version=2)                                                                                                                      |
| `~/projects/brand-deck-agent-py/agent/land_input_schema.py`  | Pydantic envelope schema (`extra=forbid`)                                                                                                                                          |

---

_Authoritative as of 2026-04-30. Schedule + locked artifacts verified against live launchd plist + scripts. Phase 2 backlog pulled from `LAND_DECK_PIPELINE_AUDIT_2026-04-29.md` §7 + `feedback_deck_llm_substrate_2026-04-29.md`. Update this file when (1) the LLM substrate swaps, (2) the legacy named-account sheets migrate, or (3) the schedule layer changes._
