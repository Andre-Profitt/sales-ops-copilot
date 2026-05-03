from pathlib import Path

from scripts.sd_factory.artifacts import (
    ArtifactPaths,
    director_root,
    production_runs_root,
    regional_root,
    state_period_root,
    thinkcell_scaffold_root,
)
from scripts.sd_factory.context import context_for_period
from scripts.sd_factory.runner import can_continue, run_step


def test_context_wraps_existing_period_context_for_2026_q2() -> None:
    context = context_for_period("2026-Q2")

    assert context.period == "2026-Q2"
    assert context.month_label == "May 2026"
    assert context.snapshot_date == "2026-04-30"
    assert context.production_summary_title == "May 2026 Regional Production Line"


def test_artifact_paths_for_2026_q2_are_conservative() -> None:
    root = Path("/repo")
    paths = ArtifactPaths("2026-Q2", root=root, director_slug="Jesper-Tyrer")

    assert state_period_root("2026-Q2", root=root) == root / "state" / "2026-Q2"
    assert regional_root("2026-Q2", root=root) == root / "state" / "2026-Q2" / "__regional__"
    assert director_root("2026-Q2", "Jesper-Tyrer", root=root) == root / "state" / "2026-Q2" / "Jesper-Tyrer"
    assert production_runs_root("2026-Q2", root=root) == root / "state" / "2026-Q2" / "__regional__" / "production_runs"
    assert thinkcell_scaffold_root("2026-Q2", root=root) == root / "state" / "thinkcell_bridge" / "build_scaffold" / "2026-Q2"
    assert paths.state_period == root / "state" / "2026-Q2"
    assert paths.regional == root / "state" / "2026-Q2" / "__regional__"
    assert paths.director == root / "state" / "2026-Q2" / "Jesper-Tyrer"
    assert paths.production_runs == root / "state" / "2026-Q2" / "__regional__" / "production_runs"
    assert paths.thinkcell_scaffold == root / "state" / "thinkcell_bridge" / "build_scaffold" / "2026-Q2"


def test_run_step_plan_only_does_not_create_logs(tmp_path: Path) -> None:
    result = run_step(
        "sample_step",
        ["python", "-c", "raise SystemExit(99)"],
        run_dir=tmp_path,
        plan_only=True,
    )

    assert result.name == "sample_step"
    assert result.status == "planned"
    assert result.command == ["python", "-c", "raise SystemExit(99)"]
    assert result.elapsed_seconds is None
    assert result.returncode is None
    assert result.stdout_log is None
    assert result.stderr_log is None
    assert not (tmp_path / "logs").exists()
    assert can_continue([result])

