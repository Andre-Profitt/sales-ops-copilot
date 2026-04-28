# Handoff — sales-ops-copilot

**Last session:** 2026-04-28 by Claude (Andre + Opus 4.7).
**Builder agent:** if you're picking this up cold, read this doc top-to-bottom **once** before touching anything. Everything you need is here or linked.

---

## 1. TL;DR

`sales-ops-copilot` is a Python CLI that produces a daily Sales Ops AI brief for Andre Profitt (Global Senior Sales Operations Consultant at SimCorp). It pulls live Salesforce pipeline + Microsoft Fabric workspace metadata + 7 governance/hygiene alerts, sends them to Andre's Azure OpenAI deployment, and writes a markdown report.

- **Repo:** https://github.com/Andre-Profitt/sales-ops-copilot (private)
- **Local:** `~/code/apps/sales-ops-copilot/`
- **Latest commit:** `dd552ed` — alert detection module shipped end-to-end
- **Status:** Phase 1 + alerts working. End-to-end verified against $27.7M ARR pipeline + $2.4M renewal ACV + 7 active alerts.
- **What it produces:** `reports/YYYY-MM-DD.md` (markdown). Sample numbers below.

## 2. Mission

Build a daily Sales Ops AI workflow that exercises Andre's full SimCorp tenant access (Salesforce + Fabric + Azure OpenAI + Azure subs), produces real Sales Ops insight, and progressively grows toward a deployable agent on Microsoft Agent Framework / AI Foundry.

**Non-goals:**

- Don't replicate `~/crm-analytics/` work (paused as of 2026-04-28; per memory `feedback_no_python_builders.md`, do NOT touch its `build_*.py` files).
- Don't replicate Hooman Hashemi's "Health Check" PDF (that PDF is AI-generated, the name was hallucinated; see `~/.claude/projects/-Users-test/memory/feedback_dont_trust_ai_generated_pdfs.md`).
- Don't process client-level data through the LLM (per AI Code of Conduct — aggregate + samples-with-IDs only).

## 3. Current state

### What's shipped (Phase 1 + Phase 1.5)

```
sales-ops-copilot/
├── README.md, CLAUDE.md, pyproject.toml, requirements.txt, .env.example, .gitignore
├── scripts/
│   ├── preflight.py    # 5/5 credential check
│   ├── brief.py        # main runner: SF snapshot → Fabric → alerts → LLM → markdown
│   └── alerts.py       # 7 governance + hygiene checks
└── reports/            # gitignored daily outputs
```

### What's verified end-to-end

Last `brief.py` run (2026-04-28) returned:

- New-business ARR (Land + Expand): **$27,730,401** across 336 opps (Land 30 / Expand 306)
- Renewal ACV: **$2,407,485** across 26 opps
- 8 Fabric workspaces inspected (datasets + reports listed)
- 3 critical alerts + 4 important alerts surfaced
- gpt-5.3-chat synthesis (~3,800 chars) cited specific deals by name and dollar value

### Top alert hits today (regenerate by running brief.py)

| Severity  | Alert                                                   | Count |    $ARR |
| --------- | ------------------------------------------------------- | ----- | ------: |
| Critical  | Land deals Stage 3+ without Commercial Approval         | 27    |  $37.9M |
| Critical  | Stage 3+ Land/Expand ≥$500k without Commercial Approval | 105   | $142.5M |
| Critical  | Open opps with CloseDate in the past                    | 95    |  $17.5M |
| Important | Stage 3+ Dec 31 placeholder close dates                 | 122   | $107.2M |
| Important | Stage 3+ stale activity (60d+)                          | 117   |  $80.7M |
| Important | Stage 3+ no logged activity ever                        | 464   | $112.6M |
| Important | Open opps owned by inactive SF user                     | 8     |       — |

## 4. Stack + verified access

**Identity:** `APRO@simcorp.com` on tenant `aa81b43f-3969-4fd4-80c9-84c411508d82`

**License SKUs:** `SPE_E5` (M365 E5 incl. Power BI Pro) · `CCIBOTS_PRIVPREV_VIRAL` (Copilot Studio Preview) · `FLOW_FREE`

**Fabric capacities:** Trial `FTL64` (started 2026-02-16) + Premium Per User `PP3` Reserved — both in West Europe

**Azure OpenAI** at `apro-openai` (Sweden Central, sub: `OperationsAIAgents Sandbox`):

- Endpoint: `https://apro-openai.openai.azure.com/`
- API version: `2025-04-01-preview`
- Deployments: `gpt53chat` (default), `gpt54mini`, `gpt54nano`, `o4mini`, `gpt51codexmax`
- Auth: AzureCliCredential → `https://cognitiveservices.azure.com/.default` token (role: `Cognitive Services OpenAI User`)
- **Important:** GPT-5.x family rejects non-default `temperature`. Omit it.

