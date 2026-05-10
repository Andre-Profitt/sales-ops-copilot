from __future__ import annotations

import json

import pytest

from scripts.sales.rw_zebra_kg_translator import MeasureCatalog
from scripts.sales.rw_zebra_transfer_rebuilder import (
    TransferGateError,
    rebuild_native_report_from_dna,
    rebuild_visual_from_dna,
    transfer_gate,
    write_transfer_qa_artifacts,
)


def _visual_types(report: dict) -> list[str]:
    out = []
    for page in report.get("sections", []):
        for vc in page.get("visualContainers", []):
            cfg = json.loads(vc.get("config", "{}"))
            out.append((cfg.get("singleVisual") or {}).get("visualType", ""))
    return out


def _catalog() -> MeasureCatalog:
    return MeasureCatalog(
        by_scenario={
            "AC": "AC",
            "PY": "PY",
            "PL": "PL",
            "FC": "FC",
            "AC-PY": "AC-PY",
            "AC-PY %": "AC-PY %",
            "AC-PL": "AC-PL",
            "AC-PL %": "AC-PL %",
        },
        measure_to_table={
            "AC": "Data",
            "PY": "Data",
            "PL": "Data",
            "FC": "Data",
            "AC-PY": "Data",
            "AC-PY %": "Data",
            "AC-PL": "Data",
            "AC-PL %": "Data",
        },
    )


def _base_dna(**overrides):
    dna = {
        "visual_id": "v1",
        "page_name": "p1",
        "page_display_name": "Home",
        "visual_family": "Tables",
        "visual_type_full": "ZebraBITables98F88148E5424E949E69864664EE1860",
        "bounding_box": {"x": 10, "y": 90, "w": 500, "h": 240},
        "projection_roles": {"Category": ["Data.Stage"], "Values": ["Data.AC"], "PreviousYear": ["Data.PY"]},
        "scenario_pairing": ["AC", "PY"],
        "derived_variance_columns": [
            {"key": "actual-previousYear", "label": "AC-PY", "scenario_pair": ["AC", "PY"], "role": "delta", "format": 1},
            {"key": "actual-previousYear-percent", "label": "AC-PY %", "scenario_pair": ["AC", "PY"], "role": "relative", "format": 2},
        ],
        "column_settings": {"actual": {"tableView": {"markerStyle": 5, "showAsTable": 0, "hidden": False}}},
        "style": {"title": {"text": "Pipeline by stage"}},
        "static_furniture": [],
        "visual_intent": "variance table",
    }
    dna.update(overrides)
    return dna


def test_table_dna_rebuilds_tableex_with_ibcs_columns_and_no_custom_visuals():
    visuals = rebuild_visual_from_dna(_base_dna(), _catalog())

    assert len(visuals) == 1
    cfg = json.loads(visuals[0]["config"])
    sv = cfg["singleVisual"]
    assert sv["visualType"] == "tableEx"
    assert list(sv["columnProperties"]) == ["Data.Stage", "Data.AC", "Data.PY", "Data.AC-PY", "Data.AC-PY %"]
    assert "dataBars" in sv["objects"]


def test_card_dna_rebuilds_composite_kpi_tile_not_generic_single_card():
    card = _base_dna(
        visual_family="Cards",
        visual_type_full="zebraBiCards8085D508EB994C8081CA47C85ABD7C26",
        projection_roles={"Group": ["KPIs.KPI"], "Values": ["Data.AC"], "PreviousYear": ["Data.PY"]},
        visual_intent="KPI strip",
        bounding_box={"x": 10, "y": 90, "w": 300, "h": 120},
    )

    visuals = rebuild_visual_from_dna(card, _catalog())

    assert len(visuals) == 3
    assert [json.loads(v["config"])["singleVisual"]["visualType"] for v in visuals] == ["textbox", "card", "card"]


def test_waterfall_dna_rebuilds_native_waterfall_chart():
    waterfall = _base_dna(
        visual_family="Waterfall",
        visual_type_full="waterfall0221D8FBE40445C1A4E598AA8EF8B506",
        projection_roles={"Category": ["Data.Stage"], "Values": ["Data.AC"]},
        visual_intent="waterfall",
    )

    visuals = rebuild_visual_from_dna(waterfall, _catalog())

    assert len(visuals) == 1
    cfg = json.loads(visuals[0]["config"])
    assert cfg["singleVisual"]["visualType"] == "waterfallChart"
    assert set(cfg["singleVisual"]["projections"]) == {"Category", "Y"}


