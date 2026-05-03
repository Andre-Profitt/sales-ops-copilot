#!/usr/bin/env python3
"""Bounded factory harness for one Sales Director LAND deck.

This is a sidecar orchestrator. It does not change the deck generators; it
calls the existing scripts, records gate outcomes, and emits a publish-gate
report for the operator.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
DEFAULT_DIRECTOR = "Jesper Tyrer"
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_HOST = "Windows-VM"
EXPECTED_SLIDES = 28
MAX_NATIVE_EMBEDDINGS = 0
MIN_NATIVE_TABLES = 12
FORBIDDEN_TEXT = (
    "Keywords:",
    "This slide contains",
    "Insert your desired text",
    "Insert chart title here",
    "[think-cell",
    "Pipe-movement bridge",
    "Stage × Industry",
    "Sales velocity",
    "Pipeline creation velocity",
    "GRR proxy",
    "old APAC",
    "Rebekka",
    "current deck had",
    "ready for rehearsal",
    "publish blockers",
    "Original Apr 20 pack",
    "CreatedDate velocity proxy",
    "sales-velocity proxy",
    "unwtd",
    "ARR unwtd",
    "ARR (unwtd)",
)


@dataclass
class GateResult:
    name: str
    status: str
    command: list[str] = field(default_factory=list)
    artifacts: list[Path] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    started_at: str | None = None
    elapsed_seconds: float | None = None
    returncode: int | None = None


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _python() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _director_dir(period: str, director: str) -> Path:
    return STATE_DIR / period / _slug(director)


def _factory_dir(period: str, director: str) -> Path:
    return _director_dir(period, director) / "factory"


def _connected_factory_workbook(period: str, director: str) -> Path:
    return _factory_dir(period, director) / "connected" / "connected_factory.xlsx"


def _connected_factory_spec(period: str, director: str) -> Path:
    return _factory_dir(period, director) / "connected" / "connected_factory_spec.json"


def _cmd_text(command: list[str]) -> str:
    return " ".join(command)


def _run_gate(name: str, command: list[str], *, factory_dir: Path) -> GateResult:
    logs_dir = factory_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    elapsed = time.time() - started
    (logs_dir / f"{name}.stdout.log").write_text(result.stdout)
    (logs_dir / f"{name}.stderr.log").write_text(result.stderr)
    status = "pass" if result.returncode == 0 else "fail"
    notes = [f"stdout: {logs_dir / f'{name}.stdout.log'}"]
    if result.stderr:
        notes.append(f"stderr: {logs_dir / f'{name}.stderr.log'}")
    return GateResult(
        name=name,
        status=status,
        command=command,
        notes=notes,
        started_at=dt.datetime.now().isoformat(timespec="seconds"),
        elapsed_seconds=round(elapsed, 2),
        returncode=result.returncode,
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _brief_sections(path: Path) -> list[str]:
    sections = []
    for line in path.read_text().splitlines():
        if line.startswith("## "):
            sections.append(line[3:].strip())
    return sections


def _source_artifacts_gate(period: str, director: str) -> GateResult:
    director_dir = _director_dir(period, director)
    required = [
        director_dir / "trends.json",
        director_dir / "brief.md",
        director_dir / "land.model.xlsx",
        director_dir / "land.xlsx",
    ]
    missing = [path for path in required if not path.exists()]
    notes = [] if not missing else [f"missing: {', '.join(str(path) for path in missing)}"]
    status = "pass" if not missing else "fail"
    if not missing:
        trends = _read_json(director_dir / "trends.json")
        trends_director = (trends.get("director") or {}).get("name")
        if trends.get("period") != period:
            status = "fail"
            notes.append(f"trends period mismatch: {trends.get('period')!r}")
        if trends_director != director:
            status = "fail"
            notes.append(f"trends director mismatch: {trends_director!r}")
        notes.append(f"schema_version: {trends.get('schema_version', '(missing)')}")
    return GateResult(
        name="source_fact_extraction",
        status=status,
        artifacts=required,
        notes=notes,
    )


def _build_narrative_spec(period: str, director: str, *, write: bool) -> GateResult:
    director_dir = _director_dir(period, director)
    trends_path = director_dir / "trends.json"
    brief_path = director_dir / "brief.md"
    spec_path = _factory_dir(period, director) / "narrative_spec.json"
    if not trends_path.exists() or not brief_path.exists():
        return GateResult(
            name="narrative_spec",
            status="fail",
            artifacts=[trends_path, brief_path],
            notes=["source artifacts must exist before narrative spec synthesis"],
        )

    trends = _read_json(trends_path)
    sections = _brief_sections(brief_path)
    required_sections = {"Headline", "Action items", "KPIs"}
    missing_sections = sorted(required_sections - set(sections))
    spec = {
        "schema": "director-land-narrative-spec/v1",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "director": director,
        "period": period,
        "motion": "LAND",
        "source_artifacts": {
            "trends_json": str(trends_path),
            "brief_md": str(brief_path),
        },
        "checks": {
            "brief_sections": sections,
            "missing_required_sections": missing_sections,
            "highlights": len(trends.get("highlights") or []),
            "risks": len(trends.get("risks") or []),
            "action_items": len(trends.get("action_items") or []),
            "top_deals_named": len(trends.get("top_deals_named") or []),
            "pending_commercial_approval_named": len(
                trends.get("pending_commercial_approval_named") or []
            ),
            "at_risk_renewals_named": len(trends.get("at_risk_renewals_named") or []),
        },
        "deck_intent": {
            "audience": "Sales Director",
            "headline_motion": "Land + Expand ARR",
            "separate_renewal_motion": "Renewal ACV",
            "currency": trends.get("currency") or "EUR",
            "publish_rule": "ARR and ACV remain separate; source facts are director-scoped.",
        },
    }

    status = "pass" if not missing_sections else "fail"
    notes = []
    if missing_sections:
        notes.append(f"missing brief sections: {', '.join(missing_sections)}")
    if write:
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, indent=2))
        notes.append(f"wrote {spec_path}")
    return GateResult(
        name="narrative_spec",
        status=status,
        artifacts=[spec_path],
        notes=notes,
    )


def _validate_pptx(path: Path, *, director: str, period: str) -> GateResult:
    notes: list[str] = []
    if not path.exists() or path.stat().st_size == 0:
        return GateResult(
            name="render_package_validation",
            status="fail",
            artifacts=[path],
            notes=[f"final deck missing or empty: {path}"],
        )
    try:
        with ZipFile(path) as zf:
            names = zf.namelist()
            slides = [
                name
                for name in names
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            ]
            embeddings = [name for name in names if name.startswith("ppt/embeddings/")]
            slide_text = html.unescape("\n".join(
                zf.read(name).decode("utf-8", "ignore") for name in slides
            ))
    except BadZipFile as exc:
        return GateResult(
            name="render_package_validation",
            status="fail",
            artifacts=[path],
            notes=[f"invalid pptx zip package: {exc}"],
        )

    failed = False
    if len(slides) != EXPECTED_SLIDES:
        notes.append(f"slide count {len(slides)} != {EXPECTED_SLIDES}")
        failed = True
    if len(embeddings) > MAX_NATIVE_EMBEDDINGS:
        notes.append(f"native embeddings {len(embeddings)} > {MAX_NATIVE_EMBEDDINGS}")
        failed = True
    native_tables = slide_text.count("<a:tbl")
    if native_tables < MIN_NATIVE_TABLES:
        notes.append(f"native tables {native_tables} < {MIN_NATIVE_TABLES}")
        failed = True
    for needle in (director, period):
        if needle not in slide_text:
            notes.append(f"missing expected text: {needle}")
            failed = True
    if director == "Jesper Tyrer":
        for needle in (
            "Q1 opened",
            "May 2026",
            "Friday, May 1, 2026",
            "EUR 17.1M",
            "Q1 slips",
            "EUR 9.4M",
            "FY26 renewals",
            "EUR 33.5M",
            "Current state workbook",
            "reconcile",
            "Q1 Land losses",
            "Q2-Q3 risk triage",
            "EUR 4.9M",
            "overdue-close",
            "EUR 10.7M",
            "EUR 5.6M",
            "Commit = EUR 2.7M",
            "zero recent activity",
            "top 7 open deals",
            "top 5 = 89%",
            "Amova Asset Management",
            "3 owners carry 50 pushes",
            "EUR 22.0M",
            "11 open deals pushed",
            "Edwina Chow owns 5",
            "Approved 2026",
            "Coolabah",
            "EUR 3.8M",
            "6 -> 12",
            "EUR 4.6M",
            "1W / 16L",
            "EUR 8.6M lost",
            "unweighted",
            "weighted ARR",
            "unweighted ARR",
        ):
            if needle not in slide_text:
                notes.append(f"missing original-target coverage: {needle}")
                failed = True
    leaked = [needle for needle in FORBIDDEN_TEXT if needle in slide_text]
    if leaked:
        notes.append(f"forbidden placeholder text leaked: {', '.join(leaked)}")
        failed = True
    notes.append(
        f"slides={len(slides)} embeddings={len(embeddings)} tables={native_tables} size={path.stat().st_size}"
    )
    return GateResult(
        name="render_package_validation",
        status="fail" if failed else "pass",
        artifacts=[path],
        notes=notes,
    )


def _report_markdown(
    *,
    director: str,
    period: str,
    dry_run: bool,
    report_only: bool,
    gates: list[GateResult],
) -> str:
    status = "PASS" if all(g.status in {"pass", "skip"} for g in gates) else "FAIL"
    lines = [
        f"# Director LAND Deck Factory Report - {director} {period}",
        "",
        f"- Generated: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- Mode: {'dry-run' if dry_run else 'report-only' if report_only else 'execute'}",
        f"- Overall: {status}",
        "",
        "## Gates",
        "",
        "| Gate | Status | Command | Notes |",
        "|---|---:|---|---|",
    ]
    for gate in gates:
        command = f"`{_cmd_text(gate.command)}`" if gate.command else ""
        notes = "<br>".join(gate.notes) if gate.notes else ""
        lines.append(f"| {gate.name} | {gate.status.upper()} | {command} | {notes} |")

    lines.extend(["", "## Artifacts", ""])
    seen: set[Path] = set()
    for gate in gates:
        for artifact in gate.artifacts:
            if artifact in seen:
                continue
            seen.add(artifact)
            exists = "yes" if artifact.exists() else "no"
            size = artifact.stat().st_size if artifact.exists() and artifact.is_file() else ""
            lines.append(f"- `{artifact}` exists={exists} size={size}")
    lines.append("")
    return "\n".join(lines)


def _write_report(
    *,
    period: str,
    director: str,
    dry_run: bool,
    report_only: bool,
    gates: list[GateResult],
) -> Path:
    report_dir = _factory_dir(period, director)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "publish_gate_report.md"
    report_path.write_text(
        _report_markdown(
            director=director,
            period=period,
            dry_run=dry_run,
            report_only=report_only,
            gates=gates,
        )
    )
    return report_path


def _dry_run_gate(name: str, command: list[str]) -> GateResult:
    return GateResult(name=name, status="skip", command=command, notes=["dry-run: not executed"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--director", default=DEFAULT_DIRECTOR)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--dry-run", action="store_true", help="Print/report the plan; run nothing.")
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Do not run source/deck subprocesses; validate existing artifacts and write report.",
    )
    parser.add_argument("--skip-source", action="store_true", help="Reuse existing source artifacts.")
    parser.add_argument("--skip-deck-build", action="store_true", help="Reuse existing final PPTX.")
    parser.add_argument("--skip-seed", action="store_true", help="Pass --skip-seed to deck builder.")
    args = parser.parse_args()

    factory_dir = _factory_dir(args.period, args.director)
    director_dir = _director_dir(args.period, args.director)
    final_pptx = director_dir / f"{_slug(args.director)}-LAND-{args.period}.pptx"

    source_cmd = [
        _python(),
        "scripts/land_brief.py",
        "--director",
        args.director,
        "--period",
        args.period,
    ]
    workbook_cmd = [
        _python(),
        "scripts/validate_workbook_contract.py",
        str(director_dir),
    ]
    excel_coverage_cmd = [
        _python(),
        "scripts/validate_excel_analysis_coverage.py",
        str(director_dir),
    ]
    connected_factory_build_cmd = [
        _python(),
        "scripts/build_connected_factory_workbook.py",
        "--director",
        args.director,
        "--period",
        args.period,
    ]
    connected_factory_validate_cmd = [
        _python(),
        "scripts/validate_connected_factory_spec.py",
        "--spec",
        str(_connected_factory_spec(args.period, args.director)),
        "--workbook",
        str(_connected_factory_workbook(args.period, args.director)),
    ]
    deck_cmd = [
        _python(),
        "scripts/build_land_presentation_decks.py",
        "--director",
        args.director,
        "--period",
        args.period,
        "--host",
        args.host,
    ]
    if args.skip_seed:
        deck_cmd.append("--skip-seed")
    render_cmd = [
        _python(),
        "scripts/render_deck_for_review.py",
        str(final_pptx),
        "--output-dir",
        str(factory_dir / "render"),
    ]
    powerpoint_open_cmd = [
        _python(),
        "scripts/powerpoint_open_smoke.py",
        str(final_pptx),
        "--host",
        args.host,
    ]
    intel_coverage_cmd = [
        _python(),
        "scripts/audit_jesper_apac_intel_coverage.py",
        str(final_pptx),
        "--json-output",
        str(factory_dir / "jesper_apac_intel_coverage.json"),
        "--markdown-output",
        str(factory_dir / "jesper_apac_intel_coverage.md"),
    ]

    gates: list[GateResult] = []
    if args.dry_run:
        gates.extend(
            [
                _dry_run_gate("source_fact_extraction", source_cmd),
                _dry_run_gate("workbook_contract", workbook_cmd),
                _dry_run_gate("excel_analysis_coverage", excel_coverage_cmd),
                _dry_run_gate("connected_factory_build", connected_factory_build_cmd),
                _dry_run_gate("connected_factory_validate", connected_factory_validate_cmd),
                _dry_run_gate("narrative_spec", []),
                _dry_run_gate("deck_build", deck_cmd),
                _dry_run_gate("render_package_validation", []),
                _dry_run_gate("jesper_apac_intel_coverage", intel_coverage_cmd),
                _dry_run_gate("powerpoint_open_smoke", powerpoint_open_cmd),
                _dry_run_gate("visual_render_smoke", render_cmd),
            ]
        )
    else:
        if args.report_only or args.skip_source:
            gates.append(_source_artifacts_gate(args.period, args.director))
        else:
            gates.append(_run_gate("source_fact_extraction", source_cmd, factory_dir=factory_dir))
            gates.append(_source_artifacts_gate(args.period, args.director))

        if args.report_only:
            gates.append(GateResult("workbook_contract", "skip", workbook_cmd, notes=["report-only"]))
        else:
            gates.append(_run_gate("workbook_contract", workbook_cmd, factory_dir=factory_dir))

        gates.append(_run_gate("excel_analysis_coverage", excel_coverage_cmd, factory_dir=factory_dir))
        gates.append(_run_gate("connected_factory_build", connected_factory_build_cmd, factory_dir=factory_dir))
        gates.append(
            _run_gate(
                "connected_factory_validate",
                connected_factory_validate_cmd,
                factory_dir=factory_dir,
            )
        )
        gates.append(_build_narrative_spec(args.period, args.director, write=not args.report_only))

        if args.report_only or args.skip_deck_build:
            gates.append(GateResult("deck_build", "skip", deck_cmd, notes=["existing deck reused"]))
        else:
            gates.append(_run_gate("deck_build", deck_cmd, factory_dir=factory_dir))
        gates.append(_validate_pptx(final_pptx, director=args.director, period=args.period))
        if args.director == "Jesper Tyrer":
            gates.append(_run_gate("jesper_apac_intel_coverage", intel_coverage_cmd, factory_dir=factory_dir))
        else:
            gates.append(GateResult("jesper_apac_intel_coverage", "skip", intel_coverage_cmd, notes=["Jesper/APAC only"]))
        gates.append(_run_gate("powerpoint_open_smoke", powerpoint_open_cmd, factory_dir=factory_dir))
        gates.append(_run_gate("visual_render_smoke", render_cmd, factory_dir=factory_dir))

    report_path = _write_report(
        period=args.period,
        director=args.director,
        dry_run=args.dry_run,
        report_only=args.report_only,
        gates=gates,
    )
    gates.append(GateResult("publish_gate_report", "pass", artifacts=[report_path]))

    print(f"publish-gate report: {report_path}")
    for gate in gates:
        print(f"{gate.status.upper():>4} {gate.name}")
    return 0 if all(gate.status in {"pass", "skip"} for gate in gates) else 2


if __name__ == "__main__":
    raise SystemExit(main())
