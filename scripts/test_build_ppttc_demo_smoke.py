"""Mac-runnable smoke tests for `build_ppttc_demo` (tcrender-backed).

Verifies:
    1. The demo module imports cleanly on every platform (no eager
       win32com / pywin32 path; render runs over SSH via tcrender).
    2. argparse accepts the documented CLI surface (--ppttc,
       --template-override, --out, --keep-stage-files, --ssh-host, --timeout).
    3. --help exits 0.
    4. The real fixture .ppttc parses as JSON with >= 30 named bindings.
       (Jesper-Tyrer-LAND-2026-Q2.ppttc has exactly 42.)
    5. The demo's structural validator accepts the real fixture and rejects
       documented bad shapes (object, empty list, missing keys).
    6. Missing ppttc input surfaces rc=3 with a clear message.
    7. The DemoResult dataclass is frozen (public contract).

Live render (Mac -> Windows-VM ppttc.exe) is gated behind TCRENDER_LIVE=1
and verified by libs/tcrender/tests/test_smoke.py rather than here.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

DEMO_PATH = Path(__file__).resolve().parent / "build_ppttc_demo.py"
DEMO_DIR = str(DEMO_PATH.parent)
REPO_ROOT = DEMO_PATH.parent.parent
FIXTURE_PPTTC = REPO_ROOT / "_windows_test" / "Jesper-Tyrer-LAND-2026-Q2.ppttc"


@pytest.fixture(autouse=True)
def _ensure_scripts_on_path() -> None:
    if DEMO_DIR not in sys.path:
        sys.path.insert(0, DEMO_DIR)


def _load_demo():
    if "build_ppttc_demo" in sys.modules:
        return importlib.reload(sys.modules["build_ppttc_demo"])
    return importlib.import_module("build_ppttc_demo")


def test_demo_module_imports_clean() -> None:
    """Importing the demo must not require pywin32/win32com on Mac/Linux."""
    demo = _load_demo()
    assert hasattr(demo, "main")
    assert hasattr(demo, "run")
    assert hasattr(demo, "DemoResult")


def test_argparse_accepts_documented_cli(tmp_path: Path) -> None:
    demo = _load_demo()
    ppttc = tmp_path / "x.ppttc"
    override = tmp_path / "tpl.pptx"
    out = tmp_path / "out.pptx"
    args = demo._parse_args(
        [
            "--ppttc",
            str(ppttc),
            "--template-override",
            str(override),
            "--out",
            str(out),
            "--keep-stage-files",
            "--ssh-host",
            "Other-VM",
            "--timeout",
            "120",
        ]
    )
    assert args.ppttc == ppttc
    assert args.template_override == override
    assert args.out == out
    assert args.keep_stage_files is True
    assert args.ssh_host == "Other-VM"
    assert args.timeout == 120


def test_argparse_defaults() -> None:
    demo = _load_demo()
    args = demo._parse_args(["--ppttc", "/tmp/x.ppttc"])
    assert args.template_override is None
    assert args.out is None
    assert args.keep_stage_files is False
    assert args.ssh_host == "Windows-VM"
    assert args.timeout == 240.0


def test_argparse_requires_ppttc() -> None:
    demo = _load_demo()
    with pytest.raises(SystemExit):
        demo._parse_args([])


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    demo = _load_demo()
    with pytest.raises(SystemExit) as exc_info:
        demo._parse_args(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    for flag in (
        "--ppttc",
        "--template-override",
        "--out",
        "--keep-stage-files",
        "--ssh-host",
        "--timeout",
    ):
        assert flag in captured.out


def test_real_fixture_ppttc_parses_with_enough_bindings() -> None:
    """The canonical Jesper-Tyrer fixture must parse and carry real binding count."""
    assert FIXTURE_PPTTC.exists(), f"fixture missing: {FIXTURE_PPTTC}"
    parsed = json.loads(FIXTURE_PPTTC.read_text(encoding="utf-8"))
    assert isinstance(parsed, list) and parsed
    entry = parsed[0]
    assert "template" in entry
    assert "data" in entry
    bindings = entry["data"]
    named = [b for b in bindings if isinstance(b, dict) and "name" in b]
    total_rows = sum(len(b.get("table", [])) for b in named)
    assert len(named) >= 30, f"expected >= 30 named bindings, got {len(named)}"
    assert total_rows >= 50, f"expected >= 50 total table rows, got {total_rows}"


def test_load_and_validate_uses_real_fixture() -> None:
    """The script's own validator must accept the real .ppttc unmodified."""
    demo = _load_demo()
    parsed, count = demo._load_and_validate_ppttc(FIXTURE_PPTTC)
    assert isinstance(parsed, list) and parsed
    assert count == len(parsed[0]["data"])


def test_load_and_validate_rejects_bad_shapes(tmp_path: Path) -> None:
    demo = _load_demo()
    bad = tmp_path / "bad.ppttc"
    bad.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        demo._load_and_validate_ppttc(bad)
    bad.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        demo._load_and_validate_ppttc(bad)
    bad.write_text('[{"template": "x"}]', encoding="utf-8")
    with pytest.raises(ValueError):
        demo._load_and_validate_ppttc(bad)


def test_main_reports_missing_ppttc_gracefully(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    demo = _load_demo()
    rc = demo.main(["--ppttc", str(tmp_path / "nope.ppttc")])
    assert rc == 3
    captured = capsys.readouterr()
    assert "input missing" in captured.err


def test_demo_result_dataclass_is_frozen(tmp_path: Path) -> None:
    """DemoResult is the public structured-summary type; must stay immutable."""
    demo = _load_demo()
    r = demo.DemoResult(
        input_ppttc=tmp_path / "x.ppttc",
        template_path_used=tmp_path / "tpl.pptx",
        output_pptx=tmp_path / "out.pptx",
        output_size_bytes=1234,
        bindings_count=42,
        elapsed_seconds=1.234,
        exit_code=0,
    )
    with pytest.raises((AttributeError, Exception)):
        r.bindings_count = 999  # type: ignore[misc]


def test_pywin32_path_is_not_eagerly_imported() -> None:
    """Importing the demo on Mac must not pull in win32com.client."""
    _ = _load_demo()
    if sys.platform != "win32":
        assert "win32com.client" not in sys.modules


def test_demo_uses_tcrender_for_render() -> None:
    """The demo must import tcrender (the new render path), not tc_com_driver."""
    demo = _load_demo()
    # tcrender symbols must be importable from the demo module
    assert hasattr(demo, "TcRenderClient")
    assert hasattr(demo, "SSHTransport")
    assert hasattr(demo, "RenderError")
