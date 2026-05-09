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

Notes on pbixray column names (probed 2026-05-09 against Zebra CRM Sales
pipeline demo v2.pbix):
  - dax_measures: TableName, Name, Expression, DisplayFolder, Description
    (no FormatString — .get("FormatString", "") returns "" for real files)
  - relationships: FromTableName, FromColumnName, ToTableName, ToColumnName,
    Cardinality (e.g. "M:1"), CrossFilteringBehavior (e.g. "Single"),
    IsActive (0/1 int)
  - schema: TableName, ColumnName, PandasDataType
  - tables: pandas.StringArray — list() converts to list[str]
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    scenario: str | None = None  # "AC" | "PY" | "PL" | "FC" | None
    is_variance: bool = False


@dataclass(frozen=True)
class Relationship:
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    cardinality: str  # "many_to_one" | "one_to_many" | "one_to_one" | "many_to_many"
    cross_filter: str  # "single" | "both"
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

# pbixray uses "Single" / "Both" (capital first letter); the PBIX XML also
# contains "OneDirection" / "BothDirections" in some versions — cover both.
_CROSSFILTER_MAP = {
    "Single": "single",
    "Both": "both",
    "OneDirection": "single",
    "BothDirections": "both",
    "Automatic": "single",  # PBIX default for M:1 — treat as single
}


def shape_datamodel(pbix: Any, template_slug: str) -> DataModel:
    """Translate a pbixray.PBIXRay-shaped object into our DataModel dataclasses.

    `pbix` must expose: .tables (list[str]), .dax_measures (list[dict]),
    .relationships (list[dict]), .schema (list[dict]). Real pbixray and the
    test stub both satisfy this interface after the caller converts DataFrames
    to records (see integration test for the adapter pattern).
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
            cardinality=_CARDINALITY_MAP.get(row.get("Cardinality", ""), "unknown"),
            cross_filter=_CROSSFILTER_MAP.get(row.get("CrossFilteringBehavior", ""), "single"),
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
    parser.add_argument("--source-dir", type=Path, required=True, help="Dir of Zebra PBIX files")
    parser.add_argument(
        "--analysis-dir", type=Path, required=True, help="Dir of existing visual-side miner output"
    )
    parser.add_argument(
        "--out-dir", type=Path, required=True, help="Output dir for new graph artifacts"
    )
    args = parser.parse_args()
    # Emit logic added in Task 3.
    raise SystemExit("emit not yet wired — see Task 3")


if __name__ == "__main__":
    main()
