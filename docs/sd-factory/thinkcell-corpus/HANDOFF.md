# think-cell Corpus Handoff

Date: 2026-05-01

This is the orientation note for continuing the SimCorp think-cell work. The
goal is not to rebuild decks. The goal is to use the installed think-cell
template corpus, the Windows VM, and Salesforce-backed quarter data to create
repeatable, validated PowerPoint automation lanes.

## Bottom Line

The 2026-Q2 think-cell scaffold is usable.

Usable means:

- The automation surface exists in the Windows/PowerPoint/think-cell VM.
- A named think-cell or table-image surface exists or can be created from a
  proven donor.
- Salesforce-derived data binds into the surface.
- The generated PPTX renders nonblank.
- Proof artifacts assert expected bound text/data, not just `ppttc.exe` exit
  code 0.

Usable does not mean:

- The slides are automatically production-polished.
- Stock `.potx` templates can be dropped directly into `.ppttc` automation.
- Native editable think-cell tables are production-proven. They remain blocked
  until a clean named table donor binds without repair prompts.
- Every director should get every visual.

## Current State

- Quarter contracts: 12
- L5-proven contracts: 12
- Work queue: 12 protect-lane QA jobs
- Knowledge graph: 752 nodes, 4,089 edges, 589 RAG documents
- Indexed stock templates: 62 `.potx` files, 497 slides
- Nameable stock donor candidates: 51 slides with empty `m_strName`

Main artifacts:

- Scaffold: `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- Work queue: `state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json`
- Graph manifest: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json`
- Graph RAG index: `state/thinkcell_bridge/knowledge_graph/thinkcell_graph_rag_index.json`
- Manifest: `docs/thinkcell-corpus/manifest.json`

## Proven Contracts

| Contract | Lane | Proven director | Use |
|---|---|---|---|
| `QTR01_StageMix_Bar` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Stage mix |
| `QTR02_ForecastMix_Bar` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Forecast category mix |
| `QTR03_OwnerCoaching_Bar` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Owner coaching |
| `QTR04_DealRisk_Scatter` | Stock Scatter donor + patched name + `.ppttc` | Jesper Tyrer | Named deal risk |
| `QTR05_FY26RenewalTimeline_Gantt` | Stock Gantt donor + patched name + `.ppttc` | Jesper Tyrer | FY26 Renewal ACV timeline |
| `QTR06_Q2RenewalTimeline_Gantt` | Stock Gantt donor + patched name + `.ppttc` | Sarah Pittroff | Q2 Renewal ACV timeline |
| `QTR07_StageIndustry_Mekko` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Stage by industry mix |
| `QTR08_PipelineMovement_Waterfall` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Pipeline movement bridge |
| `QTR09_Geography_RankedBar` | Native chart seed rename + `.ppttc` | Jesper Tyrer | Ranked geography |
| `QTR10_ActionDecisionRegister_TableImage` | Excel COM `AddRangeImage` | Jesper Tyrer | Action/decision register |
| `QTR11_CommercialApprovalGap_TableImage` | Excel COM `AddRangeImage` | Jesper Tyrer | Commercial Approval gaps |
| `QTR12_StalePipeline_BarTable` | Hybrid native chart + table-image | Jesper Tyrer | Stale pipeline and named triage |

## Start Here Next Session

Run these from `/Users/test/code/apps/sales-ops-copilot`:

```bash
jq '{contract_count: (.contracts|length), l5_proven: ([.contracts[] | select(.readiness=="l5_proven" and .proof_status=="pass")] | length)}' \
  state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json

jq '{contract_count, job_count, protect_jobs: ([.jobs[] | select(.lane=="protect_proven_lane")] | length)}' \
  state/thinkcell_bridge/build_scaffold/2026-Q2/work_queue.json

.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR04 scatter L5 proof" --kind build_proof --limit 3
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "FY26 renewal timeline donor slides" --limit 5
```

Expected result:

