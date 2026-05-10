"""Compose the Product Retention tab of rpt_vp_ops_scorecard."""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_matrix_visual,
    build_shape_visual,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_page_kpi_contract import contract_for
from scripts.sales.rw_zebra_kg_ibcs_synth import (
    zebra_detail_table_objects,
    zebra_heatmap_matrix_objects,
    zebra_native_card_objects,
)

PAGE = "Product Retention"
ASSET = "f_asset_line_item"


def _panel(x: float, y: float, w: float, h: float) -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill="#FFFFFF", line="#D8DEE8", z=40, radius=2)


def _card(measure: str, title: str, *, x: float, accent: str, value_color: str = "#1A1D31") -> dict:
    return build_card_visual_with_objects(
        measure_table=ASSET,
        measure_name=measure,
        display_title=title,
        x=x,
        y=104,
        w=216,
        h=76,
        objects=zebra_native_card_objects(
            pattern="product-retention-kpi-card",
            visual_intent="active-base product retention KPI",
            tint="#FFFFFF",
            accent=accent,
            value_color=value_color,
            label_color=accent,
            value_font_size=20,
            label_font_size=9,
        ),
    )


def _compose(section: dict) -> None:
    contract = contract_for(PAGE)
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=420, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual(
            "Active-base ARR by product, region, and segment. Churn mechanics require prior/current asset snapshots.",
            x=24,
            y=42,
            w=760,
            h=22,
            font_size_pt=9,
            color="#5C6670",
            bold=False,
        ),
        _panel(24, 84, 1232, 116),
        _card("Existing ARR Run Rate", "Active-base ARR", x=40, accent="#083EA7"),
        _card("Existing ARR Expiring In Period", "Expiring active-base ARR", x=280, accent="#2B5C8A"),
        _card("Business At Risk ARR", "At-risk active-base ARR", x=520, accent="#C33A32", value_color="#8B2C25"),
        _card("Business At Risk Pct", "Risk % of active base", x=760, accent="#D98A00"),
        _card("Active Asset Line Count", "Active asset line count", x=1000, accent="#2B5C8A"),
        _panel(24, 224, 596, 210),
        build_textbox_visual(
            "Product Family x Region Heatmap",
            x=40,
            y=236,
            w=360,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_matrix_visual(
            rows=[{"table": ASSET, "field": "product_family", "title": "Product family"}],
            columns=[{"table": "d_region", "field": "region", "title": "Region"}],
            values=[
                {"table": ASSET, "field": "Existing ARR Run Rate", "title": "Active-base ARR"},
                {"table": ASSET, "field": "Business At Risk ARR", "title": "At-risk active-base ARR"},
            ],
            x=40,
            y=268,
            w=560,
            h=142,
            objects=zebra_heatmap_matrix_objects(
                pattern="product-family-region-heatmap",
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
                ),
            ),
        ),
        _panel(660, 224, 596, 210),
        build_textbox_visual(
            "Product Family x Segment Risk",
            x=676,
            y=236,
            w=360,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_matrix_visual(
            rows=[{"table": ASSET, "field": "product_family", "title": "Product family"}],
            columns=[{"table": ASSET, "field": "industry", "title": "Segment"}],
            values=[
                {"table": ASSET, "field": "Business At Risk Pct", "title": "Risk % of base"},
                {"table": ASSET, "field": "Existing ARR Expiring In Period", "title": "Expiring active-base ARR"},
            ],
            x=676,
            y=268,
            w=560,
            h=142,
            objects=zebra_heatmap_matrix_objects(
                pattern="product-family-segment-risk-heatmap",
                databar_specs=(
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
            ),
        ),
        _panel(24, 458, 1232, 222),
        build_textbox_visual(
            "Account-product Retention Ledger",
            x=40,
            y=470,
            w=420,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_table_visual(
            name="product_retention_account_product_ledger",
            columns=[
                {"table": ASSET, "field": "account_name", "kind": "column", "title": "Account"},
                {"table": ASSET, "field": "region", "kind": "column", "title": "Region"},
                {"table": ASSET, "field": "industry", "kind": "column", "title": "Segment"},
                {"table": ASSET, "field": "product_family", "kind": "column", "title": "Product family"},
                {"table": ASSET, "field": "product_area", "kind": "column", "title": "Product area"},
                {"table": ASSET, "field": "asset_start_date", "kind": "column", "title": "Start date"},
                {"table": ASSET, "field": "asset_end_date", "kind": "column", "title": "End date"},
                {"table": ASSET, "field": "Existing ARR Expiring In Period", "kind": "measure", "title": "Active-base ARR"},
                {"table": ASSET, "field": "Business At Risk ARR", "kind": "measure", "title": "At-risk active-base ARR"},
                {"table": ASSET, "field": "Business At Risk Pct", "kind": "measure", "title": "Risk % of base"},
            ],
            x=40,
            y=502,
            w=1190,
            h=116,
            objects=zebra_detail_table_objects(),
        ),
        build_textbox_visual(contract.caveat, x=40, y=628, w=1160, h=34, font_size_pt=8, color="#5C6670", bold=False),
    ]


if __name__ == "__main__":
    raise SystemExit(
        "Use `python3 -m scripts.sales.rw_compose_all_pages` or `rw_apply_zebra_lab_proof`."
    )
