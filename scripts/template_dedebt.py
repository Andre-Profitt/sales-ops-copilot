#!/usr/bin/env python3
"""Strip polish_pass / master_transplant debris + apply brand-color rule book.

Produces a clean LAND_thinkcell_seed.pptx from the current (debt-laden) seed.
Idempotent: running it on already-clean output is a no-op (modulo timestamp
fields in docProps/core.xml).

Pipeline:
  1. Drop orphan <p:sp> shapes (placeholder marker not declared on layout)
  2. Drop off-canvas shapes (xfrm/off past sldSz canvas edge)
  3. Drop "leak shapes" carrying lorem-ipsum / placeholder-prompt text
  4. Uppercase all <a:fld id="..."> GUIDs in ppt/charts/chart*.xml (ECMA-376 §A.2)
  5. Apply brand-color rule book to runs with no explicit <a:rPr>/<a:solidFill>:
       - title placeholder OR sz>=18      -> #083EA7  (SimCorp navy)
       - section header (sz 14-17)        -> #1A1D31  (near-black)
       - body (sz<14, no placeholder hint) -> #1A1D31  (near-black)
       - footer/page-num placeholder      -> #666666  (mid-grey)
       - on dark-fill shape (luma <= 0x33) -> #FFFFFF  (white)
       - tcfield runs                     -> inherit shape parent's rule

Hard rules respected:
  - Slide 1 + slide 16/closing preserved (SimCorp official brand pattern -
    only color-sweep applies, no shape removals).
  - Think-cell oleObject anchors and chart parts left UNTOUCHED.
  - No viz-type changes (color and data only).

Usage:
    python3 scripts/template_dedebt.py assets/LAND_thinkcell_seed.pptx \\
        --out assets/LAND_thinkcell_seed.dedebt.pptx
    python3 scripts/template_dedebt.py assets/LAND_thinkcell_seed.pptx --in-place

Exit codes:
    0  success
    1  input issues
    2  could not parse
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(1)

NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"p": NS_P, "a": NS_A, "r": NS_R}
NS_DECL = {"p": NS_P, "a": NS_A}

EMU_PER_INCH = 914400
SLIDE1_PRESERVE = ("ppt/slides/slide1.xml",)
SLIDE_CLOSING_HINTS = ("slide16.xml", "slide28.xml")

DARK_LUMA_MAX = 0x33
SCHEME_NAMES = (
    "dk1",
    "lt1",
    "dk2",
    "lt2",
    "accent1",
    "accent2",
    "accent3",
    "accent4",
    "accent5",
    "accent6",
    "hlink",
    "folHlink",
)
SCHEME_ALIASES = {"bg1": "lt1", "tx1": "dk1", "bg2": "lt2", "tx2": "dk2"}

PLACEHOLDER_PHRASES = (
    "lorem ipsum",
    "consectetur adipiscing",
    "click to add title",
    "click to add text",
    "click to add subtitle",
    "click to add notes",
    "your title here",
    "your text here",
    "rechteck",
    "platzhalter",
)

GUID_LOWER_RE = re.compile(
    r"\{([0-9a-fA-F]{8})-([0-9a-fA-F]{4})-([0-9a-fA-F]{4})-([0-9a-fA-F]{4})-([0-9a-fA-F]{12})\}"
)


@dataclass
class DebtReport:
    orphans_removed: list[str] = field(default_factory=list)
    offcanvas_removed: list[str] = field(default_factory=list)
    leak_shapes_removed: list[str] = field(default_factory=list)
    fld_ids_uppercased: int = 0
    runs_color_applied: dict[str, int] = field(default_factory=dict)
    parts_processed: int = 0
    parts_skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "orphans_removed": self.orphans_removed,
            "offcanvas_removed": self.offcanvas_removed,
            "leak_shapes_removed": self.leak_shapes_removed,
            "fld_ids_uppercased": self.fld_ids_uppercased,
            "runs_color_applied": self.runs_color_applied,
            "parts_processed": self.parts_processed,
            "parts_skipped": self.parts_skipped,
        }


def _qn(local: str, ns: str = NS_A) -> str:
    return f"{{{ns}}}{local}"


def _parse(data: bytes) -> etree._Element:
    return etree.fromstring(data)


def _serialize(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _load_theme_colors(zin: zipfile.ZipFile) -> dict[str, str]:
    try:
        root = _parse(zin.read("ppt/theme/theme1.xml"))
    except (KeyError, etree.XMLSyntaxError):
        return {}
    scheme = root.find(".//a:clrScheme", NS)
    if scheme is None:
        return {}
    out: dict[str, str] = {}
    for n in SCHEME_NAMES:
        node = scheme.find(f"a:{n}", NS)
        if node is None:
            continue
        srgb = node.find("a:srgbClr", NS)
        if srgb is not None and srgb.get("val"):
            out[n] = srgb.get("val", "").upper()
            continue
        sysclr = node.find("a:sysClr", NS)
        if sysclr is not None and sysclr.get("lastClr"):
            out[n] = sysclr.get("lastClr", "").upper()
    for alias, target in SCHEME_ALIASES.items():
        if target in out:
            out[alias] = out[target]
    return out


def _resolve_color(elem: etree._Element | None, theme: dict[str, str]) -> str | None:
    if elem is None:
        return None
    for child in elem:
        tag = etree.QName(child).localname
        if tag == "srgbClr":
            v = child.get("val")
            return v.upper() if v else None
        if tag == "sysClr":
            v = child.get("lastClr") or child.get("val")
            return v.upper() if v else None
        if tag == "schemeClr":
            v = child.get("val")
            if v and v in theme:
                return theme[v]
            return None
    return None


def _slide_dims(zin: zipfile.ZipFile) -> tuple[int, int]:
    try:
        root = _parse(zin.read("ppt/presentation.xml"))
    except (KeyError, etree.XMLSyntaxError):
        return 12192000, 6858000
    sld = root.find("p:sldSz", NS)
    if sld is None:
        return 12192000, 6858000
    try:
        return int(sld.get("cx") or 12192000), int(sld.get("cy") or 6858000)
    except ValueError:
        return 12192000, 6858000


def _layout_for_slide(zin: zipfile.ZipFile, slide_part: str) -> str | None:
    rels = slide_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    try:
        root = _parse(zin.read(rels))
    except (KeyError, etree.XMLSyntaxError):
        return None
    for r in root:
        target = r.get("Target") or ""
        if "slideLayout" in target:
            return "ppt/slideLayouts/" + target.split("/")[-1]
    return None


def _layout_placeholder_keys(zin: zipfile.ZipFile, layout_part: str) -> set[tuple[str, str]]:
    try:
        root = _parse(zin.read(layout_part))
    except (KeyError, etree.XMLSyntaxError):
        return set()
    keys: set[tuple[str, str]] = set()
    for ph in root.findall(".//p:ph", NS):
        keys.add((ph.get("idx") or "0", ph.get("type") or ""))
    return keys


def _luma(hex_str: str) -> int:
    if len(hex_str) < 6:
        return 0xFF
    try:
        r = int(hex_str[0:2], 16)
        g = int(hex_str[2:4], 16)
        b = int(hex_str[4:6], 16)
    except ValueError:
        return 0xFF
    return (r * 299 + g * 587 + b * 114) // 1000


def _shape_text(sp: etree._Element) -> str:
    parts = [(t.text or "") for t in sp.findall(".//a:t", NS)]
    return " ".join(p for p in parts if p).strip()


def _shape_position(sp: etree._Element) -> tuple[int, int, int, int] | None:
    xfrm = sp.find(".//a:xfrm", NS)
    if xfrm is None:
        xfrm = sp.find(".//p:xfrm", NS)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    try:
        return (
            int(off.get("x") or 0),
            int(off.get("y") or 0),
            int(ext.get("cx") or 0),
            int(ext.get("cy") or 0),
        )
    except ValueError:
        return None


def _is_thinkcell_anchor(sp: etree._Element) -> bool:
    cnv = sp.find(".//p:cNvPr", NS)
    if cnv is not None:
        name = (cnv.get("name") or "").lower()
        if "think-cell" in name or "tclayout" in name or name.startswith("tcfield"):
            return True
    if sp.find(".//a:fld", NS) is not None:
        return True
    return False


def _is_chart_frame(sp: etree._Element) -> bool:
    return sp.find(".//a:graphic", NS) is not None and sp.find(".//a:graphicData", NS) is not None


def _strip_orphans_offcanvas_leaks(
    root: etree._Element,
    layout_keys: set[tuple[str, str]],
    slide_w: int,
    slide_h: int,
    rep: DebtReport,
    slide_part: str,
    preserve: bool,
) -> None:
    spTree = root.find(".//p:spTree", NS)
    if spTree is None:
        return
    for sp in list(spTree.findall("p:sp", NS)):
        cnv = sp.find(".//p:cNvPr", NS)
        sp_name = cnv.get("name") if cnv is not None else "(unnamed)"
        ph = sp.find(".//p:ph", NS)

        # Leak detection (Lorem ipsum / placeholder prompts in non-master/layout text)
        text = _shape_text(sp).lower()
        if text:
            for phrase in PLACEHOLDER_PHRASES:
                if phrase in text:
                    if not preserve:
                        spTree.remove(sp)
                        rep.leak_shapes_removed.append(f"{slide_part}::{sp_name} ({phrase!r})")
                    break
            else:
                # No leak phrase matched, fall through to orphan/off-canvas checks
                pass
            if sp.getparent() is None:
                continue

        # Off-canvas check. Think-cell tcfield/anchor shapes are intentionally
        # placed off-canvas as a hiding mechanism (load-bearing for think-cell
        # data binding). Never strip them regardless of position.
        if not _is_thinkcell_anchor(sp):
            pos = _shape_position(sp)
            if pos is not None:
                x, y, _cx, _cy = pos
                if (x > slide_w or y > slide_h) and not preserve:
                    spTree.remove(sp)
                    rep.offcanvas_removed.append(
                        f"{slide_part}::{sp_name} at ({x / EMU_PER_INCH:.2f}in,{y / EMU_PER_INCH:.2f}in)"
                    )
                    continue

        # Orphan placeholder check: shape has <p:ph> but layout doesn't declare
        # the same idx/type. Skip if it's a think-cell anchor (those are
        # bound differently and should never be considered orphans).
        if ph is not None and not _is_thinkcell_anchor(sp) and not preserve:
            key = (ph.get("idx") or "0", ph.get("type") or "")
            if key not in layout_keys:
                spTree.remove(sp)
                rep.orphans_removed.append(
                    f"{slide_part}::{sp_name} idx={key[0]} type={key[1] or '(default)'}"
                )


def _uppercase_fld_ids(root: etree._Element, rep: DebtReport) -> None:
    for fld in root.findall(".//a:fld", NS):
        v = fld.get("id")
        if v is None:
            continue
        m = GUID_LOWER_RE.match(v)
        if m and any(c.islower() for c in v):
            new = "{" + "-".join(g.upper() for g in m.groups()) + "}"
            if new != v:
                fld.set("id", new)
                rep.fld_ids_uppercased += 1


def _classify_run_for_color(
    sp: etree._Element,
    run: etree._Element,
    theme: dict[str, str],
    slide_h: int = 6858000,
) -> str | None:
    """Pick a brand color hex (no leading #) for a run with no explicit color.
    Returns None if the run already has explicit color or shouldn't be modified.
    """
    rPr = run.find("a:rPr", NS)
    if rPr is not None and rPr.find("a:solidFill", NS) is not None:
        return None

    sp_pr = sp.find("p:spPr", NS) if sp is not None else None
    sp_fill_color = None
    if sp_pr is not None:
        sp_fill = sp_pr.find("a:solidFill", NS)
        sp_fill_color = _resolve_color(sp_fill, theme)
    if sp_fill_color and _luma(sp_fill_color) <= DARK_LUMA_MAX:
        return "FFFFFF"

    ph = sp.find(".//p:ph", NS) if sp is not None else None
    ph_type = ph.get("type") if ph is not None else None
    if ph_type in {"ftr", "sldNum", "dt"}:
        return "666666"
    if ph_type in {"title", "ctrTitle"}:
        return "083EA7"

    # Title-tier escalation by position: when sz/ph type don't classify as
    # title but the shape's xfrm/off.y sits in the top quarter of the slide,
    # treat as title. Catches cover slides where size inherits from layout.
    pos = _shape_position(sp)
    if pos is not None:
        _x, y, _cx, _cy = pos
        if y <= slide_h // 4:
            return "083EA7"

    sz_attr = (rPr.get("sz") if rPr is not None else None) or "1100"
    try:
        sz_pt = int(sz_attr) // 100
    except ValueError:
        sz_pt = 11
    if sz_pt >= 18:
        return "083EA7"
    return "1A1D31"


def _apply_color_sweep(
    root: etree._Element, theme: dict[str, str], rep: DebtReport, slide_h: int = 6858000
) -> None:
    """Add explicit srgbClr to runs that inherit theme defaults."""
    spTree = root.find(".//p:spTree", NS)
    if spTree is None:
        return
    for sp in spTree.findall(".//p:sp", NS):
        for r in sp.findall(".//a:r", NS):
            color = _classify_run_for_color(sp, r, theme, slide_h)
            if color is None:
                continue
            rPr = r.find("a:rPr", NS)
            if rPr is None:
                rPr = etree.SubElement(r, _qn("rPr"))
                # rPr must be the first child of <a:r>; lxml SubElement appends.
                # Move to position 0.
                r.remove(rPr)
                r.insert(0, rPr)
            sf = etree.SubElement(rPr, _qn("solidFill"))
            srgb = etree.SubElement(sf, _qn("srgbClr"))
            srgb.set("val", color)
            rep.runs_color_applied[color] = rep.runs_color_applied.get(color, 0) + 1


def dedebt(input_path: Path, output_path: Path) -> DebtReport:
    rep = DebtReport()
    if input_path.resolve() != output_path.resolve():
        shutil.copyfile(input_path, output_path)

    # Process in two passes: first read everything we need (theme, layout keys),
    # then mutate slides + chart parts in a single re-zip cycle.
    with zipfile.ZipFile(output_path, "r") as zin:
        theme = _load_theme_colors(zin)
        slide_w, slide_h = _slide_dims(zin)
        all_names = zin.namelist()
        slide_parts = sorted(
            n for n in all_names if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        chart_parts = sorted(
            n for n in all_names if n.startswith("ppt/charts/chart") and n.endswith(".xml")
        )
        layout_keys_cache: dict[str, set[tuple[str, str]]] = {}
        for sp_name in slide_parts:
            layout_part = _layout_for_slide(zin, sp_name)
            if layout_part:
                if layout_part not in layout_keys_cache:
                    layout_keys_cache[layout_part] = _layout_placeholder_keys(zin, layout_part)
        contents: dict[str, bytes] = {n: zin.read(n) for n in all_names}

    # Mutate slides
    for sp_name in slide_parts:
        rep.parts_processed += 1
        layout_part = _layout_for_slide_from_contents(contents, sp_name)
        layout_keys = layout_keys_cache.get(layout_part or "", set())
        try:
            root = _parse(contents[sp_name])
        except etree.XMLSyntaxError:
            rep.parts_skipped.append(sp_name)
            continue
        preserve = sp_name in SLIDE1_PRESERVE or sp_name.endswith(SLIDE_CLOSING_HINTS)
        _strip_orphans_offcanvas_leaks(root, layout_keys, slide_w, slide_h, rep, sp_name, preserve)
        _apply_color_sweep(root, theme, rep, slide_h)
        contents[sp_name] = _serialize(root)

    # Mutate chart parts (uppercase fld GUIDs)
    for ch_name in chart_parts:
        rep.parts_processed += 1
        try:
            root = _parse(contents[ch_name])
        except etree.XMLSyntaxError:
            rep.parts_skipped.append(ch_name)
            continue
        _uppercase_fld_ids(root, rep)
        contents[ch_name] = _serialize(root)

    # Re-zip
    tmp_path = output_path.with_suffix(".tmp.pptx")
    with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, data in contents.items():
            zout.writestr(name, data)
    shutil.move(tmp_path, output_path)

    return rep


def _layout_for_slide_from_contents(contents: dict[str, bytes], slide_part: str) -> str | None:
    rels = slide_part.replace("ppt/slides/", "ppt/slides/_rels/") + ".rels"
    if rels not in contents:
        return None
    try:
        root = _parse(contents[rels])
    except etree.XMLSyntaxError:
        return None
    for r in root:
        target = r.get("Target") or ""
        if "slideLayout" in target:
            return "ppt/slideLayouts/" + target.split("/")[-1]
    return None


def _format_summary(rep: DebtReport) -> str:
    lines = [
        "== template_dedebt summary",
        f"   parts_processed: {rep.parts_processed}",
        f"   orphans_removed: {len(rep.orphans_removed)}",
        f"   offcanvas_removed: {len(rep.offcanvas_removed)}",
        f"   leak_shapes_removed: {len(rep.leak_shapes_removed)}",
        f"   fld_ids_uppercased: {rep.fld_ids_uppercased}",
        "   runs_color_applied: "
        + ", ".join(f"#{k}={v}" for k, v in sorted(rep.runs_color_applied.items())),
    ]
    if rep.orphans_removed[:6]:
        lines.append("   orphans (first 6):")
        for x in rep.orphans_removed[:6]:
            lines.append(f"     - {x}")
    if rep.offcanvas_removed[:6]:
        lines.append("   off-canvas (first 6):")
        for x in rep.offcanvas_removed[:6]:
            lines.append(f"     - {x}")
    if rep.leak_shapes_removed[:6]:
        lines.append("   leaks (first 6):")
        for x in rep.leak_shapes_removed[:6]:
            lines.append(f"     - {x}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("input", type=Path)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--in-place", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not args.input.exists():
        sys.stderr.write(f"input not found: {args.input}\n")
        return 1
    if args.in_place:
        out = args.input
    elif args.out:
        out = args.out
    else:
        out = args.input.with_suffix(".dedebt.pptx")

    rep = dedebt(args.input, out)
    if args.json:
        import json

        print(json.dumps(rep.to_dict(), indent=2))
    else:
        print(_format_summary(rep))
        print(f"\noutput: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
