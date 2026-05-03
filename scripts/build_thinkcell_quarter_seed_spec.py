#!/usr/bin/env python3
"""Build a Salesforce-backed think-cell quarter-deck seed-bank spec."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"


@dataclass(frozen=True)
class SeedContract:
    name: str
    family: str
    thinkcell_template_family: str
    data_source: str
    metric_guardrail: str
    supported_lane: str
    eligible_directors: list[str]
    fallback_directors: list[str]
    fallback: str
    build_priority: str
    notes: str


def _load_fit(period: str) -> dict[str, Any]:
    path = ROOT / "state" / period / "__regional__" / "thinkcell_sf_fit" / "thinkcell_quarter_salesforce_fit.json"
    if not path.exists():
        raise SystemExit(f"missing Salesforce fit JSON: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _eligible_directors(fit: dict[str, Any], gate: str) -> tuple[list[str], list[str]]:
    eligible: list[str] = []
    fallback: list[str] = []
    for row in fit.get("directors", []):
        director = str(row["director"])
        visual_fit = row.get("visual_fit", {})
        is_eligible = _gate_value(visual_fit, gate)
        if is_eligible:
            eligible.append(director)
        else:
            fallback.append(director)
    return eligible, fallback


def _gate_value(visual_fit: dict[str, Any], gate: str) -> bool:
    if gate == "bar_column":
        return bool(visual_fit.get("bar_column", {}).get("eligible"))
    if gate == "scatter_bubble":
        return bool(visual_fit.get("scatter_bubble", {}).get("eligible"))
    if gate == "timeline_gantt_fy26_renewals":
        return bool(visual_fit.get("timeline_gantt", {}).get("eligible_for_fy26_renewals"))
    if gate == "timeline_gantt_q2_renewals":
        return bool(visual_fit.get("timeline_gantt", {}).get("eligible_for_q2_renewals"))
    if gate == "mekko":
        return bool(visual_fit.get("mekko", {}).get("eligible"))
    if gate == "map":
        return bool(visual_fit.get("map", {}).get("eligible"))
    if gate == "tables":
        return bool(visual_fit.get("tables", {}).get("eligible"))
    if gate == "action_gantt":
        return bool(visual_fit.get("action_register", {}).get("gantt_eligible_from_salesforce"))
    if gate == "all":
        return True
    return False


def _contract(
    fit: dict[str, Any],
    *,
    name: str,
    family: str,
    template: str,
    source: str,
    guardrail: str,
    lane: str,
    gate: str,
    fallback: str,
    priority: str,
    notes: str,
) -> SeedContract:
    eligible, fallback_directors = _eligible_directors(fit, gate)
    return SeedContract(
        name=name,
        family=family,
        thinkcell_template_family=template,
        data_source=source,
        metric_guardrail=guardrail,
        supported_lane=lane,
        eligible_directors=eligible,
        fallback_directors=fallback_directors,
        fallback=fallback,
        build_priority=priority,
        notes=notes,
    )


def build_spec(period: str) -> dict[str, Any]:
    fit = _load_fit(period)
    contracts = [
        _contract(
            fit,
            name="QTR01_StageMix_Bar",
            family="bar_column",
            template="think-cell Charts/Bar, Column",
            source="Salesforce Q2 Land+Expand rows grouped by StageName.",
            guardrail="ARR universe only: Type IN ('Land','Expand'); never mix Renewal ACV.",
            lane="native think-cell chart via named seed + ppttc",
            gate="bar_column",
            fallback="native PowerPoint table only if fewer than two stages survive filters",
            priority="P0",
            notes="Default operating view for all directors.",
        ),
        _contract(
            fit,
            name="QTR02_ForecastMix_Bar",
            family="bar_column",
            template="think-cell Charts/Bar, Column",
            source="Salesforce Q2 Land+Expand rows grouped by ForecastCategoryName.",
            guardrail="ARR universe only; show omitted explicitly when present.",
            lane="native think-cell chart via named seed + ppttc",
            gate="bar_column",
            fallback="table-image register",
            priority="P0",
            notes="Pairs with forecast-quality narrative.",
        ),
        _contract(
            fit,
            name="QTR03_OwnerCoaching_Bar",
            family="bar_column",
            template="think-cell Charts/Bar, Column",
            source="Salesforce Q2 Land+Expand rows grouped by Opportunity Owner.",
            guardrail="Use converted EUR ARR and keep row counts separate from ARR sums.",
            lane="native think-cell chart via named seed + ppttc",
            gate="bar_column",
            fallback="ranked owner table",
            priority="P0",
            notes="High-value for coaching and inspection rhythm.",
        ),
        _contract(
            fit,
            name="QTR04_DealRisk_Scatter",
            family="scatter_bubble",
            template="think-cell Charts/Scatter, Bubble",
            source="Q2 Land+Expand named opportunities: ARR EUR, probability, age/stale flags.",
            guardrail="ARR only; do not plot Renewal ACV points.",
            lane="native think-cell chart via named seed + ppttc",
            gate="scatter_bubble",
            fallback="ranked risk table when probability or ARR has no spread",
            priority="P1",
            notes="Not for Patrick this quarter: data collapses.",
        ),
        _contract(
            fit,
            name="QTR05_FY26RenewalTimeline_Gantt",
            family="timeline_gantt",
            template="think-cell Charts/Timeline, Gantt",
            source="FY26 Renewal opportunities by CloseDate and Renewal ACV.",
            guardrail="Renewal ACV only; never combine with ARR.",
            lane="native think-cell chart via named seed + ppttc",
            gate="timeline_gantt_fy26_renewals",
            fallback="renewal watchlist table when dates collapse",
            priority="P1",
            notes="Not for Adam this quarter: date spread collapses.",
        ),
        _contract(
            fit,
            name="QTR06_Q2RenewalTimeline_Gantt",
            family="timeline_gantt",
            template="think-cell Charts/Timeline, Gantt",
            source="Q2 Renewal opportunities by CloseDate and Renewal ACV.",
            guardrail="Renewal ACV only; use only when Q2 renewal dates have real spread.",
            lane="native think-cell chart via named seed + ppttc",
            gate="timeline_gantt_q2_renewals",
            fallback="renewal watchlist table",
            priority="P2",
            notes="Only three directors qualify in current Q2 data.",
        ),
        _contract(
            fit,
            name="QTR07_StageIndustry_Mekko",
            family="mekko",
            template="think-cell Charts/Mekko",
            source="Q2 Land+Expand rows cross-tabbed by StageName and Industry.",
            guardrail="ARR universe only; use only when cells are dense enough to read.",
            lane="native think-cell chart via named seed + ppttc",
            gate="mekko",
            fallback="stacked bar or table-image matrix",
            priority="P2",
            notes="Eligible often, but should stay rare because interpretation cost is high.",
        ),
        _contract(
            fit,
            name="QTR08_PipelineMovement_Waterfall",
            family="waterfall",
            template="think-cell Charts/Waterfall",
            source="Workbook movement bridge: opening, created, pulled-in, pushed-out, closed.",
            guardrail="ARR movement only; source requires prior snapshot/workbook, not live Salesforce alone.",
            lane="native think-cell chart via named seed + ppttc",
            gate="all",
            fallback="movement table when prior snapshot is missing",
            priority="P1",
            notes="Conditional because the Salesforce point-in-time query alone cannot create opening movement.",
        ),
        _contract(
            fit,
            name="QTR09_Geography_RankedBar",
            family="bar_column_map_fallback",
            template="think-cell Charts/Bar, Column",
            source="Q2 Land+Expand rows by country/territory.",
            guardrail="ARR only; prefer ranked bars unless geographic spread is decision-relevant.",
            lane="native think-cell bar via named seed + ppttc",
            gate="bar_column",
            fallback="map only for explicit geography story",
            priority="P2",
            notes="The fit test says maps qualify for 6/9 but ranked bars are usually clearer.",
        ),
        _contract(
            fit,
            name="QTR10_ActionDecisionRegister_TableImage",
            family="table_image",
            template="Useful Elements/Tables plus Excel COM AddRangeImage donor",
            source="Regional intelligence spec first-two-week actions and decision checklist.",
            guardrail="Actions are registers, not Gantt timelines, until due dates are structured.",
            lane="Excel COM AddRangeImage table-image donor",
            gate="tables",
            fallback="native PowerPoint table",
            priority="P0",
            notes="All directors qualify; current Salesforce NextStep is text.",
        ),
        _contract(
            fit,
            name="QTR11_CommercialApprovalGap_TableImage",
            family="table_image",
            template="Useful Elements/Tables plus Excel COM AddRangeImage donor",
            source="Stage 3+ Land/Expand approval-gap rows from regional intelligence spec.",
            guardrail="Commercial Approval is a Land/Expand governance gate; do not apply to Renewal ACV.",
            lane="Excel COM AddRangeImage table-image donor",
            gate="tables",
            fallback="native PowerPoint table",
            priority="P0",
            notes="High-value SimCorp-specific inspection object.",
        ),
        _contract(
            fit,
            name="QTR12_StalePipeline_BarTable",
            family="bar_column_table_image",
            template="think-cell Charts/Bar, Column plus table-image details",
            source="No-activity and stale-age rows from Salesforce/regional intelligence spec.",
            guardrail="ARR universe only; stale ARR is not Renewal ACV.",
            lane="native think-cell bar for summary; table-image donor for named deals",
            gate="bar_column",
            fallback="table-image only",
            priority="P0",
            notes="Directly supports the May 1-15 operating actions.",
        ),
    ]
    return {
        "schema": "thinkcell-quarter-seed-bank-spec/v1",
        "period": period,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_fit": str(
            ROOT
            / "state"
            / period
            / "__regional__"
            / "thinkcell_sf_fit"
            / "thinkcell_quarter_salesforce_fit.json"
        ),
        "salesforce_totals": fit.get("totals", {}),
        "family_eligibility_counts": fit.get("family_eligibility_counts", {}),
        "hard_rules": [
            "ARR equals Land+Expand only and uses APTS_Opportunity_ARR__c.",
            "ACV equals Renewal only and uses APTS_Renewal_ACV__c.",
            "Every Type-bearing source must apply explicit Type filters.",
            "Headline currency figures must use converted/reporting EUR values.",
            "Do not use funnels for the SimCorp 8-stage process.",
        ],
        "contracts": [asdict(contract) for contract in contracts],
    }


def write_markdown(spec: dict[str, Any], path: Path) -> None:
    lines = [
        "# think-cell Quarter Seed-Bank Spec",
        "",
        f"- Period: `{spec['period']}`",
        f"- Source fit: `{spec['source_fit']}`",
        f"- Publishable Q2 rows: `{spec['salesforce_totals'].get('q2_publishable_rows')}`",
        f"- Internal/test rows removed: `{spec['salesforce_totals'].get('q2_internal_rows_removed')}`",
        "",
        "## Contracts",
        "",
        "| Name | Family | Priority | Eligible | Fallback | Lane |",
        "|---|---|---:|---:|---|---|",
    ]
    for contract in spec["contracts"]:
        eligible = len(contract["eligible_directors"])
        total = eligible + len(contract["fallback_directors"])
        lines.append(
            "| "
            f"`{contract['name']}` | {contract['family']} | {contract['build_priority']} | "
            f"{eligible}/{total} | {contract['fallback']} | {contract['supported_lane']} |"
        )
    lines.extend(["", "## Fallbacks", ""])
    for contract in spec["contracts"]:
        if contract["fallback_directors"]:
            lines.append(
                f"- `{contract['name']}` fallback directors: "
                + ", ".join(contract["fallback_directors"])
            )
    lines.extend(["", "## Hard Rules", ""])
    lines.extend(f"- {rule}" for rule in spec["hard_rules"])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "state" / "thinkcell_bridge" / "quarter_seed_bank",
    )
    args = parser.parse_args()

    out_dir = args.output_dir / args.period
    out_dir.mkdir(parents=True, exist_ok=True)
    spec = build_spec(args.period)
    json_path = out_dir / "quarter_seed_bank_spec.json"
    md_path = out_dir / "quarter_seed_bank_spec.md"
    json_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    write_markdown(spec, md_path)
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    print(f"contracts={len(spec['contracts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
