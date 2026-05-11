"""Mine the Zebra KG datamodel-side for relationship topology patterns.

Reads data/zebra_kg/nodes_datamodel.jsonl + edges_datamodel.jsonl
(produced by rw_zebra_kg_datamodel). Per-template, classifies:
fact tables, dim tables, calendar/scenario dim presence, bidirectional
+ inactive relationship counts, role-playing dimensions.

Emits data/zebra_kg/topology_patterns.json with per-template detail
plus a cross-template summary.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_topology_atlas
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NODES = REPO_ROOT / "data/zebra_kg/nodes_datamodel.jsonl"
DEFAULT_EDGES = REPO_ROOT / "data/zebra_kg/edges_datamodel.jsonl"
DEFAULT_OUT = REPO_ROOT / "data/zebra_kg/topology_patterns.json"

# Matches explicit calendar dim names AND PBI auto-generated DateTableTemplate_* /
# LocalDateTable_* hidden tables that are always date-intelligence dims.
_CALENDAR_NAME_RE = re.compile(
    r"^(d_)?(calendar|date|time)(s|\s.*)?\Z"
    r"|^(DateTableTemplate|LocalDateTable)_",
    re.IGNORECASE,
)
_SCENARIO_NAME_RE = re.compile(r"^(d_)?(scenarios?|versions?)$", re.IGNORECASE)


def _table_name_from_id(node_id: str) -> str:
    """`tbl:template-slug:name` → `name`. Robust to colons in template slug."""
    parts = node_id.split(":", 2)
    return parts[2] if len(parts) >= 3 else node_id


def _template_from_table_id(node_id: str) -> str:
    parts = node_id.split(":", 2)
    return parts[1] if len(parts) >= 3 else ""


def classify_template_topology(template_slug: str, nodes: list[dict], edges: list[dict]) -> dict:
    """Return topology classification for a single template."""
    template_tables = [
        n for n in nodes if n.get("type") == "Table" and n.get("template") == template_slug
    ]
    table_names = sorted({t["name"] for t in template_tables})

    rel_prefix = f"tbl:{template_slug}:"
    template_edges = [
        e
        for e in edges
        if e.get("type") == "related_to"
        and e.get("src", "").startswith(rel_prefix)
        and e.get("dst", "").startswith(rel_prefix)
    ]

    fact_tables: set[str] = set()
    dim_tables: set[str] = set()
    bidirectional_count = 0
    inactive_count = 0
    # For role-playing dim detection: (from_table, to_table) -> [from_col, ...]
    join_cols: dict[tuple[str, str], list[str]] = defaultdict(list)

    for e in template_edges:
        ft = _table_name_from_id(e["src"])
        tt = _table_name_from_id(e["dst"])
        props = e.get("props") or {}
        cardinality = props.get("cardinality", "")
        if cardinality == "many_to_one":
            fact_tables.add(ft)
            dim_tables.add(tt)
        if props.get("cross_filter") == "both":
            bidirectional_count += 1
        if props.get("active") is False:
            inactive_count += 1
        from_col = props.get("from_col", "")
        if from_col:
            join_cols[(ft, tt)].append(from_col)

    role_playing_dims = []
    for (ft, tt), cols in join_cols.items():
        if len(cols) >= 2 and len(set(cols)) >= 2:
            role_playing_dims.append(
                {
                    "from_table": ft,
                    "to_table": tt,
                    "from_cols": sorted(set(cols)),
                }
            )
    role_playing_dims.sort(key=lambda r: (r["from_table"], r["to_table"]))

    has_calendar_dim = any(_CALENDAR_NAME_RE.match(n) for n in table_names)
    has_scenario_dim = any(_SCENARIO_NAME_RE.match(n) for n in table_names)

    return {
        "template_slug": template_slug,
        "table_count": len(table_names),
        "fact_tables": sorted(fact_tables),
        "dim_tables": sorted(dim_tables),
        "relationship_count": len(template_edges),
        "bidirectional_count": bidirectional_count,
        "inactive_count": inactive_count,
        "has_calendar_dim": has_calendar_dim,
        "has_scenario_dim": has_scenario_dim,
        "role_playing_dims": role_playing_dims,
    }


def build_topology_atlas(nodes: list[dict], edges: list[dict]) -> dict:
    """Cluster + summarize across all templates."""
    templates = sorted(
        {n["template"] for n in nodes if n.get("type") == "Table" and n.get("template")}
    )

    per_template: dict[str, dict] = {}
    for slug in templates:
        per_template[slug] = classify_template_topology(slug, nodes, edges)

    summary = {
        "templates_with_calendar_dim": sum(
            1 for v in per_template.values() if v["has_calendar_dim"]
        ),
        "templates_with_scenario_dim": sum(
            1 for v in per_template.values() if v["has_scenario_dim"]
        ),
        "templates_with_bidirectional_rels": sum(
            1 for v in per_template.values() if v["bidirectional_count"] > 0
        ),
        "templates_with_role_playing_dims": sum(
            1 for v in per_template.values() if v["role_playing_dims"]
        ),
        "total_relationships": sum(v["relationship_count"] for v in per_template.values()),
        "total_bidirectional": sum(v["bidirectional_count"] for v in per_template.values()),
        "total_inactive": sum(v["inactive_count"] for v in per_template.values()),
    }

    return {
        "template_count": len(templates),
        "per_template": per_template,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--nodes", type=Path, default=DEFAULT_NODES)
    parser.add_argument("--edges", type=Path, default=DEFAULT_EDGES)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    nodes = [json.loads(line) for line in args.nodes.expanduser().read_text().splitlines() if line]
    edges = [json.loads(line) for line in args.edges.expanduser().read_text().splitlines() if line]
    atlas = build_topology_atlas(nodes, edges)

    out = args.out.expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(atlas, indent=2, ensure_ascii=False) + "\n")

    s = atlas["summary"]
    print(f"templates: {atlas['template_count']}")
    print(f"  with calendar dim:        {s['templates_with_calendar_dim']:3}")
    print(f"  with scenario dim:        {s['templates_with_scenario_dim']:3}")
    print(f"  with bidirectional rels:  {s['templates_with_bidirectional_rels']:3}")
    print(f"  with role-playing dims:   {s['templates_with_role_playing_dims']:3}")
    print(f"total relationships: {s['total_relationships']}")
    print(f"  bidirectional: {s['total_bidirectional']}")
    print(f"  inactive: {s['total_inactive']}")
    print(f"out: {out}")


if __name__ == "__main__":
    main()
