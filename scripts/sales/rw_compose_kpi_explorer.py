"""Compose the RW KPI Explorer slice-and-dice tab."""

from __future__ import annotations

from scripts.sales._pbir_helpers import (
    build_matrix_visual,
    build_shape_visual,
    build_table_visual,
    build_textbox_visual,
)
from scripts.sales.rw_zebra_kg_ibcs_synth import zebra_detail_table_objects

PAGE = "RW KPI Explorer"


def _panel(x: float, y: float, w: float, h: float) -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill="#FFFFFF", line="#D8DEE8", z=40, radius=2)


def _compose(section: dict) -> None:
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=360, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual(
            "Slice RW KPIs by region, fiscal quarter, motion, and stage with ARR/ACV/rate bases visible.",
            x=24,
            y=42,
            w=610,
            h=22,
            font_size_pt=9,
            color="#5C6670",
            bold=False,
        ),
        _panel(24, 86, 596, 276),
        build_textbox_visual(
            "Land + Expand ARR Mix",
            x=40,
            y=98,
            w=360,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_matrix_visual(
            rows=[{"table": "d_region", "field": "region", "title": "Region"}],
            columns=[{"table": "f_opportunity", "field": "motion_type", "title": "Motion"}],
            values=[
                {"table": "f_opportunity", "field": "Total Open Pipeline ARR", "title": "Open ARR (Land + Expand)"},
                {"table": "f_opportunity", "field": "Total Closed Won ARR", "title": "Won ARR (Land + Expand)"},
                {"table": "f_opportunity", "field": "Win Rate ARR", "title": "Win rate (ARR-wtd)"},
            ],
            x=40,
            y=130,
            w=560,
            h=212,
            objects=zebra_detail_table_objects(),
        ),
        _panel(660, 86, 596, 276),
        build_textbox_visual(
            "Renewal ACV Exposure",
            x=676,
            y=98,
            w=360,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_table_visual(
            name="kpi_explorer_renewal_acv_by_region",
            columns=[
                {"table": "d_region", "field": "region", "kind": "column", "title": "Region"},
                {
                    "table": "f_opportunity",
                    "field": "Total Open Renewal ACV",
                    "kind": "measure",
                    "title": "Open renewal ACV",
                },
                {
                    "table": "f_opportunity",
                    "field": "Renewal Retention Pct (Period)",
                    "kind": "measure",
                    "title": "Retention % (ACV-wtd)",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Renewal ACV Won",
                    "kind": "measure",
                    "title": "Won renewal ACV",
                },
                {
                    "table": "f_opportunity",
                    "field": "Total Renewal ACV Lost",
                    "kind": "measure",
                    "title": "Lost renewal ACV",
                },
            ],
            x=676,
            y=130,
            w=560,
            h=212,
            objects=zebra_detail_table_objects(),
        ),
        _panel(24, 390, 596, 292),
        build_textbox_visual(
            "Stage Conversion Diagnostics",
            x=40,
            y=402,
            w=360,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_table_visual(
            name="kpi_explorer_stage_diagnostics",
            columns=[
                {
                    "table": "f_stage_transition",
                    "field": "from_stage_name",
                    "kind": "column",
                    "title": "Stage",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Forward Pct (LE)",
                    "kind": "measure",
                    "title": "Forward % (count, Land + Expand)",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Backward Pct (LE)",
                    "kind": "measure",
                    "title": "Backward % (count, Land + Expand)",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Avg Days In Prior Stage (LE)",
                    "kind": "measure",
                    "title": "Avg days",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Moves ARR 7d",
                    "kind": "measure",
                    "title": "7d ARR moved (Land + Expand)",
                },
            ],
            x=40,
            y=434,
            w=560,
            h=226,
            objects=zebra_detail_table_objects(),
        ),
        _panel(660, 390, 596, 292),
        build_textbox_visual(
            "Growth Mix and New Customer Signal",
            x=676,
            y=402,
            w=420,
            h=24,
            font_size_pt=11,
            color="#1A1D31",
        ),
        build_table_visual(
            name="kpi_explorer_growth_mix_by_region",
            columns=[
                {"table": "d_region", "field": "region", "kind": "column", "title": "Region"},
                {"table": "f_opportunity", "field": "Open Land ARR", "kind": "measure", "title": "Open Land ARR"},
                {
                    "table": "f_opportunity",
                    "field": "Open Expand ARR",
                    "kind": "measure",
                    "title": "Open Expand ARR",
                },
                {
                    "table": "f_opportunity",
                    "field": "Avg Deal Size Won",
                    "kind": "measure",
                    "title": "Avg won ARR (Land + Expand)",
                },
                {"table": "f_opportunity", "field": "Partner ARR", "kind": "measure", "title": "Partner ARR (Land + Expand)"},
                {"table": "f_opportunity", "field": "Partner Pct", "kind": "measure", "title": "Partner % ARR"},
                {
                    "table": "f_opportunity",
                    "field": "Total Land Won Count",
                    "kind": "measure",
                    "title": "Land won count",
                },
            ],
            x=676,
            y=434,
            w=560,
            h=226,
            objects=zebra_detail_table_objects(),
        ),
    ]


if __name__ == "__main__":
    raise SystemExit(
        "Use `python3 -m scripts.sales.rw_compose_all_pages` or `rw_apply_zebra_lab_proof`."
    )
