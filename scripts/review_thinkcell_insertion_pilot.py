#!/usr/bin/env python3
"""Review a think-cell insertion pilot against the current meeting-spine slide."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CURRENT_SLIDE = (
    ROOT
    / "state"
    / "2026-Q2"
    / "__regional__"
    / "visual_gate"
    / "review_package"
    / "Jesper-Tyrer-LAND-2026-Q2-meeting-spine"
    / "png"
    / "slide-05.png"
)


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _run_dir(period: str, run_id: str) -> Path:
    return ROOT / "state" / period / "__regional__" / "thinkcell_insertion_pilot" / run_id


def _load_manifest(period: str, run_id: str) -> dict[str, Any]:
    path = _run_dir(period, run_id) / "manifest.json"
    if not path.exists():
        raise SystemExit(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _contract(manifest: dict[str, Any], contract_id: str) -> dict[str, Any]:
    for contract in manifest.get("contracts", []):
        if contract.get("contract_id") == contract_id:
            return contract
    raise SystemExit(f"contract {contract_id} not found in manifest")


def _render_candidate(candidate: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "render_deck_for_review.py"),
            str(candidate),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "candidate render failed\n"
            f"stdout:\n{completed.stdout[-2000:]}\n"
            f"stderr:\n{completed.stderr[-2000:]}"
        )
    pngs = sorted((output_dir / "png").glob("slide-*.png"))
    if not pngs:
        raise SystemExit(f"candidate render produced no PNGs in {output_dir / 'png'}")
    return pngs[0]


def _fit(image: Image.Image, *, width: int) -> Image.Image:
    ratio = width / image.width
    return image.resize((width, int(image.height * ratio)), Image.Resampling.LANCZOS)


def _label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    try:
        font = ImageFont.truetype("Arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    draw.text(xy, text, fill=(26, 29, 49), font=font)


def _contact_sheet(current_png: Path, candidate_png: Path, output: Path) -> None:
    current = _fit(Image.open(current_png).convert("RGB"), width=900)
    candidate = _fit(Image.open(candidate_png).convert("RGB"), width=900)
    label_h = 56
    gap = 30
    width = current.width + candidate.width + gap
    height = label_h + max(current.height, candidate.height)
    sheet = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    _label(draw, (0, 14), "Current meeting-spine slide")
    _label(draw, (current.width + gap, 14), "think-cell QTR04 pilot candidate")
    sheet.paste(current, (0, label_h))
    sheet.paste(candidate, (current.width + gap, label_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)


def _stock_residue(candidate: Path) -> list[str]:
    import zipfile

    residue_terms = [
        "Insert chart title here",
        "Insert your desired text",
        "Lorem ipsum",
        "Company 1",
        "Correlation:",
        "Item comparison:",
    ]
    with zipfile.ZipFile(candidate) as zf:
        text = "\n".join(
            zf.read(name).decode("utf-8", errors="ignore")
            for name in zf.namelist()
            if name.startswith("ppt/") and name.endswith(".xml")
        )
    return [term for term in residue_terms if term in text]


def _write_review(
    *,
    manifest: dict[str, Any],
    contract: dict[str, Any],
    contract_dir: Path,
    current_png: Path,
    candidate_png: Path,
    contact_sheet: Path,
    decision: str,
    reason: str,
) -> dict[str, Any]:
    candidate = Path(contract["candidate_path"])
    residue = _stock_residue(candidate)
    validation = contract.get("candidate_validation") or {}
    improvement_asserted = decision == "assert-improvement"
    insertion_allowed = improvement_asserted and validation.get("ok") is True and not residue
    record = {
        "schema": "thinkcell-insertion-decision-record/v1",
        "created_at_utc": _utc_now(),
        "period": manifest["period"],
        "run_id": manifest["run_id"],
        "director_slug": manifest["director_slug"],
        "director_name": manifest["director_name"],
        "contract_id": contract["contract_id"],
        "candidate_path": str(candidate),
        "current_slide_png": str(current_png),
        "candidate_png": str(candidate_png),
        "side_by_side_contact_sheet": str(contact_sheet),
        "eligibility_status": "pass" if contract.get("eligibility", {}).get("decision") == "ready" else "fail",
        "candidate_validation": validation,
        "stock_residue_terms": residue,
        "leadership_decision_improvement_asserted": improvement_asserted,
        "decision_status": "pass" if insertion_allowed else "blocked",
        "decision_reason": reason,
        "production_insertion_allowed": insertion_allowed,
        "publish_blocked": True,
        "publish_block_reason": (
            "SharePoint remains blocked until P0 publish-gate hardening lands and "
            "a one-director pilot asserts leadership decision improvement."
        ),
        "guardrails": {
            "arr_axis": "APTS_Opportunity_ARR__c",
            "type_filter": "Type IN ('Land','Expand')",
            "currency_basis": "FX-converted EUR Salesforce report aggregate; no raw multi-currency SOQL SUM",
            "renewal_acv_blended": False,
            "native_powerpoint_table": False,
        },
    }
    preflight = {
        "schema": "thinkcell-insertion-pilot-preflight/v1",
        "created_at_utc": record["created_at_utc"],
        "contract_id": contract["contract_id"],
        "candidate_path": str(candidate),
        "candidate_exists": candidate.exists(),
        "candidate_validation": validation,
        "stock_residue_terms": residue,
        "current_slide_png_exists": current_png.exists(),
        "candidate_png_exists": candidate_png.exists(),
        "side_by_side_contact_sheet_exists": contact_sheet.exists(),
    }
    contract_dir.mkdir(parents=True, exist_ok=True)
    (contract_dir / "manifest.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    (contract_dir / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    (contract_dir / "decision_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default="2026-Q2")
    parser.add_argument("--director-slug", default="Jesper-Tyrer")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--contract", default="QTR04_DealRisk_Scatter")
    parser.add_argument("--current-slide-png", type=Path, default=DEFAULT_CURRENT_SLIDE)
    parser.add_argument("--decision", choices=["block", "assert-improvement"], default="block")
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()

    manifest = _load_manifest(args.period, args.run_id)
    if manifest.get("director_slug") != args.director_slug:
        raise SystemExit(f"manifest director is {manifest.get('director_slug')}, not {args.director_slug}")
    contract = _contract(manifest, args.contract)
    candidate = Path(contract.get("candidate_path") or contract.get("intended_candidate_output_path") or "")
    if not candidate.exists():
        raise SystemExit(f"candidate not found: {candidate}")
    if not args.current_slide_png.exists():
        raise SystemExit(f"current slide PNG not found: {args.current_slide_png}")

    contract_dir = _run_dir(args.period, args.run_id) / args.director_slug / args.contract
    candidate_png = _render_candidate(candidate, contract_dir / "rendered_candidate")
    contact_sheet = contract_dir / "side_by_side_contact_sheet.jpg"
    _contact_sheet(args.current_slide_png, candidate_png, contact_sheet)
    record = _write_review(
        manifest=manifest,
        contract=contract,
        contract_dir=contract_dir,
        current_png=args.current_slide_png,
        candidate_png=candidate_png,
        contact_sheet=contact_sheet,
        decision=args.decision,
        reason=args.reason,
    )
    print(f"decision_status={record['decision_status']}")
    print(f"decision_record={contract_dir / 'decision_record.json'}")
    print(f"contact_sheet={contact_sheet}")
    return 0 if record["decision_status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
