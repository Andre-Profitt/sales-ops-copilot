# think-cell Infra Capability Plan

Date: 2026-05-02

Purpose: convert the newly discovered think-cell, Excel, VBA, C#, Python, and
Windows VM surfaces into a governed presentation-build infrastructure. This is
the planning layer to read before patching the regional deck builder.

## Operating Decision

Use think-cell as a controlled update and assembly runtime, not as a
free-form chart factory.

The builder must not draw substitute charts with `python-pptx` when a
think-cell contract exists. It must resolve each requested visual through a
capability registry, a contract proof, a candidate/promotion record, and render
gates. If a lane is not proven, the builder falls back to the existing safe
meeting-spine slide, not to a fake native-looking object.

## Evidence Checked

Primary corpus files:

- `automation-api-surface.md`
- `automation-contract.md`
- `json-data-automation-hub.md`
- `vm-api-probe.md`
- `build-scaffold.md`
- `deck-factory-blueprint.md`
- `deck-factory-visual-plan.md`
- `interactive-ui-path-probe.md`
- `unblock-matrix.md`
- `HANDOFF_SLIDE_BUILD_2026-05-02.md`

Current machine inputs:

- Visual plan:
  `state/2026-Q2/__regional__/thinkcell_visual_plan/thinkcell_visual_contract_plan.json`
