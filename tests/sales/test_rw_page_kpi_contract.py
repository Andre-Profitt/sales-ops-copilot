"""Contract tests for the RW KPI-targeted Power BI pages."""

from __future__ import annotations

import json
from dataclasses import replace

from scripts.sales.rw_compose_all_pages import compose_report, validate_contract_pages
from scripts.sales.rw_dashboard_harness import audit
from scripts.sales.rw_dashboard_visual_qa import audit_report
from scripts.sales.rw_page_kpi_contract import (
    PAGE_KPI_CONTRACTS,
    KPIPlacement,
    required_measures,
    validate_decision_contracts,
)
from scripts.sales.rw_filter_bar import FILTER_REFS_BY_PAGE, FORBIDDEN_MOTION_SLICER_REF
from scripts.sales.rw_metric_basis_audit import audit_metric_basis
from scripts.sales.rw_semantic_filter_audit import audit_semantic_filter_flow


def _single_visual(vc: dict) -> dict:
    return json.loads(vc["config"])["singleVisual"]


def _visual_type(vc: dict) -> str:
    return _single_visual(vc)["visualType"]


def _page(report: dict, display_name: str) -> dict:
    return next(s for s in report["sections"] if s["displayName"] == display_name)


def _single_contract(page: str, **overrides):
    return {page: replace(PAGE_KPI_CONTRACTS[page], **overrides)}


def test_decision_contracts_are_self_consistent():
    assert validate_decision_contracts() == []


def test_all_target_pages_compose_against_declared_kpi_contracts():
    report = compose_report({"sections": []})

    assert set(PAGE_KPI_CONTRACTS) <= {s["displayName"] for s in report["sections"]}
    assert validate_contract_pages(report) == []
    for page in PAGE_KPI_CONTRACTS:
        assert _page(report, page)["visualContainers"], page


def test_target_pages_use_only_native_power_bi_visual_types():
    report = compose_report({"sections": []})
    allowed = {"basicShape", "textbox", "card", "tableEx", "clusteredBarChart", "pivotTable", "slicer"}

    unexpected: list[tuple[str, str]] = []
    for page in PAGE_KPI_CONTRACTS:
        for vc in _page(report, page)["visualContainers"]:
            visual_type = _visual_type(vc)
            if visual_type not in allowed:
                unexpected.append((page, visual_type))

    assert unexpected == []


def test_target_pages_follow_page_specific_slice_controls():
    report = compose_report({"sections": []})

    for page in PAGE_KPI_CONTRACTS:
        slicer_visuals = [vc for vc in _page(report, page)["visualContainers"] if _visual_type(vc) == "slicer"]
        slicers = [_single_visual(vc) for vc in slicer_visuals]
        refs = {slicer["projections"]["Values"][0]["queryRef"] for slicer in slicers}
        assert refs == FILTER_REFS_BY_PAGE[page], page
        assert FORBIDDEN_MOTION_SLICER_REF not in refs, page
        for slicer in slicer_visuals:
            assert slicer["width"] >= 180, page
            assert slicer["height"] >= 62, page


def test_kpi_explorer_adds_slice_and_dice_views_without_arr_acv_blend():
    report = compose_report({"sections": []})
    explorer = _page(report, "RW KPI Explorer")
    encoded = "\n".join(vc["config"] for vc in explorer["visualContainers"])

    assert sum(1 for vc in explorer["visualContainers"] if _visual_type(vc) == "slicer") == 3
    assert "d_region.region" in encoded
    assert "d_calendar.fiscal_quarter" in encoded
    assert "f_opportunity.stage_name" in encoded
    assert "Total Open Pipeline ARR" in encoded
    assert "Total Open Renewal ACV" in encoded
    assert "Total Open Pipeline Value" not in encoded


def test_semantic_filter_audit_blocks_motion_slicer_policy_regression():
    report = compose_report({"sections": []})
    result = audit_semantic_filter_flow(report=report)

    assert result["counts"]["critical"] == 0
    assert result["counts"]["high"] == 0
    assert {finding["id"] for finding in result["findings"]} == {
        "transition_date_role:f_stage_transition",
        "transition_date_role:f_forecast_transition",
    }


def test_target_pages_have_no_plain_card_or_plain_table_visual_debt():
    report = compose_report({"sections": []})
    findings = [
        finding
        for finding in audit(report)
        if finding.startswith("[plain-card]") or finding.startswith("[plain-table]")
    ]

    assert findings == []


