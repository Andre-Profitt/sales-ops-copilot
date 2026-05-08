# Agent Coordination — sales-ops-copilot

Two parallel agent tracks operate in this repo. **Read this file before editing.**

## Track ownership

| Track                 | Owns                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | Don't touch                                                                                                                                                                                                                                            |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **`track:cockpit`**   | `scripts/alerts.py` · `scripts/brief.py` · `scripts/agent.py` · `scripts/cockpit.py` · `scripts/cockpit.tcss` · `scripts/brief_pdf.py` · `scripts/brief_html.py` · `scripts/deck.py` · `scripts/weekly_deck.py` · `scripts/weekly_brief.py` · `scripts/ack.py` · `scripts/stage_probs.py` · `scripts/snapshot_diff.py` · `scripts/run_daily.sh` · `scripts/run_weekly.sh` · `scripts/test_flow.py` · `scripts/preflight.py` · `eval/` · `sf_dashboard/cockpit/` (Dashboard `01ZTb00000FxX2YMAV` only) · `docs/POWER_AUTOMATE_FLOW_RUNBOOK.md` · `docs/AGENT_COORDINATION.md` (this file) | `scripts/sf_audit/` · `docs/sf_audit/` · all role-tailored dashboards                                                                                                                                                                                  |
| **`track:sf-audit`**  | `scripts/sf_audit/` · `docs/sf_audit/` · all role-tailored dashboards (CRO, VP, Sales Director, AE, Deal Desk, Marketing, CSM, Finance, Sales Ops Quarterly) · rebuilds of SD Monthly + Sales Ops Q                                                                                                                                                                                                                                                                                                                                                                                      | `scripts/alerts.py` · `brief.py` · `agent.py` · `cockpit.py` · `eval/` · `sf_dashboard/cockpit/`                                                                                                                                                       |
| **`track:workforce`** | `scripts/workforce/` · `workforce/` (raw + DuckDB store, both gitignored) · `docs/workforce/` · `docs/plans/2026-04-29-ap-rw-phase1-plan.md` · `wf.py` CLI (read-only against static pack in Phase 1) · Fabric lakehouse `lkh_workforce_rw` · semantic model `sm_workforce_rw` · report `rpt_workforce_rw`                                                                                                                                                                                                                                                                               | `scripts/alerts.py` · `brief.py` · `agent.py` · `cockpit.py` · `eval/` · `sf_dashboard/cockpit/` · `scripts/sf_audit/` · `docs/sf_audit/` · `scripts/sales/` · `docs/sales/` · the live SF org PATCH lane (Fabric ETL is read-only against SF)         |
| **`track:rw`**        | `scripts/sales/rw_kpi_graph.py` · `scripts/sales/rw_push_semantic_model.py` · `scripts/sales/rw_push_report.py` · `scripts/sales/rw_add_visual.py` · `scripts/sales/sf_to_fabric_rw.py` · `scripts/sales/sf_to_fabric_rw_phase2.py` · `scripts/sales/sf_to_fabric_rw_phase3.py` · `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` · Fabric workspace `Salesforce Analytics - Sales Manager` semantic model `sm_sales_kpis_rw` · report `rpt_vp_ops_scorecard`                                                                                                                                   | `scripts/alerts.py` · `brief.py` · `agent.py` · `cockpit.py` · `eval/` · `sf_dashboard/cockpit/` · `scripts/sf_audit/` · `docs/sf_audit/` · `scripts/workforce/` · `docs/workforce/` · the live SF org PATCH lane (Fabric ETL is read-only against SF) |

## Design philosophies (intentional contrast)

- **Cockpit track** — ONE focused executive cockpit. Single dashboard `01ZTb00000FxX2YMAV`. Density over breadth. Hooman-PDF-grade visual density is the bar.
- **sf-audit track** — Multiple role-tailored dashboards (~9). Each scoped to one consumer (CRO, VP, AE, etc.). Specialization over generalization.

User running both tracks deliberately to compare which design philosophy delivers better managerial value.

## Shared resources — protocol

- `scripts/_filters.py` — test-pollution exclusion. Both tracks reference. Last writer wins; `check_filters_sync.py` catches drift between this repo and `~/code/apps/account-drilldown/`.
- `scripts/_directors.py` — 9 MD-1 director scope map.
- Live SF org `simcorp.my.salesforce.com` — **never PATCH the same Report ID or Dashboard ID from both tracks simultaneously.** Cockpit owns dashboard `01ZTb00000FxX2YMAV` and its 19 reports in folder `Sales Ops Commercial Health`. Everything else in the org is sf-audit's lane.

## Commit-message convention

Prefix every commit with the track tag:

- `feat(track:cockpit): ...`
- `fix(track:cockpit): ...`
- `feat(track:sf-audit): ...`

Existing pre-tag commits are grandfathered.

## Active claims

When editing a SHARED file, append a 1-line claim here. Remove it when done.

```
(no active claims)
```

## What's deprecated

- `docs/DASHBOARD_REDESIGN_2026-04-28.md` — superseded by `docs/sf_audit/ROLE_BASED_DASHBOARD_DESIGN_2026-04-28.md` which is deeper (9 roles vs 5) and surfaced more SF schema (Einstein IqScore, Risk fields, Pardot). Kept in git history; pointer added at top.

## Findings shared across tracks

The sf-audit track's recon surfaced data-side findings that benefit BOTH tracks (these are SF org observations, not track-specific):

- **Stage 5 (Preferred) is the slip swamp** — open Stage 5 deals sit there avg 177 days; Stage 6 only 67 days. Deals die waiting for redlining to start, not in legal.
- **Activity drought on top deals** — 23 of 25 top-CFQ deals had no activity in 30+ days. Org-wide only 3.6% of open Land+Expand had any task in last 30 days.
- **Win rate inverts with deal size** — <$100K = 41%; $100-500K = 31%; $1M+ = **23%**. Big deals lose more than they win.
- **Regional spread is 21pts** — NA 26.9% / UK&I 25.6% vs Southwestern Europe 47.4% / Central Europe 44.4% win rate.
- **`Approval_Status__c` Field History Tracking is OFF** — 0 OFH entries in 365 days. One-click Setup fix needed to start collecting forward.
- **Lying boolean pattern** — `Opportunity.KYC_Approval_Message__c` and `Stage_20_Approval__c` are not the canonical truth fields. Truth lives in picklists (`Account.KYC_Approval_Status__c`, `Opportunity.Approval_Status__c`). Memory at `~/.claude/projects/-Users-test/memory/feedback_kyc_field_on_account_not_opp.md`.

Both tracks honor these findings.
