#!/usr/bin/env python3
"""Validate the May 2026 regional Sales Director SharePoint folder.

Schema is `may-sharepoint-upload-validation/v1` (preserved). New fields are
additive so downstream consumers (`sd_factory_doctor.py`,
`report_regional_production_status.py`) keep reading what they already read.

The validator answers four questions:

* **expected vs present** — every planned upload is in the folder.
* **stale top-level files** — every file in the folder either matches a
  planned upload or is unrelated to the regional publish lane. Files whose
  name matches *any* of `period_context.sharepoint_publish_suffixes` (or the
  pre-publish warning README) but is *not* in the planned set is flagged as
  stale, because that is exactly the leftover-of-a-prior-cycle pattern Andre
  has been bitten by.
* **size bounds** — Office files (`.pptx`/`.xlsx`) must land within
  ``[expected*0.95, expected*1.20]``. The previous "actual >= expected" rule
  treated any larger-than-expected blob as good, including stale 15 MB files
  that had never been replaced.
* **freshness** — SharePoint copy must not be older than the local source by
  more than 60 s. A missing Graph `lastModifiedDateTime` is a blocker for
  Office production files (.pptx/.xlsx) and a warning for evidence/manifest
  files.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# CLI invocation puts scripts/ on sys.path[0]; pytest collection imports this
# module via the `scripts.` namespace package, which leaves scripts/ off
# sys.path. Add it idempotently so the bare sibling imports below resolve in
# both contexts without forcing a `scripts/__init__.py`.
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from period_context import DEFAULT_PERIOD, PeriodContext, context_for_period  # noqa: E402


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCHEMA = "may-sharepoint-upload-validation/v1"
OFFICE_SUFFIXES = (".pptx", ".xlsx")
OFFICE_SIZE_LOWER = 0.95
OFFICE_SIZE_UPPER = 1.20
EVIDENCE_SIZE_MIN_TOLERANCE_BYTES = 2048
EVIDENCE_SIZE_TOLERANCE_RATIO = 0.25
FRESHNESS_GRACE_SECONDS = 60

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = (
    ROOT
    / "state"
    / DEFAULT_PERIOD
    / "__regional__"
    / context_for_period(DEFAULT_PERIOD).sharepoint_validation_manifest_name
)


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _children(token: str, drive_id: str, folder: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{GRAPH_BASE}/drives/{drive_id}/root:/{folder}:/children"
        "?$select=id,name,size,lastModifiedDateTime,webUrl,file,folder",
        headers=_headers(token),
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("value", [])


def _is_office(name: str) -> bool:
    return name.endswith(OFFICE_SUFFIXES)


def _parse_graph_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _expected_record(path: Path) -> dict[str, Any]:
    stat = path.stat()
    mtime_utc = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    return {
        "source_path": str(path),
        "size_bytes": stat.st_size,
        "source_mtime_utc": mtime_utc.isoformat(),
    }


def _evaluate_size(
    name: str,
    expected_size: int,
    actual_size: int,
) -> dict[str, Any] | None:
    if _is_office(name):
        lower = int(expected_size * OFFICE_SIZE_LOWER)
        upper = int(expected_size * OFFICE_SIZE_UPPER)
        rule = f"office_actual_within_[{OFFICE_SIZE_LOWER:.2f}x,{OFFICE_SIZE_UPPER:.2f}x]_of_source"
        if lower <= actual_size <= upper:
            return None
        return {
            "name": name,
            "expected": expected_size,
            "actual": actual_size,
            "lower_bound": lower,
            "upper_bound": upper,
            "rule": rule,
        }

    tolerance = max(
        EVIDENCE_SIZE_MIN_TOLERANCE_BYTES, int(expected_size * EVIDENCE_SIZE_TOLERANCE_RATIO)
    )
    if actual_size > 0 and abs(actual_size - expected_size) <= tolerance:
        return None
    return {
        "name": name,
        "expected": expected_size,
        "actual": actual_size,
        "rule": f"evidence_actual_positive_and_within_{tolerance}_bytes_of_source",
    }


def _evaluate_freshness(
    name: str,
    source_mtime_utc: datetime | None,
    sharepoint_modified: datetime | None,
    grace_seconds: int = FRESHNESS_GRACE_SECONDS,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (mismatch, warning) — at most one is non-None.

    Mismatch entries fail the gate. Warnings do not.
    """

    office = _is_office(name)
    if sharepoint_modified is None:
        entry = {
            "name": name,
            "source_mtime_utc": source_mtime_utc.isoformat() if source_mtime_utc else None,
            "sharepoint_lastModifiedDateTime": None,
            "rule": "sharepoint_lastModifiedDateTime_missing",
        }
        if office:
            return entry, None
        return None, entry

    if source_mtime_utc is None:
        # We could not stat the local source; treat as a non-blocking warning so
        # the gate still surfaces it but does not flap when builders are running
        # in a different working tree.
        return None, {
            "name": name,
            "source_mtime_utc": None,
            "sharepoint_lastModifiedDateTime": sharepoint_modified.isoformat(),
            "rule": "local_source_missing_for_freshness_check",
        }

    lag_seconds = (source_mtime_utc - sharepoint_modified).total_seconds()
    if lag_seconds <= grace_seconds:
        return None, None
    return (
        {
            "name": name,
            "source_mtime_utc": source_mtime_utc.isoformat(),
            "sharepoint_lastModifiedDateTime": sharepoint_modified.isoformat(),
            "lag_seconds": round(lag_seconds, 3),
            "grace_seconds": grace_seconds,
            "rule": "sharepoint_copy_older_than_local_source_by_more_than_grace",
        },
        None,
    )