def test_total_open_pipeline_value_is_the_only_cross_motion_measure():
    report = compose_report({"sections": []})
    encoded_by_page = {
        section["displayName"]: "\n".join(v["config"] for v in section["visualContainers"])
        for section in report["sections"]
    }

    pages_with_cross_motion_value = [
        page for page, encoded in encoded_by_page.items() if "Total Open Pipeline Value" in encoded
    ]

    assert required_measures() >= {"Total Open Pipeline Value", "Total Open Pipeline ARR"}
    assert pages_with_cross_motion_value == ["Forecast"]
    assert PAGE_KPI_CONTRACTS["Forecast"].caveat.startswith(
        "Total Open Pipeline Value is the only explicit cross-motion value measure"
    )


def test_what_changed_visual_qa_has_no_wall_of_cards():
    report = compose_report({"sections": []})
    what_changed = _page(report, "What Changed")

    result = audit_report({"sections": [what_changed]})
    findings = [f for f in result["findings"] if f["severity"] in {"medium", "high", "critical"}]
    card_count = sum(1 for vc in what_changed["visualContainers"] if _visual_type(vc) == "card")

    assert card_count < 8
    assert findings == []


def test_what_changed_uses_native_visual_types_only():
    report = compose_report({"sections": []})
    what_changed = _page(report, "What Changed")
    visual_types = {_visual_type(vc) for vc in what_changed["visualContainers"]}

    assert visual_types <= {"basicShape", "card", "tableEx", "textbox", "slicer"}
    assert not any(kind.startswith("ZebraBI") for kind in visual_types)


def test_what_changed_applies_zebra_native_table_grammar_to_movement_ledger():
    report = compose_report({"sections": []})
    what_changed = _page(report, "What Changed")
    ledgers = [
        _single_visual(vc)
        for vc in what_changed["visualContainers"]
        if "Stage Moves Count 7d" in vc["config"]
    ]

    assert len(ledgers) == 1
    ledger = ledgers[0]
    assert ledger["visualType"] in {"tableEx", "pivotTable"}
    assert list(ledger["columnProperties"]) == [
        "f_stage_transition.Stage Moves Count 7d",
        "f_stage_transition.Stage Moves ARR 7d",
        "f_opportunity.New Opps Count 7d",
        "f_opportunity.Closed Won Count 7d",
        "f_opportunity.Closed Lost Count 7d",
    ]
    objects = ledger.get("objects") or {}
    assert objects["stylePreset"] == {
        "source": "zebra-visual-dna",
        "pattern": "compact-movement-ledger",
        "visual_intent": "movement table",
    }
    assert objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"
    assert "dataBars" in objects


def test_what_changed_exception_band_uses_zebra_ledger_not_scorecards():
    report = compose_report({"sections": []})
    what_changed = _page(report, "What Changed")
    exception_ledgers = [
        _single_visual(vc)
        for vc in what_changed["visualContainers"]
        if _visual_type(vc) == "tableEx" and "At Risk Opps ARR" in vc["config"]
    ]

    assert len(exception_ledgers) == 1
    ledger = exception_ledgers[0]
    assert list(ledger["columnProperties"]) == [
        "f_opportunity.At Risk Opps Count",
        "f_opportunity.At Risk Opps ARR",
        "f_opportunity.Watch Opps Count",
        "f_opportunity.Watch Opps ARR",
        "f_opportunity.Healthy Moves Count",
        "f_opportunity.Healthy Moves ARR",
    ]
    objects = ledger.get("objects") or {}
    assert objects["stylePreset"] == {
        "source": "zebra-visual-dna",
        "pattern": "exception-band-ledger",
        "visual_intent": "exception movement ledger",
    }
    assert objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"
    assert {"columnHeaders", "values", "grid"} <= set(objects)
    assert not [
        _single_visual(vc)
        for vc in what_changed["visualContainers"]
        if _visual_type(vc) == "card" and any(token in vc["config"] for token in ("At Risk", "Watch", "Healthy"))
    ]


def test_rw_zebra_native_cards_avoid_pastel_rag_tile_surfaces():
    report = compose_report({"sections": []})
    encoded = "\n".join(
        vc["config"]
        for page in ("What Changed", "Stage Hygiene")
        for vc in _page(report, page)["visualContainers"]
    )

    for pastel in ("#ffeeee", "#fff8e6", "#eef9ee", "#FFEEEE", "#FFF8E6", "#EEF9EE"):
        assert pastel not in encoded


def test_stage_hygiene_visual_qa_has_no_medium_plus_findings():
    report = compose_report({"sections": []})
    stage_hygiene = _page(report, "Stage Hygiene")

    result = audit_report({"sections": [stage_hygiene]})
    findings = [f for f in result["findings"] if f["severity"] in {"medium", "high", "critical"}]
    card_count = sum(1 for vc in stage_hygiene["visualContainers"] if _visual_type(vc) == "card")

    assert card_count < 8
    assert findings == []


