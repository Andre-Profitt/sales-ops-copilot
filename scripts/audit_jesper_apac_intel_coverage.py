#!/usr/bin/env python3
"""Audit Jesper/APAC deck coverage against the recovered original APAC intel."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import BadZipFile, ZipFile


A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


@dataclass(frozen=True)
class CoverageRule:
    rule_id: str
    label: str
    needles: tuple[str, ...]


@dataclass
class RuleResult:
    rule_id: str
    label: str
    status: str
    missing: list[str]
    slides: list[int]


COVERAGE_RULES: tuple[CoverageRule, ...] = (
    CoverageRule(
        "scope_and_snapshot",
        "Snapshot scope and ARR/ACV separation",
        (
            "May 2026",
            "Friday, May 1, 2026",
            "2026-04-30",
            "May 1",
            "Land+Expand",
            "Renewal ACV",
        ),
    ),
    CoverageRule(
        "q1_accountability",
        "Original Q1 accountability spine",
        (
            "Q1 opened",
            "EUR 17.1M",
            "Q1 lost",
            "EUR 5.5M",
            "Q1 slips",
            "EUR 9.4M",
        ),
    ),
    CoverageRule(
        "q1_loss_detail",
        "Q1 loss detail and hygiene",
        (
            "Q1 Land losses",
            "Missing reason code",
            "Stage-at-loss mix",
        ),
    ),
    CoverageRule(
        "since_last_review_delta",
        "Original since-last-review delta",
        (
            "6 -> 12",
            "EUR 4.6M",
            "approved-2026 deals moved 1 -> 2",
        ),
    ),
    CoverageRule(
        "forecast_accuracy_lens",
        "Original forecast-accuracy lens",
        (
            "1W / 16L",
            "EUR 8.6M lost",
            "6%",
        ),
    ),
    CoverageRule(
        "original_forecast_mix",
        "Original APAC forecast mix",
        (
            "EUR 5.6M",
            "12 open Pipeline Inspection deals",
            "Commit = EUR 2.7M",
            "48%",
        ),
    ),
    CoverageRule(
        "q2_activity_baseline",
        "Original Q2 activity baseline",
        (
            "6 deals / EUR 5.0M",
            "zero recent activity",
        ),
    ),
    CoverageRule(
        "q2_q3_risk_triage",
        "Original Q2-Q3 risk triage",
        (
            "Q2-Q3 risk triage",
            "EUR 4.9M",
            "Coolabah",
            "Danantara",
            "BOCI",
            "Mandiri",
        ),
    ),
    CoverageRule(
        "concentration_spine",
        "Original concentration spine",
        (
            "top 7 open deals",
            "EUR 9.6M",
            "top 5 = 89%",
            "Amova Asset Management",
        ),
    ),
    CoverageRule(
        "push_discipline",
        "Original push-discipline spine",
        (
            "3 owners carry 50 pushes",
            "EUR 22.0M",
            "11 open deals pushed",
            "Edwina Chow owns 5",
            "2 at 5+ pushes",
            "EUR 1.0M",
            "5 at 3-4 pushes",
            "EUR 3.0M",
        ),
    ),
    CoverageRule(
        "commercial_approval_scope",
        "Commercial approval scope guardrail",
        (
            "Q2 approval gaps",
            "Bank Mandiri",
            "EUR 10.7M",
            "all-open",
        ),
    ),
    CoverageRule(
        "commercial_approval_original_approved",
        "Original commercial approvals",
        (
            "Approved 2026",
            "Coolabah",
            "Danantara",
            "EUR 3.8M",
            "Amova",
            "Pending",
        ),
    ),
    CoverageRule(
        "weighted_unweighted_labels",
        "Weighted and unweighted labeling",
        (
            "unweighted",
            "weighted ARR",
            "unweighted ARR",
            "ACV",
        ),
    ),
    CoverageRule(
        "arr_basis_deckwide_rule",
        "Deckwide ARR basis rule",
        (
            "Land+Expand ARR is unweighted unless explicitly labeled weighted",
            "unweighted ARR",
            "weighted ARR",
        ),
    ),
    CoverageRule(
        "renewal_reconciliation",
        "Renewal ACV reconciliation",
        (
            "FY26 renewals",
            "EUR 33.5M",
            "Current state workbook",
            "reconcile",
        ),
    ),
    CoverageRule(
        "q2_close_guardrails",
        "Q2 close-date guardrails",
        (
            "overdue-close",
            "Krungthai",
            "LTH",
            "August",
        ),
    ),
)


def _slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_slide_text(deck_path: Path) -> list[str]:
    try:
        with ZipFile(deck_path) as zf:
            slide_names = sorted(
                [
                    name
                    for name in zf.namelist()
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ],
                key=_slide_sort_key,
            )
            slides: list[str] = []
            for name in slide_names:
                root = ET.fromstring(zf.read(name))
                text = " ".join(node.text or "" for node in root.iter(A_NS + "t"))
                slides.append(re.sub(r"\s+", " ", html.unescape(text)).strip())
            return slides
    except BadZipFile as exc:
        raise SystemExit(f"invalid pptx zip package: {deck_path}: {exc}") from exc


def _needle_present(text: str, needle: str) -> bool:
    return needle.lower() in text.lower()


def _evaluate_rule(rule: CoverageRule, slides: list[str]) -> RuleResult:
    deck_text = "\n".join(slides)
    missing = [needle for needle in rule.needles if not _needle_present(deck_text, needle)]
    hits: list[int] = []
    for idx, slide_text in enumerate(slides, start=1):
        if any(_needle_present(slide_text, needle) for needle in rule.needles):
            hits.append(idx)
    return RuleResult(
        rule_id=rule.rule_id,
        label=rule.label,
        status="pass" if not missing else "fail",
        missing=missing,
        slides=hits,
    )


def _evaluate_negative_rules(slides: list[str]) -> list[RuleResult]:
    deck_text = "\n".join(slides)
    checks: list[tuple[str, str, tuple[str, ...]]] = [
        (
            "arr_shorthand_removed",
            "ARR shorthand removed",
            (r"\bunwtd\b", r"\bwtd\b", r"ARR\s*\(unwtd\)", r"ARR unwtd"),
        ),
    ]
    results: list[RuleResult] = []
    for rule_id, label, patterns in checks:
        hits: list[int] = []
        matched: list[str] = []
        for idx, slide_text in enumerate(slides, start=1):
            for pattern in patterns:
                if re.search(pattern, slide_text, flags=re.IGNORECASE):
                    hits.append(idx)
                    matched.append(pattern)
        results.append(
            RuleResult(
                rule_id=rule_id,
                label=label,
                status="pass" if not matched else "fail",
                missing=[] if not matched else [f"forbidden pattern: {pattern}" for pattern in sorted(set(matched))],
                slides=sorted(set(hits)),
            )
        )
    return results


def _markdown(deck_path: Path, results: list[RuleResult]) -> str:
    status = "PASS" if all(result.status == "pass" for result in results) else "FAIL"
    lines = [
        f"# Jesper APAC Intel Coverage Audit",
        "",
        f"- Deck: `{deck_path}`",
        f"- Status: {status}",
        "",
        "| Rule | Status | Slides | Missing |",
        "|---|---:|---|---|",
    ]
    for result in results:
        slides = ", ".join(str(slide) for slide in result.slides) or "-"
        missing = ", ".join(result.missing) or ""
        lines.append(f"| {result.label} | {result.status.upper()} | {slides} | {missing} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deck", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    slides = _extract_slide_text(args.deck)
    results = [_evaluate_rule(rule, slides) for rule in COVERAGE_RULES]
    results.extend(_evaluate_negative_rules(slides))
    status = "PASS" if all(result.status == "pass" for result in results) else "FAIL"

    payload = {
        "schema": "jesper-apac-intel-coverage/v1",
        "deck": str(args.deck),
        "status": status,
        "slide_count": len(slides),
        "rules": [asdict(result) for result in results],
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(payload, indent=2))
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(_markdown(args.deck, results))

    print(json.dumps(payload, indent=2))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
