"""Tests for scripts/build_thinkcell_template_intelligence_db.py."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_thinkcell_template_intelligence_db as mod  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_fake_pptx(path: Path, texts: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    runs = "".join(f"<a:r><a:t>{text}</a:t></a:r>" for text in texts)
    slide_xml = (
        '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        f"<p:cSld><p:spTree><p:sp><p:txBody><a:p>{runs}</a:p></p:txBody></p:sp>"
        "</p:spTree></p:cSld></p:sld>"
    )
    with ZipFile(path, "w") as zf:
        zf.writestr("ppt/slides/slide1.xml", slide_xml)
        zf.writestr("ppt/embeddings/oleObject1.bin", b"tc")


def _fixture_repo(tmp_path: Path, candidate_texts: list[str]) -> dict[str, Path]:
    repo = tmp_path / "repo"
    period = "2026-Q2"
    candidate = repo / "state" / period / "__regional__" / "pilot" / "qtr04.pptx"
    _write_fake_pptx(candidate, candidate_texts)

    catalog = repo / "state" / "thinkcell_bridge" / "template_catalog" / "thinkcell_template_catalog.json"
    _write_json(
        catalog,
        [
            {
                "relative_path": "think-cell Charts/Scatter, Bubble/Scatter, Bubble.potx",
                "slide_count": 2,
                "chart_refs": 2,
                "graphic_frames": 2,
                "pictures": 0,
                "ole_objects": 6,
                "tag_files": 67,
                "named_thinkcell_payloads": 0,
                "render_candidate": True,
                "text_sample": ["Correlation: Scatter"],
            }
        ],
    )
    selection = repo / "config" / "thinkcell_template_selection.may_2026.json"
    _write_json(
        selection,
        {
            "schema": "thinkcell-template-selection/v1",
            "hard_constraint": "stock templates are donor references only",
            "selected_families": [
                {
                    "family": "Scatter, Bubble",
                    "template": "/Library/Application Support/Microsoft/think-cell/templates/think-cell Charts/Scatter, Bubble/Scatter, Bubble.potx",
                    "status": "recommended new chart lane",
                    "use_for": ["deal inspection"],
                    "deck_targets": ["S09"],
                }
            ],
        },
    )
    capability = repo / "docs" / "thinkcell-corpus" / "thinkcell_infra_capability_map.json"
    _write_json(
        capability,
        {
            "schema": "simcorp-thinkcell-infra-capability-map/v1",
            "capabilities": [{"id": "ppttc_windows_bridge", "status": "production"}],
        },
    )
    scaffold = (
        repo
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "thinkcell_build_scaffold.json"
    )
    _write_json(
        scaffold,
        {
            "schema": "thinkcell-build-scaffold/v1",
            "contracts": [
                {
                    "name": "QTR04_DealRisk_Scatter",
                    "priority": "P1",
                    "family": "scatter_bubble",
                    "thinkcell_template_family": "think-cell Charts/Scatter, Bubble",
                    "supported_lane": "native think-cell chart via named seed + ppttc",
                    "readiness": "l5_proven",
                    "proof_status": "pass",
                    "guardrail": "ARR only",
                    "fallback": "ranked risk table",
                }
            ],
        },
    )
    proof = (
        repo
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "work"
        / "QTR04_DealRisk_Scatter"
        / "QTR04_DealRisk_Scatter-proof.json"
    )
    _write_json(proof, {"status": "pass", "deck": "/tmp/proof.pptx", "render_dir": "/tmp/render"})
    visual_plan = (
        repo
        / "state"
        / period
        / "__regional__"
        / "thinkcell_visual_plan"
        / "thinkcell_visual_contract_plan.json"
    )
    _write_json(
        visual_plan,
        {
            "schema": "sales-director-thinkcell-visual-contract-plan/v1",
            "directors": [
                {
                    "director": "Jesper Tyrer",
                    "slug": "Jesper-Tyrer",
                    "territory": "APAC",
                    "decisions": [
                        {
                            "contract": "QTR04_DealRisk_Scatter",
                            "priority": "P1",
                            "family": "scatter_bubble",
                            "decision": "include",
                            "lane": "native think-cell chart via named seed + ppttc",
                            "reason": "deal risk has enough named deals",
                            "evidence": ["proof_status=pass"],
                            "guardrail": "ARR only",
                        }
                    ],
                }
            ],
        },
    )
    manifest = repo / "state" / period / "__regional__" / "thinkcell_insertion_pilot" / "run-1" / "manifest.json"
    _write_json(
        manifest,
        {
            "schema": "thinkcell-insertion-pilot-plan/v1",
            "run_id": "run-1",
            "director_slug": "Jesper-Tyrer",
            "contracts": [
                {
                    "contract_id": "QTR04_DealRisk_Scatter",
                    "status": "candidate_created",
                    "publishable": False,
                    "candidate_path": str(candidate),
                    "candidate_validation": {"ok": True, "slide_count": 1, "reasons": []},
                }
            ],
        },
    )
    return {
        "repo": repo,
        "catalog": catalog,
        "selection": selection,
        "capability": capability,
        "scaffold": scaffold,
        "visual_plan": visual_plan,
        "manifest": manifest,
    }


def _build(paths: dict[str, Path], tmp_path: Path) -> dict:
    return mod.build_database(
        repo_root=paths["repo"],
        period="2026-Q2",
        output_dir=tmp_path / "out",
        template_catalog_path=paths["catalog"],
        template_selection_path=paths["selection"],
        scaffold_path=paths["scaffold"],
        visual_plan_path=paths["visual_plan"],
        capability_map_path=paths["capability"],
        candidate_manifest_paths=[paths["manifest"]],
    )


def test_candidate_with_template_residue_blocks_promotion(tmp_path: Path):
    paths = _fixture_repo(
        tmp_path,
        ["Correlation: Scatter", "Insert chart title here", "Lorem ipsum", "Company 1"],
    )
    result = _build(paths, tmp_path)

    assert result["report"]["summary"]["candidate_blocker_count"] == 1
    finding = result["report"]["candidate_findings"][0]
    assert finding["promotion_grade"] == "not_promotion_ready_template_residue"

    with sqlite3.connect(result["db_path"]) as conn:
        recommendation = conn.execute(
            "select recommendation from director_decision where contract_id = ?",
            ("QTR04_DealRisk_Scatter",),
        ).fetchone()[0]
    assert recommendation == "hold_not_promotion_ready_template_residue"


def test_clean_candidate_still_needs_promotion_record(tmp_path: Path):
    paths = _fixture_repo(tmp_path, ["Deal risk inspection", "ARR (mEUR)", "Probability (%)"])
    result = _build(paths, tmp_path)

    assert result["report"]["summary"]["candidate_blocker_count"] == 0
    finding = result["report"]["candidate_findings"][0]
    assert finding["promotion_grade"] == "valid_candidate_needs_promotion_record"

    with sqlite3.connect(result["db_path"]) as conn:
        recommendation = conn.execute(
            "select recommendation from director_decision where contract_id = ?",
            ("QTR04_DealRisk_Scatter",),
        ).fetchone()[0]
    assert recommendation == "requires_promotion_record"
