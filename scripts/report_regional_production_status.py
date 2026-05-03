#!/usr/bin/env python3
"""Summarize the current regional Sales Director deck production state."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(name: str) -> str:
    return name.replace(" ", "-")


def _latest_manifest(folder: Path) -> tuple[Path | None, dict[str, Any] | None]:
    manifests = sorted(folder.glob("*/manifest.json"))
    if not manifests:
        return None, None
    path = manifests[-1]
    return path, _load_json(path)


def _latest_manifest_with_directors(folder: Path, minimum: int) -> tuple[Path | None, dict[str, Any] | None]:
    candidates = sorted(folder.glob("*/manifest.json"), reverse=True)
    for path in candidates:
        manifest = _load_json(path)
        if len(manifest.get("directors") or []) >= minimum:
            return path, manifest
    return None, None


def _step_counts(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        status = str(step.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    return counts


def _run_summary(path: Path | None, manifest: dict[str, Any] | None) -> dict[str, Any] | None:
    if not path or not manifest:
        return None
    steps = manifest.get("steps") or []
    return {
        "path": str(path),
        "run_dir": str(path.parent),
        "status": manifest.get("status"),
        "created_at_utc": manifest.get("created_at_utc"),
        "review_package": manifest.get("review_package"),
        "director_count": len(manifest.get("directors") or []),
        "step_counts": _step_counts(steps),
        "steps": [
            {
                "name": step.get("name"),
                "status": step.get("status"),
                "elapsed_seconds": step.get("elapsed_seconds"),
            }
            for step in steps
        ],
    }


def _package_summary(path: Path, validation: dict[str, Any] | None) -> dict[str, Any]:
    pptx_paths = sorted(path.glob("*.pptx")) if path.exists() else []
    pptx_files = [p.name for p in pptx_paths]
    pptx_mtimes = {
        p.name: dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        for p in pptx_paths
    }
    lock_files = sorted(p.name for p in path.glob("~$*")) if path.exists() else []
    return {
        "path": str(path),
        "exists": path.exists(),
        "pptx_count": len(pptx_files),
        "pptx_files": pptx_files,
        "pptx_mtimes": pptx_mtimes,
        "lock_files": lock_files,
        "validation_status": (validation or {}).get("status"),
        "expected_deck_count": (validation or {}).get("expected_deck_count"),
        "present_deck_count": (validation or {}).get("present_deck_count"),
        "missing_decks": (validation or {}).get("missing_decks") or [],
        "extra_decks": (validation or {}).get("extra_decks") or [],
        "missing_reports": (validation or {}).get("missing_reports") or [],
    }


def _sharepoint_summary(regional: Path, context: Any) -> dict[str, Any]:
    validation_path = regional / context.sharepoint_validation_manifest_name
    upload_path = regional / context.sharepoint_upload_manifest_name
    containment_path = regional / context.sharepoint_containment_manifest_name
    validation = _load_json(validation_path) if validation_path.exists() else None
    upload = _load_json(upload_path) if upload_path.exists() else None
    containment = _load_json(containment_path) if containment_path.exists() else None
    return {
        "validation_path": str(validation_path) if validation_path.exists() else None,
        "upload_path": str(upload_path) if upload_path.exists() else None,
        "containment_path": str(containment_path) if containment_path.exists() else None,
        "status": (validation or {}).get("status") or "missing",
        "expected_count": (validation or {}).get("expected_count"),
        "present_expected_count": (validation or {}).get("present_expected_count"),
        "missing": (validation or {}).get("missing") or [],
        "stale_top_level_files": (validation or {}).get("stale_top_level_files") or [],
        "size_mismatch": (validation or {}).get("size_mismatch") or [],
        "upload_status": (upload or {}).get("status"),
        "uploaded_count": len((upload or {}).get("uploaded") or []),
        "containment_status": (containment or {}).get("status"),
        "quarantined_count": len((containment or {}).get("moved") or []),
    }


def _publish_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing", "directors": []}
    rows = _load_json(path)
    directors = []
    for row in rows:
        metrics = row.get("metrics") or {}
        directors.append(
            {
                "slug": row.get("slug"),
                "territory": row.get("territory"),
                "status": row.get("status"),
                "factory_status": row.get("factory_status"),
                "readiness_status": row.get("readiness_status"),
                "blocker_count": len(row.get("blockers") or []),
                "polish_count": len(row.get("polish_items") or []),
                "named_thinkcell_elements_present": metrics.get("named_thinkcell_elements_present"),
                "table_image_count": len(metrics.get("table_image_pic_slides") or []),
                "freshness": metrics.get("freshness") or {},
            }
        )
    ok = bool(directors) and all(row["status"] == "pass" for row in directors)
    return {
        "path": str(path),
        "status": "pass" if ok else "fail",
        "director_count": len(directors),
        "directors": directors,
    }


def _expected_slugs() -> list[str]:
    return [_slug(str(director["name"])) for director in canonical_directors()]


def build_status(period: str) -> dict[str, Any]:
    context = context_for_period(period)
    regional = ROOT / "state" / period / "__regional__"
    production_path, production_manifest = _latest_manifest(regional / "production_runs")
    latest_table_path, latest_table_manifest = _latest_manifest(regional / "table_image_factory_runs")
    full_table_path, full_table_manifest = _latest_manifest_with_directors(
        regional / "table_image_factory_runs",
        minimum=len(_expected_slugs()),
    )

    validation = None
    if production_path:
        validation_path = production_path.parent / "review_package_validation.json"
        if validation_path.exists():
            validation = _load_json(validation_path)

    publish = _publish_summary(regional / "publish_gate" / "regional_publish_gate.json")
    package = _package_summary(context.review_package_dir, validation)
    sharepoint = _sharepoint_summary(regional, context)
    expected_slugs = _expected_slugs()
    publish_slugs = [row["slug"] for row in publish.get("directors", [])]
    missing_publish_slugs = [slug for slug in expected_slugs if slug not in publish_slugs]

    status = "pass"
    failures: list[str] = []
    if (production_manifest or {}).get("status") != "pass":
        failures.append("latest production run is not pass")
    if (validation or {}).get("status") != "pass":
        failures.append("review package validation is not pass")
    if publish.get("status") != "pass":
        failures.append("regional publish gate is not pass")
    if missing_publish_slugs:
        failures.append(f"publish gate missing directors: {', '.join(missing_publish_slugs)}")
    if package["pptx_count"] != len(expected_slugs):
        failures.append(f"Downloads package has {package['pptx_count']} decks; expected {len(expected_slugs)}")
    if package["lock_files"]:
        failures.append("Downloads package contains Office lock files")
    if sharepoint.get("status") not in {"missing", "pass"}:
        failures.append("SharePoint validation is not pass")
    if failures:
        status = "fail"

    residual_risks = [
        "Current deck tables are linked table-image objects driven by Excel, not native think-cell tables.",
        "Full PowerPoint/think-cell refresh still depends on the Windows VM and Mac PowerPoint finalization bridge.",
        "The validated period context is May 2026 / 2026-Q2 only; quarter-roll logic is intentionally blocked until certified.",
    ]
    if sharepoint.get("status") != "pass":
        residual_risks.append("SharePoint upload is not part of the latest green verification run.")

    return {
        "schema": "regional-production-status/v1",
        "status": status,
        "failures": failures,
        "period": context.period,
        "month_label": context.month_label,
        "snapshot_date": context.snapshot_date,
        "kickoff_date": context.kickoff_date,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "latest_production_run": _run_summary(production_path, production_manifest),
        "latest_table_image_run": _run_summary(latest_table_path, latest_table_manifest),
        "latest_full_table_image_run": _run_summary(full_table_path, full_table_manifest),
        "publish_gate": publish,
        "review_package": package,
        "sharepoint": sharepoint,
        "commands": {
            "fast_package_gate": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --jobs 6",
            "package_plus_sharepoint_validate": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --jobs 6 --sharepoint-validate",
            "package_plus_sharepoint_publish": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --jobs 6 --sharepoint-publish",
            "source_only": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --refresh-source --source-only --jobs 4",
            "one_director_full_refresh": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --director-slug {context.apac_strict_slug} --refresh-source --full-table-image-refresh --jobs 2",
            "all_directors_full_refresh": f".venv/bin/python scripts/run_regional_production_line.py --period {context.period} --refresh-source --full-table-image-refresh --jobs 4",
            "status_report": f".venv/bin/python scripts/report_regional_production_status.py --period {context.period}",
        },
        "residual_risks": residual_risks,
    }


def write_markdown(status: dict[str, Any], path: Path) -> None:
    latest = status.get("latest_production_run") or {}
    table_full = status.get("latest_full_table_image_run") or {}
    package = status.get("review_package") or {}
    publish = status.get("publish_gate") or {}
    sharepoint = status.get("sharepoint") or {}

    lines = [
        f"# {status['month_label']} Regional Production Status",
        "",
        f"- Status: `{status['status']}`",
        f"- Period: `{status['period']}`",
        f"- Snapshot date: `{status['snapshot_date']}`",
        f"- Kickoff date: `{status['kickoff_date']}`",
        f"- Review package: `{package.get('path', '')}`",
        "",
        "## Latest Green Artifacts",
        "",
        f"- Production manifest: `{latest.get('path', 'missing')}`",
        f"- Full table-image manifest: `{table_full.get('path', 'missing')}`",
        f"- Publish gate: `{publish.get('path', 'missing')}`",
        "",
        "## Gates",
        "",
        f"- Production run: `{latest.get('status')}`; steps={latest.get('step_counts', {})}",
        f"- Review package validation: `{package.get('validation_status')}`; decks={package.get('present_deck_count')}/{package.get('expected_deck_count')}",
        f"- Publish gate: `{publish.get('status')}`; directors={publish.get('director_count')}",
        f"- Downloads deck count: `{package.get('pptx_count')}`; lock files={len(package.get('lock_files') or [])}",
        f"- SharePoint validation: `{sharepoint.get('status')}`; assets={sharepoint.get('present_expected_count')}/{sharepoint.get('expected_count')}; quarantined={sharepoint.get('quarantined_count')}",
        "",
        "## Director Readiness",
        "",
        "| Director | Status | Elements | Table Images | Final PPTX Timestamp |",
        "|---|---:|---:|---:|---|",
    ]
    package_files = package.get("pptx_files") or []
    package_mtimes = package.get("pptx_mtimes") or {}
    for row in publish.get("directors", []):
        slug = str(row.get("slug") or "")
        package_file = next((name for name in package_files if name.startswith(f"{slug}-LAND-")), "")
        lines.append(
            "| {slug} | {status} | {elements} | {tables} | {timestamp} |".format(
                slug=slug,
                status=row.get("status"),
                elements=row.get("named_thinkcell_elements_present"),
                tables=row.get("table_image_count"),
                timestamp=package_mtimes.get(package_file, ""),
            )
        )

    lines.extend(["", "## Commands", ""])
    for label, command in status.get("commands", {}).items():
        lines.append(f"- `{label}`: `{command}`")

    lines.extend(["", "## Residual Risks", ""])
    lines.extend(f"- {risk}" for risk in status.get("residual_risks", []))
    if status.get("failures"):
        lines.extend(["", "## Failures", ""])
        lines.extend(f"- {failure}" for failure in status["failures"])

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    status = build_status(args.period)
    regional = ROOT / "state" / args.period / "__regional__" / "production_status"
    json_output = args.json_output or regional / "regional_production_status.json"
    markdown_output = args.markdown_output or regional / "regional_production_status.md"
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    write_markdown(status, markdown_output)

    print(f"status={status['status']}")
    print(f"json={json_output}")
    print(f"markdown={markdown_output}")
    return 0 if status["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