def test_stage_hygiene_uses_native_visual_types_only():
    report = compose_report({"sections": []})
    stage_hygiene = _page(report, "Stage Hygiene")
    visual_types = {_visual_type(vc) for vc in stage_hygiene["visualContainers"]}

    assert visual_types <= {"basicShape", "card", "tableEx", "textbox", "slicer"}
    assert not any(kind.startswith("ZebraBI") for kind in visual_types)


def test_stage_hygiene_hero_and_process_cards_use_zebra_native_card_grammar():
    report = compose_report({"sections": []})
    stage_hygiene = _page(report, "Stage Hygiene")
    cards = [_single_visual(vc) for vc in stage_hygiene["visualContainers"] if _visual_type(vc) == "card"]

    assert len(cards) == 7
    for card in cards:
        objects = card.get("objects") or {}
        assert objects["stylePreset"] == {
            "source": "zebra-visual-dna",
            "pattern": "stage-hygiene-process-kpi-card",
            "visual_intent": "Stage Hygiene hero/process KPI",
        }
        assert objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.visualObjectGrammar.v1"
        assert {"background", "border", "labels", "categoryLabels"} <= set(objects)


def test_stage_hygiene_stage_and_detail_tables_use_zebra_ibcs_table_grammar():
    report = compose_report({"sections": []})
    stage_hygiene = _page(report, "Stage Hygiene")
    stage_tables = [
        _single_visual(vc)
        for vc in stage_hygiene["visualContainers"]
        if _visual_type(vc) == "tableEx" and "Stage Forward Pct (LE)" in vc["config"]
    ]
    detail_tables = [
        _single_visual(vc)
        for vc in stage_hygiene["visualContainers"]
        if _visual_type(vc) == "tableEx" and "Stage 4 Forward Pct" in vc["config"]
    ]

    assert len(stage_tables) == 1
    assert len(detail_tables) == 1
    stage_table = stage_tables[0]
    assert list(stage_table["columnProperties"]) == [
        "f_stage_transition.from_stage_name",
        "f_stage_transition.Stage Forward Pct (LE)",
        "f_stage_transition.Stage Backward Pct (LE)",
        "f_stage_transition.Avg Days In Prior Stage (LE)",
        "f_stage_transition.Total Stage Transitions",
        "f_stage_transition.Stage Moves ARR 7d",
    ]
    stage_objects = stage_table.get("objects") or {}
    assert stage_objects["stylePreset"] == {
        "source": "zebra-visual-dna",
        "pattern": "stage-hygiene-variance-table",
        "visual_intent": "stage conversion and time-in-stage table",
    }
    assert stage_objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"
    assert "dataBars" in stage_objects

    detail_objects = detail_tables[0].get("objects") or {}
    assert detail_objects["stylePreset"] == {
        "source": "zebra-visual-dna",
        "pattern": "detail-ledger",
        "visual_intent": "detail ledger",
    }
    assert detail_objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"


def test_product_retention_composes_native_heatmaps_and_ledger():
    report = compose_report({"sections": []})
    product_retention = _page(report, "Product Retention")
    visual_types = [_visual_type(vc) for vc in product_retention["visualContainers"]]
    encoded = "\n".join(vc["config"] for vc in product_retention["visualContainers"])

    assert set(visual_types) <= {"basicShape", "card", "pivotTable", "tableEx", "textbox", "slicer"}
    assert visual_types.count("pivotTable") == 2
    assert visual_types.count("tableEx") == 1
    assert "f_asset_line_item.product_family" in encoded
    assert "d_region.region" in encoded
    assert "f_asset_line_item.industry" in encoded
    assert "Total Open Pipeline Value" not in encoded
    assert "Total Open Renewal ACV" not in encoded
    assert "Open Land ARR" not in encoded
    assert "Open Expand ARR" not in encoded


def test_product_retention_has_consultant_grade_native_visual_qa_and_basis_labels():
    report = compose_report({"sections": []})
    product_retention = _page(report, "Product Retention")

    visual_result = audit_report({"sections": [product_retention]})
    metric_result = audit_metric_basis({"sections": [product_retention]})
    visual_findings = [
        f for f in visual_result["findings"] if f["severity"] in {"medium", "high", "critical"}
    ]

    assert visual_findings == []
    assert metric_result["summary"]["finding_count"] == 0


