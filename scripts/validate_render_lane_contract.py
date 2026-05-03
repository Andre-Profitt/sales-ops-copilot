#!/usr/bin/env python3
"""Validate the Sales Director render-lane contract."""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


VALID_STATUSES = {
    "contracted",
    "contracted_ai_cached_required",
    "l5_component_proven",
    "needs_l5_component_proof",
    "needs_table_image_contract",
    "table_image_contract_defined",
}


def _error(errors: list[str], message: str) -> None:
    errors.append(message)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _defined_names(workbook_path: Path) -> dict[str, str]:
    with zipfile.ZipFile(workbook_path) as zf:
        workbook_xml = zf.read("xl/workbook.xml")
    root = ET.fromstring(workbook_xml)
    namespace = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    names: dict[str, str] = {}
    for node in root.findall("x:definedNames/x:definedName", namespace):
        name = node.attrib.get("name")
        if name:
            names[name] = (node.text or "").strip()
    return names


def _expected_defined_name_attr(sheet: str, cell_range: str) -> str:
    return f"'{sheet}'!{cell_range}"


def validate_contract(contract_path: Path, *, expected_slots: int) -> list[str]:
    root = contract_path.resolve().parent.parent
    contract = _load_json(contract_path)
    errors: list[str] = []

    if contract.get("schema") != "sd-factory-render-lane-contract/v1":
        _error(errors, "schema must be sd-factory-render-lane-contract/v1")

    lanes = contract.get("lanes")
    if not isinstance(lanes, dict) or not lanes:
        _error(errors, "lanes must be a non-empty object")
        lanes = {}

    component_proofs = contract.get("component_proofs")
    if not isinstance(component_proofs, list):
        _error(errors, "component_proofs must be a list")
        component_proofs = []

    proof_by_contract: dict[str, dict[str, Any]] = {}
    for proof in component_proofs:
        contract_name = proof.get("contract")
        if not contract_name:
            _error(errors, "component proof is missing contract")
            continue
        if contract_name in proof_by_contract:
            _error(errors, f"duplicate component proof: {contract_name}")
        proof_by_contract[contract_name] = proof
        proof_path = proof.get("proof_path")
        if not proof_path:
            _error(errors, f"{contract_name}: missing proof_path")
        elif not (root / proof_path).exists():
            _error(errors, f"{contract_name}: proof_path does not exist: {proof_path}")
        if proof.get("lane") not in lanes:
            _error(errors, f"{contract_name}: unknown lane {proof.get('lane')!r}")

    table_image_contracts = contract.get("table_image_contracts")
    if not isinstance(table_image_contracts, list):
        _error(errors, "table_image_contracts must be a list")
        table_image_contracts = []

    table_contract_by_slot: dict[str, dict[str, Any]] = {}
    table_contract_by_workbook_name: dict[str, dict[str, Any]] = {}
    defined_name_cache: dict[Path, dict[str, str]] = {}
    for table_contract in table_image_contracts:
        slot_id = table_contract.get("slot_id")
        workbook_name = table_contract.get("workbook_name")
        if not slot_id:
            _error(errors, "table image contract is missing slot_id")
            continue
        if not workbook_name:
            _error(errors, f"{slot_id}: table image contract missing workbook_name")
            continue
        if slot_id in table_contract_by_slot:
            _error(errors, f"duplicate table image slot contract: {slot_id}")
        if workbook_name in table_contract_by_workbook_name:
            _error(errors, f"duplicate table image workbook name: {workbook_name}")
        table_contract_by_slot[slot_id] = table_contract
        table_contract_by_workbook_name[workbook_name] = table_contract

        source_builder = table_contract.get("source_builder")
        if source_builder and not (root / source_builder).exists():
            _error(errors, f"{slot_id}: source_builder does not exist: {source_builder}")

        proof_status = table_contract.get("proof_status")
        component_proof = table_contract.get("component_proof")
        proof_path = table_contract.get("proof_path")
        if proof_status == "l5_proven":
            if component_proof and component_proof not in proof_by_contract:
                _error(errors, f"{slot_id}: l5 table contract missing component proof {component_proof}")
            if not component_proof and not proof_path:
                _error(errors, f"{slot_id}: l5 table contract requires component_proof or proof_path")
            if proof_path and not (root / str(proof_path)).exists():
                _error(errors, f"{slot_id}: table proof_path does not exist: {proof_path}")

        required_terms = table_contract.get("required_terms")
        if not isinstance(required_terms, list) or not required_terms:
            _error(errors, f"{slot_id}: table image contract requires non-empty required_terms")
        for dimension in ("min_width_in", "min_height_in"):
            value = table_contract.get(dimension)
            if not isinstance(value, (int, float)) or value <= 0:
                _error(errors, f"{slot_id}: table image contract requires positive {dimension}")

        workbook = table_contract.get("representative_workbook")
        sheet = table_contract.get("sheet")
        cell_range = table_contract.get("range")
        if not workbook or not sheet or not cell_range:
            _error(errors, f"{slot_id}: table image contract requires workbook, sheet, and range")
            continue
        workbook_path = root / workbook
        if not workbook_path.exists():
            _error(errors, f"{slot_id}: representative workbook does not exist: {workbook}")
            continue
        if workbook_path not in defined_name_cache:
            defined_name_cache[workbook_path] = _defined_names(workbook_path)
        actual = defined_name_cache[workbook_path].get(str(workbook_name))
        expected = _expected_defined_name_attr(str(sheet), str(cell_range))
        if actual != expected:
            _error(
                errors,
                f"{slot_id}: workbook name {workbook_name} expected {expected}, found {actual}",
            )

    monthly_slots = contract.get("monthly_slots")
    if not isinstance(monthly_slots, list):
        _error(errors, "monthly_slots must be a list")
        monthly_slots = []

    if len(monthly_slots) != expected_slots:
        _error(errors, f"monthly_slots expected {expected_slots}, found {len(monthly_slots)}")

    seen_slots: set[str] = set()
    for slot in monthly_slots:
        slot_id = slot.get("slot_id")
        if not slot_id:
            _error(errors, "monthly slot is missing slot_id")
            continue
        if slot_id in seen_slots:
            _error(errors, f"duplicate monthly slot: {slot_id}")
        seen_slots.add(slot_id)

        primary_lane = slot.get("primary_lane")
        if primary_lane not in lanes:
            _error(errors, f"{slot_id}: unknown primary_lane {primary_lane!r}")

        status = slot.get("status")
        if status not in VALID_STATUSES:
            _error(errors, f"{slot_id}: unknown status {status!r}")

        if status == "l5_component_proven":
            component_proof = slot.get("component_proof")
            if not component_proof:
                _error(errors, f"{slot_id}: l5_component_proven requires component_proof")
            elif component_proof not in proof_by_contract:
                _error(errors, f"{slot_id}: missing component proof {component_proof}")

        if status == "table_image_contract_defined":
            table_image_contract = slot.get("table_image_contract")
            if not table_image_contract:
                _error(errors, f"{slot_id}: table_image_contract_defined requires table_image_contract")
            elif table_image_contract not in table_contract_by_workbook_name:
                _error(errors, f"{slot_id}: missing table image contract {table_image_contract}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("config/sd_factory_render_lane_contract.2026-Q2.json"),
    )
    parser.add_argument("--expected-slots", type=int, default=42)
    args = parser.parse_args()

    errors = validate_contract(args.contract, expected_slots=args.expected_slots)
    if errors:
        print("render_lane_contract: fail")
        for err in errors:
            print(f"- {err}")
        return 1

    contract = _load_json(args.contract)
    print("render_lane_contract: pass")
    print(f"monthly_slots={len(contract['monthly_slots'])}")
    print(f"component_proofs={len(contract['component_proofs'])}")
    print(f"table_image_contracts={len(contract['table_image_contracts'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
