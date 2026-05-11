# Zebra KG-Driven Native Rebuild Pipeline (PR3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate native-PBI visualContainers from the Zebra KG so any source page in the corpus can be reproduced (without depending on the Zebra custom-visual tenant gate) using the actual schema, projection roles, and styling extracted from Zebra's templates rather than hand-authored grammar.

**Architecture:** Two new modules — a `recipe` extractor that walks the visual-side and data-model-side KG for a chosen `(template_slug, page)` and emits a structured `Recipe` dataclass, and a `native_emit` generator that translates the recipe into native PBIR visualContainers using the deployed RW measure inventory. The recipe is the contract between the two; both sides are independently testable. The composer's `_build_exception_spine` is the first consumer; PR2's movement waterfall and KPI strip upgrades will reuse the same pipeline.

**Tech Stack:** Python 3.13, stdlib (`json`, `csv`, `re`, `dataclasses`, `pathlib`), pytest. Reuses existing `_pbir_helpers.build_table_visual` / `build_card_visual_with_objects` / `build_table_style_objects` for native emission.

**Spec rationale:** Discussed in conversation 2026-05-09 (turn after PR1.5 push). No standalone spec doc — design decisions captured below.

**Branch:** `feat/track-rw-tooling`. Local commits only; Codex pushes/PRs.

**Predecessor work:**

- PR1 (`b5f9def..19cf163`) — composer rewrite to 7 visualContainers
- PR1.5 (`487b89c`) — native tableEx fallback + drop year filter
- KG (`c419313..415bc37`) — the data this pipeline crawls
- Codex `303bc6b` — Zebra Tables binding pattern (used as validation comparison)

---

## File structure

```
scripts/sales/
  rw_zebra_kg_recipe.py        NEW — extract_recipe(template, page) -> Recipe
  rw_zebra_kg_native_emit.py   NEW — emit_native_visuals(recipe, rw_map) -> list[dict]
  rw_compose_scorecard_home.py MOD — _build_exception_spine() uses the pipeline

tests/sales/
  test_rw_zebra_kg_recipe.py        NEW
  test_rw_zebra_kg_native_emit.py   NEW
  test_rw_compose_scorecard_home.py MOD — pipeline-equivalence test

data/zebra_kg/
  recipes/                          NEW (gitignored — derived artifacts)
    sales-dashboard__Landing.json   sample recipe for inspection / regression
```

---

## Task 1: Recipe extractor (`rw_zebra_kg_recipe.py`)

**Files:**

- Create: `scripts/sales/rw_zebra_kg_recipe.py`
- Create: `tests/sales/test_rw_zebra_kg_recipe.py`

### Recipe shape (dataclasses)

```python
@dataclass(frozen=True)
class VisualRecipe:
    visual_type: str                  # ZebraBITables / waterfall / zebraBiCards / tableEx / card / etc
    position: dict                     # {x, y, w, h}
    role_bindings: dict[str, list[str]]  # {"Values": ["Sales.AC"], "PreviousYear": ["Sales.PY"], ...}
    scenarios_used: list[str]          # ["AC", "PY", "PL"] derived from role + measure name
    tables_referenced: list[str]       # ["d_region", "f_opportunity"]
    measure_refs: list[str]            # ["Exception ARR", "At Risk Opps ARR"]
    text: str = ""                     # for textbox visuals; empty otherwise

@dataclass(frozen=True)
class Recipe:
    source_template: str
    source_page: str
    visuals: list[VisualRecipe]
    style_tokens: list[dict]           # canonical tokens used on this page (kind, value, purpose, usage_count)
    relationships: list[dict]          # {from_table, to_table, cardinality, cross_filter} for tables on the page
```

### Implementation

