from __future__ import annotations

import json
from pathlib import Path

from scripts.sales._pbir_helpers import ZEBRA_BI_TABLES_VISUAL_TYPE, build_card_visual
from scripts.sales.rw_apply_zebra_lab_proof import (
    CUSTOM_VISUALS,
    apply_lab_proof,
    remove_zebra_lab_artifacts,
)


def _custom_visual() -> dict:
    visual = build_card_visual(
        "f_opportunity",
        "Total Closed Won ARR",
        "Closed won ARR (Land + Expand)",
        x=20,
        y=20,
        w=240,
        h=120,
    )
    config = json.loads(visual["config"])
    config["singleVisual"]["visualType"] = ZEBRA_BI_TABLES_VISUAL_TYPE
    visual["config"] = json.dumps(config)
    return visual


def test_remove_zebra_lab_artifacts_strips_page_visuals_packages_and_dirs(tmp_path: Path):
    report_dir = tmp_path / "rpt.Report"
    custom_visuals_dir = report_dir / "CustomVisuals"
    (custom_visuals_dir / CUSTOM_VISUALS[0]).mkdir(parents=True)
    (custom_visuals_dir / CUSTOM_VISUALS[1]).mkdir(parents=True)
    report = {
        "resourcePackages": [
            {"resourcePackage": {"name": CUSTOM_VISUALS[0]}},
            {"resourcePackage": {"name": "NativeTheme"}},
        ],
        "sections": [
            {"name": "PageZebraExceptions", "displayName": "Zebra Exceptions", "visualContainers": [_custom_visual()]},
            {"name": "PageStageHygiene", "displayName": "Stage Hygiene", "visualContainers": [_custom_visual()]},
        ],
    }

    remove_zebra_lab_artifacts(report, report_dir)

    assert [section["displayName"] for section in report["sections"]] == ["Stage Hygiene"]
    assert report["sections"][0]["visualContainers"] == []
    assert report["resourcePackages"] == [{"resourcePackage": {"name": "NativeTheme"}}]
    assert not (custom_visuals_dir / CUSTOM_VISUALS[0]).exists()
    assert not (custom_visuals_dir / CUSTOM_VISUALS[1]).exists()


def test_apply_lab_proof_regenerates_native_report_without_source_pbix_or_custom_lab(tmp_path: Path):
    lab_root = tmp_path / "lab"
    report_dir = lab_root / "rpt.Report"
    report_dir.mkdir(parents=True)
    (report_dir / "CustomVisuals" / CUSTOM_VISUALS[0]).mkdir(parents=True)
    report_json = report_dir / "report.json"
    report_json.write_text(
        json.dumps(
            {
                "resourcePackages": [{"resourcePackage": {"name": CUSTOM_VISUALS[0]}}],
                "sections": [
                    {
                        "name": "PageZebraExceptions",
                        "displayName": "Zebra Exceptions",
                        "visualContainers": [_custom_visual()],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    backup = apply_lab_proof(lab_root, tmp_path / "missing.pbix")
    report = json.loads(report_json.read_text(encoding="utf-8"))
    display_names = {section["displayName"] for section in report["sections"]}
    encoded = json.dumps(report)

    assert backup.exists()
    assert "Zebra Exceptions" not in display_names
    assert "Product Retention" in display_names
    assert "RW KPI Explorer" in display_names
    assert all(custom not in encoded for custom in CUSTOM_VISUALS)
    assert not (report_dir / "CustomVisuals" / CUSTOM_VISUALS[0]).exists()