**Salesforce CLI:** authenticated as `apro@simcorp.com` (preprod org `00DD0000000mIhUMAU`, instance `https://simcorp.my.salesforce.com`, API v66.0). Alias `preprod`.

**Power BI / Fabric API:** call via `az rest --resource 'https://analysis.windows.net/powerbi/api'`. 23 workspaces accessible — 8 currently wired in `brief.py` (`SALES_OPS_WORKSPACES` dict). Salesforce Analytics workspace ID is `b66233d5-9d4a-44ba-89a8-b70206d98ae7`.

**Azure subscriptions:** 42 visible. Default `OperationsAIAgents Sandbox` is heavily provisioned with Andre's multi-region AI Foundry resources. `AIHub AISandbox Sandbox` is empty but accessible — possible deployment target. `AIHackathon2026 Sandbox` has prior hackathon work.

**ADO MCP:** OAuth completes but **all API calls blocked by Entra Conditional Access** (`VS403463`). Don't try to use ADO MCPs from this CLI; web app is the workaround.

Full verified inventory: `~/.claude/intel/simcorp-andre-actual-access-2026-04-28.md`.

## 5. Verify locally before doing anything

```bash
cd ~/code/apps/sales-ops-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Confirm all 5 credentials are wired
python3 scripts/preflight.py
# Expect: 5/5 ✓ (az + sf + Fabric API + apro-openai endpoint + deployments)

# 2. Run a data-only brief to validate SF + Fabric pulls
python3 scripts/brief.py --no-llm

# 3. Full end-to-end with LLM synthesis
python3 scripts/brief.py
# Expect: report at reports/YYYY-MM-DD.md
# Stages: Critical=3, Important=4 (current day; varies as deals move)
```

If preflight fails, do not write code. Diagnose and fix the failing credential first.

## 6. Hard rules — domain context you MUST internalize

### 6.1 SimCorp metric convention — never blend (verified by `sf sobject describe`)

- **Land + Expand** deals report **ARR** via `APTS_Opportunity_ARR__c`
- **Renewal** deals report **ACV** via `APTS_Renewal_ACV__c`
- The default `Opportunity.Amount` field is a blended TCV-shape number — **never sum it for pipeline reporting**
- Always label dollar figures as either ARR (Land/Expand) or ACV (Renewal). Two separate motions, different shapes.

Memory: `~/.claude/projects/-Users-test/memory/feedback_simcorp_arr_acv_separation.md`

### 6.2 SimCorp 8-stage sales process (from Commercial Handbook)

```
1 Prospecting → 2 Discovery → 3 Engagement → 4 Shortlisted →
5 Preferred → 6 Contracting → 7 Opt-out → 8 Won
```

- **Commercial Approval is mandatory for ALL Land deals** (boolean field `Stage_20_Approval__c`)
- Expand deals with AER >€500k also require Commercial Approval
- Stage 3 (Engagement) = "due diligence in progress, prospect has invested"
- Stage 5 (Preferred) = "no longer in competition; awaiting full red-lining"
- Stage 7 (Opt-out) = won but ARR not yet recognized

Full intel: `~/.claude/intel/simcorp-sales-process-2026-04.md`
In-wrap reference: `~/.claude/skills/simcorp-org-wrap/sales-process.md`

### 6.3 Type values you'll encounter on Opportunity

`Land`, `Expand`, `Renewal` — these are the canonical ones. The `Type IN ('Land','Expand')` predicate captures new-business; `Type = 'Renewal'` captures renewals.

### 6.4 RecordType values

`Opportunity`, `QtC_Opportunity`, `Quota`, `RCA_Opportunity` — `Quota` records appear in some queries but are not real opportunities; consider filtering them out for forecast-shape work.

### 6.5 SimCorp AI Code of Conduct (Group Compliance — Konrad Torun, Emilie Terney Bech)

The brief uses Andre's whitelisted Claude/Azure-OpenAI access. Constraints:

- **No client-level data** flows through the LLM. Aggregate by Stage / Type only. Top-N samples include deal Name + Owner Name (employees, not clients).
- **No regulated/compliance work** through the brief.
- **Human in the loop** — outputs are _advisory_, never the sole basis for commercial/financial/legal decisions.
- **No people-related decision-making** (CV screening, performance evaluation, etc.).

Full whitelist: `~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md`
Cowork-specific: `~/.claude/intel/simcorp-claude-cowork-policy-2026-04-28.md`

## 7. Boundaries — things NOT to do

| Don't                                                      | Why                                                                                                                       |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Touch `~/crm-analytics/build_*.py`                         | Established CLI-first pipeline; modifications break SD Monthly + retention work. Memory: `feedback_no_python_builders.md` |
| Anchor builds on `~/crm-analytics/` outputs                | CRMA is paused as of 2026-04-28. Memory: `project_crma_paused_2026-04-28.md`                                              |
| Trust AI-generated PDFs as authoritative                   | Memory: `feedback_dont_trust_ai_generated_pdfs.md`                                                                        |
| Blend ARR + ACV                                            | Memory: `feedback_simcorp_arr_acv_separation.md`                                                                          |
| Use `temperature` parameter on `gpt53chat` / other GPT-5.x | Returns 400 error                                                                                                         |
| Pass client-level financial detail through the LLM         | AI Code of Conduct                                                                                                        |
| Try ADO/Workday MCPs from CLI                              | Blocked by Entra CA. Memory: `feedback_simcorp_entra_ca_blocks_cli.md`                                                    |
| Push code to remote without explicit user OK               | Standard caution                                                                                                          |

