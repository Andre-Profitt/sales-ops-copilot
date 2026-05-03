#!/usr/bin/env python3
"""Build a decision database for think-cell template and contract usage.

This is the infra layer between "we have a template/candidate" and "the deck
builder may use it." It normalizes the stock template catalog, SimCorp template
selection map, L5 scaffold proofs, visual-plan decisions, capability registry,
and insertion-pilot candidates into one SQLite database plus review reports.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "template_intelligence" / DEFAULT_PERIOD

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"

FORBIDDEN_CANDIDATE_TEXT = {
    "placeholder_title": "Insert chart title here",
    "placeholder_body": "Insert your desired text",
    "lorem": "Lorem ipsum",
    "template_company_1": "Company 1",
    "template_company_2": "Company 2",
    "template_keyword_footer": "Keywords: think-cell",
    "template_help_text": "This slide contains a think-cell chart",
    "template_instruction": "click the chart",
    "sample_metric": "Return on capital",
}


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _as_repo_path(path: str | Path, repo_root: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else repo_root / path


def _rel(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return str(path)


def _template_relative(template_path: str) -> str:
    marker = "/templates/"
    normalized = template_path.replace("\\", "/")
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return normalized


def _discover_candidate_manifests(repo_root: Path, period: str) -> list[Path]:
    root = repo_root / "state" / period / "__regional__" / "thinkcell_insertion_pilot"
    if not root.exists():
        return []
    return sorted(root.glob("*/manifest.json"), key=lambda item: item.stat().st_mtime)


def _slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_pptx_text(zf: ZipFile, slide_names: list[str]) -> list[str]:
    texts: list[str] = []
    for slide_name in slide_names:
        try:
            root = ET.fromstring(zf.read(slide_name))
        except ET.ParseError:
            continue
        for node in root.iter(f"{A_NS}t"):
            value = (node.text or "").strip()
            if value:
                texts.append(value)
    return texts


def audit_pptx(path: Path) -> dict[str, Any]:
    """Return package/text evidence for a candidate PPTX without opening Office."""

    result: dict[str, Any] = {
        "exists": path.exists(),
        "zip_ok": False,
        "bad_zip_member": None,
        "slide_count": 0,
        "embedding_count": 0,
        "media_count": 0,
        "text_char_count": 0,
        "forbidden_terms": [],
        "text_sample": [],
    }
    if not path.exists():
        return result

    try:
        with ZipFile(path) as zf:
            bad_member = zf.testzip()
            names = zf.namelist()
            slide_names = sorted(
                [
                    name
                    for name in names
                    if re.match(r"ppt/slides/slide\d+\.xml$", name)
                ],
                key=_slide_sort_key,
            )
            texts = _extract_pptx_text(zf, slide_names)
    except BadZipFile:
        result["bad_zip_member"] = "BadZipFile"
        return result

    full_text = "\n".join(texts)
    full_text_folded = full_text.casefold()
    forbidden = [
        {"id": key, "text": needle}
        for key, needle in FORBIDDEN_CANDIDATE_TEXT.items()
        if needle.casefold() in full_text_folded
    ]
    result.update(
        {
            "zip_ok": bad_member is None,
            "bad_zip_member": bad_member,
            "slide_count": len(slide_names),
            "embedding_count": len([name for name in names if name.startswith("ppt/embeddings/")]),
            "media_count": len([name for name in names if name.startswith("ppt/media/")]),
            "text_char_count": len(full_text),
            "forbidden_terms": forbidden,
            "text_sample": texts[:16],
        }
    )
    return result


def _candidate_grade(
    *, audit: dict[str, Any], candidate_validation: dict[str, Any] | None, publishable: bool
) -> tuple[str, str]:
    validation_ok = None if candidate_validation is None else bool(candidate_validation.get("ok"))
    if not audit["exists"]:
        return "missing_artifact", "candidate PPTX path does not exist"
    if not audit["zip_ok"]:
        return "corrupt_artifact", f"zip validation failed: {audit.get('bad_zip_member')}"
    if audit["slide_count"] <= 0:
        return "invalid_artifact", "no slides found in PPTX package"
    if audit["forbidden_terms"]:
        terms = ", ".join(item["id"] for item in audit["forbidden_terms"])
        return "not_promotion_ready_template_residue", f"template residue found: {terms}"
    if validation_ok is False:
        return "candidate_validation_failed", "manifest candidate_validation.ok is false"
    if not publishable:
        return "valid_candidate_needs_promotion_record", "candidate is valid but publishable=false"
    return "publishable_candidate", "candidate is publishable"


def _family_posture(status: str, named_payloads: int) -> str:
    status_folded = status.casefold()
    if named_payloads > 0:
        return "direct_ppttc_candidate"
    if "not safe" in status_folded or "blocked" in status_folded:
        return "reference_only_blocked_for_live_binding"
    if "already seeded" in status_folded:
        return "seeded_contract_available"
    if "recommended new chart lane" in status_folded or "conditional new chart lane" in status_folded:
        return "candidate_requires_named_donor_and_promotion"
    if "visual reference only" in status_folded or "inspiration" in status_folded:
        return "visual_reference_only"
    return "reference_or_patch_only"


def _candidate_by_contract(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["contract_id"]
        if key not in latest or str(row["run_id"]) >= str(latest[key]["run_id"]):
            latest[key] = row
    return latest


def _recommendation_for_decision(
    decision: dict[str, Any],
    contract: dict[str, Any] | None,
    latest_candidate: dict[str, Any] | None,
) -> tuple[str, str, str]:
    visual_decision = str(decision.get("decision") or "")
    priority = str(decision.get("priority") or (contract or {}).get("priority") or "")
    lane = str(decision.get("lane") or (contract or {}).get("supported_lane") or "")
    contract_id = str(decision.get("contract") or (contract or {}).get("name") or "")

    if visual_decision == "suppress":
        return "suppress", "visual plan suppresses this contract", "Keep out of deck assembly."
    if visual_decision == "fallback":
        return "use_fallback", str(decision.get("reason") or "visual plan requires fallback"), "Use existing safe spine/table fallback."
    if visual_decision == "candidate":
        return (
            "hold_candidate_pending_management_question",
            str(decision.get("reason") or "candidate only"),
            "Do not promote until the meeting question requires it.",
        )

    if "table-image" in lane.casefold() or "addrangeimage" in lane.casefold():
        return (
            "use_table_image_lane",
            "table-image lane is the production-safe dense-table path",
            "Keep Excel range traceability and render/aspect gates.",
        )

    if priority == "P0":
        return (
            "use_proven_native_seed_lane",
            "P0 contract is L5-proven and belongs in the safe spine path",
            "Use bound/proven seed output; do not hand-draw replacement charts.",
        )

    if latest_candidate:
        grade = latest_candidate["promotion_grade"]
        if grade == "valid_candidate_needs_promotion_record":
            return (
                "requires_promotion_record",
                "candidate package is clean but publishable=false",
                "Create promotion decision record with render evidence before insertion.",
            )
        return (
            f"hold_{grade}",
            latest_candidate["blocker_reason"],
            "Clean or rebuild the candidate before any meeting-spine insertion.",
        )

    return (
        "build_candidate_before_promotion",
        f"{contract_id} has no audited candidate artifact",
        "Run insertion pilot, audit the candidate, then create a promotion record.",
    )


def _connect_fresh(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE template_catalog (
            relative_path TEXT PRIMARY KEY,
            slide_count INTEGER NOT NULL,
            chart_refs INTEGER NOT NULL,
            graphic_frames INTEGER NOT NULL,
            pictures INTEGER NOT NULL,
            ole_objects INTEGER NOT NULL,
            tag_files INTEGER NOT NULL,
            named_thinkcell_payloads INTEGER NOT NULL,
            automation_posture TEXT NOT NULL,
            render_candidate INTEGER NOT NULL,
            text_sample_json TEXT NOT NULL
        );
        CREATE TABLE selected_family (
            family TEXT PRIMARY KEY,
            template TEXT NOT NULL,
            template_relative TEXT NOT NULL,
            status TEXT NOT NULL,
            automation_posture TEXT NOT NULL,
            use_for_json TEXT NOT NULL,
            deck_targets_json TEXT NOT NULL,
            catalog_found INTEGER NOT NULL,
            catalog_slide_count INTEGER,
            catalog_chart_refs INTEGER,
            catalog_named_payloads INTEGER
        );
        CREATE TABLE capability (
            capability_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            production_rule TEXT,
            entrypoints_json TEXT NOT NULL
        );
        CREATE TABLE contract (
            contract_id TEXT PRIMARY KEY,
            priority TEXT NOT NULL,
            family TEXT NOT NULL,
            thinkcell_template_family TEXT,
            selected_family TEXT,
            supported_lane TEXT NOT NULL,
            guardrail TEXT,
            fallback TEXT,
            readiness TEXT,
            proof_status TEXT,
            proof_json TEXT,
            proof_deck TEXT,
            proof_render_dir TEXT
        );
        CREATE TABLE director_decision (
            period TEXT NOT NULL,
            director_slug TEXT NOT NULL,
            director TEXT NOT NULL,
            territory TEXT,
            contract_id TEXT NOT NULL,
            priority TEXT,
            family TEXT,
            visual_decision TEXT NOT NULL,
            lane TEXT,
            reason TEXT,
            evidence_json TEXT NOT NULL,
            template TEXT,
            proof_status TEXT,
            guardrail TEXT,
            recommendation TEXT NOT NULL,
            recommendation_reason TEXT NOT NULL,
            next_action TEXT NOT NULL,
            PRIMARY KEY (period, director_slug, contract_id)
        );
        CREATE TABLE candidate_artifact (
            run_id TEXT NOT NULL,
            period TEXT NOT NULL,
            director_slug TEXT,
            contract_id TEXT NOT NULL,
            candidate_path TEXT NOT NULL,
            candidate_status TEXT,
            publishable INTEGER NOT NULL,
            validation_ok INTEGER,
            zip_ok INTEGER NOT NULL,
            bad_zip_member TEXT,
            slide_count INTEGER NOT NULL,
            embedding_count INTEGER NOT NULL,
            media_count INTEGER NOT NULL,
            forbidden_count INTEGER NOT NULL,
            forbidden_terms_json TEXT NOT NULL,
            promotion_grade TEXT NOT NULL,
            blocker_reason TEXT NOT NULL,
            source_manifest TEXT NOT NULL,
            PRIMARY KEY (run_id, contract_id, candidate_path)
        );
        """
    )


