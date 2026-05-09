# Zebra BI Knowledge Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing Zebra BI visual graph with a parallel data-model graph (DAX measures, tables, columns, relationships, style tokens) and an RW binding overlay, so RW VP Ops styling/measure replication is driven by structured data instead of prose.

**Architecture:** Four new scripts under `scripts/sales/rw_zebra_kg_*.py`. Datamodel layer uses `pbixray` (pure-Python PBIX binary parser). Style tokens reuse the existing `rw_zebra_template_miner.py` Layout helpers. Binding overlay parses `RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md` tables and reuses `rw_inventory_measures.fetch_measures_by_table()` for the live RW semantic-model side. Query CLI reads both the existing `analysis/` graph (visual side) and new `data/zebra_kg/` graph (datamodel side) for unified queries.

**Tech Stack:** Python 3.12, stdlib (`zipfile`, `json`, `csv`, `re`, `argparse`, `dataclasses`, `pathlib`), `pbixray>=0.3` (new), `pytest` (existing). No pandas, no Spark.

**Spec:** `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`

**Existing artifacts to reuse:**

- `scripts/sales/rw_zebra_template_miner.py` — already mines visuals/roles/textboxes from PBIX `Report/Layout`; wrote `analysis/graph_nodes.jsonl` (2,438 nodes), `analysis/graph_edges.jsonl` (6,209 edges), `analysis/visual_inventory.csv` (1,729 rows)
- `scripts/sales/rw_inventory_measures.py` — `fetch_measures_by_table()` returns `{table: [measure_names]}` from the deployed RW semantic model via Fabric REST
- `~/Downloads/rw-zebra-bi-template-research-20260509/files/` — 20 Zebra PBIX zips (input)
- `~/Downloads/rw-zebra-bi-template-research-20260509/analysis/` — existing visual-side outputs (input for join)
- `docs/sales/RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md` — prose RW bindings (input for binding overlay)

**Output layout (in repo):**

```
data/zebra_kg/                    <- new (mostly gitignored, README tracked)
  nodes_datamodel.jsonl
  edges_datamodel.jsonl
  measure_catalog.csv
  style_tokens.json
  README.md                        <- tracked
data/zebra_kg_rw/                 <- new (mostly gitignored, README tracked)
  bindings.jsonl
  rw_targets.csv
  README.md                        <- tracked
docs/sales/RW_ZEBRA_KG_INDEX.md   <- tracked
scripts/sales/rw_zebra_kg_datamodel.py   <- new
scripts/sales/rw_zebra_kg_tokens.py      <- new
scripts/sales/rw_zebra_kg_bind.py        <- new
scripts/sales/rw_zebra_kg_query.py       <- new
tests/sales/test_rw_zebra_kg_datamodel.py   <- new
tests/sales/test_rw_zebra_kg_tokens.py      <- new
tests/sales/test_rw_zebra_kg_bind.py        <- new
tests/sales/test_rw_zebra_kg_query.py       <- new
tests/sales/fixtures/zebra_kg_datamodel_stub.py   <- new (factory for test stubs)
```

**Conventions to honour (from existing track:rw code):**

- Stdlib + minimal deps; no pandas
- Dataclasses for internal models, `@dataclass(frozen=True)` for value objects
- `argparse` with one CLI per script, exposed via `if __name__ == "__main__": main()`
- Helpers prefixed `_` (private module-level)
- Tests under `tests/sales/test_<module>.py`, fixtures under `tests/sales/fixtures/`
- Ruff line-length 100, py312 target
- Run tests with `python3 -m pytest tests/sales/test_<module>.py -v`

---

## Task 1: Setup — dependency, gitignore, data scaffolding

**Files:**

- Modify: `requirements.txt`
- Modify: `.gitignore`
- Create: `data/zebra_kg/README.md`
- Create: `data/zebra_kg_rw/README.md`

- [ ] **Step 1: Add `pbixray` to `requirements.txt`**

Append this line to `/Users/test/code/apps/sales-ops-copilot-rw/requirements.txt`:

```
pbixray>=0.3.4
```

