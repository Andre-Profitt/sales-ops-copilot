"""Tests for the meeting-spine audit gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_meeting_spine_audit_gate import (  # noqa: E402
    DEFAULT_CONTRACT,
    SlideObservation,
    _audit_slide,
    _classify,
    audit_deck,
    run_audit,
)


def _obs(
    *,
    index: int = 1,
    title: str = "t",
    tables: int = 0,
    pictures: int = 0,
    charts: int = 0,
    ole_objects: int = 0,
    text_shapes: int = 0,
    other_shapes: int = 0,
) -> SlideObservation:
    obs = SlideObservation(
        index=index,
        title=title,
        tables=tables,
        pictures=pictures,
        charts=charts,
        ole_objects=ole_objects,
        text_shapes=text_shapes,
        other_shapes=other_shapes,
        observed_kind="",
    )
    obs.observed_kind = _classify(obs)
    return obs


class TestClassify:
    def test_editorial_native(self) -> None:
        assert _classify(_obs()) == "editorial_native"

    def test_native_ppt_table(self) -> None:
        assert _classify(_obs(tables=1)) == "native_ppt_table"

    def test_table_image(self) -> None:
        assert _classify(_obs(pictures=1)) == "table_image"

    def test_native_chart(self) -> None:
        assert _classify(_obs(charts=1)) == "native_chart"

    def test_ole_dominates(self) -> None:
        assert _classify(_obs(tables=1, ole_objects=1)) == "ole_present"

    def test_mixed_table_picture(self) -> None:
        assert _classify(_obs(tables=1, pictures=1)) == "native_ppt_mixed"


class TestAuditSlide:
    def test_pass_when_kind_matches(self) -> None:
        obs = _obs(tables=1)
        entry = {"index": 1, "purpose": "p", "expected_kind": "native_ppt_table"}
        assert _audit_slide(obs, entry) == []

    def test_surface_regression_fail(self) -> None:
        obs = _obs(tables=1)
        entry = {"index": 1, "purpose": "p", "expected_kind": "table_image"}
        findings = _audit_slide(obs, entry)
        assert any(f.code == "SURFACE_REGRESSION" and f.severity == "fail" for f in findings)

    def test_alternative_kind_accepted(self) -> None:
        obs = _obs(charts=1)
        entry = {
            "index": 1,
            "purpose": "p",
            "expected_kind": "table_image",
            "alternative_kinds": ["native_chart"],
        }
        findings = _audit_slide(obs, entry)
        assert all(f.code != "SURFACE_REGRESSION" for f in findings)

    def test_ole_always_fails(self) -> None:
        obs = _obs(tables=1, ole_objects=1)
        entry = {"index": 1, "purpose": "p", "expected_kind": "native_ppt_table"}
        findings = _audit_slide(obs, entry)
        assert any(f.code == "OLE_REGRESSION" and f.severity == "fail" for f in findings)

    def test_table_count_drift(self) -> None:
        obs = _obs(tables=3)
        entry = {
            "index": 1,
            "purpose": "p",
            "expected_kind": "native_ppt_table",
            "expected_tables_min": 1,
            "expected_tables_max": 2,
        }
        findings = _audit_slide(obs, entry)
        assert any(f.code == "TABLE_COUNT_DRIFT" for f in findings)

    def test_picture_count_drift(self) -> None:
        obs = _obs(pictures=0)
        entry = {
            "index": 1,
            "purpose": "p",
            "expected_kind": "table_image",
            "expected_pictures_min": 1,
            "expected_pictures_max": 2,
        }
        findings = _audit_slide(obs, entry)
        assert any(f.code == "TABLE_IMAGE_DRIFT" for f in findings)
        # SURFACE_REGRESSION will also fire because observed = editorial_native
        assert any(f.code == "SURFACE_REGRESSION" for f in findings)

    def test_title_drift_warns_not_fails(self) -> None:
        obs = _obs(tables=1, title="Wrong Title")
        entry = {
            "index": 1,
            "purpose": "p",
            "expected_kind": "native_ppt_table",
            "title_starts_with": "Expected Prefix",
        }
        findings = _audit_slide(obs, entry)
        title_findings = [f for f in findings if f.code == "TITLE_DRIFT"]
        assert len(title_findings) == 1
        assert title_findings[0].severity == "warn"


class TestProductionPackageIntegration:
    """Integration test against the actual May 2026 production decks."""

    PACKAGE_DIR = Path("/Users/test/Downloads/May 2026 Meeting Spine Candidates")

    @pytest.mark.skipif(
        not (Path("/Users/test/Downloads/May 2026 Meeting Spine Candidates")).exists(),
        reason="production package not present in this environment",
    )
    def test_production_decks_pass_contract(self) -> None:
        payload = run_audit(
            period="2026-Q2",
            package_dir=self.PACKAGE_DIR,
            contract_path=Path(DEFAULT_CONTRACT),
        )
        assert payload["status"] == "pass", json.dumps(payload, indent=2)
        assert payload["deck_count"] == 9

    @pytest.mark.skipif(
        not (Path("/Users/test/Downloads/May 2026 Meeting Spine Candidates")).exists(),
        reason="production package not present in this environment",
    )
    def test_each_deck_has_16_slides(self) -> None:
        contract = json.loads(Path(DEFAULT_CONTRACT).read_text(encoding="utf-8"))
        decks = sorted(self.PACKAGE_DIR.glob("*-LAND-2026-Q2-meeting-spine.pptx"))
        decks = [d for d in decks if not d.name.startswith("~$")]
        for deck in decks:
            result = audit_deck(deck, contract)
            assert result.slide_count == 16, f"{deck.name} has {result.slide_count} slides"
            assert result.status == "pass", f"{deck.name} failed: {result.findings}"
