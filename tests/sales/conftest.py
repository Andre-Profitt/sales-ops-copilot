"""Fixtures for tests/sales/. Pure data only — no network."""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def salesmanager_report() -> dict:
    """Reference report.json from a working PBI report (with table visuals)."""
    return json.loads((FIXTURES / "salesmanager_report.json").read_text())


@pytest.fixture
def empty_report() -> dict:
    """Minimal report.json shape — one empty section."""
    return {
        "config": "{}",
        "sections": [
            {
                "name": "ReportSection",
                "displayName": "Page 1",
                "filters": "[]",
                "visualContainers": [],
                "displayOption": 1,
                "height": 720,
                "width": 1280,
            }
        ],
        "resourcePackages": [],
    }