- [ ] **Step 2: Install the dependency**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
source .venv/bin/activate
pip install 'pbixray>=0.3.4'
```

Expected: package installs, `pip show pbixray` returns version >= 0.3.4.

- [ ] **Step 3: Verify pbixray opens a real Zebra PBIX**

Run (one-shot smoke):

```bash
python3 - <<'EOF'
from pbixray import PBIXRay
p = PBIXRay("/Users/test/Downloads/rw-zebra-bi-template-research-20260509/pbix-test/sales-funnel-power-bi-template__sales-pipeline-crm-template__Zebra BI - CRM Sales pipeline demo v2.pbix")
print("tables:", len(p.tables))
print("measures:", len(p.dax_measures))
print("relationships:", len(p.relationships))
EOF
```

Expected: prints non-zero counts for tables / measures / relationships. If it fails with a parser error, capture the error and stop — pbixray version may need bumping.

- [ ] **Step 4: Update `.gitignore`**

Append to `/Users/test/code/apps/sales-ops-copilot-rw/.gitignore`:

```
# track:rw — zebra KG derived artifacts (keep README, ignore generated)
data/zebra_kg/*.jsonl
data/zebra_kg/*.csv
data/zebra_kg/*.json
data/zebra_kg_rw/*.jsonl
data/zebra_kg_rw/*.csv
!data/zebra_kg/README.md
!data/zebra_kg_rw/README.md
```

- [ ] **Step 5: Create the data scaffolding READMEs**

Create `/Users/test/code/apps/sales-ops-copilot-rw/data/zebra_kg/README.md` with:

````markdown
# data/zebra_kg/

Generated artifacts from the Zebra BI knowledge-graph extraction.
Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`.

## Files

- `nodes_datamodel.jsonl` — Measure, Table, Column, Relationship, Scenario, StyleToken nodes
- `edges_datamodel.jsonl` — depends_on, related_to, scenario_of, resolves_to, uses_token
- `measure_catalog.csv` — flat catalog of every DAX measure across the 20 PBIX templates
- `style_tokens.json` — deduped style token catalog with usage counts and canonical flags

All four files are gitignored. Regenerate with:

```bash
python3 -m scripts.sales.rw_zebra_kg_datamodel \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \
  --out-dir data/zebra_kg

python3 -m scripts.sales.rw_zebra_kg_tokens \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg
```
````

Create `/Users/test/code/apps/sales-ops-copilot-rw/data/zebra_kg_rw/README.md` with:

```markdown
# data/zebra_kg_rw/

RW binding overlay — links Zebra template elements to RW tabs/fields/measures.
Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`.

## Files

- `bindings.jsonl` — RWBinding nodes with status: bound | unbound | needs_measure
- `rw_targets.csv` — flat view: RW tab × element × source visual_id × status

Both gitignored. Regenerate with:

`python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw`
```

- [ ] **Step 6: Commit**

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
git add requirements.txt .gitignore data/zebra_kg/README.md data/zebra_kg_rw/README.md
git commit -m "chore(track:rw): scaffold zebra_kg data dirs and add pbixray dep"
```

---

## Task 2: PBIX DataModel reader — pure parser, no I/O coupling

Goal: a `_load_datamodel(pbix_path: Path) -> DataModel` function that returns a structured Python object. Separating this from emission lets us unit-test against stubs without binary PBIX files.

**Files:**

- Create: `scripts/sales/rw_zebra_kg_datamodel.py`
- Create: `tests/sales/test_rw_zebra_kg_datamodel.py`
- Create: `tests/sales/fixtures/zebra_kg_datamodel_stub.py`

- [ ] **Step 1: Write the failing test for the data model dataclasses**

Create `tests/sales/fixtures/zebra_kg_datamodel_stub.py`:

```python
"""Pure-Python stub mimicking the surface of pbixray.PBIXRay we depend on.

Lets us unit-test the shaping layer without binary PBIX files.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StubPBIXRay:
    """Mimics the attributes of pbixray.PBIXRay used by rw_zebra_kg_datamodel."""

    tables: list[str]
    dax_measures: list[dict]        # rows: TableName, Name, Expression, FormatString
    relationships: list[dict]       # rows: FromTable, FromColumn, ToTable, ToColumn,
                                    #       Cardinality, CrossFilteringBehavior, IsActive
    schema: list[dict]              # rows: TableName, ColumnName, PandasDataType


def make_stub_sales_funnel() -> StubPBIXRay:
    return StubPBIXRay(
        tables=["f_opp", "d_stage"],
        dax_measures=[
            {
                "TableName": "f_opp",
                "Name": "Stage Forward Pct",
                "Expression": "DIVIDE([Forward Moves], [Total Transitions])",
                "FormatString": "0.0%",
            },
            {
                "TableName": "f_opp",
                "Name": "Forward Moves",
                "Expression": "CALCULATE(COUNTROWS(f_opp), f_opp[Direction]=\"forward\")",
                "FormatString": "#,##0",
            },
            {
                "TableName": "f_opp",
                "Name": "Total Transitions",
                "Expression": "COUNTROWS(f_opp)",
                "FormatString": "#,##0",
            },
            {
                "TableName": "f_opp",
                "Name": "ARR PY",
                "Expression": "CALCULATE([ARR], SAMEPERIODLASTYEAR(d_date[Date]))",
                "FormatString": "#,##0",
            },
        ],
        relationships=[
            {
                "FromTableName": "f_opp",
                "FromColumnName": "StageId",
                "ToTableName": "d_stage",
                "ToColumnName": "Id",
                "Cardinality": "M:1",
                "CrossFilteringBehavior": "OneDirection",
                "IsActive": True,
            }
        ],
        schema=[
            {"TableName": "f_opp", "ColumnName": "StageId", "PandasDataType": "string"},
            {"TableName": "f_opp", "ColumnName": "Direction", "PandasDataType": "string"},
            {"TableName": "d_stage", "ColumnName": "Id", "PandasDataType": "string"},
            {"TableName": "d_stage", "ColumnName": "Name", "PandasDataType": "string"},
        ],
    )
```

Create `tests/sales/test_rw_zebra_kg_datamodel.py`:

```python
"""Tests for scripts.sales.rw_zebra_kg_datamodel — pure shaping layer."""

from __future__ import annotations

import pytest

from scripts.sales import rw_zebra_kg_datamodel as kg
from tests.sales.fixtures.zebra_kg_datamodel_stub import make_stub_sales_funnel


def test_shape_returns_datamodel_with_expected_counts():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    assert dm.template_slug == "sales-funnel"
    assert {t.name for t in dm.tables} == {"f_opp", "d_stage"}
    assert {m.name for m in dm.measures} == {
        "Stage Forward Pct",
        "Forward Moves",
        "Total Transitions",
        "ARR PY",
    }
    assert len(dm.columns) == 4
    assert len(dm.relationships) == 1


def test_relationship_carries_cardinality_and_active():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    rel = dm.relationships[0]
    assert rel.from_table == "f_opp"
    assert rel.from_col == "StageId"
    assert rel.to_table == "d_stage"
    assert rel.to_col == "Id"
    assert rel.cardinality == "many_to_one"
    assert rel.cross_filter == "single"
    assert rel.active is True


def test_measure_carries_table_and_format():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")

    m = next(m for m in dm.measures if m.name == "Stage Forward Pct")
    assert m.table == "f_opp"
    assert m.format_string == "0.0%"
    assert m.expression.startswith("DIVIDE(")
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
source .venv/bin/activate
python3 -m pytest tests/sales/test_rw_zebra_kg_datamodel.py -v
```

Expected: ImportError for `scripts.sales.rw_zebra_kg_datamodel` or AttributeError for `shape_datamodel`.

- [ ] **Step 3: Create the module with dataclasses + shaping function**

Create `scripts/sales/rw_zebra_kg_datamodel.py`:

```python
"""Extract DAX measures, tables, columns, relationships from Zebra BI PBIX
templates and emit a parallel data-model graph alongside the existing
visual-side graph (which is produced by rw_zebra_template_miner.py).

Pipeline:
    PBIX zip --(pbixray)--> raw rows --(shape)--> DataModel dataclasses
        --(emit)--> nodes_datamodel.jsonl + edges_datamodel.jsonl + measure_catalog.csv

Usage:
    python3 -m scripts.sales.rw_zebra_kg_datamodel \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \\
      --out-dir data/zebra_kg
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------- value objects ----------


@dataclass(frozen=True)
class Table:
    name: str


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    data_type: str


@dataclass(frozen=True)
class Measure:
    name: str
    table: str
    expression: str
    format_string: str
    scenario: str | None = None       # "AC" | "PY" | "PL" | "FC" | None
    is_variance: bool = False


@dataclass(frozen=True)
class Relationship:
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    cardinality: str       # "many_to_one" | "one_to_many" | "one_to_one" | "many_to_many"
    cross_filter: str      # "single" | "both"
    active: bool


@dataclass(frozen=True)
class DataModel:
    template_slug: str
    tables: list[Table] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


# ---------- shaping ----------

_CARDINALITY_MAP = {
    "M:1": "many_to_one",
    "1:M": "one_to_many",
    "1:1": "one_to_one",
    "M:M": "many_to_many",
}

_CROSSFILTER_MAP = {
    "OneDirection": "single",
    "BothDirections": "both",
    "Automatic": "single",  # PBIX default for M:1 — treat as single
}


def shape_datamodel(pbix: Any, template_slug: str) -> DataModel:
    """Translate a pbixray.PBIXRay-shaped object into our DataModel dataclasses.

    `pbix` must expose: .tables (list[str]), .dax_measures (list[dict]),
    .relationships (list[dict]), .schema (list[dict]). Real pbixray and the
    test stub both satisfy this.
    """
    tables = [Table(name=t) for t in pbix.tables]

    columns = [
        Column(
            table=row["TableName"],
            name=row["ColumnName"],
            data_type=row.get("PandasDataType", "unknown"),
        )
        for row in pbix.schema
    ]

    measures = [
        Measure(
            name=row["Name"],
            table=row["TableName"],
            expression=row.get("Expression", ""),
            format_string=row.get("FormatString", ""),
        )
        for row in pbix.dax_measures
    ]

    relationships = [
        Relationship(
            from_table=row["FromTableName"],
            from_col=row["FromColumnName"],
            to_table=row["ToTableName"],
            to_col=row["ToColumnName"],
            cardinality=_CARDINALITY_MAP.get(row["Cardinality"], "unknown"),
            cross_filter=_CROSSFILTER_MAP.get(
                row["CrossFilteringBehavior"], "single"
            ),
            active=bool(row.get("IsActive", True)),
        )
        for row in pbix.relationships
    ]

    return DataModel(
        template_slug=template_slug,
        tables=tables,
        columns=columns,
        measures=measures,
        relationships=relationships,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, required=True,
                        help="Dir of Zebra PBIX files")
    parser.add_argument("--analysis-dir", type=Path, required=True,
                        help="Dir of existing visual-side miner output")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="Output dir for new graph artifacts")
    args = parser.parse_args()
    # Emit logic added in Task 3.
    raise SystemExit("emit not yet wired — see Task 3")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
source .venv/bin/activate
python3 -m pytest tests/sales/test_rw_zebra_kg_datamodel.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Add an integration test against a real PBIX**

Append to `tests/sales/test_rw_zebra_kg_datamodel.py`:

```python
ZEBRA_PBIX = Path(
    "/Users/test/Downloads/rw-zebra-bi-template-research-20260509/pbix-test/"
    "sales-funnel-power-bi-template__sales-pipeline-crm-template__"
    "Zebra BI - CRM Sales pipeline demo v2.pbix"
)


@pytest.mark.skipif(
    not ZEBRA_PBIX.exists(),
    reason="real Zebra PBIX corpus not present (download dump missing)",
)
def test_shape_real_pbix_smoke():
    """Sanity check pbixray + shape_datamodel against a real Zebra PBIX."""
    from pbixray import PBIXRay  # local import keeps stub-only tests cheap

    raw = PBIXRay(str(ZEBRA_PBIX))
    dm = kg.shape_datamodel(raw, template_slug="sales-funnel")

    assert len(dm.tables) > 0
    assert len(dm.measures) > 0
    assert all(m.table for m in dm.measures)
    assert all(r.cardinality in {
        "many_to_one", "one_to_many", "one_to_one", "many_to_many", "unknown"
    } for r in dm.relationships)
```

You also need `from pathlib import Path` and `import pytest` already imported — verify they're at the top; add `from pathlib import Path` if missing.

- [ ] **Step 6: Run the integration smoke**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_datamodel.py -v
```

Expected: 4 passed (3 stub + 1 real PBIX). If real-PBIX test fails with a pbixray error, capture the trace and stop — may need a different PBIX file or pbixray bump.

- [ ] **Step 7: Commit**

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
git add scripts/sales/rw_zebra_kg_datamodel.py tests/sales/test_rw_zebra_kg_datamodel.py tests/sales/fixtures/zebra_kg_datamodel_stub.py
git commit -m "feat(track:rw): zebra_kg datamodel shaping layer + pbixray smoke"
```

---

## Task 3: Datamodel emission — JSONL nodes/edges, measure catalog, scenario heuristic

Goal: take the `DataModel` from Task 2 and emit nodes/edges in the spec schema. Includes a small scenario classifier (AC/PY/PL/FC) based on measure-name regex.

**Files:**

- Modify: `scripts/sales/rw_zebra_kg_datamodel.py`
- Modify: `tests/sales/test_rw_zebra_kg_datamodel.py`

- [ ] **Step 1: Write failing tests for scenario classifier and node IDs**

Append to `tests/sales/test_rw_zebra_kg_datamodel.py`:

```python
def test_classify_scenario_recognises_py_pl_fc_ac():
    classify = kg.classify_scenario
    assert classify("ARR PY") == "PY"
    assert classify("Sales Plan") == "PL"
    assert classify("Forecast FY") == "FC"
    assert classify("Stage Forward Pct") == "AC"
    assert classify("Total Transitions") == "AC"


def test_classify_variance_flags_var_diff_delta():
    is_var = kg.is_variance
    assert is_var("ARR vs PY") is True
    assert is_var("Var % vs Plan") is True
    assert is_var("Delta ARR") is True
    assert is_var("Total Transitions") is False


def test_node_ids_are_stable_and_namespaced():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    nodes = list(kg.iter_nodes(dm))
    ids = {n["id"] for n in nodes}

    assert "tbl:sales-funnel:f_opp" in ids
    assert "msr:sales-funnel:Stage Forward Pct" in ids
    assert "col:sales-funnel:f_opp:StageId" in ids
    assert "rel:sales-funnel:f_opp.StageId->d_stage.Id" in ids
    # Scenario nodes — emitted once per template, only for scenarios actually used
    assert "scn:PY" in ids


def test_edges_link_measure_to_dependent_measure():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    edges = list(kg.iter_edges(dm))

    # Stage Forward Pct DAX references [Forward Moves] and [Total Transitions]
    deps = {
        (e["src"], e["dst"]) for e in edges
        if e["type"] == "depends_on"
        and e["src"] == "msr:sales-funnel:Stage Forward Pct"
    }
    assert (
        "msr:sales-funnel:Stage Forward Pct",
        "msr:sales-funnel:Forward Moves",
    ) in deps
    assert (
        "msr:sales-funnel:Stage Forward Pct",
        "msr:sales-funnel:Total Transitions",
    ) in deps


def test_edges_include_relationship_and_scenario_links():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    edges = list(kg.iter_edges(dm))
    edge_types = {e["type"] for e in edges}

    assert "related_to" in edge_types
    assert "scenario_of" in edge_types  # ARR PY measure → scn:PY


def test_measure_catalog_rows_have_dedupe_keys():
    pbix = make_stub_sales_funnel()
    dm = kg.shape_datamodel(pbix, template_slug="sales-funnel")
    rows = list(kg.measure_catalog_rows(dm))
    assert len(rows) == 4
    keys = {(r["template_slug"], r["table"], r["name"]) for r in rows}
    assert ("sales-funnel", "f_opp", "Stage Forward Pct") in keys
    assert all("expression" in r and "format_string" in r for r in rows)
```

- [ ] **Step 2: Run the new tests — confirm they fail**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_datamodel.py -v -k "classify or node_ids or edges or catalog"
```

Expected: 5 failures with `AttributeError: module 'rw_zebra_kg_datamodel' has no attribute 'classify_scenario'` (etc).

- [ ] **Step 3: Implement classifiers, node iteration, edge iteration, catalog**

Append to `scripts/sales/rw_zebra_kg_datamodel.py` (above `def main()`):

```python
# ---------- scenario / variance classification ----------

# Scenario tokens are matched as whole words anywhere in the measure name.
# Order matters: PY before AC because plain measures default to AC.
_SCENARIO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PY", re.compile(r"\b(PY|Prior Year|Last Year|LY|SPLY)\b", re.IGNORECASE)),
    ("PL", re.compile(r"\b(Plan|Budget|BU|Target)\b", re.IGNORECASE)),
    ("FC", re.compile(r"\b(Forecast|FC|Estimate|EST)\b", re.IGNORECASE)),
]

_VARIANCE_PATTERN = re.compile(
    r"\b(vs|var|variance|delta|diff|difference)\b", re.IGNORECASE
)

# Inside a DAX expression, `[Foo Bar]` is a measure or column reference.
# We treat every match as a potential measure dependency and resolve later
# against the template's measure list (column refs without table-qualifier
# get filtered out at edge-emit time).
_DAX_MEASURE_REF = re.compile(r"\[([^\]]+)\]")


def classify_scenario(measure_name: str) -> str:
    """Return 'AC' (default) or 'PY'/'PL'/'FC' if name matches a scenario token."""
    for code, pat in _SCENARIO_PATTERNS:
        if pat.search(measure_name):
            return code
    return "AC"


def is_variance(measure_name: str) -> bool:
    return bool(_VARIANCE_PATTERN.search(measure_name))


# ---------- node / edge emission ----------


def _msr_id(slug: str, name: str) -> str:
    return f"msr:{slug}:{name}"


def _tbl_id(slug: str, name: str) -> str:
    return f"tbl:{slug}:{name}"


def _col_id(slug: str, table: str, name: str) -> str:
    return f"col:{slug}:{table}:{name}"


def _rel_id(slug: str, rel: Relationship) -> str:
    return (
        f"rel:{slug}:{rel.from_table}.{rel.from_col}->"
        f"{rel.to_table}.{rel.to_col}"
    )


def iter_nodes(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    used_scenarios: set[str] = set()

    for t in dm.tables:
        yield {"id": _tbl_id(slug, t.name), "type": "Table", "name": t.name,
               "template": slug}

    for c in dm.columns:
        yield {
            "id": _col_id(slug, c.table, c.name), "type": "Column",
            "table": c.table, "name": c.name, "data_type": c.data_type,
            "template": slug,
        }

    for m in dm.measures:
        scenario = classify_scenario(m.name)
        used_scenarios.add(scenario)
        yield {
            "id": _msr_id(slug, m.name), "type": "Measure",
            "name": m.name, "table": m.table, "expression": m.expression,
            "format_string": m.format_string, "scenario": scenario,
            "is_variance": is_variance(m.name), "template": slug,
        }

    for r in dm.relationships:
        yield {
            "id": _rel_id(slug, r), "type": "Relationship",
            "from": _tbl_id(slug, r.from_table), "to": _tbl_id(slug, r.to_table),
            "from_col": r.from_col, "to_col": r.to_col,
            "cardinality": r.cardinality, "cross_filter": r.cross_filter,
            "active": r.active, "template": slug,
        }

    # Scenario nodes are global (not template-scoped) — emit once per scenario
    # actually used. The iteration here is per-template, so emit-and-dedupe at
    # the writer layer.
    for scn in sorted(used_scenarios):
        yield {"id": f"scn:{scn}", "type": "Scenario", "code": scn,
               "ibcs_glyph": _IBCS_GLYPH.get(scn, "")}


_IBCS_GLYPH = {"AC": "solid", "PY": "outlined", "PL": "hatched", "FC": "dotted"}


def iter_edges(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    measure_names = {m.name for m in dm.measures}

    for m in dm.measures:
        msr = _msr_id(slug, m.name)
        # depends_on edges
        for ref in _DAX_MEASURE_REF.findall(m.expression):
            if ref in measure_names and ref != m.name:
                yield {
                    "src": msr, "dst": _msr_id(slug, ref),
                    "type": "depends_on", "props": {},
                }
        # scenario_of edge
        scn = classify_scenario(m.name)
        yield {"src": msr, "dst": f"scn:{scn}", "type": "scenario_of", "props": {}}

    for r in dm.relationships:
        yield {
            "src": _tbl_id(slug, r.from_table),
            "dst": _tbl_id(slug, r.to_table),
            "type": "related_to",
            "props": {
                "cardinality": r.cardinality,
                "cross_filter": r.cross_filter,
                "active": r.active,
                "from_col": r.from_col,
                "to_col": r.to_col,
            },
        }


def measure_catalog_rows(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    for m in dm.measures:
        yield {
            "template_slug": slug,
            "table": m.table,
            "name": m.name,
            "expression": m.expression,
            "format_string": m.format_string,
            "scenario": classify_scenario(m.name),
            "is_variance": is_variance(m.name),
        }


# ---------- writers ----------

def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            n += 1
    return n


def write_csv(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return 0
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return len(rows)


def template_slug_from_pbix(path: Path) -> str:
    """Match the slug convention used by rw_zebra_template_miner.py."""
    return path.stem.split("__", 1)[0]
```

- [ ] **Step 4: Replace `main()` with a real driver**

Replace the existing `def main()` body in `scripts/sales/rw_zebra_kg_datamodel.py`:

```python
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--analysis-dir", type=Path, required=True,
                        help="Dir of existing visual-side miner output (read-only)")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser()
    out_dir = args.out_dir.expanduser()
    errors_log = out_dir / "extract_errors.log"
    out_dir.mkdir(parents=True, exist_ok=True)
    errors_log.write_text("")  # truncate per run

    from pbixray import PBIXRay  # imported here so unit tests don't need it

    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    all_catalog: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()

    pbix_files = sorted(source_dir.glob("*.pbix"))
    for path in pbix_files:
        slug = template_slug_from_pbix(path)
        try:
            raw = PBIXRay(str(path))
            dm = shape_datamodel(raw, template_slug=slug)
        except Exception as exc:  # pbixray may raise many shapes
            with errors_log.open("a", encoding="utf-8") as fp:
                fp.write(f"{path.name}\t{type(exc).__name__}\t{exc}\n")
            continue

        for node in iter_nodes(dm):
            if node["id"] in seen_node_ids:
                continue
            seen_node_ids.add(node["id"])
            all_nodes.append(node)
        all_edges.extend(iter_edges(dm))
        all_catalog.extend(measure_catalog_rows(dm))

    n_nodes = write_jsonl(out_dir / "nodes_datamodel.jsonl", all_nodes)
    n_edges = write_jsonl(out_dir / "edges_datamodel.jsonl", all_edges)
    n_catalog = write_csv(out_dir / "measure_catalog.csv", all_catalog)

    print(f"templates: {len(pbix_files)}  nodes: {n_nodes}  "
          f"edges: {n_edges}  measures: {n_catalog}")
    print(f"errors logged: {errors_log}")


if __name__ == "__main__":
    main()
```

(Replace the existing `def main()` and `if __name__ == "__main__":` lines, leaving only this version.)

- [ ] **Step 5: Run all unit tests for this module**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
source .venv/bin/activate
python3 -m pytest tests/sales/test_rw_zebra_kg_datamodel.py -v
```

Expected: all tests pass (3 shape + 5 new + 1 integration smoke = 9).

- [ ] **Step 6: Run the script end-to-end against the real corpus**

Run:

```bash
python3 -m scripts.sales.rw_zebra_kg_datamodel \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \
  --out-dir data/zebra_kg
```

Expected stdout: `templates: 20  nodes: <large>  edges: <large>  measures: <large>` and an empty (or near-empty) `data/zebra_kg/extract_errors.log`. If error log is non-empty, inspect — list which PBIX failed and re-run the smoke from Task 1 Step 3 against that file to debug.

- [ ] **Step 7: Sanity-check the artifacts**

Run:

```bash
wc -l data/zebra_kg/nodes_datamodel.jsonl data/zebra_kg/edges_datamodel.jsonl
wc -l data/zebra_kg/measure_catalog.csv
head -3 data/zebra_kg/measure_catalog.csv
python3 -c "
import json, collections
nodes = [json.loads(l) for l in open('data/zebra_kg/nodes_datamodel.jsonl')]
print('node types:', collections.Counter(n['type'] for n in nodes))
edges = [json.loads(l) for l in open('data/zebra_kg/edges_datamodel.jsonl')]
print('edge types:', collections.Counter(e['type'] for e in edges))
"
```

Expected: node types include Measure / Table / Column / Relationship / Scenario; edge types include depends_on / related_to / scenario_of.

- [ ] **Step 8: Commit**

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
git add scripts/sales/rw_zebra_kg_datamodel.py tests/sales/test_rw_zebra_kg_datamodel.py
git commit -m "feat(track:rw): zebra_kg datamodel emission + scenario classifier"
```

---

## Task 4: Style token extraction

Goal: sweep `Report/Layout` from all 20 PBIX files, harvest color/font/border/padding/glyph values, dedupe, count usages, mark canonical tokens (usage_count > 50). Reuses helpers from `rw_zebra_template_miner.py`.

**Files:**

- Create: `scripts/sales/rw_zebra_kg_tokens.py`
- Create: `tests/sales/test_rw_zebra_kg_tokens.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sales/test_rw_zebra_kg_tokens.py`:

```python
"""Tests for scripts.sales.rw_zebra_kg_tokens — style token extraction."""

from __future__ import annotations

import json

from scripts.sales import rw_zebra_kg_tokens as tk


SAMPLE_VISUAL_OBJECTS = {
    "labels": [
        {
            "properties": {
                "color": {"solid": {"color": "#000000"}},
                "fontFamily": {"expr": {"Literal": {"Value": "'Arial'"}}},
                "fontSize": {"expr": {"Literal": {"Value": "10D"}}},
            }
        }
    ],
    "background": [
        {"properties": {"color": {"solid": {"color": "#FFFFFF"}}}}
    ],
    "border": [
        {
            "properties": {
                "color": {"solid": {"color": "#CCCCCC"}},
                "weight": {"expr": {"Literal": {"Value": "1D"}}},
            }
        }
    ],
}


def test_extract_tokens_from_visual_objects_yields_expected_kinds():
    tokens = list(tk.extract_tokens_from_objects(SAMPLE_VISUAL_OBJECTS))
    kinds = {t.kind for t in tokens}
    assert "color" in kinds
    assert "font" in kinds
    assert "border" in kinds


def test_color_token_normalises_hex_uppercase():
    tokens = list(tk.extract_tokens_from_objects(SAMPLE_VISUAL_OBJECTS))
    colors = [t.value for t in tokens if t.kind == "color"]
    assert "#000000" in colors
    assert "#FFFFFF" in colors
    assert "#CCCCCC" in colors


def test_dedupe_counts_usage_and_flags_canonical(tmp_path):
    rows = [
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#000000", purpose="labels"),
        tk.Token(kind="color", value="#FFFFFF", purpose="background"),
    ]
    deduped = tk.dedupe_tokens(rows, canonical_threshold=2)
    by_value = {t["value"]: t for t in deduped if t["kind"] == "color"}
    assert by_value["#000000"]["usage_count"] == 3
    assert by_value["#000000"]["canonical"] is True
    assert by_value["#FFFFFF"]["usage_count"] == 1
    assert by_value["#FFFFFF"]["canonical"] is False


def test_dedupe_is_deterministic(tmp_path):
    rows = [
        tk.Token(kind="color", value="#FFFFFF", purpose="bg"),
        tk.Token(kind="color", value="#000000", purpose="lbl"),
    ]
    a = tk.dedupe_tokens(rows, canonical_threshold=10)
    b = tk.dedupe_tokens(list(reversed(rows)), canonical_threshold=10)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
```

- [ ] **Step 2: Run tests — confirm they fail**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_tokens.py -v
```

Expected: ImportError for `scripts.sales.rw_zebra_kg_tokens`.

- [ ] **Step 3: Implement the tokens module**

Create `scripts/sales/rw_zebra_kg_tokens.py`:

```python
"""Sweep all PBIX Report/Layout files in the Zebra corpus, harvest style
tokens (color/font/border/padding), dedupe, count usages, mark canonical.

Output: data/zebra_kg/style_tokens.json with rows of:
    {kind, value, purpose, usage_count, canonical}

Deterministic: sorting by (kind, value, purpose) so `pytest` parity assertions
hold across runs.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_tokens \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --out-dir data/zebra_kg
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from scripts.sales.rw_zebra_template_miner import (
    iter_pbix_layouts,
    parse_config,
    sanitized_object_groups,
)

CANONICAL_THRESHOLD = 50  # spec §"flag canonical via threshold"


@dataclass(frozen=True)
class Token:
    kind: str       # color | font | border | padding | glyph
    value: str      # hex code | family name | px | size
    purpose: str    # the object group key (e.g. "labels", "background", "border")


_LITERAL_VALUE = re.compile(r"^'?(.*?)'?D?$")


def _literal(node: Any) -> str | None:
    """Extract a value from a Power BI expression literal node."""
    try:
        raw = node["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    m = _LITERAL_VALUE.match(str(raw))
    return m.group(1) if m else str(raw)


def _solid_color(node: Any) -> str | None:
    try:
        return str(node["solid"]["color"]).upper()
    except (KeyError, TypeError):
        return None


def extract_tokens_from_objects(objects: dict[str, list[dict[str, Any]]]) -> Iterable[Token]:
    """Yield Tokens for every styling property in a single visual's `objects` dict.

    `objects` is the parsed `objects` block from a visual's config — a mapping
    of object-group names (e.g. "labels", "background", "border") to a list of
    instances, each with a "properties" dict.
    """
    for group_name, instances in (objects or {}).items():
        for inst in instances:
            props = inst.get("properties") or {}
            for prop_name, prop_value in props.items():
                # Color
                color = _solid_color(prop_value) if isinstance(prop_value, dict) else None
                if color and re.fullmatch(r"#[0-9A-F]{6,8}", color):
                    yield Token(kind="color", value=color, purpose=group_name)
                    continue

                lit = _literal(prop_value) if isinstance(prop_value, dict) else None
                if lit is None:
                    continue

                pname = prop_name.lower()
                if "font" in pname and "family" in pname:
                    yield Token(kind="font", value=lit, purpose=f"{group_name}.family")
                elif "fontsize" in pname or "textsize" in pname:
                    yield Token(kind="font", value=f"{lit}px", purpose=f"{group_name}.size")
                elif "weight" in pname and group_name == "border":
                    yield Token(kind="border", value=f"{lit}px", purpose="border.weight")
                elif "padding" in pname:
                    yield Token(kind="padding", value=f"{lit}px", purpose=f"{group_name}.{prop_name}")


def dedupe_tokens(
    tokens: Iterable[Token], canonical_threshold: int = CANONICAL_THRESHOLD
) -> list[dict[str, Any]]:
    counter: Counter[Token] = Counter(tokens)
    rows = [
        {
            "kind": tok.kind,
            "value": tok.value,
            "purpose": tok.purpose,
            "usage_count": count,
            "canonical": count >= canonical_threshold,
        }
        for tok, count in counter.items()
    ]
    rows.sort(key=lambda r: (r["kind"], r["value"], r["purpose"]))
    return rows


def sweep_corpus(source_dir: Path) -> list[dict[str, Any]]:
    layouts = iter_pbix_layouts(source_dir)
    all_tokens: list[Token] = []
    for layout in layouts:
        for section in layout.layout.get("sections", []):
            for vc in section.get("visualContainers", []):
                cfg = parse_config(vc)
                # singleVisual lives at config["singleVisual"]
                single = cfg.get("singleVisual") or {}
                objects = single.get("objects") or {}
                # also visualContainerObjects (frame/background of container)
                vc_objects = cfg.get("visualContainerObjects") or {}
                all_tokens.extend(extract_tokens_from_objects(objects))
                all_tokens.extend(extract_tokens_from_objects(vc_objects))
                # cross-check sanitized_object_groups (drops license blobs)
                _ = sanitized_object_groups(single)
    return dedupe_tokens(all_tokens)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--canonical-threshold", type=int, default=CANONICAL_THRESHOLD)
    args = parser.parse_args()

    rows = sweep_corpus(args.source_dir.expanduser())
    out_path = args.out_dir.expanduser() / "style_tokens.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n")

    canonical = sum(1 for r in rows if r["canonical"])
    print(f"tokens: {len(rows)}  canonical: {canonical}  out: {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_tokens.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run the script end-to-end**

Run:

```bash
python3 -m scripts.sales.rw_zebra_kg_tokens \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg
```

Expected: prints non-zero `tokens:` and `canonical:` counts; `data/zebra_kg/style_tokens.json` exists and is valid JSON.

- [ ] **Step 6: Confirm determinism**

Run:

```bash
md5 data/zebra_kg/style_tokens.json
python3 -m scripts.sales.rw_zebra_kg_tokens \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg
md5 data/zebra_kg/style_tokens.json
```

Expected: both md5 hashes match (sweep is deterministic).

- [ ] **Step 7: Commit**

```bash
git add scripts/sales/rw_zebra_kg_tokens.py tests/sales/test_rw_zebra_kg_tokens.py
git commit -m "feat(track:rw): zebra_kg style token sweep"
```

---

## Task 5: RW binding overlay

Goal: parse the `## Exact elements to pull` section of `RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`, cross-reference each prescribed RW field against the deployed RW semantic model (via `rw_inventory_measures.fetch_measures_by_table()`), emit `bindings.jsonl` with status: `bound | unbound | needs_measure`.

**Files:**

- Create: `scripts/sales/rw_zebra_kg_bind.py`
- Create: `tests/sales/test_rw_zebra_kg_bind.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sales/test_rw_zebra_kg_bind.py`:

```python
"""Tests for scripts.sales.rw_zebra_kg_bind — RW binding overlay."""

from __future__ import annotations

from scripts.sales import rw_zebra_kg_bind as bd


SAMPLE_DOC = """
## Exact elements to pull

### 1. Stage Hygiene - Zebra BI Tables proof

Source: `sales-funnel-power-bi-template`, pages `Home 3`.

RW element:

- `Stage x Motion Hygiene` table with embedded bars and variance notation.

Bindings:

- Category: `f_stage_transition[from_stage_name]`
- Values:
  - `Stage Forward Pct (LE)`
  - `Stage Backward Pct (LE)`

### 2. VP Ops Scorecard - exception table, not RAG cards

Source: `sales-dashboard-power-bi-template`, page `Landing`.

RW element:

- VP Ops Scorecard top exception table.

Bindings:

- Values:
  - `ARR FQTD`
"""


def test_parse_extracts_sections_with_source_template_and_values():
    sections = bd.parse_element_map(SAMPLE_DOC)
    assert len(sections) == 2

    s1 = sections[0]
    assert s1.rw_tab == "Stage Hygiene"
    assert s1.rw_element == "Stage x Motion Hygiene"
    assert s1.source_template == "sales-funnel-power-bi-template"
    assert "Stage Forward Pct (LE)" in s1.rw_values
    assert "Stage Backward Pct (LE)" in s1.rw_values


def test_classify_status_marks_bound_when_measure_exists():
    rw_model = {"f_stage_transition": ["Stage Forward Pct (LE)"]}
    status = bd.classify_status("Stage Forward Pct (LE)", rw_model)
    assert status == "bound"


def test_classify_status_marks_needs_measure_when_absent():
    rw_model = {"f_opp": ["ARR FQTD"]}
    status = bd.classify_status("Stage Forward Pct (LE)", rw_model)
    assert status == "needs_measure"


def test_emit_bindings_yields_one_per_value(tmp_path):
    rw_model = {"f_stage_transition": ["Stage Forward Pct (LE)"]}
    sections = bd.parse_element_map(SAMPLE_DOC)
    rows = list(bd.emit_bindings(sections, rw_model))

    # 2 from section 1 + 1 from section 2 = 3 bindings
    assert len(rows) == 3
    statuses = {r["status"] for r in rows}
    assert "bound" in statuses
    assert "needs_measure" in statuses
    assert all(r["type"] == "RWBinding" for r in rows)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_bind.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the bind module**

Create `scripts/sales/rw_zebra_kg_bind.py`:

```python
"""Build the RW binding overlay from RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md.

Reads the prose element-map doc + the deployed RW semantic model (via
rw_inventory_measures.fetch_measures_by_table()) and emits per-RW-value
binding records with status: bound | unbound | needs_measure.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOC = REPO_ROOT / "docs/sales/RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md"

# Regex anchors over the markdown
_HEADING = re.compile(r"^### \d+\.\s*(.+?)\s*-\s*(.+?)\s*$", re.MULTILINE)
_SOURCE = re.compile(r"^Source:\s*`([^`]+)`", re.MULTILINE)
_RW_ELEMENT_LINE = re.compile(r"^- \s*`?([^`\n]+?)`?\s*(?:\.|\s*$)", re.MULTILINE)
_VALUES_BLOCK = re.compile(
    r"- Values:\s*\n((?:\s+- `[^`]+`\s*\n?)+)", re.MULTILINE
)
_VALUE_ITEM = re.compile(r"`([^`]+)`")


@dataclass
class ElementMapSection:
    rw_tab: str
    rw_element: str
    source_template: str
    rw_values: list[str] = field(default_factory=list)


def parse_element_map(text: str) -> list[ElementMapSection]:
    sections: list[ElementMapSection] = []
    headings = list(_HEADING.finditer(text))
    for i, m in enumerate(headings):
        block_start = m.end()
        block_end = headings[i + 1].start() if i + 1 < len(headings) else len(text)
        block = text[block_start:block_end]

        rw_tab = m.group(1).strip()
        title_tail = m.group(2).strip()  # short element description from heading

        src = _SOURCE.search(block)
        source_template = src.group(1) if src else ""

        values: list[str] = []
        vmatch = _VALUES_BLOCK.search(block)
        if vmatch:
            values = _VALUE_ITEM.findall(vmatch.group(1))

        # First "RW element" bullet after "RW element:" line
        rw_element = title_tail
        rw_section = re.search(r"RW element:\s*\n+\s*-\s*`([^`]+)`", block)
        if rw_section:
            rw_element = rw_section.group(1).strip()

        sections.append(ElementMapSection(
            rw_tab=rw_tab,
            rw_element=rw_element,
            source_template=source_template,
            rw_values=values,
        ))
    return sections


def classify_status(rw_value: str, rw_model: dict[str, list[str]]) -> str:
    """`rw_model` is the {table: [measure_names]} dict from
    rw_inventory_measures.fetch_measures_by_table().
    """
    name = rw_value.strip()
    for measures in rw_model.values():
        if name in measures:
            return "bound"
    return "needs_measure"


def emit_bindings(
    sections: Iterable[ElementMapSection],
    rw_model: dict[str, list[str]],
) -> Iterable[dict]:
    for sec in sections:
        for value in sec.rw_values:
            slug_tab = re.sub(r"\W+", "_", sec.rw_tab).strip("_")
            slug_val = re.sub(r"\W+", "_", value).strip("_")
            yield {
                "id": f"bind:rw:{slug_tab}:{slug_val}",
                "type": "RWBinding",
                "rw_tab": sec.rw_tab,
                "rw_element": sec.rw_element,
                "rw_field": value,
                "source_template": sec.source_template,
                "rw_measure_target": f"msr:rw:{value}",
                "status": classify_status(value, rw_model),
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--skip-rw-model", action="store_true",
        help="Don't call Fabric — emit all status=needs_measure (offline mode)",
    )
    args = parser.parse_args()

    text = args.doc.expanduser().read_text()
    sections = parse_element_map(text)

    if args.skip_rw_model:
        rw_model: dict[str, list[str]] = {}
    else:
        from scripts.sales.rw_inventory_measures import fetch_measures_by_table
        rw_model = fetch_measures_by_table()

    rows = list(emit_bindings(sections, rw_model))

    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    bind_path = out_dir / "bindings.jsonl"
    targets_path = out_dir / "rw_targets.csv"

    with bind_path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    fieldnames = ["rw_tab", "rw_element", "rw_field", "source_template",
                  "rw_measure_target", "status"]
    with targets_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r[k] for k in fieldnames})

    by_status: dict[str, int] = {}
    for r in rows:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(f"bindings: {len(rows)}  by_status: {by_status}")
    print(f"out: {bind_path}, {targets_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_bind.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run the script in offline mode (no Fabric call)**

Run:

```bash
python3 -m scripts.sales.rw_zebra_kg_bind \
  --out-dir data/zebra_kg_rw --skip-rw-model
```

Expected: writes `data/zebra_kg_rw/bindings.jsonl` and `rw_targets.csv`; prints `by_status: {'needs_measure': N}` (all needs_measure since no model loaded).

- [ ] **Step 6: Verify against the real RW semantic model**

Run (requires `az login` from existing session):

```bash
python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw
```

Expected: `by_status: {'bound': X, 'needs_measure': Y}` with X > 0 (some RW measures already exist in the deployed model). If the call hits a Fabric 401, run `az login` first and retry.

- [ ] **Step 7: Commit**

```bash
git add scripts/sales/rw_zebra_kg_bind.py tests/sales/test_rw_zebra_kg_bind.py
git commit -m "feat(track:rw): zebra_kg RW binding overlay"
```

---

## Task 6: Query CLI

Goal: a single CLI that answers the four query patterns from the spec across all artifacts.

**Files:**

- Create: `scripts/sales/rw_zebra_kg_query.py`
- Create: `tests/sales/test_rw_zebra_kg_query.py`

- [ ] **Step 1: Write failing tests**

Create `tests/sales/test_rw_zebra_kg_query.py`:

```python
"""Tests for scripts.sales.rw_zebra_kg_query — read-only query CLI."""

from __future__ import annotations

import json

import pytest

from scripts.sales import rw_zebra_kg_query as q


@pytest.fixture
def kg_dir(tmp_path):
    nodes = [
        {"id": "msr:t1:Sales AC", "type": "Measure", "name": "Sales AC",
         "table": "f", "scenario": "AC", "is_variance": False, "template": "t1"},
        {"id": "msr:t1:Sales PY", "type": "Measure", "name": "Sales PY",
         "table": "f", "scenario": "PY", "is_variance": False, "template": "t1"},
        {"id": "msr:t1:Sales vs PY", "type": "Measure", "name": "Sales vs PY",
         "table": "f", "scenario": "AC", "is_variance": True, "template": "t1"},
        {"id": "tbl:t1:f", "type": "Table", "name": "f", "template": "t1"},
        {"id": "scn:PY", "type": "Scenario", "code": "PY"},
    ]
    edges = [
        {"src": "msr:t1:Sales vs PY", "dst": "msr:t1:Sales AC", "type": "depends_on", "props": {}},
        {"src": "msr:t1:Sales vs PY", "dst": "msr:t1:Sales PY", "type": "depends_on", "props": {}},
    ]
    (tmp_path / "nodes_datamodel.jsonl").write_text(
        "\n".join(json.dumps(n) for n in nodes) + "\n"
    )
    (tmp_path / "edges_datamodel.jsonl").write_text(
        "\n".join(json.dumps(e) for e in edges) + "\n"
    )
    (tmp_path / "style_tokens.json").write_text(json.dumps([
        {"kind": "color", "value": "#000000", "purpose": "ac",
         "usage_count": 100, "canonical": True},
        {"kind": "color", "value": "#FF6600", "purpose": "highlight",
         "usage_count": 5, "canonical": False},
    ]))
    return tmp_path


def test_load_nodes_returns_all_rows(kg_dir):
    nodes = q.load_nodes(kg_dir)
    assert len(nodes) == 5


def test_filter_measures_where_is_variance_true(kg_dir):
    rows = q.filter_measures(q.load_nodes(kg_dir), is_variance=True)
    names = {r["name"] for r in rows}
    assert names == {"Sales vs PY"}


def test_canonical_tokens_only(kg_dir):
    rows = q.filter_tokens(q.load_tokens(kg_dir), canonical_only=True)
    assert len(rows) == 1
    assert rows[0]["value"] == "#000000"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_query.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement the query CLI**

Create `scripts/sales/rw_zebra_kg_query.py`:

```python
"""Read-only CLI over the Zebra BI knowledge graph.

Examples:
    # Measures across all templates that drive variance arrows
    python3 -m scripts.sales.rw_zebra_kg_query --measures --where is_variance=true

    # Style tokens used by a specific visual (requires visual-side graph)
    python3 -m scripts.sales.rw_zebra_kg_query --tokens-for vis:salesfunnel:home3:zbi_table_01

    # RW elements that are bound vs need a DAX measure authored
    python3 -m scripts.sales.rw_zebra_kg_query --rw-status

    # Canonical token palette only
    python3 -m scripts.sales.rw_zebra_kg_query --tokens --canonical-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KG_DIR = REPO_ROOT / "data/zebra_kg"
DEFAULT_RW_DIR = REPO_ROOT / "data/zebra_kg_rw"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def load_nodes(kg_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(kg_dir / "nodes_datamodel.jsonl")


def load_edges(kg_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(kg_dir / "edges_datamodel.jsonl")


def load_tokens(kg_dir: Path) -> list[dict[str, Any]]:
    path = kg_dir / "style_tokens.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def load_bindings(rw_dir: Path) -> list[dict[str, Any]]:
    return _read_jsonl(rw_dir / "bindings.jsonl")


def filter_measures(
    nodes: list[dict[str, Any]],
    is_variance: bool | None = None,
    scenario: str | None = None,
    template: str | None = None,
) -> list[dict[str, Any]]:
    rows = [n for n in nodes if n.get("type") == "Measure"]
    if is_variance is not None:
        rows = [n for n in rows if bool(n.get("is_variance")) == is_variance]
    if scenario is not None:
        rows = [n for n in rows if n.get("scenario") == scenario]
    if template is not None:
        rows = [n for n in rows if n.get("template") == template]
    return rows


def filter_tokens(
    tokens: list[dict[str, Any]],
    canonical_only: bool = False,
    kind: str | None = None,
) -> list[dict[str, Any]]:
    rows = list(tokens)
    if canonical_only:
        rows = [r for r in rows if r.get("canonical")]
    if kind:
        rows = [r for r in rows if r.get("kind") == kind]
    return rows


def _parse_where(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"--where expects key=value, got: {it}")
        k, v = it.split("=", 1)
        if v.lower() in {"true", "false"}:
            out[k] = v.lower() == "true"
        else:
            out[k] = v
    return out


def _print(rows: list[dict[str, Any]], fmt: str) -> None:
    if fmt == "json":
        json.dump(rows, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:  # tsv
        if not rows:
            return
        keys = sorted({k for r in rows for k in r.keys()})
        sys.stdout.write("\t".join(keys) + "\n")
        for r in rows:
            sys.stdout.write("\t".join(str(r.get(k, "")) for k in keys) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG_DIR)
    parser.add_argument("--rw-dir", type=Path, default=DEFAULT_RW_DIR)
    parser.add_argument("--format", choices=["tsv", "json"], default="tsv")

    parser.add_argument("--measures", action="store_true",
                        help="List measures (filterable with --where)")
    parser.add_argument("--where", action="append", default=[],
                        help="key=value filter; repeatable (e.g. is_variance=true)")
    parser.add_argument("--tokens", action="store_true", help="List style tokens")
    parser.add_argument("--canonical-only", action="store_true")
    parser.add_argument("--tokens-for", type=str, default=None,
                        help="Filter tokens by usage purpose substring")
    parser.add_argument("--rw-status", action="store_true",
                        help="RW binding overlay status summary + rows")

    args = parser.parse_args()

    nodes = load_nodes(args.kg_dir.expanduser())
    tokens = load_tokens(args.kg_dir.expanduser())
    bindings = load_bindings(args.rw_dir.expanduser())

    if args.measures:
        where = _parse_where(args.where)
        rows = filter_measures(nodes, **where)
        _print(rows, args.format)
        return

    if args.tokens or args.canonical_only or args.tokens_for:
        rows = filter_tokens(tokens, canonical_only=args.canonical_only)
        if args.tokens_for:
            needle = args.tokens_for.lower()
            rows = [r for r in rows if needle in r.get("purpose", "").lower()]
        _print(rows, args.format)
        return

    if args.rw_status:
        by_status: dict[str, int] = {}
        for b in bindings:
            by_status[b.get("status", "?")] = by_status.get(b.get("status", "?"), 0) + 1
        print(f"# RW binding status: {by_status}")
        _print(bindings, args.format)
        return

    parser.error("nothing to do — pass --measures, --tokens, --tokens-for, or --rw-status")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run unit tests**

Run:

```bash
python3 -m pytest tests/sales/test_rw_zebra_kg_query.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Smoke test against real artifacts**

Run:

```bash
python3 -m scripts.sales.rw_zebra_kg_query --measures --where is_variance=true | head -20
python3 -m scripts.sales.rw_zebra_kg_query --tokens --canonical-only --format tsv | head -20
python3 -m scripts.sales.rw_zebra_kg_query --rw-status
```

Expected: each command prints rows (or, for rw-status, the by-status summary line).

- [ ] **Step 6: Commit**

```bash
git add scripts/sales/rw_zebra_kg_query.py tests/sales/test_rw_zebra_kg_query.py
git commit -m "feat(track:rw): zebra_kg query CLI"
```

---

## Task 7: Index doc + final pass

**Files:**

- Create: `docs/sales/RW_ZEBRA_KG_INDEX.md`

- [ ] **Step 1: Write the index doc**

Create `docs/sales/RW_ZEBRA_KG_INDEX.md`:

````markdown
# RW Zebra BI Knowledge Graph — Index

Companion to the GraphRAG element map (`RW_ZEBRA_BI_GRAPHRAG_ELEMENT_MAP.md`).
This index documents the **datamodel + style + binding** layer added on top of
the existing visual-side graph at
`~/Downloads/rw-zebra-bi-template-research-20260509/analysis/`.

Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`

## Artifacts

| Path                                   | What                                      |
| -------------------------------------- | ----------------------------------------- |
| `data/zebra_kg/nodes_datamodel.jsonl`  | Measure / Table / Column / Relationship / Scenario nodes |
| `data/zebra_kg/edges_datamodel.jsonl`  | depends_on / related_to / scenario_of edges |
| `data/zebra_kg/measure_catalog.csv`    | Flat catalog of every DAX measure across 20 templates |
| `data/zebra_kg/style_tokens.json`      | Deduped color/font/border/padding tokens with usage counts and canonical flag |
| `data/zebra_kg_rw/bindings.jsonl`      | RW binding overlay: bound/unbound/needs_measure |
| `data/zebra_kg_rw/rw_targets.csv`      | Flat RW tab × element × status view |

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
# Variance-driving measures across all templates
python3 -m scripts.sales.rw_zebra_kg_query --measures --where is_variance=true

# Canonical color/font palette
python3 -m scripts.sales.rw_zebra_kg_query --tokens --canonical-only

# RW backlog: which RW elements still need a DAX measure authored?
python3 -m scripts.sales.rw_zebra_kg_query --rw-status \
  | awk -F'\t' 'NR==1 || /\tneeds_measure$/'
```

## Known limitations

- DAX dependency edges are regex-based on `[Foo Bar]` references — column
  references may register as false-positive measure dependencies. Filter at
  query time by joining against the Measure node set.
- Scenario classifier is name-based (PY/PL/FC/AC). Templates that use
  non-English or unusual conventions may fall through to AC.
- Style token canonical threshold is 50 by default — tune via
  `--canonical-threshold` if the 20-template corpus skews counts.
- DAX expressions are stored verbatim, including any embedded comments. Do
  not paste expressions into RW production measures without review.
````

- [ ] **Step 2: Run the full test suite to confirm nothing else broke**

Run:

```bash
cd /Users/test/code/apps/sales-ops-copilot-rw
source .venv/bin/activate
python3 -m pytest tests/sales/ -v
```

Expected: all tests pass; no failures or errors. If there are pre-existing failures unrelated to this work (in `test_rw_dashboard_harness.py` etc.), note them but do not fix in this plan.

- [ ] **Step 3: Final ruff lint**

Run:

```bash
python3 -m ruff check scripts/sales/rw_zebra_kg_*.py tests/sales/test_rw_zebra_kg_*.py
```

Expected: clean (no findings). If findings, fix inline; common ones are `E501` line-too-long which the existing repo ignores per pyproject — only fix unique cases.

- [ ] **Step 4: Commit the index doc**

```bash
git add docs/sales/RW_ZEBRA_KG_INDEX.md
git commit -m "docs(track:rw): RW Zebra KG index — schema, regen, queries"
```

- [ ] **Step 5: Verify branch state**

Run:

```bash
git log --oneline feat/track-rw-tooling -10
git status
```

Expected: 7 new commits on `feat/track-rw-tooling` (1 setup + 6 features/docs).
Working tree clean.

---

## Self-review checklist (run before declaring done)

1. **Spec coverage** — confirm each spec section maps to a task:

   | Spec section | Task |
   |---|---|
   | Two-layer KG layout | Task 1 |
   | DAX measure catalog | Task 3 |
   | Relationship graph | Task 3 |
   | Style token catalog | Task 4 |
   | RW binding overlay | Task 5 |
   | CLI query tool | Task 6 |
   | Node schema (Visual, VisualRole) | (existing miner — referenced in Task 7) |
   | Node schema (Measure, Table, Column, Rel, Scenario) | Task 3 |
   | Node schema (StyleToken) | Task 4 |
   | Edge: depends_on / related_to / scenario_of | Task 3 |
   | Edge: uses_token | Deferred — see Open questions below |
   | Edge: contains / resolves_to | Deferred — see Open questions below |
   | Error handling (extract_errors.log, inventory_join warning) | Task 3 (errors log); inventory join in Open questions |
   | Testing — extraction parity / edge integrity / token determinism / binding round-trip | Tasks 2, 3, 4, 5 |

2. **Open questions intentionally deferred** (carry forward to a follow-up plan):

   - **`uses_token` edges**: requires linking each visual to the tokens it uses, not just deduping tokens globally. Token sweep in Task 4 collects values without per-visual links. Adding `uses_token` requires rerunning the sweep with visual-id context — a v2 enhancement.
   - **`resolves_to` edges (VisualRole → Measure)**: the existing miner emits role-name → field-list as JSON; matching field-list strings to measure-name nodes across templates needs a separate reconciliation pass. Defer to a v2 task once the basic graph is in use and we know which mismatches are real ambiguities vs noise.
   - **Visual-id join warning** (`inventory_join: false`): only relevant once `uses_token` / `resolves_to` are added. Skipped here.

3. **Placeholder scan** — none. Every step has working code or an exact command.

4. **Type consistency** — `template_slug` (string) used identically across `Measure.table`, `_msr_id`, `_tbl_id`. `cardinality` enum `{many_to_one, one_to_many, one_to_one, many_to_many, unknown}` matches across `_CARDINALITY_MAP` definition (Task 2) and integration test assertion (Task 2 step 5).

5. **Scope check** — single coherent plan, no decomposition needed.
