"""Compose the 'Renewals' tab of rpt_vp_ops_scorecard."""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_shape_visual,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_add_visual import REPORT_ID, WORKSPACE_ID, _token, get_current_report_json, push_report
from scripts.sales.rw_page_kpi_contract import contract_for
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict
from scripts.sales.rw_zebra_kg_ibcs_synth import (
    zebra_detail_table_objects,
    zebra_heatmap_matrix_objects,
    zebra_native_card_objects,
)

PAGE = "Renewals"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(f"page {PAGE!r} not found")


def _panel(x: float, y: float, w: float, h: float) -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill="#FFFFFF", line="#D8DEE8", z=40, radius=2)


def _card(
    measure: str,
    title: str,
    *,
    measure_table: str = "f_opportunity",
    x: float,
    accent: str,
    value_color: str = "#1A1D31",
) -> dict:
    return build_card_visual_with_objects(
        measure_table=measure_table,
        measure_name=measure,
        display_title=title,
        x=x,
        y=104,
        w=156,
        h=76,
        objects=zebra_native_card_objects(
            pattern="renewal-acv-kpi-card",
            visual_intent="renewal ACV KPI strip",
            tint="#FFFFFF",
            accent=accent,
            value_color=value_color,
            label_color=accent,
            value_font_size=18,
            label_font_size=9,
        ),
    )


def _compose(section: dict) -> None:
    contract = contract_for(PAGE)
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=420, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual("Renewal ACV pipeline and active-base ARR risk, kept as separate measure families.", x=24, y=42, w=980, h=22, font_size_pt=9, color="#5C6670", bold=False),
        _panel(24, 84, 1232, 116),
        _card("Total Open Renewal ACV", "Open renewal ACV", x=40, accent="#D98A00"),
        _card("Total Renewal ACV Due", "Due renewal ACV", x=214, accent="#D98A00"),
        _card("Renewal Retention Pct (Period)", "Retention % (ACV-wtd)", x=388, accent="#3B8A3E", value_color="#1F6F3B"),
        _card("Total Renewal ACV Won", "Won renewal ACV", x=562, accent="#2B5C8A"),
        _card("Total Renewal ACV Lost", "Lost renewal ACV", x=736, accent="#C33A32", value_color="#8B2C25"),
        _card("Existing ARR Run Rate", "Active-base ARR", measure_table="f_asset_line_item", x=910, accent="#083EA7"),
        _card("Business At Risk ARR", "At-risk base ARR", measure_table="f_asset_line_item", x=1084, accent="#C33A32", value_color="#8B2C25"),
        _panel(24, 224, 588, 456),
        build_textbox_visual("Region x Risk Active-base Heatmap", x=40, y=236, w=420, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="renewal_region_risk_active_base_heatmap",
            columns=[
                {"table": "d_region", "field": "region", "kind": "column", "title": "Region"},
                {
                    "table": "f_asset_line_item",
                    "field": "termination_risk",
                    "kind": "column",
                    "title": "Risk",
                },
                {
                    "table": "f_asset_line_item",
                    "field": "Existing ARR Run Rate",
                    "kind": "measure",
                    "title": "Active-base ARR",
                },
                {
                    "table": "f_asset_line_item",
                    "field": "Business At Risk ARR",
                    "kind": "measure",
                    "title": "At-risk active-base ARR",
                },
                {
                    "table": "f_asset_line_item",
                    "field": "Business At Risk Pct",
                    "kind": "measure",
                    "title": "Risk % of active base",
                },
                {
                    "table": "f_asset_line_item",
                    "field": "Existing ARR Expiring In Period",
                    "kind": "measure",
                    "title": "Expiring active-base ARR",
                },
            ],
            x=40,
            y=270,
            w=540,
            h=380,
            objects=zebra_heatmap_matrix_objects(
                pattern="renewal-region-risk-heatmap",
                visual_intent="renewal active-base risk heatmap",
                databar_specs=(
                    (
                        "f_asset_line_item.Existing ARR Run Rate",
                        "f_asset_line_item.Existing ARR Run Rate",
                        "#083EA7",
                    ),
                    (
                        "f_asset_line_item.Business At Risk ARR",
                        "f_asset_line_item.Business At Risk ARR",
                        "#C33A32",
                    ),
                    (
                        "f_asset_line_item.Business At Risk Pct",
                        "f_asset_line_item.Business At Risk Pct",
                        "#D98A00",
                    ),
                    (
                        "f_asset_line_item.Existing ARR Expiring In Period",
                        "f_asset_line_item.Existing ARR Expiring In Period",
                        "#2B5C8A",
                    ),
                ),
                background_specs=(
                    (
                        "f_asset_line_item.Existing ARR Run Rate",
                        "f_asset_line_item.Existing ARR Run Rate Heat Color",
                    ),
                    (
                        "f_asset_line_item.Business At Risk ARR",
                        "f_asset_line_item.Business At Risk ARR Heat Color",
                    ),
                    (
                        "f_asset_line_item.Business At Risk Pct",
                        "f_asset_line_item.Business At Risk Pct Heat Color",
                    ),
                    (
                        "f_asset_line_item.Existing ARR Expiring In Period",
                        "f_asset_line_item.Existing ARR Expiring In Period Heat Color",
                    ),
                ),
            ),
        ),
        _panel(636, 224, 620, 456),
        build_textbox_visual("Active-base ARR Risk Detail", x=652, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="asset_risk_detail",
            columns=[
                {"table": "f_asset_line_item", "field": "account_name", "kind": "column", "title": "Account"},
                {"table": "f_asset_line_item", "field": "region", "kind": "column", "title": "Region"},
                {"table": "f_asset_line_item", "field": "termination_risk", "kind": "column", "title": "Risk"},
                {"table": "f_asset_line_item", "field": "asset_end_date", "kind": "column", "title": "End date"},
                {"table": "f_asset_line_item", "field": "product_family", "kind": "column", "title": "Product family"},
                {"table": "f_asset_line_item", "field": "Existing ARR Expiring In Period", "kind": "measure", "title": "Active-base ARR"},
                {"table": "f_asset_line_item", "field": "Business At Risk ARR", "kind": "measure", "title": "At-risk base ARR"},
                {"table": "f_asset_line_item", "field": "Business At Risk Pct", "kind": "measure", "title": "Risk % of base"},
            ],
            x=652,
            y=270,
            w=580,
            h=328,
            objects=zebra_detail_table_objects(),
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
