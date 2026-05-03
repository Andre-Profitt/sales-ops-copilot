#!/usr/bin/env python3
"""Think-cell insertion pilot harness.

This command never calls PowerPoint, Office, the Windows VM, or SharePoint
itself. It runs in two read/plan modes:

* ``--plan-only``: verifies that requested think-cell quarter contracts are
  L5-proven, checks director eligibility/fallback rules, runs deterministic
  deep preflight (proof PPTX + seed PPTX zip readability, ppttc JSON parse),
  emits a manifest plus a runnable ``vm_insertion_commands.sh`` and a
  ``MANUAL_POWERPOINT_STEPS.md`` for an operator to execute on the Windows VM
  bridge or by hand on a Mac/Windows PowerPoint with think-cell installed.
* ``--promote``: reads the existing run manifest, looks for actual
  VM-produced or manually-produced candidate PPTX files at the intended
  output paths, validates them (zip readable, slides present, no native
  PowerPoint tables), and updates per-contract statuses to
  ``candidate_created`` / ``awaiting_vm_insertion`` / ``candidate_invalid``.
  Always preserves ``publishable: false``.

All outputs are written under
``state/<period>/__regional__/thinkcell_insertion_pilot/<run_id>/``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shlex
import stat
import sys
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from period_context import context_for_period
except ModuleNotFoundError:  # pragma: no cover - package import fallback
    from scripts.period_context import context_for_period


# ---------------------------------------------------------------------------
# Status vocabulary
#
# Overall manifest statuses (4 disjoint values from the W10 mission):
#   planned                          - reserved for legacy/partial runs
#   ready_for_vm_or_manual_insertion - deep preflight green; VM/manual cmds emitted
#   candidate_created                - promote run validated all candidate PPTX files
#   blocked                          - any contract blocked or any validation failed
#
# Per-contract statuses are richer to surface the precise reason:
#   unknown_contract, unknown_director, not_eligible_director_fallback,
#   not_l5_proven, missing_proof_artifact, preflight_failed,
#   ready_for_vm_or_manual_insertion, awaiting_vm_insertion,
#   candidate_created, candidate_invalid
# ---------------------------------------------------------------------------

OVERALL_PLANNED = "planned"
OVERALL_READY = "ready_for_vm_or_manual_insertion"
OVERALL_CANDIDATE_CREATED = "candidate_created"
OVERALL_BLOCKED = "blocked"

STATUS_READY = "ready_for_vm_or_manual_insertion"
STATUS_AWAITING = "awaiting_vm_insertion"
STATUS_CANDIDATE_CREATED = "candidate_created"
STATUS_CANDIDATE_INVALID = "candidate_invalid"
STATUS_PREFLIGHT_FAILED = "preflight_failed"


FALLBACK_RULES: dict[str, dict[str, Any]] = {
    "QTR04_DealRisk_Scatter": {
        "fallback_directors": ["Patrick Gaughan"],
        "fallback_lane": "ranked risk table when probability or ARR has no spread",
    },
    "QTR05_FY26RenewalTimeline_Gantt": {
        "fallback_directors": ["Adam Steinhouse"],
        "fallback_lane": "renewal watchlist table",
    },
    "QTR06_Q2RenewalTimeline_Gantt": {
        "ready_directors": ["Sarah Pittroff", "Dan Peppett", "Christian Ebbesen"],
        "fallback_lane": "renewal watchlist table",
    },
}


# ARR/ACV axis guardrails per pilot contract.  These mirror the cardinal SimCorp
# rules: ARR is Land+Expand only via APTS_Opportunity_ARR__c; Renewal ACV is
# Renewal-only via APTS_Renewal_ACV__c; never blend; always set explicit Type
# filter; headline currency is FX-converted EUR via Salesforce report aggregates
# (s!field), not raw multi-currency SOQL SUM.
ARR_ACV_AXIS: dict[str, dict[str, str]] = {
    "QTR04_DealRisk_Scatter": {
        "axis": "ARR",
        "salesforce_field": "APTS_Opportunity_ARR__c",
        "report_aggregate": "s!APTS_Opportunity_ARR_c",
        "type_filter": "Type IN ('Land','Expand')",
        "must_not_blend_with": "Renewal ACV",
    },
    "QTR05_FY26RenewalTimeline_Gantt": {
        "axis": "Renewal ACV",
        "salesforce_field": "APTS_Renewal_ACV__c",
        "report_aggregate": "s!APTS_Renewal_ACV_c",
        "type_filter": "Type = 'Renewal'",
        "must_not_blend_with": "ARR",
    },
    "QTR06_Q2RenewalTimeline_Gantt": {
        "axis": "Renewal ACV",
        "salesforce_field": "APTS_Renewal_ACV__c",
        "report_aggregate": "s!APTS_Renewal_ACV_c",
        "type_filter": "Type = 'Renewal'",
        "must_not_blend_with": "ARR",
    },
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def slug_for_director(name: str) -> str:
    return name.replace(" ", "-")


def name_for_slug(slug: str) -> str:
    return slug.replace("-", " ")


def scaffold_path(repo_root: Path, period: str) -> Path:
    return (
        repo_root
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "thinkcell_build_scaffold.json"
    )


def load_scaffold(repo_root: Path, period: str) -> dict[str, Any]:
    path = scaffold_path(repo_root, period)
    if not path.exists():
        raise FileNotFoundError(f"scaffold not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def find_contract(scaffold: dict[str, Any], contract_id: str) -> dict[str, Any] | None:
    for contract in scaffold.get("contracts", []):
        if contract.get("name") == contract_id:
            return contract
    return None


def is_l5_proven_pass(contract: dict[str, Any]) -> bool:
    return contract.get("readiness") == "l5_proven" and contract.get("proof_status") == "pass"


def eligibility_for(contract: dict[str, Any], director_name: str) -> dict[str, Any]:
    fit = contract.get("salesforce_fit") or {}
    ready = list(fit.get("ready_directors") or [])
    fallback = list(fit.get("fallback_directors") or [])
    fallback_lane = str(contract.get("fallback") or "table fallback")
    name = str(contract.get("name") or "")

    if name == "QTR04_DealRisk_Scatter" and director_name == "Patrick Gaughan":
        fallback_lane = FALLBACK_RULES[name]["fallback_lane"]
    if name == "QTR05_FY26RenewalTimeline_Gantt" and director_name == "Adam Steinhouse":
        fallback_lane = FALLBACK_RULES[name]["fallback_lane"]
    if name == "QTR06_Q2RenewalTimeline_Gantt":
        ready = FALLBACK_RULES[name]["ready_directors"]
        if director_name not in ready and director_name not in fallback:
            fallback.append(director_name)
        fallback_lane = FALLBACK_RULES[name]["fallback_lane"]

    if director_name in ready:
        decision = "ready"
    elif director_name in fallback:
        decision = "fallback"
    else:
        decision = "unknown"

    return {
        "decision": decision,
        "director": director_name,
        "fallback_lane": fallback_lane,
        "all_ready_directors": ready,
        "all_fallback_directors": fallback,
    }


def check_baked_eligibility_rules(scaffold: dict[str, Any]) -> list[str]:
    discrepancies: list[str] = []

    qtr04 = find_contract(scaffold, "QTR04_DealRisk_Scatter")
    if qtr04:
        if eligibility_for(qtr04, "Patrick Gaughan")["decision"] != "fallback":
            discrepancies.append("Patrick Gaughan must fallback for QTR04_DealRisk_Scatter")
    else:
        discrepancies.append("QTR04_DealRisk_Scatter missing from scaffold")

    qtr05 = find_contract(scaffold, "QTR05_FY26RenewalTimeline_Gantt")
    if qtr05:
        if eligibility_for(qtr05, "Adam Steinhouse")["decision"] != "fallback":
            discrepancies.append(
                "Adam Steinhouse must fallback for QTR05_FY26RenewalTimeline_Gantt"
            )
    else:
        discrepancies.append("QTR05_FY26RenewalTimeline_Gantt missing from scaffold")

    qtr06 = find_contract(scaffold, "QTR06_Q2RenewalTimeline_Gantt")
    if qtr06:
        allowed = set(FALLBACK_RULES["QTR06_Q2RenewalTimeline_Gantt"]["ready_directors"])
        ready = set((qtr06.get("salesforce_fit") or {}).get("ready_directors") or [])
        if ready != allowed:
            discrepancies.append(
                "QTR06_Q2RenewalTimeline_Gantt ready directors must be "
                + ", ".join(sorted(allowed))
            )
    else:
        discrepancies.append("QTR06_Q2RenewalTimeline_Gantt missing from scaffold")

    return discrepancies


def proof_path(repo_root: Path, period: str, contract_id: str) -> Path:
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


def load_proof_for_contract(
    repo_root: Path, period: str, contract_id: str
) -> dict[str, Any] | None:
    path = proof_path(repo_root, period, contract_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def intended_candidate_output_path(
    repo_root: Path,
    period: str,
    director_slug: str,
    contract_id: str,
    *,
    run_id: str,
) -> Path:
    return (
        repo_root
        / "state"
        / period
        / "__regional__"
        / "thinkcell_insertion_pilot"
        / run_id
        / director_slug
        / contract_id
        / f"{director_slug}-{contract_id}-candidate.pptx"
    )


def _source_artifacts(
    repo_root: Path, period: str, contract_id: str, proof: dict[str, Any]
) -> dict[str, str]:
    items = {
        "proof_json": str(proof_path(repo_root, period, contract_id)),
        "bound_deck": proof.get("deck"),
        "ppttc": proof.get("ppttc"),
        "seed_pptx": proof.get("seed_pptx"),
        "render_dir": proof.get("render_dir"),
    }
    return {key: str(value) for key, value in items.items() if value}


def _bound_required_terms(proof: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for target in proof.get("targets") or []:
        for term in target.get("bound_required_terms") or []:
            if isinstance(term, str) and term and term not in terms:
                terms.append(term)
    return terms


def _artifacts_exist(artifacts: dict[str, str]) -> bool:
    return all(Path(path).exists() for path in artifacts.values())


# ---------------------------------------------------------------------------
# Deep preflight + candidate validation
# ---------------------------------------------------------------------------


def _zip_readable(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"file does not exist: {path}"
    try:
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                return False, f"zip member failed CRC check: {bad}"
            return True, None
    except (zipfile.BadZipFile, OSError) as exc:
        return False, f"zip not readable: {exc}"


def _ppttc_parses(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return False, f"file does not exist: {path}"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"could not read ppttc: {exc}"
    try:
        json.loads(text)
        return True, None
    except json.JSONDecodeError as exc:
        return False, f"ppttc is not valid JSON: {exc}"


def deep_preflight_for_contract(
    *, bound_deck: Path, seed_pptx: Path, ppttc: Path
) -> dict[str, Any]:
    """Deterministic preflight: each artifact must exist, be readable, and parse.

    Returns a structured report so the manifest preserves an audit trail.
    """
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    for kind, path, fn in (
        ("bound_deck", bound_deck, _zip_readable),
        ("seed_pptx", seed_pptx, _zip_readable),
        ("ppttc", ppttc, _ppttc_parses),
    ):
        ok, reason = fn(path)
        entry = {"kind": kind, "path": str(path), "ok": ok}
        if reason is not None:
            entry["reason"] = reason
        checks.append(entry)
        if not ok:
            failures.append(entry)

    return {
        "ok": not failures,
        "checks": checks,
        "failures": failures,
    }


def _has_native_pptx_table(pptx_path: Path) -> bool:
    """True if the PPTX zip contains at least one native ``<a:tbl>`` element.

    We deliberately scan the raw slide XML instead of using ``python-pptx`` so
    this validator runs without touching Office/COM, and so think-cell graphic
    frames (which embed pictures or OLE charts, not ``a:tbl``) are not
    misclassified as native tables.
    """
    try:
        with zipfile.ZipFile(pptx_path) as zf:
            for name in zf.namelist():
                if name.startswith("ppt/slides/slide") and name.endswith(".xml"):
                    payload = zf.read(name)
                    if b"<a:tbl" in payload or b"<a:tbl>" in payload:
                        return True
    except (zipfile.BadZipFile, OSError):
        return False
    return False


def _slide_count(pptx_path: Path) -> int:
    try:
        with zipfile.ZipFile(pptx_path) as zf:
            return sum(
                1
                for name in zf.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
    except (zipfile.BadZipFile, OSError):
        return 0


def validate_candidate_pptx(path: Path) -> dict[str, Any]:
    """Validate a VM/manual-produced candidate PPTX.

    Pass criteria:
      * file exists
      * zip is readable (CRC check)
      * at least one slide
      * no native PowerPoint table elements (native think-cell tables are blocked)
    """
    reasons: list[str] = []
    if not path.exists():
        return {"ok": False, "reasons": [f"candidate file does not exist: {path}"]}

    zip_ok, zip_reason = _zip_readable(path)
    if not zip_ok:
        reasons.append(zip_reason or "candidate is not a readable zip")
        return {"ok": False, "reasons": reasons}

    slides = _slide_count(path)
    if slides < 1:
        reasons.append("candidate has no slides")

    if _has_native_pptx_table(path):
        reasons.append(
            "candidate contains a native PowerPoint table; native think-cell tables are blocked"
        )

    return {
        "ok": not reasons,
        "reasons": reasons,
        "slide_count": slides,
    }


# ---------------------------------------------------------------------------
# Per-contract planning
# ---------------------------------------------------------------------------


def _arr_acv_guardrails_for(contract_id: str) -> dict[str, str]:
    return ARR_ACV_AXIS.get(
        contract_id,
        {
            "axis": "unknown",
            "salesforce_field": "unknown",
            "report_aggregate": "unknown",
            "type_filter": "unknown",
            "must_not_blend_with": "unknown",
        },
    )


def _manual_steps(contract_id: str, bound_deck: str, candidate_path: str) -> list[str]:
    return [
        f"Open the bound proof deck in PowerPoint (Mac or Windows) with think-cell installed: {bound_deck}",
        "Verify the named think-cell elements bound during L5 proof rendered correctly.",
        "Use think-cell -> Update from Excel only if upstream data has changed; otherwise leave bound state.",
        f"Save As -> {candidate_path} (creating any missing parent folders).",
        f"Confirm no native PowerPoint table was inserted by accident; the {contract_id} candidate must use think-cell native chart shapes only.",
        "Close PowerPoint without sharing or uploading; SharePoint publish is blocked at this stage.",
    ]


def _contract_plan(
    repo_root: Path,
    period: str,
    director_slug: str,
    director_name: str,
    contract_id: str,
    contract: dict[str, Any] | None,
    *,
    run_id: str,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "contract_id": contract_id,
        "publishable": False,
        "status": "unknown_contract",
        "reason": None,
    }
    if contract is None:
        base["reason"] = "contract not found in scaffold"
        return base

    eligibility = eligibility_for(contract, director_name)
    base["eligibility"] = eligibility
    base["supported_lane"] = contract.get("supported_lane")
    base["readiness"] = contract.get("readiness")
    base["proof_status"] = contract.get("proof_status")
    base["arr_acv_guardrails"] = _arr_acv_guardrails_for(contract_id)
    base["guardrails"] = [
        "pilot is not publishable",
        "ARR and Renewal ACV must remain separated",
        "Type filters must match the contract universe",
        "headline currency is EUR; raw multi-currency SOQL SUM is forbidden",
        "native think-cell editable tables remain blocked",
    ]

    if eligibility["decision"] == "unknown":
        base["status"] = "unknown_director"
        base["reason"] = "director not present in contract ready/fallback lists"
        return base
    if eligibility["decision"] == "fallback":
        base["status"] = "not_eligible_director_fallback"
        base["reason"] = eligibility["fallback_lane"]
        return base
    if not is_l5_proven_pass(contract):
        base["status"] = "not_l5_proven"
        base["reason"] = "contract readiness/proof_status is not l5_proven/pass"
        return base

    proof = load_proof_for_contract(repo_root, period, contract_id)
    if proof is None or proof.get("status") != "pass":
        base["status"] = "missing_proof_artifact"
        base["reason"] = "proof JSON missing or not pass"
        return base

    artifacts = _source_artifacts(repo_root, period, contract_id, proof)
    base["source_artifacts"] = artifacts
    candidate_output = str(
        intended_candidate_output_path(repo_root, period, director_slug, contract_id, run_id=run_id)
    )
    base["intended_candidate_output_path"] = candidate_output
    vm_command = [
        ".venv/bin/python",
        "scripts/run_thinkcell_windows_bridge.py",
        "--ppttc",
        artifacts.get("ppttc", ""),
        "--template",
        artifacts.get("seed_pptx", ""),
        "--output",
        candidate_output,
    ]
    for term in _bound_required_terms(proof):
        vm_command.extend(["--expect-text", term])
    base["vm_command"] = vm_command
    base["manual_steps"] = _manual_steps(
        contract_id, artifacts.get("bound_deck", ""), candidate_output
    )

    if not _artifacts_exist(artifacts):
        base["status"] = "missing_proof_artifact"
        base["reason"] = "one or more proof source artifacts are missing"
        return base

    preflight = deep_preflight_for_contract(
        bound_deck=Path(artifacts["bound_deck"]),
        seed_pptx=Path(artifacts["seed_pptx"]),
        ppttc=Path(artifacts["ppttc"]),
    )
    base["preflight"] = preflight
    if not preflight["ok"]:
        base["status"] = STATUS_PREFLIGHT_FAILED
        first = preflight["failures"][0]
        base["reason"] = (
            f"deep preflight failed: {first['kind']} - {first.get('reason', 'unknown')}"
        )
        return base

    base["status"] = STATUS_READY
    base["reason"] = (
        "L5 proof passed and deep preflight green; pilot is ready for VM or manual insertion"
    )
    return base


# ---------------------------------------------------------------------------
# plan_pilot + overall status mapping
# ---------------------------------------------------------------------------


def _overall_from_contracts(contracts: list[dict[str, Any]], discrepancies: list[str]) -> str:
    if discrepancies:
        return OVERALL_BLOCKED
    statuses = {c["status"] for c in contracts}
    if not statuses:
        return OVERALL_BLOCKED
    if statuses == {STATUS_CANDIDATE_CREATED}:
        return OVERALL_CANDIDATE_CREATED
    if statuses.issubset({STATUS_READY, STATUS_AWAITING, STATUS_CANDIDATE_CREATED}):
        return OVERALL_READY
    return OVERALL_BLOCKED


def _production_line_status(overall_status: str) -> dict[str, Any]:
    if overall_status == OVERALL_CANDIDATE_CREATED:
        percent = 92
    elif overall_status == OVERALL_READY:
        percent = 85
    elif overall_status == OVERALL_PLANNED:
        percent = 80
    else:
        percent = 76
    return {
        "percent_complete": percent,
        "remaining_blockers": [
            "QTR04/QTR05 still need human visual approval before production insertion",
            "SharePoint remains blocked until hardened publish gates and one-director pilot pass",
            "VM/Office insertion run is separate from this plan-only preflight",
        ],
    }


def plan_pilot(
    *,
    repo_root: Path,
    period: str,
    director_slug: str,
    contract_ids: list[str],
    run_id: str,
) -> dict[str, Any]:
    context_for_period(period)
    scaffold = load_scaffold(repo_root, period)
    director_name = name_for_slug(director_slug)
    discrepancies = check_baked_eligibility_rules(scaffold)
    contracts = [
        _contract_plan(
            repo_root,
            period,
            director_slug,
            director_name,
            contract_id,
            find_contract(scaffold, contract_id),
            run_id=run_id,
        )
        for contract_id in contract_ids
    ]
    overall = _overall_from_contracts(contracts, discrepancies)
    return {
        "schema": "thinkcell-insertion-pilot-plan/v1",
        "created_at_utc": _utc_now(),
        "period": period,
        "run_id": run_id,
        "director_slug": director_slug,
        "director_name": director_name,
        "plan_only": True,
        "publishable": False,
        "overall_status": overall,
        "eligibility_rule_discrepancies": discrepancies,
        "contracts": contracts,
        "production_line_status": _production_line_status(overall),
    }


# ---------------------------------------------------------------------------
# promote_pilot — read existing manifest, validate produced candidates, rewrite
# ---------------------------------------------------------------------------


def _run_dir(repo_root: Path, period: str, run_id: str) -> Path:
    return repo_root / "state" / period / "__regional__" / "thinkcell_insertion_pilot" / run_id


def _candidate_path_for(contract: dict[str, Any]) -> Path | None:
    intended = contract.get("intended_candidate_output_path")
    if not intended:
        return None
    return Path(intended)


def _promote_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Mutates ``contract`` in place: sets status + candidate_validation + candidate_path."""
    if contract.get("status") not in (STATUS_READY, STATUS_AWAITING, STATUS_CANDIDATE_CREATED):
        # Pre-existing block reasons survive promote untouched.
        return contract

    candidate = _candidate_path_for(contract)
    if candidate is None:
        contract["status"] = STATUS_AWAITING
        contract["reason"] = "no intended_candidate_output_path on contract; cannot locate file"
        return contract

    contract["candidate_path"] = str(candidate)
    if not candidate.exists():
        contract["status"] = STATUS_AWAITING
        contract["reason"] = (
            "no candidate file at intended path yet; run vm_insertion_commands.sh "
            "or follow MANUAL_POWERPOINT_STEPS.md, then re-run --promote"
        )
        contract.pop("candidate_validation", None)
        return contract

    validation = validate_candidate_pptx(candidate)
    contract["candidate_validation"] = validation
    if validation["ok"]:
        contract["status"] = STATUS_CANDIDATE_CREATED
        contract["reason"] = "candidate file validated; still not publishable"
    else:
        contract["status"] = STATUS_CANDIDATE_INVALID
        contract["reason"] = "candidate file present but failed validation"
    return contract


