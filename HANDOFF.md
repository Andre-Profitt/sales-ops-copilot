# Handoff — sales-ops-copilot

**Last updated:** 2026-04-28 by Claude (Andre + Opus 4.7).
**Builder agent:** if you're picking this up cold, read this doc top-to-bottom **once** before touching anything. Everything you need is here or linked.

---

## 1. TL;DR

`sales-ops-copilot` is a Python CLI that produces a daily Sales Ops AI brief for Andre Profitt (Global Senior Sales Operations Consultant at SimCorp). It pulls live Salesforce pipeline + Microsoft Fabric workspace metadata + 7 governance/hygiene alerts + owner-concentration rollup + an **empirically-weighted forecast** computed from real OpportunityFieldHistory transitions, sends them to Andre's Azure OpenAI deployment, and writes a markdown report.

- **Repo:** https://github.com/Andre-Profitt/sales-ops-copilot (private)
- **Local:** `~/code/apps/sales-ops-copilot/`
- **Latest commit:** `361a4a7` — canonical `_filters.py` unified across the two sister repos with drift check
- **Status:** Phase 1 + alerts + ack + weighted forecast + LAND-monthly cadence shipped. Two launchd jobs firing daily/monthly.
- **Sister repo:** `~/code/apps/account-drilldown/` provides per-account, per-rep, and forecast-pulse drills; consumes the same `_filters.py`.

## 2. Mission

Build a daily Sales Ops AI workflow that exercises Andre's full SimCorp tenant access (Salesforce + Fabric + Azure OpenAI + Azure subs), produces real Sales Ops insight, and progressively grows toward a deployable agent on Microsoft Agent Framework / AI Foundry.

**Non-goals:**

- Don't replicate `~/crm-analytics/` work (paused as of 2026-04-28; per memory `feedback_no_python_builders.md`, do NOT touch its `build_*.py` files).
- Don't replicate the SalesOps "Health Check" PDF (AI-generated, name was hallucinated; see `feedback_dont_trust_ai_generated_pdfs.md`).
- Don't process client-level data through the LLM (per AI Code of Conduct — aggregate + samples-with-IDs only).

## 3. Current state (what's actually shipped)

```
sales-ops-copilot/
├── README.md, CLAUDE.md, pyproject.toml, requirements.txt, .env.example, .gitignore
├── HANDOFF.md                 ← THIS doc
├── scripts/
│   ├── preflight.py           # 6-check credential + drift check
│   ├── brief.py               # main runner: SF + Fabric + alerts + weighted forecast → LLM → markdown
│   ├── alerts.py              # 7 governance/hygiene alerts + owner-concentration + dedup
│   ├── ack.py                 # acknowledgment store; CLI add/rm/list; soql_exclusion()
│   ├── stage_probs.py         # empirical stage→Won probabilities from OpportunityFieldHistory (30d cache)
│   ├── snapshot_diff.py       # daily Δ persistence (state/snapshots/*.json)
│   ├── forecast_backtest.py   # per-quarter StageName transition rates
│   ├── land_brief.py          # per-director LAND-monthly trends + brief.md
│   ├── excel_companion.py     # 15-sheet companion .xlsx for LAND brief
│   ├── run_land_to_deck.py    # bridge trends.json → brand-deck-agent /api/generate-land-deck
│   ├── _directors.py          # 9 MD-1 director scope map
│   ├── _filters.py            # CANONICAL test-pollution exclusion (mirrored to account-drilldown)
│   ├── check_filters_sync.py  # SHA drift check vs sister repo
│   ├── schema.py              # Pydantic models for LAND data
│   └── run_daily.sh           # launchd entrypoint
├── reports/                   # gitignored daily outputs
└── state/                     # gitignored — snapshots/, stage_probabilities.json, acknowledged.json
```

### Launchd jobs (active)

