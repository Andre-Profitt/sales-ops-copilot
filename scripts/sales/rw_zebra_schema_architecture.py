"""Mine Zebra template schemas for semantic architecture patterns.

This is deliberately datamodel-focused.  The visual transfer layer tells us how
Zebra looks; this module tells us how Zebra templates structure dimensions,
date roles, scenarios, sort keys, and relationships.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMAS = REPO_ROOT / "data/zebra_kg/schemas"
DEFAULT_OUT = REPO_ROOT / "docs/sales/RW_ZEBRA_SCHEMA_ARCHITECTURE_REVIEW.md"

CALENDAR_RE = re.compile(r"^(d_)?(calendar|date|time)(s|\s.*)?$|^(DateTableTemplate|LocalDateTable)_", re.I)
SCENARIO_RE = re.compile(r"^(d_)?(scenarios?|versions?)$", re.I)
ORDER_COL_RE = re.compile(r"(sort|order|rank|ranking|ordinal|sequence|stage_?num|monthno|quarterno)$", re.I)
KPI_RE = re.compile(r"\bkpi\b|kpi_", re.I)


def _clean_name(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    return "" if text.lower() == "nan" else text


def _schema_dirs(root: Path) -> list[Path]:
    return sorted(path for path in root.iterdir() if path.is_dir() and (path / "model.json").exists())


def _load_model(schema_dir: Path) -> dict[str, Any]:
    return json.loads((schema_dir / "model.json").read_text(encoding="utf-8"))


def _columns_by_table(model: dict[str, Any]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = defaultdict(set)
    for column in model.get("columns", []):
        table = _clean_name(column.get("table"))
        name = _clean_name(column.get("name"))
        if table and name:
            out[table].add(name)
    return dict(out)


def classify_zebra_schema(schema_dir: Path) -> dict[str, Any]:
    model = _load_model(schema_dir)
    slug = str(model.get("template_slug") or schema_dir.name)
    tables = sorted(name for table in model.get("tables", []) if (name := _clean_name(table.get("name"))))
    relationships = list(model.get("relationships", []))
    columns_by_table = _columns_by_table(model)

    fact_tables: set[str] = set()
    dim_tables: set[str] = set()
    join_cols: dict[tuple[str, str], set[str]] = defaultdict(set)
    rel_cross_filter = Counter()
    rel_cardinality = Counter()

    for rel in relationships:
        from_table = _clean_name(rel.get("from_table"))
        to_table = _clean_name(rel.get("to_table"))
        from_col = _clean_name(rel.get("from_col"))
        if from_table:
            fact_tables.add(from_table)
        if to_table:
            dim_tables.add(to_table)
            if from_col:
                join_cols[(from_table, to_table)].add(from_col)
        rel_cross_filter[str(rel.get("cross_filter") or "unknown")] += 1
        rel_cardinality[str(rel.get("cardinality") or "unknown")] += 1

    role_playing_dims = [
        {"from_table": ft, "to_table": tt, "from_cols": sorted(cols)}
        for (ft, tt), cols in join_cols.items()
        if len(cols) > 1
    ]
    role_playing_dims.sort(key=lambda row: (row["from_table"], row["to_table"]))

    calendar_tables = sorted(table for table in tables if CALENDAR_RE.search(table))
    scenario_dim_tables = sorted(table for table in tables if SCENARIO_RE.search(table))
    kpi_tables = sorted(
        table
        for table in tables
        if table not in fact_tables
        if KPI_RE.search(table) or any(KPI_RE.search(column) for column in columns_by_table.get(table, set()))
    )
    ordered_dimension_columns = {
        table: sorted(column for column in columns if ORDER_COL_RE.search(column))
        for table, columns in columns_by_table.items()
        if table in dim_tables and any(ORDER_COL_RE.search(column) for column in columns)
    }
    scenario_columns = {
        table: sorted(
            column
            for column in columns
            if column.lower() in {"scenario", "version"} or "scenario" in column.lower()
        )
        for table, columns in columns_by_table.items()
        if any(column.lower() in {"scenario", "version"} or "scenario" in column.lower() for column in columns)
    }

    long_fact_kpi_scenario = any(
        {"Value", "KPI_ID", "Scenario"} <= columns_by_table.get(table, set()) for table in fact_tables
    )

    return {
        "template_slug": slug,
        "table_count": len(tables),
        "relationship_count": len(relationships),
        "fact_tables": sorted(fact_tables),
        "dim_tables": sorted(dim_tables),
        "calendar_tables": calendar_tables,
        "scenario_dim_tables": scenario_dim_tables,
        "kpi_tables": kpi_tables,
        "ordered_dimension_columns": ordered_dimension_columns,
        "scenario_columns": scenario_columns,
        "role_playing_dims": role_playing_dims,
        "long_fact_kpi_scenario": long_fact_kpi_scenario,
        "relationship_cross_filter_counts": dict(rel_cross_filter),
        "relationship_cardinality_counts": dict(rel_cardinality),
        "inactive_relationship_count": sum(1 for rel in relationships if rel.get("active") is False),
        "bidirectional_relationship_count": sum(1 for rel in relationships if rel.get("cross_filter") == "both"),
    }


def build_zebra_schema_benchmark(schemas_root: Path = DEFAULT_SCHEMAS) -> dict[str, Any]:
    templates = [classify_zebra_schema(schema_dir) for schema_dir in _schema_dirs(schemas_root)]
    total_relationships = sum(t["relationship_count"] for t in templates)
    single_direction = sum(t["relationship_cross_filter_counts"].get("single", 0) for t in templates)
    bidirectional = sum(t["bidirectional_relationship_count"] for t in templates)
    inactive = sum(t["inactive_relationship_count"] for t in templates)

    summary = {
        "template_count": len(templates),
        "total_relationships": total_relationships,
        "single_direction_relationships": single_direction,
        "bidirectional_relationships": bidirectional,
        "inactive_relationships": inactive,
        "templates_with_calendar_tables": sum(1 for t in templates if t["calendar_tables"]),
        "templates_with_role_playing_dims": sum(1 for t in templates if t["role_playing_dims"]),
        "templates_with_ordered_dimensions": sum(1 for t in templates if t["ordered_dimension_columns"]),
        "templates_with_scenario_columns": sum(1 for t in templates if t["scenario_columns"]),
        "templates_with_scenario_dims": sum(1 for t in templates if t["scenario_dim_tables"]),
        "templates_with_kpi_tables": sum(1 for t in templates if t["kpi_tables"]),
        "templates_with_long_fact_kpi_scenario": sum(1 for t in templates if t["long_fact_kpi_scenario"]),
    }

    guidance = [
        {
            "pattern": "single_direction_star",
            "evidence": f"{single_direction}/{total_relationships} relationships use single-direction filtering.",
            "rw_application": "Keep RW relationships conservative and do not introduce bidirectional filters to make slicers feel easier.",
        },
        {
            "pattern": "role_playing_dates",
            "evidence": f"{summary['templates_with_role_playing_dims']}/{summary['template_count']} schemas use role-playing dimensions and {inactive} inactive relationships exist in the corpus.",
            "rw_application": "Add explicit transition-date roles before exposing Stage Move FQ or Forecast Move FQ slicers.",
        },
        {
            "pattern": "ordered_dimensions",
            "evidence": f"{summary['templates_with_ordered_dimensions']}/{summary['template_count']} schemas carry sort/order/rank columns on dimensions.",
            "rw_application": "Promote stage order into a canonical d_stage dimension instead of relying on label sorting.",
        },
        {
            "pattern": "scenario_as_axis",
            "evidence": f"{summary['templates_with_scenario_columns']}/{summary['template_count']} schemas carry scenario/version as data columns, while only {summary['templates_with_scenario_dims']} use scenario dimensions.",
            "rw_application": "Treat Motion as a labeled analytic axis or explicit measure family, not a universal page slicer.",
        },
        {
            "pattern": "kpi_dictionary",
            "evidence": f"{summary['templates_with_kpi_tables']}/{summary['template_count']} schemas include KPI/table metadata; sales-funnel uses KPI_ID with an inactive KPI relationship.",
            "rw_application": "Keep RW KPI/page contracts executable and consider a future d_kpi metadata table for governed explorer behavior.",
        },
    ]

    return {
        "schema": "rw-zebra-schema-architecture.v1",
        "summary": summary,
        "guidance": guidance,
        "templates": templates,
    }


def write_markdown(result: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = result["summary"]
    lines = [
        "# RW Zebra Schema Architecture Review",
        "",
        "This mines `data/zebra_kg/schemas/<slug>/model.json` across the Zebra template corpus for semantic-model patterns that should inform RW dashboard architecture.",
        "",
        "## Corpus Summary",
        "",
        f"- Templates: {summary['template_count']}",
        f"- Relationships: {summary['total_relationships']}",
        f"- Single-direction relationships: {summary['single_direction_relationships']}",
        f"- Bidirectional relationships: {summary['bidirectional_relationships']}",
        f"- Inactive relationships: {summary['inactive_relationships']}",
        f"- Templates with calendar tables: {summary['templates_with_calendar_tables']}",
        f"- Templates with role-playing dimensions: {summary['templates_with_role_playing_dims']}",
        f"- Templates with ordered dimensions: {summary['templates_with_ordered_dimensions']}",
        f"- Templates with scenario columns: {summary['templates_with_scenario_columns']}",
        f"- Templates with KPI metadata tables: {summary['templates_with_kpi_tables']}",
        "",
        "## RW Architecture Guidance",
        "",
        "| Zebra pattern | Evidence | RW application |",
        "| --- | --- | --- |",
    ]
    for item in result["guidance"]:
        lines.append(f"| `{item['pattern']}` | {item['evidence']} | {item['rw_application']} |")

    lines += [
        "",
        "## Sales Funnel Exemplar",
        "",
    ]
    sales_funnel = next(
        (t for t in result["templates"] if t["template_slug"] == "sales-funnel-power-bi-template"),
        None,
    )
    if sales_funnel:
        lines += [
            f"- Fact tables: {', '.join(f'`{table}`' for table in sales_funnel['fact_tables'])}",
            f"- Dimension tables: {', '.join(f'`{table}`' for table in sales_funnel['dim_tables'])}",
            f"- KPI tables: {', '.join(f'`{table}`' for table in sales_funnel['kpi_tables']) or '-'}",
            f"- Scenario columns: {json.dumps(sales_funnel['scenario_columns'], sort_keys=True)}",
            f"- Ordered dimension columns: {json.dumps(sales_funnel['ordered_dimension_columns'], sort_keys=True)}",
            f"- Long fact + KPI + scenario pattern: `{sales_funnel['long_fact_kpi_scenario']}`",
            "",
            "The direct RW lift is architectural, not literal: keep the KPI contract executable, treat motion/scenario as an explicit analytic axis, and move business ordering into dimensions.",
        ]

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMAS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = build_zebra_schema_benchmark(args.schemas.expanduser())
    write_markdown(result, args.out.expanduser())
    if args.json:
        args.json.expanduser().parent.mkdir(parents=True, exist_ok=True)
        args.json.expanduser().write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
