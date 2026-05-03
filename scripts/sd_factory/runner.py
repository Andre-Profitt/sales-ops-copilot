"""Reusable step-runner primitives for the Sales Director factory."""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from scripts.sd_factory.artifacts import repo_root


@dataclass
class StepResult:
    name: str
    status: str
    command: list[str]
    elapsed_seconds: float | None = None
    returncode: int | None = None
    stdout_log: str | None = None
    stderr_log: str | None = None
    notes: list[str] | None = None


def run_step(
    name: str,
    command: Sequence[str | Path],
    *,
    run_dir: Path,
    plan_only: bool = False,
    cwd: Path | None = None,
) -> StepResult:
    """Run a command and capture logs, or return a planned step."""

    command_list = [str(part) for part in command]
    if plan_only:
        return StepResult(name=name, status="planned", command=command_list)

    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(
        command_list,
        cwd=cwd or repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_log = logs / f"{name}.stdout.log"
    stderr_log = logs / f"{name}.stderr.log"
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    return StepResult(
        name=name,
        status="pass" if result.returncode == 0 else "fail",
        command=command_list,
        elapsed_seconds=round(time.time() - started, 2),
        returncode=result.returncode,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )


def can_continue(steps: Sequence[StepResult]) -> bool:
    """Return whether all prior steps allow the pipeline to continue."""

    return all(step.status in {"pass", "planned", "skip"} for step in steps)


__all__ = ["StepResult", "can_continue", "run_step"]

