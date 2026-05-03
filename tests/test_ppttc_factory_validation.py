from __future__ import annotations

import json
import sys
from pathlib import Path
from zipfile import ZipFile

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import build_ppttc_name_manifests as build_names  # noqa: E402
import run_ppttc_factory_validation as factory_validation  # noqa: E402


def _template_with_names(path: Path, names: list[str]) -> Path:
    with ZipFile(path, "w") as zf:
        for idx, name in enumerate(names, start=1):
            zf.writestr(
                f"ppt/slides/slide{idx}.xml",
                f"<p:sld>&lt;m_strName&gt;{name}&lt;/m_strName&gt;</p:sld>",
            )
    return path


def _ppttc(path: Path, template: Path, names: list[str]) -> Path:
    payload = [
        {
            "template": str(template.resolve()),
            "data": [
                {"name": name, "table": [[{"string": name}]]}
                for name in names
            ],
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_build_manifest_extracts_template_names(tmp_path: Path):
    template = _template_with_names(tmp_path / "wired.pptx", ["S01", "S02"])
    out = build_names.write_manifest(
        template,
        output_dir=tmp_path / "manifests",
        generated_at="2026-05-02T00:00:00+00:00",
    )
    payload = json.loads(out.read_text())
    assert payload["schema"] == "thinkcell-ppttc-expected-names/v1"
    assert payload["template_filename"] == "wired.pptx"
    assert payload["expected_names"] == ["S01", "S02"]
    assert len(payload["template_sha256"]) == 64


def test_build_manifest_extracts_multiple_escaped_names_in_one_xml_part(tmp_path: Path):
    template = tmp_path / "wired.pptx"
    with ZipFile(template, "w") as zf:
        zf.writestr(
            "ppt/slides/slide1.xml",
            (
                "<p:sld>"
                "&lt;m_strName&gt;S01&lt;/m_strName&gt;"
                "&lt;m_strName&gt;S02&lt;/m_strName&gt;"
                "</p:sld>"
            ),
        )

    out = build_names.write_manifest(
        template,
        output_dir=tmp_path / "manifests",
        generated_at="2026-05-02T00:00:00+00:00",
    )

    payload = json.loads(out.read_text())
    assert payload["expected_names"] == ["S01", "S02"]


def test_factory_validation_passes_matching_ppttc(tmp_path: Path):
    template = _template_with_names(tmp_path / "wired.pptx", ["S01", "S02"])
    manifest_dir = tmp_path / "manifests"
    build_names.write_manifest(template, output_dir=manifest_dir)
    ppttc = _ppttc(tmp_path / "deck.ppttc", template, ["S01", "S02"])

    report = factory_validation.build_report(
        period="2026-Q2",
        ppttc_paths=[ppttc],
        manifest_dir=manifest_dir,
        strict=True,
    )

    assert report["ok"] is True
    assert report["pass_count"] == 1
    assert report["results"][0]["manifest_match"] == "sha256"


def test_factory_validation_fails_name_drift_in_strict_mode(tmp_path: Path):
    template = _template_with_names(tmp_path / "wired.pptx", ["S01", "S02"])
    manifest_dir = tmp_path / "manifests"
    build_names.write_manifest(template, output_dir=manifest_dir)
    ppttc = _ppttc(tmp_path / "deck.ppttc", template, ["S01", "S99"])

    report = factory_validation.build_report(
        period="2026-Q2",
        ppttc_paths=[ppttc],
        manifest_dir=manifest_dir,
        strict=True,
    )

    assert report["ok"] is False
    validation = report["results"][0]["validation"]
    codes = {finding["code"] for finding in validation["findings"]}
    assert "manifest.missing_expected_name" in codes
    assert "manifest.unknown_emitted_name" in codes


def test_factory_validation_fails_when_manifest_missing(tmp_path: Path):
    template = _template_with_names(tmp_path / "wired.pptx", ["S01"])
    ppttc = _ppttc(tmp_path / "deck.ppttc", template, ["S01"])

    report = factory_validation.build_report(
        period="2026-Q2",
        ppttc_paths=[ppttc],
        manifest_dir=tmp_path / "missing-manifests",
        strict=True,
    )

    assert report["ok"] is False
    assert report["results"][0]["manifest_match"] == "no_matching_manifest"