def compute_validation_payload(
    *,
    expected: dict[str, dict[str, Any]],
    files: dict[str, dict[str, Any]],
    period: str,
    month_label: str,
    drive_id: str,
    folder: str,
    publish_suffixes: tuple[str, ...],
    warning_filename: str,
    grace_seconds: int = FRESHNESS_GRACE_SECONDS,
) -> dict[str, Any]:
    """Pure-function core of `validate_sharepoint`.

    Inputs are plain dicts so the caller (or a test) can supply data without
    touching Graph or the filesystem.

    `expected[name]` must carry `source_path`, `size_bytes`, and
    `source_mtime_utc` (ISO-8601 UTC string). `files[name]` is a Graph child
    item (dict) with `size`, `lastModifiedDateTime`, `webUrl`.
    """

    missing = sorted(name for name in expected if name not in files)

    stale = sorted(
        name
        for name in files
        if name not in expected
        and (any(name.endswith(suffix) for suffix in publish_suffixes) or name == warning_filename)
    )

    size_mismatch: list[dict[str, Any]] = []
    freshness_mismatch: list[dict[str, Any]] = []
    freshness_warnings: list[dict[str, Any]] = []

    for name in sorted(expected):
        item = files.get(name)
        if not item:
            continue
        spec = expected[name]
        actual_size = int(item.get("size") or 0)
        expected_size = int(spec.get("size_bytes") or 0)

        size_finding = _evaluate_size(name, expected_size, actual_size)
        if size_finding is not None:
            size_mismatch.append(size_finding)

        source_mtime_iso = spec.get("source_mtime_utc")
        source_mtime = _parse_graph_datetime(source_mtime_iso) if source_mtime_iso else None
        sharepoint_modified = _parse_graph_datetime(item.get("lastModifiedDateTime"))
        mismatch, warning = _evaluate_freshness(
            name,
            source_mtime,
            sharepoint_modified,
            grace_seconds=grace_seconds,
        )
        if mismatch is not None:
            freshness_mismatch.append(mismatch)
        if warning is not None:
            freshness_warnings.append(warning)

    status = (
        "pass"
        if not missing and not stale and not size_mismatch and not freshness_mismatch
        else "fail"
    )

    return {
        "schema": SCHEMA,
        "status": status,
        "period": period,
        "month_label": month_label,
        "drive_id": drive_id,
        "folder": folder,
        "expected_count": len(expected),
        "present_expected_count": len(expected) - len(missing),
        "missing": missing,
        "stale_top_level_files": stale,
        "size_mismatch": size_mismatch,
        "freshness_grace_seconds": grace_seconds,
        "freshness_mismatch": freshness_mismatch,
        "freshness_warnings": freshness_warnings,
        "validated": [
            {
                "name": name,
                "size": files[name].get("size"),
                "lastModifiedDateTime": files[name].get("lastModifiedDateTime"),
                "webUrl": files[name].get("webUrl"),
            }
            for name in sorted(expected)
            if name in files
        ],
    }


def _expected_from_planned(period: str) -> dict[str, dict[str, Any]]:
    # Lazy import: this module otherwise imports cleanly via
    # `scripts.validate_may_sharepoint_upload`. The sibling import only
    # resolves when sys.path[0] is the scripts/ directory (i.e. CLI usage).
    from upload_may_regional_assets_sharepoint import planned_assets

    return {publish_name: _expected_record(path) for path, publish_name in planned_assets(period)}


def validate_sharepoint(
    period: str,
    drive_id: str,
    folder: str,
    token: str,
    *,
    grace_seconds: int = FRESHNESS_GRACE_SECONDS,
) -> dict[str, Any]:
    context: PeriodContext = context_for_period(period)
    expected = _expected_from_planned(period)
    children = _children(token, drive_id, folder)
    files = {str(item.get("name")): item for item in children if "file" in item}
    return compute_validation_payload(
        expected=expected,
        files=files,
        period=period,
        month_label=context.month_label,
        drive_id=drive_id,
        folder=folder,
        publish_suffixes=tuple(context.sharepoint_publish_suffixes),
        warning_filename=context.sharepoint_warning_filename,
        grace_seconds=grace_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument(
        "--drive-id",
        default=None,
        help="Defaults to upload script's DEFAULT_DRIVE_ID.",
    )
    parser.add_argument("--folder")
    parser.add_argument("--token")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--upload-manifest", action="store_true")
    parser.add_argument(
        "--freshness-grace-seconds",
        type=int,
        default=FRESHNESS_GRACE_SECONDS,
        help="Maximum allowed lag (SP older than local source) before failing the gate.",
    )
    args = parser.parse_args()

    from upload_may_regional_assets_sharepoint import (
        DEFAULT_DRIVE_ID,
        graph_token,
        upload_file,
    )

    context = context_for_period(args.period)
    folder = args.folder or context.sharepoint_folder
    drive_id = args.drive_id or DEFAULT_DRIVE_ID
    manifest_path = args.manifest or (
        ROOT / "state" / args.period / "__regional__" / context.sharepoint_validation_manifest_name
    )
    token = graph_token(args.token)
    payload = validate_sharepoint(
        args.period,
        drive_id,
        folder,
        token,
        grace_seconds=args.freshness_grace_seconds,
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.upload_manifest:
        upload_file(token, drive_id, folder, manifest_path, manifest_path.name)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
