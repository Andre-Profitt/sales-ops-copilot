"""Compose the 'Growth Mix' tab of rpt_vp_ops_scorecard."""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_clustered_bar_chart_visual,
    build_shape_visual,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_add_visual import REPORT_ID, WORKSPACE_ID, _token, get_current_report_json, push_report
from scripts.sales.rw_page_kpi_contract import contract_for
from scripts.sales.rw_validate import fetch_measures_by_table, validate_visual_dict
from scripts.sales.rw_zebra_kg_ibcs_synth import (
    tag_visual_with_zebra_transfer_metadata,
    zebra_detail_table_objects,
    zebra_native_card_objects,
)

PAGE = "Growth Mix"


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
    x: float,
    tint: str,
    accent: str,
    value_color: str = "#1A1D31",
) -> dict:
    return build_card_visual_with_objects(
        measure_table="f_opportunity",
        measure_name=measure,
        display_title=title,
        x=x,
        y=104,
        w=216,
        h=76,
        objects=zebra_native_card_objects(
            pattern="growth-mix-kpi-card",
            visual_intent="growth mix KPI strip",
            tint=tint,
            accent=accent,
            value_color=value_color,
            label_color=accent,
            value_font_size=22,
            label_font_size=9,
        ),
    )


def _zebra_chart(visual: dict) -> dict:
    return tag_visual_with_zebra_transfer_metadata(
        visual,
        pattern="growth-mix-region-chart",
        visual_intent="Land and Expand ARR by region",
    )


def _compose(section: dict) -> None:
    contract = contract_for(PAGE)
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=420, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual("Land/Expand ARR basis, ARR share percentages, and count-based new-customer signals.", x=24, y=42, w=980, h=22, font_size_pt=9, color="#5C6670", bold=False),
        _panel(24, 84, 1232, 116),
        _card("Open Land ARR", "Open Land ARR", x=40, tint="#F4F7FB", accent="#2B5C8A"),
        _card("Open Expand ARR", "Open Expand ARR", x=280, tint="#F4F7FB", accent="#2B5C8A"),
        _card("Avg Deal Size Won", "Avg won ARR (L+E)", x=520, tint="#EEF9EE", accent="#3B8A3E", value_color="#1F6F3B"),
        _card("Partner ARR", "Partner ARR (L+E)", x=760, tint="#FFF8E6", accent="#D98A00"),
        _card("Partner Pct", "Partner % ARR share", x=1000, tint="#FFF8E6", accent="#D98A00"),
        _panel(24, 224, 588, 456),
        build_textbox_visual("Open Land + Expand ARR by Region", x=40, y=236, w=420, h=24, font_size_pt=11, color="#1A1D31"),
        _zebra_chart(build_clustered_bar_chart_visual(
            category_table="d_region",
            category_column="region",
            category_title="Region",
            measure_table="f_opportunity",
            measure_name="Total Open Pipeline ARR",
            measure_title="Open ARR (L+E)",
            x=40,
            y=270,
            w=540,
            h=380,
            fill="#2B5C8A",
        )),
        _panel(636, 224, 620, 456),
        build_textbox_visual("Strategic Mix Detail", x=652, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="growth_mix_detail",
            columns=[
                {"table": "d_region", "field": "region", "kind": "column", "title": "Region"},
                {"table": "f_opportunity", "field": "Open Land ARR", "kind": "measure", "title": "Open Land ARR"},
                {"table": "f_opportunity", "field": "Open Expand ARR", "kind": "measure", "title": "Open Expand ARR"},
                {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "kind": "measure", "title": "Open ARR (L+E)"},
                {"table": "f_opportunity", "field": "Avg Deal Size Won", "kind": "measure", "title": "Avg won ARR (L+E)"},
                {"table": "f_opportunity", "field": "Partner ARR", "kind": "measure", "title": "Partner ARR (L+E)"},
                {"table": "f_opportunity", "field": "Partner Pct", "kind": "measure", "title": "Partner % ARR"},
                {"table": "f_opportunity", "field": "Total Land Won Count", "kind": "measure", "title": "Land won count"},
            ],
            x=652,
            y=270,
            w=580,
            h=182,
            objects=zebra_detail_table_objects(),
        ),
        build_textbox_visual("Product / Acquired Mix", x=652, y=470, w=360, h=22, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="growth_mix_product_acquired_detail",
            columns=[
                {"table": "f_opportunity", "field": "won_value_tier", "kind": "column", "title": "Won tier"},
                {"table": "f_opportunity", "field": "Closed Won Deals Count", "kind": "measure", "title": "Won deal count"},
                {"table": "f_opportunity", "field": "Cross Sell To Acquired ARR", "kind": "measure", "title": "Axioma ARR (L+E)"},
                {"table": "f_opportunity", "field": "SaaS YoY Growth Pct", "kind": "measure", "title": "SaaS ARR YoY %"},
                {"table": "f_opportunity", "field": "PS ARR Attach Pct", "kind": "measure", "title": "PS attach % (ACV/ARR)"},
            ],
            x=652,
            y=500,
            w=580,
            h=98,
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
