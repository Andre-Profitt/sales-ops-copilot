#!/usr/bin/env python3
"""Render a PPTX to PDF and PNG slides for visual QA."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parent.parent


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"required binary not found on PATH: {name}")
    return path


def _convert_to_pdf(pptx: Path, pdf_dir: Path) -> Path:
    soffice = _require_binary("soffice")
    result = _run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(pptx),
        ]
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout or "LibreOffice PDF conversion failed")
    expected = pdf_dir / f"{pptx.stem}.pdf"
    if expected.exists():
        return expected
    matches = sorted(pdf_dir.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise SystemExit(f"LibreOffice did not produce a PDF in {pdf_dir}")
    return matches[0]


def _convert_to_png(pdf: Path, png_dir: Path) -> list[Path]:
    pdftoppm = _require_binary("pdftoppm")
    prefix = png_dir / "slide"
    result = _run([pdftoppm, "-png", "-r", "144", str(pdf), str(prefix)])
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout or "pdftoppm conversion failed")
    pngs = sorted(png_dir.glob("slide-*.png"))
    if not pngs:
        raise SystemExit(f"pdftoppm did not produce PNG slides in {png_dir}")
    too_small = [path for path in pngs if path.stat().st_size < 20_000]
    if too_small:
        names = ", ".join(path.name for path in too_small[:6])
        raise SystemExit(f"rendered slide image(s) look too small or blank: {names}")
    return pngs


def _inspect_pngs(pngs: list[Path]) -> None:
    problems: list[str] = []
    for path in pngs:
        with Image.open(path) as image:
            width, height = image.size
            gray = image.convert("L")
            stat = ImageStat.Stat(gray)
        if width < 1000 or height < 700:
            problems.append(f"{path.name}: small canvas {width}x{height}")
        if stat.stddev[0] < 2.0:
            problems.append(f"{path.name}: near-blank render stddev={stat.stddev[0]:.2f}")
    if problems:
        raise SystemExit("render visual smoke failed: " + "; ".join(problems[:8]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    pptx = args.pptx.expanduser().resolve()
    if not pptx.exists() or pptx.stat().st_size == 0:
        raise SystemExit(f"missing or empty deck: {pptx}")

    output_dir = args.output_dir.expanduser().resolve()
    pdf_dir = output_dir / "pdf"
    png_dir = output_dir / "png"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)

    pdf = _convert_to_pdf(pptx, pdf_dir)
    pngs = _convert_to_png(pdf, png_dir)
    _inspect_pngs(pngs)
    print(f"rendered_pdf={pdf}")
    print(f"rendered_png_dir={png_dir}")
    print(f"rendered_png_count={len(pngs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