- `com.simcorp.sales-ops-copilot.daily` — 07:00 daily; runs `snapshot_diff.py` then `brief.py`
- `com.simcorp.sales-ops-copilot.land-monthly` — 06:00 1st-of-month; runs `forecast_backtest` + `land_brief --all-directors`
- Both have explicit `EnvironmentVariables` block (PATH + HOME) per `project_ai_os_daemon_env.md` — without it, claude/codex CLIs fall through to Ollama.

### What's verified end-to-end (as of last brief run)

- New-business open ARR (Land + Expand): **$27.7M** across 336 opps
- New-business **weighted ARR** (empirical close estimate): **$9.2M**
- Renewal open ACV: **$2.4M** across 26 opps; weighted ACV: **$399K**
- Empirical stage probs: 1 → 4.8%, 2 → 11.7%, 3 → 20.3%, 4 → 39.5%, 5 → 66.5%, 6 → 87.2%, 7 → 100%
- 7 active alerts; owner concentration: Adam Hatcliff = ~30% of alert ARR
- `_filters.py` byte-identical with sister repo (drift check passes)

## 4. Stack + verified access

**Identity:** `APRO@simcorp.com` on tenant `aa81b43f-3969-4fd4-80c9-84c411508d82`
**License SKUs:** `SPE_E5` (M365 E5) · `CCIBOTS_PRIVPREV_VIRAL` (Copilot Studio Preview) · `FLOW_FREE`
**Fabric capacities:** Trial `FTL64` (started 2026-02-16) + Premium Per User `PP3` Reserved — both West Europe
**Azure subscriptions:** 42 visible. Default `OperationsAIAgents Sandbox` heavily provisioned with multi-region AI Foundry. `AIHub AISandbox` empty but accessible. `AIHackathon2026 Sandbox` has prior hackathon work.

**Azure OpenAI** at `apro-openai` (Sweden Central):

- Endpoint: `https://apro-openai.openai.azure.com/`
- API version: `2025-04-01-preview`
- Deployments: `gpt53chat` (default), `gpt54mini`, `gpt54nano`, `o4mini`, `gpt51codexmax`
- Auth: AzureCliCredential → `https://cognitiveservices.azure.com/.default`
- **GPT-5.x family rejects non-default `temperature`. Omit it.**

**Salesforce CLI:** authenticated as `apro@simcorp.com` (preprod org `00DD0000000mIhUMAU`, instance `https://simcorp.my.salesforce.com`, API v66.0). Alias `preprod`.

**Power BI / Fabric API:** `az rest --resource 'https://analysis.windows.net/powerbi/api'`. 23 workspaces accessible — 8 wired in `brief.py` `SALES_OPS_WORKSPACES` dict.

### MCP capabilities (NEW — 2026-04-28)

Andre has fresh MCP auth on **Salesforce** and **Azure** as of 2026-04-28. Use these in addition to (not in place of) `sf` CLI / `az rest` when the MCP gives you something the CLI can't:

- `mcp__claude_ai_SalesForce__*` — direct SF object access without shelling to the CLI; use when you need richer typed responses or want to avoid the JSON-decode boilerplate the CLI requires.
- M365 MCP suite (`mcp__claude_ai_Microsoft_365__*`) — already available; use for SharePoint folder search, Outlook email search, Teams chat search, calendar.
- **Still blocked from CLI:** ADO and Workday MCPs (Entra Conditional Access — `VS403463`). Don't try.

If you build a feature using SF MCP, **also** keep the `sf` CLI path working — launchd jobs run unattended where MCP isn't available.

Full verified inventory: `~/.claude/intel/simcorp-andre-actual-access-2026-04-28.md`.

## 5. Verify locally before doing anything

```bash
cd ~/code/apps/sales-ops-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. 6/6 credential + drift check
python3 scripts/preflight.py

# 2. Sanity: empirical stage probabilities computable
python3 scripts/stage_probs.py

# 3. _filters.py drift vs account-drilldown
python3 scripts/check_filters_sync.py

# 4. Data-only brief (no LLM)
python3 scripts/brief.py --no-llm

# 5. Full brief
python3 scripts/brief.py
```

If any of 1-3 fail, fix the failing check before writing code.

