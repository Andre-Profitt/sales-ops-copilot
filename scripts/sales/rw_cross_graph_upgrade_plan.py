"""Cross-analyze Zebra, RW KPI, and live Power BI graphs for upgrade targets."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_PBI_GRAPH = (
    Path("output")
    / "rw_dashboard_harness"
    / "pbi_knowledge_graph"
    / "rw_live_pbi_kg.pbi_knowledge_graph.json"
)
DEFAULT_ZEBRA_INFRA = Path("data") / "zebra_kg" / "infrastructure" / "summary.json"
DEFAULT_ZEBRA_TRANSFER = Path("data") / "zebra_kg" / "transfer" / "rw_page_transfer_patterns.json"
DEFAULT_MARKDOWN = Path("docs") / "sales" / "RW_CROSS_GRAPH_UPGRADE_TARGET_PLAN.md"
DEFAULT_JSON = (
    Path("output")
    / "rw_dashboard_harness"
    / "cross_graph_upgrade_plan"
    / "rw_cross_graph_upgrade_plan.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def _generated_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _page_index(pbi_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {page["page"]: page for page in pbi_graph.get("page_summaries", [])}


def _findings_by_page(pbi_graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for finding in pbi_graph.get("cleanup_findings", []):
        page = str(finding.get("page") or "")
        if page:
            out.setdefault(page, []).append(finding)
    return out


def _findings_without_page(pbi_graph: dict[str, Any]) -> list[dict[str, Any]]:
    return [finding for finding in pbi_graph.get("cleanup_findings", []) if not finding.get("page")]


def _data_surface_rows() -> list[dict[str, Any]]:
    from scripts.sales.rw_data_surface_flow_audit import audit_data_surface_flow

    return list(audit_data_surface_flow().get("flow_rows", []))


def _flow_index(flow_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["kpi_id"]: row for row in flow_rows}


def _visual_mix_insights(
    pbi_graph: dict[str, Any],
    zebra_infra: dict[str, Any],
) -> list[dict[str, str]]:
    visual_counts = Counter(pbi_graph.get("summary", {}).get("visual_type_counts", {}))
    total_pbi = max(1, int(pbi_graph.get("summary", {}).get("visual_count") or 0))
    zebra_family = Counter(zebra_infra.get("by_family", {}))
    total_zebra = max(1, int(zebra_infra.get("total_zebra_visuals") or sum(zebra_family.values()) or 0))
    table_like = visual_counts.get("tableEx", 0) + visual_counts.get("pivotTable", 0)
    bridge_like = visual_counts.get("waterfallChart", 0)
    insights = [
        {
            "signal": "bridge_gap",
            "evidence": (
                f"Live PBI has {bridge_like} native waterfall/bridge visuals; Zebra corpus has "
                f"{zebra_family.get('ZebraWaterfall', 0)}/{total_zebra} waterfall visuals."
            ),
            "meaning": "RW pages are not yet using Zebra's bridge/decomposition grammar for executive variance stories.",
        },
        {
            "signal": "card_weight",
            "evidence": (
                f"Live PBI card share is {visual_counts.get('card', 0)}/{total_pbi}; Zebra card share is "
                f"{zebra_family.get('ZebraBICards', 0)}/{total_zebra}."
            ),
            "meaning": "Cards are acceptable for a KPI spine, but the target state should move more meaning into variance tables and bridges.",
        },
        {
            "signal": "ibcs_table_base",
            "evidence": (
                f"Live PBI already has {table_like} native table/matrix visuals and Zebra has "
                f"{zebra_family.get('ZebraBITables', 0)} table visuals."
            ),
            "meaning": "The native tableEx path is the right base; the next lift is scenario columns, variance deltas, and action-ledger ordering.",
        },
    ]
    return insights


def _zebra_schema_signals(zebra_infra: dict[str, Any], zebra_transfer: dict[str, Any]) -> list[dict[str, str]]:
    learned = zebra_transfer.get("learned_rules", {})
    return [
        {
            "pattern": "scenario_variance_columns",
            "evidence": (
                "Zebra top comparison keys include actual, previousYear, plan, forecast, "
                "actual-plan, actual-previousYear, and variance-percent columns."
            ),
            "rw_application": "Forecast, Growth Mix, Renewals, and Scorecard need AC/PL/PY/FC-style measures where source data supports them.",
        },
        {
            "pattern": "ibcs_table_ordering",
            "evidence": learned.get("variance_table", ""),
            "rw_application": "Make variance tables the primary diagnostic surface, not secondary tables below KPI cards.",
        },
        {
            "pattern": "waterfall_bridge",
            "evidence": learned.get("waterfall_bridge", ""),
            "rw_application": "Use bridge visuals for Forecast gap, Renewal base movement, and Growth contribution decomposition.",
        },
        {
            "pattern": "neutral_kpi_tile",
            "evidence": learned.get("kpi_tile", ""),
            "rw_application": "Keep KPI cards neutral and compact; reserve color for thin accents, variance arrows, or RAG text.",
        },
        {
            "pattern": "static_furniture",
            "evidence": learned.get("static_furniture", ""),
            "rw_application": "Retain section headers and furniture as layout structure, but avoid decorative card stacks.",
        },
    ]


def _opportunity(
    *,
    rank: int,
    priority: str,
    opportunity_id: str,
    target: str,
    owner_lane: str,
    graph_evidence: list[str],
    zebra_pattern: str,
    target_state: str,
    data_or_model_work: list[str],
    bi_surface_work: list[str],
    acceptance: list[str],
) -> dict[str, Any]:
    return {
        "rank": rank,
        "priority": priority,
        "id": opportunity_id,
        "target": target,
        "owner_lane": owner_lane,
        "graph_evidence": graph_evidence,
        "zebra_pattern": zebra_pattern,
        "target_state": target_state,
        "data_or_model_work": data_or_model_work,
        "bi_surface_work": bi_surface_work,
        "acceptance": acceptance,
    }


def build_upgrade_plan(
    *,
    pbi_graph: dict[str, Any],
    zebra_infra: dict[str, Any],
    zebra_transfer: dict[str, Any],
    flow_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    flow_rows = flow_rows if flow_rows is not None else _data_surface_rows()
    flow = _flow_index(flow_rows)
    pages = _page_index(pbi_graph)
    page_findings = _findings_by_page(pbi_graph)
    report_findings = _findings_without_page(pbi_graph)

    opportunities = [
        _opportunity(
            rank=1,
            priority="P0",
            opportunity_id="forecast_scenario_spine",
            target="Forecast",
            owner_lane="data model + BI surface",
            graph_evidence=[
                "PBI graph: Forecast has high cleanup findings for pipeline coverage and forecast accuracy.",
                f"KPI graph: pipeline_coverage_3x status is {flow.get('pipeline_coverage_3x', {}).get('dashboard_status', 'unknown')}.",
                f"KPI graph: forecast_accuracy status is {flow.get('forecast_accuracy', {}).get('dashboard_status', 'unknown')}.",
                "Zebra graph: AC/PL/FC scenario pairings and synthesized variance columns are core patterns.",
            ],
            zebra_pattern="scenario_variance_columns + waterfall_bridge",
            target_state=(
                "Forecast becomes a scenario spine: actual/won ARR, open value, target/plan, submitted forecast, "
                "coverage gap, and forecast accuracy are shown as variance table plus bridge, not proxy cards."
            ),
            data_or_model_work=[
                "Stage a quota/target denominator and create `Pipeline Coverage Ratio`.",
                "Stage ForecastingItem or snapshot history for true submitted-forecast accuracy.",
                "Add forecast-transition date role before adding movement-period slicers.",
            ],
            bi_surface_work=[
                "Replace proxy-first slip cards with an AC/PL/FC variance table.",
                "Add a Forecast gap bridge: plan/quota -> closed won ARR -> open ARR gap, with Renewal ACV shown separately.",
                "Do not use a top-level ARR+ACV blended value; keep Land/Expand ARR and Renewal ACV as separate columns/cards.",
            ],
            acceptance=[
                "Forecast page has zero high data-surface findings.",
                "`Forecast Accuracy` and `Pipeline Coverage Ratio` are real measures, not proxy labels.",
                "Visual QA, unit policy, metric basis, and semantic-filter gates remain clear at high severity.",
            ],
        ),
        _opportunity(
            rank=2,
            priority="P0",
            opportunity_id="growth_mix_trusted_segmentation",
            target="Growth Mix",
            owner_lane="source data + BI surface",
            graph_evidence=[
                "PBI graph: Growth Mix has a high finding for Synergy deals won.",
                f"KPI graph: synergy_deals_won status is {flow.get('synergy_deals_won', {}).get('dashboard_status', 'unknown')}.",
                f"KPI graph: synergy_deals_pipe status is {flow.get('synergy_deals_pipe', {}).get('dashboard_status', 'unknown')}.",
                "Zebra graph: variance tables and bridge charts are the dominant pattern for explaining mix shifts.",
            ],
            zebra_pattern="variance_table + waterfall_bridge",
            target_state=(
                "Growth Mix explains contribution, not just values: Land, Expand, Partner, Axioma, SaaS, PS attach, "
                "Synergy, and one-off revenue become a governed mix matrix and contribution bridge."
            ),
            data_or_model_work=[
                "Stage a trusted Synergy flag for won and open pipeline.",
                "Keep one-off/non-recurring revenue as a separate governed basis; it is now staged and surfaced.",
                "Keep Land and Expand written out and separate from Renewal ACV.",
            ],
            bi_surface_work=[
                "Add Synergy won/open rows to the strategic mix table once the flag exists.",
                "Add a contribution bridge by growth source and motion.",
                "Move proxy Land won count out of the Synergy slot once real Synergy measures exist.",
            ],
            acceptance=[
                "`synergy_deals_won` and `synergy_deals_pipe` are no longer proxy/model gaps.",
                "Growth Mix has explicit source/motion labels and no ARR/Renewal ACV blending.",
                "The page still passes visual QA with zero medium+ findings.",
            ],
        ),
        _opportunity(
            rank=3,
            priority="P1",
            opportunity_id="renewal_base_bridge",
            target="Renewals",
            owner_lane="semantic model + BI surface",
            graph_evidence=[
                "PBI graph: Renewals is visually clean but still uses only one chart and one detail table.",
                f"KPI graph: indexation_arr_growth status is {flow.get('indexation_arr_growth', {}).get('dashboard_status', 'unknown')}.",
                "Zebra graph: 140 waterfall visuals in the corpus indicate bridge/decomposition is a first-class executive pattern.",
            ],
            zebra_pattern="waterfall_bridge + variance_table",
            target_state=(
                "Renewals becomes an active-base bridge: active-base ARR -> expiring base -> at-risk base -> won/lost "
                "renewal ACV -> retained base and indexation/uplift. Renewal ACV and active-base ARR stay separated."
            ),
            data_or_model_work=[
                "Stage indexation/uplift or contract price-change fields.",
                "Verify active Asset/Subscription base grain and renewal linkage.",
                "Add renewal-base variance measures without mixing Renewal ACV into ARR.",
            ],
            bi_surface_work=[
                "Replace the single at-risk bar emphasis with an active-base waterfall/bridge.",
                "Keep the account detail ledger as drill path, not as the primary story.",
                "Add an indexation/uplift row only after source data is real.",
            ],
            acceptance=[
                "`indexation_arr_growth` no longer shows missing source data.",
                "Renewals has an explicit bridge visual or bridge-equivalent native table.",
                "Renewal ACV and active-base ARR labels remain visibly distinct.",
            ],
        ),
        _opportunity(
            rank=4,
            priority="P1",
            opportunity_id="product_segment_retention_churn",
            target="Renewals / Product Mix",
            owner_lane="semantic model + BI surface",
            graph_evidence=[
                "Current semantic model has product grain on `f_asset_line_item`: product family, area, type, account, region, industry, ARR, and asset end date.",
                "Churn/NRR experiment is explicitly tracked here: Salesforce asset probe found 97,586 current active/non-expired rows and 125,419 historical/effective-dated rows since 2025-01-01, including 17,466 inactive rows.",
                "PBI graph: Renewals already exposes product family in the active-base detail ledger, but not as a product x segment x region heatmap or retention bridge.",
                "Salesforce gap probe identified OpportunityLineItem as the likely source for new-business product/revenue-stream mix.",
                "Zebra graph: scenario variance columns map naturally to prior active base versus current active base by product.",
            ],
            zebra_pattern="scenario_variance_columns + ibcs_table_ordering + heatmap matrix",
            target_state=(
                "Build both views: (1) product x segment x region mix heatmaps for current exposure and risk, and "
                "(2) installed-base churn/retention by account-product-period: prior active-base ARR, current "
                "active-base ARR, retained ARR, churn/downsell, expansion, cross-sell, and product churn."
            ),
            data_or_model_work=[
                "Create an effective-dated or snapshot fact for active-base ARR by account-product-period.",
                "Build the experimental Churn/NRR tab from prior/current active-base ARR snapshots before promoting any churn metric to production.",
                "Use asset start/end dates to reconstruct prior/current base only if historical rows are not overwritten; otherwise persist monthly snapshots.",
                "Define segment explicitly: industry, account type, named segment, or another governed account attribute.",
                "Stage OpportunityLineItem later for Land + Expand product mix; do not use renewal asset base as new-business product pipeline.",
            ],
            bi_surface_work=[
                "Product heatmap: Product Family/Product Area x Region with active-base ARR, expiring ARR, at-risk ARR, and risk percentage.",
                "Product heatmap: Product Family/Product Area x Segment once segment is governed.",
                "Churn view: prior versus current active-base ARR by account-product-period, with retained/churn/downsell/expansion/cross-sell classification.",
                "Experimental NRR strip: starting active-base ARR, retained active-base ARR, churn/downsell ARR, expansion/cross-sell ARR, GRR %, and NRR %.",
                "Add account-product churn ledger: prior product ARR, current product ARR, delta, churn classification, renewal date.",
                "Keep this as active-base ARR retention, not Renewal ACV and not Land + Expand ARR.",
            ],
            acceptance=[
                "Product heatmap and churn view both exist; neither is substituted for the other.",
                "The churn/NRR experiment is labeled experimental until snapshot/effective-date reconstruction is tie-out tested.",
                "Gross retention and net retention by account-product are computed from prior/current active-base ARR.",
                "Product churn/downsell/expansion/cross-sell classifications are deterministic and tested.",
                "All visuals label basis as active-base ARR; Renewal ACV remains separate.",
                "Heatmap/matrix output passes visual QA and metric-basis gates.",
            ],
        ),
        _opportunity(
            rank=5,
            priority="P1",
            opportunity_id="movement_date_roles",
            target="Stage Hygiene / What Changed / Forecast",
            owner_lane="semantic model",
            graph_evidence=[
                "PBI graph: report-level cleanup has medium findings for stage and forecast transition-date roles.",
                "Zebra schema graph: role-playing date dimensions are a mined architecture pattern.",
                "Current pages use Close FQ as cohort context, but movement analytics need transition-period context.",
            ],
            zebra_pattern="role_playing_dates",
            target_state=(
                "Movement pages can slice stage and forecast changes by transition date without confusing that with close-period cohorts."
            ),
            data_or_model_work=[
                "Add direct calendar roles for `f_stage_transition.transition_at` and `f_forecast_transition.transition_at`.",
                "Keep Close FQ slicers on executive pages; add movement-period controls only where page contract allows.",
                "Document date-role basis in visible labels and contracts.",
            ],
            bi_surface_work=[
                "Add controlled movement-period views after model roles exist.",
                "Use transition-date roles for Stage Hygiene and What Changed movement ledgers.",
            ],
            acceptance=[
                "Semantic-filter audit has zero medium transition-date findings.",
                "No page uses a movement-period slicer before the model role exists.",
            ],
        ),
        _opportunity(
            rank=6,
            priority="P1",
            opportunity_id="scorecard_driver_tree",
            target="VP Ops Scorecard",
            owner_lane="BI surface",
            graph_evidence=[
                "PBI graph: VP Ops Scorecard has 8 cards, 12 shapes, and no cleanup findings.",
                "Enterprise graph: VP Ops Scorecard is 91% Zebra-native, lower than the other executive pages.",
                "Zebra graph: KPI cards are a spine; variance tables and bridges carry the explanation.",
            ],
            zebra_pattern="kpi_tile + variance_table + bridge",
            target_state=(
                "The scorecard becomes a driver tree: headline outcome, gap-to-plan, exception lane, stage lane, renewal lane, "
                "and 7-day movement lane. Cards summarize; tables/bridge explain."
            ),
            data_or_model_work=[
                "Depends on Forecast plan/coverage and movement-date work for the strongest scorecard version.",
            ],
            bi_surface_work=[
                "Reduce pure scorecard feel by making one primary variance/driver table the central artifact.",
                "Use neutral Zebra card treatment and explicit Land + Expand / Renewal ACV labels.",
                "Add navigation/drill targets from each lane to its detail tab.",
            ],
            acceptance=[
                "VP Ops Scorecard reaches 100% Zebra-native decision-visual coverage.",
                "The page has a visible driver path from headline to detail, not only metric tiles.",
            ],
        ),
        _opportunity(
            rank=7,
            priority="P2",
            opportunity_id="explorer_contract_and_slice_dice",
            target="RW KPI Explorer",
            owner_lane="governance + BI surface",
            graph_evidence=[
                "PBI graph: RW KPI Explorer uses 17 measures but has no KPI contract.",
                "KPI graph: 31 canonical KPIs exist; 29 are placed on executive pages.",
                "Zebra graph: KPI metadata tables are a mined schema pattern across templates.",
            ],
            zebra_pattern="kpi_dictionary + scenario_axis",
            target_state=(
                "Explorer becomes a governed analysis page with explicit safe slicers, KPI metadata, and separate ARR/Renewal ACV lanes."
            ),
            data_or_model_work=[
                "Consider future `d_kpi` metadata table only after page contracts stabilize.",
                "Do not use a universal Motion slicer that contradicts DAX motion guardrails.",
            ],
            bi_surface_work=[
                "Add an explorer contract documenting allowed slicers and non-executive status.",
                "Group explorer visuals into Land + Expand ARR, Renewal ACV, Stage, and Growth lanes.",
            ],
            acceptance=[
                "Explorer contract exists and is tested.",
                "Explorer remains free of `Total Open Pipeline Value` unless explicitly labeled cross-motion.",
            ],
        ),
        _opportunity(
            rank=8,
            priority="P2",
            opportunity_id="expand_zebra_exemplar_library",
            target="Zebra transfer framework",
            owner_lane="transfer engineering",
            graph_evidence=[
                "Current transfer framework is grounded primarily in `sales-funnel-power-bi-template`.",
                "Zebra corpus has 20 templates and 360 mined Zebra visuals.",
                "RW Growth Mix and Renewals need patterns beyond the sales-funnel exemplar.",
            ],
            zebra_pattern="multi_template_pattern_mining",
            target_state=(
                "The transfer layer learns page archetypes from sales, SaaS, daily flash, PVM, and cost/benefit templates before broader rewrites."
            ),
            data_or_model_work=[
                "No production model change required.",
            ],
            bi_surface_work=[
                "Mine and compare `saas-sales-power-bi-dashboard-template`, `daily-sales-flash-power-bi-dashboard`, `price-volume-mix-analysis-power-bi-template`, and `cost-benefit-analysis-power-bi-template`.",
                "Extract reusable native patterns for variance tables, bridge charts, comments/annotations, and executive page furniture.",
            ],
            acceptance=[
                "A second and third Zebra exemplar produce DNA + native rebuild gates with zero custom leftovers.",
                "RW page helpers reference specific learned patterns, not generic Zebra lineage.",
            ],
        ),
    ]

    summary = {
        "generated_at": _generated_at(),
        "pbi_verdict": pbi_graph.get("summary", {}).get("verdict"),
        "pbi_pages": pbi_graph.get("summary", {}).get("page_count"),
        "pbi_visuals": pbi_graph.get("summary", {}).get("visual_count"),
        "pbi_cleanup_counts": pbi_graph.get("summary", {}).get("cleanup_counts", {}),
        "zebra_visuals": zebra_infra.get("total_zebra_visuals"),
        "rw_clean_kpis": sum(1 for row in flow_rows if row.get("dashboard_status") == "surfaced"),
        "rw_total_kpis": len(flow_rows),
        "p0_count": sum(1 for item in opportunities if item["priority"] == "P0"),
        "p1_count": sum(1 for item in opportunities if item["priority"] == "P1"),
        "p2_count": sum(1 for item in opportunities if item["priority"] == "P2"),
    }

    return {
        "schema": "rw-cross-graph-upgrade-plan.v1",
        "summary": summary,
        "visual_mix_insights": _visual_mix_insights(pbi_graph, zebra_infra),
        "zebra_schema_signals": _zebra_schema_signals(zebra_infra, zebra_transfer),
        "opportunities": opportunities,
        "page_graph_snapshot": {
            page: {
                "visual_type_counts": pages.get(page, {}).get("visual_type_counts", {}),
                "kpis_served": pages.get(page, {}).get("kpis_served", []),
                "cleanup_findings": [
                    {
                        "severity": finding.get("severity"),
                        "source": finding.get("source"),
                        "message": finding.get("message"),
                    }
                    for finding in page_findings.get(page, [])
                ],
            }
            for page in pages
        },
        "report_findings": report_findings,
    }


def _md_list(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values]


def render_markdown(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        "# RW Cross-Graph Upgrade Target Plan",
        "",
        f"Generated: `{summary['generated_at']}`",
        "",
        "This compares three graphs: Zebra template/visual grammar, the live RW Power BI artifact graph, and the RW KPI coverage graph. The target is not more cosmetic styling; it is a better executive operating system with Zebra-grade scenario, variance, and bridge semantics.",
        "",
        "## Readout",
        "",
        f"- Live PBI graph verdict: `{summary['pbi_verdict']}`",
        f"- Live PBI footprint: `{summary['pbi_pages']}` pages, `{summary['pbi_visuals']}` visuals",
        f"- PBI cleanup counts: `{summary['pbi_cleanup_counts']}`",
        f"- Zebra mined visual corpus: `{summary['zebra_visuals']}` visuals",
        f"- RW KPI surface: `{summary['rw_clean_kpis']}` clean out of `{summary['rw_total_kpis']}` KPIs",
        f"- Target plan: `{summary['p0_count']}` P0, `{summary['p1_count']}` P1, `{summary['p2_count']}` P2",
        "",
        "## Core Graph Signals",
        "",
        "| Signal | Evidence | Meaning |",
        "| --- | --- | --- |",
    ]
    for item in plan["visual_mix_insights"]:
        lines.append(f"| `{item['signal']}` | {item['evidence']} | {item['meaning']} |")

    lines += [
        "",
        "## Zebra Patterns To Transfer",
        "",
        "| Pattern | Evidence | RW application |",
        "| --- | --- | --- |",
    ]
    for item in plan["zebra_schema_signals"]:
        lines.append(f"| `{item['pattern']}` | {item['evidence']} | {item['rw_application']} |")

    lines += [
        "",
        "## Ranked Upgrade Opportunities",
        "",
    ]
    for item in plan["opportunities"]:
        lines += [
            f"### {item['rank']}. {item['target']} — `{item['id']}` ({item['priority']})",
            "",
            f"- Owner lane: {item['owner_lane']}",
            f"- Zebra pattern: `{item['zebra_pattern']}`",
            f"- Target state: {item['target_state']}",
            "",
            "**Graph evidence**",
            *_md_list(item["graph_evidence"]),
            "",
            "**Data/model work**",
            *_md_list(item["data_or_model_work"]),
            "",
            "**BI surface work**",
            *_md_list(item["bi_surface_work"]),
            "",
            "**Acceptance**",
            *_md_list(item["acceptance"]),
            "",
        ]

    lines += [
        "## Execution Sequence",
        "",
        "1. Close P0 source/model blockers: quota/target, forecast snapshots, Synergy flag.",
        "2. Add movement date roles so Stage/Forecast movement pages can support period analysis without abusing Close FQ.",
        "3. Rebuild Forecast and Growth Mix with scenario variance tables and bridge/decomposition visuals.",
        "4. Add product x segment x region active-base retention/churn heatmaps from asset snapshots or effective-dated asset rows.",
        "5. Upgrade Renewals to an active-base bridge once indexation/uplift fields are staged.",
        "6. Recompose VP Ops Scorecard as a driver tree after Forecast/Growth Mix have real measures.",
        "7. Add an explicit explorer contract and mine additional Zebra templates for broader pattern transfer.",
        "",
        "## Non-Targets",
        "",
        "- Do not spend the next pass on color/card styling alone; visual QA is already clean.",
        "- Do not force Zebra custom visuals through SimCorp restrictions; native transfer remains the path.",
        "- Do not count proxy KPIs as finished executive metrics.",
        "- Do not blend ARR and Renewal ACV. ARR is Land + Expand only; Renewal ACV is Renewal only. Production pages should show those bases separately, not as one top-level ARR+ACV total.",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(
    *,
    markdown_path: Path = DEFAULT_MARKDOWN,
    json_path: Path = DEFAULT_JSON,
    pbi_graph_path: Path = DEFAULT_PBI_GRAPH,
    zebra_infra_path: Path = DEFAULT_ZEBRA_INFRA,
    zebra_transfer_path: Path = DEFAULT_ZEBRA_TRANSFER,
) -> tuple[Path, Path, dict[str, Any]]:
    pbi_graph = _read_json(pbi_graph_path)
    zebra_infra = _read_json(zebra_infra_path)
    zebra_transfer = _read_json(zebra_transfer_path)
    plan = build_upgrade_plan(
        pbi_graph=pbi_graph,
        zebra_infra=zebra_infra,
        zebra_transfer=zebra_transfer,
    )
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(plan), encoding="utf-8")
    json_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return markdown_path, json_path, plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbi-graph", type=Path, default=DEFAULT_PBI_GRAPH)
    parser.add_argument("--zebra-infra", type=Path, default=DEFAULT_ZEBRA_INFRA)
    parser.add_argument("--zebra-transfer", type=Path, default=DEFAULT_ZEBRA_TRANSFER)
    parser.add_argument("--markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = parser.parse_args()
    markdown_path, json_path, plan = write_outputs(
        markdown_path=args.markdown,
        json_path=args.json,
        pbi_graph_path=args.pbi_graph,
        zebra_infra_path=args.zebra_infra,
        zebra_transfer_path=args.zebra_transfer,
    )
    print(f"cross-graph plan markdown: {markdown_path}")
    print(f"cross-graph plan json: {json_path}")
    print(
        f"opportunities={len(plan['opportunities'])} "
        f"p0={plan['summary']['p0_count']} "
        f"p1={plan['summary']['p1_count']} "
        f"p2={plan['summary']['p2_count']}"
    )


if __name__ == "__main__":
    main()
