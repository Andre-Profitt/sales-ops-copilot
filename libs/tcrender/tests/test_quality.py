"""Tests for tcrender.quality -- production quality gate."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tcrender.models import RenderResult
from tcrender.quality import GateResult, QualityGateError, gate_render


_SLIDE_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp><p:txBody>
        <a:bodyPr/>
        <a:p><a:r><a:t>{text}</a:t></a:r></a:p>
      </p:txBody></p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""


def _make_pptx(tmp_path: Path, slides: list[str]) -> Path:
    out = tmp_path / "fake.pptx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, body in enumerate(slides, start=1):
            xml = _SLIDE_XML_TEMPLATE.format(
                text=body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            zf.writestr(f"ppt/slides/slide{i}.xml", xml.encode("utf-8"))
        zf.writestr("[Content_Types].xml", b"<Types/>")
    return out


def _make_ppttc(tmp_path: Path, *, director: str = "Jesper Tyrer", period: str = "2026-Q2") -> Path:
    p = tmp_path / "demo.ppttc"
    p.write_text(
        json.dumps(
            [
                {
                    "template": "x.pptx",
                    "data": [
                        {"name": "S01_DirectorName", "table": [[{"string": director}]]},
                        {"name": "S01_Period", "table": [[{"string": period}]]},
                        {
                            "name": "S01_ScopeLabel",
                            "table": [[{"string": "APAC region intelligence"}]],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return p


def _make_result(pptx: Path, ppttc: Path) -> RenderResult:
    return RenderResult(
        input_ppttc=ppttc,
        output_path=pptx,
        output_size_bytes=pptx.stat().st_size,
        exit_code=0,
        elapsed_seconds=1.0,
        ssh_stdout_tail="",
        ssh_stderr_tail="",
    )


def test_gate_passes_when_evidence_lands_and_no_jinja_leak(tmp_path: Path) -> None:
    pptx = _make_pptx(
        tmp_path,
        slides=["Jesper Tyrer review for 2026-Q2 -- APAC region intelligence"],
    )
    ppttc = _make_ppttc(tmp_path)
    result = _make_result(pptx, ppttc)

    gate = gate_render(result, ppttc, min_match_ratio=0.6)

    assert isinstance(gate, GateResult)
    assert gate.passed
    assert gate.failures == ()
    assert gate.binding_count == 3
    assert gate.bindings_with_evidence == 3
    assert gate.jinja_leaks == ()


def test_gate_fails_on_jinja_leak(tmp_path: Path) -> None:
    """Surviving ``{director_name}`` in slide XML -> no_jinja_leak failure."""
    pptx = _make_pptx(
        tmp_path,
        slides=["Jesper Tyrer 2026-Q2 APAC region intelligence -- {director_name}"],
    )
    ppttc = _make_ppttc(tmp_path)
    result = _make_result(pptx, ppttc)

    gate = gate_render(result, ppttc, min_match_ratio=0.6)
    assert not gate.passed
    checks = [f.check for f in gate.failures]
    assert "no_jinja_leak" in checks
    assert "director_name" in gate.jinja_leaks


def test_gate_fails_on_low_match_ratio(tmp_path: Path) -> None:
    """No evidence in slides -> verify_match_ratio AND completeness fail."""
    pptx = _make_pptx(tmp_path, slides=["completely unrelated body text"])
    ppttc = _make_ppttc(tmp_path)
    result = _make_result(pptx, ppttc)

    gate = gate_render(result, ppttc, min_match_ratio=0.6)
    assert not gate.passed
    checks = {f.check for f in gate.failures}
    assert "verify_match_ratio" in checks
    assert "completeness" in checks


def test_gate_brand_check_stub_passes(tmp_path: Path) -> None:
    """Today the brand check is a no-op stub -- gate stays green."""
    pptx = _make_pptx(
        tmp_path,
        slides=["Jesper Tyrer 2026-Q2 APAC region intelligence"],
    )
    ppttc = _make_ppttc(tmp_path)
    result = _make_result(pptx, ppttc)

    gate = gate_render(result, ppttc, min_match_ratio=0.6, brand_check=True)
    assert gate.passed
    assert "brand_check" not in {f.check for f in gate.failures}


def test_quality_gate_error_is_render_error_subclass() -> None:
    """QualityGateError must be catchable as RenderError for callers."""
    from tcrender.models import RenderError

    err = QualityGateError("boom")
    assert isinstance(err, RenderError)
    assert str(err) == "boom"


def test_gate_rejects_invalid_min_match_ratio(tmp_path: Path) -> None:
    pptx = _make_pptx(tmp_path, slides=["x"])
    ppttc = _make_ppttc(tmp_path)
    result = _make_result(pptx, ppttc)
    with pytest.raises(ValueError):
        gate_render(result, ppttc, min_match_ratio=2.0)
