"""One orchestrator for the full land_review_full_28 lane.

Order:
  1. validate registry
  2. validate template contract (against tcseed)
  3. for each director:
     a. build source notes
     b. compute metrics & insight titles
     c. build .ppttc + evidence manifest
     d. render via tcrender (Mac->VM->Mac)
     e. refresh AddRangeImage table images
     f. verify render bindings
  4. write regional summary
  5. exit non-zero on any required failure (strict mode)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable

# Canonical 9 MD-1 directors. Source of truth: scripts/_directors.py
# (see also docs/handoffs/2026-05-04-phase0-status.md). Imported at runtime;
# falls back to the hardcoded Phase 0 list if the import fails.
try:
    sys.path.insert(0, str(REPO / "scripts"))
    from _directors import canonical_directors as _canonical_directors  # type: ignore

    DIRECTORS = [d["name"] for d in _canonical_directors()]
except Exception:
    DIRECTORS = [
        "Megan Miceli",
        "Patrick Gaughan",
        "Jesper Tyrer",
        "Sarah Pittroff",
        "Francois Thaury",
        "Dan Peppett",
        "Christian Ebbesen",
        "Mourad",
        "Adam Steinhouse",
    ]


def _run(cmd: list[str], step: str) -> int:
    print(f"==> {step}")
    return subprocess.run(cmd, cwd=REPO).returncode


def _slug(name: str) -> str:
    return name.replace(" ", "-")


def _process_director(name: str, period: str, template: Path, registry: Path, strict: bool) -> dict:
    slug = _slug(name)
    director_dir = REPO / "state" / period / slug
    director_dir.mkdir(parents=True, exist_ok=True)

    steps: list[tuple[str, list[str]]] = [
        (
            "source_notes",
            [PY, "scripts/build_source_notes.py", "--out", str(director_dir / "source_notes.json")],
        ),
        (
            "insight_titles",
            [
                PY,
                "scripts/build_insight_titles.py",
                "--metrics",
                str(director_dir / "metrics.json"),
                "--rules",
                "config/rules/land_review_insight_titles.yml",
                "--out",
                str(director_dir / "insight_titles.json"),
            ],
        ),
        (
            "ppttc",
            [
                PY,
                "scripts/build_ppttc.py",
                "--director",
                name,
                "--period",
                period,
                "--registry",
                str(registry),
                "--template",
                str(template),
                "--emit-evidence-manifest",
                "--out-dir",
                str(director_dir),
            ],
        ),
        # Render is delegated to libs/tcrender; assume an existing CLI surface.
        # If `python -m tcrender` doesn't exist, this step fails and the strict
        # gate stops the director. That's fine for MVP — orchestrator wires
        # the calls; downstream tooling exists per PR 7.
        (
            "render",
            [
                PY,
                "-m",
                "tcrender",
                "--ppttc",
                str(director_dir / f"{slug}-LAND-{period}.ppttc"),
                "--template",
                str(template),
                "--out",
                str(director_dir / "rendered_stage1.pptx"),
            ],
        ),
        (
            "refresh_images",
            [
                PY,
                "scripts/refresh_thinkcell_table_images.py",
                "--pptx",
                str(director_dir / "rendered_stage1.pptx"),
                "--workbook",
                str(director_dir / "land.model.xlsx"),
                "--registry",
                str(registry),
                "--out",
                str(director_dir / "rendered_final.pptx"),
            ],
        ),
        (
            "verify",
            [
                PY,
                "scripts/verify_render_bindings.py",
                "--pptx",
                str(director_dir / "rendered_final.pptx"),
                "--manifest",
                str(director_dir / "render_evidence_manifest.json"),
                "--out",
                str(director_dir / "qa_report.json"),
            ],
        ),
    ]

    statuses: dict[str, str] = {}
    for step_name, cmd in steps:
        rc = _run(cmd, f"{name} :: {step_name}")
        statuses[step_name] = "pass" if rc == 0 else "fail"
        if rc != 0 and strict:
            return {
                "director": name,
                "status": "fail",
                "first_failure": step_name,
                "steps": statuses,
            }

    overall = "pass" if all(v == "pass" for v in statuses.values()) else "fail"
    return {"director": name, "status": overall, "steps": statuses}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--directors", nargs="*", default=["all"])
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument(
        "--registry", default="config/thinkcell/land_review_full_28.binding_registry.yml"
    )
    parser.add_argument(
        "--template", default="assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx"
    )
    args = parser.parse_args(argv)

    if args.directors == ["all"]:
        directors = DIRECTORS
    else:
        directors = [d.replace("-", " ") for d in args.directors]

    # 1 + 2: registry + template preflight (once)
    rc = _run(
        [PY, "scripts/validate_thinkcell_binding_registry.py", "--registry", args.registry],
        "validate_registry",
    )
    if rc != 0:
        return rc

    contract_out = REPO / "state" / args.period / "__regional__" / "template_contract_report.json"
    contract_out.parent.mkdir(parents=True, exist_ok=True)
    rc = _run(
        [
            PY,
            "scripts/verify_thinkcell_template_contract.py",
            "--template",
            args.template,
            "--registry",
            args.registry,
            "--out",
            str(contract_out),
        ],
        "verify_template_contract",
    )
    if rc != 0:
        return rc

    # 3: per-director
    results: list[dict] = []
    if args.jobs > 1:
        with ThreadPoolExecutor(max_workers=args.jobs) as ex:
            futs = {
                ex.submit(
                    _process_director,
                    d,
                    args.period,
                    Path(args.template),
                    Path(args.registry),
                    args.strict,
                ): d
                for d in directors
            }
            for f in as_completed(futs):
                results.append(f.result())
    else:
        for d in directors:
            results.append(
                _process_director(
                    d, args.period, Path(args.template), Path(args.registry), args.strict
                )
            )

    # 4: regional summary
    summary = {
        "period": args.period,
        "deck_family": "land_review_full_28",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "directors": results,
        "passed": sum(1 for r in results if r["status"] == "pass"),
        "failed": sum(1 for r in results if r["status"] == "fail"),
    }
    summary_path = (
        REPO / "state" / args.period / "__regional__" / "land_review_full_28_run_summary.json"
    )
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
