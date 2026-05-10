"""Audit RW semantic-model and page-filter flow for executive dashboard use."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Literal

from scripts.sales.rw_compose_all_pages import compose_report
from scripts.sales.rw_filter_bar import (
    FILTER_RATIONALE_BY_PAGE,
    FILTER_REFS_BY_PAGE,
    FILTER_TITLES_BY_REF,
    FORBIDDEN_MOTION_SLICER_REF,
    MOTION_SLICER_ALLOWED_PAGES,
    SEMANTIC_FILTER_GAPS,
)
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS
from scripts.sales.rw_push_semantic_model import build_model_bim
from scripts.sales.rw_zebra_schema_architecture import build_zebra_schema_benchmark

Severity = Literal["info", "low", "medium", "high", "critical"]

SEVERITY_RANK: dict[Severity, int] = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

DEFAULT_JSON = Path("output/rw_dashboard_harness/semantic_filter_audit.json")
DEFAULT_MARKDOWN = Path("docs/sales/RW_SEMANTIC_FILTER_ARCHITECTURE.md")


def _single_visual(vc: dict) -> dict:
    try:
        return json.loads(vc.get("config", "{}")).get("singleVisual", {})
    except json.JSONDecodeError:
        return {}


def _visual_type(vc: dict) -> str:
    return str(_single_visual(vc).get("visualType", ""))


def _slicer_refs(section: dict) -> list[str]:
    refs: list[str] = []
    for vc in section.get("visualContainers", []):
        if _visual_type(vc) != "slicer":
            continue
        values = _single_visual(vc).get("projections", {}).get("Values", [])
        if values:
            refs.append(str(values[0].get("queryRef", "")))
    return refs


def _table_columns(model: dict) -> dict[str, set[str]]:
    return {
        table.get("name", ""): {column.get("name", "") for column in table.get("columns", [])}
        for table in model.get("tables", [])
    }


def _relationships(model: dict) -> list[dict]:
    return list(model.get("relationships", []))


def _has_relationship(
    relationships: list[dict],
    *,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> bool:
    return any(
        rel.get("fromTable") == from_table
        and rel.get("fromColumn") == from_column
        and rel.get("toTable") == to_table
        and rel.get("toColumn") == to_column
        for rel in relationships
    )


def _finding(
    *,
    finding_id: str,
    severity: Severity,
    area: str,
    message: str,
    impact: str,
    next_action: str,
    page: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": finding_id,
        "severity": severity,
        "area": area,
        "message": message,
        "impact": impact,
        "next_action": next_action,
    }
    if page:
        payload["page"] = page
    return payload


def _audit_page_filters(report: dict) -> tuple[list[dict], list[dict]]:
    pages = {section.get("displayName"): section for section in report.get("sections", [])}
    findings: list[dict] = []
    policy_rows: list[dict] = []

    for page, expected_refs in FILTER_REFS_BY_PAGE.items():
        section = pages.get(page)
        if section is None:
            findings.append(
                _finding(
                    finding_id="missing_page",
                    severity="high",
                    area="page filters",
                    message=f"{page} is absent from the composed report.",
                    impact="The executive information flow cannot be validated.",
                    next_action="Compose all KPI-targeted pages before publishing.",
                    page=page,
                )
            )
            continue

        actual_refs = frozenset(ref for ref in _slicer_refs(section) if ref)
        policy_rows.append(
            {
                "page": page,
                "motion": PAGE_KPI_CONTRACTS[page].motion if page in PAGE_KPI_CONTRACTS else "explorer",
                "expected_refs": sorted(expected_refs),
                "actual_refs": sorted(actual_refs),
                "rationale": FILTER_RATIONALE_BY_PAGE[page],
            }
        )

        if actual_refs != expected_refs:
            findings.append(
                _finding(
                    finding_id="page_slicer_policy_mismatch",
                    severity="high",
                    area="page filters",
                    message=f"{page} slicers are {sorted(actual_refs)}, expected {sorted(expected_refs)}.",
                    impact="A page-level filter can silently contradict the KPI contract.",
                    next_action="Use scripts.sales.rw_filter_bar.PAGE_FILTERS as the single slicer policy.",
                    page=page,
                )
            )

        if FORBIDDEN_MOTION_SLICER_REF in actual_refs and page not in MOTION_SLICER_ALLOWED_PAGES:
            findings.append(
                _finding(
                    finding_id="motion_slicer_conflicts_with_guardrails",
                    severity="critical",
                    area="page filters",
                    message=f"{page} has a Motion slicer even though its KPI measures enforce motion in DAX.",
                    impact="Executives can select a motion value that ARR/Renewal ACV measures intentionally ignore.",
                    next_action="Remove page-level Motion slicers; show motion as labeled visual columns instead.",
                    page=page,
                )
            )

    return findings, policy_rows


def _audit_model(model: dict) -> tuple[list[dict], dict]:
    columns_by_table = _table_columns(model)
    relationships = _relationships(model)
    findings: list[dict] = []

    if not _has_relationship(
        relationships,
        from_table="f_opportunity",
        from_column="close_date",
        to_table="d_calendar",
        to_column="date",
    ):
        findings.append(
            _finding(
                finding_id="missing_close_date_calendar_relationship",
                severity="critical",
                area="date roles",
                message="f_opportunity.close_date is not related to d_calendar.date.",
                impact="Close FQ slicers would not filter the opportunity cohort.",
                next_action="Restore rel_opp_close_date before publishing.",
            )
        )

    if not _has_relationship(
        relationships,
        from_table="f_opportunity",
        from_column="region",
        to_table="d_region",
        to_column="region",
    ):
        findings.append(
            _finding(
                finding_id="missing_region_relationship",
                severity="critical",
                area="dimensions",
                message="f_opportunity.region is not related to d_region.region.",
                impact="Region slicers would not filter core RW KPI measures.",
                next_action="Restore rel_opp_region before publishing.",
            )
        )

    if "d_stage" not in columns_by_table and "stage_order" not in columns_by_table.get("f_opportunity", set()):
        gap = next(g for g in SEMANTIC_FILTER_GAPS if g["id"] == "stage_dimension")
        findings.append(
            _finding(
                finding_id=gap["id"],
                severity=gap["severity"],  # type: ignore[arg-type]
                area=gap["area"],
                message=gap["finding"],
                impact=gap["impact"],
                next_action=gap["next_action"],
            )
        )

    for fact in ("f_stage_transition", "f_forecast_transition"):
        if not _has_relationship(
            relationships,
            from_table=fact,
            from_column="transition_at",
            to_table="d_calendar",
            to_column="date",
        ):
            gap = next(g for g in SEMANTIC_FILTER_GAPS if g["id"] == "transition_date_role")
            findings.append(
                _finding(
                    finding_id=f"{gap['id']}:{fact}",
                    severity=gap["severity"],  # type: ignore[arg-type]
                    area=gap["area"],
                    message=f"{fact}.transition_at has no direct calendar role.",
                    impact=gap["impact"],
                    next_action=gap["next_action"],
                )
            )

    model_summary = {
        "tables": sorted(columns_by_table),
        "relationships": [
            {
                "name": rel.get("name"),
                "from": f"{rel.get('fromTable')}.{rel.get('fromColumn')}",
                "to": f"{rel.get('toTable')}.{rel.get('toColumn')}",
                "crossFilteringBehavior": rel.get("crossFilteringBehavior"),
                "isActive": rel.get("isActive", True),
            }
            for rel in relationships
        ],
        "stage_model": {
            "has_d_stage": "d_stage" in columns_by_table,
            "f_opportunity_stage_columns": sorted(
                column
                for column in columns_by_table.get("f_opportunity", set())
                if column.startswith("stage")
            ),
            "f_stage_transition_stage_columns": sorted(
                column
                for column in columns_by_table.get("f_stage_transition", set())
                if "stage" in column
            ),
        },
    }
    return findings, model_summary


def audit_semantic_filter_flow(report: dict | None = None, model_bim: dict | None = None) -> dict:
    report = report or compose_report({"sections": []})
    model_bim = model_bim or build_model_bim()
    model = model_bim["model"]
    zebra_benchmark = build_zebra_schema_benchmark()

    page_findings, page_policy = _audit_page_filters(report)
    model_findings, model_summary = _audit_model(model)
    findings = page_findings + model_findings
    counts = {severity: 0 for severity in SEVERITY_RANK}
    for finding in findings:
        counts[finding["severity"]] += 1

    return {
        "schema": "rw-semantic-filter-audit.v1",
        "verdict": "guarded_exec_ready_with_model_debt"
        if counts["critical"] == 0 and counts["high"] == 0
        else "blocked",
        "counts": counts,
        "findings": findings,
        "page_filter_policy": page_policy,
        "model_summary": model_summary,
        "zebra_schema_benchmark": {
            "schema": zebra_benchmark["schema"],
            "summary": zebra_benchmark["summary"],
            "guidance": zebra_benchmark["guidance"],
        },
        "filter_titles": FILTER_TITLES_BY_REF,
    }


def _format_refs(refs: list[str]) -> str:
    return ", ".join(f"`{FILTER_TITLES_BY_REF.get(ref, ref)}`" for ref in refs) or "-"


def write_markdown(result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# RW Semantic Filter Architecture",
        "",
        f"Verdict: `{result['verdict']}`.",
        "",
        "The report is now guarded against the major executive-flow failure: page-level Motion slicers are not allowed. ARR and Renewal ACV measures enforce motion at the DAX layer, so Motion belongs in labeled visual axes, not global page filters.",
        "",
        "## Page Filter Contract",
        "",
        "| Page | Motion contract | Page slicers | Rationale |",
        "| --- | --- | --- | --- |",
    ]
    for row in result["page_filter_policy"]:
        lines.append(
            f"| {row['page']} | `{row['motion']}` | {_format_refs(row['actual_refs'])} | {row['rationale']} |"
        )

    lines += [
        "",
        "## Findings",
        "",
        "| Severity | Area | Finding | Impact | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for finding in result["findings"]:
        page = f"{finding['page']}: " if finding.get("page") else ""
        lines.append(
            f"| `{finding['severity']}` | {finding['area']} | {page}{finding['message']} | {finding['impact']} | {finding['next_action']} |"
        )

    zebra = result["zebra_schema_benchmark"]
    summary = zebra["summary"]
    lines += [
        "",
        "## Zebra Schema Benchmark",
        "",
        "These checks are informed by the Zebra schema corpus, not just local RW preference.",
        "",
        f"- Templates mined: `{summary['template_count']}`",
        f"- Relationships mined: `{summary['total_relationships']}`",
        f"- Single-direction relationships: `{summary['single_direction_relationships']}`",
        f"- Bidirectional relationships: `{summary['bidirectional_relationships']}`",
        f"- Inactive relationships: `{summary['inactive_relationships']}`",
        f"- Templates with role-playing dimensions: `{summary['templates_with_role_playing_dims']}`",
        f"- Templates with ordered dimensions: `{summary['templates_with_ordered_dimensions']}`",
        f"- Templates with scenario columns: `{summary['templates_with_scenario_columns']}`",
        "",
        "| Zebra pattern | Evidence | RW application |",
        "| --- | --- | --- |",
    ]
    for item in zebra["guidance"]:
        lines.append(f"| `{item['pattern']}` | {item['evidence']} | {item['rw_application']} |")

    lines += [
        "",
        "## Relationship Flow",
        "",
        "| Relationship | From | To | Behavior | Active |",
        "| --- | --- | --- | --- | --- |",
    ]
    for rel in result["model_summary"]["relationships"]:
        lines.append(
            f"| `{rel['name']}` | `{rel['from']}` | `{rel['to']}` | `{rel['crossFilteringBehavior']}` | `{rel['isActive']}` |"
        )

    lines += [
        "",
        "## Stage Model",
        "",
        f"- Has `d_stage`: `{result['model_summary']['stage_model']['has_d_stage']}`",
        "- `f_opportunity` stage columns: "
        + ", ".join(f"`{c}`" for c in result["model_summary"]["stage_model"]["f_opportunity_stage_columns"]),
        "- `f_stage_transition` stage columns: "
        + ", ".join(
            f"`{c}`" for c in result["model_summary"]["stage_model"]["f_stage_transition_stage_columns"]
        ),
        "",
        "The next semantic-model upgrade is a canonical `d_stage` table plus explicit transition-date roles. Until then, the report should keep Close FQ labeling and avoid transition-period slicers.",
    ]
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fail-on", choices=tuple(SEVERITY_RANK), default="high")
    args = parser.parse_args()

    result = audit_semantic_filter_flow()
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    write_markdown(result, args.markdown)

    threshold = SEVERITY_RANK[args.fail_on]
    blocking = [f for f in result["findings"] if SEVERITY_RANK[f["severity"]] >= threshold]
    print(
        "semantic-filter-audit: "
        f"verdict={result['verdict']} "
        + " ".join(f"{sev}={result['counts'][sev]}" for sev in SEVERITY_RANK)
    )
    print(f"json={args.json}")
    print(f"markdown={args.markdown}")
    if blocking:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
