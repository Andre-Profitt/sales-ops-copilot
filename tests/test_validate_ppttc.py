"""Tests for scripts/validate_ppttc.py.

The validator is the reusable `.ppttc` lint gate that the monthly factory
calls before handing files to the Windows VM bridge. These tests pin the
structural rules and the manifest-drift rules without touching Office,
the VM bridge, or think-cell.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import validate_ppttc as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _payload(*entries: dict, template: str = "/tmp/wired.pptx") -> list[dict]:
    return [{"template": template, "data": list(entries)}]


def _entry(name: str, table: list | None = None) -> dict:
    return {"name": name, "table": table if table is not None else [[{"string": name}]]}


# ---------------------------------------------------------------------------
# Top-level shape
# ---------------------------------------------------------------------------


def test_valid_payload_passes_with_no_findings():
    payload = _payload(_entry("S01_DirectorName"), _entry("S04_PipeMovement"))
    result = mod.validate_ppttc(payload)
    assert result.ok is True
    assert result.findings == []
    assert len(result.templates) == 1
    assert result.templates[0].emitted_names == ["S01_DirectorName", "S04_PipeMovement"]


def test_top_level_must_be_array():
    result = mod.validate_ppttc({"template": "x", "data": []})
    assert result.ok is False
    codes = {f.code for f in result.findings}
    assert "ppttc.not_array" in codes


def test_empty_top_level_array_is_error():
    result = mod.validate_ppttc([])
    assert result.ok is False
    assert any(f.code == "ppttc.empty" for f in result.findings)


def test_template_object_must_have_template_key():
    result = mod.validate_ppttc([{"data": []}])
    codes = {f.code for f in result.findings}
    assert "template.missing_template_key" in codes


def test_template_value_must_be_non_empty_string():
    result = mod.validate_ppttc([{"template": "", "data": []}])
    codes = {f.code for f in result.findings}
    assert "template.invalid_template_value" in codes


def test_template_object_must_have_data_array():
    result = mod.validate_ppttc([{"template": "/tmp/x.pptx"}])
    codes = {f.code for f in result.findings}
    assert "template.missing_data" in codes


def test_data_must_be_array():
    result = mod.validate_ppttc([{"template": "/tmp/x.pptx", "data": "S01"}])
    codes = {f.code for f in result.findings}
    assert "template.data_not_array" in codes


# ---------------------------------------------------------------------------
# Data entry shape
# ---------------------------------------------------------------------------


def test_entry_must_be_object():
    result = mod.validate_ppttc(_payload("not-an-object"))  # type: ignore[arg-type]
    codes = {f.code for f in result.findings}
    assert "data.entry_not_object" in codes


def test_entry_must_have_name():
    payload = _payload({"table": [[{"string": "x"}]]})
    result = mod.validate_ppttc(payload)
    codes = {f.code for f in result.findings}
    assert "data.invalid_name" in codes


def test_entry_must_have_table():
    payload = _payload({"name": "S01_DirectorName"})
    result = mod.validate_ppttc(payload)
    codes = {f.code for f in result.findings}
    assert "data.missing_table" in codes


def test_table_must_be_array():
    payload = _payload({"name": "S01", "table": "rows"})
    result = mod.validate_ppttc(payload)
    codes = {f.code for f in result.findings}
    assert "data.table_not_array" in codes


def test_row_must_be_array():
    payload = _payload({"name": "S01", "table": ["scalar"]})
    result = mod.validate_ppttc(payload)
    codes = {f.code for f in result.findings}
    assert "data.row_not_array" in codes


def test_cell_can_be_null_or_known_tagged_object():
    payload = _payload(
        _entry("S01", table=[[None, {"string": "hi"}, {"number": 1.5}, {"date": "2026-05-01"}]]),
    )
    result = mod.validate_ppttc(payload)
    assert result.ok is True


def test_cell_with_unknown_tag_is_warning_not_error():
    payload = _payload(_entry("S01", table=[[{"string": "hi", "weird": True}]]))
    result = mod.validate_ppttc(payload)
    assert result.ok is True
    assert any(f.code == "data.cell_unknown_tag" for f in result.warnings)


def test_cell_with_no_known_tag_is_error():
    payload = _payload(_entry("S01", table=[[{"weird": True}]]))
    result = mod.validate_ppttc(payload)
    assert result.ok is False
    assert any(f.code == "data.cell_missing_tag" for f in result.findings)


def test_cell_with_multiple_value_tags_is_error():
    payload = _payload(_entry("S01", table=[[{"string": "1", "number": 1}]]))
    result = mod.validate_ppttc(payload)
    assert result.ok is False
    assert any(f.code == "data.cell_multiple_tags" for f in result.findings)


def test_cell_must_be_null_or_object():
    payload = _payload(_entry("S01", table=[["bare-string"]]))
    result = mod.validate_ppttc(payload)
    assert result.ok is False
    assert any(f.code == "data.cell_not_object" for f in result.findings)


# ---------------------------------------------------------------------------
# Duplicate names
# ---------------------------------------------------------------------------


def test_duplicate_names_are_error():
    payload = _payload(
        _entry("S04_PipeMovement"),
        _entry("S04_PipeMovement"),
        _entry("S05_PipelineByStage"),
    )
    result = mod.validate_ppttc(payload)
    assert result.ok is False
    dup_findings = [f for f in result.findings if f.code == "data.duplicate_name"]
    assert len(dup_findings) == 1
    assert dup_findings[0].entry_name == "S04_PipeMovement"
    assert "S04_PipeMovement" in result.templates[0].duplicate_names


def test_duplicate_name_check_is_per_template_not_cross_template():
    payload = [
        {"template": "/tmp/a.pptx", "data": [_entry("S01")]},
        {"template": "/tmp/b.pptx", "data": [_entry("S01")]},
    ]
    result = mod.validate_ppttc(payload)
    assert result.ok is True
    assert all(not t.duplicate_names for t in result.templates)


# ---------------------------------------------------------------------------
# Expected-name manifest drift
# ---------------------------------------------------------------------------


def test_missing_expected_name_is_warning_in_default_mode():
    payload = _payload(_entry("S01_DirectorName"))
    result = mod.validate_ppttc(payload, expected_names=["S01_DirectorName", "S04_PipeMovement"])
    assert result.ok is True  # warning, not error
    assert any(
        f.code == "manifest.missing_expected_name" and f.entry_name == "S04_PipeMovement"
        for f in result.warnings
    )
    assert "S04_PipeMovement" in result.templates[0].missing_expected_names


def test_unknown_emitted_name_is_warning_in_default_mode():
    payload = _payload(_entry("S01_DirectorName"), _entry("S99_Bogus"))
    result = mod.validate_ppttc(payload, expected_names=["S01_DirectorName"])
    assert result.ok is True
    assert any(
        f.code == "manifest.unknown_emitted_name" and f.entry_name == "S99_Bogus"
        for f in result.warnings
    )
    assert "S99_Bogus" in result.templates[0].unknown_emitted_names


def test_strict_mode_promotes_drift_to_errors():
    payload = _payload(_entry("S01_DirectorName"), _entry("S99_Bogus"))
    result = mod.validate_ppttc(
        payload,
        expected_names=["S01_DirectorName", "S04_PipeMovement"],
        strict=True,
    )
    assert result.ok is False
    codes = {f.code for f in result.errors}
    assert "manifest.missing_expected_name" in codes
    assert "manifest.unknown_emitted_name" in codes


def test_no_manifest_means_no_drift_findings():
    payload = _payload(_entry("S99_Bogus"))
    result = mod.validate_ppttc(payload)
    assert result.ok is True
    assert all(not f.code.startswith("manifest.") for f in result.findings)
    assert result.templates[0].missing_expected_names == []
    assert result.templates[0].unknown_emitted_names == []


def test_empty_manifest_treats_every_emitted_name_as_unknown_drift():
    payload = _payload(_entry("S01"))
    result = mod.validate_ppttc(payload, expected_names=[], strict=False)
    # An empty list is falsy and treated as "no manifest"; this is the
    # contract callers rely on so they can pass an unconditional value.
    assert result.ok is True
    assert all(not f.code.startswith("manifest.") for f in result.findings)


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def test_load_expected_names_from_json_array(tmp_path: Path):
    path = tmp_path / "names.json"
    path.write_text(json.dumps(["A", "B", "C"]))
    assert mod.load_expected_names(path) == ["A", "B", "C"]


def test_load_expected_names_from_json_object_with_expected_names(tmp_path: Path):
    path = tmp_path / "names.json"
    path.write_text(json.dumps({"expected_names": ["A", "B"]}))
    assert mod.load_expected_names(path) == ["A", "B"]


def test_load_expected_names_from_json_object_with_categorized_lists(tmp_path: Path):
    path = tmp_path / "names.json"
    path.write_text(
        json.dumps(
            {
                "chart_names": ["S04_PipeMovement"],
                "text_names": ["S01_DirectorName"],
                "table_names": ["S07_TopDealsLand"],
            }
        )
    )
    names = mod.load_expected_names(path)
    assert set(names) == {
        "S04_PipeMovement",
        "S01_DirectorName",
        "S07_TopDealsLand",
    }


def test_load_expected_names_from_newline_delimited_with_comments(tmp_path: Path):
    path = tmp_path / "names.txt"
    path.write_text("# preamble\nS01_DirectorName\n\nS04_PipeMovement\n# trailing\n")
    assert mod.load_expected_names(path) == [
        "S01_DirectorName",
        "S04_PipeMovement",
    ]


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def _write_ppttc(tmp_path: Path, payload: list[dict]) -> Path:
    path = tmp_path / "deck.ppttc"
    path.write_text(json.dumps(payload))
    return path


def test_cli_returns_zero_on_clean_file(tmp_path: Path, capsys: pytest.CaptureFixture):
    path = _write_ppttc(tmp_path, _payload(_entry("S01"), _entry("S04_PipeMovement")))
    rc = mod.main([str(path)])
    out = capsys.readouterr()
    assert rc == 0
    assert "ok=yes" in out.out
    assert "names=2" in out.out


def test_cli_returns_two_on_structural_error(tmp_path: Path, capsys: pytest.CaptureFixture):
    path = _write_ppttc(tmp_path, _payload(_entry("S01"), _entry("S01")))
    rc = mod.main([str(path)])
    out = capsys.readouterr()
    assert rc == 2
    assert "data.duplicate_name" in out.err
    assert "ok=no" in out.out


def test_cli_strict_promotes_manifest_drift_to_error_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture
):
    path = _write_ppttc(tmp_path, _payload(_entry("S01")))
    manifest = tmp_path / "expected.json"
    manifest.write_text(json.dumps(["S01", "S04_PipeMovement"]))
    rc = mod.main([str(path), "--expected-names", str(manifest), "--strict"])
    out = capsys.readouterr()
    assert rc == 2
    assert "manifest.missing_expected_name" in out.err


def test_cli_warnings_as_errors_returns_three(tmp_path: Path):
    path = _write_ppttc(tmp_path, _payload(_entry("S01")))
    manifest = tmp_path / "expected.json"
    manifest.write_text(json.dumps(["S01", "S04_PipeMovement"]))
    rc = mod.main([str(path), "--expected-names", str(manifest), "--warnings-as-errors"])
    assert rc == 3


def test_cli_json_mode_emits_json_payload_to_stdout(tmp_path: Path, capsys: pytest.CaptureFixture):
    path = _write_ppttc(tmp_path, _payload(_entry("S01"), _entry("S01")))
    rc = mod.main([str(path), "--json"])
    out = capsys.readouterr()
    assert rc == 2
    parsed = json.loads(out.out)
    assert parsed["ok"] is False
    assert any(f["code"] == "data.duplicate_name" for f in parsed["findings"])
    assert parsed["templates"][0]["duplicate_names"] == ["S01"]


def test_cli_invalid_json_exits_with_clear_message(tmp_path: Path):
    path = tmp_path / "bad.ppttc"
    path.write_text("{not: 'valid'")
    with pytest.raises(SystemExit) as exc_info:
        mod.main([str(path)])
    assert "invalid JSON" in str(exc_info.value)


def test_cli_missing_file_exits_clean(tmp_path: Path):
    with pytest.raises(SystemExit):
        mod.main([str(tmp_path / "nope.ppttc")])