def test_product_retention_uses_zebra_heatmap_and_detail_table_grammar():
    report = compose_report({"sections": []})
    product_retention = _page(report, "Product Retention")
    matrices = [_single_visual(vc) for vc in product_retention["visualContainers"] if _visual_type(vc) == "pivotTable"]
    ledger = [
        _single_visual(vc)
        for vc in product_retention["visualContainers"]
        if _visual_type(vc) == "tableEx" and "f_asset_line_item.product_area" in vc["config"]
    ]

    assert len(matrices) == 2
    assert len(ledger) == 1
    for matrix in matrices:
        objects = matrix.get("objects") or {}
        assert objects["stylePreset"]["source"] == "zebra-visual-dna"
        assert objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"

    ledger_objects = ledger[0].get("objects") or {}
    assert ledger_objects["stylePreset"] == {
        "source": "zebra-visual-dna",
        "pattern": "detail-ledger",
        "visual_intent": "detail ledger",
    }
    assert ledger_objects["zebraGrammar"]["schema"] == "rw-zebra-native-transfer.columnGrammar.v1"


def test_arr_and_renewal_acv_contracts_stay_separate_by_page():
    renewal_measures = {
        "Total Open Renewal ACV",
        "Total Renewal ACV Due",
        "Renewal Retention Pct (Period)",
        "Total Renewal ACV Won",
        "Total Renewal ACV Lost",
        "Existing ARR Run Rate",
        "Existing ARR Expiring In Period",
        "Business At Risk ARR",
        "Business At Risk Pct",
    }
    growth_arr_measures = {
        "Open Land ARR",
        "Open Expand ARR",
        "Partner ARR",
        "Partner Pct",
        "Total Open Pipeline ARR",
        "Total Land Won Count",
        "Avg Deal Size Won",
        "Closed Won Deals Count",
        "Cross Sell To Acquired ARR",
        "PS ARR Attach Pct",
        "SaaS YoY Growth Pct",
    }

    assert set(PAGE_KPI_CONTRACTS["Renewals"].measures) == renewal_measures
    assert set(PAGE_KPI_CONTRACTS["Growth Mix"].measures) == growth_arr_measures
    assert PAGE_KPI_CONTRACTS["Renewals"].motion == "renewal_acv"
    assert PAGE_KPI_CONTRACTS["Growth Mix"].motion == "land_expand_arr"


def test_contract_gate_catches_missing_required_primary_kpi():
    broken = _single_contract("Forecast", primary_kpis=("forecast_closed_won", "made_up_kpi"))

    errors = validate_decision_contracts(broken)

    assert any("made_up_kpi" in error and "not in kpi_ids" in error for error in errors)
    assert any("made_up_kpi" in error and "no required visual placement" in error for error in errors)


def test_contract_gate_catches_wrong_arr_acv_motion():
    bad_placement = KPIPlacement(
        kpi_id="renewal_retention_rate",
        measure="Total Renewal ACV Won",
        visual_role="hero KPI",
        motion_guardrail="land_expand_arr",
        data_status="clean",
        label="Bad blended renewal card",
    )
    broken = _single_contract("Renewals", placements=(bad_placement,))

    errors = validate_decision_contracts(broken)

    assert any("Land + Expand ARR placement uses Renewal ACV" in error for error in errors)


def test_contract_gate_catches_unlabeled_cross_motion_measure():
    bad_placement = KPIPlacement(
        kpi_id="pipeline_coverage_3x",
        measure="Total Open Pipeline Value",
        visual_role="hero KPI",
        motion_guardrail="cross_motion_labeled",
        data_status="partial",
        label="Open pipeline",
    )
    broken = _single_contract("Forecast", placements=(bad_placement,), caveat="")

    errors = validate_decision_contracts(broken)

    assert any("cross-motion measure" in error and "not explicitly labeled" in error for error in errors)


def test_contract_gate_catches_proxy_counted_as_clean():
    bad_placement = KPIPlacement(
        kpi_id="forecast_accuracy",
        measure="Forecast Slip Pct",
        visual_role="RAG card",
        motion_guardrail="land_expand_arr",
        data_status="clean",
        label="Slip Rate",
        missing_measure="Forecast Accuracy",
    )
    broken = _single_contract("Forecast", placements=(bad_placement,))

    errors = validate_decision_contracts(broken)

    assert any("cannot be counted clean" in error for error in errors)


def test_contract_gate_catches_missing_visual_role_for_required_kpi():
    report = compose_report({"sections": []})
    forecast = _page(report, "Forecast")
    for vc in forecast["visualContainers"]:
        if "Forecast Slip Pct" in vc["config"]:
            config = json.loads(vc["config"])
            config["singleVisual"]["visualType"] = "tableEx"
            vc["config"] = json.dumps(config)
            break

    errors = validate_contract_pages(report)

    assert any("forecast_accuracy" in error and "requires role 'RAG card'" in error for error in errors)
