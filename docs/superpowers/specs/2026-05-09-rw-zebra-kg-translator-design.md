# RW Zebra KG Translator — Design Spec

**Date:** 2026-05-09
**Track:** track:rw
**Branch:** feat/track-rw-tooling
**Owner:** Andre Profitt
**Companion atlases:**

- `docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md` (610 lines, source side)
- `docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md` (480 lines, target side)

---

## 1. Purpose

Build a deterministic translator that consumes any source Zebra `visualContainer`
config and emits a native Power BI `visualContainer` that round-trips through
Microsoft Fabric without uncertified-AppSource gating, preserving IBCS fidelity at
the documented 85–90% ceiling. The translator is paired with a GraphRAG retriever
over the two infrastructure atlases so authoring tools (and reviewers) can ask
intent-based questions across the source-and-target rule corpus.

This closes PR9 of the RW dashboard rebuild track. The Zebra atlas is the source
grammar; the native atlas is the target grammar; the translator is the wire.

## 2. Scope

**In scope.**

- Semantic GraphRAG index over both atlas markdown files, linked to the existing
  structured KG (`data/zebra_kg/`).
- IBCS column synthesis (X,Y → x-y, x-y-percent) and the missing native primitives
  flagged by the corpus map (dataBars CF, composite KPI tile, multiRowCard wiring,
  ZebraBICharts dispatch).
- A single dispatcher consumed by both existing translation surfaces:
  `rw_zebra_kg_native_emit.emit_native_visuals` (report.json path) and
  `rw_zebra_kg_swap_pbix.swap_layout` (PBIX path).
- Tests at unit, dispatcher, and end-to-end (one published Fabric template) levels.

**Out of scope.**

- New Recipe shape — `VisualRecipe` from `rw_zebra_kg_recipe.py` is reused as-is.
- New query CLI — `rw_zebra_kg_query.py` stays for structured queries; GraphRAG is
  a complementary semantic layer.
- PBIX upload-flow changes — `swap_pbix --upload` keeps its current behaviour.
- Theme-JSON builder — RW-IBCS theme is already applied at the page level.
- Page-level layout, slicer wiring, navigation buttons — translator is per-visual.

## 3. Architecture

Three new modules under `scripts/sales/`, each with one clear responsibility.

```
                     atlas markdowns               structured KG
                     ────────────────              ────────────────
                     RW_ZEBRA_BI_*.md              nodes_datamodel.jsonl
                     RW_POWER_BI_NATIVE_*.md       dax_patterns.json
                              │                   topology_patterns.json
                              │                   infrastructure/*_atlas.json
                              │                   schemas/<slug>/
                              ▼                            │
                  rw_zebra_kg_graphrag.py ◀────────────────┘
                  (semantic retriever)
                              │
                              │ optional, for explainability + UX
                              ▼
                  ┌─── rw_zebra_kg_translator.py ────┐
                  │     (dispatcher: family → builder) │
                  └────┬─────────────────────────┬─────┘
                       │                         │
                       ▼                         ▼
              rw_zebra_kg_ibcs_synth.py    _pbir_helpers.py
              (synthesis + missing CF)     (existing builders)
                       │                         │
                       └─────┬───────────────────┘
                             ▼
                  ┌──────────┴──────────┐
                  ▼                     ▼
       native_emit.emit_native_visuals  swap_pbix.swap_layout
       (report.json path)               (PBIX path)
```

Each component is independently testable; the dispatcher is the only seam where
they compose.

## 4. Components

### 4.1 `rw_zebra_kg_graphrag.py` — semantic retriever

**Responsibility.** Index the prose atlases and make them retrievable by intent
query, linked to the structured KG nodes.

