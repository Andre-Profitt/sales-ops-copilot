# data/zebra_kg/schemas/

Per-template schematic models extracted from the 20 Zebra BI PBIX
templates. Each subdirectory contains the full data model (tables,
columns, measures, relationships) for one template, in a directory
shape that maps to Fabric's TMDL parts list.

The directories are gitignored (regenerable from the source PBIX files);
only this README is tracked.

## Layout

Per-template directory at `<template_slug>/`:

```
<template_slug>/
  metadata.json        template_slug, source_pbix, pbixray_version, counts
  model.json           full structured model (all tables/cols/measures/rels)
  measures.csv         flat measure list with full DAX (greppable)
  relationships.json   all rels + cardinality/cross-filter/active topology summary
  tables/
    <table>.json       per-table: columns + measures filtered to this table
```

`table_count` in metadata reflects the number of files written under
`tables/` (includes calculated tables surfaced from `pbixray.schema`);
`user_visible_table_count` is `pbixray.tables` (excludes calculated).

## Regen

```bash
# All 20 templates (~30s)
python3 -m scripts.sales.rw_zebra_kg_save_schemas \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg/schemas

# Single template (probe before scaling)
python3 -m scripts.sales.rw_zebra_kg_save_schemas \
  --template sales-dashboard-power-bi-template
```

## What's here as of 2026-05-09

20 templates, 257 files total. 177 tables (incl. calculated helpers),
839 columns, 439 measures, 133 relationships.

Top 5 by measure count (richest schemas to lift from):

| Template | Measures | Tables | Rels |
|---|---:|---:|---:|
| manufacturing-oee-power-bi-template | 58 | 12 | 9 |
| daily-sales-flash-power-bi-dashboard | 40 | 20 | 14 |
| saas-sales-power-bi-dashboard-template | 38 | 10 | 5 |
| brand-product-portfolio-analysis-automotive | 31 | 5 | 2 |
| cost-management-power-bi-template | 26 | 16 | 10 |

`daily-sales-flash` is the natural source for PR2's `*_7d` measures
(period-delta / what-changed grammar). `cost-management` and
`manufacturing-oee` are the richest if RW ever moves toward
operational-finance scorecards.

## Use this

1. Pick a target template via the suggester or by inspecting `_index.json`
   (cross-template summary, see PR5-T2 follow-up).
2. Read `<slug>/measures.csv` and grep for the DAX pattern you need.
3. Read `<slug>/tables/<table>.json` for the column shape that backs that
   measure — those are the columns RW would need to provide.
4. Adapt: rename Zebra tables to RW (`Sales` → `f_opportunity`, `Calendar`
   → `d_calendar`, etc.), add cardinal-rule motion filter, push via
   `rw_push_semantic_model.py`.

See also `docs/sales/RW_ZEBRA_KG_PATTERNS.md` for the cross-template
DAX pattern atlas + topology atlas + suggester.
