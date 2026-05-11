"""Build a knowledge graph for the RW Power BI report artifact.

The canonical KPI graph explains what RW expects. This module explains what the
Power BI report actually contains: pages, visuals, field bindings, semantic
model objects, KPI placements, and cleanup findings.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.sales.rw_dashboard_harness import (
    DEFAULT_DESKTOP_REPORT,
    decode_config,
    field_refs,
    hash_obj,
    load_report,
    slug,
    visual_summary,
    visual_type,
    write_json,
)
from scripts.sales.rw_kpi_graph import GRAPH
from scripts.sales.rw_page_kpi_contract import PAGE_KPI_CONTRACTS

SCHEMA = "rw-pbi-knowledge-graph.v1"
DEFAULT_OUT_DIR = Path("output") / "rw_dashboard_harness" / "pbi_knowledge_graph"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_PBI_KNOWLEDGE_GRAPH.md"
SEVERITY_ORDER = ("info", "low", "medium", "high", "critical")
SEVERITY_RANK = {severity: idx for idx, severity in enumerate(SEVERITY_ORDER)}
TABLE_COLUMN_RE = re.compile(r"(?:(?:'([^']+)')|([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
MEASURE_REF_RE = re.compile(r"\[([^\]]+)\]")
REPORT_ID = "report:rw-vp-ops"
MODEL_ID = "semantic_model:sm_sales_kpis_rw"
ALLOWED_NON_CONTRACT_PAGES = {"RW KPI Explorer"}


def timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def node_id(kind: str, *parts: str) -> str:
    return f"{kind}:" + "/".join(slug(str(part)) for part in parts if str(part))


def page_id(page: str) -> str:
    return node_id("page", page)


def table_id(table: str) -> str:
    return node_id("table", table)


def measure_id(table: str, measure: str) -> str:
    return node_id("measure", table, measure)


def column_id(table: str, column: str) -> str:
    return node_id("column", table, column)


def kpi_id(kpi: str) -> str:
    return node_id("kpi", kpi)


def finding_id(source: str, raw_id: str, idx: int) -> str:
    return node_id("finding", source, raw_id or str(idx), str(idx))


def _counts_by_severity(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(f.get("severity", "info") for f in findings)
    return {severity: counts.get(severity, 0) for severity in SEVERITY_ORDER}


def _parse_ref(ref: str) -> tuple[str, str, str] | None:
    if len(ref) < 4 or ref[1] != ":" or "." not in ref:
        return None
    ref_kind = ref[0]
    table, name = ref[2:].split(".", 1)
    if ref_kind == "M":
        return "measure", table, name
    if ref_kind == "C":
        return "column", table, name
    return None


def _load_report_for_source(source: str, path: Path | None) -> dict:
    if source == "composed":
        from scripts.sales.rw_compose_all_pages import compose_report

        return compose_report({"sections": []})
    return load_report(source, path)


def _load_model_bim() -> dict:
    from scripts.sales.rw_push_semantic_model import build_model_bim

    return build_model_bim()


def _semantic_indexes(model_bim: dict[str, Any]) -> dict[str, Any]:
    model = model_bim.get("model", {})
    measures: dict[tuple[str, str], dict[str, Any]] = {}
    columns: dict[tuple[str, str], dict[str, Any]] = {}
    measures_by_name: dict[str, list[str]] = defaultdict(list)
    for table in model.get("tables", []):
        table_name = str(table.get("name") or "")
        for column in table.get("columns", []):
            name = str(column.get("name") or "")
            if name:
                columns[(table_name, name)] = column
        for measure in table.get("measures", []):
            name = str(measure.get("name") or "")
            if not name:
                continue
            measures[(table_name, name)] = measure
            measures_by_name[name].append(measure_id(table_name, name))
    return {
        "model": model,
        "measures": measures,
        "columns": columns,
        "measures_by_name": measures_by_name,
    }


def _measure_target_for_name(indexes: dict[str, Any], name: str) -> str:
    matches = indexes["measures_by_name"].get(name, [])
    if matches:
        return matches[0]
    return measure_id("missing_or_unmapped", name)


def _dax_column_refs(expression: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for match in TABLE_COLUMN_RE.finditer(expression):
        table = match.group(1) or match.group(2) or ""
        column = match.group(3) or ""
        refs.append((table, column))
    return refs


def _dax_measure_refs(expression: str) -> list[str]:
    scrubbed = TABLE_COLUMN_RE.sub("", expression)
    return [match.group(1) for match in MEASURE_REF_RE.finditer(scrubbed)]


def _safe_expression(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(str(part) for part in value)
    return str(value or "")


def _normalize_audit_finding(
    *,
    source: str,
    raw: dict[str, Any],
    idx: int,
    kpi_pages: dict[str, list[str]],
) -> dict[str, Any]:
    raw_id = str(raw.get("id") or raw.get("code") or raw.get("finding_id") or "")
    pages = list(raw.get("pages") or [])
    kpi = str(raw.get("kpi_id") or "")
    if not pages and kpi:
        pages = kpi_pages.get(kpi, [])
    page = str(raw.get("page") or (pages[0] if len(pages) == 1 else ""))
    severity = str(raw.get("severity") or "info")
    if severity not in SEVERITY_RANK:
        severity = "info"
    message = str(raw.get("message") or raw.get("finding") or raw.get("id") or raw_id)
    next_action = str(raw.get("next_action") or raw.get("recommendation") or "")
    return {
        "id": finding_id(source, raw_id, idx),
        "source": source,
        "source_id": raw_id,
        "severity": severity,
        "page": page,
        "pages": pages,
        "kpi_id": kpi,
        "lane": raw.get("lane") or raw.get("area") or source,
        "visual_name": raw.get("visual_name", ""),
        "visual_type": raw.get("visual_type", ""),
        "measure": raw.get("measure", ""),
        "message": message,
        "next_action": next_action,
        "evidence": raw.get("evidence", {}),
    }


def collect_graph_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for section in report.get("sections", []):
        page = str(section.get("displayName") or section.get("name") or "")
        if page and page not in PAGE_KPI_CONTRACTS and page not in ALLOWED_NON_CONTRACT_PAGES:
            findings.append(
                {
                    "id": finding_id("pbi_graph", f"uncontracted_page:{page}", len(findings) + 1),
                    "source": "pbi_graph",
                    "source_id": "uncontracted_page",
                    "severity": "medium",
                    "page": page,
                    "pages": [page],
                    "kpi_id": "",
                    "lane": "page contract",
                    "visual_name": "",
                    "visual_type": "",
                    "measure": "",
                    "message": f"{page} is present in the report but not in the RW KPI page contract.",
                    "next_action": "Either add an explicit page contract or remove/keep it as a non-production lab tab.",
                    "evidence": {},
                }
            )
        for visual in section.get("visualContainers", []):
            vt = visual_type(visual)
            if vt.startswith("ZebraBI"):
                name = str(decode_config(visual).get("name") or "")
                findings.append(
                    {
                        "id": finding_id("pbi_graph", f"custom_visual:{page}:{name or vt}", len(findings) + 1),
                        "source": "pbi_graph",
                        "source_id": "custom_visual",
                        "severity": "high",
                        "page": page,
                        "pages": [page],
                        "kpi_id": "",
                        "lane": "Power BI production cleanliness",
                        "visual_name": name,
                        "visual_type": vt,
                        "measure": "",
                        "message": f"{page} contains a Zebra custom visual ({vt}).",
                        "next_action": "Convert this proof visual to native tableEx/IBCS grammar or remove the lab tab before production inspection.",
                        "evidence": {"visual_type": vt},
                    }
                )
    return findings


def collect_cleanup_findings(report: dict[str, Any], model_bim: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from scripts.sales.rw_dashboard_visual_qa import audit_report as audit_visual_quality
    from scripts.sales.rw_data_surface_flow_audit import audit_data_surface_flow
    from scripts.sales.rw_enterprise_standard_audit import audit_enterprise_standard
    from scripts.sales.rw_metric_basis_audit import audit_metric_basis
    from scripts.sales.rw_semantic_filter_audit import audit_semantic_filter_flow
    from scripts.sales.rw_unit_policy import audit_unit_policy

    visual_qa = audit_visual_quality(report)
    metric_basis = audit_metric_basis(report)
    unit_policy = audit_unit_policy(report=report, model_bim=model_bim)
    semantic_filter = audit_semantic_filter_flow(report=report, model_bim=model_bim)
    data_surface = audit_data_surface_flow(report=report, model_bim=model_bim)
    enterprise = audit_enterprise_standard(report=report, model_bim=model_bim)

    kpi_pages = {
        row["kpi_id"]: list(row.get("pages") or [])
        for row in data_surface.get("flow_rows", [])
        if row.get("kpi_id")
    }
    raw_groups = {
        "visual_qa": visual_qa.get("findings", []),
        "metric_basis": metric_basis.get("findings", []),
        "unit_policy": unit_policy.get("findings", []),
        "semantic_filter": semantic_filter.get("findings", []),
        "data_surface": data_surface.get("findings", []),
        "enterprise_standard": enterprise.get("findings", []),
    }
    findings: list[dict[str, Any]] = []
    for source, raw_findings in raw_groups.items():
        for idx, raw in enumerate(raw_findings, start=1):
            findings.append(
                _normalize_audit_finding(
                    source=source,
                    raw=raw,
                    idx=idx,
                    kpi_pages=kpi_pages,
                )
            )

    summaries = {
        "visual_qa": visual_qa.get("summary", {}),
        "metric_basis": metric_basis.get("summary", {}),
        "unit_policy": {
            "counts": unit_policy.get("counts", {}),
            "unit_policy": unit_policy.get("unit_policy", {}),
        },
        "semantic_filter": {
            "counts": semantic_filter.get("counts", {}),
            "verdict": semantic_filter.get("verdict"),
        },
        "data_surface": data_surface.get("summary", {}),
        "enterprise_standard": {
            "verdict": enterprise.get("verdict"),
            "counts": enterprise.get("counts", {}),
            "zebra_native_page_coverage": enterprise.get("zebra_native_page_coverage", []),
            "upgrade_backlog": enterprise.get("upgrade_backlog", []),
        },
    }
    return findings, summaries


def build_pbi_knowledge_graph(
    report: dict[str, Any],
    *,
    model_bim: dict[str, Any] | None = None,
    source: str = "unknown",
    label: str = "rw_pbi_knowledge_graph",
    include_audits: bool = True,
) -> dict[str, Any]:
    model_bim = model_bim or _load_model_bim()
    indexes = _semantic_indexes(model_bim)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    edge_keys: set[str] = set()
    page_visuals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    page_measures: dict[str, set[str]] = defaultdict(set)
    page_columns: dict[str, set[str]] = defaultdict(set)
    page_kpis: dict[str, set[str]] = defaultdict(set)

    def add_node(node_key: str, kind: str, **props: Any) -> None:
        current = nodes.setdefault(node_key, {"id": node_key, "kind": kind})
        for key, value in props.items():
            if value not in (None, "", [], {}):
                current[key] = value

    def add_edge(source_id: str, target_id: str, edge_type: str, **props: Any) -> None:
        key = json.dumps([source_id, target_id, edge_type, props], sort_keys=True, default=str)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({"source": source_id, "target": target_id, "type": edge_type, **props})

    add_node(
        REPORT_ID,
        "report",
        name="RW VP Ops Power BI",
        source=source,
        label=label,
    )
    add_node(MODEL_ID, "semantic_model", name="sm_sales_kpis_rw")
    add_edge(REPORT_ID, MODEL_ID, "USES_SEMANTIC_MODEL")

    model = indexes["model"]
    for table in model.get("tables", []):
        table_name = str(table.get("name") or "")
        if not table_name:
            continue
        tid = table_id(table_name)
        add_node(
            tid,
            "semantic_table",
            name=table_name,
            column_count=len(table.get("columns", [])),
            measure_count=len(table.get("measures", [])),
        )
        add_edge(MODEL_ID, tid, "HAS_TABLE")
        for column in table.get("columns", []):
            column_name = str(column.get("name") or "")
            if not column_name:
                continue
            cid = column_id(table_name, column_name)
            add_node(
                cid,
                "semantic_column",
                table=table_name,
                name=column_name,
                data_type=column.get("dataType", ""),
                format_string=column.get("formatString", ""),
                sort_by_column=column.get("sortByColumn", ""),
                exists_in_model=True,
            )
            add_edge(tid, cid, "HAS_COLUMN")
        for measure in table.get("measures", []):
            measure_name = str(measure.get("name") or "")
            if not measure_name:
                continue
            mid = measure_id(table_name, measure_name)
            expression = _safe_expression(measure.get("expression"))
            add_node(
                mid,
                "semantic_measure",
                table=table_name,
                name=measure_name,
                format_string=measure.get("formatString", ""),
                description=measure.get("description", ""),
                expression_hash=hash_obj(expression),
                exists_in_model=True,
            )
            add_edge(tid, mid, "HAS_MEASURE")
            for dep_measure in _dax_measure_refs(expression):
                target = _measure_target_for_name(indexes, dep_measure)
                add_node(
                    target,
                    "semantic_measure",
                    name=dep_measure,
                    exists_in_model=bool(indexes["measures_by_name"].get(dep_measure)),
                )
                add_edge(mid, target, "DAX_DEPENDS_ON")
            for dep_table, dep_column in _dax_column_refs(expression):
                target = column_id(dep_table, dep_column)
                add_node(
                    target,
                    "semantic_column",
                    table=dep_table,
                    name=dep_column,
                    exists_in_model=(dep_table, dep_column) in indexes["columns"],
                )
                add_edge(mid, target, "DAX_USES_COLUMN")

    for relationship in model.get("relationships", []):
        from_table = str(relationship.get("fromTable") or "")
        from_column = str(relationship.get("fromColumn") or "")
        to_table = str(relationship.get("toTable") or "")
        to_column = str(relationship.get("toColumn") or "")
        if from_table and to_table:
            add_edge(
                table_id(from_table),
                table_id(to_table),
                "RELATES_TO",
                relationship_name=relationship.get("name", ""),
                from_column=from_column,
                to_column=to_column,
                is_active=relationship.get("isActive", True),
                cross_filtering_behavior=relationship.get("crossFilteringBehavior", ""),
            )
        if from_table and from_column and to_table and to_column:
            add_edge(
                column_id(from_table, from_column),
                column_id(to_table, to_column),
                "RELATES_TO",
                relationship_name=relationship.get("name", ""),
            )

    for kpi in GRAPH.kpis:
        kid = kpi_id(kpi.kpi_id)
        add_node(
            kid,
            "rw_kpi",
            kpi_id=kpi.kpi_id,
            name=kpi.name,
            impact=kpi.impact,
            process_area=kpi.process_area,
            target_text=kpi.target_text,
            motion_filter=kpi.motion_filter,
            coverage_status=kpi.coverage_status,
            definition=kpi.definition,
            why_it_matters=kpi.why_it_matters,
        )

    for page_name, contract in PAGE_KPI_CONTRACTS.items():
        pid = page_id(page_name)
        add_node(
            pid,
            "report_page",
            name=page_name,
            executive_question=contract.executive_question,
            job=contract.job,
            motion=contract.motion,
            caveat=contract.caveat,
        )
        for kpi in contract.kpi_ids:
            kid = kpi_id(kpi)
            page_kpis[page_name].add(kpi)
            add_edge(pid, kid, "SERVES_KPI")
        for placement in contract.placements:
            target_measure = _measure_target_for_name(indexes, placement.measure)
            add_node(
                target_measure,
                "semantic_measure",
                name=placement.measure,
                exists_in_model=bool(indexes["measures_by_name"].get(placement.measure)),
            )
            add_edge(
                kpi_id(placement.kpi_id),
                target_measure,
                "SURFACED_AS_MEASURE",
                page=page_name,
                visual_role=placement.visual_role,
                motion_guardrail=placement.motion_guardrail,
                data_status=placement.data_status,
                label=placement.label,
                secondary=placement.secondary,
                missing_measure=placement.missing_measure,
            )
            add_edge(
                pid,
                target_measure,
                "DECLARES_PAGE_MEASURE",
                visual_role=placement.visual_role,
                data_status=placement.data_status,
            )

    for page_index, section in enumerate(report.get("sections", []), start=1):
        page_name = str(section.get("displayName") or section.get("name") or f"Page {page_index}")
        pid = page_id(page_name)
        contract = PAGE_KPI_CONTRACTS.get(page_name)
        add_node(
            pid,
            "report_page",
            name=page_name,
            order=page_index,
            width=section.get("width"),
            height=section.get("height"),
            visual_count=len(section.get("visualContainers", [])),
            executive_question=contract.executive_question if contract else "",
            motion=contract.motion if contract else "",
        )
        add_edge(REPORT_ID, pid, "HAS_PAGE", order=page_index)
        for visual_index, visual in enumerate(section.get("visualContainers", []), start=1):
            summary = visual_summary(page_name, visual)
            vname = str(summary.get("name") or "")
            vid = node_id("visual", page_name, vname or f"{summary.get('type')}_{summary.get('visual_hash')}")
            config = decode_config(visual)
            single_visual = config.get("singleVisual", {})
            objects = single_visual.get("objects", {})
            add_node(
                vid,
                "visual",
                page=page_name,
                name=vname,
                title=summary.get("title", ""),
                visual_type=summary.get("type", ""),
                x=summary.get("x"),
                y=summary.get("y"),
                width=summary.get("width"),
                height=summary.get("height"),
                z=summary.get("z"),
                order=visual_index,
                fields=summary.get("fields", []),
                object_keys=summary.get("object_keys", []),
                has_objects=summary.get("has_objects", False),
                visual_hash=summary.get("visual_hash", ""),
                style_preset=(objects.get("stylePreset") or {}) if isinstance(objects, dict) else {},
            )
            add_edge(pid, vid, "HAS_VISUAL", order=visual_index)
            page_visuals[page_name].append(
                {
                    "id": vid,
                    "name": vname,
                    "title": summary.get("title", ""),
                    "type": summary.get("type", ""),
                    "fields": summary.get("fields", []),
                }
            )
            for ref in field_refs(visual):
                parsed = _parse_ref(ref)
                if parsed is None:
                    continue
                ref_kind, table, field = parsed
                if ref_kind == "measure":
                    target = measure_id(table, field)
                    page_measures[page_name].add(f"{table}.{field}")
                    add_node(
                        target,
                        "semantic_measure",
                        table=table,
                        name=field,
                        exists_in_model=(table, field) in indexes["measures"],
                    )
                    add_edge(vid, target, "USES_MEASURE")
                else:
                    target = column_id(table, field)
                    page_columns[page_name].add(f"{table}.{field}")
                    add_node(
                        target,
                        "semantic_column",
                        table=table,
                        name=field,
                        exists_in_model=(table, field) in indexes["columns"],
                    )
                    add_edge(vid, target, "USES_COLUMN")

    cleanup_findings: list[dict[str, Any]] = collect_graph_findings(report)
    audit_summaries: dict[str, Any] = {}
    if include_audits:
        audit_findings, audit_summaries = collect_cleanup_findings(report, model_bim)
        cleanup_findings.extend(audit_findings)
    for finding in cleanup_findings:
        fid = finding["id"]
        add_node(fid, "cleanup_finding", **finding)
        if finding.get("page"):
            add_edge(fid, page_id(str(finding["page"])), "FINDING_ON_PAGE")
        elif finding.get("kpi_id"):
            add_edge(fid, kpi_id(str(finding["kpi_id"])), "FINDING_ON_KPI")
        else:
            add_edge(fid, REPORT_ID, "FINDING_ON_REPORT")

    visual_type_counts = Counter(
        str(visual.get("type") or visual_type(visual))
        for section in report.get("sections", [])
        for visual in section.get("visualContainers", [])
    )
    used_measure_nodes = {
        edge["target"] for edge in edges if edge["type"] == "USES_MEASURE"
    }
    used_column_nodes = {edge["target"] for edge in edges if edge["type"] == "USES_COLUMN"}
    contracted_kpis = {kpi for contract in PAGE_KPI_CONTRACTS.values() for kpi in contract.kpi_ids}
    cleanup_counts = _counts_by_severity(cleanup_findings)
    page_summaries = []
    findings_by_page: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for finding in cleanup_findings:
        if finding.get("page"):
            findings_by_page[str(finding["page"])].append(finding)
    for section in report.get("sections", []):
        page_name = str(section.get("displayName") or section.get("name") or "")
        contract = PAGE_KPI_CONTRACTS.get(page_name)
        visual_mix = Counter(v["type"] for v in page_visuals.get(page_name, []))
        page_summaries.append(
            {
                "page": page_name,
                "executive_question": contract.executive_question if contract else "",
                "motion": contract.motion if contract else "",
                "visual_count": len(page_visuals.get(page_name, [])),
                "visual_type_counts": dict(sorted(visual_mix.items())),
                "measures_used": sorted(page_measures.get(page_name, set())),
                "columns_used": sorted(page_columns.get(page_name, set())),
                "kpis_served": sorted(page_kpis.get(page_name, set())),
                "cleanup_counts": _counts_by_severity(findings_by_page.get(page_name, [])),
                "cleanup_findings": [
                    {
                        "source": finding["source"],
                        "severity": finding["severity"],
                        "message": finding["message"],
                        "next_action": finding["next_action"],
                    }
                    for finding in findings_by_page.get(page_name, [])
                ],
                "visuals": page_visuals.get(page_name, []),
            }
        )

    summary = {
        "source": source,
        "label": label,
        "generated_at": timestamp(),
        "page_count": len(report.get("sections", [])),
        "visual_count": sum(len(section.get("visualContainers", [])) for section in report.get("sections", [])),
        "visual_type_counts": dict(sorted(visual_type_counts.items())),
        "semantic_table_count": len(model.get("tables", [])),
        "semantic_measure_count": len(indexes["measures"]),
        "semantic_column_count": len(indexes["columns"]),
        "semantic_relationship_count": len(model.get("relationships", [])),
        "used_measure_count": len(used_measure_nodes),
        "used_column_count": len(used_column_nodes),
        "canonical_kpi_count": len(GRAPH.kpis),
        "contracted_kpi_count": len(contracted_kpis),
        "cleanup_finding_count": len(cleanup_findings),
        "cleanup_counts": cleanup_counts,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "verdict": _verdict(cleanup_counts),
    }

    return {
        "schema": SCHEMA,
        "summary": summary,
        "nodes": sorted(nodes.values(), key=lambda node: (node["kind"], node["id"])),
        "edges": sorted(edges, key=lambda edge: (edge["source"], edge["type"], edge["target"])),
        "page_summaries": page_summaries,
        "audit_summaries": audit_summaries,
        "cleanup_findings": sorted(
            cleanup_findings,
            key=lambda item: (
                -SEVERITY_RANK.get(item.get("severity", "info"), 0),
                item.get("page") or "",
                item.get("source") or "",
                item.get("source_id") or "",
            ),
        ),
    }


def _verdict(cleanup_counts: dict[str, int]) -> str:
    if cleanup_counts["critical"]:
        return "blocked"
    if cleanup_counts["high"]:
        return "needs_source_or_model_work"
    if cleanup_counts["medium"]:
        return "lab_ready_with_cleanup_debt"
    return "clean"


def render_markdown(graph: dict[str, Any], json_path: Path | None = None) -> str:
    summary = graph["summary"]
    audit_summaries = graph.get("audit_summaries", {})
    enterprise = audit_summaries.get("enterprise_standard", {})
    lines = [
        "# RW Power BI Knowledge Graph",
        "",
        f"Generated: `{summary['generated_at']}`",
        f"Source: `{summary['source']}`",
        f"Verdict: `{summary['verdict']}`",
        "",
        "This graph connects the actual Power BI report artifact to the RW KPI contract, semantic model, visual bindings, and cleanup gates. It is the current map of what each tab does and what still needs tightening.",
        "",
        "## Executive Read",
        "",
        f"- Pages: `{summary['page_count']}`",
        f"- Visuals: `{summary['visual_count']}` ({', '.join(f'{k}={v}' for k, v in summary['visual_type_counts'].items())})",
        f"- Semantic model: `{summary['semantic_table_count']}` tables, `{summary['semantic_measure_count']}` measures, `{summary['semantic_relationship_count']}` relationships",
        f"- Used on BI surface: `{summary['used_measure_count']}` measures, `{summary['used_column_count']}` columns",
        f"- RW KPI contract: `{summary['contracted_kpi_count']}` KPIs placed from `{summary['canonical_kpi_count']}` canonical RW KPIs",
        f"- Cleanup findings: `{summary['cleanup_finding_count']}` ({', '.join(f'{k}={v}' for k, v in summary['cleanup_counts'].items())})",
        f"- Graph size: `{summary['node_count']}` nodes, `{summary['edge_count']}` edges",
    ]
    if json_path:
        lines.append(f"- Machine graph: `{json_path}`")

    if enterprise:
        lines += [
            "",
            "## Enterprise Standard Snapshot",
            "",
            f"- Enterprise verdict: `{enterprise.get('verdict', 'n/a')}`",
            f"- Enterprise counts: `{enterprise.get('counts', {})}`",
        ]
        coverage_rows = enterprise.get("zebra_native_page_coverage") or []
        if coverage_rows:
            lines += [
                "",
                "| Page | Decision visuals | Zebra-native | Coverage |",
                "| --- | ---: | ---: | ---: |",
            ]
            for row in coverage_rows:
                lines.append(
                    f"| {row['page']} | {row['decision_visuals']} | {row['zebra_native_visuals']} | {row['zebra_native_coverage']:.0%} |"
                )

    lines += [
        "",
        "## Tab Map",
        "",
        "| Tab | Executive question | Visuals | Measures | KPIs | Cleanup |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for page in graph["page_summaries"]:
        cleanup = page["cleanup_counts"]
        cleanup_text = ", ".join(f"{k}={v}" for k, v in cleanup.items() if v) or "clear"
        lines.append(
            f"| {page['page']} | {page['executive_question'] or '-'} | {page['visual_count']} | "
            f"{len(page['measures_used'])} | {len(page['kpis_served'])} | {cleanup_text} |"
        )

    lines += [
        "",
        "## Per-Tab Graph",
        "",
    ]
    for page in graph["page_summaries"]:
        lines += [
            f"### {page['page']}",
            "",
            f"- Question: {page['executive_question'] or 'Not contracted.'}",
            f"- Motion basis: `{page['motion'] or 'n/a'}`",
            f"- Visual mix: `{page['visual_type_counts']}`",
            f"- KPIs served: {', '.join(f'`{kpi}`' for kpi in page['kpis_served']) or '-'}",
            f"- Measures used: {', '.join(f'`{measure}`' for measure in page['measures_used'][:16]) or '-'}",
        ]
        if len(page["measures_used"]) > 16:
            lines.append(f"- Additional measures: `{len(page['measures_used']) - 16}`")
        decision_visuals = [
            visual
            for visual in page["visuals"]
            if visual["type"] not in {"textbox", "basicShape", "slicer"}
        ][:8]
        if decision_visuals:
            lines += ["", "| Visual | Type | Fields |", "| --- | --- | --- |"]
            for visual in decision_visuals:
                label = visual["title"] or visual["name"] or visual["id"]
                fields = ", ".join(f"`{field}`" for field in visual["fields"][:8])
                lines.append(f"| {label} | `{visual['type']}` | {fields or '-'} |")
        if page["cleanup_findings"]:
            lines += ["", "| Severity | Source | Finding | Next action |", "| --- | --- | --- | --- |"]
            for finding in page["cleanup_findings"][:8]:
                lines.append(
                    f"| `{finding['severity']}` | `{finding['source']}` | {finding['message']} | {finding['next_action'] or '-'} |"
                )
        else:
            lines.append("- Cleanup: clear at current graph gates.")
        lines.append("")

    report_findings = [finding for finding in graph["cleanup_findings"] if not finding.get("page")]
    lines += [
        "## Cross-Report Cleanup Queue",
        "",
        "| Severity | Source | Lane/KPI | Finding | Next action |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not report_findings:
        lines.append("| `info` | all | - | No report-level findings. | Keep graph gate in the build path. |")
    for finding in report_findings[:30]:
        lane = finding.get("kpi_id") or finding.get("lane") or "-"
        lines.append(
            f"| `{finding['severity']}` | `{finding['source']}` | `{lane}` | {finding['message']} | {finding['next_action'] or '-'} |"
        )

    backlog = enterprise.get("upgrade_backlog") or []
    if backlog:
        lines += [
            "",
            "## Upgrade Backlog",
            "",
            "| # | Lane | Work | Why |",
            "| ---: | --- | --- | --- |",
        ]
        for item in backlog:
            lines.append(f"| {item['sequence']} | {item['lane']} | {item['work']} | {item['why']} |")

    lines += [
        "",
        "## Guardrails",
        "",
        "- ARR means Land + Expand only.",
        "- Renewal ACV means Renewal only.",
        "- Production report pages do not use a top-level blended ARR+ACV value; Land/Expand ARR and Renewal ACV stay as separate measures.",
        "- Monetary visuals stay on `EUR M`; K/MM/BMM/$ visual labels or display-unit overrides are blocked.",
        "- Proxy KPIs are tracked as debt, not counted as clean executive metrics.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(graph: dict[str, Any], *, out_dir: Path, markdown_path: Path, label: str) -> tuple[Path, Path]:
    json_path = out_dir / f"{slug(label)}.pbi_knowledge_graph.json"
    write_json(json_path, graph)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(graph, json_path=json_path), encoding="utf-8")
    return json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build an RW Power BI knowledge graph.")
    parser.add_argument("--source", choices=("composed", "live", "desktop", "path"), default="composed")
    parser.add_argument("--path", type=Path, help="report.json path when --source path")
    parser.add_argument("--label", default="rw_pbi_knowledge_graph")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--skip-audits", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.source == "path" and not args.path:
        raise SystemExit("--path is required when --source path")
    if args.source == "desktop" and args.path is None:
        args.path = DEFAULT_DESKTOP_REPORT
    report = _load_report_for_source(args.source, args.path)
    graph = build_pbi_knowledge_graph(
        report,
        source=args.source,
        label=args.label,
        include_audits=not args.skip_audits,
    )
    json_path, markdown_path = write_outputs(
        graph,
        out_dir=args.out_dir,
        markdown_path=args.markdown,
        label=args.label,
    )
    counts = graph["summary"]["cleanup_counts"]
    print(f"pbi knowledge graph json: {json_path}")
    print(f"pbi knowledge graph markdown: {markdown_path}")
    print(
        f"verdict={graph['summary']['verdict']} "
        f"nodes={graph['summary']['node_count']} edges={graph['summary']['edge_count']} "
        + " ".join(f"{severity}={counts[severity]}" for severity in SEVERITY_ORDER)
    )


if __name__ == "__main__":
    main()
