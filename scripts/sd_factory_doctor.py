#!/usr/bin/env python3
"""Preflight the Sales Director deck factory without mutating deck assets."""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Check:
    name: str
    status: str
    severity: str
    finding: str
    evidence: str | None = None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_binary(name: str, *, severity: str) -> Check:
    path = shutil.which(name)
    return Check(
        name=f"binary:{name}",
        status="pass" if path else "fail",
        severity=severity,
        finding=f"found at {path}" if path else "not found on PATH",
        evidence=path,
    )


def _check_python_module(name: str, *, severity: str) -> Check:
    found = importlib.util.find_spec(name) is not None
    return Check(
        name=f"python_module:{name}",
        status="pass" if found else "fail",
        severity=severity,
        finding="importable" if found else "not importable",
    )


def _latest_manifest(folder: Path) -> Path | None:
    candidates = sorted(folder.glob("*/manifest.json"))
    return candidates[-1] if candidates else None


def _check_latest_production_manifest(period: str) -> Check:
    folder = ROOT / "state" / period / "__regional__" / "production_runs"
    manifest_path = _latest_manifest(folder)
    if not manifest_path:
        return Check(
            name="latest_production_manifest",
            status="fail",
            severity="critical",
            finding=f"no manifest found under {folder}",
        )
    manifest = _load_json(manifest_path)
    status = manifest.get("status")
    step_count = len(manifest.get("steps") or [])
    return Check(
        name="latest_production_manifest",
        status="pass" if status == "pass" else "fail",
        severity="critical",
        finding=f"status={status}; steps={step_count}",
        evidence=str(manifest_path),
    )


def _check_sharepoint_manifest(period: str) -> Check:
    context = context_for_period(period)
    path = ROOT / "state" / period / "__regional__" / context.sharepoint_validation_manifest_name
    if not path.exists():
        return Check(
            name="sharepoint_validation_manifest",
            status="warn",
            severity="warning",
            finding=f"missing {path}",
        )
    payload = _load_json(path)
    status = payload.get("status")
    expected = payload.get("expected_count")
    present = payload.get("present_expected_count")
    mismatches = len(payload.get("size_mismatch") or [])
    stale = len(payload.get("stale_top_level_files") or [])
    missing = len(payload.get("missing") or [])
    return Check(
        name="sharepoint_validation_manifest",
        status="pass" if status == "pass" and expected == present and not mismatches and not stale and not missing else "fail",
        severity="critical",
        finding=f"status={status}; assets={present}/{expected}; missing={missing}; stale={stale}; size_mismatch={mismatches}",
        evidence=str(path),
    )


def _check_thinkcell_scaffold(period: str) -> Check:
    path = ROOT / "state" / "thinkcell_bridge" / "build_scaffold" / period / "thinkcell_build_scaffold.json"
    if not path.exists():
        return Check(
            name="thinkcell_build_scaffold",
            status="warn",
            severity="warning",
            finding=f"missing {path}",
        )
    payload = _load_json(path)
    contracts = payload.get("contracts") or []
    runtime_status = (payload.get("runtime") or {}).get("status")
    proven = sum(1 for contract in contracts if contract.get("proof_status") == "pass")
    return Check(
        name="thinkcell_build_scaffold",
        status="pass" if runtime_status == "pass" and contracts else "fail",
        severity="warning",
        finding=f"runtime={runtime_status}; contracts={len(contracts)}; l5_proven={proven}",
        evidence=str(path),
    )


def _check_review_package(period: str) -> Check:
    context = context_for_period(period)
    package_dir = context.review_package_dir
    decks = sorted(package_dir.glob(context.meeting_spine_pattern)) if package_dir.exists() else []
    lock_files = sorted(package_dir.glob("~$*")) if package_dir.exists() else []
    ok = package_dir.exists() and len(decks) == 9 and not lock_files
    return Check(
        name="downloads_review_package",
        status="pass" if ok else "fail",
        severity="critical",
        finding=f"exists={package_dir.exists()}; decks={len(decks)}; lock_files={len(lock_files)}",
        evidence=str(package_dir),
    )


def _check_azure_token() -> Check:
    command = [
        "az",
        "account",
        "get-access-token",
        "--resource",
        "https://graph.microsoft.com",
        "--query",
        "accessToken",
        "-o",
        "tsv",
    ]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=30)
    token_present = result.returncode == 0 and bool(result.stdout.strip())
    finding = "Graph token available" if token_present else (result.stderr.strip() or "Graph token unavailable")
    return Check(
        name="azure_graph_token",
        status="pass" if token_present else "fail",
        severity="critical",
        finding=finding,
    )


def build_doctor(period: str, *, check_azure_token: bool) -> dict[str, Any]:
    context = context_for_period(period)
    checks = [
        Check(
            name="period_context",
            status="pass",
            severity="critical",
            finding=f"{context.period}; {context.month_label}; snapshot={context.snapshot_date}; folder={context.sharepoint_folder}",
        ),
        _check_binary("soffice", severity="critical"),
        _check_binary("pdftoppm", severity="critical"),
        _check_binary("az", severity="warning"),
        _check_python_module("pptx", severity="critical"),
        _check_python_module("PIL", severity="critical"),
        _check_python_module("requests", severity="critical"),
        _check_python_module("openpyxl", severity="critical"),
        _check_python_module("duckdb", severity="warning"),
        _check_latest_production_manifest(period),
        _check_review_package(period),
        _check_sharepoint_manifest(period),
        _check_thinkcell_scaffold(period),
    ]
    if check_azure_token:
        checks.append(_check_azure_token())

    critical_failures = [check for check in checks if check.status == "fail" and check.severity == "critical"]
    warning_failures = [check for check in checks if check.status == "fail" and check.severity != "critical"]
    status = "pass" if not critical_failures else "fail"
    if status == "pass" and warning_failures:
        status = "warn"
    return {
        "schema": "sales-director-factory-doctor/v1",
        "status": status,
        "period": context.period,
        "month_label": context.month_label,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "critical_failures": [asdict(check) for check in critical_failures],
        "warning_failures": [asdict(check) for check in warning_failures],
        "checks": [asdict(check) for check in checks],
    }


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Sales Director Factory Doctor",
        "",
        f"- Status: `{payload['status']}`",
        f"- Period: `{payload['period']}`",
        f"- Generated UTC: `{payload['generated_at_utc']}`",
        "",
        "| Check | Status | Severity | Finding | Evidence |",
        "|---|---:|---:|---|---|",
    ]
    for check in payload["checks"]:
        lines.append(
            "| {name} | {status} | {severity} | {finding} | {evidence} |".format(
                name=check["name"],
                status=check["status"],
                severity=check["severity"],
                finding=str(check["finding"]).replace("|", "/"),
                evidence=check.get("evidence") or "",
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--check-azure-token", action="store_true")
    args = parser.parse_args()

    payload = build_doctor(args.period, check_azure_token=args.check_azure_token)
    output_dir = ROOT / "state" / args.period / "__regional__" / "factory_plan"
    json_output = args.json_output or output_dir / "factory_doctor_report.json"
    markdown_output = args.markdown_output or output_dir / "factory_doctor_report.md"
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(payload, markdown_output)
    print(f"status={payload['status']}")
    print(f"json={json_output}")
    print(f"markdown={markdown_output}")
    return 0 if payload["status"] in {"pass", "warn"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
