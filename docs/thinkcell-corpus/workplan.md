# think-cell Workplan

Purpose: make SimCorp excellent at think-cell automation without drifting into
deck rebuilding. This plan is about template knowledge, automation proof,
donor selection, and repeatable future-session retrieval.

## Operating Assumption

think-cell automation is an update pipeline, not a general chart factory.

The supported path is:

1. A PowerPoint template already contains think-cell elements.
2. Those elements have `AddRangeData` or `AddRangeImage` names.
3. JSON `.ppttc`, Excel `UpdateBatch`, or `ppttc.exe` fills those named elements.
4. The generated PowerPoint is validated for actual bound data, not just exit code.

This aligns with the official think-cell manual:

- Advanced report automation requires a PowerPoint template containing the think-cell elements to fill.
- JSON and Excel `UpdateBatch` require named elements.
- Excel `AddRangeData` updates charts, tables, automation text fields, Harvey balls, checkboxes, or images.
- Excel `AddRangeImage` updates images of tables.
- `ppttc.exe` is the Windows command-line JSON automation path.

Official references:

- https://www.think-cell.com/en/resources/manual/introductionautomation
- https://www.think-cell.com/en/resources/manual/exceldataautomation
- https://www.think-cell.com/en/resources/manual/jsondataautomation

## Current State

The corpus now has four layers.

| Layer | Artifact | Purpose |
|---|---|---|
| Raw template inventory | `state/thinkcell_bridge/template_catalog/` | Template-level count and render contact sheet. |
| Slide corpus | `state/thinkcell_bridge/slide_corpus/` | 497 slide records with text, object counts, OLE hints, signals, and donor classes. |
| Programmatic lab | `state/thinkcell_bridge/programmatic_lab/` | VM capability proof, strict `.ppttc` contract proof, and bridge/render smoke. |
| Graph RAG | `state/thinkcell_bridge/knowledge_graph/` | Queryable graph of templates, slides, signals, SimCorp contracts, Salesforce gates, and automation lanes. |
| Build scaffold | `state/thinkcell_bridge/build_scaffold/` | Level-gated build briefs that turn graph findings into seed, binding, and proof work units. |

Current extraction numbers:

- 62 templates.
- 497 slides.
- 278 readable `think-cellXML` OLE parts.
- 139 slides expose readable think-cell internals.
- 51 slides have empty `m_strName` and are nameable donor candidates.
- 37 slides are high-fit native chart donor candidates.
- 11 slides are table reference/donor-probe slides.
- 25 slides are avoid-by-default for SimCorp operating reviews.

Current VM automation proof:

- Windows 11 Parallels VM is reachable.
- PowerPoint and Excel expose `thinkcell.addin`.
- `ppttc.exe` exists and runs.
- PowerPoint addin exposes `PresentationFromTemplateStep3`, `UpdateChartStep3`, and `UpdateBatchStep3`.
- Excel addin exposes `CreateUpdate`, `AddRangeData`, `AddRangeImage`, and `Send`.
- Programmatic create-chart API remains absent.
- `scripts/run_thinkcell_windows_bridge.py` now stages each bridge invocation
  into an isolated Windows run directory. Parallel bridge calls previously
  collided in the shared `C:\tcw\sales-ops-copilot-thinkcell` folder.

## Core Commands

Refresh the slide corpus:

```bash
.venv/bin/python scripts/extract_thinkcell_slide_corpus.py
```

Refresh quarter seed contracts:

```bash
.venv/bin/python scripts/build_thinkcell_quarter_seed_spec.py --period 2026-Q2
```

Run the think-cell automation lab:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --render
```

Run the all-director contract pass without rebinding every deck:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py \
  --period 2026-Q2 \
  --all-directors \
  --skip-bridge
```

Build the knowledge graph:

```bash
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
```

Build level-gated scaffolds from graph findings:

```bash
.venv/bin/python scripts/build_thinkcell_build_scaffold.py --period 2026-Q2
```

Write a contract proof after binding:

```bash
.venv/bin/python scripts/prove_thinkcell_build_scaffold_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR10_ActionDecisionRegister_TableImage \
  --render
.venv/bin/python scripts/prove_thinkcell_native_chart_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR01_StageMix_Bar
.venv/bin/python scripts/prove_thinkcell_native_chart_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR08_PipelineMovement_Waterfall
.venv/bin/python scripts/prove_thinkcell_native_chart_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR09_Geography_RankedBar
.venv/bin/python scripts/prove_thinkcell_hybrid_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR12_StalePipeline_BarTable
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR04_DealRisk_Scatter
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR05_FY26RenewalTimeline_Gantt
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Sarah-Pittroff \
  --contract QTR06_Q2RenewalTimeline_Gantt
```

Query the graph:

```bash
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "scatter fallback Patrick"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "FY26 renewal timeline donor slides"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "Commercial Approval table image contract"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "which slides are native bar column donors"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "forecast mix bar donor" --kind slide
```

## Workstreams

### 1. Corpus Quality

Goal: improve the slide-level knowledge layer until it can drive donor selection.

Tasks:

- Add thumbnail paths to each slide node so graph answers can point to visual evidence.
- Add chart subtype classification from `think-cellXML` classes: bar, stacked bar, 100%, waterfall, scatter, bubble, Gantt, Mekko, pie/doughnut.
- Add data-layout hints where extractable: series orientation, category orientation, totals row, date columns, bubble size column.
- Add a `production_relevance` field: `seed_candidate`, `reference_only`, `avoid`, `blocked_native_table`, `table_image_candidate`.
- Add regression tests that assert known donor slides remain classified correctly.

Success gate:

```bash
.venv/bin/python scripts/extract_thinkcell_slide_corpus.py
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "waterfall donor movement bridge" --limit 5
```

### 2. Automation Proof

Goal: keep a small set of hard automation proofs that run quickly and prevent false confidence.

Tasks:

- Keep the Windows COM capability probe current.
- Add a direct Excel `UpdateBatch` proof using one chart, one automation text field, and one table image in the same target deck.
- Add a direct `ppttc.exe` proof using the quarter seed-bank contract, not only LAND.
- Add a negative control: running against a template with zero named elements must fail the lab, even if `ppttc.exe` exits 0.
- Add a data-bound assertion for each proof: expected text/value appears in output XML.