def test_report_rebuild_preserves_static_furniture_and_gate_blocks_fallbacks():
    source_report = {
        "resourcePackages": [{"resourcePackage": {"name": "ZebraBITables", "type": 0}}],
        "publicCustomVisuals": ["ZebraBITables"],
        "sections": [{"name": "p1", "displayName": "Home", "visualContainers": []}],
    }
    dna = {
        "template_slug": "demo",
        "visuals": [
            _base_dna(static_furniture=[{"visual_id": "header", "visual_type": "textbox", "text": "Sales funnel", "bounding_box": {"x": 8, "y": 16, "w": 400, "h": 40}}])
        ],
    }

    rebuilt = rebuild_native_report_from_dna(dna, source_report, _catalog())
    gate = transfer_gate(source_report, rebuilt, dna=dna, catalog=_catalog())

    assert "textbox" in _visual_types(rebuilt)
    assert gate["source_pages"] == 1
    assert gate["rebuilt_pages"] == 1
    assert gate["custom_visual_leftovers"] == 0
    assert gate["custom_resource_packages"] == 0
    assert gate["fallback_textboxes"] == 0
    assert gate["lost_zebra_visuals"] == 0
    assert gate["unknown_visual_types"] == 0
    assert gate["blank_visual_types"] == 0
    assert gate["unresolved_measure_refs"] == 0
    assert gate["passed"] is True


def test_transfer_gate_fails_when_a_zebra_visual_would_be_lost():
    source_report = {"sections": [{"name": "p1", "displayName": "Home", "visualContainers": []}]}
    dna = {
        "template_slug": "demo",
        "visuals": [
            _base_dna(
                projection_roles={"Category": ["Data.Stage"]},
                scenario_pairing=[],
                derived_variance_columns=[],
            )
        ],
    }
    rebuilt = rebuild_native_report_from_dna(dna, source_report, _catalog())

    gate = transfer_gate(source_report, rebuilt, dna=dna, catalog=_catalog())

    assert gate["passed"] is False
    assert gate["lost_zebra_visuals"] == 1
    assert gate["failures"] == ["lost_zebra_visuals=1"]


def test_rebuild_normalizes_blank_source_furniture_to_native_shape():
    blank = {"x": 1, "y": 2, "width": 3, "height": 4, "config": json.dumps({"name": "blank", "singleVisual": {}})}
    source_report = {"sections": [{"name": "p1", "displayName": "Home", "visualContainers": [blank]}]}
    dna = {"template_slug": "demo", "visuals": []}

    rebuilt = rebuild_native_report_from_dna(dna, source_report, _catalog())
    gate = transfer_gate(source_report, rebuilt, dna=dna, catalog=_catalog())

    assert _visual_types(rebuilt) == ["basicShape"]
    assert gate["blank_visual_types"] == 0
    assert gate["visual_count_delta"] == 0
    assert gate["passed"] is True


def test_transfer_gate_fails_for_blank_and_unknown_visual_types():
    blank = {"config": json.dumps({"name": "blank", "singleVisual": {"visualType": ""}})}
    unknown = {"config": json.dumps({"name": "unknown", "singleVisual": {"visualType": "notARealPowerBIVisual"}})}
    report = {"sections": [{"name": "p1", "displayName": "Home", "visualContainers": [blank, unknown]}]}

    gate = transfer_gate(report, report, known_native_visual_types={"textbox", "card"})

    assert gate["passed"] is False
    assert gate["blank_visual_types"] == 1
    assert gate["unknown_visual_types"] == 1
    assert "blank_visual_types=1" in gate["failures"]
    assert "unknown_visual_types=1" in gate["failures"]


def test_transfer_gate_fails_for_unresolved_measure_references():
    catalog = MeasureCatalog(by_scenario={}, measure_to_table={"Known": "Data"})
    bad = rebuild_visual_from_dna(_base_dna(projection_roles={"Values": ["Data.Missing"]}, scenario_pairing=["AC"]), catalog)[0]
    report = {"sections": [{"name": "p1", "displayName": "Home", "visualContainers": [bad]}]}

    gate = transfer_gate(report, report, catalog=catalog)

    assert gate["passed"] is False
    assert gate["unresolved_measure_refs"] == 1
    assert gate["unresolved_measure_ref_details"] == ["[Home] Data.'Missing'"]


def test_transfer_qa_artifacts_are_written_outside_review_markdown(tmp_path):
    gate = {"passed": False, "failures": ["lost_zebra_visuals=1"], "lost_zebra_visuals": 1}

    json_path, md_path = write_transfer_qa_artifacts(gate, tmp_path, "demo-template")

    assert json_path.name == "transfer_gate_demo-template.json"
    assert md_path.name == "transfer_gate_demo-template.md"
    assert json.loads(json_path.read_text())["lost_zebra_visuals"] == 1
    assert "# Zebra transfer gate: demo-template" in md_path.read_text()
    with pytest.raises(TransferGateError):
        write_transfer_qa_artifacts(gate, tmp_path, "demo-template", fail_on_error=True)