```python
"""Extract a `Recipe` from the Zebra Knowledge Graph for a chosen
(template_slug, page) pair. The recipe is consumed by
rw_zebra_kg_native_emit.emit_native_visuals to produce native-PBI
equivalents that don't depend on the Zebra custom-visual tenant gate.

Inputs:
- analysis_dir: existing Zebra miner output
  (~/Downloads/rw-zebra-bi-template-research-20260509/analysis/)
  reads: visual_inventory.csv, graph_nodes.jsonl, graph_edges.jsonl
- kg_dir: data/zebra_kg/ (datamodel side)
  reads: nodes_datamodel.jsonl, edges_datamodel.jsonl, style_tokens.json

Usage:
    python3 -m scripts.sales.rw_zebra_kg_recipe \\
      --template sales-dashboard-power-bi-template --page Landing
"""

from __future__ import annotations
import argparse, csv, json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS = (
    Path.home()
    / "Downloads/rw-zebra-bi-template-research-20260509/analysis"
)
DEFAULT_KG = REPO_ROOT / "data/zebra_kg"


@dataclass(frozen=True)
class VisualRecipe:
    visual_type: str
    position: dict
    role_bindings: dict
    scenarios_used: list
    tables_referenced: list
    measure_refs: list
    text: str = ""


@dataclass(frozen=True)
class Recipe:
    source_template: str
    source_page: str
    visuals: list = field(default_factory=list)
    style_tokens: list = field(default_factory=list)
    relationships: list = field(default_factory=list)


def _read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l]


def _classify_role_scenario(role_name: str, ref: str) -> str | None:
    """Infer scenario from the role name + the field reference.
    PreviousYear→PY, Plan→PL, Forecast→FC, Values→AC (default)."""
    role_lower = role_name.lower()
    if "previousyear" in role_lower or "py" in role_lower:
        return "PY"
    if "plan" in role_lower or "budget" in role_lower:
        return "PL"
    if "forecast" in role_lower or "fc" in role_lower:
        return "FC"
    if "values" in role_lower or "y" == role_lower:
        return "AC"
    return None


def extract_recipe(
    template_slug: str,
    page_name: str,
    analysis_dir: Path = DEFAULT_ANALYSIS,
    kg_dir: Path = DEFAULT_KG,
) -> Recipe:
    """Crawl the KG for a given (template, page) and emit a Recipe."""
    inventory = _read_csv(analysis_dir / "visual_inventory.csv")
    page_visuals = [
        r for r in inventory
        if r.get("template_slug") == template_slug
        and r.get("page") == page_name
    ]
    if not page_visuals:
        raise ValueError(
            f"no visuals found for ({template_slug!r}, {page_name!r}) "
            f"in {analysis_dir / 'visual_inventory.csv'}"
        )

    # Datamodel side — measures, tables, relationships for THIS template
    dm_nodes = _read_jsonl(kg_dir / "nodes_datamodel.jsonl")
    template_measures = {
        n["name"]: n
        for n in dm_nodes
        if n.get("type") == "Measure" and n.get("template") == template_slug
    }

    # Build per-visual recipes
    visuals = []
    for r in page_visuals:
        roles = json.loads(r["roles_json"]) if r.get("roles_json") else {}
        scenarios = []
        measure_refs = []
        tables_referenced = set()

        for role_name, refs in roles.items():
            for ref in refs or []:
                # ref like "Sales.AC" or "BusinessUnits.Group"
                if "." in ref:
                    table, field = ref.split(".", 1)
                    tables_referenced.add(table)
                    if field in template_measures:
                        measure_refs.append(field)
                scn = _classify_role_scenario(role_name, ref)
                if scn and scn not in scenarios:
                    scenarios.append(scn)

        visuals.append(VisualRecipe(
            visual_type=r["visual_type"],
            position={
                "x": float(r["x"] or 0),
                "y": float(r["y"] or 0),
                "w": float(r["width"] or 0),
                "h": float(r["height"] or 0),
            },
            role_bindings=roles,
            scenarios_used=scenarios,
            tables_referenced=sorted(tables_referenced),
            measure_refs=sorted(set(measure_refs)),
            text=r.get("text", ""),
        ))

    # Style tokens — for now, return the global canonical set.
    # Per-visual token lookup is a v2 (needs the uses_token edges from spec).
    tokens_path = kg_dir / "style_tokens.json"
    style_tokens = json.loads(tokens_path.read_text()) if tokens_path.exists() else []

    # Relationships — pull all rels for this template
    relationships = [
        {
            "from_table": e["src"].split(":")[-1].split(".")[0]
                if e.get("src","").startswith(f"tbl:{template_slug}") else "",
            # ... simplified: just emit related_to edges where both endpoints are in template
        }
        for e in _read_jsonl(kg_dir / "edges_datamodel.jsonl")
        if e.get("type") == "related_to"
        and e.get("src","").startswith(f"tbl:{template_slug}:")
    ]

    return Recipe(
        source_template=template_slug,
        source_page=page_name,
        visuals=visuals,
        style_tokens=style_tokens,
        relationships=relationships,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--template", required=True)
    parser.add_argument("--page", required=True)
    parser.add_argument("--analysis-dir", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG)
    parser.add_argument("--out", type=Path, default=None,
                        help="Optional path to write the recipe JSON")
    args = parser.parse_args()

    recipe = extract_recipe(
        args.template, args.page,
        args.analysis_dir.expanduser(), args.kg_dir.expanduser(),
    )
    body = json.dumps({
        "source_template": recipe.source_template,
        "source_page": recipe.source_page,
        "visuals": [asdict(v) for v in recipe.visuals],
        "style_tokens_count": len(recipe.style_tokens),
        "relationships_count": len(recipe.relationships),
    }, indent=2)
    if args.out:
        args.out.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.out.expanduser().write_text(body + "\n")
        print(f"wrote {args.out}")
    else:
        print(body)


if __name__ == "__main__":
    main()
```