- Build scaffold:
  `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- Jesper candidate pilot:
  `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260501-213522Z-claude-writer-pilot/manifest.json`
- Runtime probe:
  `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json`

## Capability Map

| Capability | Status | Production interpretation |
|---|---|---|
| Python orchestration | Production | Owns graph/RAG, visual plan, `.ppttc` writers, Windows bridge calls, deck assembly, and gates. |
| `tcrender.TcRenderClient` | Production | Default Mac-side render client for `.ppttc -> .pptx` through VM `ppttc.exe`. Use this instead of ad hoc bridge calls in new factory code. |
| Windows `ppttc.exe` bridge | Production | Safe wrapper for named native think-cell chart/text updates against donor or seed PPTX files. |
| `tc_com_driver` | Production | Wrapped Office COM dispatch surface for PowerPoint/Excel think-cell add-ins, including `UpdateBatch`. |
| Excel COM `CreateUpdate` / `AddRangeData` / `AddRangeImage` / `Send` | Production | Safe lane for range-backed chart updates and table-image refresh. `AddRangeImage` is the table lane. |
| `tcxml` | Production guardrail | Reads/writes think-cellXML for inspection and round-trip checks. Use for proof and linting before direct authoring. |
| PowerPoint COM add-in object | Observed | Exposes update/style/Mekko/UI methods. Use direct methods only behind a proof lane; prefer `ppttc.exe` for native chart binding today. |
| VBA macro host | Supported host | Valid way to call the same COM add-ins with late-bound `Object`. Useful for manual/debug probes and future operator macros, not a separate production lane by itself. |
| C# / .NET interop host | Supported host | Valid way to call Office type libraries plus late-bound think-cell objects. Candidate for a durable Windows worker, not needed before the Python bridge and CLI lanes are stabilized. |
| `tc_toolkit.aicore` | Optional enrichment | Live-verified AI Core client over Socket.IO/WSS. Use only for optional action-title/research/chart-suggestion enrichment, never as a blocking source for SimCorp financial truth. |
| `.ppttc` JSON automation | Production | Native chart/text binding when the named element already exists in a seed or donor template. It cannot create missing charts. |
| Named donor/seed patching | Production with proof | Stock `.potx` objects become usable only after copy-to-`.pptx`, content-type fix, name patch, `.ppttc` binding, package assertions, and render proof. |
| Table-image donor lane | Production | Dense table-shaped outputs remain Excel COM `AddRangeImage` objects. Treat final object as a linked table image, not native editable think-cell table. |
| Style API | Proof candidate | Runtime-proven on transient decks. Production use requires a SimCorp brand-style decision record before automated adoption. |
| Excel `PresentationFromTemplate` | Proof candidate | Documented and observed. Could matter if the seed becomes Excel-linked end to end; not needed for the current `.ppttc` seed path. |
| `tcserver.exe` HTTP service | Optional proof candidate | Inventory exists. Do not start/register it from unattended automation. Promote only after a server-mode architecture decision. |
| Interactive `StartTableInsertion` | Research only | Can create an unnamed `CSmartGrid` table from the logged-in VM console. Not bindable or production-safe yet. |
| Native editable think-cell tables | Blocked | No stable named/bindable table donor has passed without repair prompts. Use table-image lane. |
| Direct arbitrary chart creation | Not found | No public `Create*Chart` or `Insert*Chart` COM method was found. Donor/seed plus data update is the factory. |
| Deep RE / Ghidra / Frida / typeinfo probes | Research only | Useful for discovery and confidence. Do not build monthly production on hidden/private surfaces without a clean public/proven proof lane. |

## Production Lanes

### Lane A: Native think-cell chart or text

Use when the contract visual is a chart or automation text field and a named
seed/donor object already exists.

Flow:

1. Load visual decision from `thinkcell_visual_contract_plan.json`.
2. Confirm contract readiness is `l5_proven` and `proof_status=pass`.
3. Resolve `seed_pptx`, `.ppttc`, `bound_deck`, and render proof from the
   scaffold/proof JSON.
4. Rebuild or reuse the bound deck through `tcrender.TcRenderClient.render()`;
   fall back to `scripts/run_thinkcell_windows_bridge.py` only for legacy
   compatibility or diagnostics.
5. Assert required text/data terms and render visibility.
6. Promote to the meeting spine only through a candidate decision record.

Hard stops:

- missing named element
- `.ppttc` strict validation fails
- no L5 proof
- render is blank, overlapped, repaired, or missing required terms
- ARR/ACV basis is unclear

### Lane B: Table-image output

Use when the slide is a dense table, action register, approval gap list,
renewal watchlist, or triage table.

Flow:

1. Build named Excel ranges from the connected factory workbook.
2. Use Excel COM `CreateUpdate().AddRangeImage(...).Send()` through the proven
   table-image donor path.
3. Run the table-image aspect finalizer and render gate.
4. Keep source rows auditable in Excel.

Hard stops:

- native editable think-cell table required
- range is unnamed or cannot be traced to workbook/source rows
- table rows include test/internal data, placeholder text, or ARR/ACV blends

### Lane C: Candidate and research surfaces

Use only for bounded experiments:

- Style API
- `PresentationFromTemplate`
- `tcserver.exe`
- interactive table insertion
- hidden surface / binary probes

Promotion rule: a candidate surface becomes production only after it has a
named donor/template, bound output, package assertions, rendered evidence, and
a corpus update that changes its status.

## Builder Architecture

The next builder change should add an infra resolver and initial-generation
harness, not hard-coded chart drawing.

### 1. Capability registry

Source: `thinkcell_infra_capability_map.json`.

Responsibilities:

- classify lanes as `production`, `proof_candidate`, `research_only`,
  `blocked`, or `not_found`
- map each visual contract to an allowed lane family
- identify stop rules before Office or deck assembly runs

### 2. Visual contract resolver

Source: `thinkcell_visual_contract_plan.json`.

Responsibilities:

- read director decisions: `include`, `candidate`, `fallback`, `suppress`
- pass only `include` visuals to production assembly by default
- pass `candidate` visuals only when a decision record explicitly promotes them
- attach the exact ARR/ACV guardrail from the decision record

### 3. Artifact resolver

Sources:

- `thinkcell_build_scaffold.json`
- per-contract proof JSON under
  `state/thinkcell_bridge/build_scaffold/2026-Q2/work/<contract>/`
- insertion-pilot manifests under
  `state/2026-Q2/__regional__/thinkcell_insertion_pilot/`

Responsibilities:

- resolve source seed, `.ppttc`, bound proof deck, candidate deck, render dir,
  and validation status
- reject artifacts that are plan-only, corrupt, or lack a successful render
- keep `publishable=false` candidates out of batch production unless a
  promotion manifest says otherwise

### 4. Promotion decision record

New required artifact before insertion into the production spine:

```text
state/<period>/<director_slug>/factory/meeting-spine/thinkcell_promotion_decisions.json
```

Minimum fields:

- `contract_id`
- `decision`: `promote`, `hold`, or `fallback`
- `source_candidate_pptx`
- `current_spine_slide`
- `target_position`
- `render_evidence`
- `business_guardrail`
- `approved_by_agent`
- `created_at_utc`

This is the missing layer between L5 proof and production deck assembly.

### 5. Deck assembler

Current `build_regional_meeting_spine_decks.py` trims the linked deck to a
fixed 16-slide spine and calls `meeting_spine_action_layer.py`. The infra patch
should add a separate promotion step after trimming and before final aspect
fixes:

```text
source table-image-linked deck
  -> trim to meeting spine
  -> apply existing action layer
  -> resolve promoted think-cell candidates
  -> insert/replace approved candidate slides
  -> run table-image aspect fixes
  -> render/publish gates
