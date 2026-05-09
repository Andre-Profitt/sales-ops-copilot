# Zebra BI Knowledge Graph — Design Spec

**Date:** 2026-05-09
**Track:** `track:rw`
**Status:** approved (brainstorm), pending implementation plan
**Owner:** Andre

## Purpose

Extract a structured knowledge graph from the 20 downloaded Zebra BI PBIX templates so RW VP Ops (and later other Power BI projects) can replicate Zebra's styling and data-model patterns systematically rather than visually copying.

The existing artifacts capture _visuals_ (1,729-row inventory, 2,438-node graph, 6,209 edges) but miss the data-model linkage — DAX measures, table relationships, role-to-field bindings, and the styling tokens that make Zebra look Zebra. This spec closes that gap.

## Scope

**In scope:**

- Two-layer KG: template-agnostic `zebra_kg/` core + project-scoped `zebra_kg_rw/` overlay
- Extraction from 20 PBIX files already at `~/Downloads/rw-zebra-bi-template-research-20260509/files/`
- DAX measure catalog, relationship graph, style token catalog
- RW binding overlay tying Zebra elements to RW tabs/fields/measures (formalizes the prose in `RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`)
- CLI query tool

**Out of scope:**

- Live Power BI rewrites (separate work, downstream)
- Workforce / other-project overlays (B layer — schema must support, but no overlay built here)
- Re-downloading templates or scraping zebrabi.com (research dump is the input)
- Editing the existing `analysis/` graph files — we land alongside, joined by `visual_id`

## Non-goals

- Generic IBCS theory codification — we capture _what Zebra does in their templates_, not what IBCS prescribes
- A graph DB. Plain JSONL + CSV. Query tool is grep-able CLI, not Neo4j.

## Architecture

### Layered storage

```
~/code/apps/sales-ops-copilot-rw/data/zebra_kg/        <- core (B-ready)
  nodes.jsonl
  edges.jsonl
  style_tokens.json
  measure_catalog.csv
  README.md

~/code/apps/sales-ops-copilot-rw/data/zebra_kg_rw/     <- A overlay
  bindings.jsonl
  rw_targets.csv
```

`data/` gitignored if any individual file exceeds 1 MB. Index doc (see Outputs) is always tracked.

A second project (Workforce, etc.) gets its own `zebra_kg_<project>/` overlay later — core is reused, no rebuild.

### Components

| Script                              | Responsibility    | Inputs                                                   | Outputs                                             |
| ----------------------------------- | ----------------- | -------------------------------------------------------- | --------------------------------------------------- |
| `scripts/sales/zebra_kg_extract.py` | PBIX → core graph | 20 PBIX zips                                             | `nodes.jsonl`, `edges.jsonl`, `measure_catalog.csv` |
| `scripts/sales/zebra_kg_tokens.py`  | Style token sweep | 20 PBIX `Report/Layout` JSONs                            | `style_tokens.json`                                 |
| `scripts/sales/zebra_kg_bind.py`    | RW overlay        | `RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md` + RW measure model | `bindings.jsonl`, `rw_targets.csv`                  |
| `scripts/sales/zebra_kg_query.py`   | Query CLI         | core + overlay                                           | stdout                                              |

All four follow `track:rw` conventions: stdlib + `pandas` + `python-pptx`-style minimalism, no Spark, no notebook.

## Node schema

```jsonc
// Visual — joined to existing visual_inventory.csv by id
{
  "id": "vis:salesfunnel:home3:zbi_table_01",
  "type": "Visual",
  "template": "sales-funnel-power-bi-template",
  "page": "Home 3",
  "visual_family": "ZebraBITable",
  "position": {"x": 0, "y": 0, "w": 1280, "h": 280}
}

// VisualRole — a Zebra projection slot
{
  "id": "role:vis:salesfunnel:home3:zbi_table_01:Values",
  "type": "VisualRole",
  "role_name": "Values",
  "role_kind": "scenario_AC"     // AC | PY | PL | FC | Group | Category | Comments
}

// Measure — extracted DAX
{
  "id": "msr:salesfunnel:Stage Forward Pct",
  "type": "Measure",
  "name": "Stage Forward Pct",
  "table": "f_stage_transition",
  "expression": "DIVIDE([Forward Moves], [Total Transitions])",
  "scenario": "AC",
  "is_variance": false,
  "format_string": "0.0%"
}

// Table / Column / Relationship (from DataModelSchema)
{ "id": "tbl:salesfunnel:f_opp", "type": "Table", "name": "f_opp" }
{ "id": "col:salesfunnel:f_opp:Stage", "type": "Column", "table": "f_opp", "data_type": "string" }
{ "id": "rel:salesfunnel:f_opp.StageId->d_stage.Id", "type": "Relationship",
  "from": "tbl:salesfunnel:f_opp", "to": "tbl:salesfunnel:d_stage",
  "from_col": "StageId", "to_col": "Id",
  "cardinality": "many_to_one", "cross_filter": "single", "active": true }

// StyleToken
{
  "id": "tok:color:zebra_actual_black",
  "type": "StyleToken",
  "kind": "color",                   // color | font | border | padding | glyph
  "value": "#000000",
  "purpose": "AC bar",
  "usage_count": 412
}

// Scenario
{ "id": "scn:PY", "type": "Scenario", "code": "PY", "ibcs_glyph": "outlined" }
```

### Edges

