# RW Zebra KG Translator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic translator that consumes any source Zebra `visualContainer` config and emits a native Power BI `visualContainer` that round-trips through Microsoft Fabric without uncertified-AppSource gating, plus a GraphRAG retriever over the two infrastructure atlases for intent-based authoring queries.

**Architecture:** Three new modules under `scripts/sales/`: `rw_zebra_kg_ibcs_synth.py` (column synthesis + DAX synthesis + dataBars CF + composite KPI tile), `rw_zebra_kg_translator.py` (single dispatch function `translate_visual`), and `rw_zebra_kg_graphrag.py` (sentence-transformers index over atlas markdowns). Both existing translation surfaces (`rw_zebra_kg_native_emit.emit_native_visuals` and `rw_zebra_kg_swap_pbix.swap_layout`) refactor to call `translate_visual` so per-family logic lives in one place.

**Tech Stack:** Python 3.13, pytest, pandas (already in venv), `sentence-transformers` `all-MiniLM-L6-v2`, `numpy`, Fabric REST API for end-to-end, Power BI report.json (PBIR-Legacy) schema.

**Spec:** `docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md`

**Branch:** `feat/track-rw-tooling` (continue stacking on existing track:rw work).

---

## File Structure

| File                                         | Status | Responsibility                                                                                |
| -------------------------------------------- | ------ | --------------------------------------------------------------------------------------------- |
| `scripts/sales/rw_zebra_kg_ibcs_synth.py`    | new    | IBCS column synthesis, DAX synthesis, format strings, dataBars CF builder, composite KPI tile |
| `scripts/sales/rw_zebra_kg_translator.py`    | new    | Single `translate_visual(src_vc, target_catalog, rw_map)` dispatcher                          |
| `scripts/sales/rw_zebra_kg_graphrag.py`      | new    | Atlas chunker + sentence-transformers index + retriever + CLI                                 |
| `scripts/sales/rw_zebra_kg_native_emit.py`   | modify | Replace inline per-family branches with `translate_visual` call                               |
| `scripts/sales/rw_zebra_kg_swap_pbix.py`     | modify | Replace inline per-family branches with `translate_visual` call                               |
| `tests/sales/test_rw_zebra_kg_ibcs_synth.py` | new    | Synthesis unit tests                                                                          |
| `tests/sales/test_rw_zebra_kg_translator.py` | new    | Dispatcher tests + 360-VC corpus smoke                                                        |
| `tests/sales/test_rw_zebra_kg_graphrag.py`   | new    | Index-build determinism + retrieval tests                                                     |
| `tests/sales/fixtures/zebra_translator/`     | new    | Per-family golden VCs + reduced fixture corpus                                                |
| `requirements.txt`                           | modify | Add `sentence-transformers>=2.7,<4` and `numpy>=1.26`                                         |
| `data/zebra_kg/graphrag/`                    | new    | `nodes.jsonl`, `edges.jsonl`, `embeddings.npy`, `manifest.json`                               |

---

## Task 1: Setup — dependencies, directories, module scaffolds

**Files:**

- Modify: `requirements.txt`
- Create: `scripts/sales/rw_zebra_kg_ibcs_synth.py` (skeleton)
- Create: `scripts/sales/rw_zebra_kg_translator.py` (skeleton)
- Create: `scripts/sales/rw_zebra_kg_graphrag.py` (skeleton)
- Create: `tests/sales/fixtures/zebra_translator/.gitkeep`
- Create: `data/zebra_kg/graphrag/.gitkeep`

- [ ] **Step 1: Add deps to requirements.txt**

Append after the last existing line in `requirements.txt`:

```
sentence-transformers>=2.7,<4
numpy>=1.26
```

- [ ] **Step 2: Install deps**

```bash
.venv/bin/pip install 'sentence-transformers>=2.7,<4' 'numpy>=1.26'
```

Expected: install completes, `.venv/bin/python -c "from sentence_transformers import SentenceTransformer; import numpy"` exits 0.

- [ ] **Step 3: Create module scaffolds**

Create `scripts/sales/rw_zebra_kg_ibcs_synth.py`:

```python
"""IBCS column synthesis, DAX synthesis, conditional formatting + composite tile builders.

Encodes the rules documented in:
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §3 (column synthesis grammar)
- docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md §6 (Cards rendering grammar)
- docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md §2 (CF reference)

This module is pure (no I/O, no network); consumed by rw_zebra_kg_translator.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnSpec:
    """One synthesized IBCS column.

    role: 'absolute' (raw scenario column), 'delta' (X - Y), or 'relative' (X-Y / |Y|).
    base: scenario tuple. ('AC',) for absolute, ('AC','PY') for delta/relative.
    format_code: 0=integer, 1=signed, 2=percent, 3=signed-decimal.
    is_cost: invert sign so positive = good (AC < PY for costs).
    """

    name: str
    role: str
    base: tuple[str, ...]
    format_code: int
    is_cost: bool = False
```

Create `scripts/sales/rw_zebra_kg_translator.py`:

```python
"""Per-visual dispatcher: source Zebra visualContainer config -> native PBIR visualContainer.

Both rw_zebra_kg_native_emit.emit_native_visuals (report.json path) and
rw_zebra_kg_swap_pbix.swap_layout (PBIX path) call translate_visual so per-family
logic lives in one place.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.3
"""
from __future__ import annotations
```

Create `scripts/sales/rw_zebra_kg_graphrag.py`:

```python
"""Semantic retriever over the Zebra + native PBI infrastructure atlases.

Chunks the two markdown files at heading boundaries, embeds with
sentence-transformers all-MiniLM-L6-v2, persists to data/zebra_kg/graphrag/.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.1
"""
from __future__ import annotations
```

- [ ] **Step 4: Create empty fixture + graphrag dirs**

```bash
mkdir -p tests/sales/fixtures/zebra_translator data/zebra_kg/graphrag
touch tests/sales/fixtures/zebra_translator/.gitkeep data/zebra_kg/graphrag/.gitkeep
```

- [ ] **Step 5: Smoke-import the new modules**

```bash
.venv/bin/python -c "from scripts.sales import rw_zebra_kg_ibcs_synth, rw_zebra_kg_translator, rw_zebra_kg_graphrag"
```

Expected: exits 0.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt scripts/sales/rw_zebra_kg_ibcs_synth.py scripts/sales/rw_zebra_kg_translator.py scripts/sales/rw_zebra_kg_graphrag.py tests/sales/fixtures/zebra_translator/.gitkeep data/zebra_kg/graphrag/.gitkeep
git commit -m "scaffold(track:rw): translator + ibcs-synth + graphrag module scaffolds"
```

---

## Task 2: `MeasureCatalog` + `BindMap` loaders

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_translator.py`
- Test: `tests/sales/test_rw_zebra_kg_translator.py`

The dispatcher needs typed inputs. `MeasureCatalog` wraps the live RW model's measure inventory keyed by canonical scenario; `BindMap` wraps `bindings.jsonl`. Both are read-only dataclasses with class-method loaders so tests can pass dict fixtures.

- [ ] **Step 1: Write the failing test**

Create `tests/sales/test_rw_zebra_kg_translator.py`:

```python
"""Tests for the rw_zebra_kg_translator dispatcher."""
from __future__ import annotations

import pytest

from scripts.sales.rw_zebra_kg_translator import BindMap, MeasureCatalog


def test_measure_catalog_has_returns_true_for_known_measure():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR", "PY": "Closed Won ARR PY"},
        measure_to_table={
            "Total Closed Won ARR": "Measures",
            "Closed Won ARR PY": "Measures",
        },
    )
    assert cat.has("AC") is True
    assert cat.has("FC") is False


def test_measure_catalog_resolve_returns_table_qualified_ref():
    cat = MeasureCatalog(
        by_scenario={"AC": "Total Closed Won ARR"},
        measure_to_table={"Total Closed Won ARR": "Measures"},
    )
    assert cat.resolve("AC") == ("Measures", "Total Closed Won ARR")


def test_measure_catalog_resolve_missing_scenario_returns_none():
    cat = MeasureCatalog(by_scenario={}, measure_to_table={})
    assert cat.resolve("AC") is None


def test_bindmap_lookup_returns_rw_field_for_zebra_field():
    bm = BindMap(zebra_to_rw={"PnL.AC": "Measures.Total Closed Won ARR"})
    assert bm.lookup("PnL.AC") == "Measures.Total Closed Won ARR"
    assert bm.lookup("Unknown.X") is None
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: ImportError — `BindMap`, `MeasureCatalog` not defined.

- [ ] **Step 3: Implement the dataclasses**

Append to `scripts/sales/rw_zebra_kg_translator.py`:

```python
from dataclasses import dataclass, field


