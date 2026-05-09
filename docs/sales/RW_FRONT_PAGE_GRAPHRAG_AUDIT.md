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

## Consulting Pattern Reset

Desktop proved the sophistication pass still used the wrong pattern: too many
short standalone textboxes. They passed JSON validation but clipped in the
Power BI renderer.

The current front page pattern is stricter:

- 56 total visuals, down from 69.
- 18 standalone textboxes only, all 34px+ high.
- No standalone metric labels inside KPI panels.
- Larger native cards own their value and category label.
- RAG panels use status accent rails, not decorative card walls.
- The bottom portfolio surface is now a real `clusteredBarChart` for
  `Total Open Pipeline Value` by stage.
- The deal table remains the inspection queue.

Live evidence:

- `rw_capture_visual --list --page "VP Ops Scorecard"` shows 21 shapes,
  18 textboxes, 12 object-bearing cards, 3 slicers, 1 chart, and 1 table.
- `rw_validate --live` resolves all references against 100 measures.
- `rw_dashboard_harness audit --source live --label front_page_consulting_v3`
  leaves no front-page findings.

## Exception-Led Pattern Reset

The next pass changed the consulting pattern itself. V3 was cleaner, but it
still gave the eye three equally weighted RAG blocks. V4 starts with the
executive answer and then uses charts to explain where to act.

Additional correction: the ARR exception measures now explicitly filter
Land+Expand for both counts and dollars. This keeps renewal ACV out of ARR
risk-count logic and preserves the SimCorp motion contract.

The current pattern is:

- Left rail: persistent filters plus the ARR/ACV contract.
- Top strip: `Exception ARR` and `Exception Opps Count` first, with at-risk,
  watch, and forward-move support metrics.
- Middle: two chart-led panels: exception ARR by region, open value by stage.
- Bottom: KPI operating pulse plus the deal-inspection queue.

Live evidence:

- 45 total visuals.
- 15 shapes, 14 textboxes, 10 object-bearing cards, 3 slicers, 2 clustered bar
  charts, and 1 table.
- No card is under 76px high; no textbox is under 34px high.
- `rw_validate --live` resolves all references against 102 measures.
- `rw_dashboard_harness audit --source live --label front_page_consulting_v4`
  leaves no front-page findings.
