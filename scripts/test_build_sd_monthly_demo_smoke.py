"""Mac-runnable smoke tests for `build_sd_monthly_demo`.

Verifies:
    1. The demo module imports cleanly on non-Windows (no eager pywin32 path).
    2. argparse accepts the documented CLI surface (`--workbook`, `--template`,
       `--out-dir`, `--keep-open`).
    3. `main()` reports `WrongPlatformError` gracefully on Mac (rc=2, stderr
       message), with no traceback leaking past the catch.

We do NOT mock-out `ThinkCellClient.connect()` here — the whole point is to
exercise the real platform-guard path on the host running pytest.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

DEMO_PATH = Path(__file__).resolve().parent / "build_sd_monthly_demo.py"
DEMO_DIR = str(DEMO_PATH.parent)


@pytest.fixture(autouse=True)
def _ensure_scripts_on_path() -> None:
    if DEMO_DIR not in sys.path:
        sys.path.insert(0, DEMO_DIR)


def _load_demo():
    if "build_sd_monthly_demo" in sys.modules:
        return importlib.reload(sys.modules["build_sd_monthly_demo"])
    return importlib.import_module("build_sd_monthly_demo")


def test_demo_module_imports_clean() -> None:
    """Importing the demo must not require pywin32 on Mac/Linux."""
    demo = _load_demo()
    assert hasattr(demo, "main")
    assert hasattr(demo, "run")
    assert hasattr(demo, "DemoResult")


def test_argparse_accepts_documented_cli(tmp_path: Path) -> None:
    """All documented flags + the keep-open switch parse correctly."""
    demo = _load_demo()
    wb = tmp_path / "wb.xlsx"
    tpl = tmp_path / "tpl.pptx"
    out = tmp_path / "out"
    args = demo._parse_args(
        [
            "--workbook",
            str(wb),
            "--template",
            str(tpl),
            "--out-dir",
            str(out),
            "--keep-open",
        ]
    )
    assert args.workbook == wb
    assert args.template == tpl
    assert args.out_dir == out
    assert args.keep_open is True


def test_argparse_defaults_out_dir() -> None:
    """`--out-dir` defaults to ~/Desktop/tc_demo_output, expanded."""
    demo = _load_demo()
    args = demo._parse_args(["--workbook", "/tmp/x.xlsx", "--template", "/tmp/y.pptx"])
    assert args.out_dir == Path("~/Desktop/tc_demo_output").expanduser()
    assert args.keep_open is False


def test_argparse_requires_workbook_and_template() -> None:
    demo = _load_demo()
    with pytest.raises(SystemExit):
        demo._parse_args([])
    with pytest.raises(SystemExit):
        demo._parse_args(["--workbook", "/tmp/x.xlsx"])


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    demo = _load_demo()
    with pytest.raises(SystemExit) as exc_info:
        demo._parse_args(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    for flag in ("--workbook", "--template", "--out-dir", "--keep-open"):
        assert flag in captured.out


@pytest.mark.skipif(sys.platform == "win32", reason="WrongPlatformError path is non-Windows-only")
def test_main_reports_wrong_platform_gracefully(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """On Mac, main() must catch WrongPlatformError, return rc=2, no traceback."""
    wb = tmp_path / "wb.xlsx"
    tpl = tmp_path / "tpl.pptx"
    wb.write_bytes(b"fake-xlsx")
    tpl.write_bytes(b"fake-pptx")

    demo = _load_demo()
    rc = demo.main(
        [
            "--workbook",
            str(wb),
            "--template",
            str(tpl),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 2
    captured = capsys.readouterr()
    assert "platform unsupported" in captured.err
    assert sys.platform in captured.err  # the exception message echoes the platform


def test_main_reports_missing_inputs_gracefully(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Missing fixture files exit rc=3 with a clear stderr message (no traceback)."""
    demo = _load_demo()
    rc = demo.main(
        [
            "--workbook",
            str(tmp_path / "missing.xlsx"),
            "--template",
            str(tmp_path / "missing.pptx"),
            "--out-dir",
            str(tmp_path / "out"),
        ]
    )
    # On Mac WrongPlatformError fires first (rc=2 from connect()); on Windows
    # the FileNotFoundError fires (rc=3). Either is a clean graceful exit.
    assert rc in (2, 3)
    captured = capsys.readouterr()
    assert captured.err  # something was reported


def test_demo_result_dataclass_is_frozen() -> None:
    """DemoResult is the public structured-summary type — must stay immutable."""
    demo = _load_demo()
    r = demo.DemoResult(
        workbook=Path("/tmp/wb.xlsx"),
        template=Path("/tmp/tpl.pptx"),
        output=Path("/tmp/out.pptx"),
        charts_updated=12,
        elapsed_s=1.234,
    )
    with pytest.raises((AttributeError, Exception)):
        r.charts_updated = 999  # type: ignore[misc]
