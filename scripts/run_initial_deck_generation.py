#!/usr/bin/env python3
"""Run the intentional initial Sales Director deck-generation harness.

This is the entrypoint for the first deck-generation pass that later flows into
the APAC meeting spine and regional package. It composes the existing factory
pieces instead of duplicating them:

1. verify the think-cell production libraries are importable from the venv;
2. resolve visual decisions through the infra capability map;
3. optionally refresh Salesforce/Excel source artifacts;
4. build the director `.ppttc` against the named LAND seed;
5. render the native seed-bound deck through `tcrender` / VM `ppttc.exe`;
6. run the current regional production line for the director;
7. record a manifest with the outputs and stop conditions.

It does not publish by default.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent
SEED_TEMPLATE = ROOT / "assets" / "LAND_thinkcell_seed.pptx"


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


def _python() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _director_by_slug(slug: str) -> dict[str, Any]:
    for director in canonical_directors():
        if _slug(str(director["name"])) == slug:
            return director
    raise SystemExit(f"unknown director slug: {slug}")


def _run_dir(period: str, director_slug: str, stamp: str) -> Path:
    return (
        ROOT
        / "state"
        / period
        / director_slug
        / "factory"
        / "initial-deck-generation"
        / stamp
    )


def _ppttc_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / f"{director_slug}-LAND-{period}.ppttc"


def _native_seed_render_output(run_dir: Path, period: str, director_slug: str) -> Path:
    return run_dir / f"{director_slug}-LAND-{period}-seed-bound.pptx"


def _linked_deck(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / f"{director_slug}-LAND-{period}-table-image-linked.pptx"


def _meeting_spine(period: str, director_slug: str) -> Path:
    return (
        ROOT
        / "state"
        / period
        / director_slug
        / "factory"
        / "meeting-spine"
        / f"{director_slug}-LAND-{period}-meeting-spine.pptx"
    )


def _connected_factory(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / "factory" / "connected" / "connected_factory.xlsx"


def _trends_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / "trends.json"


def _brief_path(period: str, director_slug: str) -> Path:
    return ROOT / "state" / period / director_slug / "brief.md"


def _default_candidate_manifest(period: str, director_slug: str) -> Path | None:
    root = ROOT / "state" / period / "__regional__" / "thinkcell_insertion_pilot"
    if not root.exists():
        return None
    candidates: list[tuple[int, str, Path]] = []
    for path in sorted(root.glob("*/manifest.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if payload.get("director_slug") != director_slug:
            continue
        statuses = {str(contract.get("status")) for contract in payload.get("contracts", [])}
        score = 0
        if payload.get("overall_status") == "candidate_created":
            score += 10
        if statuses and statuses == {"candidate_created"}:
            score += 5
        if payload.get("plan_only") is False:
            score += 1
        candidates.append((score, path.parent.name, path))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][2]


def _run_step(
    name: str,
    command: list[str],
    *,
    run_dir: Path,
    plan_only: bool,
) -> StepResult:
    if plan_only:
        return StepResult(name=name, status="planned", command=command)
    logs = run_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
    stdout_log = logs / f"{name}.stdout.log"
    stderr_log = logs / f"{name}.stderr.log"
    stdout_log.write_text(result.stdout, encoding="utf-8")
    stderr_log.write_text(result.stderr, encoding="utf-8")
    return StepResult(
        name=name,
        status="pass" if result.returncode == 0 else "fail",
        command=command,
        elapsed_seconds=round(time.time() - started, 2),
        returncode=result.returncode,
        stdout_log=str(stdout_log),
        stderr_log=str(stderr_log),
    )


def _can_continue(steps: list[StepResult]) -> bool:
    return all(step.status in {"pass", "planned", "skip"} for step in steps)


def _artifact_preflight(period: str, director_slug: str) -> StepResult:
    required = {
        "trends_json": _trends_path(period, director_slug),
        "brief_md": _brief_path(period, director_slug),
        "connected_factory_workbook": _connected_factory(period, director_slug),
        "ppttc": _ppttc_path(period, director_slug),
        "seed_template": SEED_TEMPLATE,
    }
    missing = [f"{name}: {path}" for name, path in required.items() if not path.exists()]
    return StepResult(
        name="source_artifact_preflight",
        status="fail" if missing else "pass",
        command=["internal"],
        notes=(["missing " + item for item in missing] if missing else [f"{len(required)} required artifacts present"]),
    )


def _library_preflight_command() -> list[str]:
    return [
        _python(),
        "-c",
        "import tcrender, tc_com_driver, tcxml; print('thinkcell production libs importable')",
    ]


def _source_refresh_command(period: str, director_slug: str, jobs: int) -> list[str]:
    return [
        _python(),
        "scripts/run_regional_production_line.py",
        "--period",
        period,
        "--director-slug",
        director_slug,
        "--refresh-source",
        "--source-only",
        "--rebuild-connected-factories",
        "--jobs",
        str(jobs),
    ]


def _ppttc_build_command(period: str, director: dict[str, Any]) -> list[str]:
    return [
        _python(),
        "scripts/build_ppttc.py",
        "--director",
        str(director["name"]),
        "--period",
        period,
        "--template",
        str(SEED_TEMPLATE),
        "--strict-template",
    ]


def _ppttc_validation_command(period: str, director_slug: str, run_dir: Path) -> list[str]:
    return [
        _python(),
        "scripts/run_ppttc_factory_validation.py",
        "--period",
        period,
        "--strict",
        "--ppttc",
        str(_ppttc_path(period, director_slug)),
        "--output-dir",
        str(run_dir / "ppttc_validation"),
    ]


def _infra_resolution_command(
    period: str,
    director_slug: str,
    run_dir: Path,
    candidate_manifest: Path | None,
) -> list[str]:
    command = [
        _python(),
        "scripts/resolve_thinkcell_infra_plan.py",
        "--period",
        period,
        "--director-slug",
        director_slug,
        "--write",
        "--output",
        str(run_dir / "thinkcell_infra_resolution.json"),
    ]
    if candidate_manifest:
        command.extend(["--candidate-manifest", str(candidate_manifest)])
    return command


def _native_seed_render_command(period: str, director_slug: str, run_dir: Path, host: str) -> list[str]:
    return [
        _python(),
        "scripts/build_ppttc_demo.py",
        "--ppttc",
        str(_ppttc_path(period, director_slug)),
        "--template-override",
        str(SEED_TEMPLATE),
        "--out",
        str(_native_seed_render_output(run_dir, period, director_slug)),
        "--ssh-host",
        host,
    ]


def _production_command(args: argparse.Namespace, director_slug: str) -> list[str]:
    command = [
        _python(),
        "scripts/run_regional_production_line.py",
        "--period",
        args.period,
        "--director-slug",
        director_slug,
        "--jobs",
        str(args.jobs),
    ]
    if not args.package_review and not args.sharepoint_publish:
        command.append("--skip-package")
    if args.full_table_image_refresh:
        command.extend(["--full-table-image-refresh", "--host", args.host])
    if args.refresh_sparse_tables:
        command.extend(["--refresh-sparse-tables", "--host", args.host])
    if args.sharepoint_publish:
        command.append("--sharepoint-publish")
    elif args.sharepoint_validate:
        command.append("--sharepoint-validate")
    return command


def _manifest(
    *,
    args: argparse.Namespace,
    director: dict[str, Any],
    director_slug: str,
    run_dir: Path,
    candidate_manifest: Path | None,
    steps: list[StepResult],
) -> dict[str, Any]:
    status = "planned" if args.plan_only else ("pass" if _can_continue(steps) else "fail")
    outputs = {
        "run_dir": str(run_dir),
        "ppttc": str(_ppttc_path(args.period, director_slug)),
        "native_seed_render": str(_native_seed_render_output(run_dir, args.period, director_slug)),
        "linked_deck": str(_linked_deck(args.period, director_slug)),
        "meeting_spine": str(_meeting_spine(args.period, director_slug)),
        "infra_resolution": str(run_dir / "thinkcell_infra_resolution.json"),
    }
    return {
        "schema": "initial-deck-generation/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "period": args.period,
        "profile": args.profile,
        "director": str(director["name"]),
        "director_slug": director_slug,
        "territory": str(director["scope_label"]),
        "publish": bool(args.sharepoint_publish),
        "candidate_manifest": str(candidate_manifest) if candidate_manifest else None,
        "thinkcell_stack": {
            "native_render": "tcrender.TcRenderClient -> VM ppttc.exe",
            "com_update": "tc_com_driver / Excel COM UpdateBatch",
            "table_lane": "AddRangeImage table-image donor",
            "xml_guardrail": "tcxml",
            "ai_core": "optional enrichment only; not used for financial truth in this harness",
        },
        "outputs": outputs,
        "steps": [asdict(step) for step in steps],
    }


def _write_manifest(run_dir: Path, manifest: dict[str, Any]) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def run(args: argparse.Namespace) -> dict[str, Any]:
    context = context_for_period(args.period)
    director_slug = args.director_slug or (context.apac_strict_slug if args.profile == "apac" else "")
    if not director_slug:
        raise SystemExit("--director-slug is required unless --profile apac is used")
    director = _director_by_slug(director_slug)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = _run_dir(args.period, director_slug, "plan" if args.plan_only else stamp)
    if not args.plan_only:
        run_dir.mkdir(parents=True, exist_ok=True)

    candidate_manifest = args.candidate_manifest or _default_candidate_manifest(args.period, director_slug)

    steps: list[StepResult] = []
    steps.append(
        _run_step(
            "thinkcell_library_preflight",
            _library_preflight_command(),
            run_dir=run_dir,
            plan_only=args.plan_only,
        )
    )

    if _can_continue(steps):
        steps.append(
            _run_step(
                "thinkcell_infra_resolution",
                _infra_resolution_command(args.period, director_slug, run_dir, candidate_manifest),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if args.refresh_source and _can_continue(steps):
        steps.append(
            _run_step(
                "source_refresh_and_connected_factory",
                _source_refresh_command(args.period, director_slug, args.jobs),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if _can_continue(steps):
        steps.append(
            _run_step(
                "ppttc_build_from_seed",
                _ppttc_build_command(args.period, director),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if _can_continue(steps):
        if args.plan_only:
            steps.append(StepResult("source_artifact_preflight", "planned", ["internal"]))
        else:
            steps.append(_artifact_preflight(args.period, director_slug))

    if _can_continue(steps):
        steps.append(
            _run_step(
                "ppttc_strict_validation",
                _ppttc_validation_command(args.period, director_slug, run_dir),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if args.use_thinkcell_render and _can_continue(steps):
        steps.append(
            _run_step(
                "native_seed_render_tcrender",
                _native_seed_render_command(args.period, director_slug, run_dir, args.host),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    if _can_continue(steps):
        steps.append(
            _run_step(
                "regional_director_deck_flow",
                _production_command(args, director_slug),
                run_dir=run_dir,
                plan_only=args.plan_only,
            )
        )

    manifest = _manifest(
        args=args,
        director=director,
        director_slug=director_slug,
        run_dir=run_dir,
        candidate_manifest=candidate_manifest,
        steps=steps,
    )
    if not args.plan_only:
        manifest_path = _write_manifest(run_dir, manifest)
        manifest["manifest_path"] = str(manifest_path)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug")
    parser.add_argument("--profile", choices=["apac", "regional"], default="apac")
    parser.add_argument("--host", default="Windows-VM")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--refresh-source", action="store_true")
    parser.add_argument("--full-table-image-refresh", action="store_true")
    parser.add_argument("--refresh-sparse-tables", action="store_true")
    parser.add_argument("--package-review", action="store_true")
    parser.add_argument("--sharepoint-publish", action="store_true")
    parser.add_argument("--sharepoint-validate", action="store_true")
    parser.add_argument("--no-publish", dest="sharepoint_publish", action="store_false")
    parser.set_defaults(use_thinkcell_render=True, sharepoint_publish=False)
    parser.add_argument("--use-thinkcell-render", dest="use_thinkcell_render", action="store_true")
    parser.add_argument("--no-thinkcell-render", dest="use_thinkcell_render", action="store_false")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.sharepoint_publish and args.plan_only:
        print("error: --sharepoint-publish cannot be combined with --plan-only", file=sys.stderr)
        return 2
    manifest = run(args)
    if args.plan_only:
        print("plan_only_no_write=true")
        print(json.dumps(manifest, indent=2, default=str))
    else:
        print(f"manifest={manifest['manifest_path']}")
    for step in manifest["steps"]:
        print(f"{step['status'].upper():>7} {step['name']}")
    return 0 if manifest["status"] in {"pass", "planned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
