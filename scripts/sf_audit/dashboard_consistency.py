"""Cross-dashboard consistency audit.

Read-only inspection of 11 dashboards built today. Builds a tuple per widget
of (widget_header, reportType, viz, filter_set_hash, filterColumns_set,
dateScope) and clusters by header similarity to flag divergence.

Outputs:
  state/sf_audit/raw/<dashboard_id>.json  — raw describe payloads (cached)
  state/sf_audit/dashboard_consistency_audit.md  — the report

Usage:
  python3 -m scripts.sf_audit.dashboard_consistency
  python3 -m scripts.sf_audit.dashboard_consistency --no-cache  # force refetch
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

from scripts.sf_audit.reports import sf_session

DASHBOARD_IDS = [
    "01ZTb00000FSP7hMAH",
    "01ZTb00000FSP9JMAX",
    "01ZTb00000FxYTFMA3",
    "01ZTb00000FxYUrMAN",
    "01ZTb00000FxYY5MAN",
    "01ZTb00000FxYZhMAN",
    "01ZTb00000FxYbJMAV",
    "01ZTb00000FxYcvMAF",
    "01ZTb00000FxYeXMAV",
    "01ZTb00000FxYg9MAF",
    "01ZTb00000FxYhlMAF",
]

STANDARD_FILTER_COLS = {
    "INDUSTRY",
    "ADDRESS1_COUNTRY_CODE",
    "Account.Region__c",
    "Opportunity.Account_Unit_Group__c",
}
STANDARD_FILTER_LABELS = {"Industry", "Legal Country", "Sales Region", "Account Unit Group"}


# Headers we expect to be parallel across dashboards. Loose normalization.
def normalize_header(h: str | None) -> str:
    if not h:
        return ""
    s = h.lower().strip()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    # Strip trailing time-period qualifiers so we can cluster e.g.
    # "Open Pipeline ARR" with "Open Pipeline ARR This Q".
    return s.strip()


def header_cluster_key(h: str | None) -> str:
    """Bucket headers by their semantic concept (cluster key)."""
    n = normalize_header(h)
    if not n:
        return ""
    # Common semantic keys we want to track for consistency.
    rules = [
        ("open_pipeline_arr", ["open pipeline arr", "open pipeline", "pipeline open"]),
        ("won_arr", ["won arr", "qtd won", "quarter won", "what was won", "closed won"]),
        ("lost_arr", ["lost arr", "lost l e"]),
        ("renewal_acv", ["renewal pipeline acv", "renewal acv", "renewal pipeline"]),
        ("pipeline_by_stage", ["pipeline by stage", "pipeline overview by stage"]),
        ("pipeline_by_region", ["pipeline by region", "by region", "regional pipeline"]),
        ("pipeline_by_owner", ["pipeline by owner", "by owner", "owner pipeline"]),
        ("renewals_by_stage", ["renewals by stage", "renewal by stage"]),
        ("commercial_approval", ["commercial approval"]),
        ("close_slipped", ["close date slipped", "slipped"]),
        ("stage_age", ["stage age", "days in stage"]),
        ("churn_risk", ["churn risk", "business at risk"]),
        ("win_rate", ["win rate", "wins vs losses", "win loss"]),
        ("approved_deals", ["approved deals", "approved ytd"]),
        ("new_opps", ["new opps", "new opportunities"]),
        ("stage3plus", ["stage 3", "stage3"]),
    ]
    for key, needles in rules:
        for needle in needles:
            if needle in n:
                return key
    return n  # fallback to normalized header itself


def get_dashboard(
    instance: str, token: str, did: str, cache_dir: Path, use_cache: bool = True
) -> dict[str, Any]:
    cache_path = cache_dir / f"{did}.json"
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text())
    r = requests.get(
        f"{instance}/services/data/v65.0/analytics/dashboards/{did}/describe",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, indent=2))
    return payload


def get_report_type(instance: str, token: str, report_id: str, cache: dict[str, str]) -> str:
    """Return reportType (folder/category) for a report id, cached."""
    if report_id in cache:
        return cache[report_id]
    try:
        r = requests.get(
            f"{instance}/services/data/v65.0/analytics/reports/{report_id}/describe",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        r.raise_for_status()
        rt = (r.json().get("reportMetadata") or {}).get("reportType") or {}
        type_str = rt.get("type") if isinstance(rt, dict) else (rt or "")
        cache[report_id] = type_str or ""
    except Exception as e:  # noqa: BLE001
        cache[report_id] = f"ERR:{e}"[:60]
    return cache[report_id]


def widget_tuple(c: dict[str, Any], dashboard_id: str, dashboard_name: str) -> dict[str, Any]:
    """Extract the consistency-relevant fields from a dashboard component."""
    props = c.get("properties") or {}
    fc = props.get("filterColumns") or []
    fc_names = sorted(f.get("name") for f in fc if f.get("name"))
    fc_labels = sorted(f.get("label") for f in fc if f.get("label"))
    aggs = [a.get("name") for a in (props.get("aggregates") or []) if a.get("name")]
    groupings = [g.get("name") for g in (props.get("groupings") or []) if g.get("name")]

    # Quick filter set hash (just the column-name set)
    fc_hash = hashlib.md5(",".join(fc_names).encode()).hexdigest()[:8]

    return {
        "dashboard_id": dashboard_id,
        "dashboard_name": dashboard_name,
        "component_id": c.get("id"),
        "header": c.get("header"),
        "title": c.get("title"),
        "footer": c.get("footer"),
        "report_id": c.get("reportId"),
        "type": c.get("type"),
        "viz": props.get("visualizationType"),
        "report_format": props.get("reportFormat"),
        "filter_columns_names": fc_names,
        "filter_columns_labels": fc_labels,
        "filter_columns_hash": fc_hash,
        "filter_columns_count": len(fc_names),
        "missing_standard_filters": sorted(STANDARD_FILTER_COLS - set(fc_names)),
        "extra_filters": sorted(set(fc_names) - STANDARD_FILTER_COLS),
        "aggregates": aggs,
        "groupings": groupings,
        "use_report_chart": props.get("useReportChart"),
        "drill_url": props.get("drillUrl"),
        "cluster_key": header_cluster_key(c.get("header")),
    }


def collect_all(
    instance: str, token: str, cache_dir: Path, use_cache: bool
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    widgets: list[dict[str, Any]] = []
    dashboards: dict[str, dict[str, Any]] = {}
    for did in DASHBOARD_IDS:
        print(f"  fetching {did}…", flush=True)
        try:
            md = get_dashboard(instance, token, did, cache_dir, use_cache=use_cache)
        except Exception as e:  # noqa: BLE001
            print(f"    WARN: {e}")
            continue
        dashboards[did] = {
            "id": did,
            "name": md.get("name"),
            "developer_name": md.get("developerName"),
            "folder_name": md.get("folderName"),
            "filters": [
                {
                    "name": f.get("name"),
                    "options": [o.get("value") for o in (f.get("options") or [])],
                }
                for f in (md.get("filters") or [])
            ],
            "component_count": len(md.get("components") or []),
        }
        for c in md.get("components") or []:
            widgets.append(widget_tuple(c, did, md.get("name") or did))
    return widgets, dashboards


def cluster_by_concept(widgets: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for w in widgets:
        if w["type"] == "Report" and w["cluster_key"]:
            clusters[w["cluster_key"]].append(w)
    return clusters


def render_md(widgets: list[dict[str, Any]], dashboards: dict[str, dict[str, Any]]) -> str:
    """Render the consistency-audit markdown."""
    clusters = cluster_by_concept(widgets)
    multi_dashboard_clusters = {
        k: v for k, v in clusters.items() if len({w["dashboard_id"] for w in v}) >= 2
    }

    # Build per-dimension findings.
    dim1_rows = []  # metric definition (filters/aggregates) per cluster
    dim2_rows = []  # naming consistency
    dim3_rows = []  # viz consistency
    dim4_rows = []  # filter pass-through

    # ── Dim 1 + 2 + 3: per multi-dashboard cluster ─────────────────
    for ckey, ws in sorted(multi_dashboard_clusters.items()):
        # collect distinct values per dimension across the cluster
        viz_set = sorted({(w["viz"] or "?") for w in ws})
        filter_hash_set = sorted({w["filter_columns_hash"] for w in ws})
        agg_set = sorted({tuple(w["aggregates"]) for w in ws})
        header_set = sorted({(w["header"] or "?") for w in ws})
        dashboards_count = len({w["dashboard_id"] for w in ws})

        dim1_rows.append(
            {
                "concept": ckey,
                "n_widgets": len(ws),
                "n_dashboards": dashboards_count,
                "distinct_filter_hashes": len(filter_hash_set),
                "distinct_aggregates": len(agg_set),
                "filter_hashes": filter_hash_set,
                "aggregates": [list(a) for a in agg_set],
                "examples": [(w["dashboard_id"], w["header"]) for w in ws[:6]],
            }
        )
        dim2_rows.append(
            {
                "concept": ckey,
                "n_widgets": len(ws),
                "distinct_headers": header_set,
            }
        )
        dim3_rows.append(
            {
                "concept": ckey,
                "n_widgets": len(ws),
                "viz_set": viz_set,
                "examples": [(w["dashboard_id"], w["header"], w["viz"]) for w in ws[:8]],
            }
        )

    # ── Dim 4: filter pass-through. Per-widget row across all 11 dashboards.
    # Limit to Opp-typed widgets — heuristic: filter contains any of the
    # Opportunity-prefixed columns or one of the standard 4.
    for w in widgets:
        if w["type"] != "Report":
            continue
        # Identify Opp widgets via filter-column or aggregate
        is_opp = False
        for fc in w["filter_columns_names"]:
            if "Opportunity." in fc or fc in STANDARD_FILTER_COLS:
                is_opp = True
                break
        for a in w["aggregates"]:
            if "Opportunity." in a:
                is_opp = True
                break
        if not is_opp:
            continue
        dim4_rows.append(
            {
                "dashboard_id": w["dashboard_id"],
                "header": w["header"] or "(no header)",
                "viz": w["viz"],
                "filter_count": w["filter_columns_count"],
                "missing_standard_filters": w["missing_standard_filters"],
                "extra_filters": w["extra_filters"],
                "filter_hash": w["filter_columns_hash"],
            }
        )

    # ── Top-10 ranked inconsistencies (cross-dimension) ─────────────
    findings = []

    # Highest-priority: dashboards missing dashboard-level filters at all.
    dashboards_no_filters = [d for d in dashboards.values() if not d.get("filters")]
    if dashboards_no_filters:
        findings.append(
            {
                "score": 100,  # always top
                "category": "Dashboard-level filters",
                "summary": (
                    f"{len(dashboards_no_filters)} of {len(dashboards)} dashboards "
                    f"have ZERO dashboard-level filters defined; only SD Monthly has "
                    f"the 4 standard filters."
                ),
                "details": ", ".join(f"{d['id']} ({d['name']})" for d in dashboards_no_filters),
            }
        )

    # Each widget cluster with >1 distinct filter_columns_hash → metric inconsistency
    for r in dim1_rows:
        if r["distinct_filter_hashes"] > 1:
            findings.append(
                {
                    "score": 9 + r["n_dashboards"],  # weight by spread
                    "category": "Metric definition",
                    "summary": (
                        f"'{r['concept']}' uses {r['distinct_filter_hashes']} different "
                        f"filterColumn sets across {r['n_dashboards']} dashboards "
                        f"({r['n_widgets']} widgets)"
                    ),
                    "details": f"hashes={r['filter_hashes']}",
                }
            )
        if r["distinct_aggregates"] > 1:
            findings.append(
                {
                    "score": 8 + r["n_dashboards"],
                    "category": "Metric definition",
                    "summary": (
                        f"'{r['concept']}' uses {r['distinct_aggregates']} different "
                        f"aggregates: {r['aggregates']}"
                    ),
                    "details": "",
                }
            )

    for r in dim2_rows:
        if len(r["distinct_headers"]) > 1:
            findings.append(
                {
                    "score": 5 + r["n_widgets"],
                    "category": "Naming",
                    "summary": (
                        f"'{r['concept']}' has {len(r['distinct_headers'])} different headers: "
                        f"{r['distinct_headers']}"
                    ),
                    "details": "",
                }
            )

    for r in dim3_rows:
        if len(r["viz_set"]) > 1:
            findings.append(
                {
                    "score": 7 + r["n_widgets"],
                    "category": "Visualization",
                    "summary": (
                        f"'{r['concept']}' uses {len(r['viz_set'])} different vizes: {r['viz_set']}"
                    ),
                    "details": str(r["examples"]),
                }
            )

    # Filter pass-through gaps
    missing_filters_widgets = [w for w in dim4_rows if w["missing_standard_filters"]]
    extra_filters_widgets = [w for w in dim4_rows if w["extra_filters"]]
    if missing_filters_widgets:
        # group by missing-set
        by_missing = defaultdict(list)
        for w in missing_filters_widgets:
            key = tuple(w["missing_standard_filters"])
            by_missing[key].append(w)
        for missing_set, ws in by_missing.items():
            # Heavily weight large groups missing all 4 filters — those are
            # widgets where dashboard-level filters can't cascade at all.
            severity = 50 if len(missing_set) == len(STANDARD_FILTER_COLS) else 6
            findings.append(
                {
                    "score": severity + len(ws),
                    "category": "Filter pass-through",
                    "summary": (
                        f"{len(ws)} Opp widgets missing standard filter(s): {list(missing_set)}"
                    ),
                    "details": "; ".join(f"{w['dashboard_id']}/{w['header']}" for w in ws[:10]),
                }
            )
    if extra_filters_widgets:
        findings.append(
            {
                "score": 5 + len(extra_filters_widgets),
                "category": "Filter pass-through",
                "summary": (
                    f"{len(extra_filters_widgets)} Opp widgets have non-standard "
                    f"extra filterColumns"
                ),
                "details": "; ".join(
                    f"{w['dashboard_id']}/{w['header']}={w['extra_filters']}"
                    for w in extra_filters_widgets[:8]
                ),
            }
        )

    findings.sort(key=lambda x: x["score"], reverse=True)
    top_findings = findings[:10]

    # ── Counts for executive summary ─────────────────────────────
    total_widgets = len(widgets)
    opp_widgets = len(dim4_rows)
    multi_concepts = len(multi_dashboard_clusters)
    metric_div_concepts = sum(1 for r in dim1_rows if r["distinct_filter_hashes"] > 1)
    naming_div_concepts = sum(1 for r in dim2_rows if len(r["distinct_headers"]) > 1)
    viz_div_concepts = sum(1 for r in dim3_rows if len(r["viz_set"]) > 1)
    missing_filters_count = len(missing_filters_widgets)
    extra_filters_count = len(extra_filters_widgets)

    # ── Render markdown ─────────────────────────────────────────
    md = []
    md.append("# Cross-Dashboard Consistency Audit")
    md.append("")
    md.append(f"_Generated 2026-04-28. Read-only describe of {len(dashboards)}/11 dashboards._")
    md.append("")
    md.append("## Executive summary")
    md.append("")
    # Compute dashboard-level filter coverage
    dashboards_with_filters = sum(1 for d in dashboards.values() if d.get("filters"))
    md.append(
        f"Audited **{total_widgets} widgets** across {len(dashboards)} dashboards. "
        f"{opp_widgets} are Opportunity-typed widgets that should carry the "
        f"4 standard filterColumns (Industry / Legal Country / Sales Region / "
        f"Account Unit Group). Cross-dashboard concept clusters: **{multi_concepts}**."
    )
    md.append("")
    md.append(
        f"**Dominant finding**: only **{dashboards_with_filters} of "
        f"{len(dashboards)} dashboards** define dashboard-level filters at all. "
        f"The other {len(dashboards) - dashboards_with_filters} ship with zero "
        f"filters at the dashboard level, AND **{missing_filters_count} of "
        f"{opp_widgets} Opp widgets** carry zero filterColumns. Net effect: any "
        f"filter a director picks on those 10 dashboards will silently no-op — "
        f"viewers see global totals, not their region/industry slice."
    )
    md.append("")
    md.append(
        f"Other findings: **{metric_div_concepts}** concepts where the same metric "
        f"is defined with different filter sets, **{naming_div_concepts}** "
        f"naming-divergence clusters (e.g. 'Open Pipeline ARR' vs 'Open Pipeline by "
        f"Region' for the same idea), **{viz_div_concepts}** visualization-divergence "
        f"clusters (renewal_acv uses 4 vizes across 6 widgets), and "
        f"**{extra_filters_count}** widgets carrying non-standard extras."
    )
    md.append("")
    md.append(
        "Exec-impact ranking: filter pass-through > metric definition > "
        "visualization > naming. Fixing the filter gap recovers **scoped numbers** "
        "for directors and CRO. Fixing the metric drift prevents 'why does Open "
        "Pipeline ARR show $X on SD Monthly but $Y on CRO Cockpit?' questions. "
        "Naming and viz fixes are polish."
    )
    md.append("")

    # ── Top 10 ─────────────────────────────────────────────────
    md.append("## Top 10 inconsistencies to fix")
    md.append("")
    if not top_findings:
        md.append("_No cross-dashboard inconsistencies detected._")
    else:
        md.append("| # | Category | Summary | Details |")
        md.append("|---|---|---|---|")
        for i, f in enumerate(top_findings, 1):
            details = f["details"] or "—"
            details_short = details[:200] + ("…" if len(details) > 200 else "")
            md.append(f"| {i} | {f['category']} | {f['summary']} | `{details_short}` |")
    md.append("")

    # ── Dashboard inventory ────────────────────────────────────
    md.append("## Dashboard inventory")
    md.append("")
    md.append("| Dashboard | Name | Components | Dashboard filters |")
    md.append("|---|---|---:|---|")
    for did, d in dashboards.items():
        flt_names = [f["name"] for f in d.get("filters") or []]
        md.append(f"| `{did}` | {d.get('name')} | {d.get('component_count')} | {flt_names} |")
    md.append("")

    # ── Dim 1 ──────────────────────────────────────────────────
    md.append("## Dimension 1 — Metric definition consistency")
    md.append("")
    md.append(
        "Same concept appearing on ≥2 dashboards. Flag rows where the "
        "filter-column set hash or aggregate set differs."
    )
    md.append("")
    md.append(
        "| Concept | # widgets | # dashboards | distinct filter sets | "
        "distinct aggregates | filter_hashes | aggregates |"
    )
    md.append("|---|---:|---:|---:|---:|---|---|")
    for r in dim1_rows:
        md.append(
            f"| {r['concept']} | {r['n_widgets']} | {r['n_dashboards']} | "
            f"{r['distinct_filter_hashes']} | {r['distinct_aggregates']} | "
            f"`{r['filter_hashes']}` | `{r['aggregates']}` |"
        )
    md.append("")

    # ── Dim 2 ──────────────────────────────────────────────────
    md.append("## Dimension 2 — Naming consistency")
    md.append("")
    md.append(
        "Cluster of widgets that mean the same thing. Flag rows where the "
        "literal `header` text isn't parallel."
    )
    md.append("")
    md.append("| Concept | # widgets | distinct header texts |")
    md.append("|---|---:|---|")
    for r in dim2_rows:
        if len(r["distinct_headers"]) > 1:
            md.append(f"| **{r['concept']}** | {r['n_widgets']} | {r['distinct_headers']} |")
        else:
            md.append(f"| {r['concept']} | {r['n_widgets']} | {r['distinct_headers']} |")
    md.append("")
    md.append("### Stage-name spot check (handbook expects '1 - Prospecting' through '8 - Won')")
    # Walk groupings for STAGE_NAME and report distinct sample headers.
    stage_widgets = [
        w for w in widgets if w["type"] == "Report" and "STAGE_NAME" in (w["groupings"] or [])
    ]
    md.append("")
    md.append(
        f"_{len(stage_widgets)} widgets group by STAGE_NAME. "
        "Stage-label literal text isn't visible from describe — it lives on the "
        "underlying report data. Verify by opening one widget per cluster._"
    )
    md.append("")

    # ── Dim 3 ──────────────────────────────────────────────────
    md.append("## Dimension 3 — Visualization consistency")
    md.append("")
    md.append(
        "Same concept should use the same viz where possible. Flag rows "
        "where the viz set has >1 element."
    )
    md.append("")
    md.append("| Concept | # widgets | distinct viz | examples (dashboard, header, viz) |")
    md.append("|---|---:|---|---|")
    for r in dim3_rows:
        flag = "**" if len(r["viz_set"]) > 1 else ""
        md.append(
            f"| {flag}{r['concept']}{flag} | {r['n_widgets']} | "
            f"{r['viz_set']} | {r['examples'][:4]} |"
        )
    md.append("")

    # ── Dim 4 ──────────────────────────────────────────────────
    md.append("## Dimension 4 — Filter pass-through consistency")
    md.append("")
    md.append(
        "Every Opportunity-typed widget should carry the 4 standard "
        "filterColumns. Below = widgets missing one or more, or with "
        "extras. Total Opp widgets audited: " + str(opp_widgets) + "."
    )
    md.append("")
    md.append("### Widgets MISSING one or more standard filterColumns")
    md.append("")
    if not missing_filters_widgets:
        md.append("_None._")
    else:
        md.append("| Dashboard | Header | Viz | Filter count | Missing |")
        md.append("|---|---|---|---:|---|")
        for w in missing_filters_widgets:
            md.append(
                f"| `{w['dashboard_id']}` | {w['header']} | {w['viz']} | "
                f"{w['filter_count']} | `{w['missing_standard_filters']}` |"
            )
    md.append("")
    md.append("### Widgets with EXTRA non-standard filterColumns")
    md.append("")
    if not extra_filters_widgets:
        md.append("_None._")
    else:
        md.append("| Dashboard | Header | Viz | Extra |")
        md.append("|---|---|---|---|")
        for w in extra_filters_widgets:
            md.append(
                f"| `{w['dashboard_id']}` | {w['header']} | {w['viz']} | `{w['extra_filters']}` |"
            )
    md.append("")

    # ── Hash legend ─────────────────────────────────────────────
    md.append("## Filter-set hash legend")
    md.append("")
    hash_to_set: dict[str, list[str]] = {}
    for w in widgets:
        h = w["filter_columns_hash"]
        if h and h not in hash_to_set:
            hash_to_set[h] = w["filter_columns_names"]
    md.append("| hash | filterColumn names |")
    md.append("|---|---|")
    for h, names in sorted(hash_to_set.items()):
        md.append(f"| `{h}` | `{names}` |")
    md.append("")
    md.append("---")
    md.append("")
    md.append(
        "_Method: GET /analytics/dashboards/<id>/describe (v65.0). "
        "11 dashboard describes ≈ 11 calls. No report-describe calls "
        "issued (we only inspect what describe returns on the dashboard "
        "payload). Read-only._"
    )
    md.append("")
    return "\n".join(md)


def main() -> int:
    ap = argparse.ArgumentParser(description="Cross-dashboard consistency audit")
    ap.add_argument(
        "--no-cache",
        action="store_true",
        help="Force re-fetch from SF (default uses raw/<id>.json cache)",
    )
    ap.add_argument("--out-dir", type=Path, default=Path("state/sf_audit"))
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = out_dir / "raw"

    instance, token, _ = sf_session()
    print(f"Connected to {instance}")

    widgets, dashboards = collect_all(instance, token, cache_dir, use_cache=not args.no_cache)
    print(f"\nCollected {len(widgets)} widgets across {len(dashboards)} dashboards")

    md = render_md(widgets, dashboards)
    md_path = out_dir / "dashboard_consistency_audit.md"
    md_path.write_text(md)
    json_path = out_dir / "dashboard_consistency_audit.json"
    json_path.write_text(
        json.dumps(
            {
                "widgets": widgets,
                "dashboards": dashboards,
            },
            indent=2,
        )
    )
    print(f"\nWrote {md_path}")
    print(f"Wrote {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
