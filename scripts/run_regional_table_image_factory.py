#!/usr/bin/env python3
"""Run the regional Excel -> think-cell table-image deck factory.

This is the live May 2026 linked-output lane:

raw/current workbook artifacts -> connected Excel factory -> think-cell
table-image workbook -> linked PowerPoint refresh -> Mac carryover finalization
-> text polish -> publish gate -> optional SharePoint upload.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from _directors import canonical_directors


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_HOST = "Windows-VM"


@dataclass
class StepResult:
    name: str
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


def _run_step(name: str, command: list[str], *, run_dir: Path, plan_only: bool) -> StepResult:
    if plan_only:
        return StepResult(name=name, status="planned", command=command)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    stdout_log = logs_dir / f"{name}.stdout.log"
    stderr_log = logs_dir / f"{name}.stderr.log"
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    status = "pass" if result.returncode == 0 else "fail"
    return StepResult(
        name=name,
        status=status,
        command=command,
        elapsed_seconds=round(time.time() - started, 2),
        returncode=result.returncode,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )


def _deck_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / f"{director_slug}-LAND-{period}-table-image-linked.pptx"


def _workbook_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / "factory" / "connected" / "connected_factory_table_images.xlsx"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--director-slug")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--interactive-task", action="store_true")
    parser.add_argument("--skip-finalize-mac", action="store_true")
    parser.add_argument(
        "--finalize-mac",
        action="store_true",
        help="Run the Mac PowerPoint carryover/geometry finalizer after each Windows refresh.",
    )
    parser.add_argument("--finalize-close", action="store_true")
    parser.add_argument("--skip-polish", action="store_true")
    parser.add_argument("--skip-publish-gate", action="store_true")
    parser.add_argument("--upload-sharepoint", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()

    directors = _selected(args.director_slug)
    if not directors:
        raise SystemExit(f"unknown director slug: {args.director_slug}")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "state" / args.period / "__regional__" / "table_image_factory_runs" / stamp
    if not args.plan_only:
        run_dir.mkdir(parents=True, exist_ok=True)

    steps: list[StepResult] = []
    intel_cmd = [_python(), "scripts/build_regional_intelligence_specs.py", "--period", args.period]
    if args.director_slug:
        intel_cmd.extend(["--director-slug", args.director_slug])
    steps.append(_run_step("regional_intelligence_specs", intel_cmd, run_dir=run_dir, plan_only=args.plan_only))

    for director in directors:
        slug = _slug(str(director["name"]))
        command = [
            _python(),
            "scripts/build_table_image_linked_deck.py",
            "--period",
            args.period,
            "--director-slug",
            slug,
            "--host",
            args.host,
            "--all-table-images",
        ]
        if args.refresh_existing:
            command.append("--refresh-existing")
        if args.interactive_task:
            command.append("--interactive-task")
        if args.finalize_mac or (not args.skip_finalize_mac and sys.platform == "darwin"):
            command.append("--finalize-mac")
        if args.skip_finalize_mac:
            command.append("--skip-finalize-mac")
        if args.finalize_close:
            command.append("--finalize-close")
        steps.append(_run_step(f"linked_deck_{slug}", command, run_dir=run_dir, plan_only=args.plan_only))
        if steps[-1].status == "fail":
            break

    if not args.skip_polish and all(step.status in {"pass", "planned"} for step in steps):
        polish_cmd = [_python(), "scripts/polish_regional_linked_deck_text.py", "--period", args.period]
        if args.director_slug:
            polish_cmd.extend(["--director-slug", args.director_slug])
        steps.append(_run_step("polish_linked_deck_text", polish_cmd, run_dir=run_dir, plan_only=args.plan_only))

    if all(step.status in {"pass", "planned"} for step in steps):
        aspect_cmd = [_python(), "scripts/fix_table_image_aspect_ratios.py", "--period", args.period, "--linked-decks"]
        if args.director_slug:
            aspect_cmd.extend(["--director-slug", args.director_slug])
        steps.append(_run_step("table_image_aspect_polish", aspect_cmd, run_dir=run_dir, plan_only=args.plan_only))

    if not args.skip_publish_gate and all(step.status in {"pass", "planned"} for step in steps):
        steps.append(
            _run_step(
                "regional_publish_gate",
                [_python(), "scripts/run_regional_deck_publish_gate.py", "--period", args.period],
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if args.upload_sharepoint and all(step.status in {"pass", "planned"} for step in steps):
        steps.append(
            _run_step(
                "upload_sharepoint",
                [_python(), "scripts/upload_may_regional_assets_sharepoint.py", "--period", args.period],
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    manifest = {
        "status": "planned" if args.plan_only else ("pass" if all(step.status == "pass" for step in steps) else "fail"),
        "period": args.period,
        "run_dir": str(run_dir),
        "directors": [
            {
                "name": str(director["name"]),
                "slug": _slug(str(director["name"])),
                "territory": str(director["scope_label"]),
                "deck": str(_deck_path(args.period, _slug(str(director["name"])))),
                "table_image_workbook": str(_workbook_path(args.period, _slug(str(director["name"])))),
            }
            for director in directors
        ],
        "steps": [asdict(step) for step in steps],
    }
    if args.plan_only:
        print("plan_only_no_write=true")
        print(json.dumps(manifest, indent=2))
        for step in steps:
            print(f"{step.status.upper():>7} {step.name}")
        return 0

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"manifest={manifest_path}")
    for step in steps:
        print(f"{step.status.upper():>7} {step.name}")
    return 0 if manifest["status"] in {"pass", "planned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
