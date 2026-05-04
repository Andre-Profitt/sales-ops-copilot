"""Tests for the insight-title rules engine.

Each rule has a `when` predicate evaluated against a director's
metric blob, and a `title` template that interpolates metric values.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "build_insight_titles.py"


def test_late_stage_gap_fires(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "stage_5_plus_arr": 1_500_000,
                "total_open_arr": 38_500_000,
                "stage_5_plus_arr_share": 0.039,
                "omitted_arr": 5_000_000,
                "omitted_arr_share": 0.13,
            }
        )
    )
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    titles = json.loads(out.read_text())
    assert "Late-stage" in titles["S05"] or "late-stage" in titles["S05"].lower()
    assert "3.9" in titles["S05"]


def test_default_title_used_when_no_rule_fires(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "stage_5_plus_arr_share": 0.40,
                "omitted_arr_share": 0.10,
            }
        )
    )
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    proc = subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0
    titles = json.loads(out.read_text())
    # No rule fires; default falls back to a non-empty deterministic string
    assert isinstance(titles["S05"], str) and titles["S05"]
    assert titles["S05"] != ""


def test_every_analytic_slide_has_title(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({}))  # empty — force defaults
    out = tmp_path / "titles.json"
    rules = REPO / "config" / "rules" / "land_review_insight_titles.yml"

    subprocess.run(
        [PY, str(SCRIPT), "--metrics", str(metrics), "--rules", str(rules), "--out", str(out)],
        check=True,
        cwd=REPO,
    )
    titles = json.loads(out.read_text())
    # All analytic slides must have a non-empty title
    analytic = [
        "S02",
        "S04",
        "S05",
        "S06",
        "S07",
        "S08",
        "S09",
        "S11",
        "S12",
        "S13",
        "S15",
        "S16",
        "S17",
        "S18",
        "S19",
        "S21",
        "S22",
        "S23",
        "S24",
        "S25",
        "S26",
        "S27",
    ]
    for sid in analytic:
        assert sid in titles, f"missing title for {sid}"
        assert titles[sid], f"empty title for {sid}"
