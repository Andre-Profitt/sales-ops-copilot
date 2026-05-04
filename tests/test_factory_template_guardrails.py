"""Guardrails on which template scripts/factory.py is allowed to load."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PY = sys.executable


def _run_factory(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [PY, str(REPO / "scripts" / "factory.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_factory_refuses_legacy_seed_without_override() -> None:
    legacy = REPO / "assets" / "LAND_thinkcell_seed.pptx"
    assert legacy.exists(), "fixture: legacy seed must exist on disk for this test"

    proc = _run_factory(
        "--period",
        "2026-Q2",
        "--directors",
        "Patrick-Gaughan",
        "--template",
        str(legacy),
        "--dry-run",
    )

    assert proc.returncode != 0, proc.stdout + proc.stderr
    combined = proc.stdout + proc.stderr
    assert "legacy" in combined.lower() or "quarantined" in combined.lower()


def test_factory_accepts_legacy_seed_with_override() -> None:
    legacy = REPO / "assets" / "LAND_thinkcell_seed.pptx"
    proc = _run_factory(
        "--period",
        "2026-Q2",
        "--directors",
        "Patrick-Gaughan",
        "--template",
        str(legacy),
        "--allow-legacy-seed",
        "--dry-run",
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_factory_default_points_at_tcseed() -> None:
    proc = _run_factory("--print-default-template")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "land_review_full_28" in proc.stdout
    assert "tcseed.pptx" in proc.stdout
