"""Per-slide SSIM visual-regression check for two PPTX files.

Usage:
  --baseline:  golden pptx (e.g., last-known-good Patrick canary)
  --candidate: new pptx (e.g., today's render)
  --out:       JSON report with per-slide SSIM + an overall pass/fail
  --threshold: minimum SSIM per slide (default 0.92)
  --soffice:   path to LibreOffice soffice binary (default: /opt/homebrew/bin/soffice)

Renders both PPTX files to per-slide PNG via LibreOffice headless, then
computes structural-similarity per matching slide pair via skimage.

Exit codes:
  0 — all slides pass threshold
  1 — at least one slide below threshold
  2 — usage / dependency error
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim


def _render_pptx_to_pngs(pptx: Path, out_dir: Path, soffice: Path) -> list[Path]:
    """LibreOffice doesn't emit per-slide PNG directly; go via PDF then render PDF pages.

    Falls back to soffice's --convert-to png if PDF render isn't available.
    Returns sorted list of slide PNG paths.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    # Step 1: pptx -> pdf (LibreOffice handles this cleanly)
    proc = subprocess.run(
        [str(soffice), "--headless", "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"soffice pdf conversion failed: {proc.stderr}")
    pdf = out_dir / (pptx.stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError(f"expected {pdf} after conversion, got: {list(out_dir.iterdir())}")

    # Step 2: pdf -> per-page png via pdftoppm (preferred) or pdf2image fallback
    if shutil.which("pdftoppm"):
        subprocess.run(
            ["pdftoppm", "-png", "-r", "150", str(pdf), str(out_dir / "slide")],
            check=True,
            capture_output=True,
            text=True,
        )
        pngs = sorted(out_dir.glob("slide-*.png"))
    else:
        try:
            from pdf2image import convert_from_path  # type: ignore
        except ImportError as exc:
            raise RuntimeError("need pdftoppm in PATH or pdf2image installed") from exc
        images = convert_from_path(str(pdf), dpi=150)
        pngs = []
        for i, img in enumerate(images, 1):
            p = out_dir / f"slide-{i:03d}.png"
            img.save(p)
            pngs.append(p)
    if not pngs:
        raise RuntimeError(f"no pngs produced from {pdf}")
    return pngs


def _ssim_score(a: Path, b: Path) -> float:
    """SSIM in [-1, 1] (1 = identical). Resize candidate to baseline shape if mismatched."""
    img_a = np.array(Image.open(a).convert("L"))
    img_b = np.array(Image.open(b).convert("L"))
    if img_a.shape != img_b.shape:
        img_b_resized = Image.open(b).convert("L").resize((img_a.shape[1], img_a.shape[0]))
        img_b = np.array(img_b_resized)
    score = ssim(img_a, img_b, data_range=255)
    # skimage.ssim returns a float when gradient=False, full=False (defaults);
    # pyright collapses the overload union. Coerce explicitly.
    return float(score)  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--threshold", type=float, default=0.92)
    parser.add_argument("--soffice", type=Path, default=Path("/opt/homebrew/bin/soffice"))
    parser.add_argument(
        "--keep-renders",
        action="store_true",
        help="Keep per-slide PNG renders (default: delete after scoring)",
    )
    args = parser.parse_args(argv)

    if not args.baseline.exists() or not args.candidate.exists():
        sys.stderr.write(f"missing input pptx: {args.baseline} or {args.candidate}\n")
        return 2
    if not args.soffice.exists():
        sys.stderr.write(f"soffice not found at {args.soffice}\n")
        return 2

    work = Path(tempfile.mkdtemp(prefix="ssim_"))
    try:
        baseline_pngs = _render_pptx_to_pngs(args.baseline, work / "baseline", args.soffice)
        candidate_pngs = _render_pptx_to_pngs(args.candidate, work / "candidate", args.soffice)
    except Exception as exc:
        sys.stderr.write(f"render failed: {exc}\n")
        return 2

    n = min(len(baseline_pngs), len(candidate_pngs))
    results: list[dict] = []
    fails = 0
    for i in range(n):
        score = _ssim_score(baseline_pngs[i], candidate_pngs[i])
        passed = score >= args.threshold
        if not passed:
            fails += 1
        results.append(
            {
                "slide_idx": i + 1,
                "ssim": round(score, 4),
                "threshold": args.threshold,
                "status": "pass" if passed else "fail",
            }
        )

    slide_count_match = len(baseline_pngs) == len(candidate_pngs)
    report = {
        "status": "pass" if fails == 0 and slide_count_match else "fail",
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "baseline_slides": len(baseline_pngs),
        "candidate_slides": len(candidate_pngs),
        "slide_count_match": slide_count_match,
        "threshold": args.threshold,
        "below_threshold": fails,
        "slides": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    if not args.keep_renders:
        shutil.rmtree(work, ignore_errors=True)

    if report["status"] == "pass":
        print(f"OK: {n} slides pass SSIM >= {args.threshold}")
        return 0
    print(
        f"FAIL: {fails} slide(s) below SSIM {args.threshold}; report -> {args.out}", file=sys.stderr
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
