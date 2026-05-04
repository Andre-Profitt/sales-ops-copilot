#!/usr/bin/env python3
"""Per-run text inventory for a .pptx — every <a:r> and <a:fld> on every slide.

Companion to scripts/validate_pptx_strict.py. Where the validator gates on
known-bad patterns, this dumps the full text-run census so the deck-factory
harness can make brand-styling decisions with real data:

  - which runs have explicit colors vs inherit theme tx1 (the brand-leak class)
  - which runs are think-cell field anchors vs literal text vs leftover
    placeholder prompts (the polished_v2 lorem class)
  - font diversity per run, size outliers, b/i/u flag distribution
  - shape fill behind every run, so contrast deltas can be computed downstream

Spec references (ECMA-376 / ISO 29500-1):
  - §19.3.1.43 r (text run)         §19.3.1.34 fld (text field)
  - §19.3.1.50 sp (shape)           §19.3.1.32 cNvPr (non-visual props)
  - §20.1.4.1.7 latin               §20.1.10.45 schemeClr
  - §20.1.4.1.43 solidFill          §20.1.10.55 srgbClr
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

# scripts/ may not be on sys.path when invoked as `python3 scripts/...py`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Re-use helpers from the validator to avoid drift.
from validate_pptx_strict import (  # type: ignore[import-not-found]  # noqa: E402
    NS,
    PLACEHOLDER_PHRASES,
    _load_theme_colors,
    _resolve_color,
)


@dataclass
class RunRow:
    slide: int
    layout: str
    shape_name: str
    shape_fill_hex: str | None
    run_index: int
    source_kind: str  # literal | tcfield | placeholder-prompt
    fld_id: str | None
    fld_type: str | None
    text_preview: str
    explicit_color_hex: str | None
    effective_color_hex: str | None
    font_name: str
    size_pt: float | None
    bold: bool
    italic: bool
    underline: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SlideInventory:
    slide_number: int
    part: str
    layout: str
    runs: list[RunRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slide_number": self.slide_number,
            "part": self.part,
            "layout": self.layout,
            "runs": [r.to_dict() for r in self.runs],
        }


@dataclass
class Inventory:
    path: str
    slide_count: int = 0
    theme_major_font: str = ""
    theme_minor_font: str = ""
    theme_tx1_hex: str | None = None
    slides: list[SlideInventory] = field(default_factory=list)

    def to_dict(self) -> dict:
        rows = [r for s in self.slides for r in s.runs]
        by_kind = Counter(r.source_kind for r in rows)
        by_font = Counter(r.font_name for r in rows)
        explicit = sum(1 for r in rows if r.explicit_color_hex is not None)
        return {
            "path": self.path,
            "slide_count": self.slide_count,
            "theme": {
                "major_font": self.theme_major_font,
                "minor_font": self.theme_minor_font,
                "tx1_hex": self.theme_tx1_hex,
            },
            "summary": {
                "total_runs": len(rows),
                "by_source_kind": dict(by_kind),
                "explicit_color": explicit,
                "inherited_color": len(rows) - explicit,
                "by_font": dict(by_font),
            },
            "slides": [s.to_dict() for s in self.slides],
        }


def _read_xml(zf: zipfile.ZipFile, name: str) -> etree._Element | None:
    try:
        return etree.fromstring(zf.read(name))
    except (KeyError, etree.XMLSyntaxError):
        return None


def _theme_fonts(zf: zipfile.ZipFile) -> tuple[str, str]:
    root = _read_xml(zf, "ppt/theme/theme1.xml")
    if root is None:
        return "", ""
    major = root.find(".//a:majorFont/a:latin", NS)
    minor = root.find(".//a:minorFont/a:latin", NS)
    return (
        major.get("typeface", "") if major is not None else "",
        minor.get("typeface", "") if minor is not None else "",
    )


def _layout_for_slide(zf: zipfile.ZipFile, slide_part: str) -> str:
    """Return e.g. 'slideLayout1' for ppt/slides/slide1.xml via its rels file."""
    base = slide_part.rsplit("/", 1)[1]  # slide1.xml
    rels_part = f"ppt/slides/_rels/{base}.rels"
    root = _read_xml(zf, rels_part)
    if root is None:
        return "(unknown)"
    ns_pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    type_layout = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
    for rel in root.findall(f"{{{ns_pkg}}}Relationship"):
        if rel.get("Type") == type_layout:
            target = rel.get("Target", "")
            return target.rsplit("/", 1)[-1].replace(".xml", "")
    return "(none)"


def _enclosing_shape(elem: etree._Element) -> etree._Element | None:
    p_sp = f"{{{NS['p']}}}sp"
    cur = elem
    while cur is not None:
        if cur.tag == p_sp:
            return cur
        cur = cur.getparent()
    return None


def _shape_name(sp: etree._Element | None) -> str:
    if sp is None:
        return "(unnamed)"
    cnv = sp.find("p:nvSpPr/p:cNvPr", NS)
    if cnv is None:
        return "(unnamed)"
    return cnv.get("name") or "(unnamed)"


def _shape_fill_hex(sp: etree._Element | None, theme: dict[str, str]) -> str | None:
    if sp is None:
        return None
    sp_pr = sp.find("p:spPr", NS)
    if sp_pr is None:
        return None
    return _resolve_color(sp_pr.find("a:solidFill", NS), theme)


def _is_placeholder_prompt(text: str) -> bool:
    s = text.strip().lower()
    if not s:
        return False
    return any(p in s for p in PLACEHOLDER_PHRASES)


def _run_font(rpr: etree._Element | None, theme_minor: str) -> str:
    """Latin typeface from rPr; theme +mn-lt → minor font; else (default).

    PPT also resolves +mj-lt (major). We don't see it in seed runs, but handle
    it so we don't mislabel theme-typed text on layouts later.
    """
    if rpr is None:
        return theme_minor or "(default)"
    latin = rpr.find("a:latin", NS)
    if latin is None:
        return theme_minor or "(default)"
    typeface = latin.get("typeface", "") or ""
    if typeface == "+mn-lt":
        return theme_minor or "(default)"
    if typeface == "+mj-lt":
        return theme_minor or "(default)"
    return typeface or theme_minor or "(default)"


def _run_size_pt(rpr: etree._Element | None) -> float | None:
    if rpr is None:
        return None
    sz = rpr.get("sz")
    if not sz:
        return None
    try:
        return int(sz) / 100.0
    except ValueError:
        return None


def _flag(rpr: etree._Element | None, attr: str) -> bool:
    if rpr is None:
        return False
    val = rpr.get(attr)
    return val == "1"


def _underline(rpr: etree._Element | None) -> bool:
    if rpr is None:
        return False
    u = rpr.get("u")
    return bool(u) and u != "none"


def _classify_run(elem: etree._Element, text: str) -> tuple[str, str | None, str | None]:
    """Source kind + (fld_id, fld_type) when applicable."""
    tag = etree.QName(elem).localname
    if tag == "fld":
        return "tcfield", elem.get("id"), elem.get("type")
    # Literal a:r — but its text may BE a placeholder prompt.
    if _is_placeholder_prompt(text):
        return "placeholder-prompt", None, None
    return "literal", None, None


def _runs_in_doc_order(root: etree._Element) -> list[etree._Element]:
    """All <a:r> + <a:fld> in document order. iterwalk preserves order;
    a sibling fld can appear before, between, or after r elements within a
    paragraph, so we cannot assume r-only.
    """
    out: list[etree._Element] = []
    a_r = f"{{{NS['a']}}}r"
    a_fld = f"{{{NS['a']}}}fld"
    for el in root.iter():
        if el.tag in (a_r, a_fld):
            out.append(el)
    return out


def _text_of(elem: etree._Element) -> str:
    t = elem.find("a:t", NS)
    return (t.text or "") if (t is not None and t.text) else ""


def inventory(path: Path) -> Inventory:
    inv = Inventory(path=str(path))
    if not path.exists():
        return inv
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile:
        return inv

    with zf:
        theme = _load_theme_colors(zf)
        major, minor = _theme_fonts(zf)
        inv.theme_major_font = major
        inv.theme_minor_font = minor
        inv.theme_tx1_hex = theme.get("tx1") or theme.get("dk1")
        default_text_color = inv.theme_tx1_hex

        slide_parts = sorted(
            n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        inv.slide_count = len(slide_parts)

        for slide_part in slide_parts:
            base = slide_part.rsplit("/", 1)[1]
            slide_num = int("".join(ch for ch in base.replace(".xml", "") if ch.isdigit()) or "0")
            root = _read_xml(zf, slide_part)
            if root is None:
                continue
            layout = _layout_for_slide(zf, slide_part)
            slide_inv = SlideInventory(slide_number=slide_num, part=slide_part, layout=layout)

            shape_run_index: dict[int, int] = {}
            for elem in _runs_in_doc_order(root):
                sp = _enclosing_shape(elem)
                shape_id = id(sp) if sp is not None else 0
                shape_run_index[shape_id] = shape_run_index.get(shape_id, 0) + 1
                run_idx = shape_run_index[shape_id]
                shape_name = _shape_name(sp)
                shape_fill = _shape_fill_hex(sp, theme)

                rpr = elem.find("a:rPr", NS)
                text = _text_of(elem)
                source_kind, fld_id, fld_type = _classify_run(elem, text)

                explicit = (
                    _resolve_color(rpr.find("a:solidFill", NS), theme) if rpr is not None else None
                )
                effective = explicit if explicit is not None else default_text_color

                slide_inv.runs.append(
                    RunRow(
                        slide=slide_num,
                        layout=layout,
                        shape_name=shape_name,
                        shape_fill_hex=shape_fill,
                        run_index=run_idx,
                        source_kind=source_kind,
                        fld_id=fld_id,
                        fld_type=fld_type,
                        text_preview=text[:80],
                        explicit_color_hex=explicit,
                        effective_color_hex=effective,
                        font_name=_run_font(rpr, inv.theme_minor_font),
                        size_pt=_run_size_pt(rpr),
                        bold=_flag(rpr, "b"),
                        italic=_flag(rpr, "i"),
                        underline=_underline(rpr),
                    )
                )

            inv.slides.append(slide_inv)

    return inv


def _format_color(hex_val: str | None) -> str:
    return f"#{hex_val}" if hex_val else "null"


def _format_pair(explicit: str | None, effective: str | None) -> str:
    return f"{_format_color(explicit)}/{_format_color(effective)}"


def _format_flags(r: RunRow) -> str:
    flags = "".join(c for c, v in (("b", r.bold), ("i", r.italic), ("u", r.underline)) if v)
    return f" {flags}" if flags else ""


def _format_text(inv: Inventory) -> str:
    name = Path(inv.path).name
    lines = [f"== {name}"]
    if not inv.slides:
        lines.append("   (no slides found or file unreadable)")
        return "\n".join(lines)

    rows = [r for s in inv.slides for r in s.runs]
    for slide in inv.slides:
        lines.append("")
        lines.append(f"SLIDE {slide.slide_number}   layout={slide.layout}")
        # Group rows by shape for readability — preserve doc order via first-seen.
        seen_shapes: list[tuple[str, str | None]] = []
        shape_runs: dict[tuple[str, str | None], list[RunRow]] = {}
        for r in slide.runs:
            key = (r.shape_name, r.shape_fill_hex)
            if key not in shape_runs:
                shape_runs[key] = []
                seen_shapes.append(key)
            shape_runs[key].append(r)
        for key in seen_shapes:
            shape_name, fill = key
            lines.append(f'  shape "{shape_name}"           fill={_format_color(fill)}')
            for r in shape_runs[key]:
                src = r.source_kind
                if r.source_kind == "tcfield":
                    src_label = f"tcfield({r.fld_id})" if r.fld_id else "tcfield"
                else:
                    src_label = src
                color = _format_pair(r.explicit_color_hex, r.effective_color_hex)
                size = f"sz={r.size_pt:g}" if r.size_pt is not None else "sz=?"
                preview = r.text_preview.replace("\n", " ")
                lines.append(
                    f"    run {r.run_index}  src={src_label:<20} "
                    f'"{preview}"  color={color}  font={r.font_name} {size}{_format_flags(r)}'
                )

    by_kind = Counter(r.source_kind for r in rows)
    by_font = Counter(r.font_name for r in rows)
    explicit = sum(1 for r in rows if r.explicit_color_hex is not None)
    inherited = len(rows) - explicit
    sizes = sorted({r.size_pt for r in rows if r.size_pt is not None})
    lines.append("")
    lines.append("SUMMARY:")
    parts = "   ".join(
        f"{k}={by_kind.get(k, 0)}" for k in ("literal", "tcfield", "placeholder-prompt")
    )
    lines.append(f"  total_runs={len(rows)}   {parts}")
    lines.append(f"  explicit_color={explicit}   inherited_color={inherited}")
    top = ", ".join(f"{font}={cnt}" for font, cnt in by_font.most_common(5))
    lines.append(f"  by_font: {top}")
    if sizes:
        lines.append(f"  sizes_pt: min={sizes[0]:g} max={sizes[-1]:g} unique={len(sizes)}")
    if inv.theme_tx1_hex:
        lines.append(
            f"  theme: tx1=#{inv.theme_tx1_hex}  major={inv.theme_major_font!r}  "
            f"minor={inv.theme_minor_font!r}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    inventories = [inventory(path) for path in args.paths]
    if args.json:
        print(json.dumps({"inventories": [i.to_dict() for i in inventories]}, indent=2))
        return 0
    for inv in inventories:
        print(_format_text(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
