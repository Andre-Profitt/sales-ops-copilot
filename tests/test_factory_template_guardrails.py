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
    """Polished/charts/strip-backup variants are off-limits without override."""
    legacy = REPO / "assets" / "LAND_thinkcell_seed_polished.pptx"
    assert legacy.exists(), "fixture: legacy polished seed must exist on disk for this test"

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
    """Forensic-only override unlocks polished/etc. variants."""
    legacy = REPO / "assets" / "LAND_thinkcell_seed_polished.pptx"
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


def test_factory_default_points_at_canonical_seed() -> None:
    """Default template is the canonical programmatic seed (used by thinkcell_programmatic_lab.py)."""
    proc = _run_factory("--print-default-template")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "LAND_thinkcell_seed.pptx" in proc.stdout


def test_factory_accepts_canonical_seed_no_override() -> None:
    """Canonical seed is NOT in LEGACY_SEED_MARKERS; no --allow-legacy-seed needed."""
    canonical = REPO / "assets" / "LAND_thinkcell_seed.pptx"
    assert canonical.exists()
    proc = _run_factory(
        "--period",
        "2026-Q2",
        "--directors",
        "Patrick-Gaughan",
        "--template",
        str(canonical),
        "--dry-run",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