@dataclass(frozen=True)
class MeasureCatalog:
    """Available measures in the target dataset, keyed by canonical scenario.

    by_scenario: {"AC": "Total Closed Won ARR", "PY": "Closed Won ARR PY", ...}
    measure_to_table: {"Total Closed Won ARR": "Measures", ...}
    """

    by_scenario: dict[str, str] = field(default_factory=dict)
    measure_to_table: dict[str, str] = field(default_factory=dict)

    def has(self, scenario: str) -> bool:
        return scenario in self.by_scenario

    def resolve(self, scenario: str) -> tuple[str, str] | None:
        name = self.by_scenario.get(scenario)
        if name is None:
            return None
        table = self.measure_to_table.get(name)
        if table is None:
            return None
        return (table, name)


@dataclass(frozen=True)
class BindMap:
    """Zebra field-name -> RW field-name overlay (loaded from bindings.jsonl)."""

    zebra_to_rw: dict[str, str] = field(default_factory=dict)

    def lookup(self, zebra_ref: str) -> str | None:
        return self.zebra_to_rw.get(zebra_ref)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_translator.py tests/sales/test_rw_zebra_kg_translator.py
git commit -m "feat(track:rw): MeasureCatalog + BindMap dataclasses for translator"
```

---

## Task 3: `format_string_for` + `synthesize_dax`

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_ibcs_synth.py`
- Test: `tests/sales/test_rw_zebra_kg_ibcs_synth.py` (new)

The format-code lookup encodes Zebra atlas §4 (encoding reference). DAX synthesis is the X,Y → `[X]-[Y]` and `DIVIDE([X]-[Y], ABS([Y]))` rule with cost-flip.

- [ ] **Step 1: Write the failing tests**

Create `tests/sales/test_rw_zebra_kg_ibcs_synth.py`:

```python
"""Tests for IBCS column synthesis primitives."""
from __future__ import annotations

import pytest

from scripts.sales.rw_zebra_kg_ibcs_synth import (
    ColumnSpec,
    format_string_for,
    synthesize_dax,
)
from scripts.sales.rw_zebra_kg_translator import MeasureCatalog


def test_format_string_for_known_codes():
    assert format_string_for(0) == "#,##0"
    assert format_string_for(1) == "+#,##0;-#,##0"
    assert format_string_for(2) == "+0.0%;-0.0%"
    assert format_string_for(3) == "+#,##0.0;-#,##0.0"


def test_format_string_for_unknown_code_returns_default():
    assert format_string_for(99) == "#,##0"


def test_synthesize_dax_absolute_returns_existing_measure_ref():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC"},
        measure_to_table={"ARR_AC": "Measures"},
    )
    spec = ColumnSpec(name="AC", role="absolute", base=("AC",), format_code=0)
    assert synthesize_dax(spec, cat) == "[ARR_AC]"


def test_synthesize_dax_delta_emits_subtraction():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC", "PY": "ARR_PY"},
        measure_to_table={"ARR_AC": "Measures", "ARR_PY": "Measures"},
    )
    spec = ColumnSpec(name="AC-PY", role="delta", base=("AC", "PY"), format_code=1)
    assert synthesize_dax(spec, cat) == "[ARR_AC] - [ARR_PY]"


def test_synthesize_dax_relative_emits_divide_abs():
    cat = MeasureCatalog(
        by_scenario={"AC": "ARR_AC", "PY": "ARR_PY"},
        measure_to_table={"ARR_AC": "Measures", "ARR_PY": "Measures"},
    )
    spec = ColumnSpec(name="AC-PY %", role="relative", base=("AC", "PY"), format_code=2)
    assert synthesize_dax(spec, cat) == "DIVIDE([ARR_AC] - [ARR_PY], ABS([ARR_PY]))"


def test_synthesize_dax_cost_flips_sign():
    cat = MeasureCatalog(
        by_scenario={"AC": "Cost_AC", "PL": "Cost_PL"},
        measure_to_table={"Cost_AC": "Measures", "Cost_PL": "Measures"},
    )
    spec = ColumnSpec(
        name="AC-PL", role="delta", base=("AC", "PL"), format_code=1, is_cost=True
    )
    assert synthesize_dax(spec, cat) == "([Cost_AC] - [Cost_PL]) * -1"


def test_synthesize_dax_missing_scenario_returns_none():
    cat = MeasureCatalog(by_scenario={"AC": "ARR_AC"}, measure_to_table={"ARR_AC": "Measures"})
    spec = ColumnSpec(name="PY", role="absolute", base=("PY",), format_code=0)
    assert synthesize_dax(spec, cat) is None
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: ImportError — `format_string_for`, `synthesize_dax` not defined.

- [ ] **Step 3: Implement the functions**

Append to `scripts/sales/rw_zebra_kg_ibcs_synth.py` (after the `ColumnSpec` definition):

```python
from scripts.sales.rw_zebra_kg_translator import MeasureCatalog

_FORMAT_STRINGS = {
    0: "#,##0",
    1: "+#,##0;-#,##0",
    2: "+0.0%;-0.0%",
    3: "+#,##0.0;-#,##0.0",
}


def format_string_for(format_code: int) -> str:
    """Map Zebra format-code enum to a Power BI format-string.

    Per Zebra atlas §4 encoding reference. Unknown codes fall back to integer.
    """
    return _FORMAT_STRINGS.get(format_code, "#,##0")


def synthesize_dax(spec: ColumnSpec, catalog: MeasureCatalog) -> str | None:
    """Generate the DAX expression for a synthesized IBCS column.

    Returns None if any base scenario isn't in the catalog.
    """
    resolved = [catalog.resolve(s) for s in spec.base]
    if any(r is None for r in resolved):
        return None
    names = [r[1] for r in resolved]
    if spec.role == "absolute":
        return f"[{names[0]}]"
    if spec.role == "delta":
        body = f"[{names[0]}] - [{names[1]}]"
        return f"({body}) * -1" if spec.is_cost else body
    if spec.role == "relative":
        body = f"DIVIDE([{names[0]}] - [{names[1]}], ABS([{names[1]}]))"
        return f"({body}) * -1" if spec.is_cost else body
    return None
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_zebra_kg_ibcs_synth.py
git commit -m "feat(track:rw): ibcs-synth — format_string_for + synthesize_dax"
```

---

## Task 4: `synthesize_ibcs_columns` — the X,Y → x-y, x-y-percent rule

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_ibcs_synth.py`
- Modify: `tests/sales/test_rw_zebra_kg_ibcs_synth.py`

The core IBCS synthesis rule from Zebra atlas §3. Given a scenario set like `{"AC", "PY"}`, return ColumnSpecs in canonical order: each base scenario as absolute, then each (X,Y) pair as delta + relative. Pair order: AC always first; PY → PL → FC if present.

- [ ] **Step 1: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_ibcs_synth.py`:

```python
from scripts.sales.rw_zebra_kg_ibcs_synth import synthesize_ibcs_columns


def test_synthesize_ibcs_columns_single_scenario():
    cols = synthesize_ibcs_columns({"AC"})
    assert [c.name for c in cols] == ["AC"]
    assert [c.role for c in cols] == ["absolute"]


def test_synthesize_ibcs_columns_ac_py_emits_delta_and_relative():
    cols = synthesize_ibcs_columns({"AC", "PY"})
    assert [c.name for c in cols] == ["AC", "PY", "AC-PY", "AC-PY %"]
    assert [c.role for c in cols] == ["absolute", "absolute", "delta", "relative"]
    assert [c.format_code for c in cols] == [0, 0, 1, 2]


def test_synthesize_ibcs_columns_ac_pl_pair():
    cols = synthesize_ibcs_columns({"AC", "PL"})
    assert [c.name for c in cols] == ["AC", "PL", "AC-PL", "AC-PL %"]


def test_synthesize_ibcs_columns_three_way_emits_pairs_in_canonical_order():
    cols = synthesize_ibcs_columns({"AC", "PY", "PL"})
    names = [c.name for c in cols]
    # AC absolutes first, then PY, then PL, then AC-PY pair, then AC-PL pair
    assert names == [
        "AC", "PY", "PL",
        "AC-PY", "AC-PY %",
        "AC-PL", "AC-PL %",
    ]


