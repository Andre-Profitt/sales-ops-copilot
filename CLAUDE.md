# sales-ops-copilot

Daily Sales Ops AI brief — pulls Salesforce pipeline + Microsoft Fabric workspace metadata, sends to Azure OpenAI for synthesis, writes a markdown report.

## Stack

- Python 3.13
- `azure-identity` (AzureCliCredential) — auth via `az login`
- `openai` (Azure OpenAI client) — endpoint `https://apro-openai.openai.azure.com/`, deployments `gpt53chat`, `gpt54mini`, `gpt54nano`, `o4mini`, `gpt51codexmax`
- Salesforce CLI (`sf`) — auth'd as `apro@simcorp.com` against preprod org
- Power BI / Fabric REST API — via `az rest --resource 'https://analysis.windows.net/powerbi/api'`

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Verify auth
python3 scripts/preflight.py

# Generate today's brief
python3 scripts/brief.py
```

Output: `reports/YYYY-MM-DD.md`

## Conventions

- `reports/` is gitignored — outputs are local-only
- All auth comes from existing `az` and `sf` sessions; no app-level secrets in `.env`
- GPT-5.x family rejects non-default `temperature` — leave it unset
- Workspaces inspected are hardcoded in `SALES_OPS_WORKSPACES` in `brief.py`; expand by adding `name: workspace_id` pairs verified via `az rest ... /myorg/groups`

## Compliance

Per SimCorp's AI Code of Conduct (`~/.claude/skills/simcorp-org-wrap/governance.md`):

- No client-level data flows through this tool. Salesforce queries are aggregate-only (counts + sums by stage).
- No regulated/compliance work goes through this brief.
- Apro-openai is authorized via `Cognitive Services OpenAI User` role on `apro-openai` in `OperationsAIAgents Sandbox`.

## Roadmap

- **Phase 1 (done)**: single-shot CLI — preflight + brief generator
- **Phase 2**: schedule via launchd or frontier-os daemon for daily runs
- **Phase 3**: lift into Microsoft Agent Framework on AI Foundry (`apro-foundry-project`), deploy as agent in `AIHub AISandbox` subscription
- **Phase 4**: wire as MCP tool back into Claude Code as `/morning-brief`

## Adjacent projects (do not duplicate)

- `~/code/apps/RevOps-Hub/` — Palantir Foundry-based RevOps platform (different layer)
- `~/code/apps/book-of-business/` — CRM Analytics + SF report builder (CLI-first, builders-only); per memory `feedback_no_python_builders.md`, do NOT touch its `build_*.py` files
- `~/crm-analytics/` — Sales Director Monthly deck pipeline (separate workspace)

## Tracks in this repo

This repo hosts multiple parallel tracks. Read `docs/AGENT_COORDINATION.md` before edits. **Filter your context to the relevant track:**

| Track                | Scope                                     | Code                                                         | Docs                                     |
| -------------------- | ----------------------------------------- | ------------------------------------------------------------ | ---------------------------------------- |
| **track:cockpit**    | Daily Sales Ops brief + alerts            | `scripts/brief.py`, `scripts/alerts/`                        | repo root                                |
| **track:rw**         | Richard Wyeth Power BI scorecard (Fabric) | `scripts/sales/rw_*.py`, `scripts/sales/sf_to_fabric_rw*.py` | `docs/sales/`, `docs/superpowers/specs/` |
| **track:workforce**  | Workforce KPI model (Power BI)            | `scripts/workforce/`                                         | `docs/workforce/`                        |
| **track:sf-audit**   | Salesforce metadata + report audits       | `scripts/sf_audit/`                                          | `docs/sf_audit/`                         |
| **track:sd-factory** | SD-Monthly LAND deck factory + ThinkCell  | (separate repos / `~/crm-analytics/`)                        | `docs/sd-factory/`                       |

Cross-cutting docs (relevant to all tracks): `AGENT_COORDINATION.md`, `ARCHITECTURE.md`, `SALES_PROCESS_GRAPH.md`, `FORECAST_ACCURACY_CAVEAT.md`, `REPORTING_SNAPSHOTS.md`.
