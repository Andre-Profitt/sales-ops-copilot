#!/usr/bin/env python3
"""Build and prove a hybrid think-cell scaffold contract."""

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
    _proof_deck as _proof_table_deck,
    _proof_render as _proof_table_render,
    _proof_workbook as _proof_table_workbook,
    _render_deck as _render_table_deck,
    _workbook,
)
from prove_thinkcell_native_chart_contract import (
    NativeChartContract,
    _bridge_ppttc,
    _check_bound_package,
    _proof_render as _proof_native_render,
    _render_deck as _render_native_deck,
    _replace_named_element,
    _source_ppttc,
    _write_contract_ppttc,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_DIRECTOR_SLUG = "Jesper-Tyrer"
DEFAULT_CONTRACT = "QTR12_StalePipeline_BarTable"

HYBRID_CONTRACTS: dict[str, dict[str, Any]] = {
    DEFAULT_CONTRACT: {
        "native_chart": NativeChartContract(
            contract=DEFAULT_CONTRACT,
            source_name="S22_StaleActivity",
            target_name=DEFAULT_CONTRACT,
            slide=22,
            required_terms=("3 - Engagement", "6 - Contracting", "ARR (mEUR)"),
        ),
        "table_image_targets": (
            TargetProofSpec(
                name="S22_NamedRiskTriage",
                slide=22,
                workbook_name="S22_NamedRiskTriage",
                required_terms=("Danantara", "Silent 90d+", "PT Bank Mandiri"),
                min_width_in=5.0,
                min_height_in=1.0,
            ),
        ),
    }
}


def _work_dir(period: str, contract: str) -> Path:
    return ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "work" / contract


def _director_name(slug: str) -> str:
    return slug.replace("-", " ")


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# {payload['contract']} Hybrid Proof",
        "",
        f"- Status: `{payload['status']}`",
        f"- Period: `{payload['period']}`",
        f"- Director: `{payload['director_slug']}`",
        f"- Integration scope: `{payload['integration_scope']}`",
        f"- Native bar deck: `{payload['native_chart']['deck']}`",
        f"- Table-image deck: `{payload['table_image']['deck']}`",
        "",
        "## Checks",
        "",
        "| Component | Check | Status |",
        "|---|---|---|",
    ]
    for component in ("native_chart", "table_image"):
        for check in payload[component]["checks"]:
            lines.append(f"| `{component}` | `{check['name']}` | `{check['status']}` |")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _asdict_checks(checks: list[Any]) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]


def prove_qtr12(period: str, director_slug: str) -> dict[str, Any]:
    spec = HYBRID_CONTRACTS[DEFAULT_CONTRACT]
    native_contract: NativeChartContract = spec["native_chart"]
    table_targets: tuple[TargetProofSpec, ...] = spec["table_image_targets"]

    work_dir = _work_dir(period, DEFAULT_CONTRACT)
    work_dir.mkdir(parents=True, exist_ok=True)

    seed = work_dir / f"{DEFAULT_CONTRACT}-native-bar-seed.pptx"
    ppttc = work_dir / f"{DEFAULT_CONTRACT}-native-bar-{period}.ppttc"
    bound = work_dir / f"{DEFAULT_CONTRACT}-native-bar-{period}-bound.pptx"
    native_render_dir = work_dir / "rendered_native_bar"

    source_ppttc = _source_ppttc(period, director_slug)
    native_checks = [
        _replace_named_element(
            native_contract.source_seed,
            seed,
            native_contract.source_name,
            native_contract.target_name,
        ),
        _write_contract_ppttc(source_ppttc, ppttc, seed, native_contract),
    ]
    if all(check.status == "pass" for check in native_checks):
        native_checks.append(_bridge_ppttc(ppttc, seed, bound))
    if all(check.status == "pass" for check in native_checks):
        native_checks.append(_check_bound_package(bound, native_contract))
    if all(check.status == "pass" for check in native_checks):
        native_checks.append(_render_native_deck(bound, native_render_dir))
    if all(check.status == "pass" for check in native_checks):
        native_checks.append(_proof_native_render(native_render_dir, native_contract))

    table_deck = _linked_deck(period, director_slug).expanduser().resolve()
    table_workbook = _workbook(period, director_slug).expanduser().resolve()
    table_render_dir = work_dir / "rendered_table_image"
    table_checks = [
        _proof_table_workbook(table_workbook, table_targets),
        _proof_table_deck(table_deck, table_targets),
    ]
    if all(check.status == "pass" for check in table_checks):
        table_checks.append(_render_table_deck(table_deck, table_render_dir))
    if all(check.status == "pass" for check in table_checks):
        table_checks.append(_proof_table_render(table_render_dir, table_targets))

    status = (
        "pass"
        if all(check.status == "pass" for check in native_checks + table_checks)
        else "fail"
    )
    return {
        "schema": "thinkcell-hybrid-build-proof/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": status,
        "contract": DEFAULT_CONTRACT,
        "period": period,
        "director_slug": director_slug,
        "director_name": _director_name(director_slug),
        "integration_scope": "component_lane_proof_not_production_slide_polish",
        "deck": str(bound),
        "workbook": str(table_workbook),
        "render_dir": str(work_dir),
        "targets": [
            {
                "name": native_contract.target_name,
                "source_name": native_contract.source_name,
                "slide": native_contract.slide,
                "component": "native_chart",
                "required_terms": list(native_contract.required_terms),
            },
            *[
                {
                    "name": target.name,
                    "workbook_name": target.workbook_name,
                    "slide": target.slide,
                    "component": "table_image",
                    "required_terms": list(target.required_terms),
                }
                for target in table_targets
            ],
        ],
        "native_chart": {
            "deck": str(bound),
            "seed_pptx": str(seed),
            "ppttc": str(ppttc),
            "source_ppttc": str(source_ppttc),
            "render_dir": str(native_render_dir),
            "checks": _asdict_checks(native_checks),
        },
        "table_image": {
            "deck": str(table_deck),
            "workbook": str(table_workbook),
            "render_dir": str(table_render_dir),
            "checks": _asdict_checks(table_checks),
        },
        "checks": _asdict_checks(native_checks + table_checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--director-slug", default=DEFAULT_DIRECTOR_SLUG)
    parser.add_argument("--contract", default=DEFAULT_CONTRACT)
    args = parser.parse_args()

    if args.contract != DEFAULT_CONTRACT:
        raise SystemExit(f"unsupported hybrid contract: {args.contract}")

    payload = prove_qtr12(args.period, args.director_slug)
    work_dir = _work_dir(args.period, args.contract)
    proof_json = work_dir / f"{args.contract}-proof.json"
    proof_md = work_dir / f"{args.contract}-proof.md"
    proof_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    _write_markdown(proof_md, payload)
    print(f"status={payload['status']}")
    print(f"proof_json={proof_json}")
    print(f"proof_md={proof_md}")
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
