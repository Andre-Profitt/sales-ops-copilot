#!/usr/bin/env python3
"""Build per-director think-cell visual contract plans.

The deck factory already knows which think-cell contracts are proven. This
script turns that global blueprint into per-director decisions: include,
candidate, fallback, or suppress, with the data-shape evidence that justifies
each decision.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from _directors import canonical_directors
from run_regional_deck_publish_gate import _visual_gate_findings


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"


CONTRACT_TARGETS: dict[str, str] = {
    "QTR01_StageMix_Bar": "stage mix / pipeline quality",
    "QTR02_ForecastMix_Bar": "forecast mix",
    "QTR03_OwnerCoaching_Bar": "owner coaching",
    "QTR04_DealRisk_Scatter": "named deal risk inspection",
    "QTR05_FY26RenewalTimeline_Gantt": "FY26 renewal watchlist",
    "QTR06_Q2RenewalTimeline_Gantt": "Q2 renewal timing",
    "QTR07_StageIndustry_Mekko": "stage by industry mix",
    "QTR08_PipelineMovement_Waterfall": "pipeline movement bridge",
    "QTR09_Geography_RankedBar": "geography ranking",
    "QTR10_ActionDecisionRegister_TableImage": "action decision register",
    "QTR11_CommercialApprovalGap_TableImage": "commercial approval gap",
    "QTR12_StalePipeline_BarTable": "stale pipeline triage",
}

MULTI_GEO_TERRITORY_TOKENS = {
    "APAC",
    "Southern Europe",
    "UK & Ireland",
    "NL & Nordics",
    "Middle East & Africa",
}


@dataclass(frozen=True)
class VisualDecision:
    contract: str
    priority: str
    family: str
    target: str
    lane: str
    decision: str
    reason: str
    evidence: list[str]
    fallback: str
    template: str
    proof_status: str
    guardrail: str


@dataclass(frozen=True)
class DirectorPlan:
    director: str
    slug: str
    territory: str
    status: str
    blockers: list[str]
    visual_gate_metrics: dict[str, Any]
    decisions: list[VisualDecision]
    artifacts: dict[str, str]


def _slug(value: str) -> str:
    return value.replace(" ", "-")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _blueprint_path(period: str) -> Path:
    return ROOT / "state" / period / "__regional__" / "thinkcell_deck_blueprint" / "thinkcell_deck_factory_blueprint.json"


def _director_dir(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug


def _selected_directors(director_slug: str | None) -> list[dict[str, Any]]:
    directors = canonical_directors()
    if not director_slug:
        return directors
    return [director for director in directors if _slug(str(director["name"])) == director_slug]


def _gate_metric(metrics: dict[str, Any], rule: str) -> dict[str, Any]:
    for key, value in metrics.items():
        if key.endswith(f":{rule}") and isinstance(value, dict):
            return value
    return {}


def _scatter_pass(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    gate = _gate_metric(metrics, "scatter_requires_two_noncollapsed_axes")
    if not gate:
        return False, ["scatter visual gate missing"]
    distinct_x = int(gate.get("distinct_x") or 0)
    distinct_y = int(gate.get("distinct_y") or 0)
    min_x = int(gate.get("min_x") or 2)
    min_y = int(gate.get("min_y") or 2)
    return distinct_x >= min_x and distinct_y >= min_y, [
        f"scatter axes distinct_x={distinct_x}/{min_x}, distinct_y={distinct_y}/{min_y}",
        f"source={gate.get('source')}",
    ]


def _timeline_pass(metrics: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    gate = _gate_metric(metrics, "timeline_requires_distinct_dates")
    if not gate:
        return False, ["timeline visual gate missing"], []
    dates = [str(value) for value in gate.get("distinct_dates") or [] if value]
    minimum = int(gate.get("min") or 2)
    return len(dates) >= minimum, [
        f"renewal dates={len(dates)}/{minimum}",
        f"source={gate.get('source')}",
    ], dates


def _waterfall_pass(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    gate = _gate_metric(metrics, "waterfall_requires_negative_closed_lost")
    if not gate:
        return False, ["waterfall sign gate missing"]
    passed = gate.get("pass") is True
    return passed, [
        f"closed-lost sign pass={passed}",
        f"source={gate.get('source')}",
    ]


def _action_register_evidence(metrics: dict[str, Any]) -> list[str]:
    gate = _gate_metric(metrics, "action_register_rejects_generic_gantt")
    if not gate:
        return ["action-date collapse gate missing"]
    return [
        f"action rows={gate.get('rows')}",
        f"same-date ratio={gate.get('most_common_date_ratio')} max={gate.get('max_same_date_ratio')}",
        "keep as table/register; do not force a Gantt when due dates collapse",
    ]


def _has_q2_date(dates: list[str]) -> bool:
    for value in dates:
        try:
            parsed = dt.date.fromisoformat(value[:10])
        except ValueError:
            continue
        if dt.date(2026, 4, 1) <= parsed <= dt.date(2026, 6, 30):
            return True
    return False


def _territory_is_multi_geo(territory: str) -> bool:
    return any(token.lower() in territory.lower() for token in MULTI_GEO_TERRITORY_TOKENS)


def _first_template(contract: dict[str, Any]) -> str:
    candidates = contract.get("donor_candidates") or []
    if not candidates:
        return ""
    first = candidates[0] if isinstance(candidates[0], dict) else {}
    return str(first.get("template") or "")


def _contract_names(decisions: list[VisualDecision], decision: str) -> list[str]:
    return [item.contract for item in decisions if item.decision == decision]


def _base_decision(contract: dict[str, Any], director: str) -> tuple[bool, list[str]]:
    proof_ok = str(contract.get("proof_status") or "") == "pass"
    ready = director in set(contract.get("ready_directors") or [])
    evidence = [
        f"proof_status={contract.get('proof_status')}",
        f"readiness={contract.get('readiness')}",
        f"director_ready={ready}",
    ]
    return proof_ok and ready, evidence


def _decision_for_contract(
    contract: dict[str, Any],
    *,
    director: str,
    territory: str,
    spec: dict[str, Any],
    metrics: dict[str, Any],
) -> VisualDecision:
    name = str(contract["name"])
    priority = str(contract.get("priority") or "")
    lane = str(contract.get("supported_lane") or "")
    fallback = str(contract.get("fallback") or "")
    base_ok, evidence = _base_decision(contract, director)
    reason = "proven contract and director data shape fit"
    decision = "include"

    current = spec.get("current_may_orientation") or {}
    original = spec.get("original_intelligence") or {}
    q2_arr = float(current.get("q2_closeable_land_expand_unweighted_arr_eur") or 0)
    q2_renewal_acv = float(current.get("q2_renewal_acv_eur") or 0)
    q2_q3_renewal_acv = float(original.get("q2_q3_renewal_acv_eur") or 0)
    q2_deal_count = len(spec.get("top_q2_deals") or [])
    action_count = len(spec.get("first_two_week_actions") or [])

    if priority == "P0":
        if not base_ok:
            decision = "fallback"
            reason = "P0 contract is not fully proven for this director"
        elif name in {"QTR01_StageMix_Bar", "QTR02_ForecastMix_Bar", "QTR03_OwnerCoaching_Bar"} and q2_arr <= 0:
            decision = "fallback"
            reason = "no Land+Expand ARR survives the current source filter"
        elif name == "QTR10_ActionDecisionRegister_TableImage":
            evidence.extend(_action_register_evidence(metrics))
            if action_count <= 0:
                decision = "include_statement"
                reason = "no action rows; use a sourced no-action statement"
        elif name == "QTR11_CommercialApprovalGap_TableImage":
            evidence.append(f"missing_stage3={original.get('missing_stage3')}")
            evidence.append(f"top_q2_deals={q2_deal_count}")
            reason = "approval gap lane remains Excel-traceable even when the current gap count is zero"
        elif name == "QTR12_StalePipeline_BarTable":
            evidence.append(f"first_two_week_actions={action_count}")
    elif name == "QTR04_DealRisk_Scatter":
        scatter_ok, scatter_evidence = _scatter_pass(metrics)
        evidence.extend(scatter_evidence)
        if base_ok and scatter_ok and q2_deal_count >= 3:
            decision = "include"
            reason = "deal risk has enough named deals and non-collapsed axes"
        else:
            decision = "fallback"
            reason = "scatter would overstate precision; use ranked named-deal table/bar"
    elif name == "QTR05_FY26RenewalTimeline_Gantt":
        timeline_ok, timeline_evidence, _dates = _timeline_pass(metrics)
        evidence.extend(timeline_evidence)
        evidence.append(f"q2_renewal_acv_eur={q2_renewal_acv}")
        evidence.append(f"q2_q3_renewal_acv_eur={q2_q3_renewal_acv}")
        if base_ok and timeline_ok and (q2_renewal_acv > 0 or q2_q3_renewal_acv > 0):
            decision = "include"
            reason = "renewal ACV has date spread and a separate ACV basis"
        else:
            decision = "fallback"
            reason = "renewal timeline does not clear ACV/date-spread gates"
    elif name == "QTR08_PipelineMovement_Waterfall":
        waterfall_ok, waterfall_evidence = _waterfall_pass(metrics)
        evidence.extend(waterfall_evidence)
        if base_ok and waterfall_ok:
            decision = "candidate"
            reason = "signed movement gate passes; promote only when opening/closing movement is a management question"
        else:
            decision = "fallback"
            reason = "movement bridge sign gate failed or proof missing"
    elif name == "QTR06_Q2RenewalTimeline_Gantt":
        timeline_ok, timeline_evidence, dates = _timeline_pass(metrics)
        evidence.extend(timeline_evidence)
        evidence.append(f"has_q2_date={_has_q2_date(dates)}")
        if base_ok and timeline_ok and _has_q2_date(dates) and q2_renewal_acv > 0:
            decision = "candidate"
            reason = "Q2 renewal timing is useful for this director, but not universal"
        else:
            decision = "suppress"
            reason = "Q2 renewal timeline is not materially justified"
    elif name == "QTR07_StageIndustry_Mekko":
        if base_ok and q2_deal_count >= 8:
            decision = "candidate"
            reason = "possible stage/industry mix, but requires industry-dimension proof before insertion"
        else:
            decision = "suppress"
            reason = "Mekko needs a real two-dimensional decision question"
        evidence.append(f"top_q2_deals={q2_deal_count}")
    elif name == "QTR09_Geography_RankedBar":
        if base_ok and _territory_is_multi_geo(territory):
            decision = "candidate"
            reason = "territory spans geographies; use only when country ranking changes action"
        else:
            decision = "suppress"
            reason = "geography is not the decision variable for this director"
        evidence.append(f"territory={territory}")
    else:
        if not base_ok:
            decision = "fallback"
            reason = "contract proof or director fit missing"

    return VisualDecision(
        contract=name,
        priority=priority,
        family=str(contract.get("family") or ""),
        target=CONTRACT_TARGETS.get(name, "Sales Director visual"),
        lane=lane,
        decision=decision,
        reason=reason,
        evidence=evidence,
        fallback=fallback,
        template=_first_template(contract),
        proof_status=str(contract.get("proof_status") or ""),
        guardrail=str(contract.get("guardrail") or ""),
    )


def _build_one(period: str, director: dict[str, Any], contracts: list[dict[str, Any]]) -> DirectorPlan:
    name = str(director["name"])
    slug = _slug(name)
    territory = str(director["scope_label"])
    root = _director_dir(period, slug)
    regional_spec = root / "factory" / "regional_intelligence_spec.json"
    connected_spec = root / "factory" / "connected" / "connected_factory_spec.json"
    connected_workbook = root / "factory" / "connected" / "connected_factory.xlsx"
    spec = _read_json(regional_spec) if regional_spec.exists() else {}
    visual_blockers, visual_polish, metrics = _visual_gate_findings(connected_spec, connected_workbook)
    decisions = [
        _decision_for_contract(
            contract,
            director=name,
            territory=territory,
            spec=spec,
            metrics=metrics,
        )
        for contract in contracts
    ]
    blockers: list[str] = []
    if not regional_spec.exists():
        blockers.append(f"missing regional intelligence spec: {regional_spec}")
    if not connected_spec.exists():
        blockers.append(f"missing connected factory spec: {connected_spec}")
    if not connected_workbook.exists():
        blockers.append(f"missing connected factory workbook: {connected_workbook}")
    blockers.extend(visual_blockers)
    blockers.extend(visual_polish)
    for required in [
        "QTR01_StageMix_Bar",
        "QTR02_ForecastMix_Bar",
        "QTR03_OwnerCoaching_Bar",
        "QTR10_ActionDecisionRegister_TableImage",
        "QTR11_CommercialApprovalGap_TableImage",
        "QTR12_StalePipeline_BarTable",
    ]:
        match = next((item for item in decisions if item.contract == required), None)
        if not match or match.decision not in {"include", "include_statement"}:
            blockers.append(f"P0 visual contract not included: {required}")

    return DirectorPlan(
        director=name,
        slug=slug,
        territory=territory,
        status="pass" if not blockers else "needs_work",
        blockers=blockers,
        visual_gate_metrics=metrics,
        decisions=decisions,
        artifacts={
            "regional_intelligence_spec": str(regional_spec),
            "connected_factory_spec": str(connected_spec),
            "connected_factory_workbook": str(connected_workbook),
        },
    )


def build_plan(period: str, director_slug: str | None, jobs: int) -> dict[str, Any]:
    blueprint = _read_json(_blueprint_path(period))
    contracts = list(blueprint.get("contracts") or [])
    directors = _selected_directors(director_slug)
    if jobs > 1 and len(directors) > 1:
        with ThreadPoolExecutor(max_workers=min(jobs, len(directors))) as executor:
            plans = list(executor.map(lambda director: _build_one(period, director, contracts), directors))
    else:
        plans = [_build_one(period, director, contracts) for director in directors]

    all_decisions = [decision for plan in plans for decision in plan.decisions]
    summary = {
        "director_count": len(plans),
        "status": "pass" if all(plan.status == "pass" for plan in plans) else "needs_work",
        "include_count": len([item for item in all_decisions if item.decision == "include"]),
        "candidate_count": len([item for item in all_decisions if item.decision == "candidate"]),
        "fallback_count": len([item for item in all_decisions if item.decision == "fallback"]),
        "suppress_count": len([item for item in all_decisions if item.decision == "suppress"]),
        "include_statement_count": len([item for item in all_decisions if item.decision == "include_statement"]),
    }
    return {
        "schema": "sales-director-thinkcell-visual-contract-plan/v1",
        "period": period,
        "created_at_utc": _utc_now(),
        "status": summary["status"],
        "sources": {
            "blueprint": str(_blueprint_path(period)),
            "publish_gate_visual_gate_source": "scripts/run_regional_deck_publish_gate.py::_visual_gate_findings",
        },
        "summary": summary,
        "directors": [
            {
                **{key: value for key, value in asdict(plan).items() if key != "decisions"},
                "decisions": [asdict(decision) for decision in plan.decisions],
                "decision_summary": {
                    "include": _contract_names(plan.decisions, "include"),
                    "candidate": _contract_names(plan.decisions, "candidate"),
                    "fallback": _contract_names(plan.decisions, "fallback"),
                    "suppress": _contract_names(plan.decisions, "suppress"),
                    "include_statement": _contract_names(plan.decisions, "include_statement"),
                },
            }
            for plan in plans
        ],
    }


def _md_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value).replace("\n", " ") for value in values) + " |"


def write_markdown(plan: dict[str, Any], path: Path) -> None:
    lines = [
        "# think-cell Visual Contract Plan",
        "",
        f"Period: `{plan['period']}`",
        f"Status: `{plan['status']}`",
        f"Generated: `{plan['created_at_utc']}`",
        "",
        "## Factory Answer",
        "",
        "The builders are using the template corpus as a governed contract layer. The remaining upgrade is to let this plan drive actual slide insertion for P1/P2 visuals instead of keeping them as manually reviewed candidates.",
        "",
        "## Summary",
        "",
    ]
    for key, value in plan["summary"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Director Decisions",
            "",
            _md_row(["Director", "Status", "Include", "Candidate", "Fallback", "Suppress"]),
            _md_row(["---", "---", "---", "---", "---", "---"]),
        ]
    )
    for director in plan["directors"]:
        summary = director["decision_summary"]
        lines.append(
            _md_row(
                [
                    director["slug"],
                    director["status"],
                    ", ".join(summary["include"] + summary["include_statement"]),
                    ", ".join(summary["candidate"]),
                    ", ".join(summary["fallback"]),
                    ", ".join(summary["suppress"]),
                ]
            )
        )
    lines.extend(["", "## Detail", ""])
    for director in plan["directors"]:
        lines.extend([f"### {director['director']} ({director['territory']})", ""])
        if director["blockers"]:
            lines.extend(f"- blocker: {item}" for item in director["blockers"])
            lines.append("")
        for decision in director["decisions"]:
            evidence = "; ".join(decision["evidence"][:4])
            lines.append(
                f"- `{decision['contract']}` -> `{decision['decision']}`: "
                f"{decision['reason']} ({evidence})"
            )
        lines.append("")
    lines.extend(["## Sources", ""])
    for label, source in plan["sources"].items():
        lines.append(f"- `{label}`: `{source}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_outputs(plan: dict[str, Any], output_dir: Path, docs_copy: Path | None) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "thinkcell_visual_contract_plan.json"
    md_path = output_dir / "thinkcell_visual_contract_plan.md"
    json_path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    write_markdown(plan, md_path)
    if docs_copy:
        write_markdown(plan, docs_copy)
    return json_path, md_path, docs_copy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to state/<period>/__regional__/thinkcell_visual_plan.",
    )
    parser.add_argument(
        "--docs-copy",
        type=Path,
        default=ROOT / "docs" / "thinkcell-corpus" / "deck-factory-visual-plan.md",
        help="Durable markdown copy. Use an empty string to skip.",
    )
    args = parser.parse_args()

    docs_copy = args.docs_copy
    if str(docs_copy) == "":
        docs_copy = None
    output_dir = args.output_dir or ROOT / "state" / args.period / "__regional__" / "thinkcell_visual_plan"
    plan = build_plan(args.period, args.director_slug, args.jobs)
    json_path, md_path, docs_path = write_outputs(plan, output_dir, docs_copy)
    print(f"visual_plan_json={json_path}")
    print(f"visual_plan_md={md_path}")
    if docs_path:
        print(f"docs_copy={docs_path}")
    print(
        "status={status} directors={directors} include={include} candidate={candidate} fallback={fallback}".format(
            status=plan["status"],
            directors=plan["summary"]["director_count"],
            include=plan["summary"]["include_count"] + plan["summary"]["include_statement_count"],
            candidate=plan["summary"]["candidate_count"],
            fallback=plan["summary"]["fallback_count"],
        )
    )
    return 0 if plan["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