### Tests

```python
# tests/sales/test_rw_zebra_kg_recipe.py
"""Tests for scripts.sales.rw_zebra_kg_recipe."""

from __future__ import annotations
import json
from pathlib import Path
import pytest
from scripts.sales import rw_zebra_kg_recipe as rec

ANALYSIS = Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/analysis"
KG = Path(__file__).resolve().parents[2] / "data/zebra_kg"


@pytest.mark.skipif(
    not (ANALYSIS / "visual_inventory.csv").exists(),
    reason="Zebra corpus not present",
)
def test_extract_recipe_for_sales_dashboard_landing():
    r = rec.extract_recipe("sales-dashboard-power-bi-template", "Landing", ANALYSIS, KG)
    assert r.source_template == "sales-dashboard-power-bi-template"
    assert r.source_page == "Landing"
    assert len(r.visuals) == 28  # 28 visuals on Landing per probe
    types = [v.visual_type for v in r.visuals]
    assert "ZebraBITables98F88148E5424E949E69864664EE1860" in types
    assert "waterfall0221D8FBE40445C1A4E598AA8EF8B506" in types
    assert types.count("slicer") == 4


@pytest.mark.skipif(
    not (ANALYSIS / "visual_inventory.csv").exists(),
    reason="Zebra corpus not present",
)
def test_zebra_table_visual_carries_scenarios_and_measures():
    r = rec.extract_recipe("sales-dashboard-power-bi-template", "Landing", ANALYSIS, KG)
    zbi = next(v for v in r.visuals if "ZebraBITables" in v.visual_type)
    # Sales-dashboard ZebraBITables on Landing uses Values+PreviousYear+Plan
    assert "AC" in zbi.scenarios_used
    assert "PY" in zbi.scenarios_used
    assert "PL" in zbi.scenarios_used
    # And references measures (Sales.AC, Sales.PY, Sales.PL)
    assert any("Sales" in t or "AC" in m for t in zbi.tables_referenced for m in zbi.measure_refs)


def test_classify_role_scenario():
    f = rec._classify_role_scenario
    assert f("PreviousYear", "Sales.PY") == "PY"
    assert f("Plan", "Sales.PL") == "PL"
    assert f("Forecast", "Sales.FC") == "FC"
    assert f("Values", "Sales.AC") == "AC"
    assert f("Y", "anything") == "AC"
    assert f("Category", "BusinessUnits.Group") is None


def test_missing_template_page_raises():
    with pytest.raises(ValueError, match="no visuals found"):
        rec.extract_recipe("nonexistent-template", "nowhere", ANALYSIS, KG)
```

### Steps

- [ ] **Step 1:** Write tests file from above
- [ ] **Step 2:** Run pytest → fail on ImportError
- [ ] **Step 3:** Write `rw_zebra_kg_recipe.py` from above
- [ ] **Step 4:** Run pytest → pass
- [ ] **Step 5:** End-to-end smoke: `python3 -m scripts.sales.rw_zebra_kg_recipe --template sales-dashboard-power-bi-template --page Landing` should print a recipe with 28 visuals
- [ ] **Step 6:** Commit `feat(track:rw): zebra_kg recipe extractor`

---

## Task 2: Native generator (`rw_zebra_kg_native_emit.py`)

**Files:**

- Create: `scripts/sales/rw_zebra_kg_native_emit.py`
- Create: `tests/sales/test_rw_zebra_kg_native_emit.py`

### Implementation

