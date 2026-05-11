"""Tests for the RW native visual vocabulary upgrade audit."""

from __future__ import annotations

from pathlib import Path

from scripts.sales._pbir_helpers import build_textbox_visual
from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_native_visual_upgrade_audit import (
    audit_native_visual_upgrades,
    write_markdown,
)


def test_native_visual_upgrade_audit_accepts_growth_mix_v2_heatmaps():
    result = audit_native_visual_upgrades(compose_report({"sections": []}))

    assert result["schema"] == "rw-native-visual-upgrade-audit.v1"
    assert not any(
        finding["id"] == "growth_mix_missing_source_heatmap"
        for finding in result["findings"]
    )
    assert not any(
        finding["id"] == "growth_mix_missing_motion_heatmap"
        for finding in result["findings"]
    )
    assert not any(finding["page"] == "Renewals" for finding in result["findings"])


def test_native_visual_upgrade_audit_flags_missing_growth_source_heatmap():
    report = {
        "sections": [
            {
                "displayName": "Growth Mix",
                "visualContainers": [
                    build_textbox_visual("Growth Mix", x=24, y=12, w=420, h=28)
                ],
            }
        ]
    }

    result = audit_native_visual_upgrades(report)

    assert any(
        finding["id"] == "growth_mix_missing_source_heatmap"
        and finding["severity"] == "high"
        for finding in result["findings"]
    )


def test_native_visual_upgrade_audit_writes_markdown(tmp_path: Path):
    result = audit_native_visual_upgrades(compose_report({"sections": []}))
    out = tmp_path / "visual_upgrade.md"

    write_markdown(result, out)

    text = out.read_text()
    assert "# RW Native Visual Upgrade Audit" in text
    assert "Target Visual Vocabulary" in text
