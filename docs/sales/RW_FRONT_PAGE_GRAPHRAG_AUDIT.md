# RW front page GraphRAG audit - 2026-05-09

## Problem

The live `VP Ops Scorecard` page was still the original landing page: 26 visuals
on one canvas, mostly standalone KPI cards. The result matched Andre's read:
numbers sprawled across the page with no decision hierarchy.

Live audit evidence before cleanup:

- 26 visuals on `VP Ops Scorecard`
- 23 plain cards with no renderer-authored objects block
- 6 stage-forward cards overflowing the 1280 x 720 canvas
- 3 slicers interrupting the card grid instead of acting as a controlled rail
- no section headers, no risk-first hierarchy, no table/matrix surface

## GraphRAG Read

The canonical graph is `scripts/sales/rw_kpi_graph.py`: 31 target KPIs across
five process areas. The front page should not display all of them. It should
retrieve the high-impact live signals and route RW to job tabs for diagnosis.

Front-page retrieval policy:

- Lead with current operating risk, not historical scorekeeping.
- Keep ARR and ACV lanes separate.
- Use `Total Open Pipeline Value` only where explicitly labeled as the
  cross-motion open-value measure.
- Keep missing/partial KG items off the front page unless they explain a gap.
- Replace card rows with grouped lanes plus real data surfaces.

## Cleanup Plan

The new page is a control room, not a metric dump:

- Left rail: filters plus the GraphRAG routing contract.
- Top band: At Risk / Watch / Healthy operating signals.
- Middle band: three high-impact KPI lanes.
  - Growth ARR: won ARR and win rate.
  - Pipeline discipline: open ARR and stage-forward rate.
  - Renewal ACV: retention and won renewal ACV.
- Bottom band: two data surfaces.
  - Open value by stage and motion.
  - Open deals to inspect by value.

The deeper tabs remain the detail layer: What Changed, Forecast, Stage Hygiene,
Renewals, and Growth Mix.

## Sophistication Pass

The follow-up pass made the front page graph-backed and visually denser without
returning to a card wall:

- front-page lanes now resolve explicit KPI IDs from `scripts/sales/rw_kpi_graph.py`
- each KPI lane carries target context from the graph
- each risk band carries a short operating definition
- bottom matrix/table sit in framed panels with accent rails
- `pivotTable` and `tableEx` now carry conservative formatting object blocks

Live evidence after the pass:

- `VP Ops Scorecard` has 65 visuals
- bottom `pivotTable` and `tableEx` both show `*cf*` in `rw_capture_visual`
- front page no longer appears in the harness audit as plain-card, plain-table,
  or canvas-overflow debt
- live report validates at 96 visualContainers / 100 measures