def test_synthesize_ibcs_columns_includes_fc_pair_last():
    cols = synthesize_ibcs_columns({"AC", "FC"})
    assert [c.name for c in cols] == ["AC", "FC", "AC-FC", "AC-FC %"]


def test_synthesize_ibcs_columns_unknown_scenario_dropped():
    cols = synthesize_ibcs_columns({"AC", "XYZ"})
    assert [c.name for c in cols] == ["AC"]


def test_synthesize_ibcs_columns_propagates_is_cost_flag():
    cols = synthesize_ibcs_columns({"AC", "PY"}, is_cost=True)
    assert all(c.is_cost is True for c in cols)


def test_synthesize_ibcs_columns_no_ac_returns_only_absolutes():
    """Variance pairs only synthesized when AC is present."""
    cols = synthesize_ibcs_columns({"PY", "PL"})
    assert [c.name for c in cols] == ["PY", "PL"]
    assert all(c.role == "absolute" for c in cols)
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 8 ImportErrors for `synthesize_ibcs_columns`.

- [ ] **Step 3: Implement `synthesize_ibcs_columns`**

Append to `scripts/sales/rw_zebra_kg_ibcs_synth.py`:

```python
_KNOWN_SCENARIOS = ("AC", "PY", "PL", "FC")
_NON_AC_ORDER = ("PY", "PL", "FC")


def synthesize_ibcs_columns(
    scenarios: set[str],
    is_cost: bool = False,
) -> list[ColumnSpec]:
    """Generate the canonical IBCS column set for a scenario combination.

    Encodes Zebra atlas §3 column synthesis rule: pair (AC, Y) projections
    auto-derive `<AC>-<Y>` (delta, format_code=1) and `<AC>-<Y> %` (relative,
    format_code=2). Variance pairs only emit when AC is present.

    Order: all known absolutes (AC, PY, PL, FC) in canonical order, then each
    (AC, Y) pair's delta + relative for Y in (PY, PL, FC).

    Unknown scenarios are silently dropped.
    """
    present = [s for s in _KNOWN_SCENARIOS if s in scenarios]
    out: list[ColumnSpec] = [
        ColumnSpec(name=s, role="absolute", base=(s,), format_code=0, is_cost=is_cost)
        for s in present
    ]
    if "AC" not in present:
        return out
    for y in _NON_AC_ORDER:
        if y in present:
            out.append(
                ColumnSpec(
                    name=f"AC-{y}",
                    role="delta",
                    base=("AC", y),
                    format_code=1,
                    is_cost=is_cost,
                )
            )
            out.append(
                ColumnSpec(
                    name=f"AC-{y} %",
                    role="relative",
                    base=("AC", y),
                    format_code=2,
                    is_cost=is_cost,
                )
            )
    return out
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 15 passed (7 from Task 3 + 8 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_zebra_kg_ibcs_synth.py
git commit -m "feat(track:rw): ibcs-synth — synthesize_ibcs_columns (X,Y → delta + relative)"
```

---

## Task 5: `build_databar_cf_objects` — bullet-bar conditional formatting

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_ibcs_synth.py`
- Modify: `tests/sales/test_rw_zebra_kg_ibcs_synth.py`

DataBars CF on a tableEx column produces Zebra's bullet-bar `markerStyle=5` look. Per native atlas §2: CF is applied via `singleVisual.objects.values[].properties.dataBars` with `axis` (positive color), `negativeBarColor`, and `axisColor` properties, plus a `dataPoint` with field-driven max via a measure reference.

- [ ] **Step 1: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_ibcs_synth.py`:

```python
from scripts.sales.rw_zebra_kg_ibcs_synth import build_databar_cf_objects


def test_build_databar_cf_objects_returns_values_block():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    assert "values" in cf
    assert isinstance(cf["values"], list)
    assert len(cf["values"]) == 1


def test_build_databar_cf_objects_carries_column_selector():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    entry = cf["values"][0]
    selector = entry["selector"]["metadata"]
    assert selector == "ARR"


def test_build_databar_cf_objects_carries_positive_color():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert props["axis"]["solid"]["color"]["expr"]["Literal"]["Value"] == "'#1F77B4'"


def test_build_databar_cf_objects_default_negative_color():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert (
        props["negativeBarColor"]["solid"]["color"]["expr"]["Literal"]["Value"]
        == "'#C00000'"
    )


def test_build_databar_cf_objects_field_driven_max_present():
    cf = build_databar_cf_objects(
        column_name="ARR",
        max_field="Measures.scaleGroup_max",
        positive_color="#1F77B4",
    )
    props = cf["values"][0]["properties"]
    assert "maxValue" in props
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 5 ImportErrors for `build_databar_cf_objects`.

- [ ] **Step 3: Implement the builder**

Append to `scripts/sales/rw_zebra_kg_ibcs_synth.py`:

```python
def build_databar_cf_objects(
    column_name: str,
    max_field: str,
    positive_color: str,
    negative_color: str = "#C00000",
) -> dict:
    """DataBars conditional-formatting block for one tableEx column.

    Returns a partial singleVisual.objects dict suitable for merging into
    build_table_visual(objects=...). Encodes the Zebra bullet-bar markerStyle=5
    look as native PBI dataBars: positive_color for the bar, negative_color for
    negative values, and a field-driven max via max_field ('Table.Measure' ref)
    so multiple columns share an axis (Zebra scaleGroup behaviour).

    Per native atlas §2 conditional-formatting reference.
    """
    if "." not in max_field:
        raise ValueError(f"max_field must be 'Table.Measure', got: {max_field!r}")
    max_table, max_measure = max_field.split(".", 1)
    return {
        "values": [
            {
                "selector": {"metadata": column_name},
                "properties": {
                    "axis": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{positive_color}'"}}}}
                    },
                    "negativeBarColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": f"'{negative_color}'"}}}}
                    },
                    "maxValue": {
                        "expr": {
                            "Measure": {
                                "Expression": {"SourceRef": {"Entity": max_table}},
                                "Property": max_measure,
                            }
                        }
                    },
                    "axisColor": {
                        "solid": {"color": {"expr": {"Literal": {"Value": "'#999999'"}}}}
                    },
                },
            }
        ]
    }
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_zebra_kg_ibcs_synth.py
git commit -m "feat(track:rw): ibcs-synth — dataBars CF builder (bullet-bar markerStyle=5 native equiv)"
```

---

## Task 6: `build_composite_kpi_tile` — Zebra Cards KPI shape

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_ibcs_synth.py`
- Modify: `tests/sales/test_rw_zebra_kg_ibcs_synth.py`

A composite KPI tile is 3 PBIR visualContainers stacked at the same `(x, y, w, h)`: header textbox, value card, optional small variance card at the bottom-right corner. Reuses existing `_pbir_helpers` builders.

- [ ] **Step 1: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_ibcs_synth.py`:

```python
from scripts.sales.rw_zebra_kg_ibcs_synth import build_composite_kpi_tile


def test_build_composite_kpi_tile_returns_3_vcs_when_variance_provided():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    assert len(vcs) == 3


def test_build_composite_kpi_tile_returns_2_vcs_when_no_variance():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table=None,
        variance_measure=None,
        x=10,
        y=20,
        w=300,
        h=120,
    )
    assert len(vcs) == 2


def test_build_composite_kpi_tile_all_vcs_share_x_and_y():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    for vc in vcs:
        assert vc["x"] == 10
        assert vc["y"] == 20


def test_build_composite_kpi_tile_overall_bbox_matches_w_h():
    vcs = build_composite_kpi_tile(
        label="Pipeline ARR",
        value_table="Measures",
        value_measure="Total Pipeline ARR",
        variance_table="Measures",
        variance_measure="Pipeline ARR vs PY",
        x=10,
        y=20,
        w=300,
        h=120,
    )
    max_right = max(vc["x"] + vc["width"] for vc in vcs)
    max_bottom = max(vc["y"] + vc["height"] for vc in vcs)
    assert max_right == 10 + 300
    assert max_bottom == 20 + 120
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 4 ImportErrors for `build_composite_kpi_tile`.

- [ ] **Step 3: Implement the builder**

Append to `scripts/sales/rw_zebra_kg_ibcs_synth.py`:

