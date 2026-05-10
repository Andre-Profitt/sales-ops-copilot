"""RW KPI expected-vs-BI coverage checklist.

This is the readable checklist layer over the KPI intelligence matrix.  It
answers the operating question: for each KPI RW expects, do we have a trusted
Power BI surface, a partial/proxy surface, or a data/model blocker?
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from scripts.sales.rw_dashboard_intelligence import (
    KPIIntelligenceRow,
    build_intelligence_rows,
)
from scripts.sales.rw_kpi_graph import GRAPH, SalesKPI


DEFAULT_MARKDOWN = Path("docs/sales/RW_KPI_COVERAGE_CHECKLIST.md")
DEFAULT_JSON = (
    Path("output")
    / "rw_dashboard_harness"
    / "kpi_coverage"
    / "rw_kpi_coverage.kpi_coverage.json"
)


COVERAGE_LABELS = {
    "surfaced": "Covered",
    "surfaced_partial": "Partial/proxy on BI",
    "model_available_not_surfaced": "Not surfaced",
    "partial_data_or_measure_gap": "Model/measure gap",
    "source_data_gap": "Source-data gap",
}

COVERAGE_BUCKETS = {
    "surfaced": "covered",
    "surfaced_partial": "partial_proxy",
    "model_available_not_surfaced": "not_surfaced",
    "partial_data_or_measure_gap": "model_measure_gap",
    "source_data_gap": "source_data_gap",
}

CHECK_MARKS = {
    "covered": "[x]",
    "partial_proxy": "[~]",
    "not_surfaced": "[ ]",
    "model_measure_gap": "[ ]",
    "source_data_gap": "[ ]",
}


@dataclass(frozen=True)
class KPICoverageChecklistRow:
    check: str
    coverage_bucket: str
    kpi_id: str
    rw_expected: str
    process_area: str
    target: str
    impact: str
    motion_filter: str
    source_coverage: str
    dashboard_status: str
    bi_coverage: str
    pages: tuple[str, ...]
    present_measures: tuple[str, ...]
    missing_measures: tuple[str, ...]
    next_action: str


def _kpi_index() -> dict[str, SalesKPI]:
    return {kpi.kpi_id: kpi for kpi in GRAPH.kpis}


def _coverage_bucket(row: KPIIntelligenceRow) -> str:
    return COVERAGE_BUCKETS[row.dashboard_status]


def _check_mark(row: KPIIntelligenceRow) -> str:
    return CHECK_MARKS[_coverage_bucket(row)]


def _rw_expected(kpi: SalesKPI) -> str:
    return f"{kpi.name}; target {kpi.target_text}"


def build_rows() -> tuple[KPICoverageChecklistRow, ...]:
    kpis = _kpi_index()
    rows: list[KPICoverageChecklistRow] = []
    for intelligence in build_intelligence_rows():
        kpi = kpis[intelligence.kpi_id]
        bucket = _coverage_bucket(intelligence)
        rows.append(
            KPICoverageChecklistRow(
                check=_check_mark(intelligence),
                coverage_bucket=bucket,
                kpi_id=intelligence.kpi_id,
                rw_expected=_rw_expected(kpi),
                process_area=kpi.process_area,
                target=kpi.target_text,
                impact=intelligence.impact,
                motion_filter=intelligence.motion_filter,
                source_coverage=intelligence.source_coverage,
                dashboard_status=intelligence.dashboard_status,
                bi_coverage=COVERAGE_LABELS[intelligence.dashboard_status],
                pages=intelligence.pages,
                present_measures=intelligence.model_measures,
                missing_measures=intelligence.missing_measures,
                next_action=intelligence.next_action,
            )
        )
    return tuple(rows)


def coverage_summary(rows: tuple[KPICoverageChecklistRow, ...]) -> dict[str, Any]:
    counts = {
        "total_kpis": len(rows),
        "covered": 0,
        "partial_proxy": 0,
        "not_surfaced": 0,
        "model_measure_gap": 0,
        "source_data_gap": 0,
    }
    for row in rows:
        counts[row.coverage_bucket] += 1
    usable = counts["covered"] + counts["partial_proxy"]
    blocked = counts["not_surfaced"] + counts["model_measure_gap"] + counts["source_data_gap"]
    counts["usable_on_bi_including_proxy"] = usable
    counts["not_dependable_yet"] = blocked
    counts["clean_coverage_pct"] = round(counts["covered"] / len(rows), 3) if rows else 0
    counts["usable_coverage_pct"] = round(usable / len(rows), 3) if rows else 0
    return counts


def build_checklist() -> dict[str, Any]:
    rows = build_rows()
    high_impact_gaps = [
        asdict(row)
        for row in rows
        if row.impact == "HIGH" and row.coverage_bucket != "covered"
    ]
    return {
        "schema": "rw-kpi-coverage-checklist.v1",
        "guardrail": (
            "ARR is Land + Expand only; Renewal ACV is Renewal only. "
            "Total Open Pipeline Value is the only explicitly labeled cross-motion value."
        ),
        "summary": coverage_summary(rows),
        "rows": [asdict(row) for row in rows],
        "high_impact_gaps": high_impact_gaps,
    }


def _md_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text


def _join(values: tuple[str, ...] | list[str]) -> str:
    return ", ".join(values) if values else "-"


def _measure_evidence(row: dict[str, Any]) -> str:
    present = _join(row["present_measures"])
    if not row["missing_measures"]:
        return present
    missing = f"missing: {_join(row['missing_measures'])}"
    return f"{present}; {missing}" if present != "-" else missing


def _append_gap_queue(lines: list[str], title: str, rows: list[dict[str, Any]]) -> None:
    lines += ["", f"## {title}", ""]
    if not rows:
        lines.append("- None.")
        return
    for row in rows:
        lines.append(
            f"- `{row['kpi_id']}` ({row['impact']}, {row['motion_filter']}): "
            f"{row['next_action']}"
        )


def to_markdown(checklist: dict[str, Any]) -> str:
    summary = checklist["summary"]
    rows = checklist["rows"]
    high_impact_gaps = checklist["high_impact_gaps"]
    lines = [
        "# RW KPI Coverage Checklist",
        "",
        "Generated from `scripts/sales/rw_kpi_graph.py`, `rw_dashboard_intelligence.py`, and the executable page KPI contract.",
        "",
        "## Coverage Answer",
        "",
        f"- RW expected KPIs: {summary['total_kpis']}",
        f"- Cleanly covered on BI: {summary['covered']} / {summary['total_kpis']}",
        (
            "- Usable on BI including partial/proxy coverage: "
            f"{summary['usable_on_bi_including_proxy']} / {summary['total_kpis']}"
        ),
        f"- Not dependable yet: {summary['not_dependable_yet']} / {summary['total_kpis']}",
        f"- Model/measure gaps: {summary['model_measure_gap']}",
        f"- Source-data gaps: {summary['source_data_gap']}",
        "",
        f"Cardinal guardrail: {checklist['guardrail']}",
        "",
        "Checklist legend: `[x]` covered, `[~]` partial/proxy on BI, `[ ]` not dependable yet.",
        "",
        "## Master Checklist",
        "",
        "| Check | KPI | RW expects | Impact | Motion | BI coverage | Pages | Measure evidence | Gap / next action |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    row["check"],
                    f"`{row['kpi_id']}`",
                    _md_cell(row["rw_expected"]),
                    row["impact"],
                    row["motion_filter"],
                    row["bi_coverage"],
                    _md_cell(_join(row["pages"])),
                    _md_cell(_measure_evidence(row)),
                    _md_cell(row["next_action"]),
                ]
            )
            + " |"
        )

    _append_gap_queue(lines, "High-Impact Gap Queue", high_impact_gaps)
    _append_gap_queue(
        lines,
        "Partial/Proxy BI Coverage",
        [row for row in rows if row["coverage_bucket"] == "partial_proxy"],
    )
    _append_gap_queue(
        lines,
        "Model/Measure Gaps",
        [row for row in rows if row["coverage_bucket"] == "model_measure_gap"],
    )
    _append_gap_queue(
        lines,
        "Source-Data Gaps",
        [row for row in rows if row["coverage_bucket"] == "source_data_gap"],
    )
    return "\n".join(lines) + "\n"


def write_outputs(
    markdown_path: Path = DEFAULT_MARKDOWN,
    json_path: Path = DEFAULT_JSON,
    checklist: dict[str, Any] | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    result = checklist or build_checklist()
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(to_markdown(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return markdown_path, json_path, result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    markdown_path, json_path, result = write_outputs(args.markdown, args.json)
    print(f"kpi coverage markdown: {markdown_path}")
    print(f"kpi coverage json: {json_path}")
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
