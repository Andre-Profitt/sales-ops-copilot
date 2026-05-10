"""Compose the 'Stage Hygiene' tab of rpt_vp_ops_scorecard."""

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
    zebra_native_card_objects,
    zebra_stage_hygiene_table_objects,
)

PAGE = "Stage Hygiene"


def _find_page(rj: dict) -> dict:
    for s in rj["sections"]:
        if s.get("displayName") == PAGE:
            return s
    raise SystemExit(f"page {PAGE!r} not found")


def _panel(x: float, y: float, w: float, h: float) -> dict:
    return build_shape_visual(x=x, y=y, w=w, h=h, fill="#FFFFFF", line="#D8DEE8", z=40, radius=2)


def _stage_card(
    measure_table: str,
    measure_name: str,
    display_title: str,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    tint: str,
    accent: str,
    value_color: str = "#1A1D31",
    value_font_size: int = 24,
) -> dict:
    return build_card_visual_with_objects(
        measure_table,
        measure_name,
        display_title,
        x=x,
        y=y,
        w=w,
        h=h,
        objects=zebra_native_card_objects(
            pattern="stage-hygiene-process-kpi-card",
            visual_intent="Stage Hygiene hero/process KPI",
            tint=tint,
            accent=accent,
            value_color=value_color,
            display_units=None,
            value_font_size=value_font_size,
            label_font_size=8,
        ),
    )


def _compose(section: dict) -> None:
    contract = contract_for(PAGE)
    section["filters"] = "[]"
    section["visualContainers"] = [
        build_textbox_visual(PAGE, x=24, y=12, w=420, h=28, font_size_pt=18, color="#1A1D31"),
        build_textbox_visual("Conversion, backward movement, and time-in-stage bottlenecks.", x=24, y=42, w=980, h=22, font_size_pt=9, color="#5C6670", bold=False),
        _panel(24, 84, 1232, 116),
        _stage_card("f_stage_transition", "Stage Forward Pct (LE)", "Forward rate", x=40, y=104, w=216, h=76, tint="#EEF9EE", accent="#3B8A3E"),
        _stage_card("f_stage_transition", "Stage Backward Pct (LE)", "Backward rate", x=280, y=104, w=216, h=76, tint="#FFEEEE", accent="#C33A32"),
        _stage_card("f_stage_transition", "Avg Days In Prior Stage (LE)", "Stage aging", x=520, y=104, w=216, h=76, tint="#F4F7FB", accent="#2B5C8A"),
        _stage_card("f_opportunity", "Land Avg Sales Cycle Days", "Land cycle", x=760, y=104, w=216, h=76, tint="#F4F7FB", accent="#2B5C8A"),
        _stage_card("f_opportunity", "Avg Sales Cycle Days", "L+E cycle", x=1000, y=104, w=216, h=76, tint="#F4F7FB", accent="#2B5C8A"),
        _panel(24, 224, 760, 456),
        build_textbox_visual("Stage Conversion Matrix", x=40, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="stage_hygiene_conversion_matrix",
            columns=[
                {"table": "f_stage_transition", "field": "from_stage_name", "kind": "column", "title": "Stage"},
                {"table": "f_stage_transition", "field": "Stage Forward Pct (LE)", "kind": "measure", "title": "Forward %"},
                {"table": "f_stage_transition", "field": "Stage Backward Pct (LE)", "kind": "measure", "title": "Backward %"},
                {"table": "f_stage_transition", "field": "Avg Days In Prior Stage (LE)", "kind": "measure", "title": "Avg days"},
                {"table": "f_stage_transition", "field": "Total Stage Transitions", "kind": "measure", "title": "Moves"},
                {"table": "f_stage_transition", "field": "Stage Moves ARR 7d", "kind": "measure", "title": "7d ARR moved"},
            ],
            x=40,
            y=268,
            w=728,
            h=392,
            objects=zebra_stage_hygiene_table_objects(
                max_field="f_stage_transition.Stage Moves ARR 7d",
                databar_column="Stage Moves ARR 7d",
            ),
        ),
        _panel(804, 224, 452, 214),
        build_textbox_visual("Stage 3 Gate Pressure", x=820, y=236, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        _stage_card("f_opportunity", "Commercial Approval Compliance Pct", "Approval compliance", x=820, y=274, w=200, h=72, tint="#EEF9EE", accent="#3B8A3E"),
        _stage_card("f_opportunity", "Commercial Approval To Close Days", "Approval-to-close", x=1036, y=274, w=200, h=72, tint="#F4F7FB", accent="#2B5C8A"),
        build_textbox_visual(contract.caveat, x=820, y=362, w=410, h=46, font_size_pt=8, color="#5C6670", bold=False),
        _panel(804, 466, 452, 214),
        build_textbox_visual("Stage 4 Bottleneck Detail", x=820, y=478, w=360, h=24, font_size_pt=11, color="#1A1D31"),
        build_table_visual(
            name="stage_hygiene_detail",
            columns=[
                {"table": "f_stage_transition", "field": "from_stage_name", "kind": "column", "title": "Stage"},
                {"table": "f_stage_transition", "field": "Stage 4 Forward Pct", "kind": "measure", "title": "S4 Forward"},
                {"table": "f_stage_transition", "field": "Avg Days In Stage 4", "kind": "measure", "title": "S4 Avg Days"},
                {"table": "f_stage_transition", "field": "Stage Moves ARR 7d", "kind": "measure", "title": "7d ARR moved"},
            ],
            x=820,
            y=510,
            w=420,
            h=150,
            objects=zebra_detail_table_objects(),
        ),
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
