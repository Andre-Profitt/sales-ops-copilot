#!/usr/bin/env python3
"""Generate the think-cell contract work queue from the build scaffold."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_OUTPUT_ROOT = ROOT / "state" / "thinkcell_bridge" / "build_scaffold"

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2}


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing scaffold: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _default_scaffold(period: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / period / "thinkcell_build_scaffold.json"


def _default_output_dir(period: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / period


def _is_table_image(contract: dict[str, Any]) -> bool:
    name = str(contract.get("name", "")).lower()
    family = str(contract.get("family", "")).lower()
    lane = str(contract.get("supported_lane", "")).lower()
    return name.endswith("_tableimage") or family == "table_image" or "addrangeimage" in lane


def _is_hybrid(contract: dict[str, Any]) -> bool:
    text = f"{contract.get('family', '')} {contract.get('supported_lane', '')} {contract.get('fallback', '')}".lower()
    return "bar_table" in text or ("native think-cell" in text and "table-image" in text)


def _is_proven(contract: dict[str, Any]) -> bool:
    return contract.get("readiness") == "l5_proven" and contract.get("proof_status") == "pass"


def _contract_sort_key(contract: dict[str, Any]) -> tuple[int, int, str]:
    if _is_table_image(contract) and _is_proven(contract):
        lane_rank = 0
    elif _is_proven(contract):
        lane_rank = 1
    else:
        lane_rank = 2
    priority_rank = PRIORITY_RANK.get(str(contract.get("priority", "P9")), 9)
    return (lane_rank, priority_rank, str(contract["name"]))


def _level(contract: dict[str, Any], level: str) -> dict[str, Any]:
    for item in contract.get("levels", []):
        if item.get("level") == level:
            return item
    return {}


def _base_inputs(scaffold: dict[str, Any], contract: dict[str, Any], period: str) -> list[str]:
    inputs = scaffold.get("inputs", {})
    values = [
        str(Path("state/thinkcell_bridge/build_scaffold") / period / "thinkcell_build_scaffold.json"),
        str(Path("state/thinkcell_bridge/build_scaffold") / period / "contracts" / f"{contract['name']}.md"),
    ]
    for key in ("quarter_seed_spec", "knowledge_graph_manifest", "slide_corpus", "programmatic_lab"):
        if inputs.get(key):
            values.append(str(inputs[key]))
    return values


def _seed_outputs(contract: dict[str, Any], period: str) -> list[str]:
    work_dir = Path("state/thinkcell_bridge/build_scaffold") / period / "work" / contract["name"]
    return [
        str(work_dir / f"{contract['name']}-seed.pptx"),
        str(work_dir / f"{contract['name']}-{period}.ppttc"),
    ]


def _proof_outputs(contract: dict[str, Any], period: str) -> list[str]:
    work_dir = Path("state/thinkcell_bridge/build_scaffold") / period / "work" / contract["name"]
    return [
        str(work_dir / f"{contract['name']}-{period}-bound.pptx"),
        str(work_dir / f"{contract['name']}-proof.json"),
        str(work_dir / f"{contract['name']}-proof.md"),
    ]


def _protect_outputs(contract: dict[str, Any], period: str) -> list[str]:
    work_dir = Path("state/thinkcell_bridge/build_scaffold") / period / "work" / contract["name"]
    return [
        str(work_dir / f"{contract['name']}-proof.json"),
        str(work_dir / f"{contract['name']}-proof.md"),
    ]


def _seed_gates(contract: dict[str, Any]) -> list[str]:
    gates = [
        _level(contract, "L1").get("gate", "Contract keeps Salesforce fit and ARR/ACV guardrails."),
        _level(contract, "L3").get("gate", "Donor evidence is selected from the scaffold."),
        _level(contract, "L4").get("gate", "Seed PPTX contains expected names before binding."),
    ]
    if _is_hybrid(contract):
        gates.append("Hybrid lane must preserve table-image named-deal fallback for deal detail rows.")
    return gates


def _proof_gates(contract: dict[str, Any]) -> list[str]:
    gates = [
        _level(contract, "L5").get(
            "gate",
            "Bound output renders and contains expected values/text, not only ppttc exit code 0.",
        )
    ]
    if _is_hybrid(contract):
        gates.append("If native bar binding passes but named deals are weak, retain table-image named-deal fallback.")
    return gates


def _stop_conditions(contract: dict[str, Any]) -> list[str]:
    stops = [
        "Stop before production deck insertion unless L5 proof is pass.",
        "Stop if proof output is based only on ppttc exit code without rendered value/text evidence.",
    ]
    guardrail = contract.get("guardrail")
    if guardrail:
        stops.append(f"Stop if data violates guardrail: {guardrail}")
    fallback = contract.get("fallback")
    if fallback:
        stops.append(f"Use documented fallback instead of improvising: {fallback}")
    return stops


def _protect_job(scaffold: dict[str, Any], contract: dict[str, Any], period: str, index: int) -> dict[str, Any]:
    return {
        "job_id": f"{period}.{index:03d}.{contract['name']}.protect_proven_lane",
        "contract": contract["name"],
        "role": "QA Gatekeeper",
        "priority": contract.get("priority", "P0"),
        "lane": "protect_proven_lane",
        "readiness": contract.get("readiness", "unknown"),
        "proof_status": contract.get("proof_status", "unknown"),
        "dependencies": [],
        "inputs": _base_inputs(scaffold, contract, period) + _protect_outputs(contract, period),
        "outputs": _protect_outputs(contract, period),
        "gates": [
            "Existing L5 proof remains attached and pass.",
            "Reference/protect lane is not overwritten while authoring unproven contracts.",
            _level(contract, "L5").get("gate", "Rendered proof checks values/text."),
        ],
        "stop_conditions": _stop_conditions(contract),
        "status": "planned",
    }


def _seed_job(scaffold: dict[str, Any], contract: dict[str, Any], period: str, index: int) -> dict[str, Any]:
    return {
        "job_id": f"{period}.{index:03d}.{contract['name']}.seed_authoring",
        "contract": contract["name"],
        "role": "Think-cell Seedsmith",
        "priority": contract.get("priority", "P9"),
        "lane": "L4 seed_authoring",
        "readiness": contract.get("readiness", "unknown"),
        "proof_status": contract.get("proof_status", "unknown"),
        "dependencies": [],
        "inputs": _base_inputs(scaffold, contract, period),
        "outputs": _seed_outputs(contract, period),
        "gates": _seed_gates(contract),
        "stop_conditions": _stop_conditions(contract),
        "status": "planned",
    }


def _proof_job(
    scaffold: dict[str, Any],
    contract: dict[str, Any],
    period: str,
    index: int,
    seed_job_id: str,
) -> dict[str, Any]:
    return {
        "job_id": f"{period}.{index:03d}.{contract['name']}.binding_proof",
        "contract": contract["name"],
        "role": "Binding Engineer",
        "priority": contract.get("priority", "P9"),
        "lane": "L5 binding_proof",
        "readiness": contract.get("readiness", "unknown"),
        "proof_status": contract.get("proof_status", "unknown"),
        "dependencies": [seed_job_id],
        "inputs": _base_inputs(scaffold, contract, period) + _seed_outputs(contract, period),
        "outputs": _proof_outputs(contract, period),
        "gates": _proof_gates(contract),
        "stop_conditions": _stop_conditions(contract),
        "status": "planned",
    }


def build_queue(scaffold: dict[str, Any], period: str) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    contracts = sorted(scaffold.get("contracts", []), key=_contract_sort_key)
    job_index = 1
    for contract in contracts:
        if _is_proven(contract):
            jobs.append(_protect_job(scaffold, contract, period, job_index))
            job_index += 1
            continue
        if contract.get("readiness") == "ready_for_named_seed_authoring" and not _is_table_image(contract):
            seed = _seed_job(scaffold, contract, period, job_index)
            jobs.append(seed)
            job_index += 1
            jobs.append(_proof_job(scaffold, contract, period, job_index, seed["job_id"]))
            job_index += 1
            continue
        jobs.append(_protect_job(scaffold, contract, period, job_index))
        job_index += 1
    return {
        "schema": "thinkcell-work-queue/v1",
        "created_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "period": period,
        "source_scaffold": str(_default_scaffold(period)),
        "contract_count": len(contracts),
        "job_count": len(jobs),
        "jobs": jobs,
    }


def _markdown(queue: dict[str, Any]) -> str:
    jobs = queue["jobs"]
    roles = Counter(job["role"] for job in jobs)
    statuses = Counter(job["status"] for job in jobs)
    lines = [
        f"# think-cell Work Queue - {queue['period']}",
        "",
        f"- Contracts: {queue['contract_count']}",
        f"- Jobs: {queue['job_count']}",
        "",
        "## Counts by Role",
        "",
    ]
    for role, count in sorted(roles.items()):
        lines.append(f"- {role}: {count}")
    lines.extend(["", "## Counts by Status", ""])
    for status, count in sorted(statuses.items()):
        lines.append(f"- {status}: {count}")
    lines.extend(["", "## First 10 Jobs", ""])
    lines.append("| # | Job ID | Contract | Role | Priority | Lane | Status |")
    lines.append("|---:|---|---|---|---|---|---|")
    for idx, job in enumerate(jobs[:10], 1):
        lines.append(
            "| {idx} | {job_id} | {contract} | {role} | {priority} | {lane} | {status} |".format(
                idx=idx,
                job_id=job["job_id"],
                contract=job["contract"],
                role=job["role"],
                priority=job["priority"],
                lane=job["lane"],
                status=job["status"],
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--scaffold", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    scaffold_path = args.scaffold or _default_scaffold(args.period)
    output_dir = args.output_dir or _default_output_dir(args.period)
    scaffold = _load_json(scaffold_path)
    queue = build_queue(scaffold, args.period)
    queue["source_scaffold"] = str(scaffold_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "work_queue.json"
    md_path = output_dir / "work_queue.md"
    json_path.write_text(json.dumps(queue, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(queue), encoding="utf-8")
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"contracts={queue['contract_count']} jobs={queue['job_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
