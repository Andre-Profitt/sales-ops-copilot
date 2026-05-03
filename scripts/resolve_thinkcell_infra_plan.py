#!/usr/bin/env python3
"""Resolve think-cell visual decisions through the capability registry.

This is a dry infra resolver. It does not open Office, call the Windows VM,
modify decks, or publish artifacts. It joins:

* the per-director visual contract plan,
* the build scaffold and proof metadata,
* the think-cell infra capability map,
* and an optional insertion-pilot candidate manifest.

The output tells the deck builder what is safe to use as-is, what needs a
promotion decision record, and what must remain fallback/suppressed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _visual_plan_path(repo_root: Path, period: str) -> Path:
    return (
        repo_root
        / "state"
        / period
        / "__regional__"
        / "thinkcell_visual_plan"
        / "thinkcell_visual_contract_plan.json"
    )


def _scaffold_path(repo_root: Path, period: str) -> Path:
    return (
        repo_root
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "thinkcell_build_scaffold.json"
    )


def _capability_map_path(repo_root: Path) -> Path:
    return repo_root / "docs" / "thinkcell-corpus" / "thinkcell_infra_capability_map.json"


def _output_path(repo_root: Path, period: str, director_slug: str) -> Path:
    return (
        repo_root
        / "state"
        / period
        / director_slug
        / "factory"
        / "meeting-spine"
        / "thinkcell_infra_resolution.json"
    )


def _director_from_visual_plan(visual_plan: dict[str, Any], director_slug: str) -> dict[str, Any]:
    for director in visual_plan.get("directors", []):
        if director.get("slug") == director_slug:
            return director
    raise KeyError(f"director slug not found in visual plan: {director_slug}")


def _contracts_by_name(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(contract.get("name")): contract
        for contract in scaffold.get("contracts", [])
        if contract.get("name")
    }


def _capability_statuses(capability_map: dict[str, Any]) -> dict[str, str]:
    return {
        str(capability.get("id")): str(capability.get("status"))
        for capability in capability_map.get("capabilities", [])
        if capability.get("id")
    }


def _candidate_by_contract(candidate_manifest: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not candidate_manifest:
        return {}
    return {
        str(contract.get("contract_id")): contract
        for contract in candidate_manifest.get("contracts", [])
        if contract.get("contract_id")
    }


def _lane_family(lane: str, family: str) -> str:
    text = f"{lane} {family}".casefold()
    if "table-image" in text or "addrangeimage" in text:
        return "table_image"
    if "native think-cell" in text or "ppttc" in text or "seed" in text:
        return "native_chart"
    return "unknown"


def _required_capabilities(lane_family: str) -> list[str]:
    if lane_family == "table_image":
        return ["excel_com_updatebatch", "table_image_donor", "python_orchestration"]
    if lane_family == "native_chart":
        return ["ppttc_windows_bridge", "named_donor_seed_patching", "python_orchestration"]
    return ["python_orchestration"]


def _capabilities_ok(required: list[str], statuses: dict[str, str]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for capability_id in required:
        status = statuses.get(capability_id)
        if status != "production":
            failures.append(f"{capability_id} status is {status or 'missing'}")
    return not failures, failures


def _proof_path(repo_root: Path, period: str, contract_id: str) -> Path:
    return (
        repo_root
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "work"
        / contract_id
        / f"{contract_id}-proof.json"
    )


def _proof_summary(repo_root: Path, period: str, contract_id: str) -> dict[str, Any]:
    path = _proof_path(repo_root, period, contract_id)
    if not path.exists():
        return {"proof_json": str(path), "exists": False, "status": "missing"}
    proof = _read_json(path)
    return {
        "proof_json": str(path),
        "exists": True,
        "status": proof.get("status"),
        "deck": proof.get("deck"),
        "seed_pptx": proof.get("seed_pptx"),
        "ppttc": proof.get("ppttc"),
        "render_dir": proof.get("render_dir"),
    }


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    return {
        "status": candidate.get("status"),
        "publishable": candidate.get("publishable", False),
        "candidate_path": candidate.get("candidate_path")
        or candidate.get("intended_candidate_output_path"),
        "candidate_validation": candidate.get("candidate_validation"),
        "source_artifacts": candidate.get("source_artifacts"),
    }


def _assembly_action(
    *,
    decision: str,
    priority: str,
    lane_family: str,
    capability_ok: bool,
    l5_ok: bool,
    proof: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> str:
    if decision == "suppress":
        return "suppress"
    if decision == "fallback":
        return "use_fallback_existing_spine"
    if not capability_ok:
        return "blocked_by_capability"
    if not l5_ok or proof.get("status") != "pass":
        return "blocked_by_proof"
    if decision == "candidate":
        return "hold_candidate_pending_management_question"
    if lane_family == "table_image":
        return "use_existing_table_image_linked_spine"
    if priority == "P0":
        return "use_existing_linked_spine"
    if candidate and candidate.get("status") == "candidate_created":
        return "requires_promotion_decision"
    return "build_candidate_before_promotion"


def resolve_director(
    *,
    repo_root: Path,
    period: str,
    director_slug: str,
    capability_map_path: Path | None = None,
    visual_plan_path: Path | None = None,
    scaffold_path: Path | None = None,
    candidate_manifest_path: Path | None = None,
) -> dict[str, Any]:
    capability_map = _read_json(capability_map_path or _capability_map_path(repo_root))
    visual_plan = _read_json(visual_plan_path or _visual_plan_path(repo_root, period))
    scaffold = _read_json(scaffold_path or _scaffold_path(repo_root, period))
    candidate_manifest = (
        _read_json(candidate_manifest_path)
        if candidate_manifest_path and candidate_manifest_path.exists()
        else None
    )

    director = _director_from_visual_plan(visual_plan, director_slug)
    contracts = _contracts_by_name(scaffold)
    statuses = _capability_statuses(capability_map)
    candidates = _candidate_by_contract(candidate_manifest)
    decisions: list[dict[str, Any]] = []

    for item in director.get("decisions", []):
        contract_id = str(item.get("contract"))
        scaffold_contract = contracts.get(contract_id, {})
        lane = str(item.get("lane") or scaffold_contract.get("supported_lane") or "")
        family = str(item.get("family") or scaffold_contract.get("family") or "")
        priority = str(item.get("priority") or scaffold_contract.get("priority") or "")
        lane_family = _lane_family(lane, family)
        required = _required_capabilities(lane_family)
        capability_ok, capability_failures = _capabilities_ok(required, statuses)
        l5_ok = (
            scaffold_contract.get("readiness") == "l5_proven"
            and scaffold_contract.get("proof_status") == "pass"
        )
        proof = _proof_summary(repo_root, period, contract_id)
        candidate = _candidate_summary(candidates.get(contract_id))
        action = _assembly_action(
            decision=str(item.get("decision")),
            priority=priority,
            lane_family=lane_family,
            capability_ok=capability_ok,
            l5_ok=l5_ok,
            proof=proof,
            candidate=candidate,
        )
        decisions.append(
            {
                "contract_id": contract_id,
                "priority": priority,
                "visual_decision": item.get("decision"),
                "assembly_action": action,
                "lane": lane,
                "lane_family": lane_family,
                "required_capabilities": required,
                "capability_ok": capability_ok,
                "capability_failures": capability_failures,
                "l5_ok": l5_ok,
                "proof": proof,
                "candidate": candidate,
                "guardrail": item.get("guardrail"),
                "reason": item.get("reason"),
            }
        )

    blockers = [
        {
            "contract_id": decision["contract_id"],
            "assembly_action": decision["assembly_action"],
            "capability_failures": decision["capability_failures"],
        }
        for decision in decisions
        if str(decision["assembly_action"]).startswith("blocked")
    ]
    promotion_required = [
        decision["contract_id"]
        for decision in decisions
        if decision["assembly_action"] == "requires_promotion_decision"
    ]

    return {
        "schema": "simcorp-thinkcell-infra-resolution/v1",
        "created_at_utc": _utc_now(),
        "period": period,
        "director": director.get("director"),
        "director_slug": director_slug,
        "status": "blocked" if blockers else "pass",
        "publishable": False,
        "sources": {
            "capability_map": str(capability_map_path or _capability_map_path(repo_root)),
            "visual_plan": str(visual_plan_path or _visual_plan_path(repo_root, period)),
            "scaffold": str(scaffold_path or _scaffold_path(repo_root, period)),
            "candidate_manifest": str(candidate_manifest_path) if candidate_manifest_path else None,
        },
        "summary": {
            "decision_count": len(decisions),
            "blocked_count": len(blockers),
            "promotion_required_count": len(promotion_required),
            "promotion_required_contracts": promotion_required,
        },
        "blockers": blockers,
        "decisions": decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug", default="Jesper-Tyrer")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--capability-map", type=Path)
    parser.add_argument("--visual-plan", type=Path)
    parser.add_argument("--scaffold", type=Path)
    parser.add_argument("--candidate-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write", action="store_true", help="Write JSON resolution to disk.")
    args = parser.parse_args()

    result = resolve_director(
        repo_root=args.repo_root,
        period=args.period,
        director_slug=args.director_slug,
        capability_map_path=args.capability_map,
        visual_plan_path=args.visual_plan,
        scaffold_path=args.scaffold,
        candidate_manifest_path=args.candidate_manifest,
    )

    if args.write:
        output = args.output or _output_path(args.repo_root, args.period, args.director_slug)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"wrote={output}")

    summary = result["summary"]
    print(
        "status={status} director={director} decisions={decisions} "
        "promotion_required={promotion_required} blocked={blocked}".format(
            status=result["status"],
            director=args.director_slug,
            decisions=summary["decision_count"],
            promotion_required=summary["promotion_required_count"],
            blocked=summary["blocked_count"],
        )
    )
    if summary["promotion_required_contracts"]:
        print("promotion_required_contracts=" + ",".join(summary["promotion_required_contracts"]))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
