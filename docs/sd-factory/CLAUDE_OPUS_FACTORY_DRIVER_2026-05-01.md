# Claude Opus Factory Driver Prompt

Date: 2026-05-01

You are Claude Opus running as the main execution agent for Andre's SimCorp
Sales Director deck factory. Codex quota is low; Codex will only orchestrate,
validate, and summarize. You own this work tranche.

Repository:

`/Users/test/code/apps/sales-ops-copilot`

## Operating Rules

- Do not commit or push.
- Do not delete unrelated work.
- Keep edits minimal and directly tied to the task.
- This is not the paused `~/crm-analytics` dashboard project. Do not touch
  `~/crm-analytics`; work only in this repo.
- Preserve SimCorp metric rules:
  - ARR = Land + Expand only via `APTS_Opportunity_ARR__c`.
  - ACV = Renewal only via `APTS_Renewal_ACV__c`.
  - Never blend ARR and ACV.
  - Type filters must be explicit where Type-bearing data is used.
  - Exclude internal/test rows where director outputs are built: account names
    containing `test`, `Simcorp`, `SC`, or internal-style records, and
    opportunities containing `test`.
- Use maximum effort/deep work. Prefer implementation plus verification over
  planning prose.

## Current think-cell Findings

- Windows VM runtime works:
  - `ppttc.exe`
  - PowerPoint COM: `PresentationFromTemplateStep3`, `UpdateBatchStep3`
  - Excel COM: `CreateUpdate`, `AddRangeData`, `AddRangeImage`, `Send`
- No reliable headless programmatic chart creation API has been found.
- Supported factory lane is named donor template + `.ppttc` JSON + VM runtime.
- `StartTableInsertion()` plus a desktop click can create native `CSmartGrid`,
  but it is unnamed and not production-ready.
- Official think-cell GitHub does not expose an Office automation SDK. Public
  repos are `.ppttc` writer references only.

Important docs:

- `docs/thinkcell-corpus/HANDOFF.md`
- `docs/thinkcell-corpus/json-data-automation-hub.md`
- `docs/thinkcell-corpus/automation-api-surface.md`
- `docs/thinkcell-corpus/github-surface-scan.md`
- `docs/thinkcell-corpus/build-scaffold.md`
- `docs/thinkcell-corpus/manifest.json`

Useful commands:

```bash
python3 scripts/build_thinkcell_knowledge_graph.py
python3 scripts/query_thinkcell_knowledge_graph.py "GitHub ppttc writer named template"
```

## Goal For This Run

Move the reusable monthly deck factory closer to production by implementing the
next hardening tranche. Do not manually rebuild decks unless necessary for a
small smoke test.

## Concrete Work Package

1. Inspect existing `.ppttc`/think-cell paths:
   - `scripts/build_ppttc.py`
   - `scripts/ppttc_template.py`
   - `scripts/run_thinkcell_windows_bridge.py`
   - `scripts/validate_chart_injection_contract.py`
   - existing tests around think-cell/factory.
2. Implement a small internal `.ppttc` validation/lint layer using existing repo
   style. Prefer a new module/script if integration into older build scripts is
   risky.
3. The validator must be able to:
   - parse emitted `.ppttc` JSON,
   - verify top-level array/template/data/name/table structure,
   - detect duplicate data names within a template,
   - compare emitted names to a supplied expected-name manifest/list when
     available,
   - fail on missing expected names and unknown emitted names in strict mode,
   - provide CLI output usable by a factory runner.
4. Wire validation into the safest existing factory path only if straightforward.
   Otherwise leave it as a standalone reusable gate and document how to call it.
5. Add focused unit tests. Tests must not require Windows, PowerPoint, Excel, or
   think-cell.
6. Update the relevant think-cell corpus/factory docs. If adding a new corpus
   doc, update `docs/thinkcell-corpus/manifest.json` and
   `scripts/build_thinkcell_knowledge_graph.py`.
7. Run local verification:
   - `python3 -m py_compile` on touched scripts,
   - targeted `pytest`,
   - `python3 -m json.tool docs/thinkcell-corpus/manifest.json` if touched,
   - KG rebuild if corpus/KG docs changed.
8. Write an audit note:
   - `docs/CLAUDE_OPUS_FACTORY_RUN_2026-05-01.md`
   - include files changed, tests run, blockers, and next best work.

## Success Gate

The repo has a reusable `.ppttc` validation/lint artifact with passing local
tests, plus an audit note Codex can show Andre. If blocked, ship the smallest
useful subset and document exact evidence.

Final report should be under 250 words and list changed files.