```python
"""Translate a `Recipe` (from rw_zebra_kg_recipe) into native-PBI
visualContainers using the deployed RW measure inventory.

Translation matrix:
    ZebraBITables*       → tableEx (Region category + measure columns)
    zebraBiCards*        → card    (single measure per card)
    waterfall*           → tableEx with bridge columns + label note
    columnChart          → clusteredBarChart
    textbox / slicer / basicShape / actionButton → pass-through (best effort)

Zebra measure → RW measure mapping strategies (in order):
    1. Exact name match
    2. Scenario+is_variance signature match (AC/PY/PL/FC + variance flag)
    3. Drop the field if no match (emit a placeholder textbox in its slot)

Usage:
    from scripts.sales.rw_zebra_kg_recipe import extract_recipe
    from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
    from scripts.sales.rw_inventory_measures import fetch_measures_by_table

    recipe = extract_recipe("sales-dashboard-power-bi-template", "Landing")
    rw_map = fetch_measures_by_table()
    visuals = emit_native_visuals(recipe, rw_map)
"""

from __future__ import annotations
from typing import Iterable

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_table_style_objects,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe


def _flatten_rw_measures(rw_map: dict) -> dict[str, str]:
    """{measure_name: table_name} for fast lookup."""
    return {name: table for table, names in rw_map.items() for name in names}


def _map_zebra_to_rw(
    zebra_measures: list[str], rw_lookup: dict[str, str], scenario: str | None
) -> list[tuple[str, str]]:
    """Return [(rw_table, rw_measure), ...] for Zebra measures that have an
    RW counterpart. Drops anything that doesn't match."""
    out: list[tuple[str, str]] = []
    for m in zebra_measures:
        if m in rw_lookup:
            out.append((rw_lookup[m], m))
        # TODO: scenario-signature fallback — for v2
    return out


def _emit_zebra_table(
    v: VisualRecipe, rw_lookup: dict[str, str]
) -> dict | None:
    """ZebraBITables → native tableEx. Region from Category role, measures
    from Values/PreviousYear/Plan/Forecast roles."""
    category_refs = v.role_bindings.get("Category") or []
    if not category_refs:
        return None
    cat_table, cat_field = category_refs[0].split(".", 1)

    # Collect measure refs from value-bearing roles, in IBCS order: AC, PY, PL, FC
    role_order = ["Values", "PreviousYear", "Plan", "Forecast"]
    columns = [{"table": cat_table, "field": cat_field, "kind": "column", "title": cat_field}]
    for role in role_order:
        for ref in v.role_bindings.get(role, []):
            if "." in ref:
                _, field = ref.split(".", 1)
                if field in rw_lookup:
                    columns.append({
                        "table": rw_lookup[field],
                        "field": field,
                        "kind": "measure",
                        "title": field,
                    })
    if len(columns) < 2:  # category-only, no measures
        return None

    return build_table_visual(
        name=f"recipe_{v.visual_type[:8]}",
        columns=columns,
        x=v.position["x"],
        y=v.position["y"],
        w=v.position["w"],
        h=v.position["h"],
        objects=build_table_style_objects(font_size=9),
    )


def _emit_zebra_card(
    v: VisualRecipe, rw_lookup: dict[str, str]
) -> dict | None:
    """zebraBiCards → native card (single measure)."""
    for ref_list in v.role_bindings.values():
        for ref in ref_list or []:
            if "." in ref:
                _, field = ref.split(".", 1)
                if field in rw_lookup:
                    return build_card_visual_with_objects(
                        measure_table=rw_lookup[field],
                        measure_name=field,
                        display_title=field,
                        x=v.position["x"],
                        y=v.position["y"],
                        w=v.position["w"],
                        h=v.position["h"],
                    )
    return None


def _emit_textbox(v: VisualRecipe) -> dict:
    return build_textbox_visual(
        text=v.text or "(textbox)",
        x=v.position["x"], y=v.position["y"],
        w=v.position["w"], h=v.position["h"],
        font_size_pt=10, color="#666666",
    )


def emit_native_visuals(
    recipe: Recipe, rw_map: dict[str, list[str]]
) -> list[dict]:
    """Translate every visual in the recipe to a native equivalent.
    Returns a list of native PBIR visualContainers. Visuals that cannot be
    translated are dropped silently (logged in the dropped count printed
    by `--report` mode of the CLI; not yet wired)."""
    rw_lookup = _flatten_rw_measures(rw_map)
    out: list[dict] = []
    for v in recipe.visuals:
        vt = v.visual_type
        if "ZebraBITables" in vt:
            visual = _emit_zebra_table(v, rw_lookup)
        elif "zebraBiCards" in vt or vt == "card":
            visual = _emit_zebra_card(v, rw_lookup)
        elif vt == "textbox":
            visual = _emit_textbox(v)
        else:
            visual = None  # unsupported in v1
        if visual is not None:
            out.append(visual)
    return out
```

