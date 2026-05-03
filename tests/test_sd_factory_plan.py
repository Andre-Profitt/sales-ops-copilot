from __future__ import annotations

from dataclasses import asdict

from scripts.sd_factory.plan import (
    CANONICAL_STAGES,
    factory_plan_for_period,
    plan_to_markdown,
)


def test_canonical_stages_have_unique_ids_and_known_phases() -> None:
    ids = [stage.id for stage in CANONICAL_STAGES]
    assert len(ids) == len(set(ids)), f"duplicate stage ids: {ids}"
    valid_phases = {"source", "finalize", "gate", "package", "evidence", "publish"}
    invalid = [stage.id for stage in CANONICAL_STAGES if stage.phase not in valid_phases]
    assert not invalid, f"unknown phase on: {invalid}"


def test_validated_period_returns_ready_plan_with_canonical_stages() -> None:
    plan = factory_plan_for_period("2026-Q2")

    assert plan.period_status == "ready"
    assert plan.period == "2026-Q2"
    assert plan.month_label == "May 2026"
    assert plan.snapshot_date == "2026-04-30"
    assert (
        plan.sharepoint_folder
        == "General/Book of Business/Sales Director Reporting/Q2 2026/May 2026"
    )
    assert plan.counts["total"] == len(CANONICAL_STAGES)
    assert plan.counts["publish_only"] >= 1
    assert plan.counts["requires_office"] >= 1
    assert any(stage["id"] == "regional_publish_gate" for stage in plan.stages)
    assert any(stage["id"] == "sharepoint_validate" for stage in plan.stages)


def test_uncertified_period_emits_blockers_and_does_not_blend_arr_acv() -> None:
    plan = factory_plan_for_period("2026-Q3")

    assert plan.period_status == "uncertified"
    assert plan.month_label is None
    assert plan.snapshot_date is None
    assert plan.blockers, "uncertified period must emit blockers"
    assert any("certification harness" in item for item in plan.blockers)
    assert "ARR = Land+Expand via APTS_Opportunity_ARR__c." in plan.constraints
    assert "ACV = Renewal via APTS_Renewal_ACV__c." in plan.constraints


def test_no_publish_filter_drops_publish_only_stages() -> None:
    full = factory_plan_for_period("2026-Q2")
    no_publish = factory_plan_for_period("2026-Q2", include_publish=False)

    assert full.counts["total"] > no_publish.counts["total"]
    assert no_publish.counts["publish_only"] == 0
    assert not any(stage["runs_on_publish_only"] for stage in no_publish.stages)


def test_no_full_refresh_filter_drops_office_dependent_stages() -> None:
    no_office = factory_plan_for_period("2026-Q2", include_full_refresh=False)

    assert no_office.counts["requires_office"] == 0
    assert not any(stage["requires_office"] for stage in no_office.stages)


def test_plan_command_template_uses_period_and_snapshot_date() -> None:
    plan = factory_plan_for_period("2026-Q2")
    source_refresh = next(stage for stage in plan.stages if stage["id"] == "source_refresh")

    assert "2026-Q2" in source_refresh["command"]
    assert "2026-04-30" in source_refresh["command"]


def test_plan_serializes_to_dict_and_markdown_without_errors() -> None:
    plan = factory_plan_for_period("2026-Q2", director_slug="Jesper-Tyrer")

    assert plan.director_slug == "Jesper-Tyrer"
    payload = asdict(plan)
    assert payload["schema"] == "sales-director-factory-plan/v1"
    markdown = plan_to_markdown(plan)
    assert "Sales Director Factory Plan - 2026-Q2" in markdown
    assert "Jesper-Tyrer" in markdown