def promote_pilot(
    *,
    repo_root: Path,
    period: str,
    run_id: str,
) -> dict[str, Any]:
    run_dir = _run_dir(repo_root, period, run_id)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no plan-only manifest at {manifest_path}; run --plan-only first")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["plan_only"] = False
    manifest["publishable"] = False
    manifest["promoted_at_utc"] = _utc_now()

    for contract in manifest.get("contracts", []):
        _promote_contract(contract)

    discrepancies = manifest.get("eligibility_rule_discrepancies") or []
    overall = _overall_from_contracts(manifest["contracts"], discrepancies)
    manifest["overall_status"] = overall
    manifest["production_line_status"] = _production_line_status(overall)

    write_run_dir(run_dir, manifest)
    return manifest


# ---------------------------------------------------------------------------
# Run-dir output
# ---------------------------------------------------------------------------


def _markdown_manifest(manifest: dict[str, Any]) -> str:
    lines = [
        "# Think-cell Insertion Pilot",
        "",
        f"- Period: `{manifest['period']}`",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Director: `{manifest['director_name']}`",
        f"- Status: `{manifest['overall_status']}`",
        f"- Publishable: `{manifest['publishable']}`",
        "",
        "## Contracts",
        "",
    ]
    for contract in manifest["contracts"]:
        lines.append(f"### {contract['contract_id']}")
        lines.append(f"- Status: `{contract['status']}`")
        if contract.get("reason"):
            lines.append(f"- Reason: {contract['reason']}")
        if contract.get("intended_candidate_output_path"):
            lines.append(f"- Candidate output: `{contract['intended_candidate_output_path']}`")
        if contract.get("candidate_path") and contract.get("candidate_path") != contract.get(
            "intended_candidate_output_path"
        ):
            lines.append(f"- Candidate path: `{contract['candidate_path']}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _production_status_markdown(manifest: dict[str, Any]) -> str:
    status = manifest["production_line_status"]
    lines = [
        "# Production Line Status",
        "",
        f"- Estimated complete: {status['percent_complete']}%",
        f"- Insertion pilot status: `{manifest['overall_status']}`",
        f"- SharePoint publishable: `{manifest['publishable']}`",
        "",
        "## Blockers",
        "",
    ]
    for blocker in status["remaining_blockers"]:
        lines.append(f"- {blocker}")
    return "\n".join(lines).rstrip() + "\n"


def _vm_insertion_commands_sh(manifest: dict[str, Any]) -> str:
    """Render an executable shell script with the VM bridge invocations.

    Only emitted when overall_status is ready_for_vm_or_manual_insertion or
    candidate_created (i.e. every contract has a vm_command). For a blocked
    run the script is intentionally absent.
    """
    director = manifest["director_name"]
    period = manifest["period"]
    run_id = manifest["run_id"]
    lines = [
        "#!/usr/bin/env bash",
        "# vm_insertion_commands.sh",
        f"# Generated by run_thinkcell_insertion_pilot.py at {manifest['created_at_utc']}",
        f"# Director: {director}",
        f"# Period: {period}",
        f"# Run ID: {run_id}",
        "#",
        "# This script is NOT publishable. Outputs are pilot candidates only.",
        "# Run from the repo root on a host that has the Windows VM bridge configured",
        "# (or substitute with the manual PowerPoint steps in MANUAL_POWERPOINT_STEPS.md).",
        "#",
        "# Each invocation calls the VM bridge with the proof-bound .ppttc and writes the",
        "# candidate PPTX under state/<period>/__regional__/thinkcell_insertion_pilot/<run_id>/.",
        "set -euo pipefail",
        "",
    ]
    for contract in manifest["contracts"]:
        cid = contract["contract_id"]
        out = contract.get("intended_candidate_output_path")
        cmd = contract.get("vm_command") or []
        if not out or not cmd:
            continue
        out_dir = str(Path(out).parent)
        lines.append(f"# --- {cid} ---")
        lines.append(
            f"# axis={contract.get('arr_acv_guardrails', {}).get('axis', 'unknown')} "
            f"type_filter={contract.get('arr_acv_guardrails', {}).get('type_filter', 'unknown')}"
        )
        lines.append(f"mkdir -p {shlex.quote(out_dir)}")
        lines.append(" ".join(shlex.quote(arg) for arg in cmd))
        lines.append("")
    lines.append("echo 'pilot candidates produced; run --promote to validate.'")
    return "\n".join(lines) + "\n"


def _manual_steps_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# Manual PowerPoint Insertion Steps",
        "",
        "Run these by hand if the Windows VM bridge is unavailable. The harness",
        "will not call PowerPoint or think-cell on your behalf.",
        "",
        f"- Period: `{manifest['period']}`",
        f"- Run ID: `{manifest['run_id']}`",
        f"- Director: `{manifest['director_name']}`",
        f"- Overall status: `{manifest['overall_status']}`",
        f"- Publishable: `{manifest['publishable']}` (always false at this stage)",
        "",
        "## General rules",
        "",
        "- This output is NOT publishable. SharePoint upload remains blocked.",
        "- Do NOT replace any chart with a native PowerPoint table — native think-cell",
        "  editable tables (and the native PowerPoint table fallback) are blocked.",
        "- Preserve the ARR / Renewal ACV split per contract; never blend them.",
        "- Preserve the Type filter per contract.",
        "- Headline numbers must come from FX-converted EUR Salesforce report aggregates,",
        "  not raw multi-currency SOQL SUM.",
        "",
        "## Per contract",
        "",
    ]
    for contract in manifest["contracts"]:
        cid = contract["contract_id"]
        lines.append(f"### {cid}")
        axis = contract.get("arr_acv_guardrails") or {}
        if axis:
            lines.append(
                f"- Axis: **{axis.get('axis', 'unknown')}** via "
                f"`{axis.get('salesforce_field', 'unknown')}` "
                f"(report aggregate `{axis.get('report_aggregate', 'unknown')}`)"
            )
            lines.append(
                f"- Type filter: `{axis.get('type_filter', 'unknown')}`; never blend with "
                f"`{axis.get('must_not_blend_with', 'unknown')}`."
            )
        for step in contract.get("manual_steps") or []:
            lines.append(f"  - {step}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _changes_md(manifest: dict[str, Any]) -> str:
    overall = manifest["overall_status"]
    if overall == OVERALL_CANDIDATE_CREATED:
        body = (
            "Promoted plan-only manifest to candidate_created after validating each "
            "VM/manual-produced candidate PPTX. Still not publishable."
        )
    elif overall == OVERALL_READY:
        body = (
            "Wrote ready_for_vm_or_manual_insertion plan plus vm_insertion_commands.sh "
            "and MANUAL_POWERPOINT_STEPS.md. No Office, VM, or SharePoint call ran."
        )
    else:
        body = (
            f"Wrote {overall} manifest; one or more contracts blocked. No Office, "
            "VM, or SharePoint call ran."
        )
    return f"# Changes\n\n{body}\n"


def _verification_md(manifest: dict[str, Any]) -> str:
    return (
        "# Verification\n\n"
        f"- Overall status: `{manifest['overall_status']}`\n"
        f"- Publishable: `{manifest['publishable']}`\n"
        "- Plan-only mode emits manifest + vm_insertion_commands.sh + "
        "MANUAL_POWERPOINT_STEPS.md.\n"
        "- Promote mode rewrites manifest with candidate_validation per contract.\n"
        "- Run `.venv/bin/python -m pytest tests/test_thinkcell_insertion_pilot.py -q` "
        "to re-run the focused suite.\n"
    )


def _next_for_codex_md(manifest: dict[str, Any]) -> str:
    overall = manifest["overall_status"]
    if overall == OVERALL_BLOCKED:
        body = (
            "One or more contracts are blocked. Inspect each contract's `status`/`reason`"
            " before doing anything else; do not run vm_insertion_commands.sh."
        )
    elif overall == OVERALL_READY:
        body = (
            "Run `bash vm_insertion_commands.sh` on the Windows VM bridge host (or follow"
            " MANUAL_POWERPOINT_STEPS.md), then re-run this CLI with `--promote` and the"
            " same `--run-id` to validate the candidates."
        )
    elif overall == OVERALL_CANDIDATE_CREATED:
        body = (
            "Candidates exist and are validated. Review them visually side-by-side with the"
            " current Q2 deck pages and capture leadership-decision-improvement evidence"
            " before any future SharePoint publish. Publish remains blocked here."
        )
    else:
        body = "Manifest is at a legacy/partial state; review and decide next mode."
    return f"# Next For Codex Audit\n\n{body}\n"


def write_run_dir(run_dir: Path, manifest: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (run_dir / "RUN_LOG.md").write_text(_markdown_manifest(manifest), encoding="utf-8")
    (run_dir / "CHANGES.md").write_text(_changes_md(manifest), encoding="utf-8")
    (run_dir / "VERIFICATION.md").write_text(_verification_md(manifest), encoding="utf-8")
    (run_dir / "NEXT_FOR_CODEX_AUDIT.md").write_text(_next_for_codex_md(manifest), encoding="utf-8")
    (run_dir / "PRODUCTION_LINE_STATUS.md").write_text(
        _production_status_markdown(manifest), encoding="utf-8"
    )

    overall = manifest["overall_status"]
    vm_sh = run_dir / "vm_insertion_commands.sh"
    manual_md = run_dir / "MANUAL_POWERPOINT_STEPS.md"
    if overall in (OVERALL_READY, OVERALL_CANDIDATE_CREATED):
        vm_sh.write_text(_vm_insertion_commands_sh(manifest), encoding="utf-8")
        existing = vm_sh.stat().st_mode
        vm_sh.chmod(existing | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        manual_md.write_text(_manual_steps_markdown(manifest), encoding="utf-8")
    else:
        # If we are demoting/blocked, stale files would mislead operators - remove them.
        for stale in (vm_sh, manual_md):
            if stale.exists():
                stale.unlink()


def _default_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", required=True)
    parser.add_argument("--director-slug", required=True)
    parser.add_argument("--contracts", nargs="+", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--plan-only",
        dest="plan_only",
        action="store_true",
        help="emit manifest + VM/manual steps without running Office",
    )
    mode.add_argument(
        "--promote",
        dest="promote",
        action="store_true",
        help="validate VM/manual-produced candidate PPTX files for an existing run",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-id", default=_default_run_id())
    args = parser.parse_args(argv)

    if args.promote:
        try:
            manifest = promote_pilot(
                repo_root=args.repo_root,
                period=args.period,
                run_id=args.run_id,
            )
        except FileNotFoundError as exc:
            parser.error(str(exc))
        run_dir = _run_dir(args.repo_root, args.period, args.run_id)
        print(f"run_dir={run_dir}")
        print(f"status={manifest['overall_status']}")
        if manifest["overall_status"] == OVERALL_CANDIDATE_CREATED:
            return 0
        if manifest["overall_status"] == OVERALL_READY:
            return 0  # awaiting VM run; harness still healthy
        return 2

    try:
        manifest = plan_pilot(
            repo_root=args.repo_root,
            period=args.period,
            director_slug=args.director_slug,
            contract_ids=list(args.contracts),
            run_id=args.run_id,
        )
    except ValueError as exc:
        parser.error(str(exc))

    run_dir = _run_dir(args.repo_root, args.period, args.run_id)
    write_run_dir(run_dir, manifest)
    print(f"run_dir={run_dir}")
    print(f"status={manifest['overall_status']}")
    return 0 if manifest["overall_status"] in (OVERALL_PLANNED, OVERALL_READY) else 2


if __name__ == "__main__":
    raise SystemExit(main())