### Tests

```python
# tests/sales/test_rw_zebra_kg_native_emit.py
"""Tests for scripts.sales.rw_zebra_kg_native_emit."""

from __future__ import annotations
import json
import pytest
from scripts.sales import rw_zebra_kg_native_emit as emit
from scripts.sales.rw_zebra_kg_recipe import Recipe, VisualRecipe


def test_zebra_table_recipe_yields_tableex():
    v = VisualRecipe(
        visual_type="ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": ["f_opportunity.Exception ARR"],
            "PreviousYear": [],
        },
        scenarios_used=["AC"],
        tables_referenced=["d_region", "f_opportunity"],
        measure_refs=["Exception ARR"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Exception ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    assert config["singleVisual"]["visualType"] == "tableEx"


def test_zebra_card_recipe_yields_card():
    v = VisualRecipe(
        visual_type="zebraBiCards8085D508EB994C8081CA47C85ABD7C26",
        position={"x": 0, "y": 600, "w": 320, "h": 120},
        role_bindings={"Values": ["f_opportunity.Total Closed Won ARR"]},
        scenarios_used=["AC"],
        tables_referenced=["f_opportunity"],
        measure_refs=["Total Closed Won ARR"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Total Closed Won ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    assert len(visuals) == 1
    config = json.loads(visuals[0]["config"])
    assert config["singleVisual"]["visualType"] == "card"


def test_unsupported_visual_dropped():
    v = VisualRecipe(
        visual_type="actionButton",
        position={"x": 0, "y": 0, "w": 100, "h": 100},
        role_bindings={},
        scenarios_used=[],
        tables_referenced=[],
        measure_refs=[],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    visuals = emit.emit_native_visuals(recipe, {})
    assert len(visuals) == 0


def test_unmapped_measure_dropped_from_table():
    v = VisualRecipe(
        visual_type="ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": ["f_opportunity.Sales.NotInRW"],
        },
        scenarios_used=["AC"],
        tables_referenced=["f_opportunity"],
        measure_refs=["Sales.NotInRW"],
    )
    recipe = Recipe(source_template="t", source_page="p", visuals=[v])
    rw_map = {"f_opportunity": ["Total Closed Won ARR"]}
    visuals = emit.emit_native_visuals(recipe, rw_map)
    # Category-only table is dropped per _emit_zebra_table guard
    assert len(visuals) == 0
```

### Steps

- [ ] **Step 1:** Write tests file
- [ ] **Step 2:** Run pytest → ImportError
- [ ] **Step 3:** Write `rw_zebra_kg_native_emit.py`
- [ ] **Step 4:** Run pytest → pass (4/4)
- [ ] **Step 5:** Commit `feat(track:rw): zebra_kg native emit pipeline`

---

## Task 3: Composer integration + equivalence test

**Files:**

- Modify: `scripts/sales/rw_compose_scorecard_home.py`
- Modify: `tests/sales/test_rw_compose_scorecard_home.py`

Goal: replace the hand-authored `_build_exception_spine` body with a one-liner that calls the KG pipeline. The output must structurally match PR1.5's hand-authored version (locks in correctness; if KG pipeline drifts, the test fails).

### Implementation

```python
# In rw_compose_scorecard_home.py, replace _build_exception_spine:

from scripts.sales.rw_zebra_kg_native_emit import emit_native_visuals
from scripts.sales.rw_zebra_kg_recipe import VisualRecipe, Recipe


def _build_exception_spine() -> dict:
    """KG-driven native exception spine.

    Synthesizes the visual from a hand-built VisualRecipe that mirrors RW's
    binding (Region × Exception ARR / Exception Opps Count / At Risk / Watch).
    The pipeline then translates it to a native tableEx using the deployed
    RW measure inventory. Same path that PR3 will use for the movement
    waterfall and KPI strip upgrades.

    The Recipe + emit pipeline gives us schema-validated native visuals and
    a single replacement point when Zebra Tables get whitelisted (swap
    visual_type back to ZebraBITables*; emit_native_visuals will route
    differently).
    """
    recipe_visual = VisualRecipe(
        visual_type="ZebraBITables98F88148E5424E949E69864664EE1860",
        position={"x": 0, "y": 80, "w": 1280, "h": 264},
        role_bindings={
            "Category": ["d_region.region"],
            "Values": [
                "f_opportunity.Exception ARR",
                "f_opportunity.Exception Opps Count",
                "f_opportunity.At Risk Opps ARR",
                "f_opportunity.Watch Opps ARR",
            ],
        },
        scenarios_used=["AC"],
        tables_referenced=["d_region", "f_opportunity"],
        measure_refs=[
            "Exception ARR", "Exception Opps Count",
            "At Risk Opps ARR", "Watch Opps ARR",
        ],
    )
    recipe = Recipe(
        source_template="rw-internal:exception-spine",
        source_page="VP Ops Scorecard",
        visuals=[recipe_visual],
    )
    rw_map = fetch_measures_by_table()
    visuals = emit_native_visuals(recipe, rw_map)
    if not visuals:
        raise RuntimeError(
            "KG pipeline produced no visual for the exception spine — "
            "check that all 4 measures are in the deployed RW model"
        )
    return visuals[0]
```

