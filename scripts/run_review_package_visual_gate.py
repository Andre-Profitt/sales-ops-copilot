#!/usr/bin/env python3
"""Render every packaged meeting-spine deck and write a visual QA report."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageStat

from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent


@dataclass
class DeckVisualResult:
    filename: str
    status: str
    slide_count: int
    pdf_path: str | None
    png_dir: str | None
    contact_sheet: str | None
    problems: list[str]
    attempt_count: int
    elapsed_seconds: float


def _require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"required binary not found on PATH: {name}")
    return path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)


def _render_pdf(pptx: Path, pdf_dir: Path) -> Path:
    pdf_dir.mkdir(parents=True, exist_ok=True)
    result = _run(
        [
            _require_binary("soffice"),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(pptx),
        ]
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "LibreOffice conversion failed")
    expected = pdf_dir / f"{pptx.stem}.pdf"
    if expected.exists():
        return expected
    matches = sorted(pdf_dir.glob("*.pdf"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise RuntimeError(f"LibreOffice did not produce PDF in {pdf_dir}")
    return matches[0]


def _render_pngs(pdf: Path, png_dir: Path) -> list[Path]:
    png_dir.mkdir(parents=True, exist_ok=True)
    result = _run([_require_binary("pdftoppm"), "-png", "-r", "120", str(pdf), str(png_dir / "slide")])
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "pdftoppm conversion failed")
    return sorted(png_dir.glob("slide-*.png"))


def _inspect_pngs(pngs: list[Path]) -> list[str]:
    problems: list[str] = []
    if len(pngs) != 16:
        problems.append(f"expected 16 rendered slides; found {len(pngs)}")
    for path in pngs:
        if path.stat().st_size < 20_000:
            problems.append(f"{path.name}: file too small")
            continue
        with Image.open(path) as image:
            width, height = image.size
            gray = image.convert("L")
            stat = ImageStat.Stat(gray)
        if width < 1000 or height < 700:
            problems.append(f"{path.name}: small canvas {width}x{height}")
        if stat.stddev[0] < 2.0:
            problems.append(f"{path.name}: near-blank render stddev={stat.stddev[0]:.2f}")
    return problems


def _contact_sheet(pngs: list[Path], output: Path) -> Path | None:
    selected_indexes = [1, 2, 3, 4, 5, 7, 14, 16]
    selected = [pngs[idx - 1] for idx in selected_indexes if idx <= len(pngs)]
    if not selected:
        return None
    thumb_w = 320
    thumb_h = 180
    label_h = 26
    margin = 12
    columns = 4
    rows = (len(selected) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * (thumb_w + margin) + margin, rows * (thumb_h + label_h + margin) + margin), "white")
    for i, path in enumerate(selected):
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((thumb_w, thumb_h))
            x = margin + (i % columns) * (thumb_w + margin)
            y = margin + (i // columns) * (thumb_h + label_h + margin)
            sheet.paste(thumb, (x, y + label_h))
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=88)
    return output


def _render_one(deck: Path, output_dir: Path) -> DeckVisualResult:
    started = time.time()
    deck_dir = output_dir / deck.stem
    attempts = 3
    problems: list[str] = []
    pngs: list[Path] = []
    pdf_path: Path | None = None
    png_dir: Path | None = None
    contact_path: Path | None = None
    attempt_count = 0
    for attempt in range(1, attempts + 1):
        attempt_count = attempt
        if deck_dir.exists():
            shutil.rmtree(deck_dir)
        problems = []
        pngs = []
        pdf_path = None
        png_dir = None
        contact_path = None
        try:
            pdf_path = _render_pdf(deck, deck_dir / "pdf")
            png_dir = deck_dir / "png"
            pngs = _render_pngs(pdf_path, png_dir)
            problems.extend(_inspect_pngs(pngs))
            contact_path = _contact_sheet(pngs, deck_dir / "contact_sheet.jpg")
        except Exception as exc:  # pragma: no cover - CLI defensive path
            problems.append(str(exc))
        if not problems:
            break
        if attempt < attempts:
            time.sleep(1.0)
    return DeckVisualResult(
        filename=deck.name,
        status="pass" if not problems else "fail",
        slide_count=len(pngs),
        pdf_path=str(pdf_path) if pdf_path else None,
        png_dir=str(png_dir) if png_dir else None,
        contact_sheet=str(contact_path) if contact_path else None,
        problems=problems,
        attempt_count=attempt_count,
        elapsed_seconds=round(time.time() - started, 2),
    )


def run_visual_gate(period: str, package_dir: Path, output_dir: Path, jobs: int) -> dict[str, object]:
    context = context_for_period(period)
    decks = sorted(path for path in package_dir.glob(context.meeting_spine_pattern) if not path.name.startswith("~$"))
    # LibreOffice headless conversion is not process-safe against the same user
    # profile. Keep this serial; the rest of the production line remains parallel.
    results = [_render_one(deck, output_dir) for deck in decks]
    status = "pass" if decks and all(result.status == "pass" for result in results) else "fail"
    return {
        "schema": "review-package-visual-gate/v1",
        "status": status,
        "period": context.period,
        "package_dir": str(package_dir),
        "output_dir": str(output_dir),
        "deck_count": len(decks),
        "results": [asdict(result) for result in results],
    }


def write_markdown(payload: dict[str, object], path: Path) -> None:
    lines = [
        "# Review Package Visual Gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Decks: `{payload['deck_count']}`",
        f"- Output: `{payload['output_dir']}`",
        "",
        "| Deck | Status | Slides | Attempts | Seconds | Contact Sheet | Problems |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for row in payload.get("results", []):
        result = dict(row)
        contact = result.get("contact_sheet") or ""
        problems = "; ".join(result.get("problems") or [])
        lines.append(
            "| {deck} | {status} | {slides} | {attempts} | {seconds} | {contact} | {problems} |".format(
                deck=result.get("filename"),
                status=result.get("status"),
                slides=result.get("slide_count"),
                attempts=result.get("attempt_count"),
                seconds=result.get("elapsed_seconds"),
                contact=contact,
                problems=problems,
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--package-dir", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()

    context = context_for_period(args.period)
    package_dir = (args.package_dir or context.review_package_dir).expanduser().resolve()
    output_dir = (
        args.output_dir
        or ROOT / "state" / context.period / "__regional__" / "visual_gate" / "review_package"
    ).expanduser().resolve()
    payload = run_visual_gate(context.period, package_dir, output_dir, args.jobs)
    json_output = args.json_output or output_dir / "review_package_visual_gate.json"
    markdown_output = args.markdown_output or output_dir / "review_package_visual_gate.md"
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(payload, markdown_output)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