**Index build.** Chunks Zebra atlas §3 (IBCS column synthesis), §6 (Cards rendering
grammar), §7 (translation matrix), §11 (complete Zebra API surface), §12 (native
rebuild rulebook), §13 (cellular findings) and Native atlas §2 (CF reference), §5
(PBIR visualContainer schema), §6 (translation matrix, 47 rows). Each chunk
becomes a node; edges link chunks to KG nodes by `template_slug`,
`visual_family`, and `pattern_name` keys mined from chunk text.

**Embeddings.** `sentence-transformers` `all-MiniLM-L6-v2`. Local, ~80MB model,
runs on M4 in seconds. No external API; fits the SimCorp-tenant compliance posture.

**Persistence.** `data/zebra_kg/graphrag/` with three files:

- `nodes.jsonl` — `{id, source_doc, section, anchor, text, linked_kg_ids: [...]}`
- `edges.jsonl` — `{src, dst, relation}` where relation ∈ `{describes, links_to_pattern, links_to_template}`
- `embeddings.npy` — float32 matrix aligned to `nodes.jsonl` row order.

**Retriever API.**

```python
def retrieve(intent: str,
             family: str | None = None,
             top_k: int = 5) -> list[Chunk]: ...
```

`Chunk` is a dataclass with `id`, `source_doc`, `section`, `text`, `score`,
`linked_kg_ids`. `family` filter restricts to chunks tagged with a Zebra family
(Tables/Cards/Charts/Waterfall) when supplied.

**CLI.** `python3 -m scripts.sales.rw_zebra_kg_graphrag query "..."` and
`python3 -m scripts.sales.rw_zebra_kg_graphrag build` (regenerate index).

### 4.2 `rw_zebra_kg_ibcs_synth.py` — fidelity primitives

Encodes the IBCS rules that the corpus map flagged as documented-but-unimplemented.

**Public functions.**

- `synthesize_ibcs_columns(scenarios: set[str]) -> list[ColumnSpec]` — given a
  scenario set such as `{"AC", "PY"}`, returns column specs for `AC`, `PY`,
  `AC-PY`, `AC-PY %` in canonical Zebra column order. Encodes the X,Y →
  x-y / x-y-percent grammar (Zebra atlas §3).
- `synthesize_dax(spec: ColumnSpec, target_model: ModelCatalog) -> str` — emits
  `[X] - [Y]` for delta, `DIVIDE([X]-[Y], ABS([Y]))` for relative variance, with
  `* -1` invert flip when `spec.is_cost` is true.
- `format_string_for(format_code: int) -> str` — `0`→`#,##0`, `1`→
  `+#,##0;-#,##0`, `2`→`+0.0%;-0.0%`, `3`→`+#,##0.0;-#,##0.0`.
- `build_databar_cf_objects(column_name: str, max_field: str, positive_color: str,
negative_color: str = "#C00000") -> dict` — emits the conditional formatting
  block that produces Zebra's bullet-bar `markerStyle=5` look on a `tableEx`
  column. Field-driven max via `max_field`. Returns the `objects` block to merge
  into a `singleVisual.objects` dict.
- `build_composite_kpi_tile(label: str, value_measure: str,
variance_measure: str | None, x: int, y: int, w: int, h: int,
visual_id_prefix: str) -> list[dict]` — emits a 3-VC stack (textbox header +
  card value + small variance card) at the same `(x,y,w,h)` to mimic Zebra's
  Cards KPI tile.

**ColumnSpec dataclass.**

```python
@dataclass
class ColumnSpec:
    name: str               # e.g. "AC-PY"
    role: str               # "absolute" | "delta" | "relative"
    base: tuple[str, ...]   # e.g. ("AC", "PY")
    format_code: int        # 0/1/2/3
    is_cost: bool = False
```

### 4.3 `rw_zebra_kg_translator.py` — dispatcher

**Responsibility.** Single function maps a source Zebra `visualContainer` config
and a target measure catalog to a list of native `visualContainer` dicts.

**API.**

