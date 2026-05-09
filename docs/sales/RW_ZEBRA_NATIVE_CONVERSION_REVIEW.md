# RW Zebra BI to Power BI Conversion Review

Date: 2026-05-09

## Executive Read

The current bulk publisher is useful as plumbing, not as a polished conversion
system. It proves that Codex can create Fabric SemanticModels and Reports for
the 20 Zebra templates, but the rendered dashboards are not consultant-grade
because the converter is flattening and approximating Zebra semantics too
aggressively.

The right conclusion is not "native conversion failed." The right conclusion is:
we need a two-lane bridge.

1. **Fidelity lane:** preserve Zebra BI custom visuals, their object settings,
   page structure, and visual packages where the goal is to evaluate Zebra
   templates as Zebra templates.
2. **Native lane:** translate only selected Zebra patterns into native Power BI
   for RW production, with hand-authored IBCS equivalents and QA gates. This is
   a redesign/transformation, not a one-to-one converter.

## Conversion Audit Gate

Generated audit:
`docs/sales/RW_ZEBRA_NATIVE_CONVERSION_AUDIT.md`.

The bridge audit is decisive:

- Source corpus: 195 PBIX pages, 1,729 visualContainers.
- Current native translator input: 360 mined Zebra visualContainers.
- Dropped page context: 1,369 non-Zebra visualContainers.
- Native output after the page-preserving patch: 180 pages, 360 visuals.
- Structural translator failures: 0 unresolved measure refs, 0 off-canvas
  visuals, 1 native fallback textbox.

So the current bridge is mechanically useful, but it covers only 20.8% of the
source visualContainers. It cannot be judged as a polished Zebra template
conversion because it intentionally excludes most page furniture: text, shapes,
navigation, slicers, backgrounds, annotations, and non-Zebra supporting visuals.

## What The Current Publisher Proves

- Fabric auth and item creation work via `AzureCliCredential`.
- TMDL SemanticModel creation works for all 20 templates.
- Report binding works: each `zbr_<slug>` report points at its own
  `sm_zbr_<slug>` semantic model.
- A blank structural data model can remove most "field not found" failures.
- The local publisher can detect missing report refs and synthesize placeholder
  category columns.

## Why The Dashboards Look Bad

### 1. Page structure was initially collapsed

The first publisher put every Zebra visual for a template onto one report page.
That was wrong. Many templates are multi-page:

- Cost Management: 16 source pages
- Dynamic Comments: 14 source pages
- Sales Dashboard: 12 source pages
- Consolidated Financials: 11 source pages
- SaaS Sales: 10 source pages

This caused overlaps, off-canvas objects, and nonsensical page composition. A
local patch now preserves source pages and clamps visuals to the 1280x720 canvas,
but it has not been republished after review paused the run.

### 2. We mined only Zebra custom visuals, not full report pages

`data/zebra_kg/infrastructure/raw_configs.jsonl` contains one row per Zebra
custom visual. It does not preserve the full PBIX page:

- native textboxes
- shapes/backgrounds
- navigational buttons
- slicers
- page-level filters
- tooltip page wiring
- explanatory annotations outside the custom visual

Zebra templates rely on those elements for the polished dashboard frame. Dropping
them makes the output look like visual fragments.

### 3. Zebra semantics are not native visual semantics

Zebra BI Tables, Charts, and Cards encode behavior that native visuals do not
replicate automatically:

- automatic absolute and relative variances
- Top N + Others behavior
- responsive density / layout switching
- small multiples
- integrated comments and comment markers
- formula-editor calculated rows/columns
- per-column chart type settings inside tables
- waterfall subtotals and IBCS result/invert/skip behavior
- group/scenario semantics such as AC/PY/PL/FC

The current translator maps families very broadly:

- Zebra Tables -> native `tableEx`
- Zebra Cards -> `card`, `multiRowCard`, or table fallback
- Zebra Charts -> `clusteredBarChart`
- Zebra Waterfall -> `waterfallChart`

That is too lossy for polished dashboards.

### 4. Blank semantic models make the pages feel broken

The emitted TMDL models contain zero-row M `#table` partitions. That is acceptable
for a structural smoke test, but visually it means most measures render blank.
Blank visuals plus stripped context reads as broken, even when the refs resolve.

### 5. Native Power BI is not a pixel-equivalent target

Native visuals do not have a one-to-one setting for many Zebra BI visual
properties. A polished native version requires deliberate Power BI design:
matrix/table formatting, variance columns, conditional formatting, data bars,
small multiples alternatives, themes, page composition, and measured information
density.

## External Product Reality

Zebra BI is not just a skin on top of native Power BI. Zebra positions its Power
BI visuals as a certified custom-visual suite for advanced reporting. Their docs
call out exactly the things the native translator currently loses: automatic
comparisons/variances, responsive design, Top N + Others, custom calculations,
hierarchies, comments, small multiples, and company-wide custom themes.

Microsoft also treats AppSource/custom visuals as first-class Power BI visuals
with certification and licensing constraints. So for template evaluation,
preserving Zebra visuals is a valid enterprise path; native imitation is a
separate design path.

## Recommended New Path

### Path 1 — Zebra Fidelity Lab

Goal: let Andre review the actual Zebra template design language in Fabric.

Build a publisher that:

- starts from the full source PBIX `Report/Layout`, not just Zebra visual rows
- preserves every visualContainer on every page
- strips or injects license settings safely
- copies Zebra custom visual packages into the report definition
- binds the report to the matching `sm_zbr_<slug>` model
- emits missing placeholder columns/measures only when needed
- publishes one report per template

This should make the 20 reports look much closer to the source templates, even
with blank data.

### Path 2 — RW Native Redesign

Goal: use Zebra ideas to make the RW VP Ops dashboard consultant-grade without
depending on Zebra custom visuals unless we deliberately choose them.

Do not auto-convert all templates. Instead:

- select 3-5 reference patterns from the Zebra corpus
- translate each into an RW-specific native component
- validate in Power BI Desktop with screenshots
- promote only the patterns that improve the RW dashboard

Candidate RW patterns:

- executive exception table with variance/data bars
- stage movement waterfall
- forecast bridge with scenario comparison
- renewal/ARR small-multiple trend
- compact KPI strip with RAG and variance deltas

## Immediate Fixes Before Any More Bulk Publishing

1. Preserve source pages in the publisher.
2. Preserve full PBIX page context, not just Zebra visuals.
3. Add a visual-fidelity audit: page count, off-canvas, fallback count, custom
   visual count, missing refs, and blank-model caveat per report.
4. Add a small screenshot gate on 3 templates before opening all 20 again.
5. Decide per run whether the output is `fidelity-zebra` or `native-approx`; do
   not mix the two under the same acceptance criteria.

## Decision

The current Path B native bulk publisher should be treated as a foundation
artifact, not the final reviewable output. The next publish should be a
Zebra-fidelity lab or a smaller RW-native redesign batch, not another blind
20-template native approximation.
