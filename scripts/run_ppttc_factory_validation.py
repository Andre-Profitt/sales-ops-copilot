#!/usr/bin/env python3
"""Validate generated `.ppttc` files against expected-name manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_ppttc import load_payload, validate_ppttc

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_DIR = ROOT / "assets" / "thinkcell_manifests"


@dataclass(frozen=True)
class NameManifest:
    path: Path
    template_path: str
    template_path_relative: str | None
    template_filename: str
    template_sha256: str
    expected_names: list[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_name_manifest(path: Path) -> NameManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    names = payload.get("expected_names")
    if not isinstance(names, list):
        raise ValueError(f"{path}: expected_names must be an array")
    return NameManifest(
        path=path,
        template_path=str(payload.get("template_path") or ""),
        template_path_relative=payload.get("template_path_relative"),
        template_filename=str(payload.get("template_filename") or Path(str(payload.get("template_path") or "")).name),
        template_sha256=str(payload.get("template_sha256") or ""),
        expected_names=[str(name) for name in names],
    )


def load_name_manifests(manifest_dir: Path) -> list[NameManifest]:
    if not manifest_dir.exists():
        return []
    manifests: list[NameManifest] = []
    for path in sorted(manifest_dir.glob("*.expected-names.json")):
        manifests.append(_load_name_manifest(path))
    return manifests


def _template_from_ppttc(payload: Any) -> str | None:
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    if not isinstance(first, dict):
        return None
    template = first.get("template")
    return template if isinstance(template, str) and template.strip() else None


def match_manifest(template_path: str | None, manifests: list[NameManifest]) -> tuple[NameManifest | None, str]:
    if not template_path:
        return None, "no_template_in_ppttc"
    template = Path(template_path).expanduser()
    template_resolved = str(template.resolve()) if template.exists() else str(template)
    template_filename = template.name
    template_hash = _sha256(template) if template.exists() else None

    if template_hash:
        by_hash = [manifest for manifest in manifests if manifest.template_sha256 == template_hash]
        if len(by_hash) == 1:
            return by_hash[0], "sha256"

    by_path = [
        manifest
        for manifest in manifests
        if manifest.template_path == template_resolved
        or manifest.template_path == template_path
        or manifest.template_path_relative == template_path
    ]
    if len(by_path) == 1:
        return by_path[0], "path"

    by_filename = [manifest for manifest in manifests if manifest.template_filename == template_filename]
    if len(by_filename) == 1:
        return by_filename[0], "filename"

    if len(by_filename) > 1:
        return None, "ambiguous_template_filename"
    return None, "no_matching_manifest"


def _default_ppttc_paths(period: str, root: Path = ROOT) -> list[Path]:
    state_dir = root / "state" / period
    return sorted(
        path
        for path in state_dir.glob("*/*.ppttc")
        if "__regional__" not in path.parts and path.is_file()
    )


def validate_ppttc_file(
    ppttc_path: Path,
    *,
    name_manifests: list[NameManifest],
    strict: bool,
) -> dict[str, Any]:
    try:
        payload = load_payload(ppttc_path)
    except SystemExit as exc:
        return {
            "ppttc": str(ppttc_path),
            "status": "error",
            "template": None,
            "manifest": None,
            "manifest_match": None,
            "error": str(exc),
            "validation": None,
        }

    template = _template_from_ppttc(payload)
    manifest, match_reason = match_manifest(template, name_manifests)
    if manifest is None:
        return {
            "ppttc": str(ppttc_path),
            "status": "error",
            "template": template,
            "manifest": None,
            "manifest_match": match_reason,
            "error": f"no expected-name manifest for template ({match_reason})",
            "validation": None,
        }

    result = validate_ppttc(payload, expected_names=manifest.expected_names, strict=strict)
    return {
        "ppttc": str(ppttc_path),
        "status": "pass" if result.ok else "error",
        "template": template,
        "manifest": str(manifest.path),
        "manifest_match": match_reason,
        "expected_name_count": len(manifest.expected_names),
        "validation": result.as_dict(),
    }


def build_report(
    *,
    period: str,
    ppttc_paths: list[Path],
    manifest_dir: Path,
    strict: bool,
) -> dict[str, Any]:
    name_manifests = load_name_manifests(manifest_dir)
    results = [
        validate_ppttc_file(path, name_manifests=name_manifests, strict=strict)
        for path in ppttc_paths
    ]
    error_count = sum(1 for item in results if item["status"] != "pass")
    warning_count = sum(
        len((item.get("validation") or {}).get("findings", []))
        for item in results
        if item.get("validation")
    ) - sum(
        (item.get("validation") or {}).get("error_count", 0)
        for item in results
        if item.get("validation")
    )
    return {
        "schema": "thinkcell-ppttc-factory-validation/v1",
        "created_at_utc": _utc_now(),
        "period": period,
        "strict": strict,
        "manifest_dir": str(manifest_dir),
        "name_manifest_count": len(name_manifests),
        "ppttc_count": len(ppttc_paths),
        "pass_count": len(results) - error_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "ok": error_count == 0,
        "results": results,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "ppttc_factory_validation.json"
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", required=True, help="Period label, e.g. 2026-Q2.")
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=DEFAULT_MANIFEST_DIR,
        help="Directory containing *.expected-names.json manifests.",
    )
    parser.add_argument(
        "--ppttc",
        action="append",
        type=Path,
        help="Specific .ppttc file to validate. Repeatable; defaults to state/<period>/*/*.ppttc.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Optional directory for JSON report. Defaults to timestamped state/<period>/__regional__/ppttc_validation run.",
    )
    parser.add_argument("--strict", action="store_true", help="Treat manifest drift as errors.")
    args = parser.parse_args()

    ppttc_paths = [path.expanduser() for path in args.ppttc] if args.ppttc else _default_ppttc_paths(args.period)
    report = build_report(
        period=args.period,
        ppttc_paths=ppttc_paths,
        manifest_dir=args.manifest_dir.expanduser(),
        strict=args.strict,
    )
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    output_dir = args.output_dir or ROOT / "state" / args.period / "__regional__" / "ppttc_validation" / run_id
    report_path = write_report(report, output_dir)

    print(
        f"ppttc_factory_validation period={args.period} ppttc={report['ppttc_count']} "
        f"manifests={report['name_manifest_count']} pass={report['pass_count']} "
        f"errors={report['error_count']} warnings={report['warning_count']} ok={'yes' if report['ok'] else 'no'}"
    )
    print(report_path)
    for item in report["results"]:
        if item["status"] != "pass":
            print(f"ERROR {item['ppttc']}: {item.get('error') or item['status']}", file=sys.stderr)
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
