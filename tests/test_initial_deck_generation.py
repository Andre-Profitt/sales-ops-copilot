"""Tests for scripts/run_initial_deck_generation.py."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import run_initial_deck_generation as mod  # noqa: E402


def _args(**overrides):
    base = dict(
        period="2026-Q2",
        director_slug="Jesper-Tyrer",
        profile="apac",
        host="Windows-VM",
        jobs=1,
        candidate_manifest=None,
        plan_only=True,
        refresh_source=False,
        full_table_image_refresh=False,
        refresh_sparse_tables=False,
        package_review=False,
        sharepoint_publish=False,
        sharepoint_validate=False,
        use_thinkcell_render=True,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_default_plan_uses_apac_director_when_slug_omitted():
    args = _args(director_slug=None)
    manifest = mod.run(args)

    assert manifest["status"] == "planned"
    assert manifest["profile"] == "apac"
    assert manifest["director_slug"] == "Jesper-Tyrer"


def test_plan_includes_thinkcell_render_before_regional_flow():
    manifest = mod.run(_args())
    steps = [step["name"] for step in manifest["steps"]]

    assert steps == [
        "thinkcell_library_preflight",
        "thinkcell_infra_resolution",
        "ppttc_build_from_seed",
        "source_artifact_preflight",
        "ppttc_strict_validation",
        "native_seed_render_tcrender",
        "regional_director_deck_flow",
    ]
    assert manifest["thinkcell_stack"]["native_render"] == "tcrender.TcRenderClient -> VM ppttc.exe"


def test_refresh_source_plan_inserts_source_refresh_before_ppttc_build():
    manifest = mod.run(_args(refresh_source=True))
    steps = [step["name"] for step in manifest["steps"]]

    assert steps.index("source_refresh_and_connected_factory") < steps.index("ppttc_build_from_seed")


def test_no_thinkcell_render_skips_native_seed_render_step():
    manifest = mod.run(_args(use_thinkcell_render=False))
    steps = [step["name"] for step in manifest["steps"]]

    assert "native_seed_render_tcrender" not in steps
    assert "regional_director_deck_flow" in steps


def test_production_command_skips_package_by_default_and_adds_table_refresh():
    args = _args(plan_only=False, full_table_image_refresh=True)
    command = mod._production_command(args, "Jesper-Tyrer")

    assert "--skip-package" in command
    assert "--full-table-image-refresh" in command
    assert "--host" in command
