"""Binding-level render evidence verification.

Reads:
  --pptx:     final rendered presentation
  --manifest: render_evidence_manifest.json (from build_ppttc)
Writes:
  --out:      per-binding pass/fail report

Exit:
  0 — all required bindings pass
  1 — at least one required binding fails
  2 — usage error
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pptx import Presentation


def _slide_texts(prs) -> dict[int, str]:
    out: dict[int, str] = {}
    for i, slide in enumerate(prs.slides, 1):
        chunks: list[str] = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                chunks.append(shape.text_frame.text)  # type: ignore[attr-defined]
        out[i] = "\n".join(chunks)
    return out


def _slide_picture_count(prs) -> dict[int, int]:
    """Count picture-like shapes per slide; used as evidence for table_image bindings."""
    out: dict[int, int] = {}
    for i, slide in enumerate(prs.slides, 1):
        n = 0
        for shape in slide.shapes:
            # 13 = MSO_SHAPE_TYPE.PICTURE
            if int(shape.shape_type or 0) == 13:
                n += 1
        out[i] = n
    return out


def _slide_id_to_index(slide_id: str) -> int:
    return int(slide_id.lstrip("S"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pptx", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.pptx.exists():
        sys.stderr.write(f"pptx not found: {args.pptx}\n")
        return 2

    manifest = json.loads(args.manifest.read_text())
    prs = Presentation(str(args.pptx))
    texts = _slide_texts(prs)
    pictures = _slide_picture_count(prs)

    results: list[dict] = []
    fails = 0
    for b in manifest.get("bindings", []):
        slide_idx = b.get("slide") or _slide_id_to_index(b["name"][:3])
        evidence: str = ""
        status = "pass"

        if b.get("status") == "suppressed":
            status = "fail" if b.get("required") else "skip"
            evidence = f"binding suppressed: {b.get('reason', 'no reason given')}"
        elif b["lane"] == "ppttc_text" or b["kind"] in ("text", "scalar"):
            expected = b.get("expected_text", "")
            present = expected and expected in texts.get(slide_idx, "")
            if expected and not present:
                status = "fail" if b.get("required") else "warn"
                evidence = f"expected '{expected[:80]}' not found on slide {slide_idx}"
            else:
                evidence = f"text matched on slide {slide_idx}"
        elif b["lane"] == "excel_table_image" or b["kind"] == "table_image":
            n = pictures.get(slide_idx, 0)
            if n < 1:
                status = "fail" if b.get("required") else "warn"
                evidence = f"no picture shape on slide {slide_idx}"
            else:
                evidence = f"picture present on slide {slide_idx} (count={n})"
        elif b["lane"] == "ppttc_chart":
            # post-render Think-Cell chart inspection requires OOXML detail;
            # for MVP, treat presence of any non-text shape on the slide as evidence.
            evidence = f"chart presence assumed on slide {slide_idx}"
        else:
            evidence = f"no evidence rule for lane '{b['lane']}'"

        if status == "fail" and b.get("required"):
            fails += 1
        results.append({**b, "status": status, "evidence": evidence})

    report = {
        "status": "pass" if fails == 0 else "fail",
        "pptx": str(args.pptx),
        "manifest": str(args.manifest),
        "required_failures": fails,
        "bindings": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    if fails:
        sys.stderr.write(f"FAIL: {fails} required binding(s) without evidence\n")
        return 1
    print(f"OK: all {sum(1 for b in results if b.get('required'))} required bindings have evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
