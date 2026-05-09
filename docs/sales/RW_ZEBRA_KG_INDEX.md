# RW Zebra BI Knowledge Graph — Index

Companion to the GraphRAG element map (`RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`).
This index documents the **datamodel + style + binding** layer added on top of
the existing visual-side graph at
`~/Downloads/rw-zebra-bi-template-research-20260509/analysis/`.

Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`
Plan: `docs/superpowers/plans/2026-05-09-zebra-bi-knowledge-graph.md`

## Artifacts

| Path                                  | What                                                                          |
| ------------------------------------- | ----------------------------------------------------------------------------- |
| `data/zebra_kg/nodes_datamodel.jsonl` | Measure / Table / Column / Relationship / Scenario nodes                      |
| `data/zebra_kg/edges_datamodel.jsonl` | depends_on / related_to / scenario_of edges                                   |
| `data/zebra_kg/measure_catalog.csv`   | Flat catalog of every DAX measure across 20 templates                         |
| `data/zebra_kg/style_tokens.json`     | Deduped color/font/border/padding tokens with usage counts and canonical flag |
| `data/zebra_kg_rw/bindings.jsonl`     | RW binding overlay: bound / unbound / needs_measure                           |
| `data/zebra_kg_rw/rw_targets.csv`     | Flat RW tab × element × status view                                           |

End-to-end run produces: 1,572 nodes / 1,099 edges / 439 measures / 106 tokens
(4 canonical) / 33 RW bindings.

## Schema

Node types: `Visual` (from existing miner), `VisualRole` (from existing miner),
`Measure`, `Table`, `Column`, `Relationship`, `Scenario`, `StyleToken`,
`RWBinding`. Schema details in
`docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md` §"Node schema".

## Regen

```bash
# 1. visual-side (already done; re-run only if Zebra corpus changes)
python3 -m scripts.sales.rw_zebra_template_miner \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis

# 2. datamodel-side
python3 -m scripts.sales.rw_zebra_kg_datamodel \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \
  --out-dir data/zebra_kg

# 3. style tokens
python3 -m scripts.sales.rw_zebra_kg_tokens \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg

# 4. RW binding overlay (requires az login for Fabric REST)
python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw
```

## Common queries

```bash
# Variance-driving measures across all templates (currently zero — Zebra Tables
# compute variance at render time, not via named measures).
python3 -m scripts.sales.rw_zebra_kg_query --measures --where is_variance=true

# All PY-scenario measures
python3 -m scripts.sales.rw_zebra_kg_query --measures --where scenario=PY

# Canonical color/font palette
python3 -m scripts.sales.rw_zebra_kg_query --tokens --canonical-only

# RW binding status — what's bound vs needs_measure?
python3 -m scripts.sales.rw_zebra_kg_query --rw-status
```

## Known limitations

- **DAX dependency edges are regex-based.** `[Foo Bar]` references in expressions
  may resolve to columns, not measures. The emit step filters against the
  template's measure-name set, but column references that happen to share a
  measure name will register as false-positive `depends_on` edges.
- **Scenario classifier is name-based** (PY/PL/FC fall through to AC). Templates
  with non-English or unusual conventions may misclassify.
- **Style token canonical threshold is 50** by default; tune via
  `--canonical-threshold`. With the 20-template corpus, only Zebra's font ramp
  crossed the threshold (Segoe UI / 9px / 10px / 12px).
- **Zebra custom-visual color palettes are not captured.** Zebra BI Cards /
  Tables / charts store their colors inside visual-specific config blocks, not
  the standard PowerBI `objects.color.solid.color` schema this sweep targets.
  Per-visual palette extraction is a v2 enhancement, paired with the spec's
  deferred `uses_token` edges.
- **DAX expressions are stored verbatim**, including any embedded comments.
  Do not paste expressions into RW production measures without review.
- **NaN handling** at the pbixray boundary: empty `Expression` / `FormatString`
  cells come back as `float('nan')`, which is truthy in Python. The shaping
  layer coerces non-strings to `""` via `_as_str()` — see
  `scripts/sales/rw_zebra_kg_datamodel.py:_as_str`.
