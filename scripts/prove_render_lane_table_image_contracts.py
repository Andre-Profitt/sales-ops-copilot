#!/usr/bin/env python3
"""Prove table-image render-lane contracts from the render-lane contract JSON."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from prove_thinkcell_build_scaffold_contract import (
    TargetProofSpec,
    _linked_deck,
    _proof_deck,
    _proof_render,
    _proof_workbook,
    _render_deck,
    _workbook,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_DIRECTOR_SLUG = "Jesper-Tyrer"
DEFAULT_CONTRACT = ROOT / "config" / "sd_factory_render_lane_contract.2026-Q2.json"
PROOF_CONTRACT = "TABLEIMAGE_MonthlySlots"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _target_from_contract(contract: dict[str, Any]) -> TargetProofSpec:
    return TargetProofSpec(
        name=str(contract["slot_id"]),
        slide=int(contract["slide"]),
        workbook_name=str(contract["workbook_name"]),
        required_terms=tuple(str(term) for term in contract["required_terms"]),
        min_width_in=float(contract["min_width_in"]),
        min_height_in=float(contract["min_height_in"]),
    )


def _selected_contracts(
    contract_path: Path,
    *,
    target_slot: str | None,
    include_l5_proven: bool,
) -> list[dict[str, Any]]:
    payload = _load_json(contract_path)
    contracts = payload.get("table_image_contracts", [])
    selected: list[dict[str, Any]] = []
    for contract in contracts:
        if target_slot and contract.get("slot_id") != target_slot:
            continue
        if not include_l5_proven and contract.get("proof_status") == "l5_proven":
            continue
        selected.append(contract)
    if target_slot and not selected:
        raise SystemExit(f"unknown table-image slot: {target_slot}")
    return selected


def _work_dir(period: str) -> Path:
    return ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work" / PROOF_CONTRACT


def _asdict_checks(checks: list[Any]) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# Render-Lane Table Image Proof",
        "",
        f"- Status: `{payload['status']}`",
        f"- Period: `{payload['period']}`",
        f"- Director: `{payload['director_slug']}`",
        f"- Deck: `{payload['deck']}`",
        f"- Workbook: `{payload['workbook']}`",
        "",
        "## Targets",
        "",
        "| Slot | Slide | Workbook name | Status |",
        "|---|---:|---|---|",
    ]
    target_status: dict[str, str] = {}
    for check in payload["checks"]:
        for target in check.get("details", {}).get("targets", []):
            name = target.get("target") or target.get("name")
            if name:
                target_status[str(name)] = str(target.get("status"))
    for target in payload["targets"]:
        lines.append(
            f"| `{target['name']}` | {target['slide']} | `{target['workbook_name']}` | "
            f"`{target_status.get(target['name'], 'n/a')}` |"
        )
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Status |",
            "|---|---|",
        ]
    )
    for check in payload["checks"]:
        lines.append(f"| `{check['name']}` | `{check['status']}` |")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def prove_table_image_contracts(
    *,
    period: str,
    director_slug: str,
    contract_path: Path,
    target_slot: str | None,
    include_l5_proven: bool,
) -> dict[str, Any]:
    contracts = _selected_contracts(
        contract_path,
        target_slot=target_slot,
        include_l5_proven=include_l5_proven,
    )
    targets = tuple(_target_from_contract(contract) for contract in contracts)
    work_dir = _work_dir(period)
    work_dir.mkdir(parents=True, exist_ok=True)
    deck = _linked_deck(period, director_slug).expanduser().resolve()
    workbook = _workbook(period, director_slug).expanduser().resolve()
    render_dir = work_dir / "rendered"

    checks = [
        _proof_workbook(workbook, targets),
        _proof_deck(deck, targets),
    ]
    if all(check.status == "pass" for check in checks):
        checks.append(_render_deck(deck, render_dir))
    if all(check.status == "pass" for check in checks):
        checks.append(_proof_render(render_dir, targets))

    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    return {
        "schema": "render-lane-table-image-proof/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "contract": PROOF_CONTRACT,
        "period": period,
        "director_slug": director_slug,
        "deck": str(deck),
        "workbook": str(workbook),
        "render_dir": str(render_dir),
        "targets": [
            {
                "name": target.name,
                "slide": target.slide,
                "workbook_name": target.workbook_name,
                "required_terms": list(target.required_terms),
                "min_width_in": target.min_width_in,
                "min_height_in": target.min_height_in,
            }
            for target in targets
        ],
        "checks": _asdict_checks(checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug", default=DEFAULT_DIRECTOR_SLUG)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--target-slot")
    parser.add_argument(
        "--include-l5-proven",
        action="store_true",
        help="Also re-prove table-image slots that already have L5 component proof.",
    )
    args = parser.parse_args()

    payload = prove_table_image_contracts(
        period=args.period,
        director_slug=args.director_slug,
        contract_path=args.contract,
        target_slot=args.target_slot,
        include_l5_proven=args.include_l5_proven,
    )
    work_dir = _work_dir(args.period)
    suffix = f"-{args.target_slot}" if args.target_slot else ""
    proof_json = work_dir / f"{PROOF_CONTRACT}{suffix}-proof.json"
    proof_md = work_dir / f"{PROOF_CONTRACT}{suffix}-proof.md"
    proof_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(proof_md, payload)
    print(f"status={payload['status']}")
    print(f"proof_json={proof_json}")
    print(f"proof_md={proof_md}")
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
