"""Tests for the May 2026 SharePoint upload validator.

These tests target the pure helper `compute_validation_payload` so no live
Graph calls or filesystem reads are required. They lock in the P0 hardening
items I-1, I-2, I-3 from
``state/2026-Q2/__regional__/claude_parallel/20260501-2055Z_gate_hardening/ASSERTION_BACKLOG.md``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from scripts.period_context import context_for_period
from scripts.validate_may_sharepoint_upload import (
    FRESHNESS_GRACE_SECONDS,
    SCHEMA,
    compute_validation_payload,
)


PERIOD = "2026-Q2"
DRIVE_ID = "drive-id-test"
CONTEXT = context_for_period(PERIOD)
FOLDER = CONTEXT.sharepoint_folder
SUFFIXES = tuple(CONTEXT.sharepoint_publish_suffixes)
WARNING_FILENAME = CONTEXT.sharepoint_warning_filename
MONTH_LABEL = CONTEXT.month_label

# Reference SharePoint snapshot — both deck and source are 1 minute old.
SOURCE_MTIME = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
SP_MODIFIED = datetime(2026, 5, 1, 12, 1, 0, tzinfo=timezone.utc)
SOURCE_MTIME_ISO = SOURCE_MTIME.isoformat()
SP_MODIFIED_ISO = SP_MODIFIED.isoformat()


def _expected_office(name: str, *, size: int = 8_000_000) -> dict[str, Any]:
    return {
        "source_path": f"/tmp/{name}",
        "size_bytes": size,
        "source_mtime_utc": SOURCE_MTIME_ISO,
    }


def _expected_evidence(name: str, *, size: int = 4_096) -> dict[str, Any]:
    return {
        "source_path": f"/tmp/{name}",
        "size_bytes": size,
        "source_mtime_utc": SOURCE_MTIME_ISO,
    }


def _graph_file(
    name: str,
    *,
    size: int,
    last_modified: str | None = SP_MODIFIED_ISO,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "name": name,
        "size": size,
        "webUrl": f"https://example.invalid/{name}",
        "file": {"mimeType": "application/octet-stream"},
    }
    if last_modified is not None:
        item["lastModifiedDateTime"] = last_modified
    return item


def _payload(
    expected: dict[str, dict[str, Any]],
    files_list: list[dict[str, Any]],
    *,
    grace_seconds: int = FRESHNESS_GRACE_SECONDS,
) -> dict[str, Any]:
    files = {item["name"]: item for item in files_list}
    return compute_validation_payload(
        expected=expected,
        files=files,
        period=PERIOD,
        month_label=MONTH_LABEL,
        drive_id=DRIVE_ID,
        folder=FOLDER,
        publish_suffixes=SUFFIXES,
        warning_filename=WARNING_FILENAME,
        grace_seconds=grace_seconds,
    )


def test_clean_payload_passes_with_full_schema_fields() -> None:
    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    workbook = f"Adam Steinhouse US Pension & Insurance Connected Excel Audit Workbook - {MONTH_LABEL}.xlsx"
    expected = {
        deck: _expected_office(deck, size=8_000_000),
        workbook: _expected_office(workbook, size=200_000),
    }
    files = [
        _graph_file(deck, size=8_100_000),
        _graph_file(workbook, size=205_000),
    ]
    payload = _payload(expected, files)

    assert payload["schema"] == SCHEMA
    assert payload["status"] == "pass"
    assert payload["expected_count"] == 2
    assert payload["present_expected_count"] == 2
    assert payload["missing"] == []
    assert payload["stale_top_level_files"] == []
    assert payload["size_mismatch"] == []
    assert payload["freshness_mismatch"] == []
    assert payload["freshness_warnings"] == []
    assert payload["freshness_grace_seconds"] == FRESHNESS_GRACE_SECONDS
    assert {row["name"] for row in payload["validated"]} == {deck, workbook}


def test_missing_expected_file_is_listed() -> None:
    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    payload = _payload(expected, [])

    assert payload["status"] == "fail"
    assert payload["missing"] == [deck]
    assert payload["present_expected_count"] == 0


@pytest.mark.parametrize("suffix_index", list(range(5)))
def test_stale_scan_iterates_every_publish_suffix(suffix_index: int) -> None:
    """I-1: stale detection must cover all five publish suffixes (was [:2])."""

    suffix = SUFFIXES[suffix_index]
    stale_name = f"Removed Director Old Region {suffix}"
    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [
        _graph_file(deck, size=8_100_000),
        _graph_file(stale_name, size=1_234),
    ]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert stale_name in payload["stale_top_level_files"]


def test_stale_scan_does_not_flag_expected_names() -> None:
    """Files matching a publish suffix that ARE in `expected` must not be flagged."""

    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    workbook = f"Adam Steinhouse US Pension & Insurance Connected Excel Audit Workbook - {MONTH_LABEL}.xlsx"
    expected = {
        deck: _expected_office(deck, size=8_000_000),
        workbook: _expected_office(workbook, size=200_000),
    }
    files = [
        _graph_file(deck, size=8_100_000),
        _graph_file(workbook, size=205_000),
    ]
    payload = _payload(expected, files)

    assert payload["stale_top_level_files"] == []


def test_warning_readme_is_treated_as_stale() -> None:
    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [
        _graph_file(deck, size=8_100_000),
        _graph_file(WARNING_FILENAME, size=512),
    ]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert WARNING_FILENAME in payload["stale_top_level_files"]


def test_unrelated_files_are_not_flagged_as_stale() -> None:
    deck = f"Adam Steinhouse US Pension & Insurance LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [
        _graph_file(deck, size=8_100_000),
        _graph_file("regional_publish_gate.md", size=4_096),
        _graph_file("review_package_visual_gate.json", size=2_048),
        _graph_file("Some Other Project Plan.docx", size=12_000),
    ]
    payload = _payload(expected, files)

    assert payload["status"] == "pass"
    assert payload["stale_top_level_files"] == []


def test_office_size_below_lower_bound_is_blocker() -> None:
    """I-2: an Office file below 0.95x of source size must fail the gate."""

    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=10_000_000)}
    files = [_graph_file(deck, size=9_400_000)]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert payload["size_mismatch"]
    entry = payload["size_mismatch"][0]
    assert entry["name"] == deck
    assert entry["expected"] == 10_000_000
    assert entry["actual"] == 9_400_000
    assert entry["lower_bound"] == int(10_000_000 * 0.95)
    assert entry["upper_bound"] == int(10_000_000 * 1.20)
    assert "0.95x" in entry["rule"] and "1.20x" in entry["rule"]


def test_office_size_above_upper_bound_is_blocker() -> None:
    """I-2: a stale 15 MB Office file masquerading as a 10 MB upload must fail."""

    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=10_000_000)}
    files = [_graph_file(deck, size=15_000_000)]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert payload["size_mismatch"]
    entry = payload["size_mismatch"][0]
    assert entry["actual"] == 15_000_000
    assert entry["upper_bound"] == int(10_000_000 * 1.20)


def test_office_size_within_bounds_passes() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=10_000_000)}

    for actual in (10_000_000, 10_500_000, 11_900_000, 9_600_000):
        files = [_graph_file(deck, size=actual)]
        payload = _payload(expected, files)
        assert payload["status"] == "pass", f"expected pass at actual={actual}, got {payload}"


def test_evidence_file_size_uses_legacy_tolerance() -> None:
    """Evidence files keep the existing relative-tolerance rule (unchanged by I-2)."""

    name = "regional_publish_gate.md"
    expected = {name: _expected_evidence(name, size=8_192)}

    # Within 25 % tolerance → pass.
    payload = _payload(expected, [_graph_file(name, size=10_000)])
    assert payload["status"] == "pass"

    # Way out of tolerance → fail with the legacy rule string.
    payload = _payload(expected, [_graph_file(name, size=100)])
    assert payload["status"] == "fail"
    assert payload["size_mismatch"][0]["rule"].startswith("evidence_actual_positive_and_within_")


def test_freshness_blocker_when_sharepoint_older_than_local_by_grace_plus() -> None:
    """I-3: SP older than local source by > 60 s must fail the gate."""

    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    sp_old = (SOURCE_MTIME - timedelta(seconds=120)).isoformat()
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [_graph_file(deck, size=8_100_000, last_modified=sp_old)]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert payload["freshness_mismatch"]
    entry = payload["freshness_mismatch"][0]
    assert entry["name"] == deck
    assert entry["lag_seconds"] == pytest.approx(120.0, rel=1e-3)
    assert entry["grace_seconds"] == FRESHNESS_GRACE_SECONDS
    assert entry["rule"] == "sharepoint_copy_older_than_local_source_by_more_than_grace"


def test_freshness_passes_within_grace_window() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}

    # SharePoint is 30 s OLDER than the source — inside the 60 s grace.
    sp_30s_old = (SOURCE_MTIME - timedelta(seconds=30)).isoformat()
    payload = _payload(expected, [_graph_file(deck, size=8_100_000, last_modified=sp_30s_old)])
    assert payload["status"] == "pass"
    assert payload["freshness_mismatch"] == []


def test_freshness_passes_when_sharepoint_newer_than_local() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}

    # SharePoint is 5 minutes NEWER (Graph applies its own server-side timestamp
    # on upload) — that is the expected steady state and must not flag.
    sp_newer = (SOURCE_MTIME + timedelta(minutes=5)).isoformat()
    payload = _payload(expected, [_graph_file(deck, size=8_100_000, last_modified=sp_newer)])
    assert payload["status"] == "pass"
    assert payload["freshness_mismatch"] == []


def test_missing_lastmodified_blocks_office_files() -> None:
    """I-3: missing Graph date must be a blocker for Office production files."""

    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [_graph_file(deck, size=8_100_000, last_modified=None)]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert payload["freshness_mismatch"]
    assert payload["freshness_mismatch"][0]["rule"] == "sharepoint_lastModifiedDateTime_missing"
    assert payload["freshness_warnings"] == []


def test_missing_lastmodified_warns_for_evidence_files() -> None:
    name = "regional_publish_gate.md"
    expected = {name: _expected_evidence(name, size=8_192)}
    files = [_graph_file(name, size=8_192, last_modified=None)]
    payload = _payload(expected, files)

    # Warning, not blocker.
    assert payload["status"] == "pass"
    assert payload["freshness_warnings"]
    warning = payload["freshness_warnings"][0]
    assert warning["name"] == name
    assert warning["rule"] == "sharepoint_lastModifiedDateTime_missing"


def test_unparseable_lastmodified_treated_as_missing() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    files = [_graph_file(deck, size=8_100_000, last_modified="not-a-real-iso-date")]
    payload = _payload(expected, files)

    assert payload["status"] == "fail"
    assert payload["freshness_mismatch"]
    assert payload["freshness_mismatch"][0]["rule"] == "sharepoint_lastModifiedDateTime_missing"


def test_payload_only_lists_validated_files_actually_present() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    workbook = f"Connected Excel Audit Workbook - {MONTH_LABEL}.xlsx"
    expected = {
        deck: _expected_office(deck, size=8_000_000),
        workbook: _expected_office(workbook, size=200_000),
    }
    files = [_graph_file(deck, size=8_100_000)]
    payload = _payload(expected, files)

    names_in_validated = {row["name"] for row in payload["validated"]}
    assert names_in_validated == {deck}
    assert workbook in payload["missing"]
    assert payload["status"] == "fail"


def test_grace_seconds_is_threaded_through() -> None:
    deck = f"LAND Meeting Spine - {MONTH_LABEL}.pptx"
    expected = {deck: _expected_office(deck, size=8_000_000)}
    sp_old = (SOURCE_MTIME - timedelta(seconds=200)).isoformat()
    files = [_graph_file(deck, size=8_100_000, last_modified=sp_old)]

    # With grace_seconds=300, the 200 s lag is allowed.
    payload = _payload(expected, files, grace_seconds=300)
    assert payload["status"] == "pass"
    assert payload["freshness_grace_seconds"] == 300

    # With the default 60 s, it fails.
    payload = _payload(expected, files)
    assert payload["status"] == "fail"