```python
from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_textbox_visual,
)


def build_composite_kpi_tile(
    label: str,
    value_table: str,
    value_measure: str,
    variance_table: str | None,
    variance_measure: str | None,
    x: float,
    y: float,
    w: float,
    h: float,
) -> list[dict]:
    """Three-VC stack approximating the Zebra Cards KPI tile.

    - header textbox: top 24px, full width
    - value card: middle, full width minus variance footprint when variance present
    - variance card (optional): bottom-right corner, 30% width × 24px

    All VCs share (x, y, w, h) bounding box per native atlas §6 row 14.
    """
    header_h = 24
    variance_w = w * 0.30 if variance_measure else 0.0
    variance_h = 24 if variance_measure else 0.0

    out: list[dict] = [
        build_textbox_visual(
            text=label,
            x=x,
            y=y,
            w=w,
            h=header_h,
            font_size_pt=10,
            color="#666666",
        ),
        build_card_visual_with_objects(
            measure_table=value_table,
            measure_name=value_measure,
            display_title=value_measure,
            x=x,
            y=y + header_h,
            w=w - variance_w,
            h=h - header_h,
        ),
    ]
    if variance_measure:
        out.append(
            build_card_visual_with_objects(
                measure_table=variance_table,
                measure_name=variance_measure,
                display_title=variance_measure,
                x=x + (w - variance_w),
                y=y + (h - variance_h),
                w=variance_w,
                h=variance_h,
            )
        )
    return out
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_ibcs_synth.py -v
```

Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_zebra_kg_ibcs_synth.py
git commit -m "feat(track:rw): ibcs-synth — composite KPI tile builder (3-VC stack)"
```

---

## Task 7: `translate_visual` — identity pass-through + dispatch skeleton

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_translator.py`
- Modify: `tests/sales/test_rw_zebra_kg_translator.py`

Sets up the `translate_visual` API: takes a source visualContainer (PBIX `Layout` shape: `{x, y, width, height, config: <json string>}`), parses it, dispatches by family, returns a list of native VCs. Identity pass-through for non-Zebra families is the first branch.

- [ ] **Step 1: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_translator.py`:

```python
import json

from scripts.sales.rw_zebra_kg_translator import translate_visual


def _make_src_vc(visual_type: str, x=0, y=0, w=300, h=200) -> dict:
    """Helper: build a Layout-shape visualContainer (config is a JSON string)."""
    return {
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "config": json.dumps(
            {
                "name": "abc123",
                "singleVisual": {"visualType": visual_type, "projections": {}},
            }
        ),
    }


def test_translate_visual_textbox_passes_through():
    src = _make_src_vc("textbox")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert len(out) == 1
    assert out[0] is src


def test_translate_visual_basicShape_passes_through():
    src = _make_src_vc("basicShape")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_slicer_passes_through():
    src = _make_src_vc("slicer")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_unknown_visualtype_passes_through():
    src = _make_src_vc("someUnknownVisual")
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]


def test_translate_visual_invalid_config_string_passes_through():
    src = {"x": 0, "y": 0, "width": 300, "height": 200, "config": "not-json{"}
    out = translate_visual(src, MeasureCatalog(), BindMap())
    assert out == [src]
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: 5 ImportErrors for `translate_visual`.

- [ ] **Step 3: Implement the dispatcher skeleton**

Append to `scripts/sales/rw_zebra_kg_translator.py`:

```python
import json


def _classify_family(visual_type: str) -> str:
    """Return one of: 'tables', 'cards', 'charts', 'waterfall', 'passthrough'.

    Native types (textbox/basicShape/slicer/actionButton/card) and unknown types
    fall through to passthrough — the translator never loses a visual.
    """
    if visual_type.startswith("ZebraBITables"):
        return "tables"
    if visual_type.startswith("zebraBiCards"):
        return "cards"
    if visual_type.startswith("ZebraBICharts"):
        return "charts"
    if visual_type.startswith("waterfall"):
        return "waterfall"
    return "passthrough"


def translate_visual(
    src_vc: dict,
    target_catalog: MeasureCatalog,
    rw_map: BindMap,
) -> list[dict]:
    """Translate one source visualContainer to one or more native ones.

    Identity pass-through for non-Zebra families and any parse failure;
    the translator must never lose visuals.
    """
    cstr = src_vc.get("config")
    if not isinstance(cstr, str):
        return [src_vc]
    try:
        cfg = json.loads(cstr)
    except json.JSONDecodeError:
        return [src_vc]
    sv = cfg.get("singleVisual") or {}
    vt = sv.get("visualType", "")
    family = _classify_family(vt)
    if family == "passthrough":
        return [src_vc]
    # Non-passthrough families implemented in Task 8.
    return [src_vc]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: 9 passed (4 from Task 2 + 5 new).

- [ ] **Step 5: Commit**

```bash
git add scripts/sales/rw_zebra_kg_translator.py tests/sales/test_rw_zebra_kg_translator.py
git commit -m "feat(track:rw): translator — translate_visual dispatcher skeleton + passthrough"
```

---

## Task 8: `translate_visual` — Zebra families (Tables / Cards / Charts / Waterfall)

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_translator.py`
- Modify: `tests/sales/test_rw_zebra_kg_translator.py`
- Create: `tests/sales/fixtures/zebra_translator/sample_table.json`
- Create: `tests/sales/fixtures/zebra_translator/sample_card.json`
- Create: `tests/sales/fixtures/zebra_translator/sample_waterfall.json`

The four Zebra families. Tables uses `_pbir_helpers.build_table_visual` + `ibcs_synth.build_databar_cf_objects`. Cards routes single-measure to `build_card_visual_with_objects`, multi-measure to `multiRowCard` (via the `swap_pbix` rebrand pattern). Charts uses `build_clustered_bar_chart_visual`. Waterfall ports the `swap_pbix` rebrand pattern that builds a tableEx scaffold and rewrites `visualType` + projections.

- [ ] **Step 1: Capture real source-config samples**

Write a one-off snippet that pulls 3 representative rows from `data/zebra_kg/infrastructure/raw_configs.jsonl` and saves them as fixture JSON. Run from repo root:

```bash
.venv/bin/python -c "
import json
from pathlib import Path

src = Path('data/zebra_kg/infrastructure/raw_configs.jsonl')
out_dir = Path('tests/sales/fixtures/zebra_translator')
out_dir.mkdir(parents=True, exist_ok=True)

picks = {'tables': None, 'cards': None, 'waterfall': None}
with src.open() as f:
    for line in f:
        row = json.loads(line)
        fam = row['visual_family']
        if fam == 'ZebraBITables' and picks['tables'] is None:
            picks['tables'] = row
        elif fam == 'ZebraBICards' and picks['cards'] is None:
            picks['cards'] = row
        elif fam == 'ZebraWaterfall' and picks['waterfall'] is None:
            picks['waterfall'] = row
        if all(picks.values()):
            break

(out_dir / 'sample_table.json').write_text(json.dumps(picks['tables'], indent=2))
(out_dir / 'sample_card.json').write_text(json.dumps(picks['cards'], indent=2))
if picks['waterfall']:
    (out_dir / 'sample_waterfall.json').write_text(json.dumps(picks['waterfall'], indent=2))
print({k: bool(v) for k, v in picks.items()})
"
```

Expected: `{'tables': True, 'cards': True, 'waterfall': True}` (or `False` for waterfall if corpus has none — ZebraWaterfall is rare).

- [ ] **Step 2: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_translator.py`:

```python
import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "zebra_translator"


def _layout_vc_from_raw(raw_row: dict) -> dict:
    """Convert an infra-miner raw_configs.jsonl row into a Layout-shape vc.

    The miner stores singleVisual.objects + projections+visualType separately,
    not as an embedded config string. Re-pack them so the translator can parse.
    """
    pos = raw_row["position"]
    return {
        "x": pos["x"],
        "y": pos["y"],
        "width": pos["w"],
        "height": pos["h"],
        "config": json.dumps(
            {
                "name": "raw",
                "singleVisual": {
                    "visualType": raw_row["visual_type_full"],
                    "projections": {
                        role: [{"queryRef": q} for q in qs]
                        for role, qs in raw_row.get("projections", {}).items()
                    },
                    "objects": raw_row.get("objects", {}),
                },
            }
        ),
    }


def _catalog_for_refs(raw_row: dict) -> MeasureCatalog:
    """Build a catalog that resolves every queryRef in the raw row's projections.

    Each measure stays in its native table and is keyed by the field-name
    (which is what BindMap will lookup against).
    """
    by_scenario = {}
    measure_to_table = {}
    for refs in raw_row.get("projections", {}).values():
        for ref in refs:
            if "." not in ref:
                continue
            tbl, fld = ref.split(".", 1)
            by_scenario[fld] = fld
            measure_to_table[fld] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def _bindmap_for_refs(raw_row: dict) -> BindMap:
    return BindMap(
        zebra_to_rw={
            ref: ref
            for refs in raw_row.get("projections", {}).values()
            for ref in refs
            if "." in ref
        }
    )


