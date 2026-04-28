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

    assert env["schema_version"] == "1.0"
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


def test_envelope_excludes_client_level_data():
    """Per AI Code of Conduct: aggregate-only. No client account names in envelope."""
    from scripts.land_brief import build_trends_envelope

    sf_snapshot = json.loads((FIXTURES / "sample_director.json").read_text())
    director = {"name": "Adam Steinhouse", "book_codes": ["P&I"]}

    env = build_trends_envelope(sf_snapshot, director, "2026-Q2")

    assert "Account" not in env, "envelope must not include Account-level data"
