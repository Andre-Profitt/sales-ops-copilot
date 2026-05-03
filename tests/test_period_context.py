from pathlib import Path
import sys

import pytest

from scripts.period_context import context_for_period

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from upload_may_regional_assets_sharepoint import planned_assets  # noqa: E402


def test_may_period_context_drives_sharepoint_paths() -> None:
    context = context_for_period("2026-Q2")

    assert context.month_label == "May 2026"
    assert context.sharepoint_folder.endswith("/Q2 2026/May 2026")
    assert context.sharepoint_warning_filename == "README_DO_NOT_USE_May_2026_decks_pending_QA.txt"
    assert context.sharepoint_upload_manifest_name == "sharepoint_may_2026_upload_manifest.json"
    assert context.sharepoint_validation_manifest_name == "sharepoint_may_2026_validation_manifest.json"
    assert "LAND Meeting Spine - May 2026.pptx" in context.sharepoint_publish_suffixes


def test_unsupported_periods_fail_closed_until_certified() -> None:
    with pytest.raises(ValueError, match="only 2026-Q2 / May 2026"):
        context_for_period("2026-Q3")


def test_planned_assets_use_period_context_names() -> None:
    assets = planned_assets("2026-Q2")
    publish_names = [name for _, name in assets]

    assert "Jesper Tyrer APAC LAND Meeting Spine - May 2026.pptx" in publish_names
    assert "Jesper Tyrer APAC Connected Excel Audit Workbook - May 2026.xlsx" in publish_names
    assert "Jesper Tyrer APAC PowerPoint Table Source Workbook - May 2026.xlsx" in publish_names
    assert any(Path(path).name == "sharepoint_may_2026_upload_manifest.json" for path, _ in assets)