| Edge                              | Meaning                                           |
| --------------------------------- | ------------------------------------------------- |
| `vis:X --contains--> role:X:Y`    | a visual exposes a projection slot                |
| `role:X:Y --resolves_to--> msr:Z` | the slot is bound to a measure                    |
| `vis:X --uses_token--> tok:T`     | visual styling references a token                 |
| `msr:Y --depends_on--> msr:Z`     | DAX measure dependency                            |
| `tbl:A --related_to--> tbl:B`     | semantic-model relationship (cardinality on edge) |
| `msr:Y --scenario_of--> scn:AC`   | scenario classification                           |

Edges live in `edges.jsonl` as `{"src": id, "dst": id, "type": edge_type, "props": {...}}`.

### A-layer overlay (RW bindings)

```jsonc
// zebra_kg_rw/bindings.jsonl
{
  "id": "bind:rw:stage_hygiene:Stage_Forward_Pct_LE",
  "type": "RWBinding",
  "rw_tab": "Stage Hygiene",
  "rw_element": "Stage x Motion Hygiene table",
  "rw_field": "Stage Forward Pct (LE)",
  "source_visual": "vis:salesfunnel:home3:zbi_table_01",
  "source_role": "Values",
  "source_measure_template": "msr:salesfunnel:Stage Forward Pct",
  "rw_measure_target": "msr:rw:Stage Forward Pct LE",       // may not yet exist
  "status": "bound" | "unbound" | "needs_measure"
}
```

The RW measure model (`rw_measure_target` IDs) reads from the `scripts/sales/rw_*.py` measure tables. Rows with `status: needs_measure` directly become a backlog of DAX to author.

## Data flow

```
20 PBIX zips
   │
   ├─ zebra_kg_extract.py ──► nodes.jsonl, edges.jsonl, measure_catalog.csv
   │       (DataModelSchema → measures, tables, rels)
   │       (Report/Layout    → visuals, roles, projections)
   │       (joins existing visual_inventory.csv on id)
   │
   ├─ zebra_kg_tokens.py ──► style_tokens.json
   │       (Report/Layout    → color/font/border/padding/glyph defaults)
   │       (dedupe by value, count usages, flag canonical via threshold)
   │
   └─ zebra_kg_bind.py ──► zebra_kg_rw/bindings.jsonl + rw_targets.csv
           (parses RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md table + reads RW measure model)
           (emits status: bound | unbound | needs_measure)

zebra_kg_query.py reads all of the above for ad-hoc queries.
```

## Query CLI

```bash
# What measures across all Zebra templates drive variance arrows?
zebra_kg_query.py --measures --where is_variance=true

# What style tokens does this visual use?
zebra_kg_query.py --tokens-for vis:salesfunnel:home3:zbi_table_01

# What RW elements are bound vs still need a DAX measure?
zebra_kg_query.py --rw-status

# Show the canonical token palette (usage_count > 50)
zebra_kg_query.py --tokens --canonical-only
```

Output: TSV / JSON via `--format`, stdout-piped friendly.

## Error handling

- PBIX read failures (corrupt zip, missing DataModelSchema) → log to `data/zebra_kg/extract_errors.log`, skip file, continue. Existing extraction already proved all 20 are readable.
- Missing visual ID join (graph node refers to visual not in `visual_inventory.csv`) → emit warning, keep node, mark `inventory_join: false`.
- DAX expressions that fail dependency parsing (regex on `[MeasureName]` references) → keep measure node, drop only the unparseable `depends_on` edges, log.

No retries, no fallbacks. This is a one-shot extraction; failures should be fixed and re-run, not papered over.

## Testing

`tests/sales/test_zebra_kg.py`:

1. **Extraction parity** — running `zebra_kg_extract.py` against a single known PBIX (`sales-funnel-power-bi-template`) emits the expected count of Visual / Measure / Table / Relationship nodes (golden fixture).
2. **Visual ID join** — every Visual node id in `nodes.jsonl` either exists in `visual_inventory.csv` or has `inventory_join: false`.
3. **Edge integrity** — every edge `src` and `dst` resolves to an id in `nodes.jsonl`.
4. **Token canonicalization** — running `zebra_kg_tokens.py` twice produces byte-identical `style_tokens.json` (deterministic dedupe + sort).
5. **RW binding round-trip** — every row in `RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`'s "Exact elements to pull" tables produces ≥1 RWBinding node.

Tests use real PBIX inputs (small file: sales-funnel ~3 MB) checked in under `tests/sales/fixtures/zebra_kg/` if license allows; otherwise use a synthetic PBIX shaped like the schema and skip the parity test in CI with `pytest.mark.requires_zebra_corpus`.

## Outputs (deliverables)

1. Four scripts under `scripts/sales/zebra_kg_*.py`
2. Five data files under `data/zebra_kg/` and `data/zebra_kg_rw/`
3. `docs/sales/RW_ZEBRA_KG_INDEX.md` — query examples, schema reference, regen instructions
4. Tests under `tests/sales/test_zebra_kg.py`

## Open questions deferred to plan

- Whether `data/zebra_kg/*.jsonl` is gitignored or tracked — depends on actual size after extraction (decide post-extract)
- Whether to land a Workforce overlay as a smoke test of the B layer this week — decide after RW overlay lands

## Out-of-scope reminders

- No re-styling of existing RW visuals here. This work outputs the _spec_; visual rewrites are a downstream PR.
- No live PBIX edits. We read PBIX, never write back.
- No measure authoring inside this work. `status: needs_measure` rows are a backlog, not deliverables of this spec.
