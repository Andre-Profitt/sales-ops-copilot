from __future__ import annotations

import json

from scripts.sales.rw_zebra_kg_tmdl_emit import emit_tmdl_parts, map_data_type, quote_name


def test_quote_name_only_quotes_when_required():
    assert quote_name("Values") == "Values"
    assert quote_name("Period calculation") == "'Period calculation'"


def test_map_schema_data_types_to_tmdl_types():
    assert map_data_type("string") == "string"
    assert map_data_type("Int64") == "int64"
    assert map_data_type("Float64") == "double"
    assert map_data_type("datetime64[ns]") == "dateTime"
    assert map_data_type("decimal.Decimal") == "decimal"


def test_emit_tmdl_parts_for_one_zebra_schema_round_trips_core_declarations():
    parts = emit_tmdl_parts("cost-management-power-bi-template")

    assert "definition.pbism" in parts
    assert "definition/database.tmdl" in parts
    assert "definition/model.tmdl" in parts
    assert "definition/relationships.tmdl" in parts
    assert any(path.startswith("definition/tables/") for path in parts)

    pbism = json.loads(parts["definition.pbism"])
    assert pbism["version"] == "4.2"
    assert "compatibilityLevel: 1567" in parts["definition/database.tmdl"]

    model = parts["definition/model.tmdl"]
    assert "model Model" in model
    assert "ref table" in model

    table_blob = "\n".join(
        text for path, text in parts.items() if path.startswith("definition/tables/")
    )
    assert "table AccountHierarchyTable" in table_blob
    assert "\tcolumn" in table_blob
    assert "\tmeasure" in table_blob
    assert "\tpartition" in table_blob
    assert "mode: import" in table_blob
    assert "#table({" in table_blob

    relationships = parts["definition/relationships.tmdl"]
    assert "relationship" in relationships
    assert "fromColumn:" in relationships
    assert "toColumn:" in relationships
