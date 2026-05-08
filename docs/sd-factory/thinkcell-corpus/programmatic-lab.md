# Programmatic think-cell Lab

Purpose: make think-cell work a repeatable engineering loop, not a sequence of
one-off PowerPoint experiments.

## Current Proven Lane

Run the lab from the repo root:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --render
```

Latest passing run:

- Report: `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.md`
- JSON: `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json`
- Bound seed deck: `state/thinkcell_bridge/programmatic_lab/20260501-190411/ppttc_bridge/Jesper-Tyrer-seed-bound.pptx`
- Render smoke: 28 PNG slides under `state/thinkcell_bridge/programmatic_lab/20260501-190411/render/`

Latest all-director contract run:

- Report: `state/thinkcell_bridge/programmatic_lab/20260501-154302/thinkcell_programmatic_lab.md`
- JSON: `state/thinkcell_bridge/programmatic_lab/20260501-154302/thinkcell_programmatic_lab.json`
- Scope: all 9 regional directors.
- Result: all regional intelligence specs pass, all `.ppttc` payloads emit 42/42 entries, and VM COM capability probe passes.

Latest quarter seed-bank spec:

- Report: `state/thinkcell_bridge/quarter_seed_bank/2026-Q2/quarter_seed_bank_spec.md`
- JSON: `state/thinkcell_bridge/quarter_seed_bank/2026-Q2/quarter_seed_bank_spec.json`
- Scope: 12 named quarter-deck seed contracts across bar, scatter, timeline/Gantt, Mekko, waterfall, and table-image lanes.

## What Passed

- Parallels Windows 11 VM is running.
- Windows PowerPoint/Excel can load `thinkcell.addin`.
- `ppttc.exe` is installed at `C:\Program Files (x86)\think-cell\ppttc.exe`.
- PowerPoint addin exposes `PresentationFromTemplateStep3`, `UpdateChartStep3`, and `UpdateBatchStep3`.
- Excel addin exposes `CreateUpdate`, `AddRangeData`, `AddRangeImage`, and `Send`.
- LAND seed template has 42/42 named automation elements.
- Table-image donor bank has 19/19 named donors.
- Strict `.ppttc` build for Jesper emits 42/42 entries.
- Windows bridge binds the Jesper seed deck and renders 28 slides.
- Windows bridge staging is isolated per invocation. A parallel QTR08/QTR09
  proof run exposed file cross-talk in the previous shared VM staging folder;
  each wrapper call now creates a unique `run-*` folder under
  `C:\tcw\sales-ops-copilot-thinkcell`.
- Hybrid slide/table-image contracts can require a second Mac finalization
  pass. QTR12 proved the native stale-activity bar immediately, but the
  slide-22 table image stayed at a 0.17-inch placeholder until
  `finalize_thinkcell_table_images_mac.py --slides 22 --close` completed the
  carryover state and applied factory geometry.
- Stock Scatter/Bubble and Timeline/Gantt donors can be promoted into proof
  seeds by copying the installed `.potx` to `.pptx`, converting the template
  content type, patching empty `m_strName` values inside `think-cellXML`, and
  binding a contract `.ppttc`.
- Small stock-donor decks render with unpadded PNG names such as `slide-1.png`;
  proof render checks accept both `slide-01.png` and `slide-1.png`.
- QTR04, QTR05, and QTR06 are now L5-proven through the stock-donor harness.
  QTR06 uses Sarah Pittroff because Q2-only renewal Gantt is eligible for only
  Sarah Pittroff, Dan Peppett, and Christian Ebbesen in the current Salesforce
  fit gates.

## Salesforce Intel Applied

The lab reads the live Q2 Salesforce fit artifact:

`state/2026-Q2/__regional__/thinkcell_sf_fit/thinkcell_quarter_salesforce_fit.json`

Current Q2 data shape:

- 314 publishable Q2 rows after removing 33 internal/test rows.
- Bar/Column eligible for 9/9 directors.
- Scatter/Bubble eligible for 8/9 directors.
- FY26 Renewal Timeline/Gantt eligible for 8/9 directors.
- Q2-only Renewal Timeline/Gantt eligible for 3/9 directors.
- Mekko eligible for 8/9 directors, but should remain rare and proof-driven.
- Action Gantt remains rejected from current Salesforce fields because `NextStep` is text, not a milestone date.

For Jesper/APAC specifically:

- Q2 Land+Expand rows: 26.
- Q2 Renewal rows: 1.
- Scatter: eligible.
- FY26 renewal timeline: eligible.
- Action Gantt: not eligible.
- First two-week action signals are the stale ARR and Stage 3+ Commercial Approval gaps from the regional intelligence spec.

Full regional gates from the all-director lab:

- Patrick Gaughan: scatter false; Mekko false; use table/bar fallback.
- Adam Steinhouse: FY26 renewal timeline false; use renewal watchlist table fallback.
- Sarah Pittroff, Dan Peppett, and Christian Ebbesen: Q2 renewal timeline eligible.
- All directors: action Gantt false from Salesforce fields; keep decisions/actions as registers.

## Operating Rule

The VM is the authoritative think-cell runtime, not a magic chart factory.

Use it for:

- `ppttc.exe` binding into already-named native think-cell charts/text.
- PowerPoint COM inspection and update probes.
- Excel COM `AddRangeImage` refresh of linked table-image donors.

Do not use it for:

- Headless creation of arbitrary new think-cell charts.
- Native think-cell table automation without a real named data-backed table donor.
- Any pipeline that silently treats exit code 0 as success without checking bound text/data in the output deck.

## Next Build Targets

1. Build a quarter-deck seed bank separate from LAND: bar/column, scatter/bubble, FY26 renewal timeline, and movement waterfall.
2. Add per-family Salesforce fit gates to the production deck generator so chart choices are selected by data shape, not taste.
3. Keep table-image donors as the production table lane until a real named native table donor is captured.
4. Promote the lab to a CI-style smoke command for every new seed bank: VM probe, strict `.ppttc`, bridge, and render.
5. Keep stock-donor proof assertions split into payload assertions and
   bound-package assertions. Gantt headers such as `Close Date` and `ACV` are
   valid payload terms but do not necessarily survive into slide XML after
   think-cell renders the chart.