```python
def translate_visual(src_vc: dict,
                     target_catalog: MeasureCatalog,
                     rw_map: BindMap,
                     position: Position | None = None) -> list[dict]: ...
```

Returns a list (not a single dict) because composite tiles produce multiple VCs
at the same coordinates.

**Dispatch table.**

| Source `visualType` family                                | Native target                                | Source of builder                                   |
| --------------------------------------------------------- | -------------------------------------------- | --------------------------------------------------- |
| `ZebraBITables*`                                          | `tableEx` + IBCS-synth columns + dataBars CF | `_pbir_helpers.build_table_visual` + `ibcs_synth.*` |
| `zebraBiCards*` — 1 measure, no category                  | `card`                                       | `_pbir_helpers.build_card_visual_with_objects`      |
| `zebraBiCards*` — multi-measure                           | `multiRowCard`                               | port from `swap_pbix`                               |
| `zebraBiCards*` — composite tile                          | `card` + textbox + variance card             | `ibcs_synth.build_composite_kpi_tile`               |
| `ZebraBICharts*`                                          | `clusteredBarChart` (or column variant)      | `_pbir_helpers.build_clustered_bar_chart_visual`    |
| `waterfall*`                                              | `waterfallChart`                             | port from `swap_pbix.swap_layout`                   |
| `textbox`, `basicShape`, `slicer`, `actionButton`, others | identity pass-through                        | existing                                            |

Both `native_emit.emit_native_visuals` and `swap_pbix.swap_layout` are refactored
to call `translate_visual` instead of inlining their per-family branches. Both
inherit any new family without duplicate logic.

## 5. Data flow

**Source.** Either a deserialized PBIX `Report/Layout` (from `swap_pbix`) or a
`VisualRecipe` (from `rw_zebra_kg_recipe.extract_recipe`). Both shapes carry the
fields the dispatcher needs: `visualType`, `projections` (role → queryRef list),
`objects` (decoded), `position`.

**Target catalog.** A `MeasureCatalog` dataclass loaded from
`data/zebra_kg/schemas/<rw_target>/measures.csv` and the live RW model BIM. Maps
canonical scenario names to existing measure DAX expressions.

**Bind map.** Existing `bindings.jsonl` (RW field → Zebra field overlay).

**Output.** List of native `visualContainer` JSON dicts ready to be inserted into
a `report.json` `sections[i].visualContainers` list.

## 6. Error handling

- Unknown `visualType` → log + identity pass-through (do not raise). Translator
  is best-effort; non-Zebra visuals must not be lost.
- Missing measure in `target_catalog` → emit a placeholder `textbox` with the
  intended column name + a warning row in the translator's run-log. Do not
  silently drop columns.
- IBCS synthesis with empty scenario set → return absolute columns only; do not
  raise.
- GraphRAG index missing on disk → first call to `retrieve` triggers a build
  with a printed notice. CI uses a pre-built fixture; the translator does not
  call `retrieve` in its hot path (GraphRAG is for authoring/UX only).

## 7. Testing strategy

**Unit — `tests/sales/test_rw_zebra_kg_ibcs_synth.py`.** Golden tests for:

- All 14 scenario-pair combinations present in `measure_catalog.csv` (covers AC×{PY,PL,FC}, PY×PL, etc.).
- Format-string lookup parity with the Zebra atlas §3 enum.
- DAX synthesis with and without `is_cost` flip.
- `build_databar_cf_objects` schema-validates against the PBIR objects-block grammar.
- `build_composite_kpi_tile` returns 3 VCs at identical `(x,y,w,h)`.

**Unit — `tests/sales/test_rw_zebra_kg_graphrag.py`.**

- Index-build determinism (same input → identical `nodes.jsonl` + identical embeddings via fixed seed).
- 5 hand-graded retrieval queries with expected top-1 chunk anchors.
- Family-filter cuts result set as expected.

**Dispatcher — `tests/sales/test_rw_zebra_kg_translator.py`.**

