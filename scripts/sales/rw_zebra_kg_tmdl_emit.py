"""Emit TMDL SemanticModel definitions for extracted Zebra template schemas.

Input:
    data/zebra_kg/schemas/<slug>/

Output:
    Ordered ``{path: text}`` parts suitable for Fabric SemanticModel
    create/update definition payloads.

The emitted model is structurally complete but data-empty: every table gets an
import-mode M ``#table`` partition with zero rows. This is enough for translated
reports to resolve fields and render without "field not found" errors.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_DIR = REPO_ROOT / "data/zebra_kg/schemas"

_SIMPLE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def quote_name(name: str) -> str:
    """TMDL object name, quoted only when grammar requires it."""
    if _SIMPLE_NAME.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def ref_name(table: str, column: str) -> str:
    return f"{quote_name(table)}.{quote_name(column)}"


def tmdl_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def m_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def map_data_type(raw: str | None) -> str:
    raw_l = (raw or "string").lower()
    if raw_l in {"string", "object", "category"}:
        return "string"
    if raw_l in {"int64", "int32", "integer", "long"}:
        return "int64"
    if raw_l in {"float64", "float32", "double", "single"}:
        return "double"
    if raw_l in {"decimal.decimal", "decimal"}:
        return "decimal"
    if raw_l in {"datetime64[ns]", "datetime", "date", "datetime64"}:
        return "dateTime"
    if raw_l in {"bool", "boolean"}:
        return "boolean"
    return "string"


def _load_table_files(schema_dir: Path) -> list[tuple[str, Path, dict[str, Any]]]:
    tables_dir = schema_dir / "tables"
    if not tables_dir.exists():
        raise FileNotFoundError(f"missing tables directory: {tables_dir}")

    by_name: dict[str, tuple[str, Path, dict[str, Any]]] = {}
    for path in sorted(tables_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data.get("name") or path.stem
        by_name[name] = (name, path, data)

    ordered_names: list[str] = []
    model_json = schema_dir / "model.json"
    if model_json.exists():
        model = json.loads(model_json.read_text(encoding="utf-8"))
        ordered_names = [
            table.get("name")
            for table in model.get("tables", [])
            if table.get("name") in by_name
        ]
    ordered_names.extend(name for name in sorted(by_name) if name not in ordered_names)
    return [by_name[name] for name in ordered_names]


def _synthetic_table_path(name: str) -> Path:
    stem = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_") or "Table"
    return Path(f"{stem}.json")


def _merge_extra_columns(
    table_entries: list[tuple[str, Path, dict[str, Any]]],
    extra_columns: dict[str, set[str]] | None,
) -> list[tuple[str, Path, dict[str, Any]]]:
    if not extra_columns:
        return table_entries

    merged: list[tuple[str, Path, dict[str, Any]]] = []
    seen_tables: set[str] = set()
    for name, path, table in table_entries:
        cloned = json.loads(json.dumps(table))
        existing = {str(c["name"]) for c in cloned.get("columns", [])}
        for column in sorted(extra_columns.get(name, set()) - existing):
            cloned.setdefault("columns", []).append({"name": column, "data_type": "string"})
        merged.append((name, path, cloned))
        seen_tables.add(name)

    for table_name in sorted(set(extra_columns) - seen_tables):
        merged.append(
            (
                table_name,
                _synthetic_table_path(table_name),
                {
                    "name": table_name,
                    "columns": [
                        {"name": column, "data_type": "string"}
                        for column in sorted(extra_columns[table_name])
                    ],
                    "measures": [],
                },
            )
        )
    return merged


def _measure_block(measure: dict[str, Any]) -> list[str]:
    name = str(measure["name"])
    expression = str(measure.get("expression") or "BLANK()").rstrip()
    lines = [f"\tmeasure {quote_name(name)} ="]
    if "\n" in expression:
        lines.extend(f"\t\t{line}" if line else "" for line in expression.splitlines())
    else:
        lines.append(f"\t\t{expression}")
    if fmt := measure.get("format_string"):
        lines.append(f"\t\tformatString: {fmt}")
    return lines


def _table_tmdl(table: dict[str, Any]) -> str:
    table_name = str(table["name"])
    lines = [f"table {quote_name(table_name)}", ""]

    for column in table.get("columns", []):
        col_name = str(column["name"])
        lines.extend(
            [
                f"\tcolumn {quote_name(col_name)}",
                f"\t\tdataType: {map_data_type(column.get('data_type'))}",
                "\t\tsummarizeBy: none",
                f"\t\tsourceColumn: {quote_name(col_name)}",
                "",
            ]
        )

    for measure in table.get("measures", []):
        lines.extend(_measure_block(measure))
        lines.append("")

    column_names = [str(c["name"]) for c in table.get("columns", [])]
    m_columns = ", ".join(m_string(c) for c in column_names)
    partition = f"{table_name}-partition"
    lines.extend(
        [
            f"\tpartition {quote_name(partition)} = m",
            "\t\tmode: import",
            "\t\tsource =",
            f"\t\t\tlet Source = #table({{{m_columns}}}, {{}}) in Source",
            "",
        ]
    )
    return "\n".join(lines)


def _relationship_name(index: int, rel: dict[str, Any]) -> str:
    return rel.get("name") or (
        f"rel_{index}_{rel['from_table']}_{rel['from_col']}_to_"
        f"{rel['to_table']}_{rel['to_col']}"
    )


def _relationships_tmdl(relationships: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    valid = [
        rel
        for rel in relationships
        if all(
            isinstance(rel.get(key), str)
            for key in ("from_table", "from_col", "to_table", "to_col")
        )
    ]
    for idx, rel in enumerate(valid, start=1):
        name = re.sub(r"[^A-Za-z0-9_]+", "_", _relationship_name(idx, rel)).strip("_")
        lines.append(f"relationship {quote_name(name or f'rel_{idx}')}")
        if rel.get("active") is False:
            lines.append("\tisActive: false")
        lines.append(f"\tfromColumn: {ref_name(rel['from_table'], rel['from_col'])}")
        lines.append(f"\ttoColumn: {ref_name(rel['to_table'], rel['to_col'])}")
        lines.append("")
    return "\n".join(lines)


def _load_relationships(schema_dir: Path) -> list[dict[str, Any]]:
    model_json = schema_dir / "model.json"
    if model_json.exists():
        model = json.loads(model_json.read_text(encoding="utf-8"))
        if model.get("relationships"):
            return list(model["relationships"])
    rel_json = schema_dir / "relationships.json"
    if not rel_json.exists():
        return []
    data = json.loads(rel_json.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return list(data.get("relationships") or [])
    return list(data)


def emit_tmdl_parts(
    slug: str,
    display_name: str | None = None,
    extra_columns: dict[str, set[str]] | None = None,
) -> dict[str, str]:
    schema_dir = SCHEMAS_DIR / slug
    if not schema_dir.exists():
        raise FileNotFoundError(f"missing schema directory: {schema_dir}")

    model_name = display_name or f"sm_zbr_{slug}"
    table_entries = _merge_extra_columns(_load_table_files(schema_dir), extra_columns)
    relationships = _load_relationships(schema_dir)
    table_names = [name for name, _, _ in table_entries]

    parts: dict[str, str] = {
        "definition.pbism": json.dumps(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/"
                    "semanticModel/definitionProperties/1.0.0/schema.json"
                ),
                "version": "4.2",
                "settings": {"qnaEnabled": False},
            },
            indent=2,
        ),
        "definition/database.tmdl": "database\n\tcompatibilityLevel: 1567\n",
        "definition/model.tmdl": "\n".join(
            [
                "model Model",
                "\tculture: en-US",
                "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
                "\tdiscourageImplicitMeasures",
                "",
                *(f"ref table {quote_name(name)}" for name in table_names),
                "",
            ]
        ),
        "definition/relationships.tmdl": _relationships_tmdl(relationships),
        ".platform": json.dumps(
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/"
                    "gitIntegration/platformProperties/2.0.0/schema.json"
                ),
                "metadata": {
                    "type": "SemanticModel",
                    "displayName": model_name,
                    "description": (
                        "Native blank semantic model emitted from Zebra BI template "
                        f"schema {slug}."
                    ),
                },
                "config": {
                    "version": "2.0",
                    "logicalId": "00000000-0000-0000-0000-000000000000",
                },
            },
            indent=2,
        ),
    }
    for _name, path, table in table_entries:
        parts[f"definition/tables/{path.stem}.tmdl"] = _table_tmdl(table)
    return parts


def measure_count(slug: str) -> int:
    return sum(
        len(table.get("measures", []))
        for _, _, table in _load_table_files(SCHEMAS_DIR / slug)
    )


def column_catalog(slug: str) -> dict[str, set[str]]:
    return {
        name: {str(c["name"]) for c in table.get("columns", [])}
        for name, _, table in _load_table_files(SCHEMAS_DIR / slug)
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("slug")
    args = parser.parse_args()
    for path, text in emit_tmdl_parts(args.slug).items():
        print(f"--- {path} ({len(text.encode('utf-8'))} bytes)")
