#!/usr/bin/env python3
"""Gate-4: visual review of a .pptx via Claude vision.

Renders each slide to PNG (LibreOffice headless -> PDF -> pdftoppm) and asks
Claude to review each one against a brand brief, returning structured findings
(unpolished text color, overlapping shapes, leaked placeholder copy, broken
chart axes, etc.) that structural OOXML validators cannot see.

Why this exists:
  Gates 1-3 catch structural problems (placeholder leak, off-canvas, schema
  violations). They do not catch rendered-output drift: a slide that's
  XML-valid can still look unpolished. Vision review closes that loop.

Pre-conditions:
  - LibreOffice CLI (`soffice`) on PATH
  - Poppler (`pdftoppm`) on PATH
  - `claude` CLI authenticated (uses the user's existing subscription;
    no API key needed)

Usage:
    python3 scripts/visual_review_pptx.py assets/LAND_thinkcell_seed.pptx
    python3 scripts/visual_review_pptx.py path.pptx --slides 1,8,13
    python3 scripts/visual_review_pptx.py path.pptx --report state/canary/visual.md
    python3 scripts/visual_review_pptx.py path.pptx --json
    python3 scripts/visual_review_pptx.py path.pptx --keep-pngs  # don't clean tmp dir

Exit codes:
    0  no fail-level findings
    1  one or more slides flagged FAIL
    2  warn-level findings only
    3  render or invocation failure
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

DEFAULT_DPI = 150

BRAND_BRIEF = """You are reviewing a single slide from a SimCorp sales-ops review deck.
Brand: SimCorp navy #083EA7, brand near-black #1A1D31, coral #EF3E4A,
       orange #FB9B2A, gold #F0CF61. Microsoft Sans Serif / Arial.
Audience: senior sales directors. Tone: McKinsey/Bain consulting-grade.

Review this rendered slide for any of:
  - Unreadable text (low contrast: dark text on dark fill, or light on light)
  - Placeholder/template leak ("Click to add title", "Lorem ipsum", "<S01_...>")
  - Overlapping shapes or text outside the slide canvas
  - Inconsistent type hierarchy (mixed font families, sizes mid-paragraph)
  - Charts with missing/wrong axis labels, broken legends, or no data shown
  - Off-brand colors (text/fill that does not align with the SimCorp palette)
  - Empty placeholders that should be filled
  - Broken footers / page numbers / brand bars

Return ONLY a JSON object on a single line, no prose, no fences. Schema:
  {"slide": <int>, "ok": <bool>, "findings": [
      {"severity": "fail"|"warn"|"info",
       "category": "contrast"|"leak"|"layout"|"typography"|"chart"|"brand"|"other",
       "message": "<one sentence>"} ]}

ok=true means zero fail or warn findings. info-level findings still allow ok=true."""


@dataclass
class SlideFinding:
    severity: str
    category: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SlideReport:
    slide: int
    ok: bool
    findings: list[SlideFinding] = field(default_factory=list)
    render_seconds: float = 0.0
    review_seconds: float = 0.0
    raw_response: str = ""
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "slide": self.slide,
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "render_seconds": round(self.render_seconds, 3),
            "review_seconds": round(self.review_seconds, 3),
            "error": self.error,
        }


@dataclass
class VisualReviewReport:
    pptx: str
    slide_count: int
    slides: list[SlideReport] = field(default_factory=list)

    @property
    def fails(self) -> list[SlideFinding]:
        return [f for s in self.slides for f in s.findings if f.severity == "fail"]

    @property
    def warns(self) -> list[SlideFinding]:
        return [f for s in self.slides for f in s.findings if f.severity == "warn"]

    def to_dict(self) -> dict:
        return {
            "pptx": self.pptx,
            "slide_count": self.slide_count,
            "fail_count": len(self.fails),
            "warn_count": len(self.warns),
            "slides": [s.to_dict() for s in self.slides],
        }


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False, **kw)


def render_slides_to_png(pptx: Path, work_dir: Path, dpi: int = DEFAULT_DPI) -> list[Path]:
    """LibreOffice headless: pptx -> pdf, then pdftoppm: pdf -> per-slide PNGs."""
    work_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir = work_dir / "pdf"
    pdf_dir.mkdir(exist_ok=True)
    r = _run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(pdf_dir),
            str(pptx),
        ]
    )
    if r.returncode != 0:
        raise RuntimeError(f"soffice convert failed: {r.stderr.strip() or r.stdout.strip()}")
    pdf_path = pdf_dir / (pptx.stem + ".pdf")
    if not pdf_path.exists():
        # LibreOffice sometimes drops the file under a slightly different name
        candidates = list(pdf_dir.glob("*.pdf"))
        if not candidates:
            raise RuntimeError(f"soffice produced no PDF in {pdf_dir}")
        pdf_path = candidates[0]
    png_prefix = work_dir / "slide"
    r = _run(["pdftoppm", "-r", str(dpi), "-png", str(pdf_path), str(png_prefix)])
    if r.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {r.stderr.strip()}")
    return sorted(work_dir.glob("slide-*.png"))


_ANSI_RE = re.compile(r"\x1b\][^\x07]*\x07|\x1b\[[0-9;]*[A-Za-z]")


def _extract_json(text: str) -> dict | None:
    """Find the outermost balanced {...} block — tolerant of nested braces."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def _parse_review_response(raw: str, slide_num: int) -> SlideReport:
    """Parse one Claude response, tolerating markdown fences, ANSI escapes, prose."""
    sr = SlideReport(slide=slide_num, ok=True, raw_response=raw)
    cleaned = _ANSI_RE.sub("", raw).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-z]*\n", "", cleaned)
        cleaned = re.sub(r"\n```\s*$", "", cleaned)
    obj = None
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        obj = _extract_json(cleaned)
    if obj is None:
        sr.error = f"could not parse JSON; raw[:200]={cleaned[:200]!r}"
        sr.ok = False
        return sr
    sr.ok = bool(obj.get("ok", True))
    for f in obj.get("findings") or []:
        sr.findings.append(
            SlideFinding(
                severity=f.get("severity", "info"),
                category=f.get("category", "other"),
                message=str(f.get("message", "")),
            )
        )
    return sr


