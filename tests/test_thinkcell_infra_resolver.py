"""Tests for scripts/resolve_thinkcell_infra_plan.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import resolve_thinkcell_infra_plan as mod  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _capability_map() -> dict:
    return {
        "schema": "simcorp-thinkcell-infra-capability-map/v1",
        "capabilities": [
            {"id": "python_orchestration", "status": "production"},
            {"id": "ppttc_windows_bridge", "status": "production"},
            {"id": "named_donor_seed_patching", "status": "production"},
            {"id": "excel_com_updatebatch", "status": "production"},
            {"id": "table_image_donor", "status": "production"},
        ],
    }


def _visual_plan() -> dict:
    return {
        "schema": "sales-director-thinkcell-visual-contract-plan/v1",
        "period": "2026-Q2",
        "directors": [
            {
                "director": "Jesper Tyrer",
                "slug": "Jesper-Tyrer",
                "decisions": [
                    {
                        "contract": "QTR01_StageMix_Bar",
                        "priority": "P0",
                        "family": "bar_column",
                        "lane": "native think-cell chart via named seed + ppttc",
                        "decision": "include",
                        "guardrail": "ARR universe only",
                        "reason": "proven contract and director data shape fit",
                    },
                    {
                        "contract": "QTR04_DealRisk_Scatter",
                        "priority": "P1",
                        "family": "scatter_bubble",
                        "lane": "native think-cell chart via named seed + ppttc",
                        "decision": "include",
                        "guardrail": "ARR universe only",
                        "reason": "deal risk has enough named deals",
                    },
                    {
                        "contract": "QTR08_PipelineMovement_Waterfall",
                        "priority": "P1",
                        "family": "waterfall",
                        "lane": "native think-cell chart via named seed + ppttc",
                        "decision": "candidate",
                        "guardrail": "closed-lost and slips subtract",
                        "reason": "promote only when movement is a management question",
                    },
                    {
                        "contract": "QTR10_ActionDecisionRegister_TableImage",
                        "priority": "P0",
                        "family": "table_image",
                        "lane": "Excel COM AddRangeImage table-image donor",
                        "decision": "include",
                        "guardrail": "table rows stay traceable",
                        "reason": "proven contract and director data shape fit",
                    },
                    {
                        "contract": "QTR06_Q2RenewalTimeline_Gantt",
                        "priority": "P2",
                        "family": "timeline_gantt",
                        "lane": "native think-cell chart via named seed + ppttc",
                        "decision": "suppress",
                        "guardrail": "Renewal ACV only",
                        "reason": "not materially justified",
                    },
                    {
                        "contract": "QTR05_FY26RenewalTimeline_Gantt",
                        "priority": "P1",
                        "family": "timeline_gantt",
                        "lane": "native think-cell chart via named seed + ppttc",
                        "decision": "fallback",
                        "guardrail": "Renewal ACV only",
                        "reason": "dates collapse",
                    },
                ],
            }
        ],
    }


def _contract(name: str, priority: str, lane: str, family: str = "bar_column") -> dict:
    return {
        "name": name,
        "priority": priority,
        "family": family,
        "supported_lane": lane,
        "readiness": "l5_proven",
        "proof_status": "pass",
    }


def _scaffold() -> dict:
    chart_lane = "native think-cell chart via named seed + ppttc"
    table_lane = "Excel COM AddRangeImage table-image donor"
    return {
        "schema": "thinkcell-build-scaffold/v1",
        "period": "2026-Q2",
        "contracts": [
            _contract("QTR01_StageMix_Bar", "P0", chart_lane),
            _contract("QTR04_DealRisk_Scatter", "P1", chart_lane, "scatter_bubble"),
            _contract("QTR08_PipelineMovement_Waterfall", "P1", chart_lane, "waterfall"),
            _contract("QTR10_ActionDecisionRegister_TableImage", "P0", table_lane, "table_image"),
            _contract("QTR06_Q2RenewalTimeline_Gantt", "P2", chart_lane, "timeline_gantt"),
            _contract("QTR05_FY26RenewalTimeline_Gantt", "P1", chart_lane, "timeline_gantt"),
        ],
    }


def _candidate_manifest() -> dict:
    return {
        "schema": "thinkcell-insertion-pilot-plan/v1",
        "overall_status": "candidate_created",
        "publishable": False,
        "contracts": [
            {
                "contract_id": "QTR04_DealRisk_Scatter",
                "status": "candidate_created",
                "publishable": False,
                "candidate_path": "/tmp/qtr04-candidate.pptx",
                "candidate_validation": {"ok": True, "slide_count": 2, "reasons": []},
            }
        ],
    }


def _write_proof(repo: Path, contract_id: str, status: str = "pass") -> None:
    proof = {
        "status": status,
        "deck": f"/tmp/{contract_id}.pptx",
        "seed_pptx": f"/tmp/{contract_id}-seed.pptx",
        "ppttc": f"/tmp/{contract_id}.ppttc",
        "render_dir": f"/tmp/{contract_id}-render",
    }
    path = (
        repo
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / "2026-Q2"
        / "work"
        / contract_id
        / f"{contract_id}-proof.json"
    )
    _write_json(path, proof)


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_json(repo / "docs" / "thinkcell-corpus" / "thinkcell_infra_capability_map.json", _capability_map())
    _write_json(
        repo
        / "state"
        / "2026-Q2"
        / "__regional__"
        / "thinkcell_visual_plan"
        / "thinkcell_visual_contract_plan.json",
        _visual_plan(),
    )
    _write_json(
        repo
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / "2026-Q2"
        / "thinkcell_build_scaffold.json",
        _scaffold(),
    )
    for contract_id in [
        "QTR01_StageMix_Bar",
        "QTR04_DealRisk_Scatter",
        "QTR08_PipelineMovement_Waterfall",
        "QTR10_ActionDecisionRegister_TableImage",
        "QTR06_Q2RenewalTimeline_Gantt",
        "QTR05_FY26RenewalTimeline_Gantt",
    ]:
        _write_proof(repo, contract_id)
    candidate_manifest = (
        repo
        / "state"
        / "2026-Q2"
        / "__regional__"
        / "thinkcell_insertion_pilot"
        / "run-1"
        / "manifest.json"
    )
    _write_json(candidate_manifest, _candidate_manifest())
    return repo


def _by_contract(result: dict) -> dict[str, dict]:
    return {item["contract_id"]: item for item in result["decisions"]}


def test_resolver_requires_promotion_for_include_candidate(fixture_repo: Path):
    result = mod.resolve_director(
        repo_root=fixture_repo,
        period="2026-Q2",
        director_slug="Jesper-Tyrer",
        candidate_manifest_path=(
            fixture_repo
            / "state"
            / "2026-Q2"
            / "__regional__"
            / "thinkcell_insertion_pilot"
            / "run-1"
            / "manifest.json"
        ),
    )

    decisions = _by_contract(result)

    assert result["status"] == "pass"
    assert decisions["QTR04_DealRisk_Scatter"]["assembly_action"] == "requires_promotion_decision"
    assert decisions["QTR04_DealRisk_Scatter"]["candidate"]["status"] == "candidate_created"
    assert result["summary"]["promotion_required_contracts"] == ["QTR04_DealRisk_Scatter"]


def test_resolver_keeps_p0_and_nonincluded_visuals_out_of_promotion(fixture_repo: Path):
    result = mod.resolve_director(
        repo_root=fixture_repo,
        period="2026-Q2",
        director_slug="Jesper-Tyrer",
    )
    decisions = _by_contract(result)

    assert decisions["QTR01_StageMix_Bar"]["assembly_action"] == "use_existing_linked_spine"
    assert (
        decisions["QTR10_ActionDecisionRegister_TableImage"]["assembly_action"]
        == "use_existing_table_image_linked_spine"
    )
    assert (
        decisions["QTR08_PipelineMovement_Waterfall"]["assembly_action"]
        == "hold_candidate_pending_management_question"
    )
    assert decisions["QTR06_Q2RenewalTimeline_Gantt"]["assembly_action"] == "suppress"
    assert decisions["QTR05_FY26RenewalTimeline_Gantt"]["assembly_action"] == "use_fallback_existing_spine"


def test_resolver_blocks_when_required_capability_is_not_production(fixture_repo: Path):
    cap_path = fixture_repo / "docs" / "thinkcell-corpus" / "thinkcell_infra_capability_map.json"
    caps = _capability_map()
    for capability in caps["capabilities"]:
        if capability["id"] == "ppttc_windows_bridge":
            capability["status"] = "blocked"
    _write_json(cap_path, caps)

    result = mod.resolve_director(
        repo_root=fixture_repo,
        period="2026-Q2",
        director_slug="Jesper-Tyrer",
    )
    qtr04 = _by_contract(result)["QTR04_DealRisk_Scatter"]

    assert result["status"] == "blocked"
    assert qtr04["assembly_action"] == "blocked_by_capability"
    assert qtr04["capability_failures"] == ["ppttc_windows_bridge status is blocked"]
