"""Tests for the QTR07 Mekko promotion gate."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from run_qtr07_mekko_promotion_gate import (  # noqa: E402
    QTR07_SOURCE_NAME,
    QTR07_TARGET_NAME,
    SLIDE_INDEX,
    run_audit,
)


class TestPromotionGate:
    def test_runs_against_current_state(self) -> None:
        payload = run_audit(period="2026-Q2")
        assert payload["schema"] == "qtr07-mekko-promotion-gate/v1"
        assert payload["target_chart"] == QTR07_TARGET_NAME
        assert payload["source_seed_name"] == QTR07_SOURCE_NAME
        assert payload["slide_index"] == SLIDE_INDEX
        # 9 canonical MD-1 directors must always be evaluated.
        assert payload["summary"]["directors_total"] == 9
        # Status is one of the four documented values.
        assert payload["status"] in {"pass", "warn", "fail"}

    def test_classification_taxonomy(self) -> None:
        payload = run_audit(period="2026-Q2")
        valid = {
            "native_chart_promoted",
            "table_image_fallback",
            "native_table_other",
            "missing",
            "error",
        }
        for r in payload["results"]:
            assert r["classification"] in valid, r

    def test_promotion_path_is_documented(self) -> None:
        payload = run_audit(period="2026-Q2")
        assert payload["promotion_path"], "promotion path must be documented"
        steps = payload["promotion_path"]
        assert any("ppttc" in step.lower() for step in steps)
        assert any("windows" in step.lower() or "vm" in step.lower() for step in steps)