## 8. Open work — pick a direction

These are **independent**, no dependencies on each other. Pick whichever Andre points at, or propose a different direction with rationale.

### Direction A: Daily snapshot + diff

- Persist today's `sf` snapshot as JSON to `state/YYYY-MM-DD.json`
- On next run, diff against latest stored — show what moved (new entries, stage advances, slips, lost deals, new alerts vs cleared alerts)
- Output a "Δ since yesterday" section at top of report
- ~2-3 hours; mostly state management

### Direction B: Forecast accuracy backtest

- Query `OpportunityFieldHistory` for stage transitions over last 4 quarters
- Compute actual S2→S3, S3→S4, S4→Close conversion rates
- Cohort by quarter, by motion (Land vs Expand), by owner
- Output: an HTML or markdown report; could feed back into the daily brief
- ~3-5 hours; SOQL on history tables

### Direction C: Account-level health view

- Pivot from opp-level to account-level
- Surface accounts with: multiple stale opps + open KYC + missing renewal opp
- Use `Account` SObject; join via `Opportunity.AccountId`
- ~2-3 hours

### Direction D: Render to HTML/PDF

- Convert markdown report to a presentable HTML/PDF artifact
- Could share via Teams or upload to SharePoint via M365 MCP
- ~1-2 hours; Markdown → Pandoc or weasyprint

### Direction E: Schedule daily run

- launchd plist for 7am daily
- Optionally drops result into a Teams channel via M365 MCP
- ~1 hour

### Direction F: Microsoft Agent Framework deployment

- Lift `brief.py` into a real agent on `apro-foundry-project` (Sweden Central) or new project in `AIHub AISandbox`
- Use Microsoft Agent Framework (Maestros team's stack) + AG-UI
- ~1-2 days; biggest lift, biggest leverage long-term

### Direction G: Add more alerts to `alerts.py`

Field discovery cheat sheet (already verified):

- `KYC_Approval_Message__c` (boolean) → KYC alert
- `APTS_Forecast_ARR__c` / `APTS_Forecast_Renewal_ACV__c` → forecast vs reality
- `APTS_DH_Profitability_Approver__c` → margin governance
- `Deal_Shaping_Approved__c` → GS Deal Review
- `Submit_for_Stage_20_Review__c` / `Submit_for_Stage_20_Review_Date__c` → approval-pending vs approval-missing distinction

## 9. Where the wider context lives

If you need broader SimCorp / Andre context beyond this repo:

- **Skills wrap (auto-loaded each session):** `~/.claude/skills/simcorp-org-wrap/`
  - `SKILL.md` (entry), `org-and-people.md`, `governance.md`, `mcp-connectors.md`, `data-sources.md`, `routing-rules.md`, `tools-and-access.md`, `sales-process.md`
- **Intel files (deeper snapshots):** `~/.claude/intel/simcorp-*.md` (~12 files)
- **Memory (persistent across sessions):** `~/.claude/projects/-Users-test/memory/`
  - Index: `MEMORY.md`
  - Key feedback memories: `feedback_simcorp_arr_acv_separation.md`, `feedback_no_python_builders.md`, `feedback_dont_trust_ai_generated_pdfs.md`, `feedback_verify_access_with_az_graph.md`, `project_crma_paused_2026-04-28.md`
- **Andre's user profile:** `~/.claude/projects/-Users-test/memory/user_goals_and_style.md`

## 10. How to verify your work before claiming done

1. `python3 scripts/preflight.py` returns 5/5 ✓
2. `python3 scripts/brief.py --no-llm` runs end-to-end without errors and produces a report
3. `python3 scripts/brief.py` produces a report with Synthesis section
4. The synthesis cites specific deal names and dollar values from the SF data
5. ARR + ACV totals are reported separately, never summed
6. Critical alerts appear before Important
7. If you added new alert categories: each new alert function returns `{name, severity, rule, count, total_arr, samples}` matching existing shape
8. Commit message includes verified findings (count + dollar amount) so future readers can spot drift

## 11. How to ask for help

Default to action — Andre's working style is "default to action, no menus, no should-I prompts" (see `~/.claude/CLAUDE.md`). When stuck, do ONE short sentence describing the blocker + what you did anyway.

Genuinely ambiguous architectural choices are worth asking about; tool/library/style choices are not.

---

_This handoff is the canonical source for picking up work. If you change anything substantial, update this file before commit._
