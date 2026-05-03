# Handoff To Claude: Reusable Monthly Sales Director Factory

Date: 2026-05-01
From: Codex
Repo: `/Users/test/code/apps/sales-ops-copilot`

## Mission

Help turn the current May 2026 Sales Director deck workflow into a durable
monthly factory.

This is not a request to rebuild the May decks. The May package is already
green. The ask is to help harden the reusable monthly production system:
Salesforce -> Excel model/audit workbooks -> think-cell/PowerPoint assets ->
QA gates -> SharePoint publish.

Current estimate:

- May 2026 deck delivery: about 90-95% done.
- Reusable monthly factory: about 55-65% done.
- Native think-cell sophistication: about 40-50% done.

## Hard Rules

- Do not push.
- Do not commit unless Andre explicitly asks.
- Do not rewrite production decks unless explicitly assigned a deck-edit job.
- Do not touch `.env` or secrets.
- Do not run destructive git commands.
- Do not blend ARR and ACV.
- ARR = Land + Expand via `APTS_Opportunity_ARR__c`.
- ACV = Renewal via `APTS_Renewal_ACV__c`.
- Type filters are mandatory:
  - ARR: `Type IN ('Land','Expand')`
  - ACV: `Type = 'Renewal'`
- Label weighted versus unweighted numbers explicitly.
- Keep internal/test account pollution filtered:
  - account names containing test, SimCorp, or standalone/internal `SC`
  - opportunity names containing test
- Unsupported periods must fail closed until certified.

## Current Green State

Primary production command:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --jobs 6 \
  --sharepoint-validate
```

Latest green production manifest:

```text
state/2026-Q2/__regional__/production_runs/20260501-153635/manifest.json
```

Current review package:

```text
/Users/test/Downloads/May 2026 Meeting Spine Candidates
```

SharePoint folder:

```text
General/Book of Business/Sales Director Reporting/Q2 2026/May 2026
```

Live SharePoint validation is green:

- 37/37 expected assets present.
- No stale top-level files.
- No size mismatches.

## Current Durable Factory Artifacts

Read these first:

```text
docs/SALES_DIRECTOR_FACTORY_DURABLE_PLAN.md
docs/DIRECTOR_DECK_FACTORY.md
docs/thinkcell-corpus/build-scaffold.md
state/2026-Q2/__regional__/factory_plan/durable_factory_backlog.json
state/2026-Q2/__regional__/factory_plan/factory_doctor_report.md
state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.md
state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.md
state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json
```

Important new scripts/modules:

```text
scripts/sd_factory_doctor.py
scripts/build_thinkcell_work_queue.py
scripts/sd_factory/context.py
scripts/sd_factory/artifacts.py
scripts/sd_factory/runner.py
```

Targeted verification that currently passes:

```bash
.venv/bin/python -m py_compile \
  scripts/sd_factory_doctor.py \
  scripts/build_thinkcell_work_queue.py \
  scripts/sd_factory/__init__.py \
  scripts/sd_factory/context.py \
  scripts/sd_factory/artifacts.py \
  scripts/sd_factory/runner.py

.venv/bin/python -m pytest \
  tests/test_sd_factory_scaffold.py \
  tests/test_period_context.py \
  tests/test_sales_director_row_filters.py

.venv/bin/python scripts/build_thinkcell_work_queue.py --period 2026-Q2
.venv/bin/python scripts/sd_factory_doctor.py --period 2026-Q2
```

Expected caveat:

- `.venv` doctor may report warning for missing `duckdb`; this affects unrelated
  workforce tests, not the deck factory gates.

## What Was Just Added

Codex created the durable plan and first scaffold:

- Durable plan:
  `docs/SALES_DIRECTOR_FACTORY_DURABLE_PLAN.md`
- Machine-readable backlog:
  `state/2026-Q2/__regional__/factory_plan/durable_factory_backlog.json`
- Preflight doctor:
  `scripts/sd_factory_doctor.py`
- Minimal package skeleton:
  `scripts/sd_factory/`
- think-cell executable work queue:
  `scripts/build_thinkcell_work_queue.py`
  `state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json`
  `state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.md`

The work queue currently has:

- 12 contracts.
- 19 jobs.
- 5 protect lanes.
- 7 L4 seed-authoring jobs.
- 7 L5 binding-proof jobs.

Proven/protect lanes:

- `QTR01_StageMix_Bar`
- `QTR02_ForecastMix_Bar`
- `QTR03_OwnerCoaching_Bar`
- `QTR10_ActionDecisionRegister_TableImage`
- `QTR11_CommercialApprovalGap_TableImage`

Next recommended proof job:

```text
QTR12_StalePipeline_BarTable
```

Reason: it is P0 and exercises the hybrid native-bar plus table-image
named-deal fallback lane.

## What Claude Should Help With

Preferred assignment: architecture/backlog review plus one bounded patch,
not open-ended deck work.

Recommended Claude tasks:

1. Review `docs/SALES_DIRECTOR_FACTORY_DURABLE_PLAN.md` and
   `durable_factory_backlog.json` for missing factory workstreams.
2. Propose a tighter 2-week execution sequence for getting the reusable monthly
   factory from 55-65% to about 80%.
3. Identify which tasks Codex should do mechanically versus which tasks Claude
   should own:
   - Codex: mechanical refactors, runners, tests, validation gates.
   - Claude: architecture review, narrative/plan refinement, risk analysis,
     specialist prompts, cross-contract reasoning.
4. Optionally patch only the plan/backlog docs if gaps are concrete.

Do not start by editing the deck generation scripts unless asked.

## Good Next Engineering Moves

Near-term queue:

1. Add a `factory plan` command that prints planned steps without touching
   decks or SharePoint.
2. Add a `factory doctor --check-azure-token` mode to the regular preflight
   sequence before SharePoint publish.
3. Build a work-queue runner that can mark jobs `running`, `pass`, `fail`, or
   `blocked` without executing arbitrary deck changes.
4. Prove `QTR12_StalePipeline_BarTable` end-to-end:
   - verify seed names
   - bind
   - render
   - assert expected stale-pipeline labels/values
   - preserve table-image named-deal fallback
5. Add period config scaffolding for the next month without allowing publish:
   `--period <next>` should plan, but fail closed for source refresh/publish
   until certified.
6. Start moving lower-risk helpers into `scripts/sd_factory/` while keeping
   top-level wrappers stable.

## Known Risks

- Native think-cell table insertion remains unproven. Current production table
  visuals are linked table images driven by Excel.
- Windows VM/PowerPoint/think-cell COM is still part of full refresh.
- Quarter/month roll is not certified beyond May 2026 / `2026-Q2`.
- The repo has many legacy one-off scripts; avoid large reorganizations without
  wrappers and tests.
- Full `pytest` can be blocked by unrelated workforce `duckdb` dependency.

## Desired Claude Output

Keep the response practical. Provide:

1. Verdict on the durable plan: adequate / missing pieces / risky assumptions.
2. A prioritized next 10-job backlog.
3. Which jobs Claude should own versus Codex.
4. Any suggested patch to docs/backlog, if worth doing.

Stay under 800 words unless editing files.