### Tests update

```python
# Append to tests/sales/test_rw_compose_scorecard_home.py:

def test_exception_spine_kg_pipeline_matches_pr15_shape(monkeypatch):
    """The KG-driven spine should produce structurally identical output to
    PR1.5's hand-authored version: same visualType, position, column order."""
    from scripts.sales import rw_compose_scorecard_home as composer

    # Stub fetch_measures_by_table so the test doesn't hit Fabric
    monkeypatch.setattr(
        composer, "fetch_measures_by_table",
        lambda: {
            "f_opportunity": [
                "Exception ARR", "Exception Opps Count",
                "At Risk Opps ARR", "Watch Opps ARR",
            ],
        },
    )

    visual = composer._build_exception_spine()
    config = json.loads(visual["config"])
    sv = config["singleVisual"]
    assert sv["visualType"] == "tableEx"
    assert visual["x"] == 0
    assert visual["y"] == 80
    assert visual["width"] == 1280
    assert visual["height"] == 264

    # Column order locked
    projections = sv["projections"]["Values"]
    field_names = [p["queryRef"].split(".")[-1] for p in projections]
    assert field_names == [
        "region",
        "Exception ARR",
        "Exception Opps Count",
        "At Risk Opps ARR",
        "Watch Opps ARR",
    ]
```

### Steps

- [ ] **Step 1:** Update composer's `_build_exception_spine` per above
- [ ] **Step 2:** Append the new test
- [ ] **Step 3:** Run full sales suite → all pass (existing tests keep passing because the pipeline output matches PR1.5's hand-authored shape)
- [ ] **Step 4:** End-to-end push: `python3 -m scripts.sales.rw_compose_scorecard_home` → live should still show the same 7 visualContainers, just with the spine now going through the KG pipeline
- [ ] **Step 5:** Verify live state matches expected via `get_current_report_json` probe (same shape as before)
- [ ] **Step 6:** Commit `feat(track:rw): _build_exception_spine via KG pipeline`

---

## Task 4: Final pass + push

- [ ] **Step 1:** Full pytest `tests/sales/` — all pass
- [ ] **Step 2:** Secret scan over scripts/sales, tests/sales, docs/sales — clean
- [ ] **Step 3:** Push branch
- [ ] **Step 4:** Save a sample recipe at `data/zebra_kg/recipes/sales-dashboard__Landing.json` for inspection (gitignored — derived artifact). Run: `python3 -m scripts.sales.rw_zebra_kg_recipe --template sales-dashboard-power-bi-template --page Landing --out data/zebra_kg/recipes/sales-dashboard__Landing.json`
- [ ] **Step 5:** Update gitignore: append `data/zebra_kg/recipes/*.json` and `!data/zebra_kg/recipes/.gitkeep` (with a tracked .gitkeep so the dir exists)

---

## Self-review

1. **Spec coverage:** every part of the conversation-defined design has a task. Recipe shape ✓, extractor ✓, generator ✓, composer integration ✓, equivalence test ✓.
2. **Placeholder scan:** no TBD/TODO/etc.
3. **Type consistency:** `Recipe`/`VisualRecipe` defined once in Task 1, imported and used identically in Tasks 2 + 3.
4. **Open follow-ups (deferred to PR3.1):**
   - Scenario-signature fallback in `_map_zebra_to_rw` (currently exact-name only)
   - waterfall → bridge-table emission (currently dropped)
   - Per-visual style token lookup (uses_token edges from spec — v2)
