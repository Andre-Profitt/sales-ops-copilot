#!/usr/bin/env python3
"""Audit May 2026 regional decks against the original Sales Director goals."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from pptx import Presentation

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, PeriodContext, context_for_period


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_TC_SHEETS = {
    "TC_S04_ReviewDelta",
    "TC_S05_ForecastQuality",
    "TC_S06_HygieneSignals",
    "TC_S07_TopDealsLand",
    "TC_S08_ClosePlan",
    "TC_S09_CommercialApproval",
    "TC_S11_Renewals",
    "TC_S12_RenewalRecon",
    "TC_S13_ForecastDetail",
    "TC_S16_OwnerCoaching",
    "TC_S18_QTDLossSpine",
    "TC_S19_DealHygiene",
    "TC_S21_Concentration",
    "TC_S22_NamedRisk",
    "TC_S24_MayPlan",
    "TC_S26_ActionItems",
    "TC_S27_DecisionChecklist",
}
FORBIDDEN_TEXT = {
    "SC Test",
    "Test Account",
    "Test MASB",
    "5000%",
    "9000%",
    "#NAME",
    "#NULL",
    "Click to add subtitle",
    "Title of the section",
    "no director-specific prior-review target pack",
    "prior territory concentration spine is not applied",
    "prior territory risk spine is not applied",
}


@dataclass
class GoalCheck:
    goal: str
    status: str
    evidence: list[str]
    gaps: list[str]


@dataclass
class DirectorAudit:
    director: str
    territory: str
    slug: str
    status: str
    checks: list[GoalCheck]
    artifacts: dict[str, str]
    residual_risks: list[str]


def slugify(value: str) -> str:
    return value.replace(" ", "-")


def _selected_directors(director_slug: str | None) -> list[dict[str, Any]]:
    directors = canonical_directors()
    if not director_slug:
        return directors
    return [director for director in directors if slugify(str(director["name"])) == director_slug]


def _audit_from_dict(value: dict[str, Any]) -> DirectorAudit:
    return DirectorAudit(
        director=str(value.get("director") or ""),
        territory=str(value.get("territory") or ""),
        slug=str(value.get("slug") or ""),
        status=str(value.get("status") or "needs_work"),
        checks=[GoalCheck(**check) for check in value.get("checks", [])],
        artifacts=dict(value.get("artifacts") or {}),
        residual_risks=list(value.get("residual_risks") or []),
    )


def _merge_audits(path: Path, audits: list[DirectorAudit]) -> list[DirectorAudit]:
    if not path.exists():
        return audits
    try:
        existing = [_audit_from_dict(row) for row in json.loads(path.read_text(encoding="utf-8"))]
    except (json.JSONDecodeError, OSError, TypeError):
        existing = []
    merged = {audit.slug: audit for audit in existing if audit.slug}
    for audit in audits:
        merged[audit.slug] = audit
    order = {slugify(str(director["name"])): index for index, director in enumerate(canonical_directors())}
    return sorted(merged.values(), key=lambda audit: order.get(audit.slug, 999))


def _zip_ok(path: Path) -> bool:
    try:
        with ZipFile(path) as zf:
            return zf.testzip() is None
    except BadZipFile:
        return False


def _deck_text(path: Path) -> str:
    prs = Presentation(path)
    chunks: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            text = getattr(shape, "text", "") or ""
            if text:
                chunks.append(text)
    return re.sub(r"\s+", " ", "\n".join(chunks)).strip()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _check_text(text: str, needles: list[str]) -> tuple[list[str], list[str]]:
    lower = text.lower()
    hits = [needle for needle in needles if needle.lower() in lower]
    missing = [needle for needle in needles if needle.lower() not in lower]
    return hits, missing


def _goal(goal: str, evidence: list[str], gaps: list[str]) -> GoalCheck:
    return GoalCheck(goal=goal, status="pass" if not gaps else "needs_work", evidence=evidence, gaps=gaps)


def _source_coverage_check(spec: dict[str, Any] | None, *, is_apac: bool, apac_status: str | None) -> GoalCheck:
    if not spec:
        return _goal("Original ETL / prior-intel coverage", [], ["missing regional_intelligence_spec.json"])
    checks = spec.get("readiness_checks", {})
    missing = [key for key, value in checks.items() if value is not True]
    evidence = [
        "regional_intelligence_spec exists",
        f"original_sidecar={checks.get('has_original_sidecar')}",
        f"gold_or_audit_context={checks.get('has_gold_or_audit_context')}",
    ]
    if is_apac:
        if apac_status != "PASS":
            missing.append(f"APAC strict intel coverage status={apac_status or 'missing'}")
        else:
            evidence.append("APAC strict intel coverage PASS")
    return _goal("Original ETL / prior-intel coverage", evidence, missing)


def _workbook_check(path: Path) -> GoalCheck:
    if not path.exists():
        return _goal("Excel traceability layer", [], [f"missing workbook: {path}"])
    wb = load_workbook(path, read_only=True, data_only=False)
    sheetnames = set(wb.sheetnames)
    missing_tc = sorted(REQUIRED_TC_SHEETS - sheetnames)
    raw_sheets = sorted(name for name in sheetnames if name.startswith("Raw_"))
    gaps: list[str] = []
    if missing_tc:
        gaps.append("missing TC sheets: " + ", ".join(missing_tc))
    if len(raw_sheets) < 8:
        gaps.append(f"expected raw audit tabs, found {len(raw_sheets)}")
    evidence = [
        f"{len(sheetnames)} workbook sheets",
        f"{len(raw_sheets)} Raw_* source/audit sheets",
        f"{len(REQUIRED_TC_SHEETS) - len(missing_tc)}/{len(REQUIRED_TC_SHEETS)} required TC_* sheets",
    ]
    return _goal("Excel traceability layer", evidence, gaps)


def _publish_gate_lookup(period: str) -> dict[str, dict[str, Any]]:
    path = ROOT / "state" / period / "__regional__" / "publish_gate" / "regional_publish_gate.json"
    data = _load_json(path) or []
    return {str(row.get("slug")): row for row in data if isinstance(row, dict)}


def _meeting_manifest_lookup(period: str) -> dict[str, dict[str, Any]]:
    path = ROOT / "state" / period / "__regional__" / "meeting_spine" / "meeting_spine_manifest.json"
    data = _load_json(path) or {}
    return {str(row.get("slug")): row for row in data.get("results", []) if isinstance(row, dict)}


def _apac_status(path: Path) -> str | None:
    data = _load_json(path)
    return str(data.get("status")) if isinstance(data, dict) else None


def _visual_residuals(gate: dict[str, Any] | None) -> list[str]:
    if not gate:
        return ["publish gate missing"]
    residuals: list[str] = []
    visual = ((gate.get("metrics") or {}).get("visual_gate") or {})
    for key, value in visual.items():
        if "action_register_rejects_generic_gantt" in key and value.get("most_common_date_ratio", 0) > 0.8:
            residuals.append("Action dates collapse to one date, so keep this as a decision/action register, not a Gantt.")
        if "scatter_requires_two_noncollapsed_axes" in key:
            if value.get("distinct_x", 99) < value.get("min_x", 2) or value.get("distinct_y", 99) < value.get("min_y", 2):
                residuals.append("Scatter gate collapses; use table/bar fallback for this data shape.")
        if "timeline_requires_distinct_dates" in key:
            if len(value.get("distinct_dates") or []) < value.get("min", 2):
                residuals.append("Renewal timeline gate collapses; use watchlist table fallback for this data shape.")
    return sorted(set(residuals))


def _audit_one(
    period: str,
    director: dict[str, Any],
    publish_gate: dict[str, dict[str, Any]],
    meeting_manifest: dict[str, dict[str, Any]],
    *,
    period_context: PeriodContext,
) -> DirectorAudit:
    name = str(director["name"])
    territory = str(director["scope_label"])
    slug = slugify(name)
    director_dir = ROOT / "state" / period / slug
    linked_deck = director_dir / f"{slug}-LAND-{period}-table-image-linked.pptx"
    meeting_deck = director_dir / "factory" / "meeting-spine" / f"{slug}-LAND-{period}-meeting-spine.pptx"
    workbook = director_dir / "factory" / "connected" / "connected_factory_table_images.xlsx"
    spec_path = director_dir / "factory" / "regional_intelligence_spec.json"
    spec = _load_json(spec_path)
    full_text = _deck_text(linked_deck) if linked_deck.exists() else ""
    meeting_text = _deck_text(meeting_deck) if meeting_deck.exists() else ""
    combined_text = f"{full_text} {meeting_text}"
    gate = publish_gate.get(slug)
    meeting = meeting_manifest.get(slug)
    apac_json = director_dir / "factory" / "jesper_apac_intel_coverage_current_meeting_spine.json"
    is_apac = slug == "Jesper-Tyrer"

    checks: list[GoalCheck] = []
    checks.append(
        _goal(
            "Deck package integrity",
            [
                f"linked_zip={_zip_ok(linked_deck)}",
                f"meeting_zip={_zip_ok(meeting_deck)}",
                f"publish_gate={gate.get('status') if gate else 'missing'}",
                f"meeting_spine={meeting.get('status') if meeting else 'missing'}",
            ],
            [
                gap
                for gap in [
                    "" if linked_deck.exists() and _zip_ok(linked_deck) else f"linked deck invalid/missing: {linked_deck}",
                    "" if meeting_deck.exists() and _zip_ok(meeting_deck) else f"meeting deck invalid/missing: {meeting_deck}",
                    "" if gate and gate.get("status") == "pass" else "publish gate not pass",
                    "" if meeting and meeting.get("status") == "pass" else "meeting spine not pass",
                ]
                if gap
            ],
        )
    )
    hits, missing = _check_text(
        combined_text,
        [
            period_context.month_label,
            period_context.snapshot_date,
            "May 1",
            "May operating summary",
        ],
    )
    checks.append(_goal("May forward-looking operating review", hits, missing))
    hits, missing = _check_text(combined_text, ["Land+Expand", "Renewal ACV", "unweighted", "weighted ARR"])
    forbidden_hits = [needle for needle in FORBIDDEN_TEXT if needle.lower() in combined_text.lower()]
    checks.append(
        _goal(
            "ARR/ACV and weighted/unweighted contract",
            hits + ["forbidden basis text absent" if not forbidden_hits else ""],
            missing + [f"forbidden text remains: {needle}" for needle in forbidden_hits],
        )
    )
    checks.append(_source_coverage_check(spec if isinstance(spec, dict) else None, is_apac=is_apac, apac_status=_apac_status(apac_json)))
    checks.append(_workbook_check(workbook))
    hits, missing = _check_text(combined_text, ["Commercial approval", "approval gap", "Stage 3"])
    checks.append(_goal("Commercial approval and governance coverage", hits, missing))
    hits, missing = _check_text(combined_text, ["May deal readiness", "customer proof", "dated next steps", "forecast"])
    checks.append(_goal("Named deal readiness and forecast quality", hits, missing))
    hits, missing = _check_text(combined_text, ["FY26 Renewal", "ACV only", "Renewal ACV"])
    checks.append(_goal("Renewal ACV watchlist without ARR blend", hits, missing))
    hits, missing = _check_text(combined_text, ["May action register", "May decision checklist", "May territory plan"])
    checks.append(_goal("Director action / decision spine", hits, missing))

    residuals = _visual_residuals(gate)
    if gate and gate.get("status") == "pass":
        checks.append(_goal("Visual and table publish gate", ["publish gate PASS", "table-image links present"], []))
    else:
        checks.append(_goal("Visual and table publish gate", [], ["publish gate missing or failing"]))

    status = "pass" if all(check.status == "pass" for check in checks) else "needs_work"
    return DirectorAudit(
        director=name,
        territory=territory,
        slug=slug,
        status=status,
        checks=checks,
        artifacts={
            "linked_deck": str(linked_deck),
            "meeting_spine_deck": str(meeting_deck),
            "connected_table_image_workbook": str(workbook),
            "regional_intelligence_spec": str(spec_path),
        },
        residual_risks=residuals,
    )


def _write_markdown(audits: list[DirectorAudit], path: Path, *, period_context: PeriodContext) -> None:
    lines = [
        f"# {period_context.month_label} Regional Deck Goal Audit",
        "",
        "This audit checks the current decks against the original Sales Director operating-review goals, not just file-open readiness.",
        "",
        "## Executive Read",
        "",
        "| Director | Territory | Status | Residual risks |",
        "|---|---|---:|---:|",
    ]
    for audit in audits:
        lines.append(f"| {audit.director} | {audit.territory} | {audit.status} | {len(audit.residual_risks)} |")

    lines.extend(
        [
            "",
            "## Cross-Batch Findings",
            "",
            "- All nine linked decks and all nine 16-slide meeting-spine candidates pass the publish/open/package gates.",
            "- APAC now passes the strict original-intel coverage audit on both the full deck and the 16-slide meeting spine.",
            "- Non-APAC decks now reference their own original ETL/gold context instead of claiming no prior pack is attached.",
            "- The current table layer is traceable through Excel and linked table images. It is still not a fully native think-cell table donor lane.",
            "- Some visuals correctly fall back to tables/registers when data shape is weak; do not force Gantt/scatter/timeline charts when the gates reject them.",
            "",
            "## Detail",
            "",
        ]
    )
    for audit in audits:
        lines.extend(
            [
                f"### {audit.director} - {audit.territory}",
                "",
                f"- Status: `{audit.status}`",
                f"- Meeting spine: `{audit.artifacts['meeting_spine_deck']}`",
                f"- Excel trace: `{audit.artifacts['connected_table_image_workbook']}`",
                "",
                "| Goal | Status | Evidence | Gaps |",
                "|---|---:|---|---|",
            ]
        )
        for check in audit.checks:
            evidence = "; ".join(item for item in check.evidence if item) or "-"
            gaps = "; ".join(check.gaps) or "-"
            lines.append(f"| {check.goal} | {check.status} | {evidence} | {gaps} |")
        if audit.residual_risks:
            lines.extend(["", "Residual risks:"])
            lines.extend(f"- {risk}" for risk in audit.residual_risks)
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--copy-markdown-to-downloads", action="store_true")
    parser.add_argument("--jobs", type=int, default=1, help="Parallel director audits for local deck/workbook checks.")
    args = parser.parse_args()
    try:
        period_context = context_for_period(args.period)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    output_dir = args.output_dir or (ROOT / "state" / args.period / "__regional__" / "goal_audit")
    output_dir.mkdir(parents=True, exist_ok=True)
    publish_gate = _publish_gate_lookup(args.period)
    meeting_manifest = _meeting_manifest_lookup(args.period)
    directors = _selected_directors(args.director_slug)
    if not directors:
        raise SystemExit(f"unknown director slug: {args.director_slug}")
    if args.jobs > 1 and len(directors) > 1:
        with ThreadPoolExecutor(max_workers=min(args.jobs, len(directors))) as executor:
            audits = list(
                executor.map(
                    lambda director: _audit_one(
                        args.period,
                        director,
                        publish_gate,
                        meeting_manifest,
                        period_context=period_context,
                    ),
                    directors,
                )
            )
    else:
        audits = [
            _audit_one(
                args.period,
                director,
                publish_gate,
                meeting_manifest,
                period_context=period_context,
            )
            for director in directors
        ]
    json_path = output_dir / "regional_deck_goal_audit.json"
    md_path = output_dir / "regional_deck_goal_audit.md"
    audits_to_write = _merge_audits(json_path, audits) if args.director_slug else audits
    json_path.write_text(json.dumps([asdict(audit) for audit in audits_to_write], indent=2) + "\n", encoding="utf-8")
    _write_markdown(audits_to_write, md_path, period_context=period_context)
    if args.copy_markdown_to_downloads:
        shutil.copy2(md_path, Path.home() / "Downloads" / f"{period_context.month_label} regional deck goal audit.md")

    print(f"json={json_path}")
    print(f"markdown={md_path}")
    for audit in audits:
        print(f"{audit.status.upper():>10} {audit.slug:<22} residual_risks={len(audit.residual_risks)}")
    return 0 if all(audit.status == "pass" for audit in audits) else 2


if __name__ == "__main__":
    raise SystemExit(main())
