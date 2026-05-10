"""Compose every RW KPI-targeted report page.

This is the production page-contract entry point: all six core tabs are rebuilt
from code against the deployed RW KPI semantic model.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

from scripts.sales.rw_page_kpi_contract import validate_contract_pages


COMPOSER_MODULES: dict[str, str] = {
    "What Changed": "scripts.sales.rw_compose_what_changed",
    "Forecast": "scripts.sales.rw_compose_forecast",
    "Stage Hygiene": "scripts.sales.rw_compose_stage_hygiene",
    "Renewals": "scripts.sales.rw_compose_renewals",
    "Growth Mix": "scripts.sales.rw_compose_growth_mix",
    "VP Ops Scorecard": "scripts.sales.rw_compose_scorecard_home",
}


def _load_composer(module_name: str) -> Callable[[dict], None]:
    return import_module(module_name)._compose


def _find_or_create_page(rj: dict, display_name: str) -> dict:
    for section in rj.get("sections", []):
        if section.get("displayName") == display_name:
            return section
    section = {
        "name": display_name.replace(" ", ""),
        "displayName": display_name,
        "filters": "[]",
        "ordinal": len(rj.get("sections", [])),
        "visualContainers": [],
        "displayOption": 1,
        "height": 720.0,
        "width": 1280.0,
    }
    rj.setdefault("sections", []).append(section)
    return section


def compose_report(rj: dict) -> dict:
    """Mutate and return report.json with every target page rebuilt."""
    for page, module_name in COMPOSER_MODULES.items():
        section = _find_or_create_page(rj, page)
        section["visualContainers"] = []
        section["filters"] = "[]"
        section["height"] = 720.0
        section["width"] = 1280.0
        _load_composer(module_name)(section)
    for ordinal, section in enumerate(rj.get("sections", [])):
        section["ordinal"] = ordinal
    return rj


def main() -> None:
    from scripts.sales.rw_add_visual import REPORT_ID, WORKSPACE_ID, _token, get_current_report_json, push_report
    from scripts.sales.rw_validate import fetch_measures_by_table, validate_report

    print("composing all RW KPI-targeted pages")
    token = _token()
    rj = compose_report(get_current_report_json(token))
    contract_errors = validate_contract_pages(rj)
    if contract_errors:
        raise SystemExit("\n".join(["contract validation FAILED:"] + contract_errors))
    by_table = fetch_measures_by_table()
    ref_errors = validate_report(rj, by_table)
    if ref_errors:
        raise SystemExit("\n".join(["pre-flight validation FAILED:"] + ref_errors))
    push_report(token, rj)
    print(f"done. open: https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{REPORT_ID}")


if __name__ == "__main__":
    main()
