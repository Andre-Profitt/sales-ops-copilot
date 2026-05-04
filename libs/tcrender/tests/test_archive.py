"""Tests for tcrender.archive -- per-director archival + audit sidecar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tcrender.archive import ARCHIVE_AUDIT_FILENAME, archive_render
from tcrender.models import RenderResult


def _make_render_result(tmp_path: Path, *, content: bytes = b"PK\x03\x04dummy") -> RenderResult:
    """Materialize a fake .pptx and a synthetic .ppttc, return a RenderResult."""
    out = tmp_path / "Jesper-Tyrer-LAND-2026-Q2.pptx"
    out.write_bytes(content)
    ppttc = tmp_path / "Jesper.ppttc"
    ppttc.write_text(
        json.dumps(
            [
                {
                    "template": "x.pptx",
                    "data": [
                        {"name": "S01_DirectorName", "table": [[{"string": "Jesper Tyrer"}]]},
                        {"name": "S01_Period", "table": [[{"string": "2026-Q2"}]]},
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    return RenderResult(
        input_ppttc=ppttc,
        output_path=out,
        output_size_bytes=len(content),
        exit_code=0,
        elapsed_seconds=2.5,
        ssh_stdout_tail="ok",
        ssh_stderr_tail="",
    )


def test_archive_render_moves_pptx_into_per_director_tree(tmp_path: Path) -> None:
    """Archived .pptx ends up at <root>/<period>/<dir>/decks/<ts>/<file>."""
    result = _make_render_result(tmp_path)
    archive_root = tmp_path / "state"

    archived = archive_render(
        result,
        director="Jesper-Tyrer",
        period="2026-Q2",
        audit={"fix_F_01": "fixed-2026-05-03", "fix_F_02": "fixed-2026-05-03"},
        archive_root=archive_root,
        timestamp="20260503-180000",
        ppttc_path=result.input_ppttc,
    )

    assert archived.exists()
    assert archived.parent.parent == archive_root / "2026-Q2" / "Jesper-Tyrer" / "decks"
    # Original output got moved (not copied)
    assert not Path(result.output_path).exists()


def test_archive_render_emits_audit_sidecar_with_hashes(tmp_path: Path) -> None:
    """audit.json must capture sha256 + size for ppttc, template, output."""
    result = _make_render_result(tmp_path)
    template = tmp_path / "LAND_template.pptx"
    template.write_bytes(b"PK\x03\x04tpldummy")

    archived = archive_render(
        result,
        director="Jesper Tyrer",  # space-form should be normalized
        period="2026-Q2",
        audit={"fix_F_01": "fixed", "note": "smoke"},
        archive_root=tmp_path / "state",
        timestamp="20260503-180000",
        template_path=template,
        ppttc_path=result.input_ppttc,
    )

    audit = archived.parent / ARCHIVE_AUDIT_FILENAME
    assert audit.exists()
    payload = json.loads(audit.read_text())

    # Director slug normalization
    assert payload["director"] == "Jesper-Tyrer"
    assert payload["period"] == "2026-Q2"
    # File-meta blocks
    assert payload["ppttc"]["sha256"]
    assert payload["ppttc"]["binding_count"] == 2
    assert payload["template"]["sha256"]
    assert payload["template"]["size_bytes"] == len(b"PK\x03\x04tpldummy")
    assert payload["output"]["sha256"]
    assert payload["output"]["size_bytes_at_render"] == result.output_size_bytes
    # Caller fix flags survive
    assert payload["fix_F_01"] == "fixed"
    assert payload["note"] == "smoke"
    # Render block carries elapsed + exit_code
    assert payload["render"]["exit_code"] == 0
    assert payload["render"]["elapsed_seconds"] == 2.5


def test_archive_render_extra_audit_overrides_caller_audit(tmp_path: Path) -> None:
    """``extra_audit`` should win on key collision with ``audit``."""
    result = _make_render_result(tmp_path)
    archived = archive_render(
        result,
        director="Jesper-Tyrer",
        period="2026-Q2",
        audit={"shared_key": "from_audit", "only_audit": True},
        archive_root=tmp_path / "state",
        timestamp="20260503-180000",
        ppttc_path=result.input_ppttc,
        extra_audit={"shared_key": "from_extra", "only_extra": True},
    )
    payload = json.loads((archived.parent / ARCHIVE_AUDIT_FILENAME).read_text())
    assert payload["shared_key"] == "from_extra"
    assert payload["only_audit"] is True
    assert payload["only_extra"] is True


def test_archive_render_raises_when_output_missing(tmp_path: Path) -> None:
    """Archival is a no-op only when the source exists."""
    out = tmp_path / "missing.pptx"
    result = RenderResult(
        input_ppttc=tmp_path / "x.ppttc",
        output_path=out,
        output_size_bytes=0,
        exit_code=0,
        elapsed_seconds=0.0,
        ssh_stdout_tail="",
        ssh_stderr_tail="",
    )
    with pytest.raises(FileNotFoundError):
        archive_render(
            result,
            director="Jesper-Tyrer",
            period="2026-Q2",
            archive_root=tmp_path / "state",
        )
