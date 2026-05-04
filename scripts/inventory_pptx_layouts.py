#!/usr/bin/env python3
"""Deterministic OOXML inventory of slide masters, slide layouts, and slides.

Companion to validate_pptx_strict.py and diff_oxml.py. Reports the structural
picture of a .pptx — which masters exist, which layouts inherit from which
master, which slides use which layout — so we know what to keep, what to
collapse, and what is dead weight before reworking a template.

Usage:
    python3 scripts/inventory_pptx_layouts.py path/to/seed.pptx
    python3 scripts/inventory_pptx_layouts.py --json path/to/seed.pptx

Exit codes:
    0   inventory printed
    3   could not open / parse
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(3)


NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": NS_P, "a": NS_A, "r": NS_R, "pr": NS_PKG}

REL_LAYOUT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
REL_MASTER = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster"
REL_OLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"

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

PART_NUM_RE = re.compile(r"(\d+)\.xml$")


@dataclass
class Placeholder:
    idx: str
    type: str
    sz: str
    has_default_text: bool

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MasterInfo:
    part: str
    name: str
    bg: str
    layout_parts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LayoutInfo:
    part: str
    name: str
    type: str
    master_part: str
    placeholders: list[Placeholder] = field(default_factory=list)
    slide_parts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["placeholders"] = [p.to_dict() for p in self.placeholders]
        return d


@dataclass
class SlideInfo:
    part: str
    layout_part: str
    layout_name: str
    ole_objects: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Inventory:
    path: str
    masters: list[MasterInfo] = field(default_factory=list)
    layouts: list[LayoutInfo] = field(default_factory=list)
    slides: list[SlideInfo] = field(default_factory=list)
    dead_layouts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "master_count": len(self.masters),
            "layout_count": len(self.layouts),
            "slide_count": len(self.slides),
            "dead_layout_count": len(self.dead_layouts),
            "masters": [m.to_dict() for m in self.masters],
            "layouts": [l.to_dict() for l in self.layouts],
            "slides": [s.to_dict() for s in self.slides],
            "dead_layouts": self.dead_layouts,
        }


def _short(part: str) -> str:
    return Path(part).stem


def _part_num(part: str) -> int:
    m = PART_NUM_RE.search(part)
    return int(m.group(1)) if m else 0


def _read_xml(zf: zipfile.ZipFile, name: str) -> etree._Element | None:
    try:
        return etree.fromstring(zf.read(name))
    except (KeyError, etree.XMLSyntaxError):
        return None


def _load_theme_colors(zf: zipfile.ZipFile) -> dict[str, str]:
    root = _read_xml(zf, "ppt/theme/theme1.xml")
    if root is None:
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
        sys_clr = node.find("a:sysClr", NS)
        if sys_clr is not None and sys_clr.get("lastClr"):
            out[n] = sys_clr.get("lastClr", "").upper()
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
            return theme.get(v) if v else None
    return None


def _master_clrmap(root: etree._Element) -> dict[str, str]:
    cmap = root.find("p:clrMap", NS)
    if cmap is None:
        return {}
    return {k: v for k, v in cmap.attrib.items()}


def _describe_bg(root: etree._Element, theme: dict[str, str], clrmap: dict[str, str]) -> str:
    bg = root.find(".//p:cSld/p:bg", NS)
    if bg is None:
        return "inherits"
    bg_pr = bg.find("p:bgPr", NS)
    if bg_pr is not None:
        fill = bg_pr.find("a:solidFill", NS)
        hex_color = _resolve_color(fill, theme)
        if hex_color:
            return f"solidFill -> #{hex_color}"
        return "bgPr (non-solid fill)"
    bg_ref = bg.find("p:bgRef", NS)
    if bg_ref is not None:
        idx = bg_ref.get("idx", "?")
        scheme = bg_ref.find("a:schemeClr", NS)
        if scheme is not None:
            v = scheme.get("val", "")
            mapped = clrmap.get(v, v)
            theme_hex = theme.get(mapped) or theme.get(v)
            if theme_hex:
                return f"bgRef idx={idx} schemeClr={v} -> #{theme_hex}"
            return f"bgRef idx={idx} schemeClr={v}"
        return f"bgRef idx={idx}"
    return "bg (unrecognized)"


def _read_rels(zf: zipfile.ZipFile, rel_part: str) -> list[tuple[str, str, str]]:
    """Return list of (rId, type, target_normalized_part)."""
    root = _read_xml(zf, rel_part)
    if root is None:
        return []
    base_dir = str(Path(rel_part).parent.parent).replace("\\", "/")
    out: list[tuple[str, str, str]] = []
    for rel in root.findall("pr:Relationship", NS):
        rid = rel.get("Id", "")
        rtype = rel.get("Type", "")
        target = rel.get("Target", "")
        normalized = _normalize_target(base_dir, target)
        out.append((rid, rtype, normalized))
    return out


def _normalize_target(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    parts = (base_dir + "/" + target).split("/")
    stack: list[str] = []
    for p in parts:
        if p in ("", "."):
            continue
        if p == ".." and stack:
            stack.pop()
        else:
            stack.append(p)
    return "/".join(stack)


def _layout_master_part(zf: zipfile.ZipFile, layout_part: str) -> str:
    rel_part = f"ppt/slideLayouts/_rels/{Path(layout_part).name}.rels"
    for _rid, rtype, target in _read_rels(zf, rel_part):
        if rtype == REL_MASTER:
            return target
    return ""


def _slide_layout_part(zf: zipfile.ZipFile, slide_part: str) -> str:
    rel_part = f"ppt/slides/_rels/{Path(slide_part).name}.rels"
    for _rid, rtype, target in _read_rels(zf, rel_part):
        if rtype == REL_LAYOUT:
            return target
    return ""


def _slide_ole_count(zf: zipfile.ZipFile, slide_part: str) -> int:
    rel_part = f"ppt/slides/_rels/{Path(slide_part).name}.rels"
    return sum(1 for _rid, rtype, _t in _read_rels(zf, rel_part) if rtype == REL_OLE)


def _placeholder_has_text(sp: etree._Element) -> bool:
    for t in sp.findall(".//a:t", NS):
        if (t.text or "").strip():
            return True
    return False


def _layout_placeholders(root: etree._Element) -> list[Placeholder]:
    out: list[Placeholder] = []
    for sp in root.findall(".//p:sp", NS):
        ph = sp.find(".//p:nvSpPr/p:nvPr/p:ph", NS)
        if ph is None:
            continue
        out.append(
            Placeholder(
                idx=ph.get("idx", ""),
                type=ph.get("type", ""),
                sz=ph.get("sz", ""),
                has_default_text=_placeholder_has_text(sp),
            )
        )
    return out


def _master_name(root: etree._Element, part: str) -> str:
    csld = root.find("p:cSld", NS)
    if csld is not None and csld.get("name"):
        return csld.get("name", "")
    return _short(part)


def _layout_name_and_type(root: etree._Element, part: str) -> tuple[str, str]:
    csld = root.find("p:cSld", NS)
    name = csld.get("name", "") if csld is not None else ""
    if not name:
        name = _short(part)
    layout_type = root.get("type") or ""
    return name, layout_type


def build_inventory(path: Path) -> Inventory:
    inv = Inventory(path=str(path))
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        master_parts = sorted(
            (
                n
                for n in names
                if n.startswith("ppt/slideMasters/slideMaster") and n.endswith(".xml")
            ),
            key=_part_num,
        )
        layout_parts = sorted(
            (
                n
                for n in names
                if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml")
            ),
            key=_part_num,
        )
        slide_parts = sorted(
            (n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")),
            key=_part_num,
        )

        theme = _load_theme_colors(zf)

        master_clrmaps: dict[str, dict[str, str]] = {}
        for mpart in master_parts:
            mroot = _read_xml(zf, mpart)
            if mroot is None:
                continue
            master_clrmaps[mpart] = _master_clrmap(mroot)
            inv.masters.append(
                MasterInfo(
                    part=mpart,
                    name=_master_name(mroot, mpart),
                    bg=_describe_bg(mroot, theme, master_clrmaps[mpart]),
                )
            )

        for lpart in layout_parts:
            lroot = _read_xml(zf, lpart)
            if lroot is None:
                continue
            master_part = _layout_master_part(zf, lpart)
            name, ltype = _layout_name_and_type(lroot, lpart)
            inv.layouts.append(
                LayoutInfo(
                    part=lpart,
                    name=name,
                    type=ltype,
                    master_part=master_part,
                    placeholders=_layout_placeholders(lroot),
                )
            )

        layout_by_part = {l.part: l for l in inv.layouts}
        for spart in slide_parts:
            lpart = _slide_layout_part(zf, spart)
            lname = layout_by_part[lpart].name if lpart in layout_by_part else ""
            inv.slides.append(
                SlideInfo(
                    part=spart,
                    layout_part=lpart,
                    layout_name=lname,
                    ole_objects=_slide_ole_count(zf, spart),
                )
            )
            if lpart in layout_by_part:
                layout_by_part[lpart].slide_parts.append(spart)

        master_by_part = {m.part: m for m in inv.masters}
        for layout in inv.layouts:
            if layout.master_part in master_by_part:
                master_by_part[layout.master_part].layout_parts.append(layout.part)

        inv.dead_layouts = [l.part for l in inv.layouts if not l.slide_parts]

    return inv


def _format_text(inv: Inventory) -> str:
    out: list[str] = [f"== {inv.path}"]
    out.append(f"masters: {len(inv.masters)}")
    out.append(f"layouts: {len(inv.layouts)}")
    out.append(f"slides:  {len(inv.slides)}")
    out.append(f"dead layouts (never referenced): {len(inv.dead_layouts)}")
    out.append("")
    out.append("MASTERS:")
    for m in inv.masters:
        out.append(f"  {_short(m.part)} (name={m.name!r})")
        out.append(f"    bg: {m.bg}")
        out.append(f"    used by {len(m.layout_parts)} layouts")
    out.append("")
    out.append("LAYOUTS:")
    for layout in inv.layouts:
        master = _short(layout.master_part) if layout.master_part else "?"
        ltype = layout.type or "(unset)"
        out.append(
            f"  {_short(layout.part)} (name={layout.name!r}, type={ltype!r}, inherits {master})"
        )
        if layout.placeholders:
            out.append("    placeholders:")
            for ph in layout.placeholders:
                bits = []
                if ph.idx:
                    bits.append(f"idx={ph.idx}")
                bits.append(f"type={ph.type or '(default)'}")
                if ph.sz:
                    bits.append(f"sz={ph.sz}")
                bits.append(f"has_default_text={'true' if ph.has_default_text else 'false'}")
                out.append("      " + "  ".join(bits))
        else:
            out.append("    placeholders: (none)")
        if layout.slide_parts:
            slide_nums = [str(_part_num(s)) for s in layout.slide_parts]
            out.append(f"    used by slides: [{', '.join(slide_nums)}]")
        else:
            out.append("    used by slides: [] (DEAD)")
    out.append("")
    out.append("SLIDES:")
    for s in inv.slides:
        layout_short = _short(s.layout_part) if s.layout_part else "?"
        out.append(
            f"  {_short(s.part)} -> {layout_short} ({s.layout_name})  oleObjects={s.ole_objects}"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("path", type=Path)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not args.path.exists():
        sys.stderr.write(f"file not found: {args.path}\n")
        return 3
    try:
        inv = build_inventory(args.path)
    except zipfile.BadZipFile as e:
        sys.stderr.write(f"not a valid zip: {e}\n")
        return 3

    if args.json:
        print(json.dumps(inv.to_dict(), indent=2))
    else:
        print(_format_text(inv))
    return 0


if __name__ == "__main__":
    sys.exit(main())