Success gate:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py --period 2026-Q2 --director-slug Jesper-Tyrer --render
```

### 3. Native Table Resolution

Goal: determine whether native think-cell tables can become a supported lane.

Current verdict: table-image donors are proven; native editable think-cell tables are not production-proven in this repo.

Tasks:

- In the Windows VM, manually create one real think-cell table with an `AddRangeData` name from the mini toolbar.
- Save it as a donor deck.
- Run Excel `UpdateBatch().AddRangeData(...)` against that table.
- Compare its package and `think-cellXML` against stock table slides and our table-image donor.
- If it updates reliably, add it as a separate native-table seed lane.
- If it does not, keep `AddRangeImage` as the production table lane and document the failed proof.

Success gate:

```text
One native table donor updates from Excel data, saves to PPTX, reopens, and contains the expected table text after update.
```

### 4. Quarter Seed Bank

Goal: build a reusable seed-bank contract for quarter decks without rebuilding the current decks.

Current contracts:

- `QTR01_StageMix_Bar`
- `QTR02_ForecastMix_Bar`
- `QTR03_OwnerCoaching_Bar`
- `QTR04_DealRisk_Scatter`
- `QTR05_FY26RenewalTimeline_Gantt`
- `QTR06_Q2RenewalTimeline_Gantt`
- `QTR07_StageIndustry_Mekko`
- `QTR08_PipelineMovement_Waterfall`
- `QTR09_Geography_RankedBar`
- `QTR10_ActionDecisionRegister_TableImage`
- `QTR11_CommercialApprovalGap_TableImage`
- `QTR12_StalePipeline_BarTable`

Tasks:

- For each native chart contract, map one best stock template slide donor.
- Generate a quarter seed PPTX from intact donor slides.
- Patch empty `m_strName` values to quarter contract names.
- Run `.ppttc` binding on one director.
- Render the output and inspect slide images.
- Only after this proof should any production deck integration be considered.

Current L5 proof status:

- `QTR01`, `QTR02`, `QTR03`, `QTR07`, `QTR08`, and `QTR09` are proven native
  chart seed-renaming lanes.
- `QTR04`, `QTR05`, and `QTR06` are proven stock-donor lanes that copy the
  installed `.potx` donor to `.pptx`, patch empty `m_strName` values, bind a
  contract `.ppttc`, assert package terms, and render.
- `QTR10` and `QTR11` are proven table-image lanes.
- `QTR12` is proven as a hybrid native chart plus table-image component lane.
- The 2026-Q2 work queue now has 12 protect-lane QA jobs and no unproven seed
  authoring jobs.

Success gate:

```text
Quarter seed PPTX contains all required names, binds through Windows `ppttc.exe`, and renders nonblank output with expected text/data.
```

### 5. Graph RAG

Goal: make future sessions start from queryable memory instead of redoing discovery.

Tasks:

- Add query aliases for common prompts: `scatter`, `timeline`, `tables`, `native table`, `Commercial Approval`, `Stage 3`, `ARR`, `Renewal ACV`.
- Add graph docs for "why not" answers, especially funnels, action Gantt, native tables, and pies/doughnuts.
- Add a compact session bootstrap prompt that tells future agents which commands to run first.
- Optional: add vector embeddings later; the current BM25-style query is enough for deterministic local use.

Success gate:

```bash
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "native table blocked why"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "best donor for Q2 forecast mix"
```

### 6. Build Scaffold

Goal: convert graph findings into specific build levels so future work does not
jump from retrieval straight to deck edits.

Levels:

- `L0 Runtime Surface`: VM and addin capability proof.
- `L1 Salesforce Fit Gate`: director eligibility and fallback proof.
- `L2 Template Family`: stock family mapping.
- `L3 Slide Donor`: candidate donor/reference slide selection.
- `L4 Named Seed Contract`: real named think-cell seed surface.
- `L5 Binding Proof`: bound output render and package assertion.

Tasks:

- Keep build-level nodes in the knowledge graph.
- Generate per-contract scaffold briefs from the graph and quarter seed spec.
- Use the scaffold briefs as the start point for any seed-authoring or binding test.
- Add proof JSON after L5 runs so the scaffold can distinguish pending from proven.
- Keep QTR10/QTR11 as the reference table-image proof pattern: workbook named
  ranges, linked deck named elements, visible shape geometry, rendered slide
  crop, proof JSON.
- Keep QTR01-QTR03 as the reference native-chart proof pattern: donor chart
  seed, renamed think-cell element, `.ppttc` payload, Windows bridge, package
  term assertions, rendered chart visibility, proof JSON.
- Keep QTR04-QTR06 as the reference stock-donor proof pattern: installed
  `.potx` donor, PPTX content-type conversion, empty-name patch, payload-level
  assertions, bound-package assertions, render visibility, proof JSON.

Success gate:

```bash
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_build_scaffold.py --period 2026-Q2
.venv/bin/python scripts/prove_thinkcell_build_scaffold_contract.py --period 2026-Q2 --director-slug Jesper-Tyrer --contract QTR10_ActionDecisionRegister_TableImage --render
```

## Current Priorities

1. Native table resolution.
2. Production visual-polish QA for the proven lanes before deck insertion.
3. Chart subtype and data-layout extraction.
4. Direct Excel `UpdateBatch` proof.
5. Thumbnail-aware graph answers.
6. Multi-director proof expansion for high-value contracts.

## Non-Goals

- Do not rebuild current Sales Director decks as part of this workstream.
- Do not force think-cell charts where the Salesforce fit gate says fallback.
- Do not use funnels for the SimCorp 8-stage process.
- Do not blend ARR and Renewal ACV.
- Do not treat stock `.potx` templates as direct `.ppttc` templates.
- Do not treat `ppttc.exe` exit code 0 as proof without bound-data assertions.
