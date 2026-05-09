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

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ANALYSIS = Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/analysis"
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
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def _classify_role_scenario(role_name: str, ref: str) -> str | None:
    """Infer scenario from the role name. PreviousYear->PY, Plan->PL,
    Forecast->FC, Values/Y->AC. Other roles (Category, Group, Comments,
    Filters) -> None.
    """
    role_lower = role_name.lower()
    if role_lower in {"previousyear"} or "previousyear" in role_lower:
        return "PY"
    if role_lower in {"plan", "budget"} or role_lower.startswith("plan"):
        return "PL"
    if role_lower in {"forecast"} or role_lower.startswith("forecast"):
        return "FC"
    if role_lower in {"values", "y"}:
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
        r
        for r in inventory
        if r.get("template_slug") == template_slug and r.get("page") == page_name
    ]
    if not page_visuals:
        raise ValueError(
            f"no visuals found for ({template_slug!r}, {page_name!r}) "
            f"in {analysis_dir / 'visual_inventory.csv'}"
        )

    dm_nodes = _read_jsonl(kg_dir / "nodes_datamodel.jsonl")
    template_measures = {
        n["name"]
        for n in dm_nodes
        if n.get("type") == "Measure" and n.get("template") == template_slug
    }

    visuals: list[VisualRecipe] = []
    for r in page_visuals:
        roles_raw = r.get("roles_json") or "{}"
        try:
            roles = json.loads(roles_raw)
        except json.JSONDecodeError:
            roles = {}

        scenarios: list[str] = []
        measure_refs: list[str] = []
        tables_referenced: set[str] = set()

        for role_name, refs in roles.items():
            for ref in refs or []:
                if "." in ref:
                    table, field_name = ref.split(".", 1)
                    tables_referenced.add(table)
                    if field_name in template_measures:
                        measure_refs.append(field_name)
                scn = _classify_role_scenario(role_name, ref)
                if scn and scn not in scenarios:
                    scenarios.append(scn)

        def _f(key: str) -> float:
            try:
                return float(r.get(key) or 0)
            except (ValueError, TypeError):
                return 0.0

        visuals.append(
            VisualRecipe(
                visual_type=r["visual_type"],
                position={
                    "x": _f("x"),
                    "y": _f("y"),
                    "w": _f("width"),
                    "h": _f("height"),
                },
                role_bindings=roles,
                scenarios_used=scenarios,
                tables_referenced=sorted(tables_referenced),
                measure_refs=sorted(set(measure_refs)),
                text=r.get("text", "") or "",
            )
        )

    tokens_path = kg_dir / "style_tokens.json"
    style_tokens = json.loads(tokens_path.read_text()) if tokens_path.exists() else []

    relationships: list[dict] = []
    edges_path = kg_dir / "edges_datamodel.jsonl"
    if edges_path.exists():
        prefix = f"tbl:{template_slug}:"
        for e in _read_jsonl(edges_path):
            if e.get("type") != "related_to":
                continue
            src = e.get("src", "")
            dst = e.get("dst", "")
            if not (src.startswith(prefix) and dst.startswith(prefix)):
                continue
            props = e.get("props") or {}
            relationships.append(
                {
                    "from_table": src[len(prefix) :],
                    "to_table": dst[len(prefix) :],
                    "cardinality": props.get("cardinality", "unknown"),
                    "cross_filter": props.get("cross_filter", "single"),
                    "active": props.get("active", True),
                }
            )

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
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional path to write the full recipe JSON",
    )
    args = parser.parse_args()

    recipe = extract_recipe(
        args.template,
        args.page,
        args.analysis_dir.expanduser(),
        args.kg_dir.expanduser(),
    )
    body = {
        "source_template": recipe.source_template,
        "source_page": recipe.source_page,
        "visuals": [asdict(v) for v in recipe.visuals],
        "style_tokens_count": len(recipe.style_tokens),
        "relationships_count": len(recipe.relationships),
    }
    payload = json.dumps(body, indent=2)
    if args.out:
        out = args.out.expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(payload + "\n")
        print(
            f"wrote {out}  visuals={len(recipe.visuals)}  "
            f"tokens={len(recipe.style_tokens)}  "
            f"rels={len(recipe.relationships)}"
        )
    else:
        print(payload)


if __name__ == "__main__":
    main()