- For every row in `data/zebra_kg/infrastructure/raw_configs.jsonl` (360 rows), call `translate_visual` with a fixture catalog. Assert: returns ≥ 1 VC, every returned VC has required PBIR keys (`name`, `position`, `singleVisual`), no exception.
- Per-family golden tests: 1 representative VC per family translated against an asserted JSON fixture.
- Both `native_emit.emit_native_visuals` and `swap_pbix.swap_layout` smoke tests confirm they call `translate_visual` (mock + count).

**End-to-end — `tests/sales/test_rw_zebra_kg_translator_e2e.py`** (skipped without
Fabric creds).

- Translate one full template (`IBCS Sales-Cost-Profit`), publish to a Fabric
  scratch workspace, fetch the deployed `report.json`, assert visualContainer
  count and measure-reference count match expectations.

## 8. Acceptance criteria

1. `rw_zebra_kg_translator.translate_visual` handles all 4 Zebra families
   (Tables / Cards / Charts / Waterfall) for the 360 visualContainers in the
   corpus without raising.
2. IBCS synthesis golden tests pass for the 14 scenario-pair combinations in
   `measure_catalog.csv`.
3. GraphRAG retrieval returns the correct atlas section for 5 hand-graded intent
   queries (top-1 anchor match).
4. End-to-end template publishes to a Fabric scratch workspace and validates
   (visualContainer count in == count out modulo composite-tile expansion;
   measure-reference count preserved).
5. `rw_compose_scorecard_home` runs unchanged after the refactor (existing test
   passes without modification).
6. `swap_pbix --upload` runs unchanged (existing test passes without modification).

## 9. Trade-offs

- **`sentence-transformers` adds ~200MB to the venv.** Accepted: M4 has the
  headroom, the alternative (keyword-only index) defeats the point of intent-based
  retrieval. Model is cached after first load.
- **Two-surface dispatch (native_emit + swap_pbix both call `translate_visual`).**
  Accepted: one source of truth for translation rules outweighs the small risk of
  surface-specific edge cases. Both surfaces are exercised in CI.
- **Composite KPI tile is 3 separate VCs at one `(x,y,w,h)`.** Accepted: this is
  the documented 10–15% irreducible loss. Power BI renders them stacked
  correctly; there is no native composite-visual primitive.
- **Translator does not regenerate the GraphRAG index on every call.** The index
  is built once and persisted; rebuild is an explicit CLI step. Trade is faster
  hot path for explicit cache management.

## 10. Risks

- **Atlas-chunk drift.** If atlas markdowns are edited, the GraphRAG index
  becomes stale. Mitigation: index nodes carry a content hash; the build CLI
  prints a diff vs. on-disk index.
- **Fabric end-to-end test flakes on tenant policy.** Mitigation: end-to-end
  test is a separate marker (`@pytest.mark.fabric`) and skipped in standard CI.
- **`sentence-transformers` first-load downloads the model.** Mitigation:
  pre-warm in `make setup-rw` (existing target).

## 11. Plan size

One implementation plan under `docs/superpowers/plans/2026-05-09-rw-zebra-kg-translator.md`
with approximately 12 tasks: 3 GraphRAG (index build + retriever + tests), 5 IBCS
synth (column synth + DAX synth + format-string + dataBars CF + composite tile),
4 dispatcher (translator module + native_emit refactor + swap_pbix refactor +
end-to-end test).

## 12. Out-of-band notes

- This spec assumes the existing `_pbir_helpers.py` builder API is stable; if a
  builder needs a signature change to support a new field, document the change
  in the plan task that introduces it.
- The translator is per-visual. Page-level concerns (filters, theme, navigation)
  are handled by the existing composer (`rw_compose_scorecard_home` and
  per-tab composers). This spec does not modify them.
- Fidelity numbers come from the native atlas §6 translation matrix (47 rows);
  this spec does not redefine them.
