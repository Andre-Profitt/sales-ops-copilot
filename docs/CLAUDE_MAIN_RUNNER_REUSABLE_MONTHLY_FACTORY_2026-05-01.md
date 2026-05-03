# Claude Main Runner: Reusable Monthly Factory

Date: 2026-05-01
Owner model: Claude Opus 4.7, max effort
Repo: `/Users/test/code/apps/sales-ops-copilot`

## Mission

Claude is the main implementation runner for the reusable monthly Sales
Director deck factory while Codex quota is conserved. Codex will audit later,
so every meaningful action must leave a durable artifact.

The goal is to move the reusable factory from roughly 55-65% complete toward
80% complete without destabilizing the green May 2026 package.

## Read First

Claude must read these files before editing:

```text
docs/HANDOFF_TO_CLAUDE_REUSABLE_MONTHLY_FACTORY_2026-05-01.md
docs/SALES_DIRECTOR_FACTORY_DURABLE_PLAN.md
docs/DIRECTOR_DECK_FACTORY.md
docs/thinkcell-corpus/build-scaffold.md
state/2026-Q2/__regional__/factory_plan/durable_factory_backlog.json
state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json
state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.md
```

## Non-Negotiable Constraints

- Do not push.
- Do not commit.
- Do not rewrite production decks unless a job explicitly requires it.
- Do not delete or reset uncommitted work.
- Do not touch `.env` or secrets.
- Do not run destructive commands.
- Do not blend ARR and ACV.
- ARR = Land + Expand via `APTS_Opportunity_ARR__c`.
- ACV = Renewal via `APTS_Renewal_ACV__c`.
- Type filters are mandatory.
- Weighted and unweighted values must be explicit.
- Test/SimCorp/internal `SC` pollution must remain filtered.
- Unsupported periods fail closed until period-roll certification passes.

## Audit Contract

Claude must write all run artifacts under:

```text
state/2026-Q2/__regional__/claude_main_runner/<run_id>/
```

Required files:

```text
RUN_MANIFEST.json
RUN_LOG.md
CHANGES.md
VERIFICATION.md
NEXT_FOR_CODEX_AUDIT.md
```

`RUN_MANIFEST.json` must include:

- run_id
- started_at_utc
- model
- effort
- planned_jobs
- files_changed
- commands_run
- verification_results
- blocked_items
- residual_risks

`RUN_LOG.md` must append dated sections as work progresses. It should name
every file changed and every verification command run.

`NEXT_FOR_CODEX_AUDIT.md` must be written as if Codex 5.5 will review with no
conversation context. It must include exact commands and expected results.

## Primary Work Queue

Prioritize these jobs:

1. `factory plan --period 2026-Q2` read-only command.
2. Period-roll certification harness:
   - folder name checks
   - snapshot math checks
   - Salesforce Type filter checks
   - director roster checks
   - publish blocked for uncertified periods
3. `QTR12_StalePipeline_BarTable` proof preparation, but do not run risky
   Office/VM mutation unless the preflight is green and the action is clearly
   reversible.
4. Work-queue runner that can mark jobs running/pass/fail/blocked and write
   evidence.
5. MoM contact-sheet design gate design or skeleton.

## Implementation Style

- Prefer narrow patches over broad rewrites.
- Keep existing top-level scripts working.
- Add tests around every new command or schema.
- Use existing artifacts and manifests rather than inventing duplicate state.
- If a task requires live SharePoint, PowerPoint, VM, or Azure mutation, write
  the plan and dry-run gate first.

## Required Verification Before Exit

Run the highest applicable subset:

```bash
.venv/bin/python -m py_compile <changed-python-files>
.venv/bin/python -m pytest tests/test_sd_factory_scaffold.py tests/test_period_context.py tests/test_sales_director_row_filters.py
.venv/bin/python scripts/sd_factory_doctor.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_work_queue.py --period 2026-Q2
```

If a command cannot run, record the blocker and the exact error in
`VERIFICATION.md`.

## Exit Criteria

Claude should stop when one of these is true:

- It completes at least one durable factory job with tests and audit docs.
- It finds a concrete blocker that needs Andre/Codex/operator action.
- It reaches a safe stopping point after roughly 60-90 minutes.

Do not continue indefinitely.
