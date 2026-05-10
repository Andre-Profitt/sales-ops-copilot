"""Regenerate the local native RW Power BI inspection PBIP.

This modifies only the local Desktop lab copy under Downloads. It does not push
to Fabric. Older runs added Zebra custom visual proof pages; this command now
removes those lab-only artifacts so the inspection PBIP is native-only.

Usage:
    python3 -m scripts.sales.rw_apply_zebra_lab_proof
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

DEFAULT_LAB_ROOT = (
    Path.home() / "Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip"
)
DEFAULT_SOURCE_PBIX = (
    Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/pbix-test/"
    "sales-funnel-power-bi-template__sales-pipeline-crm-template__"
    "Zebra BI - CRM Sales pipeline demo v2.pbix"
)
CUSTOM_VISUALS = (
    "ZebraBITables98F88148E5424E949E69864664EE1860",
    "zebraBiCards8085D508EB994C8081CA47C85ABD7C26",
    "waterfall0221D8FBE40445C1A4E598AA8EF8B506",
)
CUSTOM_VISUALS_LOWER = tuple(visual.lower() for visual in CUSTOM_VISUALS)
LAB_PAGE_NAMES = {"PageZebraExceptions"}
LAB_PAGE_DISPLAY_NAMES = {"Zebra Exceptions"}


def report_dir(lab_root: Path) -> Path:
    matches = sorted(lab_root.glob("*.Report"))
    if not matches:
        raise FileNotFoundError(f"No .Report directory found under {lab_root}")
    return matches[0]


def apply_spine_rebuild_to_main_page(report: dict) -> None:
    """Apply all KPI-targeted native pages to the lab PBIP."""
    from scripts.sales.rw_compose_all_pages import compose_report

    compose_report(report)


def _is_custom_zebra_visual(visual: dict) -> bool:
    config = json.loads(visual.get("config") or "{}")
    visual_type = str(config.get("singleVisual", {}).get("visualType") or "").lower()
    return any(visual_type.startswith(custom) for custom in CUSTOM_VISUALS_LOWER)


def remove_zebra_lab_artifacts(report: dict, target_report_dir: Path | None = None) -> None:
    """Remove old custom Zebra proof pages, visual containers, and resources."""
    report["sections"] = [
        section
        for section in report.get("sections", [])
        if section.get("name") not in LAB_PAGE_NAMES
        and section.get("displayName") not in LAB_PAGE_DISPLAY_NAMES
    ]
    for section in report.get("sections", []):
        section["visualContainers"] = [
            visual
            for visual in section.get("visualContainers", [])
            if not _is_custom_zebra_visual(visual)
        ]

    report["resourcePackages"] = [
        package
        for package in report.get("resourcePackages", [])
        if str(package.get("resourcePackage", {}).get("name") or "") not in CUSTOM_VISUALS
    ]

    if target_report_dir is not None:
        custom_visuals_dir = target_report_dir / "CustomVisuals"
        for visual in CUSTOM_VISUALS:
            shutil.rmtree(custom_visuals_dir / visual, ignore_errors=True)
        if custom_visuals_dir.exists() and not any(custom_visuals_dir.iterdir()):
            custom_visuals_dir.rmdir()

    for ordinal, section in enumerate(report.get("sections", [])):
        section["ordinal"] = ordinal


def apply_lab_proof(lab_root: Path, source_pbix: Path) -> Path:
    target_report_dir = report_dir(lab_root)
    report_json = target_report_dir / "report.json"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target_report_dir / f"report.pre_zebra_lab_proof_{timestamp}.json"
    shutil.copy2(report_json, backup)

    report = json.loads(report_json.read_text(encoding="utf-8"))
    remove_zebra_lab_artifacts(report, target_report_dir)
    apply_spine_rebuild_to_main_page(report)
    remove_zebra_lab_artifacts(report, target_report_dir)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--source-pbix", type=Path, default=DEFAULT_SOURCE_PBIX)
    args = parser.parse_args()
    backup = apply_lab_proof(args.lab_root.expanduser(), args.source_pbix.expanduser())
    print("regenerated native RW Power BI lab")
    print(f"backup: {backup}")
    print(f"lab: {args.lab_root.expanduser()}")


if __name__ == "__main__":
    main()
