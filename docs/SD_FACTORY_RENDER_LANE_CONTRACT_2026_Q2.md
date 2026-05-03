# Sales Director Render-Lane Contract

Date: 2026-05-03

This is the operational companion to
`docs/FACTORY_RENDERING_STRATEGY_2026-05-03.md`.

The contract is machine-readable at:

`config/sd_factory_render_lane_contract.2026-Q2.json`

## What It Locks

- The monthly factory target is 9 Sales Director decks, not the 8-director
  `tc-aicore` subset.
- The factory is compute-and-bind: Salesforce/workbooks compute facts, cached
  AI text supplies narrative inputs, and `.ppttc` / Excel COM perform the
  deterministic rendering.
- GPT-5.5 is the preferred upstream reasoning/writing model when available; it
  sharpens narrative and chart choices from grounded facts, then the cached
  output is bound deterministically.
- `tc.ai` is explicitly out of the monthly production path as a dependency, but
  it may be used as a GPT-5.5-assisted ribbon refinement surface when accepted
  outputs are copied back into the run artifact.
- Every monthly binding slot has exactly one primary lane.
- L5 component proofs are recorded separately from production insertion. A
  component can be proven and still require visual/publish gates before it is
  leadership-ready.

## Current Shape

- 42 monthly `.ppttc` binding names are represented.
- 17 native/table component proofs are represented.
- 9 table-image source-range contracts are represented, validated against the
  connected table-image workbook's defined names, and L5-proven for Jesper APAC.
- 14 monthly slots are currently tied to L5-proven component contracts:
  S04, S05, S06, S09, S13, S15, S16, S17, S18, S19, S21 chart, S22, S25, and
  S26.
- Table-shaped monthly slots default to Excel COM `AddRangeImage`, because
  native editable think-cell tables remain blocked.
- AI text slots are allowed only as cached upstream material; the rendered deck
  must be reproducible from the run artifact.
- GPT-5.5 output must include evidence references for every generated title,
  S02 bullet, risk statement, and chart recommendation before binding.
- Anything accepted from a GPT-5.5-assisted `tc.ai` ribbon pass is treated the
  same way: cached, evidence-referenced, and gate-checked before rendering.

## Gaps To Close

1. AI reproducibility: wire the `tc-aicore` AI enrichment artifact into the
   production all-9 monthly run manifest and publish gate.

Closed on 2026-05-03: `tc-aicore` now mirrors the production 9-director registry,
including Mourad / MEA.

Closed on 2026-05-03: the missing table-image contract layer is defined and
L5-proven for S07, S08, S11, S12, S21, and S24 via
`TABLEIMAGE_MonthlySlots-proof.json`.

Closed on 2026-05-03: native chart proofs are L5-passing for S06, S18, S19,
S21 chart, and S25 via QTR13-QTR17 proof artifacts.

Closed on 2026-05-03: `tc-aicore` now queries `OpportunityFieldHistory`
`CloseDate` changes and S04 computes slipped ARR from in-quarter moves out of
period instead of using a hardcoded zero.

Partially closed on 2026-05-03: `tc-aicore` now writes and validates a cached
AI enrichment artifact before title/S02 splicing. The production line now also
emits a per-director AI deck-builder review workbook that ties the AI slots,
think-cell lanes, deck paths, and publish evidence together. The remaining work
is enforcing accepted GPT-5.5/ribbon text artifacts inside the all-9 publish
gate.

## Verification

Run:

```bash
python3 scripts/validate_render_lane_contract.py \
  --contract config/sd_factory_render_lane_contract.2026-Q2.json
```

Expected result:

```text
render_lane_contract: pass
monthly_slots=42
component_proofs=17
table_image_contracts=9
```

For the S04 slipped-ARR fact gate in `tc-aicore`, run:

```bash
cd ~/code/labs/tc-aicore
python3 scripts/smoke_slipped_arr.py
```

Expected result:

```text
slipped_arr_smoke: pass
```

For the AI reproducibility gate in `tc-aicore`, run:

```bash
cd ~/code/labs/tc-aicore
python3 scripts/smoke_ai_artifact.py
```

Expected result:

```text
ai_artifact_smoke: pass
```
