#!/usr/bin/env python3
"""Audit QTR07 Stage × Industry Mekko promotion status across the 9 directors.

QTR07 is the only L5-proven native think-cell chart automation lane that
addresses an executive question the current meeting spine has no clean
answer for ('which stages concentrate in which industries?'). The L5 proof
exists at:

  state/thinkcell_bridge/build_scaffold/2026-Q2/work/
    QTR07_StageIndustry_Mekko/QTR07_StageIndustry_Mekko-2026-Q2-bound.pptx

That proof is bound for Jesper Tyrer (director_slug='Jesper-Tyrer'). To
promote QTR07 in production for all 9 directors:

  1. Generate per-director .ppttc binding (script: build_ppttc_name_manifests.py
     or equivalent — already wired in the seed pipeline).
  2. Run scripts/run_thinkcell_windows_bridge.py per director to call
     ppttc.exe on the Windows VM and produce a director-bound deck.
  3. Transplant the bound slide 16 (Stacked 100% bar / Mekko) into each
     director's 28-slide linked deck, replacing the current table-image.

This gate audits state, not action. It classifies each director's linked
deck slide 16 as:
- `native_chart_promoted`: native chart present, OLE binding live
- `table_image_fallback`: still rendering as static table-image picture
- `missing`: slide 16 doesn't exist
- `error`: deck not present

A director's status is `pass` only when slide 16 is `native_chart_promoted`.
The aggregate status is `pass` only when all 9 are promoted.

Today (2026-05-03) only Jesper has the proof; the linked decks ship slide
16 as table-image. The gate reports this honestly so the team knows what's
left before claiming the template is fully native think-cell.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from zipfile import ZipFile

from pptx import Presentation

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent
QTR07_TARGET_NAME = "QTR07_StageIndustry_Mekko"
QTR07_SOURCE_NAME = "S16_StageByIndustry"
SLIDE_INDEX = 16


@dataclass
class DirectorPromotionStatus:
    director: str
    director_slug: str
    deck_path: str
    deck_exists: bool
    classification: str
    detail: dict = field(default_factory=dict)


def _slug(name: str) -> str:
    return name.replace(" ", "-")


def _linked_deck_path(period: str, slug: str) -> Path:
    return ROOT / "state" / period / slug / f"{slug}-LAND-{period}-table-image-linked.pptx"


def _classify_slide_16(path: Path) -> tuple[str, dict]:
    if not path.exists():
        return "error", {"reason": "deck not present"}
    try:
        prs = Presentation(str(path))
    except Exception as exc:
        return "error", {"reason": f"unreadable: {exc}"}
    if len(prs.slides) < SLIDE_INDEX:
        return "missing", {"slide_count": len(prs.slides)}
    slide = prs.slides[SLIDE_INDEX - 1]
    n_charts = 0
    n_pictures = 0
    n_ole = 0
    n_tables = 0
    for shape in slide.shapes:
        if getattr(shape, "has_chart", False):
            n_charts += 1
        elif "OLE" in str(getattr(shape, "shape_type", "")):
            n_ole += 1
        elif getattr(shape, "name", "") == "Pic" or "Picture" in str(
            getattr(shape, "shape_type", "")
        ):
            n_pictures += 1
        elif getattr(shape, "has_table", False):
            n_tables += 1
    has_target_name = False
    has_source_name = False
    with ZipFile(path) as zf:
        try:
            slide_xml = zf.read(f"ppt/slides/slide{SLIDE_INDEX}.xml").decode(
                "utf-8", errors="ignore"
            )
            has_target_name = QTR07_TARGET_NAME in slide_xml
            has_source_name = QTR07_SOURCE_NAME in slide_xml
        except KeyError:
            pass
    detail = {
        "n_charts": n_charts,
        "n_pictures": n_pictures,
        "n_ole_objects": n_ole,
        "n_tables": n_tables,
        "has_target_name": has_target_name,
        "has_source_name_seed": has_source_name,
    }
    if n_charts >= 1 and (has_target_name or has_source_name):
        return "native_chart_promoted", detail
    if n_pictures >= 1:
        return "table_image_fallback", detail
    if n_tables >= 1:
        return "native_table_other", detail
    return "missing", detail


def audit_director(period: str, name: str) -> DirectorPromotionStatus:
    slug = _slug(name)
    path = _linked_deck_path(period, slug)
    classification, detail = _classify_slide_16(path)
    return DirectorPromotionStatus(
        director=name,
        director_slug=slug,
        deck_path=str(path),
        deck_exists=path.exists(),
        classification=classification,
        detail=detail,
    )


def run_audit(period: str) -> dict:
    context = context_for_period(period)
    statuses = [audit_director(context.period, d["name"]) for d in canonical_directors()]
    promoted = [s for s in statuses if s.classification == "native_chart_promoted"]
    fallback = [s for s in statuses if s.classification == "table_image_fallback"]
    missing = [s for s in statuses if s.classification in ("missing", "error")]

    # Accept: all 9 promoted -> pass.
    # Warn: at least 1 promoted but not all (in-progress rollout).
    # Fail: zero promoted AND zero fallback (means decks are missing) — warn otherwise.
    if len(promoted) == len(statuses):
        status = "pass"
    elif promoted:
        status = "warn"
    elif missing:
        status = "fail"
    else:
        status = "warn"
    return {
        "schema": "qtr07-mekko-promotion-gate/v1",
        "status": status,
        "period": context.period,
        "target_chart": QTR07_TARGET_NAME,
        "source_seed_name": QTR07_SOURCE_NAME,
        "slide_index": SLIDE_INDEX,
        "summary": {
            "directors_total": len(statuses),
            "promoted": len(promoted),
            "table_image_fallback": len(fallback),
            "missing_or_error": len(missing),
        },
        "promotion_path": [
            "Generate per-director .ppttc payload binding stage-by-industry rows from the director's Salesforce slice.",
            "Run scripts/run_thinkcell_windows_bridge.py to bind the .ppttc against LAND_thinkcell_seed_charts.pptx via ppttc.exe on the Windows VM.",
            "Transplant the bound slide 16 (Stacked 100% bar / Mekko) into the director's 28-slide linked deck, replacing the table-image picture.",
            "Re-run the meeting-spine build so the spine derivative inherits the native chart.",
            "Re-run gates: meeting_spine_audit_gate accepts native_chart as alternative for slide 6.",
        ],
        "results": [_to_dict(s) for s in statuses],
    }


def _to_dict(s: DirectorPromotionStatus) -> dict:
    return asdict(s)


def write_markdown(payload: dict, path: Path) -> None:
    s = payload["summary"]
    lines = [
        "# QTR07 Stage × Industry Mekko Promotion Gate",
        "",
        f"- Status: `{payload['status']}`",
        f"- Period: `{payload['period']}`",
        f"- Promoted: {s['promoted']} / {s['directors_total']}",
        f"- Table-image fallback: {s['table_image_fallback']}",
        f"- Missing or error: {s['missing_or_error']}",
        "",
        "| Director | Slug | Slide 16 classification | Detail |",
        "|---|---|---|---|",
    ]
    for r in payload["results"]:
        d = r.get("detail") or {}
        detail = (
            f"charts={d.get('n_charts', '?')} pic={d.get('n_pictures', '?')} "
            f"ole={d.get('n_ole_objects', '?')} tbl={d.get('n_tables', '?')}"
        )
        lines.append(
            f"| {r['director']} | {r['director_slug']} | {r['classification']} | {detail} |"
        )
    lines.append("")
    lines.append("## Promotion path (when ready)")
    lines.append("")
    for step in payload["promotion_path"]:
        lines.append(f"- {step}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()

    payload = run_audit(args.period)
    output_dir = ROOT / "state" / args.period / "__regional__" / "qtr07_mekko_promotion"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output = args.json_output or output_dir / "qtr07_mekko_promotion_status.json"
    markdown_output = args.markdown_output or output_dir / "qtr07_mekko_promotion_status.md"
    json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(payload, markdown_output)
    print(json.dumps(payload, indent=2))
    # `warn` status is non-fatal so the production line keeps moving.
    return 2 if payload["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
