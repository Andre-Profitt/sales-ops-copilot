"""trends.json envelope schema contract.

The envelope is consumed by func-simcorp-deckgen-dev /api/generate-land-deck
(Plan B). Schema must remain stable; any breaking change requires bumping
schema_version.
"""

from __future__ import annotations
import json
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


def test_build_trends_envelope_minimum_fields():
    from scripts.land_brief import build_trends_envelope

    sf_snapshot = json.loads((FIXTURES / "sample_director.json").read_text())
    director = {
        "name": "Adam Steinhouse",
        "book_codes": ["P&I"],
        "scope": "us_only",
        "user_id": None,
    }
    period = "2026-Q2"

    env = build_trends_envelope(sf_snapshot, director, period)

    assert env["schema_version"] == "2.0"
    assert env["director"]["name"] == "Adam Steinhouse"
    assert env["period"] == period
    assert env["currency"] == "EUR"
    assert env["currency_format"] == "mEUR"
    assert isinstance(env["kpis"], list) and len(env["kpis"]) > 0
    for k in env["kpis"]:
        assert "name" in k
        assert "value" in k
        assert "unit" in k and k["unit"] in ("EUR", "pct", "count", "days")
        assert k.get("narrative_priority") in ("high", "medium", "low")


def test_envelope_separates_arr_from_acv():
    from scripts.land_brief import build_trends_envelope

    sf_snapshot = json.loads((FIXTURES / "sample_director.json").read_text())
    director = {"name": "Adam Steinhouse", "book_codes": ["P&I"], "scope": "us_only"}

    env = build_trends_envelope(sf_snapshot, director, "2026-Q2")

    kpi_names = [k["name"] for k in env["kpis"]]
    assert "total_pipeline_arr" in kpi_names
    assert "total_renewal_acv" in kpi_names
    assert "total_blended_pipeline" not in kpi_names


def test_envelope_carries_named_per_deal_arrays():
    """Per feedback_simcorp_enterprise_claude_per_deal_2026-04-30, the
    envelope surfaces named per-deal arrays (top deals, pending approval,
    at-risk renewals) for the LLM. Enterprise Claude contract covers
    consent. Verify the three keys are present on the envelope."""
    from scripts.land_brief import build_trends_envelope

    sf_snapshot = json.loads((FIXTURES / "sample_director.json").read_text())
    director = {"name": "Adam Steinhouse", "book_codes": ["P&I"]}

    env = build_trends_envelope(sf_snapshot, director, "2026-Q2")

    for key in ("top_deals_named", "pending_commercial_approval_named", "at_risk_renewals_named"):
        assert key in env, f"envelope missing per-deal array '{key}'"
        assert isinstance(env[key], list), f"'{key}' must be a list"


def test_highlights_derived_from_late_stage_concentration():
    """When >70% of new-business ARR is in Stage 5+, highlight that."""
    from scripts.land_brief import derive_highlights_risks

    envelope = {
        "kpis": [
            {
                "name": "total_pipeline_arr",
                "value": 10_000_000,
                "unit": "EUR",
                "narrative_priority": "high",
            },
            {
                "name": "pipeline_arr_stage_3",
                "value": 1_000_000,
                "unit": "EUR",
                "stage_label": "3 Engagement",
                "narrative_priority": "medium",
            },
            {
                "name": "pipeline_arr_stage_5",
                "value": 6_000_000,
                "unit": "EUR",
                "stage_label": "5 Preferred",
                "narrative_priority": "medium",
            },
            {
                "name": "pipeline_arr_stage_6",
                "value": 2_500_000,
                "unit": "EUR",
                "stage_label": "6 Contracting",
                "narrative_priority": "medium",
            },
        ],
        "highlights": [],
        "risks": [],
    }
    out = derive_highlights_risks(envelope)
    assert len(out["highlights"]) >= 1
    assert any("late-stage" in (h.get("rule") or "") for h in out["highlights"])


def test_envelope_validates_against_pydantic():
    from scripts.schema import TrendsEnvelope
    from scripts.land_brief import build_trends_envelope, derive_highlights_risks

    sf_snapshot = json.loads((FIXTURES / "sample_director.json").read_text())
    director = {"name": "Adam Steinhouse", "book_codes": ["P&I"], "scope": "us_only"}
    env = derive_highlights_risks(build_trends_envelope(sf_snapshot, director, "2026-Q2"))

    parsed = TrendsEnvelope.model_validate(env)
    assert parsed.schema_version == "2.0"
