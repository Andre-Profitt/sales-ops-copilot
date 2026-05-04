"""Tests for tcrender.template_prep -- Jinja-style placeholder substitution."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tcrender.template_prep import (
    binding_name_to_placeholder,
    extract_scalar_string_bindings,
    scan_placeholders,
    substitute_placeholders,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PPTTC = REPO_ROOT / "_windows_test" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"
LAND_TEMPLATE = REPO_ROOT / "_windows_test" / "LAND_template.pptx"


# -- binding_name_to_placeholder ------------------------------------------


@pytest.mark.parametrize(
    ("binding_name", "expected"),
    [
        ("S01_DirectorName", "director_name"),
        ("S01_Period", "period"),
        ("S01_ScopeLabel", "scope_label"),
        ("S22_StaleActivityFootnote", "stale_activity_footnote"),
        ("S100_LongIdentifierName", "long_identifier_name"),
        ("DirectorName", "director_name"),
        ("already_snake", "already_snake"),
        # Single-segment Pascal -> lowercase
        ("Period", "period"),
    ],
)
def test_binding_name_to_placeholder_examples(binding_name: str, expected: str) -> None:
    assert binding_name_to_placeholder(binding_name) == expected


def test_binding_name_to_placeholder_rejects_empty() -> None:
    with pytest.raises(ValueError):
        binding_name_to_placeholder("")
    with pytest.raises(ValueError):
        binding_name_to_placeholder("   ")


# -- scan_placeholders ----------------------------------------------------


def test_scan_placeholders_on_land_template() -> None:
    """The shipped LAND_template.pptx must contain the 3 cover-slide placeholders."""
    assert LAND_TEMPLATE.exists(), f"LAND template missing: {LAND_TEMPLATE}"
    found = scan_placeholders(LAND_TEMPLATE)
    # Three known placeholders from manual inspection 2026-05-02:
    # {director_name} on slide1, {period} on slides 1/2/5/12/23/26,
    # {scope_label} on slide1.
    assert "director_name" in found
    assert "period" in found
    assert "scope_label" in found
    # director_name lives on slide1.xml only.
    assert any(p.name == "slide1.xml" for p in found["director_name"])
    # period appears on multiple slides.
    assert len(found["period"]) >= 2


def test_scan_placeholders_on_pptx_with_no_placeholders(tmp_path: Path) -> None:
    """A .pptx with no placeholders returns an empty dict."""
    fake = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>plain title, no braces</a:t></a:r></a:p>",
    )
    assert scan_placeholders(fake) == {}


def test_scan_placeholders_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        scan_placeholders(tmp_path / "does-not-exist.pptx")


# -- substitute_placeholders ----------------------------------------------


def test_substitute_placeholders_does_not_mutate_input(tmp_path: Path) -> None:
    """The input .pptx must remain byte-identical after substitution."""
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>{name} ships at {time}</a:t></a:r></a:p>",
    )
    src_bytes_before = src.read_bytes()

    out = substitute_placeholders(
        src,
        bindings={"name": "Jesper", "time": "2026-Q2"},
        output_path=tmp_path / "out.pptx",
    )

    assert out.exists()
    assert out != src
    assert src.read_bytes() == src_bytes_before, "input was mutated"


def test_substitute_placeholders_replaces_all_in_slide_xml(tmp_path: Path) -> None:
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text=(
            "<a:p><a:r><a:t>{director_name}</a:t></a:r></a:p>"
            "<a:p><a:r><a:t>{period} review - {scope_label}</a:t></a:r></a:p>"
        ),
    )
    out = substitute_placeholders(
        src,
        bindings={
            "director_name": "Jesper Tyrer",
            "period": "2026-Q2",
            "scope_label": "APAC",
        },
        output_path=tmp_path / "out.pptx",
    )
    slide_xml = _read_slide1(out)
    assert "Jesper Tyrer" in slide_xml
    assert "2026-Q2" in slide_xml
    assert "APAC" in slide_xml
    assert "{director_name}" not in slide_xml
    assert "{period}" not in slide_xml
    assert "{scope_label}" not in slide_xml


def test_substitute_placeholders_leaves_unknown_keys_alone(tmp_path: Path) -> None:
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>{known} and {unknown}</a:t></a:r></a:p>",
    )
    out = substitute_placeholders(
        src,
        bindings={"known": "FOUND"},
        output_path=tmp_path / "out.pptx",
    )
    slide_xml = _read_slide1(out)
    assert "FOUND" in slide_xml
    assert "{unknown}" in slide_xml, "unknown placeholders must be preserved"


def test_substitute_placeholders_default_output_path_is_tempdir(tmp_path: Path) -> None:
    """When output_path=None, result lives outside tmp_path (in tempdir)."""
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>{x}</a:t></a:r></a:p>",
    )
    out = substitute_placeholders(src, bindings={"x": "Y"}, output_path=None)
    assert out.exists()
    assert out.suffix == ".pptx"
    assert out != src
    assert "substituted" in out.name
    # And it must still be a valid zip / contain the substitution.
    assert zipfile.is_zipfile(out)
    assert "Y" in _read_slide1(out)


def test_substitute_placeholders_rejects_non_string_values(tmp_path: Path) -> None:
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>x</a:t></a:r></a:p>",
    )
    with pytest.raises(TypeError):
        substitute_placeholders(
            src,
            bindings={"x": 42},  # type: ignore[dict-item]
            output_path=tmp_path / "out.pptx",
        )


def test_substitute_placeholders_does_not_break_zip_for_non_slide_parts(
    tmp_path: Path,
) -> None:
    """Non-slide parts must round-trip byte-for-byte through the zip."""
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>{x}</a:t></a:r></a:p>",
        extra_parts={"docProps/app.xml": b"<Properties>app metadata</Properties>"},
    )
    out = substitute_placeholders(
        src,
        bindings={"x": "Y"},
        output_path=tmp_path / "out.pptx",
    )
    with zipfile.ZipFile(out, "r") as zf:
        assert zf.read("docProps/app.xml") == b"<Properties>app metadata</Properties>"
        assert "Y" in zf.read("ppt/slides/slide1.xml").decode("utf-8")


def test_substitute_placeholders_preserves_xml_declaration(tmp_path: Path) -> None:
    """Output slide XML must retain an <?xml ... ?> declaration (PowerPoint requires it)."""
    src = _make_pptx_with_slide(
        tmp_path,
        slide_text="<a:p><a:r><a:t>{x}</a:t></a:r></a:p>",
    )
    out = substitute_placeholders(
        src,
        bindings={"x": "Y"},
        output_path=tmp_path / "out.pptx",
    )
    slide_xml = _read_slide1(out)
    assert slide_xml.startswith("<?xml")


# -- extract_scalar_string_bindings ---------------------------------------


def test_extract_scalar_string_bindings_on_jesper_fixture() -> None:
    """The Jesper-Tyrer .ppttc must yield the 3 cover-slide scalars (and others)."""
    assert FIXTURE_PPTTC.exists(), f"fixture missing: {FIXTURE_PPTTC}"
    out = extract_scalar_string_bindings(FIXTURE_PPTTC)
    assert out["director_name"] == "Jesper Tyrer"
    assert out["period"] == "2026-Q2"
    assert out["scope_label"] == "APAC"


def test_extract_scalar_string_bindings_skips_tabular_bindings(tmp_path: Path) -> None:
    """Multi-row / multi-cell tables must NOT be projected as scalars."""
    p = tmp_path / "demo.ppttc"
    p.write_text(
        json.dumps(
            [
                {
                    "template": "x.pptx",
                    "data": [
                        {
                            "name": "S01_DirectorName",
                            "table": [[{"string": "Jesper Tyrer"}]],
                        },
                        {
                            "name": "S04_Pipe",
                            "table": [
                                [None, {"string": "Opening"}, {"string": "Closing"}],
                                [{"string": "ARR"}, {"number": 1.0}, {"number": 2.0}],
                            ],
                        },
                        {
                            "name": "S05_Numeric",
                            "table": [[{"number": 99.0}]],
                        },
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    out = extract_scalar_string_bindings(p)
    assert out == {"director_name": "Jesper Tyrer"}


def test_extract_scalar_string_bindings_rejects_non_array_top_level(tmp_path: Path) -> None:
    p = tmp_path / "bad.ppttc"
    p.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        extract_scalar_string_bindings(p)


# -- helpers --------------------------------------------------------------


_SLIDE_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:sp>
        <p:txBody>
          <a:bodyPr/>
          {body}
        </p:txBody>
      </p:sp>
    </p:spTree>
  </p:cSld>
</p:sld>
"""


def _make_pptx_with_slide(
    tmp_path: Path,
    slide_text: str,
    extra_parts: dict[str, bytes] | None = None,
) -> Path:
    """Build a minimal .pptx with one slide containing ``slide_text``.

    The fake .pptx is just a zip with ``ppt/slides/slide1.xml`` plus any
    ``extra_parts`` the caller wants. Enough to exercise scan/substitute
    semantics without bringing in python-pptx.
    """
    out = tmp_path / "fake.pptx"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "ppt/slides/slide1.xml",
            _SLIDE_XML_TEMPLATE.format(body=slide_text).encode("utf-8"),
        )
        zf.writestr("[Content_Types].xml", b"<Types/>")
        if extra_parts:
            for name, data in extra_parts.items():
                zf.writestr(name, data)
    return out


def _read_slide1(pptx: Path) -> str:
    with zipfile.ZipFile(pptx, "r") as zf:
        return zf.read("ppt/slides/slide1.xml").decode("utf-8")