def build_database(
    *,
    repo_root: Path,
    period: str,
    output_dir: Path,
    template_catalog_path: Path,
    template_selection_path: Path,
    scaffold_path: Path,
    visual_plan_path: Path,
    capability_map_path: Path,
    candidate_manifest_paths: list[Path],
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    db_path = output_dir / "thinkcell_template_intelligence.sqlite"
    conn = _connect_fresh(db_path)
    _create_schema(conn)

    template_catalog = _read_json(template_catalog_path)
    template_selection = _read_json(template_selection_path)
    scaffold = _read_json(scaffold_path)
    visual_plan = _read_json(visual_plan_path)
    capability_map = _read_json(capability_map_path)
    now = _utc_now()

    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            ("schema", "simcorp-thinkcell-template-intelligence/v1"),
            ("created_at_utc", now),
            ("period", period),
            ("template_catalog", _rel(template_catalog_path, repo_root)),
            ("template_selection", _rel(template_selection_path, repo_root)),
            ("scaffold", _rel(scaffold_path, repo_root)),
            ("visual_plan", _rel(visual_plan_path, repo_root)),
            ("capability_map", _rel(capability_map_path, repo_root)),
        ],
    )

    catalog_by_relative: dict[str, dict[str, Any]] = {}
    for item in template_catalog:
        relative = str(item.get("relative_path") or "")
        catalog_by_relative[relative] = item
        named_payloads = int(item.get("named_thinkcell_payloads") or 0)
        conn.execute(
            """
            INSERT INTO template_catalog VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                relative,
                int(item.get("slide_count") or 0),
                int(item.get("chart_refs") or 0),
                int(item.get("graphic_frames") or 0),
                int(item.get("pictures") or 0),
                int(item.get("ole_objects") or 0),
                int(item.get("tag_files") or 0),
                named_payloads,
                "direct_ppttc_candidate" if named_payloads else "reference_or_patch_only",
                1 if item.get("render_candidate") else 0,
                _json(item.get("text_sample") or []),
            ),
        )

    for family in template_selection.get("selected_families", []):
        template = str(family.get("template") or "")
        template_relative = _template_relative(template)
        catalog = catalog_by_relative.get(template_relative, {})
        named_payloads = int(catalog.get("named_thinkcell_payloads") or 0)
        status = str(family.get("status") or "")
        conn.execute(
            "INSERT INTO selected_family VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(family.get("family") or ""),
                template,
                template_relative,
                status,
                _family_posture(status, named_payloads),
                _json(family.get("use_for") or []),
                _json(family.get("deck_targets") or []),
                1 if catalog else 0,
                int(catalog.get("slide_count") or 0) if catalog else None,
                int(catalog.get("chart_refs") or 0) if catalog else None,
                named_payloads if catalog else None,
            ),
        )

    for capability in capability_map.get("capabilities", []):
        conn.execute(
            "INSERT INTO capability VALUES (?, ?, ?, ?)",
            (
                str(capability.get("id") or ""),
                str(capability.get("status") or ""),
                capability.get("production_rule"),
                _json(capability.get("entrypoints") or []),
            ),
        )

    contracts_by_id: dict[str, dict[str, Any]] = {}
    for contract in scaffold.get("contracts", []):
        contract_id = str(contract.get("name") or "")
        contracts_by_id[contract_id] = contract
        proof_path = (
            repo_root
            / "state"
            / "thinkcell_bridge"
            / "build_scaffold"
            / period
            / "work"
            / contract_id
            / f"{contract_id}-proof.json"
        )
        proof = _read_json(proof_path) if proof_path.exists() else {}
        conn.execute(
            "INSERT INTO contract VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                contract_id,
                str(contract.get("priority") or ""),
                str(contract.get("family") or ""),
                contract.get("thinkcell_template_family"),
                _first_family_match(contract),
                str(contract.get("supported_lane") or ""),
                contract.get("guardrail"),
                contract.get("fallback"),
                contract.get("readiness"),
                contract.get("proof_status"),
                _rel(proof_path, repo_root),
                proof.get("deck"),
                proof.get("render_dir"),
            ),
        )

    candidate_rows: list[dict[str, Any]] = []
    for manifest_path in candidate_manifest_paths:
        if not manifest_path.exists():
            continue
        manifest = _read_json(manifest_path)
        run_id = str(manifest.get("run_id") or manifest_path.parent.name)
        director_slug = str(manifest.get("director_slug") or "")
        for candidate in manifest.get("contracts", []):
            contract_id = str(candidate.get("contract_id") or "")
            raw_candidate_path = candidate.get("candidate_path") or candidate.get(
                "intended_candidate_output_path"
            )
            if not raw_candidate_path:
                continue
            candidate_path = _as_repo_path(raw_candidate_path, repo_root)
            audit = audit_pptx(candidate_path)
            validation = candidate.get("candidate_validation")
            publishable = bool(candidate.get("publishable"))
            grade, reason = _candidate_grade(
                audit=audit,
                candidate_validation=validation,
                publishable=publishable,
            )
            row = {
                "run_id": run_id,
                "period": period,
                "director_slug": director_slug,
                "contract_id": contract_id,
                "candidate_path": _rel(candidate_path, repo_root),
                "candidate_status": candidate.get("status"),
                "publishable": publishable,
                "validation_ok": None if validation is None else bool(validation.get("ok")),
                "zip_ok": bool(audit["zip_ok"]),
                "bad_zip_member": audit.get("bad_zip_member"),
                "slide_count": int(audit["slide_count"]),
                "embedding_count": int(audit["embedding_count"]),
                "media_count": int(audit["media_count"]),
                "forbidden_count": len(audit["forbidden_terms"]),
                "forbidden_terms": audit["forbidden_terms"],
                "promotion_grade": grade,
                "blocker_reason": reason,
                "source_manifest": _rel(manifest_path, repo_root),
            }
            candidate_rows.append(row)
            conn.execute(
                """
                INSERT INTO candidate_artifact VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["run_id"],
                    row["period"],
                    row["director_slug"],
                    row["contract_id"],
                    row["candidate_path"],
                    row["candidate_status"],
                    1 if row["publishable"] else 0,
                    None if row["validation_ok"] is None else (1 if row["validation_ok"] else 0),
                    1 if row["zip_ok"] else 0,
                    row["bad_zip_member"],
                    row["slide_count"],
                    row["embedding_count"],
                    row["media_count"],
                    row["forbidden_count"],
                    _json(row["forbidden_terms"]),
                    row["promotion_grade"],
                    row["blocker_reason"],
                    row["source_manifest"],
                ),
            )

    latest_candidates = _candidate_by_contract(candidate_rows)
    recommendation_rows: list[dict[str, Any]] = []
    for director in visual_plan.get("directors", []):
        director_slug = str(director.get("slug") or "")
        for decision in director.get("decisions", []):
            contract_id = str(decision.get("contract") or "")
            contract = contracts_by_id.get(contract_id)
            recommendation, rec_reason, next_action = _recommendation_for_decision(
                decision, contract, latest_candidates.get(contract_id)
            )
            row = {
                "period": period,
                "director_slug": director_slug,
                "director": str(director.get("director") or ""),
                "territory": director.get("territory"),
                "contract_id": contract_id,
                "priority": decision.get("priority"),
                "family": decision.get("family"),
                "visual_decision": str(decision.get("decision") or ""),
                "lane": decision.get("lane"),
                "reason": decision.get("reason"),
                "evidence": decision.get("evidence") or [],
                "template": decision.get("template"),
                "proof_status": decision.get("proof_status"),
                "guardrail": decision.get("guardrail"),
                "recommendation": recommendation,
                "recommendation_reason": rec_reason,
                "next_action": next_action,
            }
            recommendation_rows.append(row)
            conn.execute(
                """
                INSERT INTO director_decision VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["period"],
                    row["director_slug"],
                    row["director"],
                    row["territory"],
                    row["contract_id"],
                    row["priority"],
                    row["family"],
                    row["visual_decision"],
                    row["lane"],
                    row["reason"],
                    _json(row["evidence"]),
                    row["template"],
                    row["proof_status"],
                    row["guardrail"],
                    row["recommendation"],
                    row["recommendation_reason"],
                    row["next_action"],
                ),
            )

    conn.commit()

    report = {
        "schema": "simcorp-thinkcell-template-intelligence-report/v1",
        "created_at_utc": now,
        "period": period,
        "database": _rel(db_path, repo_root),
        "summary": {
            "template_count": len(template_catalog),
            "selected_family_count": len(template_selection.get("selected_families", [])),
            "contract_count": len(scaffold.get("contracts", [])),
            "director_decision_count": len(recommendation_rows),
            "candidate_count": len(candidate_rows),
            "candidate_blocker_count": len(
                [
                    row
                    for row in candidate_rows
                    if row["promotion_grade"]
                    not in {"valid_candidate_needs_promotion_record", "publishable_candidate"}
                ]
            ),
        },
        "hard_constraint": template_selection.get("hard_constraint"),
        "families": [
            {
                "family": row["family"],
                "status": row["status"],
                "automation_posture": row["automation_posture"],
                "template_relative": row["template_relative"],
                "catalog_found": bool(row["catalog_found"]),
                "catalog_named_payloads": row["catalog_named_payloads"],
            }
            for row in conn.execute("SELECT * FROM selected_family ORDER BY family").fetchall()
        ],
        "candidate_findings": [
            {
                "run_id": row["run_id"],
                "contract_id": row["contract_id"],
                "candidate_path": row["candidate_path"],
                "promotion_grade": row["promotion_grade"],
                "blocker_reason": row["blocker_reason"],
                "forbidden_count": row["forbidden_count"],
                "slide_count": row["slide_count"],
                "zip_ok": bool(row["zip_ok"]),
            }
            for row in conn.execute(
                "SELECT * FROM candidate_artifact ORDER BY contract_id, run_id"
            ).fetchall()
        ],
        "recommendations": [
            {
                "director_slug": row["director_slug"],
                "contract_id": row["contract_id"],
                "visual_decision": row["visual_decision"],
                "recommendation": row["recommendation"],
                "recommendation_reason": row["recommendation_reason"],
                "next_action": row["next_action"],
            }
            for row in conn.execute(
                "SELECT * FROM director_decision ORDER BY director_slug, contract_id"
            ).fetchall()
        ],
    }
    report_json_path = output_dir / "thinkcell_template_intelligence_report.json"
    report_md_path = output_dir / "thinkcell_template_intelligence_report.md"
    report_json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    report_md_path.write_text(_render_markdown_report(report), encoding="utf-8")
    conn.close()

    return {
        "db_path": db_path,
        "report_json_path": report_json_path,
        "report_md_path": report_md_path,
        "report": report,
    }


def _first_family_match(contract: dict[str, Any]) -> str | None:
    matches = contract.get("family_matches") or []
    if not matches:
        return None
    first = matches[0]
    if not isinstance(first, dict):
        return None
    return first.get("family") or first.get("template")


def _render_markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# think-cell Template Intelligence Report",
        "",
        f"Generated: `{report['created_at_utc']}`",
        f"Period: `{report['period']}`",
        f"Database: `{report['database']}`",
        "",
        "## Verdict",
        "",
        (
            "The stock think-cell templates are a reference/donor corpus, not direct "
            "automation templates. Use the DB to pick a visual lane only after checking "
            "proof status, data-shape gates, candidate cleanliness, and promotion status."
        ),
        "",
        f"- Templates inventoried: {summary['template_count']}",
        f"- Selected SimCorp families: {summary['selected_family_count']}",
        f"- Quarter contracts: {summary['contract_count']}",
        f"- Candidate artifacts audited: {summary['candidate_count']}",
        f"- Candidate blockers: {summary['candidate_blocker_count']}",
        "",
        "## Family Posture",
        "",
        "| Family | Posture | Catalog named payloads | Status |",
        "|---|---|---:|---|",
    ]
    for family in report["families"]:
        lines.append(
            "| {family} | `{posture}` | {payloads} | {status} |".format(
                family=family["family"],
                posture=family["automation_posture"],
                payloads=family["catalog_named_payloads"]
                if family["catalog_named_payloads"] is not None
                else "",
                status=str(family["status"]).replace("|", "/"),
            )
        )
    lines += [
        "",
        "## Candidate Findings",
        "",
        "| Contract | Run | Grade | Slides | Zip | Blocker |",
        "|---|---|---|---:|---:|---|",
    ]
    for candidate in report["candidate_findings"]:
        lines.append(
            "| {contract} | {run} | `{grade}` | {slides} | {zip_ok} | {reason} |".format(
                contract=candidate["contract_id"],
                run=candidate["run_id"],
                grade=candidate["promotion_grade"],
                slides=candidate["slide_count"],
                zip_ok="yes" if candidate["zip_ok"] else "no",
                reason=str(candidate["blocker_reason"]).replace("|", "/"),
            )
        )
    lines += [
        "",
        "## Director Recommendations",
        "",
        "| Contract | Visual decision | Recommendation | Next action |",
        "|---|---|---|---|",
    ]
    for rec in report["recommendations"]:
        lines.append(
            "| {contract} | {decision} | `{recommendation}` | {next_action} |".format(
                contract=rec["contract_id"],
                decision=rec["visual_decision"],
                recommendation=rec["recommendation"],
                next_action=str(rec["next_action"]).replace("|", "/"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--template-catalog",
        type=Path,
        default=ROOT / "state" / "thinkcell_bridge" / "template_catalog" / "thinkcell_template_catalog.json",
    )
    parser.add_argument(
        "--template-selection",
        type=Path,
        default=ROOT / "config" / "thinkcell_template_selection.may_2026.json",
    )
    parser.add_argument("--scaffold", type=Path, default=None)
    parser.add_argument("--visual-plan", type=Path, default=None)
    parser.add_argument(
        "--capability-map",
        type=Path,
        default=ROOT / "docs" / "thinkcell-corpus" / "thinkcell_infra_capability_map.json",
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        action="append",
        default=[],
        help="Optional insertion-pilot manifest. Repeatable. Defaults to all discovered manifests.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    period = args.period
    output_dir = args.output_dir or (
        repo_root / "state" / "thinkcell_bridge" / "template_intelligence" / period
    )
    scaffold_path = args.scaffold or (
        repo_root
        / "state"
        / "thinkcell_bridge"
        / "build_scaffold"
        / period
        / "thinkcell_build_scaffold.json"
    )
    visual_plan_path = args.visual_plan or (
        repo_root
        / "state"
        / period
        / "__regional__"
        / "thinkcell_visual_plan"
        / "thinkcell_visual_contract_plan.json"
    )
    candidate_manifests = args.candidate_manifest or _discover_candidate_manifests(
        repo_root, period
    )
    result = build_database(
        repo_root=repo_root,
        period=period,
        output_dir=output_dir,
        template_catalog_path=_as_repo_path(args.template_catalog, repo_root),
        template_selection_path=_as_repo_path(args.template_selection, repo_root),
        scaffold_path=_as_repo_path(scaffold_path, repo_root),
        visual_plan_path=_as_repo_path(visual_plan_path, repo_root),
        capability_map_path=_as_repo_path(args.capability_map, repo_root),
        candidate_manifest_paths=[_as_repo_path(path, repo_root) for path in candidate_manifests],
    )
    report = result["report"]
    print(f"db={result['db_path']}")
    print(f"report_json={result['report_json_path']}")
    print(f"report_md={result['report_md_path']}")
    print(
        "summary="
        + json.dumps(
            {
                "templates": report["summary"]["template_count"],
                "contracts": report["summary"]["contract_count"],
                "candidates": report["summary"]["candidate_count"],
                "candidate_blockers": report["summary"]["candidate_blocker_count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(1)