```

The assembler should not synthesize chart geometry. It should copy or graft
already-bound candidate slides/objects that passed the capability gates.

### 6. Initial deck-generation harness

New entrypoint:

```bash
python3 scripts/run_initial_deck_generation.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --profile apac \
  --use-thinkcell-render \
  --no-publish
```

Responsibilities:

- verify `tcrender`, `tc_com_driver`, and `tcxml` are importable from the
  project venv
- resolve the visual plan through the capability registry
- refresh or reuse source/connected-factory artifacts
- render the native seed-bound deck through `tcrender`
- run the current regional production line for the director
- keep APAC strict coverage gates in the flow
- write a manifest that records which think-cell lanes were used

## Jesper Pilot Scope

Use Jesper Tyrer only for the first infra pass.

Visual plan says:

- Include: `QTR04_DealRisk_Scatter`
- Include: `QTR05_FY26RenewalTimeline_Gantt`
- Candidate: `QTR08_PipelineMovement_Waterfall`
- Candidate: `QTR09_Geography_RankedBar`
- Suppress: `QTR06_Q2RenewalTimeline_Gantt`
- Suppress: `QTR07_StageIndustry_Mekko`

Pilot sequence:

1. Render current Jesper meeting spine.
2. Render QTR04 and QTR05 candidate decks.
3. Create side-by-side evidence against the current spine slides they would
   replace or follow.
4. Write `thinkcell_promotion_decisions.json` with `promote` or `hold`.
5. Patch the builder to consume the decision record.
6. Build Jesper only.
7. Run publish, visual, and business gates.
8. Batch only after Jesper passes.

QTR08 and QTR09 stay as `candidate` until a management-question decision record
promotes them.

## Implementation Order

1. Add the capability registry and this plan to the corpus.
2. Add a small resolver module that loads the visual plan, scaffold, and
   capability map without touching Office.
3. Add `run_initial_deck_generation.py` as the intentional entrypoint for
   initial director deck generation.
4. Add a promotion decision writer/checker for the Jesper pilot.
5. Add builder integration behind an explicit promotion gate.
6. Render and validate Jesper.
7. Generalize to the nine-director package.

## Success Gates

Planning artifact gates:

```bash
python3 -m json.tool docs/thinkcell-corpus/thinkcell_infra_capability_map.json >/dev/null
python3 -m json.tool docs/thinkcell-corpus/manifest.json >/dev/null
python3 - <<'PY'
from pathlib import Path
for path in [
    Path("docs/thinkcell-corpus/INFRA_CAPABILITY_PLAN_2026-05-02.md"),
    Path("docs/thinkcell-corpus/thinkcell_infra_capability_map.json"),
    Path("docs/thinkcell-corpus/README.md"),
    Path("docs/thinkcell-corpus/manifest.json"),
]:
    path.read_text(encoding="ascii")
print("ascii ok")
PY
```

First code-pass gates:

```bash
python3 -m py_compile scripts/run_initial_deck_generation.py scripts/resolve_thinkcell_infra_plan.py
python3 -m pytest tests/test_thinkcell_infra_resolver.py tests/test_initial_deck_generation.py -q
python3 scripts/run_initial_deck_generation.py --period 2026-Q2 --director-slug Jesper-Tyrer --profile apac --plan-only
python3 -m py_compile scripts/build_regional_meeting_spine_decks.py
python3 -m py_compile scripts/meeting_spine_action_layer.py
python3 scripts/build_regional_meeting_spine_decks.py --period 2026-Q2 --director-slug Jesper-Tyrer
python3 scripts/run_regional_deck_publish_gate.py --period 2026-Q2 --director-slug Jesper-Tyrer
python3 scripts/audit_regional_decks_against_goals.py --period 2026-Q2 --director-slug Jesper-Tyrer
```

No batch run until the Jesper render evidence and promotion decision record
exist.

## Hard Business Rules

- ARR is Land + Expand only via `APTS_Opportunity_ARR__c`.
- ARR visuals require `Type IN ('Land','Expand')`.
- Renewal ACV is Renewal only via `APTS_Renewal_ACV__c`.
- Renewal visuals require `Type = 'Renewal'`.
- Never blend ARR and Renewal ACV in charts, tables, KPI strips, bridges, or
  captions.
- Headline currency is converted EUR from Salesforce report aggregates, not
  raw multi-currency SOQL sums.
- Stage 3 Commercial Approval uses `Stage_20_Approval__c`.
- Native editable think-cell tables remain blocked until a named/bindable table
  donor passes without repair prompts.
