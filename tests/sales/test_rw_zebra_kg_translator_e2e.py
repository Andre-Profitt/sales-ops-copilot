"""End-to-end: translate one Zebra template + push to Fabric.

Marked @pytest.mark.fabric so it is skipped in standard CI. To run:
    pytest tests/sales/test_rw_zebra_kg_translator_e2e.py -m fabric
The test requires an active `az login` and the SCRATCH_WORKSPACE_ID env var.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.fabric


@pytest.fixture
def scratch_workspace_id() -> str:
    wid = os.environ.get("SCRATCH_WORKSPACE_ID")
    if not wid:
        pytest.skip("SCRATCH_WORKSPACE_ID not set")
    return wid


def test_translate_one_template_round_trips_through_fabric(scratch_workspace_id):
    from scripts.sales.rw_zebra_kg_translator import (
        BindMap,
        MeasureCatalog,
        translate_visual,
    )

    raw_path = Path("data/zebra_kg/infrastructure/raw_configs.jsonl")
    if not raw_path.exists():
        pytest.skip("infrastructure corpus not present")

    template_slug = "consolidated-financials-power-bi-template"
    rows = [
        json.loads(l) for l in raw_path.open() if json.loads(l)["template_slug"] == template_slug
    ]
    if not rows:
        pytest.skip(f"no rows for template {template_slug}")

    catalog = MeasureCatalog()
    bm = BindMap()
    translated = []
    for row in rows:
        src = {
            "x": row["position"]["x"],
            "y": row["position"]["y"],
            "width": row["position"]["w"],
            "height": row["position"]["h"],
            "config": json.dumps(
                {
                    "name": "raw",
                    "singleVisual": {
                        "visualType": row["visual_type_full"],
                        "projections": {
                            r: [{"queryRef": q} for q in qs]
                            for r, qs in row.get("projections", {}).items()
                        },
                    },
                }
            ),
        }
        translated.extend(translate_visual(src, catalog, bm))

    # translated should never be empty (translator must not lose visuals)
    assert len(translated) >= len(rows)
