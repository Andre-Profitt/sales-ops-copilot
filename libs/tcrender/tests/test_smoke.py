"""Mac-runnable smoke tests for `tcrender`.

What's exercised at import time (no SSH required):
    1. Public API imports resolve -- TcRenderClient, SSHTransport, etc.
    2. Frozen dataclasses behave as dataclasses (immutable).
    3. validate_ppttc on the canonical Jesper-Tyrer fixture returns
       valid=True with binding_count == 42.
    4. validate_ppttc rejects the documented bad shapes.

What runs only when TCRENDER_LIVE=1 (Mac -> Windows-VM SSH round-trip):
    5. Real ppttc.exe render against the Jesper-Tyrer fixture +
       LAND_template.pptx donor; verifies the ferried output exists,
       is > 8 MB, and zipfile.is_zipfile returns True.

The live test verifies what the user's brief specifies: documented per
extraction.json that ppttc.exe is the only documented headless render path,
and the live verification matches the prior CLI run on the VM that produced
the 8,932,404-byte reference output.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

# Repo layout: libs/tcrender/tests/test_smoke.py -> repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PPTTC = REPO_ROOT / "_windows_test" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"
LAND_TEMPLATE = REPO_ROOT / "_windows_test" / "LAND_template.pptx"

# Reference output observed live on Windows-VM 2026-05-02
REFERENCE_OUTPUT_BYTES = 8_932_404
REFERENCE_OUTPUT_FLOOR = 8 * 1024 * 1024  # 8 MiB minimum
EXPECTED_BINDING_COUNT = 42


def test_public_api_imports_clean() -> None:
    """All documented public symbols must import without side effects."""
    import tcrender

    assert hasattr(tcrender, "TcRenderClient")
    assert hasattr(tcrender, "SSHTransport")
    assert hasattr(tcrender, "Transport")
    assert hasattr(tcrender, "RenderResult")
    assert hasattr(tcrender, "ValidationResult")
    assert hasattr(tcrender, "RenderError")
    assert tcrender.__version__ == "0.1.0"


def test_render_result_is_frozen(tmp_path: Path) -> None:
    """RenderResult is a frozen dataclass (public contract)."""
    from tcrender import RenderResult

    r = RenderResult(
        input_ppttc=tmp_path / "a.ppttc",
        output_path=tmp_path / "b.pptx",
        output_size_bytes=100,
        exit_code=0,
        elapsed_seconds=1.0,
        ssh_stdout_tail="",
        ssh_stderr_tail="",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        r.exit_code = 1  # type: ignore[misc]


def test_validation_result_is_frozen() -> None:
    from tcrender import ValidationResult

    v = ValidationResult(valid=True, errors=(), binding_count=0)
    with pytest.raises((FrozenInstanceError, AttributeError)):
        v.valid = False  # type: ignore[misc]


def test_validate_ppttc_on_jesper_fixture() -> None:
    """The canonical fixture must validate with exactly 42 named bindings."""
    from tcrender import TcRenderClient

    assert FIXTURE_PPTTC.exists(), f"fixture missing: {FIXTURE_PPTTC}"
    client = TcRenderClient()
    v = client.validate_ppttc(FIXTURE_PPTTC)
    assert v.valid, f"unexpected validation errors: {v.errors}"
    assert v.binding_count == EXPECTED_BINDING_COUNT, (
        f"expected {EXPECTED_BINDING_COUNT} bindings, got {v.binding_count}"
    )


def test_validate_ppttc_rejects_object_top_level(tmp_path: Path) -> None:
    from tcrender import TcRenderClient

    bad = tmp_path / "bad.ppttc"
    bad.write_text("{}", encoding="utf-8")
    v = TcRenderClient().validate_ppttc(bad)
    assert not v.valid
    assert any("must be JSON array" in e for e in v.errors)


def test_validate_ppttc_rejects_empty_array(tmp_path: Path) -> None:
    from tcrender import TcRenderClient

    bad = tmp_path / "bad.ppttc"
    bad.write_text("[]", encoding="utf-8")
    v = TcRenderClient().validate_ppttc(bad)
    assert not v.valid
    assert any("empty" in e for e in v.errors)


def test_validate_ppttc_rejects_missing_template(tmp_path: Path) -> None:
    from tcrender import TcRenderClient

    bad = tmp_path / "bad.ppttc"
    bad.write_text('[{"data": []}]', encoding="utf-8")
    v = TcRenderClient().validate_ppttc(bad)
    assert not v.valid
    assert any("template" in e for e in v.errors)


def test_validate_ppttc_rejects_invalid_json(tmp_path: Path) -> None:
    from tcrender import TcRenderClient

    bad = tmp_path / "bad.ppttc"
    bad.write_text("{not valid json", encoding="utf-8")
    v = TcRenderClient().validate_ppttc(bad)
    assert not v.valid
    assert any("invalid JSON" in e for e in v.errors)


def test_validate_ppttc_rejects_missing_file(tmp_path: Path) -> None:
    from tcrender import TcRenderClient

    v = TcRenderClient().validate_ppttc(tmp_path / "nope.ppttc")
    assert not v.valid


def test_ssh_transport_constructible_with_default_host() -> None:
    """Construction must not require network -- only `SSHTransport()`."""
    from tcrender import SSHTransport

    t = SSHTransport()
    assert t.host == "Windows-VM"
    # Custom host should round-trip
    t2 = SSHTransport(host="Other-VM")
    assert t2.host == "Other-VM"


def test_winquote_handles_paths_with_spaces() -> None:
    """Internal helper used to build PowerShell command lines."""
    from tcrender.transport import SSHTransport

    q = SSHTransport._winquote(r"C:\Program Files (x86)\think-cell\ppttc.exe")
    assert q.startswith("'") and q.endswith("'")
    assert "Program Files (x86)" in q


def test_rewrite_ppttc_with_no_override_is_passthrough() -> None:
    """When template_override=None, parsed list must match disk content."""
    import json

    from tcrender.transport import SSHTransport

    rewritten = SSHTransport._rewrite_ppttc(FIXTURE_PPTTC, None)
    original = json.loads(FIXTURE_PPTTC.read_text(encoding="utf-8"))
    assert rewritten == original


def test_rewrite_ppttc_overrides_all_entries() -> None:
    from tcrender.transport import SSHTransport

    new_path = r"C:\Users\test\AppData\Local\Temp\stage\template.pptx"
    rewritten = SSHTransport._rewrite_ppttc(FIXTURE_PPTTC, new_path)
    assert all(entry["template"] == new_path for entry in rewritten)


# -- live render (gated) --------------------------------------------------

LIVE = os.environ.get("TCRENDER_LIVE") == "1"


@pytest.mark.skipif(not LIVE, reason="live render gated behind TCRENDER_LIVE=1")
def test_live_render_jesper_fixture(tmp_path: Path) -> None:
    """End-to-end: stage, ppttc.exe, ferry. Runs only with TCRENDER_LIVE=1.

    Verifies:
        - exit_code == 0
        - ferried output exists, > 8 MiB, and is a valid zip
        - elapsed_seconds reported
    """
    from tcrender import TcRenderClient

    assert FIXTURE_PPTTC.exists(), f"fixture missing: {FIXTURE_PPTTC}"
    assert LAND_TEMPLATE.exists(), f"LAND template missing: {LAND_TEMPLATE}"

    out_path = tmp_path / "Jesper-Tyrer-LAND-2026-Q2-output-LIVE.pptx"
    client = TcRenderClient()
    result = client.render(
        ppttc_path=FIXTURE_PPTTC,
        output_path=out_path,
        template_override=LAND_TEMPLATE,
        timeout=240.0,
    )
    assert result.exit_code == 0, f"ppttc.exe failed: stderr={result.ssh_stderr_tail}"
    assert out_path.exists(), "ferried output missing"
    assert result.output_size_bytes >= REFERENCE_OUTPUT_FLOOR, (
        f"output {result.output_size_bytes} < {REFERENCE_OUTPUT_FLOOR}"
    )
    assert zipfile.is_zipfile(out_path), "ferried output is not a valid .pptx"
    assert result.elapsed_seconds > 0
