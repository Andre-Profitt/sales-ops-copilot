# sales-ops-copilot

Daily Sales Ops AI brief that exercises Andre's full SimCorp stack end-to-end:

- **Salesforce** (sf CLI, auth'd as `apro@simcorp.com` against preprod org)
- **Microsoft Fabric** (az + Power BI REST API — `Salesforce Analytics - Sales Manager` workspace + 22 others)
- **Azure OpenAI** (`apro-openai` in Sweden Central with `gpt-5.3-chat`, `gpt-5.4-mini`, `gpt-5.4-nano`, `o4-mini`, `gpt-5.1-codex-max`)
- **Local Claude Code** orchestration (slash command optional)

## Why this exists

Every credential is already in place. No permission requests needed. The point is to prove the stack works end-to-end, then iterate it into a real Sales Ops AI workflow on Microsoft Agent Framework / AI Foundry.

## Quickstart

```bash
cd ~/code/apps/sales-ops-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Verify auth — requires az login + sf org login already done
python3 scripts/preflight.py

# Run today's brief
python3 scripts/brief.py
```

Output lands in `reports/YYYY-MM-DD.md`.

## Stack

```
┌──────────────────────────┐
│  brief.py (orchestrator) │
└──────┬───────┬───────┬───┘
       │       │       │
   ┌───▼─┐ ┌──▼──┐ ┌──▼──────────┐
   │ sf  │ │ az  │ │ apro-openai │
   │ CLI │ │ REST│ │ gpt-5.3-chat│
   └─────┘ └─────┘ └─────────────┘
       │       │
   ┌───▼─┐ ┌───▼────────────┐
   │ SFDC│ │ Fabric/PBI API │
   │ data│ │ workspaces     │
   └─────┘ └────────────────┘
```

## Roadmap

- **Phase 1 (tonight):** single-shot Python script — preflight + brief generator
- **Phase 2:** schedule via launchd or frontier-os daemon for daily runs
- **Phase 3:** lift into Microsoft Agent Framework on AI Foundry, deploy to AIHub AISandbox subscription
- **Phase 4:** wire as MCP tool back into Claude Code as `/morning-brief`

## Boundaries

- This is NOT a CRM Analytics dashboard builder. CRMA work stays in `~/crm-analytics/`.
- This is NOT a Power BI report builder. PBI workspaces are read-only here.
- This DOES use OpenAI for synthesis. Per SimCorp AI Code of Conduct (`~/.claude/skills/simcorp-org-wrap/governance.md`), no client data flows through it; pipeline metadata only.
