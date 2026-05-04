#!/usr/bin/env python3
"""Per-slide placeholder inventory — surface leakage and orphans.

Companion to validate_pptx_strict.py / diff_oxml.py / inventory_pptx_layouts.py.
Lists every <p:sp> on every slide that carries a <p:ph>, classifies its state
(filled / empty / prompt-leak / lorem-ipsum / tcfield-only / mixed), and
cross-checks against the slide's layout placeholders to surface:
  - orphan slide shapes (no matching layout placeholder)
  - unfilled layout placeholders (slide doesn't realize a declared placeholder)

Usage:
    python3 scripts/inventory_pptx_placeholders.py path/to/seed.pptx
    python3 scripts/inventory_pptx_placeholders.py --json path/to/*.pptx
    python3 scripts/inventory_pptx_placeholders.py --quiet path/to/seed.pptx

Exit codes:
    0   no leak states (lorem-ipsum / prompt-leak) and no orphans/unfilled
    1   leak states present
    2   structural gaps only (orphan or unfilled, no leaks)
    3   could not open
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(3)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_pptx_strict import PLACEHOLDER_PHRASES  # noqa: E402

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": NS_P, "a": NS_A, "r": NS_R, "pkg": NS_PKG}

LOREM_MARKERS = ("lorem ipsum", "consectetur adipiscing")

STATES = (
    "filled",
    "empty",
    "prompt-leak",
    "lorem-ipsum",
    "tcfield-only",
    "mixed",
)


@dataclass
class PlaceholderRow:
    slide_num: int
    shape_name: str
    idx: str
    type: str
    layout_match: str  # "matched" | "orphan"
    layout_ph_name: str
    state: str
    text_preview: str
    tcfield_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GapRow:
    kind: str  # "unfilled" | "orphan" | "layout-unused"
    location: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LeakShape:
    slide_num: int
    shape_name: str
    state: str  # "lorem-ipsum" | "prompt-leak"
    text_preview: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    path: str
    slide_count: int = 0
    rows: list[PlaceholderRow] = field(default_factory=list)
    gaps: list[GapRow] = field(default_factory=list)
    leak_shapes: list[LeakShape] = field(default_factory=list)
    slide_layouts: dict[int, tuple[str, str]] = field(default_factory=dict)

    def state_counts(self) -> Counter[str]:
        c: Counter[str] = Counter()
        for r in self.rows:
            c[r.state] += 1
        for ls in self.leak_shapes:
            c[ls.state] += 1
        return c

    def gap_counts(self) -> Counter[str]:
        c: Counter[str] = Counter()
        for g in self.gaps:
            c[g.kind] += 1
        return c

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "slide_count": self.slide_count,
            "state_counts": dict(self.state_counts()),
            "gap_counts": dict(self.gap_counts()),
            "rows": [r.to_dict() for r in self.rows],
            "gaps": [g.to_dict() for g in self.gaps],
            "leak_shapes": [ls.to_dict() for ls in self.leak_shapes],
            "slide_layouts": {str(k): list(v) for k, v in self.slide_layouts.items()},
        }


def _ph_key(idx: str | None, ph_type: str | None) -> tuple[str, str]:
    """ECMA-376 §19.3.1.36 default: idx=0 type=title when neither attribute is present."""
    if idx is None and ph_type is None:
        return ("0", "title")
    return (idx or "0", ph_type or "body")


def _slide_num_from_part(part_name: str) -> int:
    stem = part_name.rsplit("/", 1)[-1].removeprefix("slide").removesuffix(".xml")
    return int(stem)


def _layout_part_for_slide(zf: zipfile.ZipFile, slide_part: str) -> str | None:
    rels_name = slide_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    try:
        rels_root = etree.fromstring(zf.read(rels_name))
    except (KeyError, etree.XMLSyntaxError):
        return None
    for rel in rels_root.findall("pkg:Relationship", NS):
        rtype = rel.get("Type", "")
        if rtype.endswith("/slideLayout"):
            target = rel.get("Target", "")
            if target.startswith("../"):
                target = "ppt/" + target[3:]
            return target
    return None


def _layout_metadata(
    zf: zipfile.ZipFile, layout_part: str
) -> tuple[str, dict[tuple[str, str], str]]:
    """Return (layout display name, {ph_key: shape name})."""
    try:
        root = etree.fromstring(zf.read(layout_part))
    except (KeyError, etree.XMLSyntaxError):
        return ("?", {})
    csld = root.find("p:cSld", NS)
    layout_name = (csld.get("name") if csld is not None else None) or layout_part.rsplit("/", 1)[-1]
    placeholders: dict[tuple[str, str], str] = {}
    for sp in root.findall(".//p:sp", NS):
        ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            continue
        cnv = sp.find("p:nvSpPr/p:cNvPr", NS)
        sp_name = (cnv.get("name") if cnv is not None else None) or "?"
        placeholders[_ph_key(ph.get("idx"), ph.get("type"))] = sp_name
    return (layout_name, placeholders)


def _shape_text(sp: etree._Element) -> tuple[str, list[str], bool]:
    """Return (joined text, fld ids, has_txBody).

    On slide-level <p:sp> the text body is <p:txBody>; on layouts/masters it is
    <a:txBody>. Accept either. Field <a:t> children are skipped from the joined
    literal text so 'fld with text' shapes classify as tcfield-only by default
    and 'mixed' only when a sibling <a:t> outside the fld carries content.
    """
    body = sp.find("p:txBody", NS)
    if body is None:
        body = sp.find("a:txBody", NS)
    has_tx = body is not None
    parts: list[str] = []
    fld_ids: list[str] = []
    if body is None:
        return ("", fld_ids, has_tx)
    in_fld = 0
    for ev, el in etree.iterwalk(body, events=("start", "end")):
        tag = etree.QName(el).localname
        if tag == "fld":
            if ev == "start":
                fid = el.get("id") or ""
                if fid:
                    fld_ids.append(fid)
                in_fld += 1
            else:
                in_fld -= 1
            continue
        if ev == "start" and tag == "t" and el.text and in_fld == 0:
            parts.append(el.text)
    return ("".join(parts), fld_ids, has_tx)


def _classify(text: str, fld_ids: list[str], has_tx: bool) -> str:
    lit = text.strip()
    has_lit = bool(lit)
    has_fld = bool(fld_ids)
    if not has_tx and not has_fld:
        return "empty"
    low = lit.lower()
    if any(m in low for m in LOREM_MARKERS):
        return "lorem-ipsum"
    for phrase in PLACEHOLDER_PHRASES:
        if phrase in LOREM_MARKERS:
            continue
        if phrase in low:
            return "prompt-leak"
    if has_fld and not has_lit:
        return "tcfield-only"
    if has_fld and has_lit:
        return "mixed"
    if has_lit:
        return "filled"
    return "empty"


def _scan_slide(
    zf: zipfile.ZipFile,
    slide_part: str,
    rep: Report,
    layout_index: dict[str, tuple[str, dict[tuple[str, str], str]]],
) -> None:
    slide_num = _slide_num_from_part(slide_part)
    try:
        root = etree.fromstring(zf.read(slide_part))
    except (KeyError, etree.XMLSyntaxError) as e:
        rep.gaps.append(GapRow("parse-error", slide_part, f"could not parse: {e}"))
        return

    layout_part = _layout_part_for_slide(zf, slide_part)
    if layout_part and layout_part not in layout_index:
        layout_index[layout_part] = _layout_metadata(zf, layout_part)
    layout_name, layout_phs = (
        layout_index.get(layout_part, ("(none)", {}))
        if layout_part
        else (
            "(none)",
            {},
        )
    )
    rep.slide_layouts[slide_num] = (
        layout_part.rsplit("/", 1)[-1].removesuffix(".xml") if layout_part else "(none)",
        layout_name,
    )

    seen_keys: set[tuple[str, str]] = set()
    for sp in root.findall(".//p:sp", NS):
        cnv = sp.find("p:nvSpPr/p:cNvPr", NS)
        shape_name = (cnv.get("name") if cnv is not None else None) or "?"
        ph = sp.find("p:nvSpPr/p:nvPr/p:ph", NS)

        if ph is None:
            text, _flds, _has_tx = _shape_text(sp)
            lit = text.strip().lower()
            if not lit:
                continue
            preview = text.strip().replace("\n", " ")[:80]
            if any(m in lit for m in LOREM_MARKERS):
                rep.leak_shapes.append(LeakShape(slide_num, shape_name, "lorem-ipsum", preview))
                continue
            for phrase in PLACEHOLDER_PHRASES:
                if phrase in LOREM_MARKERS:
                    continue
                if phrase in lit:
                    rep.leak_shapes.append(LeakShape(slide_num, shape_name, "prompt-leak", preview))
                    break
            continue

        idx_attr = ph.get("idx")
        type_attr = ph.get("type")
        key = _ph_key(idx_attr, type_attr)
        seen_keys.add(key)

        text, fld_ids, has_tx = _shape_text(sp)
        state = _classify(text, fld_ids, has_tx)
        idx_disp = idx_attr if idx_attr is not None else "(default)"
        type_disp = type_attr if type_attr is not None else "(default)"

        if key in layout_phs:
            layout_match = "matched"
            layout_ph_name = layout_phs[key]
        else:
            layout_match = "orphan"
            layout_ph_name = ""
            rep.gaps.append(
                GapRow(
                    "orphan",
                    f"slide{slide_num}",
                    f"shape {shape_name!r} placeholder idx={idx_disp} type={type_disp} "
                    f"not declared on layout {layout_name!r}",
                )
            )

        preview = text.strip().replace("\n", " ")[:80]
        rep.rows.append(
            PlaceholderRow(
                slide_num=slide_num,
                shape_name=shape_name,
                idx=idx_disp,
                type=type_disp,
                layout_match=layout_match,
                layout_ph_name=layout_ph_name,
                state=state,
                text_preview=preview,
                tcfield_ids=fld_ids,
            )
        )

    for key, ph_name in layout_phs.items():
        if key in seen_keys:
            continue
        rep.gaps.append(
            GapRow(
                "unfilled",
                f"slide{slide_num}",
                f"layout {layout_name!r} declares placeholder {ph_name!r} "
                f"idx={key[0]} type={key[1]} but slide has no shape with that placeholder",
            )
        )


def _layout_usage_gaps(
    zf: zipfile.ZipFile,
    layout_index: dict[str, tuple[str, dict[tuple[str, str], str]]],
    slide_layouts: dict[int, tuple[str, str]],
) -> list[GapRow]:
    used = {sl[0] for sl in slide_layouts.values()}
    out: list[GapRow] = []
    all_layouts = sorted(
        n
        for n in zf.namelist()
        if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml")
    )
    for lp in all_layouts:
        stem = lp.rsplit("/", 1)[-1].removesuffix(".xml")
        if stem in used:
            continue
        if lp not in layout_index:
            layout_index[lp] = _layout_metadata(zf, lp)
        layout_name = layout_index[lp][0]
        out.append(
            GapRow(
                "layout-unused",
                stem,
                f"layout {layout_name!r} not referenced by any slide",
            )
        )
    return out


def inventory(path: Path) -> Report:
    rep = Report(path=str(path))
    if not path.exists():
        rep.gaps.append(GapRow("file-missing", str(path), "file not found"))
        return rep
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as e:
        rep.gaps.append(GapRow("zip-invalid", str(path), f"not a valid zip: {e}"))
        return rep
    with zf:
        slide_parts = sorted(
            n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        # numerical sort so slide11 follows slide10 not slide1
        slide_parts.sort(key=_slide_num_from_part)
        rep.slide_count = len(slide_parts)
        layout_index: dict[str, tuple[str, dict[tuple[str, str], str]]] = {}
        for sp in slide_parts:
            _scan_slide(zf, sp, rep, layout_index)
        rep.gaps.extend(_layout_usage_gaps(zf, layout_index, rep.slide_layouts))
    return rep


def _format_text(rep: Report, quiet: bool = False) -> str:
    name = Path(rep.path).name
    out = [f"== {name}  slides={rep.slide_count}"]
    leak_states = {"prompt-leak", "lorem-ipsum"}

    rows_by_slide: dict[int, list[PlaceholderRow]] = {}
    for r in rep.rows:
        rows_by_slide.setdefault(r.slide_num, []).append(r)
    leaks_by_slide: dict[int, list[LeakShape]] = {}
    for ls in rep.leak_shapes:
        leaks_by_slide.setdefault(ls.slide_num, []).append(ls)

    all_slides = sorted(set(rows_by_slide) | set(leaks_by_slide))
    for sn in all_slides:
        rows = rows_by_slide.get(sn, [])
        leaks = leaks_by_slide.get(sn, [])
        slide_has_leak = bool(leaks) or any(r.state in leak_states for r in rows)
        slide_has_orphan = any(r.layout_match == "orphan" for r in rows)
        if quiet and not (slide_has_leak or slide_has_orphan):
            continue
        layout_stem, layout_name = rep.slide_layouts.get(sn, ("?", "?"))
        out.append("")
        out.append(f"SLIDE {sn:<3} layout={layout_stem} ({layout_name})")
        for r in rows:
            marker = "  <<<" if r.state in leak_states or r.layout_match == "orphan" else ""
            tc = f" tcfields={r.tcfield_ids}" if r.tcfield_ids else ""
            preview = f'"{r.text_preview}"' if r.text_preview else '""'
            out.append(
                f"  ph idx={r.idx:<3} type={r.type:<10} state={r.state:<14} {preview}{tc}{marker}"
            )
        for ls in leaks:
            preview = f'"{ls.text_preview}"' if ls.text_preview else '""'
            out.append(f"  shape {ls.shape_name!r:<28} state={ls.state:<14} {preview}  <<<")

    if rep.gaps and not quiet:
        out.append("")
        out.append("GAPS:")
        for g in rep.gaps:
            out.append(f"  [{g.kind}] {g.location}: {g.detail}")
    elif quiet:
        leaks_only = [g for g in rep.gaps if g.kind == "orphan"]
        if leaks_only:
            out.append("")
            out.append("GAPS (orphans only):")
            for g in leaks_only:
                out.append(f"  [{g.kind}] {g.location}: {g.detail}")

    sc = rep.state_counts()
    gc = rep.gap_counts()
    out.append("")
    out.append(
        "SUMMARY:  "
        + "  ".join(f"{s}={sc.get(s, 0)}" for s in STATES)
        + f"  orphan={gc.get('orphan', 0)}"
        + f"  unfilled={gc.get('unfilled', 0)}"
        + f"  layout-unused={gc.get('layout-unused', 0)}"
    )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument(
        "--quiet",
        action="store_true",
        help="text mode: only show slides with leaks/orphans + summary",
    )
    args = p.parse_args(argv)

    reports = [inventory(path) for path in args.paths]
    if args.json:
        print(json.dumps({"reports": [r.to_dict() for r in reports]}, indent=2))
    else:
        for r in reports:
            print(_format_text(r, quiet=args.quiet))

    worst = 0
    for r in reports:
        sc = r.state_counts()
        gc = r.gap_counts()
        if sc.get("lorem-ipsum", 0) or sc.get("prompt-leak", 0):
            worst = max(worst, 1)
        elif gc.get("orphan", 0) or gc.get("unfilled", 0):
            worst = max(worst, 2)
        if any(g.kind in ("file-missing", "zip-invalid") for g in r.gaps):
            worst = max(worst, 3)
    return worst


if __name__ == "__main__":
    sys.exit(main())
