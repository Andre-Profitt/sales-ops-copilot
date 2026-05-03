#!/usr/bin/env python3
"""Build the Sales Director think-cell deck-factory blueprint.

This script collapses the graph/RAG scaffold, template selection map, and latest
`.ppttc` manifest validation into one human and machine readable build plan.
It does not create slides; it defines which proven think-cell contracts should
be used, when they should be used, and which gates must pass before insertion.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"


CONTRACT_ROLES: dict[str, dict[str, str]] = {
    "QTR01_StageMix_Bar": {
        "deck_role": "Stage distribution for open Land/Expand ARR.",
        "production_rule": "Universal P0 chart when at least two stages survive the internal/test filter.",
        "polish_rule": "Horizontal bar or compact column, direct labels, no funnel.",
    },
    "QTR02_ForecastMix_Bar": {
        "deck_role": "Forecast category mix: Commit, Pipeline, Best Case where present.",
        "production_rule": "Universal P0 chart; label ARR as unweighted unless a weighted range is explicitly used.",
        "polish_rule": "Keep categories sparse and label omitted/no-value categories explicitly.",
    },
    "QTR03_OwnerCoaching_Bar": {
        "deck_role": "Owner ranking and coaching focus.",
        "production_rule": "Universal P0 chart paired with named action rows from the table-image lane.",
        "polish_rule": "Use ranking, not decorative scorecards; show owner names only when action follows.",
    },
    "QTR04_DealRisk_Scatter": {
        "deck_role": "Named deal risk inspection map.",
        "production_rule": "P1 conditional chart for directors with ARR and probability/age spread.",
        "polish_rule": "Use only if it points to named deal action; otherwise fall back to ranked table/bar.",
    },
    "QTR05_FY26RenewalTimeline_Gantt": {
        "deck_role": "FY26 Renewal ACV date spread and renewal attention.",
        "production_rule": "P1 conditional chart for Renewal ACV only; never mix Land/Expand ARR.",
        "polish_rule": "Use account names and distinct close dates; fall back to table when dates collapse.",
    },
    "QTR06_Q2RenewalTimeline_Gantt": {
        "deck_role": "Q2 Renewal ACV timing only where May/June dates are meaningful.",
        "production_rule": "P2 selective chart; current fit is Sarah Pittroff, Dan Peppett, and Christian Ebbesen.",
        "polish_rule": "Do not standardize this across all regions.",
    },
    "QTR07_StageIndustry_Mekko": {
        "deck_role": "Stage by industry mix when both dimensions matter.",
        "production_rule": "P2 rare chart; use only for a real two-dimensional claim.",
        "polish_rule": "Avoid if sparse or if exact values matter more than mix.",
    },
    "QTR08_PipelineMovement_Waterfall": {
        "deck_role": "Opening to closing pipeline movement bridge.",
        "production_rule": "P1 chart when the signed movement gate passes; closed-lost/slips must subtract.",
        "polish_rule": "Show only movement categories that explain the month; avoid false precision.",
    },
    "QTR09_Geography_RankedBar": {
        "deck_role": "Country or geography ranking.",
        "production_rule": "P2 chart; use ranked bar by default and only when geography is the decision variable.",
        "polish_rule": "Do not use maps as decoration.",
    },
    "QTR10_ActionDecisionRegister_TableImage": {
        "deck_role": "Action and decision register sourced from Excel rows.",
        "production_rule": "Universal P0 table-image lane; source rows from the validated fact pack/workbook.",
        "polish_rule": "Keep dense but readable; no empty rows, no placeholder subtitles.",
    },
    "QTR11_CommercialApprovalGap_TableImage": {
        "deck_role": "Commercial Approval gaps for Land deals requiring Stage 3 governance.",
        "production_rule": "Universal P0 table-image lane when gaps exist; otherwise show a short no-gap statement.",
        "polish_rule": "Filter to real Land/Expand approval gaps; exclude test/internal rows.",
    },
    "QTR12_StalePipeline_BarTable": {
        "deck_role": "Stale activity summary plus named triage table.",
        "production_rule": "Universal P0 hybrid lane after stale thresholds are computed in Excel.",
        "polish_rule": "Chart summarizes; table names the deals and next action.",
    },
}


@dataclass(frozen=True)
class ContractDirective:
    name: str
    priority: str
    family: str
    deck_role: str
    supported_lane: str
    production_rule: str
    polish_rule: str
    guardrail: str
    fallback: str
    readiness: str
    proof_status: str
    ready_director_count: int
    fallback_director_count: int
    ready_directors: list[str]
    fallback_directors: list[str]
    donor_candidates: list[dict[str, Any]]
    proof_json: str | None
    proof_markdown: str | None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _latest_ppttc_validation(period: str) -> dict[str, Any] | None:
    root = ROOT / "state" / period / "__regional__" / "ppttc_validation"
    candidates = sorted(root.glob("*/ppttc_factory_validation.json"))
    if not candidates:
        return None
    payload = _read_json(candidates[-1])
    return {
        "path": str(candidates[-1]),
        "ok": bool(payload.get("ok")),
        "ppttc_count": payload.get("ppttc_count"),
        "pass_count": payload.get("pass_count"),
        "error_count": payload.get("error_count"),
        "warning_count": payload.get("warning_count"),
        "created_at_utc": payload.get("created_at_utc"),
    }


def _candidate_summary(contract: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slide in contract.get("candidate_slides", [])[:3]:
        rows.append(
            {
                "template": slide.get("template"),
                "slide_number": slide.get("slide_number"),
                "title": slide.get("title"),
                "use_class": slide.get("use_class"),
                "simcorp_fit": slide.get("simcorp_fit"),
                "signals": slide.get("signals", []),
            }
        )
    return rows


def _directive(contract: dict[str, Any]) -> ContractDirective:
    name = str(contract["name"])
    role = CONTRACT_ROLES.get(name, {})
    fit = contract.get("salesforce_fit", {})
    artifacts = contract.get("artifact_scaffold", {})
    return ContractDirective(
        name=name,
        priority=str(contract.get("priority") or ""),
        family=str(contract.get("family") or ""),
        deck_role=role.get("deck_role", "Sales Director operating visual."),
        supported_lane=str(contract.get("supported_lane") or ""),
        production_rule=role.get("production_rule", ""),
        polish_rule=role.get("polish_rule", ""),
        guardrail=str(contract.get("guardrail") or ""),
        fallback=str(contract.get("fallback") or ""),
        readiness=str(contract.get("readiness") or ""),
        proof_status=str(contract.get("proof_status") or ""),
        ready_director_count=len(fit.get("ready_directors") or []),
        fallback_director_count=len(fit.get("fallback_directors") or []),
        ready_directors=list(fit.get("ready_directors") or []),
        fallback_directors=list(fit.get("fallback_directors") or []),
        donor_candidates=_candidate_summary(contract),
        proof_json=artifacts.get("proof_json"),
        proof_markdown=artifacts.get("proof_markdown"),
    )


def build_blueprint(period: str) -> dict[str, Any]:
    scaffold_path = ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "thinkcell_build_scaffold.json"
    selection_path = ROOT / "config" / "thinkcell_template_selection.may_2026.json"
    work_queue_path = ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work_queue.json"
    graph_manifest_path = ROOT / "state" / "thinkcell_bridge" / "knowledge_graph" / "thinkcell_kg_manifest.json"

    scaffold = _read_json(scaffold_path)
    selection = _read_json(selection_path)
    work_queue = _read_json(work_queue_path)
    graph_manifest = _read_json(graph_manifest_path) if graph_manifest_path.exists() else {}

    directives = [_directive(contract) for contract in scaffold["contracts"]]
    priority_order = {"P0": 0, "P1": 1, "P2": 2}
    directives = sorted(directives, key=lambda item: (priority_order.get(item.priority, 9), item.name))

    return {
        "schema": "sales-director-thinkcell-deck-blueprint/v1",
        "created_at_utc": _utc_now(),
        "period": period,
        "sources": {
            "scaffold": str(scaffold_path),
            "template_selection": str(selection_path),
            "work_queue": str(work_queue_path),
            "graph_manifest": str(graph_manifest_path),
        },
        "graph": {
            "node_count": graph_manifest.get("node_count"),
            "edge_count": graph_manifest.get("edge_count"),
            "rag_doc_count": graph_manifest.get("rag_doc_count"),
        },
        "ppttc_validation": _latest_ppttc_validation(period),
        "policy": {
            "P0": "Default deck spine. Use for every director when the fact-pack data shape is non-empty.",
            "P1": "Promote selectively when it improves a named leadership decision and the visual gate passes.",
            "P2": "Use sparingly. Require explicit data-shape fit and a clear decision question.",
            "tables": "Use Excel COM AddRangeImage table-image lane. Native editable think-cell tables remain blocked.",
            "charts": "Use named think-cell donor/seed objects updated by .ppttc. Do not create missing charts at runtime.",
        },
        "gates": [
            "Internal/test row filter applied before workbook and chart payload generation.",
            "ARR visuals use Type IN ('Land','Expand') and APTS_Opportunity_ARR__c.",
            "Renewal visuals use Type = 'Renewal' and APTS_Renewal_ACV__c.",
            "Headline currency basis is converted EUR, not raw multi-currency SOQL sums.",
            "Named element exists in the seed or donor before .ppttc binding.",
            "Strict .ppttc expected-name validation passes.",
            "L5 proof JSON exists and reports pass for the contract lane.",
            "Rendered PPTX opens without repair, is nonblank, and has no overlap/placeholder/error text.",
            "Regional publish gate passes before SharePoint packaging.",
        ],
        "template_families": selection.get("selected_families", []),
        "contracts": [asdict(item) for item in directives],
        "work_queue": {
            "contract_count": work_queue.get("contract_count"),
            "job_count": work_queue.get("job_count"),
            "protect_jobs": len([job for job in work_queue.get("jobs", []) if job.get("lane") == "protect_proven_lane"]),
        },
        "next_build_order": [
            "Lock P0 universal spine into the regional deck builder first: QTR01, QTR02, QTR03, QTR10, QTR11, QTR12.",
            "Promote QTR08 waterfall only behind the signed movement gate.",
            "Pilot QTR04 scatter and QTR05 FY26 renewal Gantt on one high-fit director, then batch eligible directors.",
            "Keep QTR06, QTR07, and QTR09 conditional until the fact-pack explicitly justifies them.",
            "Keep dense deal tables traceable to Excel; do not chase native editable think-cell tables for this cycle.",
        ],
    }


def _md_table_row(values: list[Any]) -> str:
    return "| " + " | ".join(str(value).replace("\n", " ") for value in values) + " |"


def write_markdown(blueprint: dict[str, Any], path: Path) -> None:
    validation = blueprint.get("ppttc_validation") or {}
    lines = [
        "# Sales Director think-cell Deck Factory Blueprint",
        "",
        f"Period: `{blueprint['period']}`",
        f"Generated: `{blueprint['created_at_utc']}`",
        "",
        "## Operating Decision",
        "",
        "Use think-cell as a controlled update layer, not a runtime chart factory. Charts must come from named donor/seed objects and bind through `.ppttc`; dense tables stay on the Excel COM `AddRangeImage` table-image lane until native tables are proven clean.",
        "",
        "## Current Proof State",
        "",
        f"- Contracts: `{len(blueprint['contracts'])}`",
        f"- Work queue jobs: `{blueprint['work_queue']['job_count']}`",
        f"- Protect-lane jobs: `{blueprint['work_queue']['protect_jobs']}`",
        f"- Latest `.ppttc` gate: `{'pass' if validation.get('ok') else 'missing_or_fail'}`"
        f" ({validation.get('pass_count', 'n/a')}/{validation.get('ppttc_count', 'n/a')} passing)",
        "",
        "## Build Policy",
        "",
    ]
    for key in ["P0", "P1", "P2", "charts", "tables"]:
        lines.append(f"- `{key}`: {blueprint['policy'][key]}")

    lines.extend(
        [
            "",
            "## Contract Map",
            "",
            _md_table_row(
                [
                    "Contract",
                    "Priority",
                    "Lane",
                    "Ready directors",
                    "Fallbacks",
                    "Deck role",
                    "Production rule",
                ]
            ),
            _md_table_row(["---", "---:", "---", "---:", "---:", "---", "---"]),
        ]
    )
    for contract in blueprint["contracts"]:
        lines.append(
            _md_table_row(
                [
                    contract["name"],
                    contract["priority"],
                    contract["supported_lane"],
                    contract["ready_director_count"],
                    contract["fallback_director_count"],
                    contract["deck_role"],
                    contract["production_rule"],
                ]
            )
        )

    lines.extend(["", "## Required Gates", ""])
    lines.extend(f"- {gate}" for gate in blueprint["gates"])
    lines.extend(["", "## Next Build Order", ""])
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(blueprint["next_build_order"], start=1))
    lines.extend(["", "## Sources", ""])
    for label, source in blueprint["sources"].items():
        lines.append(f"- `{label}`: `{source}`")
    if validation.get("path"):
        lines.append(f"- `ppttc_validation`: `{validation['path']}`")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_blueprint(blueprint: dict[str, Any], output_dir: Path, docs_copy: Path | None) -> tuple[Path, Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "thinkcell_deck_factory_blueprint.json"
    md_path = output_dir / "thinkcell_deck_factory_blueprint.md"
    json_path.write_text(json.dumps(blueprint, indent=2) + "\n", encoding="utf-8")
    write_markdown(blueprint, md_path)
    if docs_copy:
        write_markdown(blueprint, docs_copy)
    return json_path, md_path, docs_copy


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to state/<period>/__regional__/thinkcell_deck_blueprint.",
    )
    parser.add_argument(
        "--docs-copy",
        type=Path,
        default=ROOT / "docs" / "thinkcell-corpus" / "deck-factory-blueprint.md",
        help="Durable markdown copy. Use an empty string to skip.",
    )
    args = parser.parse_args()

    docs_copy = args.docs_copy
    if str(docs_copy) == "":
        docs_copy = None
    output_dir = args.output_dir or ROOT / "state" / args.period / "__regional__" / "thinkcell_deck_blueprint"
    blueprint = build_blueprint(args.period)
    json_path, md_path, docs_path = write_blueprint(blueprint, output_dir, docs_copy)
    print(f"blueprint_json={json_path}")
    print(f"blueprint_md={md_path}")
    if docs_path:
        print(f"docs_copy={docs_path}")
    print(
        "contracts={contracts} ppttc_gate={gate}".format(
            contracts=len(blueprint["contracts"]),
            gate="pass" if (blueprint.get("ppttc_validation") or {}).get("ok") else "missing_or_fail",
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