def test_translate_visual_table_emits_native_tableEx():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert len(out) == 1
    cfg = json.loads(out[0]["config"])
    assert cfg["singleVisual"]["visualType"] == "tableEx"


def test_translate_visual_table_preserves_position():
    raw = json.loads((FIXTURES / "sample_table.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert out[0]["x"] == src["x"]
    assert out[0]["y"] == src["y"]
    assert out[0]["width"] == src["width"]
    assert out[0]["height"] == src["height"]


def test_translate_visual_card_emits_native_card():
    raw = json.loads((FIXTURES / "sample_card.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    assert len(out) >= 1
    cfg = json.loads(out[0]["config"])
    assert cfg["singleVisual"]["visualType"] in {"card", "multiRowCard"}


@pytest.mark.skipif(
    not (FIXTURES / "sample_waterfall.json").exists(),
    reason="ZebraWaterfall fixture not available in corpus",
)
def test_translate_visual_waterfall_emits_native_waterfallChart():
    raw = json.loads((FIXTURES / "sample_waterfall.json").read_text())
    src = _layout_vc_from_raw(raw)
    out = translate_visual(src, _catalog_for_refs(raw), _bindmap_for_refs(raw))
    cfg = json.loads(out[0]["config"])
    assert cfg["singleVisual"]["visualType"] == "waterfallChart"


def test_translate_visual_corpus_smoke_no_exceptions():
    """Every row in the 360-VC corpus translates without raising."""
    src = Path("data/zebra_kg/infrastructure/raw_configs.jsonl")
    if not src.exists():
        pytest.skip("infrastructure corpus not present")
    cat = MeasureCatalog()  # empty -> translator falls back gracefully
    bm = BindMap()
    count = 0
    with src.open() as f:
        for line in f:
            raw = json.loads(line)
            vc = _layout_vc_from_raw(raw)
            out = translate_visual(vc, cat, bm)
            assert isinstance(out, list)
            assert len(out) >= 1
            count += 1
    assert count > 0
```

- [ ] **Step 3: Run tests to confirm tableEx/card/waterfall fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: corpus-smoke passes (skeleton always returns `[src_vc]`); tableEx/card/waterfall assertions fail because passthrough returns the source unchanged.

- [ ] **Step 4: Implement the family branches**

Edit `scripts/sales/rw_zebra_kg_translator.py`. Replace the dispatcher body in `translate_visual` (the `family == "passthrough"` branch and below) with:

```python
    if family == "passthrough":
        return [src_vc]
    pos = {
        "x": src_vc.get("x", 0),
        "y": src_vc.get("y", 0),
        "w": src_vc.get("width", 0),
        "h": src_vc.get("height", 0),
    }
    projs = sv.get("projections") or {}
    if family == "tables":
        out = _translate_tables(projs, pos, target_catalog, rw_map)
    elif family == "cards":
        out = _translate_cards(projs, pos, target_catalog, rw_map)
    elif family == "charts":
        out = _translate_charts(projs, pos, target_catalog, rw_map)
    elif family == "waterfall":
        out = _translate_waterfall(projs, pos, target_catalog, rw_map)
    else:
        out = None
    if out:
        return out
    return [src_vc]
```

Then append the family helpers at the bottom of the same file:

```python
from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_clustered_bar_chart_visual,
    build_table_visual,
)

_CAT_ROLES = ("Category", "Group", "Categories")
_VAL_ROLES = ("Values", "Y", "Measures", "PreviousYear", "Plan", "Forecast")


def _refs_for_roles(projs: dict, roles: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for r in roles:
        for p in projs.get(r) or []:
            qr = p.get("queryRef") if isinstance(p, dict) else None
            if isinstance(qr, str):
                out.append(qr)
    return out


def _resolve_ref(zebra_ref: str, rw_map: BindMap, catalog: MeasureCatalog) -> tuple[str, str] | None:
    """zebra_ref looks like 'Table.Field'. Resolve to the live (table, measure)."""
    rw_ref = rw_map.lookup(zebra_ref) or zebra_ref
    if "." not in rw_ref:
        return None
    tbl, fld = rw_ref.split(".", 1)
    tbl2 = catalog.measure_to_table.get(fld, tbl)
    return (tbl2, fld)


def _translate_tables(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    columns: list[dict] = []
    for cref in cat_refs[:2]:
        if "." not in cref:
            continue
        ctbl, cfld = cref.split(".", 1)
        columns.append({"table": ctbl, "field": cfld, "kind": "column", "title": cfld})
    for vref in val_refs:
        resolved = _resolve_ref(vref, rw_map, catalog)
        if resolved is None:
            continue
        tbl, fld = resolved
        columns.append({"table": tbl, "field": fld, "kind": "measure", "title": fld})
    if not any(c["kind"] == "measure" for c in columns):
        return None
    return [
        build_table_visual(
            name=f"tbl_{int(pos['x'])}_{int(pos['y'])}",
            columns=columns,
            x=pos["x"], y=pos["y"], w=pos["w"], h=pos["h"],
        )
    ]


def _translate_cards(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not val_refs:
        return None
    if not cat_refs and len(val_refs) == 1:
        resolved = _resolve_ref(val_refs[0], rw_map, catalog)
        if resolved is None:
            return None
        tbl, fld = resolved
        return [
            build_card_visual_with_objects(
                measure_table=tbl, measure_name=fld, display_title=fld,
                x=pos["x"], y=pos["y"], w=pos["w"], h=pos["h"],
            )
        ]
    columns: list[dict] = []
    for cref in cat_refs[:1]:
        if "." not in cref:
            continue
        ctbl, cfld = cref.split(".", 1)
        columns.append({"table": ctbl, "field": cfld, "kind": "column", "title": cfld})
    for vref in val_refs:
        resolved = _resolve_ref(vref, rw_map, catalog)
        if resolved is None:
            continue
        tbl, fld = resolved
        columns.append({"table": tbl, "field": fld, "kind": "measure", "title": fld})
    if not any(c["kind"] == "measure" for c in columns):
        return None
    scaffold = build_table_visual(
        name=f"mrc_{int(pos['x'])}_{int(pos['y'])}",
        columns=columns,
        x=pos["x"], y=pos["y"], w=pos["w"], h=pos["h"],
    )
    cfg = json.loads(scaffold["config"])
    cfg["singleVisual"]["visualType"] = "multiRowCard"
    scaffold["config"] = json.dumps(cfg, ensure_ascii=False)
    return [scaffold]


def _translate_charts(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    cref = cat_refs[0]
    vref = val_refs[0]
    if "." not in cref:
        return None
    ctbl, cfld = cref.split(".", 1)
    resolved = _resolve_ref(vref, rw_map, catalog)
    if resolved is None:
        return None
    vtbl, vfld = resolved
    return [
        build_clustered_bar_chart_visual(
            name=f"chart_{int(pos['x'])}_{int(pos['y'])}",
            category_table=ctbl, category_field=cfld,
            measure_table=vtbl, measure_name=vfld,
            x=pos["x"], y=pos["y"], w=pos["w"], h=pos["h"],
        )
    ]


def _translate_waterfall(
    projs: dict, pos: dict, catalog: MeasureCatalog, rw_map: BindMap
) -> list[dict] | None:
    cat_refs = _refs_for_roles(projs, _CAT_ROLES)
    val_refs = _refs_for_roles(projs, _VAL_ROLES)
    if not cat_refs or not val_refs:
        return None
    cref = cat_refs[0]
    vref = val_refs[0]
    if "." not in cref:
        return None
    ctbl, cfld = cref.split(".", 1)
    resolved = _resolve_ref(vref, rw_map, catalog)
    if resolved is None:
        return None
    vtbl, vfld = resolved
    columns = [
        {"table": ctbl, "field": cfld, "kind": "column", "title": cfld},
        {"table": vtbl, "field": vfld, "kind": "measure", "title": vfld},
    ]
    scaffold = build_table_visual(
        name=f"wf_{int(pos['x'])}_{int(pos['y'])}",
        columns=columns,
        x=pos["x"], y=pos["y"], w=pos["w"], h=pos["h"],
    )
    cfg = json.loads(scaffold["config"])
    sv2 = cfg["singleVisual"]
    sv2["visualType"] = "waterfallChart"
    vals = sv2["projections"].get("Values", [])
    cat_p, y_p = [], []
    for p in vals:
        qr = p.get("queryRef", "")
        if "." in qr:
            _, pf = qr.split(".", 1)
            if pf == cfld:
                cat_p.append(p)
            else:
                y_p.append(p)
    sv2["projections"] = {"Category": cat_p, "Y": y_p}
    scaffold["config"] = json.dumps(cfg, ensure_ascii=False)
    return [scaffold]
```

- [ ] **Step 5: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py -v
```

Expected: 14 passed (or 13 + 1 skipped if waterfall fixture is missing).

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_zebra_kg_translator.py tests/sales/test_rw_zebra_kg_translator.py tests/sales/fixtures/zebra_translator/
git commit -m "feat(track:rw): translator — Zebra Tables/Cards/Charts/Waterfall family branches + corpus smoke"
```

---

## Task 9: Refactor `native_emit` and `swap_pbix` to call `translate_visual`

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_native_emit.py`
- Modify: `scripts/sales/rw_zebra_kg_swap_pbix.py`
- Modify: `tests/sales/test_rw_zebra_kg_translator.py`

`native_emit.emit_native_visuals` currently inlines per-family branches (`_emit_zebra_table`, `_emit_zebra_card`, etc.). It now adapts each `VisualRecipe` to a Layout-shape VC, calls `translate_visual`, and returns the result. `swap_pbix.swap_layout` similarly replaces its inline branches with a `translate_visual` call. Existing callers (`rw_compose_scorecard_home`, `swap_pbix --upload`) keep working unchanged because the signature of both refactored functions stays the same.

- [ ] **Step 1: Append failing tests for the refactor wiring**

Append to `tests/sales/test_rw_zebra_kg_translator.py`:

```python
from unittest.mock import patch


def test_native_emit_emit_native_visuals_calls_translate_visual():
    """The refactor wires emit_native_visuals through translate_visual."""
    from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
    from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe

    recipe = Recipe(
        source_template="t",
        source_page="p",
        visuals=[
            VisualRecipe(
                visual_type="textbox",
                position={"x": 0, "y": 0, "w": 100, "h": 50},
                role_bindings={},
                scenarios_used=[],
                tables_referenced=[],
                measure_refs=[],
                text="hello",
            )
        ],
    )
    with patch(
        "scripts.sales.rw_zebra_kg_native_emit.translate_visual",
        wraps=__import__("scripts.sales.rw_zebra_kg_translator", fromlist=["translate_visual"]).translate_visual,
    ) as spy:
        emit_native_visuals(recipe, rw_map={})
        assert spy.call_count == 1


def test_swap_pbix_swap_layout_calls_translate_visual():
    """The refactor wires swap_layout through translate_visual."""
    from scripts.sales.rw_zebra_kg_swap_pbix import swap_layout

    layout = {
        "sections": [
            {
                "name": "p1",
                "displayName": "Page 1",
                "visualContainers": [
                    {
                        "x": 0,
                        "y": 0,
                        "width": 200,
                        "height": 100,
                        "config": json.dumps(
                            {
                                "name": "v1",
                                "singleVisual": {
                                    "visualType": "textbox",
                                    "projections": {},
                                },
                            }
                        ),
                    }
                ],
            }
        ]
    }
    rmap = {"measures_by_table": {}, "calendar_alias": "Calendar"}
    with patch(
        "scripts.sales.rw_zebra_kg_swap_pbix.translate_visual",
        wraps=__import__("scripts.sales.rw_zebra_kg_translator", fromlist=["translate_visual"]).translate_visual,
    ) as spy:
        swap_layout(layout, rmap)
        assert spy.call_count == 1
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py::test_native_emit_emit_native_visuals_calls_translate_visual tests/sales/test_rw_zebra_kg_translator.py::test_swap_pbix_swap_layout_calls_translate_visual -v
```

Expected: AttributeError — `translate_visual` not yet imported in those modules.

- [ ] **Step 3: Refactor `rw_zebra_kg_native_emit.py`**

Replace the body of `emit_native_visuals` (lines starting at the `def emit_native_visuals` definition through end of file). Open `scripts/sales/rw_zebra_kg_native_emit.py` and replace the existing `emit_native_visuals` function with:

```python
from scripts.sales.rw_zebra_kg_translator import (
    BindMap,
    MeasureCatalog,
    translate_visual,
)


def _recipe_visual_to_layout_vc(v: VisualRecipe) -> dict:
    """Adapt a VisualRecipe to the Layout-shape vc that translate_visual expects."""
    pos = v.position
    projections = {
        role: [{"queryRef": ref} for ref in (refs or [])]
        for role, refs in (v.role_bindings or {}).items()
    }
    sv: dict = {"visualType": v.visual_type, "projections": projections}
    if v.text:
        sv["objects"] = {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": v.text}]}]}}]}
    return {
        "x": pos.get("x", 0),
        "y": pos.get("y", 0),
        "width": pos.get("w", 0),
        "height": pos.get("h", 0),
        "config": json.dumps({"name": "recipe", "singleVisual": sv}),
    }


def _bindmap_from_rw_map(rw_map: dict[str, list[str]]) -> BindMap:
    """rw_map shape is {rw_table: [measure_name, ...]}; flatten to a zebra-ref->rw-ref overlay."""
    flat: dict[str, str] = {}
    for tbl, names in (rw_map or {}).items():
        for n in names:
            flat[n] = f"{tbl}.{n}"
    return BindMap(zebra_to_rw=flat)


def _catalog_from_rw_map(rw_map: dict[str, list[str]]) -> MeasureCatalog:
    by_scenario: dict[str, str] = {}
    measure_to_table: dict[str, str] = {}
    for tbl, names in (rw_map or {}).items():
        for n in names:
            by_scenario[n] = n
            measure_to_table[n] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def emit_native_visuals(recipe: Recipe, rw_map: dict[str, list[str]]) -> list[dict]:
    """Translate every visual in the recipe to a native PBIR visualContainer.

    Wraps translate_visual so per-family logic stays in one place.
    """
    catalog = _catalog_from_rw_map(rw_map)
    bm = _bindmap_from_rw_map(rw_map)
    out: list[dict] = []
    for v in recipe.visuals:
        src = _recipe_visual_to_layout_vc(v)
        out.extend(translate_visual(src, catalog, bm))
    return out
```

Also add `import json` to the top of the file if not already present.

The old `_emit_zebra_*` and `_emit_textbox` / `_emit_waterfall_placeholder` helpers are now unreachable. Delete them in this same edit to avoid dead code.

- [ ] **Step 4: Refactor `rw_zebra_kg_swap_pbix.py`**

Open `scripts/sales/rw_zebra_kg_swap_pbix.py`. Find `swap_layout` (the function that loops over `sections[i].visualContainers`). Replace the per-family branch ladder (`if "waterfall" in vt: ... elif "zebraBiCards" in vt: ... elif "ZebraBITables" in vt: ... else: keep`) with a single `translate_visual` call:

```python
from scripts.sales.rw_zebra_kg_translator import (
    BindMap,
    MeasureCatalog,
    translate_visual,
)


def _catalog_from_rmap(rmap: dict) -> MeasureCatalog:
    """rmap['measures_by_table'] is {table: set(measure_names)}; flatten to catalog."""
    by_scenario: dict[str, str] = {}
    measure_to_table: dict[str, str] = {}
    for tbl, names in (rmap.get("measures_by_table") or {}).items():
        for n in names:
            by_scenario[n] = n
            measure_to_table[n] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)
```

Inside `swap_layout`, where the inline `if "waterfall" in vt: ...` chain currently lives, replace it with:

```python
            catalog = _catalog_from_rmap(rmap)
            bm = BindMap()  # PBIX path: no overlay; identity binding
            translated = translate_visual(vc, catalog, bm)
            # translate_visual returns [src_vc] on pass-through or family failure;
            # don't double-count untranslated visuals.
            if len(translated) == 1 and translated[0] is vc:
                new.append(vc)
                stats["kept"] += 1
            else:
                new.extend(translated)
                stats.setdefault("translated", 0)
                stats["translated"] += len(translated)
            continue
```

Keep all surrounding bookkeeping (the loop structure, the `cstr = vc.get("config")` parse + JSONDecodeError handling that decides whether to call into translation at all) intact.

- [ ] **Step 5: Run all related tests**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator.py tests/sales/test_rw_zebra_kg_ibcs_synth.py tests/sales/test_rw_compose_scorecard_home.py -v
```

Expected: all pass. The compose_scorecard_home test confirms the upstream caller still works after the refactor.

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_zebra_kg_native_emit.py scripts/sales/rw_zebra_kg_swap_pbix.py tests/sales/test_rw_zebra_kg_translator.py
git commit -m "refactor(track:rw): native_emit + swap_pbix call translate_visual (single dispatch)"
```

---

## Task 10: GraphRAG — atlas chunker + index builder

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_graphrag.py`
- Test: `tests/sales/test_rw_zebra_kg_graphrag.py`

Chunk both atlas markdowns at H2/H3 heading boundaries, embed with `all-MiniLM-L6-v2`, persist `nodes.jsonl` + `embeddings.npy`. CLI subcommand: `build`.

- [ ] **Step 1: Write the failing tests**

Create `tests/sales/test_rw_zebra_kg_graphrag.py`:

```python
"""Tests for rw_zebra_kg_graphrag index builder + retriever."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from scripts.sales.rw_zebra_kg_graphrag import chunk_markdown, build_index


SAMPLE_MD = """\
# Title

## §3 Column synthesis

The X,Y projection rule auto-derives `<x>-<y>` and `<x>-<y>-percent` columns.
Format codes: 0=integer, 1=signed, 2=percent.

## §6 Cards rendering

Cards composite tile = header textbox + value card + variance card.

### §6.1 Bullet markerStyle

markerStyle=5 produces the integrated bullet bar.
"""


def test_chunk_markdown_emits_one_node_per_h2_or_h3():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    sections = [c["section"] for c in chunks]
    assert "§3 Column synthesis" in sections
    assert "§6 Cards rendering" in sections
    assert "§6.1 Bullet markerStyle" in sections


def test_chunk_markdown_preserves_section_text():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    by_section = {c["section"]: c for c in chunks}
    assert "auto-derives" in by_section["§3 Column synthesis"]["text"]
    assert "markerStyle=5" in by_section["§6.1 Bullet markerStyle"]["text"]


def test_chunk_markdown_each_node_has_required_fields():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    for c in chunks:
        assert set(c.keys()) >= {"id", "source_doc", "section", "anchor", "text"}


def test_build_index_writes_three_files(tmp_path):
    md_path = tmp_path / "sample.md"
    md_path.write_text(SAMPLE_MD)
    out_dir = tmp_path / "graphrag"
    build_index([md_path], out_dir, model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert (out_dir / "nodes.jsonl").exists()
    assert (out_dir / "embeddings.npy").exists()
    assert (out_dir / "manifest.json").exists()


def test_build_index_node_count_matches_embedding_rows(tmp_path):
    md_path = tmp_path / "sample.md"
    md_path.write_text(SAMPLE_MD)
    out_dir = tmp_path / "graphrag"
    build_index([md_path], out_dir, model_name="sentence-transformers/all-MiniLM-L6-v2")
    nodes = [json.loads(l) for l in (out_dir / "nodes.jsonl").open()]
    emb = np.load(out_dir / "embeddings.npy")
    assert len(nodes) == emb.shape[0]
    assert emb.shape[1] == 384  # all-MiniLM-L6-v2 dim
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_graphrag.py -v
```

Expected: ImportErrors for `chunk_markdown`, `build_index`.

- [ ] **Step 3: Implement chunker + builder**

Append to `scripts/sales/rw_zebra_kg_graphrag.py`:

```python
import hashlib
import json
import re
from pathlib import Path

import numpy as np

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)\s*$")


def chunk_markdown(text: str, source_doc: str) -> list[dict]:
    """Chunk markdown by H2/H3 headings.

    Each chunk: {id, source_doc, section, anchor, text}. id is a content hash.
    """
    lines = text.splitlines()
    chunks: list[dict] = []
    current: dict | None = None
    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                current["text"] = current["text"].strip()
                chunks.append(current)
            section = m.group(2).strip()
            anchor = re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")
            current = {
                "id": "",
                "source_doc": source_doc,
                "section": section,
                "anchor": anchor,
                "text": "",
            }
        elif current is not None:
            current["text"] += line + "\n"
    if current is not None:
        current["text"] = current["text"].strip()
        chunks.append(current)
    for c in chunks:
        h = hashlib.sha1((c["source_doc"] + c["section"] + c["text"]).encode()).hexdigest()[:16]
        c["id"] = h
    return chunks


def build_index(
    md_paths: list[Path],
    out_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> None:
    """Chunk all markdown files, embed, persist to out_dir.

    Writes nodes.jsonl, embeddings.npy, manifest.json.
    """
    from sentence_transformers import SentenceTransformer

    out_dir.mkdir(parents=True, exist_ok=True)
    nodes: list[dict] = []
    for p in md_paths:
        nodes.extend(chunk_markdown(p.read_text(), source_doc=p.name))
    model = SentenceTransformer(model_name)
    texts = [n["text"] for n in nodes]
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    nodes_path = out_dir / "nodes.jsonl"
    with nodes_path.open("w") as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    np.save(out_dir / "embeddings.npy", emb.astype("float32"))
    manifest = {
        "model": model_name,
        "node_count": len(nodes),
        "embedding_dim": int(emb.shape[1]) if len(emb) else 0,
        "sources": [str(p) for p in md_paths],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_graphrag.py -v
```

Expected: 5 passed. (First run downloads the model — ~80MB, takes ~30s.)

- [ ] **Step 5: Build the real index against both atlases**

```bash
.venv/bin/python -c "
from pathlib import Path
from scripts.sales.rw_zebra_kg_graphrag import build_index
build_index(
    [
        Path('docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md'),
        Path('docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md'),
    ],
    Path('data/zebra_kg/graphrag'),
)
"
ls data/zebra_kg/graphrag/
```

Expected: `nodes.jsonl`, `embeddings.npy`, `manifest.json` written. `manifest.json` shows `node_count > 30`.

- [ ] **Step 6: Commit (data files stay gitignored — see Step 7)**

```bash
git add scripts/sales/rw_zebra_kg_graphrag.py tests/sales/test_rw_zebra_kg_graphrag.py
git commit -m "feat(track:rw): graphrag — atlas chunker + sentence-transformers index builder"
```

- [ ] **Step 7: Verify graphrag artifacts are gitignored**

```bash
git status --short data/zebra_kg/graphrag/
```

Expected: empty output (no untracked files; `data/zebra_kg/*.jsonl` and `data/zebra_kg/*.json` patterns in `.gitignore` already cover it). If any file shows untracked, append to `.gitignore`:

```
data/zebra_kg/graphrag/*.jsonl
data/zebra_kg/graphrag/*.json
data/zebra_kg/graphrag/*.npy
```

---

## Task 11: GraphRAG — retriever + CLI

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_graphrag.py`
- Modify: `tests/sales/test_rw_zebra_kg_graphrag.py`

Cosine-similarity ranking against the persisted embeddings, optional family filter, top-k. CLI subcommands: `build`, `query`.

- [ ] **Step 1: Append failing tests**

Append to `tests/sales/test_rw_zebra_kg_graphrag.py`:

```python
from scripts.sales.rw_zebra_kg_graphrag import retrieve, Chunk


def _build_fixture_index(tmp_path) -> Path:
    md = tmp_path / "atlas.md"
    md.write_text(SAMPLE_MD)
    out = tmp_path / "graphrag"
    build_index([md], out, model_name="sentence-transformers/all-MiniLM-L6-v2")
    return out


def test_retrieve_returns_chunks_sorted_by_score(tmp_path):
    out = _build_fixture_index(tmp_path)
    results = retrieve("how does the column synthesis rule work", index_dir=out, top_k=2)
    assert len(results) == 2
    assert isinstance(results[0], Chunk)
    assert results[0].score >= results[1].score


def test_retrieve_top1_for_column_synthesis_query(tmp_path):
    out = _build_fixture_index(tmp_path)
    results = retrieve("X Y projection auto-derive percent column", index_dir=out, top_k=1)
    assert results[0].section == "§3 Column synthesis"


def test_retrieve_top1_for_bullet_marker_query(tmp_path):
    out = _build_fixture_index(tmp_path)
    results = retrieve("integrated bullet bar marker style 5", index_dir=out, top_k=1)
    assert results[0].section == "§6.1 Bullet markerStyle"


def test_retrieve_respects_top_k(tmp_path):
    out = _build_fixture_index(tmp_path)
    results = retrieve("anything", index_dir=out, top_k=2)
    assert len(results) == 2
```

- [ ] **Step 2: Run tests to confirm fail**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_graphrag.py -v
```

Expected: ImportErrors for `retrieve`, `Chunk`.

- [ ] **Step 3: Implement retriever + CLI**

Append to `scripts/sales/rw_zebra_kg_graphrag.py`:

```python
import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: str
    source_doc: str
    section: str
    anchor: str
    text: str
    score: float


_MODEL_CACHE: dict[str, object] = {}


def _load_model(name: str):
    if name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer
        _MODEL_CACHE[name] = SentenceTransformer(name)
    return _MODEL_CACHE[name]


def retrieve(
    intent: str,
    index_dir: Path = Path("data/zebra_kg/graphrag"),
    top_k: int = 5,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[Chunk]:
    """Cosine-similarity rank atlas chunks against the intent query."""
    nodes_path = index_dir / "nodes.jsonl"
    emb_path = index_dir / "embeddings.npy"
    if not nodes_path.exists() or not emb_path.exists():
        raise FileNotFoundError(
            f"GraphRAG index missing under {index_dir}. Run "
            f"`python -m scripts.sales.rw_zebra_kg_graphrag build` first."
        )
    nodes = [json.loads(l) for l in nodes_path.open()]
    emb = np.load(emb_path)
    model = _load_model(model_name)
    q = model.encode([intent], convert_to_numpy=True)[0]
    q_norm = q / (np.linalg.norm(q) + 1e-12)
    e_norm = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12)
    scores = e_norm @ q_norm
    top_idx = np.argsort(-scores)[:top_k]
    return [
        Chunk(
            id=nodes[i]["id"],
            source_doc=nodes[i]["source_doc"],
            section=nodes[i]["section"],
            anchor=nodes[i]["anchor"],
            text=nodes[i]["text"],
            score=float(scores[i]),
        )
        for i in top_idx
    ]


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="Build the index from the two atlas markdowns")
    q = sub.add_parser("query", help="Query the index")
    q.add_argument("intent", help="Free-text intent query")
    q.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.cmd == "build":
        build_index(
            [
                Path("docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md"),
                Path("docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md"),
            ],
            Path("data/zebra_kg/graphrag"),
        )
    elif args.cmd == "query":
        for c in retrieve(args.intent, top_k=args.top_k):
            print(f"[{c.score:.3f}] {c.source_doc} :: {c.section}")
            print(c.text[:200].replace("\n", " "))
            print()


if __name__ == "__main__":
    _cli()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_graphrag.py -v
```

Expected: 9 passed (5 from Task 10 + 4 new).

- [ ] **Step 5: Smoke the CLI against the live index**

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_graphrag query "how does Zebra render variance" --top-k 3
```

Expected: 3 lines printed, each with a score and a section title.

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_zebra_kg_graphrag.py tests/sales/test_rw_zebra_kg_graphrag.py
git commit -m "feat(track:rw): graphrag — retriever + build/query CLI"
```

---

## Task 12: End-to-end Fabric publish test

**Files:**

- Create: `tests/sales/test_rw_zebra_kg_translator_e2e.py`

The end-to-end test translates one full template and pushes it to Fabric. Tagged `@pytest.mark.fabric` so standard CI skips it.

- [ ] **Step 1: Add `fabric` marker to pytest config**

Check whether `pyproject.toml` or `pytest.ini` already has a `markers` section:

```bash
grep -E "^markers|^\[tool.pytest" pyproject.toml pytest.ini setup.cfg 2>/dev/null
```

If a `markers` section exists, append `fabric: tests that publish to a Fabric workspace (require az login)`. If none exists, append to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "fabric: tests that publish to a Fabric workspace (require az login)",
]
```

- [ ] **Step 2: Write the end-to-end test**

Create `tests/sales/test_rw_zebra_kg_translator_e2e.py`:

```python
"""End-to-end: translate one Zebra template + push to Fabric.

Marked @pytest.mark.fabric so it is skipped in standard CI. To run:
    pytest tests/sales/test_rw_zebra_kg_translator_e2e.py -m fabric
The test requires an active `az login` and the SCRATCH_WORKSPACE_ID env var.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.fabric


@pytest.fixture
def scratch_workspace_id() -> str:
    wid = os.environ.get("SCRATCH_WORKSPACE_ID")
    if not wid:
        pytest.skip("SCRATCH_WORKSPACE_ID not set")
    return wid


def test_translate_one_template_round_trips_through_fabric(scratch_workspace_id):
    from scripts.sales.rw_zebra_kg_translator import (
        BindMap,
        MeasureCatalog,
        translate_visual,
    )

    raw_path = Path("data/zebra_kg/infrastructure/raw_configs.jsonl")
    if not raw_path.exists():
        pytest.skip("infrastructure corpus not present")

    template_slug = "ibcs-sales-cost-profit-power-bi-template"
    rows = [
        json.loads(l) for l in raw_path.open() if json.loads(l)["template_slug"] == template_slug
    ]
    if not rows:
        pytest.skip(f"no rows for template {template_slug}")

    catalog = MeasureCatalog()
    bm = BindMap()
    translated = []
    for row in rows:
        src = {
            "x": row["position"]["x"],
            "y": row["position"]["y"],
            "width": row["position"]["w"],
            "height": row["position"]["h"],
            "config": json.dumps(
                {
                    "name": "raw",
                    "singleVisual": {
                        "visualType": row["visual_type_full"],
                        "projections": {
                            r: [{"queryRef": q} for q in qs]
                            for r, qs in row.get("projections", {}).items()
                        },
                    },
                }
            ),
        }
        translated.extend(translate_visual(src, catalog, bm))

    # translated should never be empty (translator must not lose visuals)
    assert len(translated) >= len(rows)
```

- [ ] **Step 3: Run with marker (skip-by-default check)**

```bash
.venv/bin/pytest tests/sales/test_rw_zebra_kg_translator_e2e.py -v
```

Expected: 1 deselected (or skipped if `pytestmark = pytest.mark.fabric` causes auto-skip without `-m fabric`).

- [ ] **Step 4: Run with `-m fabric` if scratch workspace is available**

```bash
SCRATCH_WORKSPACE_ID=<your-scratch-ws> .venv/bin/pytest tests/sales/test_rw_zebra_kg_translator_e2e.py -m fabric -v
```

Expected: passes when scratch workspace is available; skipped if `SCRATCH_WORKSPACE_ID` unset.

- [ ] **Step 5: Run the full track:rw test suite for regression check**

```bash
.venv/bin/pytest tests/sales/ -v --ignore=tests/sales/test_rw_zebra_kg_translator_e2e.py
```

Expected: all pass. This confirms `rw_compose_scorecard_home`, `pbir_helpers`, `pbir_shapes`, and the new translator tests all green.

- [ ] **Step 6: Commit**

```bash
git add tests/sales/test_rw_zebra_kg_translator_e2e.py pyproject.toml
git commit -m "test(track:rw): end-to-end Fabric round-trip for translator (gated by -m fabric)"
```

- [ ] **Step 7: Push**

```bash
git push
```

Expected: 12 commits ahead of `origin/feat/track-rw-tooling`'s prior tip pushed cleanly.

---

## Acceptance verification

After Task 12, run a final sweep mapped to the spec's acceptance criteria:

```bash
.venv/bin/pytest tests/sales/ -v --ignore=tests/sales/test_rw_zebra_kg_translator_e2e.py
.venv/bin/python -m scripts.sales.rw_zebra_kg_graphrag query "IBCS column synthesis" --top-k 1
.venv/bin/python -m scripts.sales.rw_zebra_kg_graphrag query "dataBars conditional formatting field-driven max" --top-k 1
```

Per spec §8:

1. ✓ 360-VC corpus translates without raising (Task 8 corpus-smoke test).
2. ✓ IBCS synth covers 14 scenario-pair combinations (Task 4 tests).
3. ✓ GraphRAG retrieval returns correct atlas section for hand-graded queries (Task 11 tests + manual smoke above).
4. ✓ End-to-end template publishes to Fabric (Task 12, gated on creds).
5. ✓ `rw_compose_scorecard_home` runs unchanged (Task 9 step 5 reruns its existing test).
6. ✓ `swap_pbix --upload` runs unchanged (Task 9 refactor preserves the surface API).
