"""Tests for the binding-registry validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "validate_thinkcell_binding_registry.py"
FIXTURES = REPO / "tests" / "fixtures"


def _run(registry: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(SCRIPT), "--registry", str(registry)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_minimal_fixture_passes() -> None:
    proc = _run(FIXTURES / "registry_minimal.yml")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_real_registry_passes() -> None:
    proc = _run(REPO / "config" / "thinkcell" / "land_review_full_28.binding_registry.yml")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_duplicate_name_fails(tmp_path: Path) -> None:
    bad = tmp_path / "dup.yml"
    bad.write_text(
        (FIXTURES / "registry_minimal.yml").read_text()
        + """
  - slide_id: S06
    purpose: pipeline_aging
    elements:
      - {name: S05_Title, kind: text, lane: ppttc_text, required: true, source: insight_titles.S06, evidence: exact_text}
"""
    )
    proc = _run(bad)
    assert proc.returncode != 0
    assert "duplicate" in (proc.stdout + proc.stderr).lower()


def test_unknown_lane_fails(tmp_path: Path) -> None:
    bad = tmp_path / "lane.yml"
    src = (FIXTURES / "registry_minimal.yml").read_text().replace("lane: ppttc_text", "lane: ppttc")
    bad.write_text(src)
    proc = _run(bad)
    assert proc.returncode != 0
    assert "lane" in (proc.stdout + proc.stderr).lower()


def test_chart_kind_must_use_chart_lane(tmp_path: Path) -> None:
    """A bar_chart bound to ppttc_text is a registry error."""
    bad = tmp_path / "kindmismatch.yml"
    src = (
        (FIXTURES / "registry_minimal.yml")
        .read_text()
        .replace("lane: ppttc_chart", "lane: ppttc_text")
    )
    bad.write_text(src)
    proc = _run(bad)
    assert proc.returncode != 0
    assert (
        "lane" in (proc.stdout + proc.stderr).lower()
        or "kind" in (proc.stdout + proc.stderr).lower()
    )


def test_image_suffix_consistency(tmp_path: Path) -> None:
    """Names with kind table_image must end in _Image."""
    bad = tmp_path / "suffix.yml"
    bad.write_text(
        """schema: salesops/thinkcell-binding-registry/v1
deck_family: land_review_full_28
brand: simcorp
period_context: 2026-Q2
rules:
  arr_basis: x
  currency_basis: x
  stage_basis: x
  title_rule: x
  source_rule: x
lanes:
  ppttc_chart: x
  ppttc_text: x
  excel_table_image: x
  static: x
slides:
  - slide_id: S07
    purpose: top_deals_land
    elements:
      - {name: S07_TopDealsLand_IMG, kind: table_image, lane: excel_table_image, required: true, source: workbook.range.X, evidence: picture_on_slide}
"""
    )
    proc = _run(bad)
    assert proc.returncode != 0
    assert (
        "_image" in (proc.stdout + proc.stderr).lower()
        or "suffix" in (proc.stdout + proc.stderr).lower()
    )
