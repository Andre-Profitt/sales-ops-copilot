#!/usr/bin/env python3
"""Refresh the sparse linked table-image targets across regional decks."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _directors import canonical_directors


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_HOST = "Windows-VM"
SPARSE_TARGETS = ("S09_PendingCommercialApproval", "S26_ActionItems")


@dataclass
class RefreshStep:
    director: str
    slug: str
    target: str
    status: str
    command: list[str]
    elapsed_seconds: float | None = None
    returncode: int | None = None
    stdout_log: str | None = None
    stderr_log: str | None = None


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _selected(director_slug: str | None) -> list[dict[str, Any]]:
    directors = canonical_directors()
    if not director_slug:
        return directors
    return [director for director in directors if _slug(str(director["name"])) == director_slug]


def _deck_path(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug / f"{slug}-LAND-{period}-table-image-linked.pptx"


def _backup_deck(deck: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / deck.name
    if not target.exists():
        shutil.copy2(deck, target)
    return target


def _run_step(
    director: dict[str, Any],
    *,
    period: str,
    host: str,
    target_name: str,
    run_dir: Path,
    timeout_seconds: int,
    plan_only: bool,
) -> RefreshStep:
    slug = _slug(str(director["name"]))
    command = [
        _python(),
        "scripts/build_table_image_linked_deck.py",
        "--period",
        period,
        "--director-slug",
        slug,
        "--host",
        host,
        "--refresh-existing",
        "--only-name",
        target_name,
        "--reposition-after-update",
        "--timeout-seconds",
        str(timeout_seconds),
    ]
    if plan_only:
        return RefreshStep(str(director["name"]), slug, target_name, "planned", command)

    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    stdout_log = logs_dir / f"{slug}_{target_name}.stdout.log"
    stderr_log = logs_dir / f"{slug}_{target_name}.stderr.log"
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    return RefreshStep(
        director=str(director["name"]),
        slug=slug,
        target=target_name,
        status="pass" if result.returncode == 0 else "fail",
        command=command,
        elapsed_seconds=round(time.time() - started, 2),
        returncode=result.returncode,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--director-slug")
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    directors = _selected(args.director_slug)
    if not directors:
        raise SystemExit(f"unknown director slug: {args.director_slug}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "state" / args.period / "__regional__" / "sparse_table_refresh_runs" / stamp
    backup_dir = run_dir / "backups"
    run_dir.mkdir(parents=True, exist_ok=True)

    for director in directors:
        deck = _deck_path(args.period, _slug(str(director["name"])))
        if not deck.exists():
            raise SystemExit(f"missing linked deck: {deck}")
        if not args.plan_only:
            _backup_deck(deck, backup_dir)

    steps: list[RefreshStep] = []
    for director in directors:
        for target_name in SPARSE_TARGETS:
            step = _run_step(
                director,
                period=args.period,
                host=args.host,
                target_name=target_name,
                run_dir=run_dir,
                timeout_seconds=args.timeout_seconds,
                plan_only=args.plan_only,
            )
            steps.append(step)
            print(f"{step.status.upper():>7} {step.slug:<22} {step.target}", flush=True)
            if step.status == "fail":
                break
        if steps and steps[-1].status == "fail":
            break

    manifest = {
        "status": "planned" if args.plan_only else ("pass" if all(step.status == "pass" for step in steps) else "fail"),
        "period": args.period,
        "run_dir": str(run_dir),
        "targets": list(SPARSE_TARGETS),
        "backup_dir": str(backup_dir) if not args.plan_only else None,
        "steps": [asdict(step) for step in steps],
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={manifest_path}")
    return 0 if manifest["status"] in {"pass", "planned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
