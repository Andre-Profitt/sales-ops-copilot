"""Apply the first Zebra BI proof page to the local RW Power BI lab PBIP.

This modifies only the local Desktop lab copy under Downloads. It does not push
to Fabric and does not embed a Zebra license key.

Usage:
    python3 -m scripts.sales.rw_apply_zebra_lab_proof
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.sales._pbir_helpers import (
    ZEBRA_BI_TABLES_VISUAL_TYPE,
    build_textbox_visual,
    build_zebra_bi_table_visual,
)

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


def report_dir(lab_root: Path) -> Path:
    matches = sorted(lab_root.glob("*.Report"))
    if not matches:
        raise FileNotFoundError(f"No .Report directory found under {lab_root}")
    return matches[0]


def copy_custom_visuals(source_pbix: Path, target_report_dir: Path) -> None:
    """Copy Zebra custom visual packages from a downloaded template PBIX."""
    with zipfile.ZipFile(source_pbix) as pbix:
        for visual in CUSTOM_VISUALS:
            target_dir = target_report_dir / "CustomVisuals" / visual
            (target_dir / "resources").mkdir(parents=True, exist_ok=True)
            for member in (
                f"Report/CustomVisuals/{visual}/package.json",
                f"Report/CustomVisuals/{visual}/resources/{visual}.pbiviz.json",
            ):
                destination = target_dir / Path(member).relative_to(
                    f"Report/CustomVisuals/{visual}"
                )
                if not destination.exists():
                    destination.write_bytes(pbix.read(member))


def ensure_resource_packages(report: dict) -> None:
    packages = report.setdefault("resourcePackages", [])
    names = {package.get("resourcePackage", {}).get("name") for package in packages}
    for visual in CUSTOM_VISUALS:
        if visual in names:
            continue
        packages.append(
            {
                "resourcePackage": {
                    "name": visual,
                    "type": 0,
                    "items": [
                        {
                            "name": f"{visual}.pbiviz.json",
                            "path": f"{visual}.pbiviz.json",
                            "type": 5,
                        }
                    ],
                    "disabled": False,
                }
            }
        )


def stage_hygiene_page(report: dict) -> dict:
    for section in report.get("sections", []):
        if section.get("name") == "PageStageHygiene" or section.get("displayName") == (
            "Stage Hygiene"
        ):
            section["name"] = "PageStageHygiene"
            section["displayName"] = "Stage Hygiene"
            section["width"] = 1280.0
            section["height"] = 720.0
            return section
    section = {
        "name": "PageStageHygiene",
        "displayName": "Stage Hygiene",
        "filters": "[]",
        "ordinal": len(report.get("sections", [])),
        "visualContainers": [],
        "displayOption": 1,
        "height": 720.0,
        "width": 1280.0,
    }
    report.setdefault("sections", []).append(section)
    return section


def zebra_exceptions_page(report: dict) -> dict:
    for section in report.get("sections", []):
        if section.get("name") == "PageZebraExceptions" or section.get("displayName") == (
            "Zebra Exceptions"
        ):
            section["name"] = "PageZebraExceptions"
            section["displayName"] = "Zebra Exceptions"
            section["width"] = 1280.0
            section["height"] = 720.0
            return section
    section = {
        "name": "PageZebraExceptions",
        "displayName": "Zebra Exceptions",
        "filters": "[]",
        "ordinal": len(report.get("sections", [])),
        "visualContainers": [],
        "displayOption": 1,
        "height": 720.0,
        "width": 1280.0,
    }
    report.setdefault("sections", []).append(section)
    return section


def apply_stage_hygiene_proof(report: dict) -> None:
    section = stage_hygiene_page(report)
    section["visualContainers"] = [
        build_textbox_visual(
            "Stage Hygiene - Zebra BI Tables proof",
            x=36,
            y=24,
            w=900,
            h=34,
            font_size_pt=18,
            color="#1F2937",
        ),
        build_textbox_visual(
            (
                "Desktop lab only. Uses Zebra BI Tables against RW stage-transition "
                "measures; ARR and Renewal ACV remain separate."
            ),
            x=36,
            y=58,
            w=1120,
            h=28,
            font_size_pt=10,
            color="#4B5563",
            bold=False,
        ),
        build_zebra_bi_table_visual(
            visual_type=ZEBRA_BI_TABLES_VISUAL_TYPE,
            categories=[
                {
                    "table": "f_stage_transition",
                    "field": "from_stage_name",
                    "title": "Stage",
                }
            ],
            values=[
                {
                    "table": "f_stage_transition",
                    "field": "Stage Forward Pct (LE)",
                    "title": "Forward %",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Backward Pct (LE)",
                    "title": "Backward %",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Avg Days In Prior Stage (LE)",
                    "title": "Avg days",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Total Stage Transitions",
                    "title": "Moves",
                },
                {
                    "table": "f_stage_transition",
                    "field": "Stage Moves ARR 7d",
                    "title": "7d ARR moved",
                },
            ],
            x=36,
            y=104,
            w=1208,
            h=560,
        ),
    ]


def apply_spine_rebuild_to_main_page(report: dict) -> None:
    """Apply all KPI-targeted native pages to the lab PBIP."""
    from scripts.sales.rw_compose_all_pages import compose_report

    compose_report(report)


def apply_zebra_exceptions_proof(report: dict) -> None:
    section = zebra_exceptions_page(report)
    section["visualContainers"] = [
        build_textbox_visual(
            "Zebra Exceptions - front-page proof",
            x=36,
            y=24,
            w=900,
            h=34,
            font_size_pt=18,
            color="#1F2937",
        ),
        build_textbox_visual(
            (
                "Exception ARR is Land + Expand only. Renewal ACV stays out of "
                "this visual; Total Open Pipeline Value is the only explicit "
                "cross-motion measure."
            ),
            x=36,
            y=58,
            w=1120,
            h=28,
            font_size_pt=10,
            color="#4B5563",
            bold=False,
        ),
        build_zebra_bi_table_visual(
            visual_type=ZEBRA_BI_TABLES_VISUAL_TYPE,
            categories=[
                {
                    "table": "d_region",
                    "field": "region",
                    "title": "Region",
                }
            ],
            values=[
                {
                    "table": "f_opportunity",
                    "field": "Exception ARR",
                    "title": "Exception ARR",
                },
                {
                    "table": "f_opportunity",
                    "field": "Exception Opps Count",
                    "title": "Exception opps",
                },
                {
                    "table": "f_opportunity",
                    "field": "At Risk Opps ARR",
                    "title": "At-risk ARR",
                },
                {
                    "table": "f_opportunity",
                    "field": "Watch Opps ARR",
                    "title": "Watch ARR",
                },
            ],
            x=36,
            y=104,
            w=900,
            h=420,
        ),
    ]


def reorder_proof_pages(report: dict) -> None:
    exceptions = zebra_exceptions_page(report)
    stage = stage_hygiene_page(report)
    proof_pages = [exceptions, stage]
    reordered = proof_pages + [s for s in report.get("sections", []) if s not in proof_pages]
    for ordinal, page in enumerate(reordered):
        page["ordinal"] = ordinal
    report["sections"] = reordered


def _license_settings(license_key: str) -> list[dict]:
    now = datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return [
        {
            "properties": {
                "licenseKey": {"expr": {"Literal": {"Value": f"'{license_key}'"}}},
                "lastLicenseCheck": {"expr": {"Literal": {"Value": f"'{now}'"}}},
            }
        }
    ]


def existing_local_license_settings(report: dict) -> list[dict] | None:
    """Return the first local Zebra license settings block already in the lab."""
    for section in report.get("sections", []):
        for visual in section.get("visualContainers", []):
            config = json.loads(visual.get("config", "{}"))
            single_visual = config.get("singleVisual", {})
            if "zebra" not in single_visual.get("visualType", "").lower():
                continue
            settings = (single_visual.get("objects") or {}).get("licenseSettings")
            if settings:
                return settings
    return None


def inject_local_license_settings(report: dict, license_settings: list[dict]) -> None:
    for section in report.get("sections", []):
        for visual in section.get("visualContainers", []):
            config = json.loads(visual.get("config", "{}"))
            single_visual = config.get("singleVisual", {})
            if "zebra" not in single_visual.get("visualType", "").lower():
                continue
            objects = single_visual.setdefault("objects", {})
            objects["licenseSettings"] = license_settings
            visual["config"] = json.dumps(config)

            if visual.get("dataTransforms"):
                data_transforms = json.loads(visual["dataTransforms"])
                data_transforms.setdefault("objects", {})["licenseSettings"] = license_settings
                visual["dataTransforms"] = json.dumps(data_transforms)


def inject_local_license(report: dict, license_key: str) -> None:
    """Inject a Zebra key into local lab visuals only.

    This is deliberately opt-in through an environment variable and is not used
    by the repo builder/test path.
    """
    inject_local_license_settings(report, _license_settings(license_key))


def apply_lab_proof(lab_root: Path, source_pbix: Path) -> Path:
    target_report_dir = report_dir(lab_root)
    report_json = target_report_dir / "report.json"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = target_report_dir / f"report.pre_zebra_lab_proof_{timestamp}.json"
    shutil.copy2(report_json, backup)

    copy_custom_visuals(source_pbix, target_report_dir)
    report = json.loads(report_json.read_text(encoding="utf-8"))
    license_settings = existing_local_license_settings(report)
    ensure_resource_packages(report)
    apply_stage_hygiene_proof(report)
    apply_zebra_exceptions_proof(report)
    apply_spine_rebuild_to_main_page(report)
    reorder_proof_pages(report)
    if license_key := os.environ.get("ZEBRA_BI_LICENSE_KEY"):
        inject_local_license(report, license_key)
    elif license_settings:
        inject_local_license_settings(report, license_settings)
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--lab-root", type=Path, default=DEFAULT_LAB_ROOT)
    parser.add_argument("--source-pbix", type=Path, default=DEFAULT_SOURCE_PBIX)
    args = parser.parse_args()
    backup = apply_lab_proof(args.lab_root.expanduser(), args.source_pbix.expanduser())
    print("applied Zebra BI lab proof")
    print(f"backup: {backup}")
    print(f"lab: {args.lab_root.expanduser()}")


if __name__ == "__main__":
    main()
