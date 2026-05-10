"""Compose every RW KPI-targeted report page.

This is the production page-contract entry point: all six core tabs are rebuilt
from code against the deployed RW KPI semantic model.
"""

from __future__ import annotations

from collections.abc import Callable

from scripts.sales.rw_add_visual import REPORT_ID, WORKSPACE_ID, _token, get_current_report_json, push_report
from scripts.sales.rw_compose_forecast import _compose as compose_forecast
from scripts.sales.rw_compose_growth_mix import _compose as compose_growth_mix
from scripts.sales.rw_compose_renewals import _compose as compose_renewals
from scripts.sales.rw_compose_scorecard_home import _compose as compose_scorecard
from scripts.sales.rw_compose_stage_hygiene import _compose as compose_stage_hygiene
from scripts.sales.rw_compose_what_changed import _compose as compose_what_changed
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS
from scripts.sales.rw_validate import fetch_measures_by_table, validate_report


COMPOSERS: dict[str, Callable[[dict], None]] = {
    "What Changed": compose_what_changed,
    "Forecast": compose_forecast,
    "Stage Hygiene": compose_stage_hygiene,
    "Renewals": compose_renewals,
    "Growth Mix": compose_growth_mix,
    "VP Ops Scorecard": compose_scorecard,
}


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
    for page, composer in COMPOSERS.items():
        section = _find_or_create_page(rj, page)
        section["visualContainers"] = []
        section["filters"] = "[]"
        section["height"] = 720.0
        section["width"] = 1280.0
        composer(section)
    for ordinal, section in enumerate(rj.get("sections", [])):
        section["ordinal"] = ordinal
    return rj


def validate_contract_pages(rj: dict) -> list[str]:
    errors: list[str] = []
    pages = {s.get("displayName"): s for s in rj.get("sections", [])}
    for page, contract in PAGE_KPI_CONTRACTS.items():
        section = pages.get(page)
        if section is None:
            errors.append(f"missing target page {page!r}")
            continue
        if not section.get("visualContainers"):
            errors.append(f"target page {page!r} has no visuals")
        encoded = "\n".join(v.get("config", "") for v in section.get("visualContainers", []))
        for measure in contract.measures:
            if measure not in encoded:
                errors.append(f"{page}: contract measure {measure!r} not present in page JSON")
    return errors


def main() -> None:
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
