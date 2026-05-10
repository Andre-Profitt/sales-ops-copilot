"""Compose the 'Renewals' tab of rpt_vp_ops_scorecard."""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_clustered_bar_chart_visual,
    build_rag_card_visual,
    build_shape_visual,
    build_table_style_objects,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_add_visual import REPORT_ID, WORKSPACE_ID, _token, get_current_report_json, push_report
from scripts.sales.rw_page_kpi_contract import contract_for
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict

PAGE = "Renewals"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(f"page {PAGE!r} not found")


def _panel(x: float, y: float, w: float, h: float) -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill="#FFFFFF", line="#D8DEE8", z=40, radius=2)


def _compose(section: dict) -> None:
    contract = contract_for(PAGE)
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=420, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual(contract.job, x=24, y=42, w=980, h=22, font_size_pt=9, color="#5C6670", bold=False),
        _panel(24, 84, 1232, 116),
        build_rag_card_visual("f_opportunity", "Renewal Retention Pct (Period)", "Retention", x=40, y=104, w=280, h=76, tint="#EEF9EE", accent="#3B8A3E", value_color="#1F6F3B", display_units=None),
        build_rag_card_visual("f_opportunity", "Total Renewal ACV Won", "Renewal ACV won", x=340, y=104, w=280, h=76, tint="#F4F7FB", accent="#2B5C8A", value_color="#1A1D31", display_units=1000000),
        build_rag_card_visual("f_opportunity", "Total Renewal ACV Lost", "Renewal ACV lost", x=640, y=104, w=280, h=76, tint="#FFEEEE", accent="#C33A32", value_color="#B3261E", display_units=1000000),
        build_rag_card_visual("f_opportunity", "Renewal ACV YTD YoY Pct", "YTD YoY", x=940, y=104, w=280, h=76, tint="#F4F7FB", accent="#2B5C8A", value_color="#1A1D31", display_units=None),
        _panel(24, 224, 588, 456),
        build_textbox_visual("Renewal ACV by Region", x=40, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_clustered_bar_chart_visual(
            category_table="d_region",
            category_column="region",
            category_title="Region",
            measure_table="f_opportunity",
            measure_name="Total Renewal ACV Won",
            measure_title="Renewal ACV won",
            x=40,
            y=270,
            w=540,
            h=380,
            fill="#2B5C8A",
        ),
        _panel(636, 224, 620, 456),
        build_textbox_visual("Renewal Detail", x=652, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="renewal_detail",
            columns=[
                {"table": "f_opportunity", "field": "account_name", "kind": "column", "title": "Account"},
                {"table": "f_opportunity", "field": "region", "kind": "column", "title": "Region"},
                {"table": "f_opportunity", "field": "stage_name", "kind": "column", "title": "Stage"},
                {"table": "f_opportunity", "field": "Total Renewal ACV Won", "kind": "measure", "title": "Won ACV"},
                {"table": "f_opportunity", "field": "Total Renewal ACV Lost", "kind": "measure", "title": "Lost ACV"},
                {"table": "f_opportunity", "field": "Renewal ACV YoY Pct", "kind": "measure", "title": "YoY"},
            ],
            x=652,
            y=270,
            w=580,
            h=328,
            objects=build_table_style_objects(font_size=8),
        ),
        build_textbox_visual(contract.caveat, x=652, y=612, w=560, h=44, font_size_pt=8, color="#5C6670", bold=False),
    ]


def main() -> None:
    token = _token()
    rj = get_current_report_json(token)
    section = _find_page(rj)
    section["visualContainers"] = []
    _compose(section)
    by_table = fetch_measures_by_table()
    errors = [e for vc in section["visualContainers"] for e in validate_visual_dict(vc, by_table)]
    if errors:
        raise SystemExit("\n".join(["pre-flight validation FAILED:"] + errors))
    push_report(token, rj)
    print(f"done. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}")


if __name__ == "__main__":
    main()