def review_one_slide(png: Path, slide_num: int, brief: str) -> SlideReport:
    """Single Claude vision call. Uses `claude -p` with @-reference."""
    t0 = time.monotonic()
    prompt = f"{brief}\n\nThe slide image is at: @{png}\n\nReturn ONLY the JSON object for slide {slide_num}."
    r = _run(["claude", "-p", prompt], timeout=120)
    dur = time.monotonic() - t0
    if r.returncode != 0:
        sr = SlideReport(
            slide=slide_num,
            ok=False,
            raw_response=r.stdout,
            error=f"claude exit {r.returncode}: {r.stderr[:200]}",
            review_seconds=dur,
        )
        return sr
    sr = _parse_review_response(r.stdout, slide_num)
    sr.review_seconds = dur
    return sr


def render_markdown(rep: VisualReviewReport) -> str:
    lines = [
        f"# visual review: {rep.pptx}",
        "",
        f"- slides: {rep.slide_count}",
        f"- result: **{'CLEAN' if rep.fails == [] and rep.warns == [] else 'PROBLEMS'}**",
        f"- fails: {len(rep.fails)}   warns: {len(rep.warns)}",
        "",
    ]
    for s in rep.slides:
        flag = "✓" if s.ok else "✗"
        lines.append(f"## {flag} slide {s.slide}  ({s.review_seconds:.1f}s)")
        if s.error:
            lines.append(f"  - error: `{s.error}`")
            lines.append("")
            continue
        if not s.findings:
            lines.append("  - clean")
        for f in s.findings:
            sev = {"fail": "**FAIL**", "warn": "warn", "info": "info"}.get(f.severity, f.severity)
            lines.append(f"  - [{sev}] *{f.category}* — {f.message}")
        lines.append("")
    return "\n".join(lines)


def _parse_slide_filter(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(1, total + 1))
    out: set[int] = set()
    for piece in spec.split(","):
        piece = piece.strip()
        if "-" in piece:
            a, b = piece.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif piece:
            out.add(int(piece))
    return sorted(n for n in out if 1 <= n <= total)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("pptx", type=Path)
    p.add_argument("--slides", help="comma-separated slide nums, e.g. '1,8,13' or '1-5,10'")
    p.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    p.add_argument("--report", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--keep-pngs", action="store_true", help="do not delete the tmp PNG dir")
    p.add_argument(
        "--brief-file",
        type=Path,
        default=None,
        help="path to a brand-brief override (default: built-in SimCorp brief)",
    )
    args = p.parse_args(argv)

    if not args.pptx.exists():
        sys.stderr.write(f"pptx not found: {args.pptx}\n")
        return 3
    if not shutil.which("soffice"):
        sys.stderr.write("soffice not on PATH (install LibreOffice)\n")
        return 3
    if not shutil.which("pdftoppm"):
        sys.stderr.write("pdftoppm not on PATH (install poppler)\n")
        return 3
    if not shutil.which("claude"):
        sys.stderr.write("claude CLI not on PATH\n")
        return 3

    brief = BRAND_BRIEF
    if args.brief_file:
        brief = args.brief_file.read_text(encoding="utf-8")

    # Render PNGs under the repo root so `claude -p`'s Read tool can access
    # them. `claude -p` refuses files outside cwd by default.
    repo_tmp = Path("state") / "visual_review_tmp"
    repo_tmp.mkdir(parents=True, exist_ok=True)
    work_dir = Path(tempfile.mkdtemp(prefix="run_", dir=repo_tmp))
    try:
        pngs = render_slides_to_png(args.pptx, work_dir, dpi=args.dpi)
        slide_nums = _parse_slide_filter(args.slides, len(pngs))
        report = VisualReviewReport(pptx=str(args.pptx), slide_count=len(pngs))

        for n in slide_nums:
            png = pngs[n - 1]
            sr = review_one_slide(png, n, brief)
            report.slides.append(sr)
            print(
                f"slide {n}: {'OK' if sr.ok else 'PROBLEMS'}  fails={sum(1 for f in sr.findings if f.severity == 'fail')}  warns={sum(1 for f in sr.findings if f.severity == 'warn')}",
                file=sys.stderr,
            )

        md = render_markdown(report)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(md, encoding="utf-8")
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(md)

        if report.fails:
            return 1
        if report.warns:
            return 2
        return 0
    finally:
        if not args.keep_pngs:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"\n[--keep-pngs] PNGs in: {work_dir}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