## 6. Hard rules — domain context you MUST internalize

### 6.1 SimCorp metric convention — never blend

- **Land + Expand** → **ARR** via `APTS_Opportunity_ARR__c`
- **Renewal** → **ACV** via `APTS_Renewal_ACV__c`
- `Opportunity.Amount` is blended TCV — never sum it for pipeline reporting
- Always label dollars as either ARR (Land/Expand) or ACV (Renewal)

Memory: `~/.claude/projects/-Users-test/memory/feedback_simcorp_arr_acv_separation.md`

### 6.2 SimCorp 8-stage sales process

```
1 Prospecting → 2 Discovery → 3 Engagement → 4 Shortlisted →
5 Preferred → 6 Contracting → 7 Opt-out → 8 Won
```

- Commercial Approval mandatory for **ALL Land deals** (boolean `Stage_20_Approval__c`)
- Expand deals with AER >€500k also require Commercial Approval
- Stage 7 (Opt-out) = won but ARR not yet recognized

Intel: `~/.claude/intel/simcorp-sales-process-2026-04.md`

### 6.3 Test-pollution filter — single source of truth

`scripts/_filters.py` is the canonical SOQL exclusion clause for sales-ops test fixtures (Maria Sabiniewicz / QtC SOL / Test/TEST/ASH Dummy / SBL Opp / Back Office). Same file is mirrored byte-for-byte at `~/code/apps/account-drilldown/scripts/_filters.py`. Drift check enforces this on every preflight.

**If you change `_filters.py` here, update the sister repo in the same commit pair.** Both `check_filters_sync.py` scripts will catch divergence.

### 6.4 Ack store — opps muted from alerts

`scripts/ack.py` manages `state/acknowledged.json`. Active acks are SHA-excluded from BOTH counts AND samples in every alert query via `_ack_exclusion()`. Default TTL 7d, auto-pruned on read.

CLI: `python3 scripts/ack.py {add|rm|list}`. Slash command `/ack` wraps it.

### 6.5 Stage probabilities — cached

`scripts/stage_probs.py` computes empirical p(Won|stage) from the last 4 quarters of `OpportunityFieldHistory`, caches at `state/stage_probabilities.json` for 30 days. Falls back to naive priors if no history.

### 6.6 SimCorp AI Code of Conduct

- **No client-level data** through the LLM; aggregate + samples-with-IDs only.
- **No regulated/compliance work**.
- **Human in the loop** — outputs are advisory, never sole basis for decisions.
- **No people-related decision-making**.

Whitelist: `~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md`

## 7. Boundaries — things NOT to do

| Don't                                          | Why                                                                      |
| ---------------------------------------------- | ------------------------------------------------------------------------ |
| Touch `~/crm-analytics/build_*.py`             | Established CLI-first pipeline. Memory: `feedback_no_python_builders.md` |
| Anchor on `~/crm-analytics/` outputs           | CRMA paused 2026-04-28. Memory: `project_crma_paused_2026-04-28.md`      |
| Trust AI-generated PDFs as authoritative       | Memory: `feedback_dont_trust_ai_generated_pdfs.md`                       |
| Blend ARR + ACV                                | Memory: `feedback_simcorp_arr_acv_separation.md`                         |
| Use `temperature=` on `gpt53chat` / GPT-5.x    | Returns 400                                                              |
| Pass client-level financial detail through LLM | AI Code of Conduct                                                       |
| Try ADO/Workday MCPs from CLI                  | Entra CA. Memory: `feedback_simcorp_entra_ca_blocks_cli.md`              |
| Modify `_filters.py` in only one repo          | Run `check_filters_sync.py` in both before commit                        |
| Push to remote without explicit user OK        | Standard caution                                                         |

## 8. Open backlog — pick a direction

Independent. Pick whichever Andre points at.

### Direction H: Multi-quarter weighted forecast (next obvious step)

