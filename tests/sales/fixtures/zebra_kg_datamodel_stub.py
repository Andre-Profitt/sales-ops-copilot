"""Pure-Python stub mimicking the surface of pbixray.PBIXRay we depend on.

Lets us unit-test the shaping layer without binary PBIX files.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StubPBIXRay:
    """Mimics the attributes of pbixray.PBIXRay used by rw_zebra_kg_datamodel."""

    tables: list[str]
    dax_measures: list[dict]  # rows: TableName, Name, Expression, FormatString
    relationships: list[dict]  # rows: FromTableName, FromColumnName, ToTableName,
    #       ToColumnName, Cardinality,
    #       CrossFilteringBehavior, IsActive
    schema: list[dict]  # rows: TableName, ColumnName, PandasDataType


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
                "Expression": 'CALCULATE(COUNTROWS(f_opp), f_opp[Direction]="forward")',
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
                "CrossFilteringBehavior": "Single",
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
