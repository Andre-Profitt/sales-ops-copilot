from __future__ import annotations

import pytest

from scripts.sd_factory.certification import (
    CertificationSpec,
    certify_candidate,
    certify_existing_period,
    check_arr_acv_type_filters,
    check_director_roster,
    check_kickoff_after_snapshot,
    check_month_label,
    check_period_format,
    check_publish_blocked_for_uncertified,
    check_sharepoint_folder,
    check_snapshot_date,
)


def test_check_period_format_passes_for_valid_period() -> None:
    check = check_period_format("2026-Q2")
    assert check.status == "pass"


@pytest.mark.parametrize("bad", ["2026Q2", "2026-Q5", "Q2-2026", ""])
def test_check_period_format_fails_for_invalid_period(bad: str) -> None:
    check = check_period_format(bad)
    assert check.status == "fail"
    assert check.severity == "critical"


def test_check_snapshot_date_in_quarter_passes() -> None:
    check = check_snapshot_date("2026-Q2", "2026-04-30")
    assert check.status == "pass"


def test_check_snapshot_date_outside_quarter_fails() -> None:
    check = check_snapshot_date("2026-Q2", "2026-03-31")
    assert check.status == "fail"


def test_check_snapshot_date_bad_format_fails() -> None:
    check = check_snapshot_date("2026-Q2", "30/04/2026")
    assert check.status == "fail"


def test_check_kickoff_after_snapshot_pass_and_fail() -> None:
    assert check_kickoff_after_snapshot("2026-04-30", "2026-05-01").status == "pass"
    assert check_kickoff_after_snapshot("2026-04-30", "2026-04-29").status == "fail"


def test_check_month_label_format() -> None:
    assert check_month_label("May 2026").status == "pass"
    assert check_month_label("may 2026").status == "fail"
    assert check_month_label("MAY-2026").status == "fail"


def test_check_sharepoint_folder_format_pass_and_fail() -> None:
    folder = "General/Book of Business/Sales Director Reporting/Q2 2026/May 2026"
    assert check_sharepoint_folder("2026-Q2", "May 2026", folder).status == "pass"
    bad_folder = "General/Book of Business/Sales Director Reporting/Q1 2026/May 2026"
    assert check_sharepoint_folder("2026-Q2", "May 2026", bad_folder).status == "fail"


def test_check_director_roster_returns_count_and_names_pass() -> None:
    checks = check_director_roster()
    assert all(check.status == "pass" for check in checks)
    names = {check.name for check in checks}
    assert names == {"director_roster_count", "director_roster_required_names"}


def test_check_arr_acv_type_filters_pass_against_repo_root() -> None:
    checks = check_arr_acv_type_filters()
    by_name = {check.name: check for check in checks}
    assert by_name["arr_filter_uses_type_in_land_expand"].status == "pass"
    assert by_name["acv_filter_uses_type_renewal"].status == "pass"
    assert by_name["arr_acv_blend_absent"].status == "pass"


def test_publish_blocked_for_uncertified_blocks_unrecognized_period() -> None:
    blocked = check_publish_blocked_for_uncertified("2026-Q3")
    assert blocked.status == "pass"
    assert "blocked" in blocked.finding.lower()


def test_publish_blocked_for_certified_period_passes() -> None:
    check = check_publish_blocked_for_uncertified("2026-Q2")
    assert check.status == "pass"


def test_certify_existing_period_passes_for_certified_lane() -> None:
    report = certify_existing_period("2026-Q2")
    assert report.period_status == "ready"
    assert report.status in {"pass", "warn"}
    assert report.publish_allowed is True
    assert not report.critical_failures


def test_certify_existing_period_raises_for_uncertified_period() -> None:
    with pytest.raises(ValueError, match="only 2026-Q2"):
        certify_existing_period("2026-Q3")


def test_certify_candidate_august_2026_q3_passes_structural_checks() -> None:
    spec = CertificationSpec(
        period="2026-Q3",
        month_label="August 2026",
        snapshot_date="2026-07-31",
        kickoff_date="2026-08-03",
        sharepoint_folder="General/Book of Business/Sales Director Reporting/Q3 2026/August 2026",
    )
    report = certify_candidate(spec)
    assert report.mode == "candidate"
    assert report.period_status == "candidate"
    assert not report.critical_failures, report.critical_failures
    assert report.publish_allowed is False, "candidate periods cannot publish until wired"


def test_certify_candidate_with_blended_arr_acv_folder_fails() -> None:
    spec = CertificationSpec(
        period="2026-Q3",
        month_label="August 2026",
        snapshot_date="2026-07-31",
        kickoff_date="2026-08-03",
        sharepoint_folder="WrongRoot/Q1 2026/August 2026",
    )
    report = certify_candidate(spec)
    failed_names = {check.name for check in report.critical_failures}
    assert "sharepoint_folder_format" in failed_names
    assert report.publish_allowed is False


def test_certify_candidate_with_snapshot_after_kickoff_fails() -> None:
    spec = CertificationSpec(
        period="2026-Q3",
        month_label="August 2026",
        snapshot_date="2026-08-05",
        kickoff_date="2026-08-04",
        sharepoint_folder="General/Book of Business/Sales Director Reporting/Q3 2026/August 2026",
    )
    report = certify_candidate(spec)
    failed_names = {check.name for check in report.critical_failures}
    assert "kickoff_after_snapshot" in failed_names