Today the brief weights only `THIS_QUARTER`. Add Q+1 and Q+2 weighted views using same empirical probs. Roughly 50 LOC in `brief.py` — reuse `weighted()` helper from `stage_probs.py`. Deliverable: 3-quarter ARR pipe vs. weighted view in the brief.

### Direction I: CSV/Excel export for owner-drill

Currently `/owner-drill` produces a markdown dossier. Add `--export-xlsx <path>` that writes the flagged-book table to xlsx so a director can paste it into a deck or share with a rep without copy-pasting markdown. Use `openpyxl` (already in the deps tree via `excel_companion.py`).

### Direction J: Tighten test-name patterns

`SEB - AM and OM test quote` ($4M, Johanna Bergkvist) is real but has "test" in the name. Today's filter doesn't catch it (correct), but doesn't catch some other pollution either. Audit by pulling the 50 highest-ARR Land opps and eyeballing for noise; tighten patterns in `_filters.py` (then sync to drilldown).

### Direction K: Account-level health view

Pivot opp-level alerts to account-level: surface accounts with multiple stale opps + open KYC + missing renewal. Use `Account` SObject; join via `Opportunity.AccountId`. ~2-3 hours.

### Direction L: Render to HTML/PDF + Teams post

Markdown report → presentable HTML/PDF → post to Teams via M365 MCP. Pandoc or weasyprint. ~1-2 hours.

### Direction M: Microsoft Agent Framework deployment

Lift `brief.py` into a real agent on `apro-foundry-project` (Sweden Central) or new project in `AIHub AISandbox`. Use Microsoft Agent Framework + AG-UI. ~1-2 days; biggest leverage long-term.

### Direction N: Add more alerts

Field discovery cheat sheet (verified):

- `KYC_Approval_Message__c` (boolean) → KYC alert
- `APTS_Forecast_ARR__c` / `APTS_Forecast_Renewal_ACV__c` → forecast vs reality
- `APTS_DH_Profitability_Approver__c` → margin governance
- `Deal_Shaping_Approved__c` → GS Deal Review
- `Submit_for_Stage_20_Review__c` / `Submit_for_Stage_20_Review_Date__c` → approval-pending vs approval-missing

## 9. Where the wider context lives

- **Skills wrap (auto-loaded each session):** `~/.claude/skills/simcorp-org-wrap/`
- **Intel (deeper snapshots):** `~/.claude/intel/simcorp-*.md`
- **Memory (persistent across sessions):** `~/.claude/projects/-Users-test/memory/`
  - Index: `MEMORY.md`
  - Today's most relevant: `project_sales_ops_copilot_2026-04-28.md`, `project_sales_ops_launchd_state_2026-04-28.md`, `feedback_simcorp_arr_acv_separation.md`
- **User profile:** `user_goals_and_style.md`
- **Slash commands (local-only, gitignored):** `~/.claude/commands/{morning-brief,owner-drill,account-drill,triage-alerts,forecast-pulse,ack,simcorp-search,simcorp-who,simcorp-mcp-health}.md`

## 10. How to verify your work before claiming done

1. `python3 scripts/preflight.py` returns all ✓
2. `python3 scripts/check_filters_sync.py` returns 0
3. `python3 scripts/brief.py --no-llm` runs end-to-end without errors
4. `python3 scripts/brief.py` produces a report with Synthesis + weighted forecast section
5. ARR + ACV totals reported separately, never summed
6. Critical alerts appear before Important
7. New alert functions return `{name, severity, rule, count, total_arr, samples}` matching existing shape
8. Commit message includes verified findings (count + dollar amount) so future readers can spot drift
9. If you touched `_filters.py`: ran `check_filters_sync.py` in BOTH repos and both passed

## 11. How to ask for help

Default to action — Andre's working style is "default to action, no menus, no should-I prompts" (`~/.claude/CLAUDE.md`). When stuck, ONE short sentence describing the blocker + what you did anyway. Genuinely ambiguous architectural choices are worth asking; tool/library/style choices are not.

---

_This handoff is the canonical source for picking up work. If you change anything substantial, update this file before commit._
