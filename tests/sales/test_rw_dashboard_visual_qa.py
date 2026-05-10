import json
from pathlib import Path

from scripts.sales._pbir_helpers import build_card_visual, build_rag_card_visual, build_table_visual, build_textbox_visual
from scripts.sales.rw_dashboard_visual_qa import audit_report, render_markdown, write_outputs


def _report(page: str, visuals: list[dict]) -> dict:
    return {"sections": [{"displayName": page, "width": 1280, "height": 720, "visualContainers": visuals}]}


def _codes(findings):
    return {f["code"] for f in findings}


def test_visual_qa_flags_clipped_text_plain_card_and_weak_headers():
    report = _report(
        "VP Ops Scorecard",
        [
            build_textbox_visual(
                "This header is far too long for the available box",
                x=20,
                y=12,
                w=120,
                h=14,
                font_size_pt=18,
            ),
            build_card_visual("f_opportunity", "Total Closed Won ARR", "Closed won ARR", x=20, y=44, w=120, h=48),
        ],
    )

    result = audit_report(report)

    codes = _codes(result["findings"])
    assert "likely_text_clipping" in codes
    assert "card_too_small" in codes
    assert "unstyled_card" in codes
    assert "weak_section_hierarchy" in codes
    assert result["summary"]["severity_counts"]["high"] >= 1


def test_visual_qa_flags_card_strip_dimension_drift_and_wall_of_cards():
    visuals = [build_textbox_visual("Forecast", x=20, y=12, w=400, h=28, font_size_pt=18)]
    for i in range(9):
        visuals.append(
            build_rag_card_visual(
                "f_opportunity",
                "Total Open Pipeline Value",
                f"KPI {i}",
                x=20 + (i % 5) * 150,
                y=60 + (i // 5) * 72,
                w=120 if i == 3 else 140,
                h=58 if i == 6 else 64,
                tint="#F4F7FB",
                accent="#2B5C8A",
            )
        )
    result = audit_report(_report("Forecast", visuals))

    codes = _codes(result["findings"])
    assert "card_strip_dimension_drift" in codes
    assert "wall_of_cards" in codes


def test_visual_qa_enforces_arr_acv_guardrails():
    renewal_page = _report(
        "Renewals",
        [
            build_textbox_visual("Renewals", x=24, y=12, w=400, h=28, font_size_pt=18),
            build_rag_card_visual(
                "f_opportunity",
                "Total Open Pipeline ARR",
                "Open ARR",
                x=24,
                y=60,
                w=260,
                h=96,
                tint="#F4F7FB",
                accent="#2B5C8A",
            ),
        ],
    )
    growth_page = _report(
        "Growth Mix",
        [
            build_textbox_visual("Growth Mix", x=24, y=12, w=400, h=28, font_size_pt=18),
            build_rag_card_visual(
                "f_opportunity",
                "Total Open Renewal ACV",
                "Renewal ACV",
                x=24,
                y=60,
                w=260,
                h=96,
                tint="#F4F7FB",
                accent="#2B5C8A",
            ),
        ],
    )
    result = audit_report({"sections": renewal_page["sections"] + growth_page["sections"]})

    findings = result["findings"]
    assert sum(1 for f in findings if f["code"] == "arr_acv_guardrail") == 2
    assert all(f["severity"] == "critical" for f in findings if f["code"] == "arr_acv_guardrail")


def test_visual_qa_writes_json_and_markdown(tmp_path: Path):
    report = _report(
        "Forecast",
        [
            build_textbox_visual("Forecast", x=24, y=12, w=400, h=28, font_size_pt=18),
            build_table_visual(
                name="plain_table",
                columns=[{"table": "f_opportunity", "field": "opp_name", "kind": "column", "title": "Opportunity"}],
                x=24,
                y=60,
                w=600,
                h=120,
            ),
        ],
    )
    result = audit_report(report)
    json_path, md_path = write_outputs(result, out_dir=tmp_path, markdown_path=tmp_path / "qa.md")

    assert json.loads(json_path.read_text())["summary"]["total_findings"] >= 1
    markdown = md_path.read_text()
    assert "# RW Dashboard Visual QA" in markdown
    assert "plain_table" in markdown or "unstyled_table" in markdown
    assert render_markdown(result).startswith("# RW Dashboard Visual QA")