- Scaffold says 12 contracts, 12 L5 proven.
- Queue says 12 contracts, 12 jobs, 12 protect jobs.
- Graph query returns the relevant proof or donor records.

## How To Use The Proofs

Use the proofs as a gate before deck insertion:

1. Pick the business question.
2. Query the graph for the matching contract and donor evidence.
3. Check the Salesforce fit gate for the director.
4. Use the existing proof harness for that lane.
5. Render the output and inspect the slide.
6. Only then consider production deck insertion or visual polish.

Do not skip step 3. Some contracts are proven but not universal:

- `QTR04` Scatter is not for Patrick Gaughan unless the axis data improves.
- `QTR05` FY26 Renewal Gantt is not for Adam Steinhouse because dates collapse.
- `QTR06` Q2 Renewal Gantt is only for Sarah Pittroff, Dan Peppett, and
  Christian Ebbesen in the current data.
- `QTR07` Mekko should stay rare and claim-driven.

## Main Commands

Native chart proof:

```bash
.venv/bin/python scripts/prove_thinkcell_native_chart_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR07_StageIndustry_Mekko
```

Stock donor proof:

```bash
.venv/bin/python scripts/prove_thinkcell_stock_donor_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR04_DealRisk_Scatter
```

Table-image proof:

```bash
.venv/bin/python scripts/prove_thinkcell_build_scaffold_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR10_ActionDecisionRegister_TableImage \
  --render
```

Hybrid proof:

```bash
.venv/bin/python scripts/prove_thinkcell_hybrid_contract.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --contract QTR12_StalePipeline_BarTable
```

Regenerate graph/scaffold/queue:

```bash
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_build_scaffold.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_work_queue.py --period 2026-Q2
```

## Implementation Notes

Stock `.potx` files are donor material. The stock-donor proof harness:

- Copies the installed `.potx` donor to `.pptx`.
- Converts the PowerPoint content type from template to presentation.
- Patches empty `m_strName` values inside embedded `think-cellXML`.
- Writes a contract `.ppttc` payload from connected factory workbook rows.
- Runs the Windows `ppttc.exe` bridge.
- Checks bound package terms and render visibility.

For Gantt, payload assertions and bound-package assertions are intentionally
separate. Headers such as `Close Date` and `ACV` are valid in the `.ppttc`
payload but may not survive into slide XML after think-cell renders the Gantt.
The bound package is checked against surviving terms such as `Renewal` and
account names.

Small donor decks may render as `slide-1.png` instead of `slide-01.png`; the
proof harness accepts both.

## Hard Business Rules

- ARR is Land + Expand only and uses `APTS_Opportunity_ARR__c`.
- Renewal ACV is Renewal only and uses `APTS_Renewal_ACV__c`.
- Never blend ARR and ACV.
- Type-bearing ARR visuals require `Type IN ('Land','Expand')`.
- Type-bearing ACV visuals require `Type = 'Renewal'`.
- Use converted EUR for leadership headline figures.
- Do not use funnels for the SimCorp 8-stage process.
- Do not use action Gantt from current Salesforce `NextStep` text.

## Read Next

- `docs/thinkcell-corpus/build-scaffold.md`: L0-L5 build levels and proof state.
- `docs/thinkcell-corpus/graph-rag.md`: graph query commands and node model.
- `docs/thinkcell-corpus/vm-api-probe.md`: current Parallels Windows VM API
  surface and best-use model.
- `docs/thinkcell-corpus/workplan.md`: current priorities and non-goals.
- `docs/thinkcell-corpus/automation-contract.md`: what is automatable versus blocked.
- `docs/thinkcell-corpus/quarter-deck-salesforce-test-2026-q2.md`: director eligibility.

## Next Best Work

The next useful work is production polish, not more proof chasing:

1. Pick one or two insertion candidates, likely QTR04 and QTR05.
2. Render proof decks side by side with the current quarter deck pages.
3. Decide whether each chart improves leadership decision quality.
4. If yes, insert behind the existing factory/publish gates.
5. If no, keep the proof as corpus knowledge and use the table/bar fallback.
