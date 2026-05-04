#!/usr/bin/env python3
"""Map every think-cell oleObject anchor to its slide and binding name.

Companion to validate_pptx_strict.py and inventory_pptx_layouts.py. Walks the
.pptx package, locates every ppt/embeddings/oleObject*.bin, identifies the
slide that hosts each via _rels/slide*.xml.rels, and joins against the
deck-factory binding manifest so we know which think-cell chart slot lives
on which slide.

The slide-to-binding map is best-effort: binding names follow a
SXX_<Name> convention where XX is the slide number. Where convention does
not apply (or is in an unexpected position), binding=null and the result
shows up under GAPS.

Usage:
    python3 scripts/inventory_pptx_thinkcell.py path/to/seed.pptx
    python3 scripts/inventory_pptx_thinkcell.py --json path/to/seed.pptx

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
from typing import Any

try:
    from lxml import etree  # type: ignore[import-untyped]
except ImportError:
    sys.stderr.write("missing dep: pip install lxml\n")
    sys.exit(3)


NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": NS_P, "a": NS_A, "r": NS_R, "mc": NS_MC, "pr": NS_PKG}

REL_OLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"

EMU_PER_INCH = 914400

SLIDE_PART_RE = re.compile(r"ppt/slides/slide(\d+)\.xml$")
SLIDE_RELS_RE = re.compile(r"ppt/slides/_rels/slide(\d+)\.xml\.rels$")
OLE_PART_RE = re.compile(r"ppt/embeddings/(oleObject\d+\.bin)$")
OLE_TARGET_RE = re.compile(r"embeddings/(oleObject\d+\.bin)$")
BINDING_SLIDE_RE = re.compile(r"^S(\d+)_")

DEFAULT_MANIFEST_PATH = (
    "state/thinkcell_bridge/excel_named_ranges/20260504T000502Z/binding_to_range_manifest.json"
)


@dataclass
class OleAnchor:
    part: str
    size_bytes: int
    slide_num: int | None
    slide_part: str | None
    rel_id: str | None
    cnvpr_id: str | None
    cnvpr_name: str | None
    oleobj_name: str | None
    prog_id: str | None
    pos_emu: tuple[int, int] | None
    size_emu: tuple[int, int] | None
    binding: str | None
    binding_slide_hint: int | None
    tc_field_ids: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["pos_in"] = (
            (round(self.pos_emu[0] / EMU_PER_INCH, 4), round(self.pos_emu[1] / EMU_PER_INCH, 4))
            if self.pos_emu
            else None
        )
        d["size_in"] = (
            (round(self.size_emu[0] / EMU_PER_INCH, 4), round(self.size_emu[1] / EMU_PER_INCH, 4))
            if self.size_emu
            else None
        )
        return d


@dataclass
class BindingEntry:
    name: str
    slide_hint: int | None
    function: str | None
    build_ppttc_line: int | None
    excel_sheet: str | None
    shape: str | None
    has_anchor: bool = False
    anchor_part: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Inventory:
    pptx: str
    ole_anchors: list[OleAnchor] = field(default_factory=list)
    bindings: list[BindingEntry] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    oddities: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "pptx": self.pptx,
            "ole_anchors": [a.to_dict() for a in self.ole_anchors],
            "bindings": [b.to_dict() for b in self.bindings],
            "gaps": self.gaps,
            "oddities": self.oddities,
            "summary": self.summary,
        }


def _load_manifest(repo_root: Path, override_path: Path | None) -> list[dict[str, Any]]:
    """Load the binding manifest. Prefer the JSON snapshot, fall back to the
    Python constant if JSON is missing.
    """
    if override_path is not None:
        with override_path.open() as f:
            data = json.load(f)
        return list(data.get("bindings", []))

    json_path = repo_root / DEFAULT_MANIFEST_PATH
    if json_path.is_file():
        with json_path.open() as f:
            data = json.load(f)
        bindings = data.get("bindings")
        if bindings:
            return list(bindings)

    return _load_manifest_from_python(repo_root)


def _load_manifest_from_python(repo_root: Path) -> list[dict[str, Any]]:
    """Fall back: import _BINDING_TO_RANGE_MANIFEST from the script."""
    py_path = repo_root / "scripts" / "add_chart_binding_named_ranges.py"
    if not py_path.is_file():
        return []
    spec_globals: dict[str, Any] = {
        "__name__": "_inv_loader",
        "__file__": str(py_path),
    }
    src = py_path.read_text()
    # WHY: avoid spawning the CLI of the script (it has __main__ side-effects)
    # by trimming after the manifest list ends. The list ends with the
    # closing "]" at module level; we can locate it by searching for the
    # function defs that follow.
    cut_marker = "\ndef "
    cut_at = src.find(cut_marker, src.find("_BINDING_TO_RANGE_MANIFEST"))
    src_to_exec = src[: cut_at if cut_at >= 0 else len(src)]
    exec(compile(src_to_exec, str(py_path), "exec"), spec_globals)
    raw = spec_globals.get("_BINDING_TO_RANGE_MANIFEST", [])
    return list(raw)


def _slide_hint_from_binding(name: str) -> int | None:
    m = BINDING_SLIDE_RE.match(name)
    return int(m.group(1)) if m else None


def _parse_rels_for_ole(rels_xml: bytes) -> list[tuple[str, str]]:
    """Return [(rId, oleObject_part_filename)] for every oleObject relationship."""
    try:
        root = etree.fromstring(rels_xml)
    except etree.XMLSyntaxError:
        return []
    out: list[tuple[str, str]] = []
    for rel in root.iter("{%s}Relationship" % NS_PKG):
        if rel.get("Type") != REL_OLE:
            continue
        rid = rel.get("Id") or ""
        target = rel.get("Target") or ""
        m = OLE_TARGET_RE.search(target)
        if not m:
            continue
        out.append((rid, m.group(1)))
    return out


def _parse_oleobj_in_slide(slide_xml: bytes, target_rid: str) -> dict[str, Any] | None:
    """Find the <p:oleObj r:id="rId..."> in the slide and pull its enclosing
    graphicFrame metadata: cNvPr name/id, oleObj name, progId, xfrm/ext.
    """
    try:
        root = etree.fromstring(slide_xml)
    except etree.XMLSyntaxError:
        return None

    for ole in root.iter("{%s}oleObj" % NS_P):
        rid = ole.get("{%s}id" % NS_R)
        if rid != target_rid:
            continue
        info: dict[str, Any] = {
            "oleobj_name": ole.get("name"),
            "prog_id": ole.get("progId"),
            "cnvpr_id": None,
            "cnvpr_name": None,
            "pos_emu": None,
            "size_emu": None,
        }
        # WHY: oleObj sits under graphicFrame > graphic > graphicData >
        # mc:AlternateContent > mc:Choice > p:oleObj. Walk up to graphicFrame
        # via getparent() until we reach it.
        parent = ole
        gf = None
        for _ in range(8):
            parent = parent.getparent()
            if parent is None:
                break
            if parent.tag == "{%s}graphicFrame" % NS_P:
                gf = parent
                break
        if gf is None:
            return info
        cnv = gf.find("p:nvGraphicFramePr/p:cNvPr", NS)
        if cnv is not None:
            info["cnvpr_id"] = cnv.get("id")
            info["cnvpr_name"] = cnv.get("name")
        xfm = gf.find("p:xfrm", NS)
        if xfm is not None:
            off = xfm.find("a:off", NS)
            ext = xfm.find("a:ext", NS)
            if off is not None:
                try:
                    info["pos_emu"] = (int(off.get("x") or 0), int(off.get("y") or 0))
                except ValueError:
                    pass
            if ext is not None:
                try:
                    info["size_emu"] = (int(ext.get("cx") or 0), int(ext.get("cy") or 0))
                except ValueError:
                    pass
        return info
    return None


def _collect_tcfield_ids(slide_xml: bytes) -> list[str]:
    """Return the set of <a:fld id="..."> ids on a slide. think-cell encodes
    its data fields as datetime fields with embedded payload in the type
    attribute; we only return their ids for cross-reference.
    """
    try:
        root = etree.fromstring(slide_xml)
    except etree.XMLSyntaxError:
        return []
    ids: list[str] = []
    for fld in root.iter("{%s}fld" % NS_A):
        fid = fld.get("id") or ""
        if fid:
            ids.append(fid)
    return ids


def _emu_in(v: int) -> str:
    inches = v / EMU_PER_INCH
    if 0 < inches < 0.01:
        return f"{v}EMU"
    return f"{inches:.2f}in"


def build_inventory(pptx_path: Path, manifest_path: Path | None) -> Inventory:
    repo_root = _detect_repo_root(pptx_path)
    bindings_raw = _load_manifest(repo_root, manifest_path)

    inv = Inventory(pptx=str(pptx_path))

    bindings: list[BindingEntry] = []
    for b in bindings_raw:
        bindings.append(
            BindingEntry(
                name=b.get("name", ""),
                slide_hint=_slide_hint_from_binding(b.get("name", "")),
                function=b.get("function"),
                build_ppttc_line=b.get("build_ppttc_line"),
                excel_sheet=b.get("excel_sheet"),
                shape=b.get("shape"),
            )
        )
    inv.bindings = bindings

    binding_by_slide: dict[int, list[BindingEntry]] = {}
    for be in bindings:
        if be.slide_hint is not None:
            binding_by_slide.setdefault(be.slide_hint, []).append(be)

    with zipfile.ZipFile(pptx_path) as z:
        names = z.namelist()
        ole_parts: dict[str, int] = {}
        for n in names:
            m = OLE_PART_RE.match(n)
            if m:
                info = z.getinfo(n)
                ole_parts[m.group(1)] = info.file_size

        slide_nums = sorted((int(m.group(1)) for m in (SLIDE_PART_RE.match(n) for n in names) if m))

        anchors_by_part: dict[str, OleAnchor] = {}
        slide_ole_count: dict[int, int] = {}
        slide_tcfield_cache: dict[int, list[str]] = {}

        for slide_num in slide_nums:
            rels_name = f"ppt/slides/_rels/slide{slide_num}.xml.rels"
            slide_name = f"ppt/slides/slide{slide_num}.xml"
            if rels_name not in names or slide_name not in names:
                continue
            rels_xml = z.read(rels_name)
            slide_xml = z.read(slide_name)
            ole_rels = _parse_rels_for_ole(rels_xml)
            if not ole_rels:
                continue

            tc_ids = _collect_tcfield_ids(slide_xml)
            slide_tcfield_cache[slide_num] = tc_ids
            slide_ole_count[slide_num] = len(ole_rels)

            for rid, ole_filename in ole_rels:
                if ole_filename not in ole_parts:
                    continue
                meta = _parse_oleobj_in_slide(slide_xml, rid) or {}
                anchor = OleAnchor(
                    part=ole_filename,
                    size_bytes=ole_parts[ole_filename],
                    slide_num=slide_num,
                    slide_part=slide_name,
                    rel_id=rid,
                    cnvpr_id=meta.get("cnvpr_id"),
                    cnvpr_name=meta.get("cnvpr_name"),
                    oleobj_name=meta.get("oleobj_name"),
                    prog_id=meta.get("prog_id"),
                    pos_emu=meta.get("pos_emu"),
                    size_emu=meta.get("size_emu"),
                    binding=None,
                    binding_slide_hint=None,
                    tc_field_ids=tc_ids,
                )
                bound = binding_by_slide.get(slide_num, [])
                if len(bound) == 1:
                    anchor.binding = bound[0].name
                    anchor.binding_slide_hint = bound[0].slide_hint
                    bound[0].has_anchor = True
                    bound[0].anchor_part = ole_filename
                elif len(bound) > 1:
                    chart_bindings = [b for b in bound if (b.shape or "") in ("matrix", "table")]
                    if len(chart_bindings) == 1:
                        anchor.binding = chart_bindings[0].name
                        anchor.binding_slide_hint = chart_bindings[0].slide_hint
                        chart_bindings[0].has_anchor = True
                        chart_bindings[0].anchor_part = ole_filename
                        anchor.notes.append(
                            f"slide has {len(bound)} bindings; matched chart-shape={chart_bindings[0].name}"
                        )
                    else:
                        anchor.notes.append(f"slide has {len(bound)} bindings — manual review")
                else:
                    anchor.notes.append("no manifest binding for this slide number")
                anchors_by_part[ole_filename] = anchor

        for part, size in ole_parts.items():
            if part not in anchors_by_part:
                anchors_by_part[part] = OleAnchor(
                    part=part,
                    size_bytes=size,
                    slide_num=None,
                    slide_part=None,
                    rel_id=None,
                    cnvpr_id=None,
                    cnvpr_name=None,
                    oleobj_name=None,
                    prog_id=None,
                    pos_emu=None,
                    size_emu=None,
                    binding=None,
                    binding_slide_hint=None,
                    notes=["oleObject part is not referenced by any slide rels"],
                )

    inv.ole_anchors = sorted(
        anchors_by_part.values(),
        key=lambda a: (
            a.slide_num if a.slide_num is not None else 10**9,
            int(re.sub(r"\D", "", a.part) or "0"),
        ),
    )

    for a in inv.ole_anchors:
        if a.slide_num is None:
            inv.gaps.append(f"oleObject {a.part}: orphan — not referenced by any slide")
        elif a.binding is None:
            hint = (
                f"expected by SXX_<Name> convention near slide {a.slide_num}" if a.slide_num else ""
            )
            inv.gaps.append(f"oleObject {a.part} on slide {a.slide_num}: no binding match ({hint})")

    for be in inv.bindings:
        if be.shape in ("cell",) or be.name.endswith("_src"):
            continue
        if not be.has_anchor:
            inv.gaps.append(
                f"binding {be.name} (slide {be.slide_hint}): no oleObject anchor present"
            )

    for slide_num, count in slide_ole_count.items():
        if count > 1:
            parts = sorted(a.part for a in inv.ole_anchors if a.slide_num == slide_num)
            inv.oddities.append(f"slide {slide_num} has {count} oleObjects: {parts}")

    for a in inv.ole_anchors:
        if a.slide_num is None or a.binding is None:
            continue
        if a.binding_slide_hint is not None and a.binding_slide_hint != a.slide_num:
            inv.oddities.append(
                f"oleObject {a.part}: slide={a.slide_num} but binding "
                f"{a.binding} hints slide {a.binding_slide_hint}"
            )

    chartlike = [b for b in inv.bindings if not (b.shape == "cell" or b.name.endswith("_src"))]
    inv.summary = {
        "oleObjects_total": len(inv.ole_anchors),
        "oleObjects_bound": sum(1 for a in inv.ole_anchors if a.binding),
        "oleObjects_orphan": sum(1 for a in inv.ole_anchors if a.slide_num is None),
        "oleObjects_unbound": sum(
            1 for a in inv.ole_anchors if a.slide_num is not None and a.binding is None
        ),
        "bindings_total": len(inv.bindings),
        "bindings_chartlike": len(chartlike),
        "bindings_with_anchor": sum(1 for b in chartlike if b.has_anchor),
        "bindings_without_anchor": sum(1 for b in chartlike if not b.has_anchor),
    }
    return inv


def _detect_repo_root(pptx_path: Path) -> Path:
    """Walk up from the pptx until we find a folder containing scripts/ +
    state/. Falls back to the pptx's parent.
    """
    p = pptx_path.resolve().parent
    for _ in range(8):
        if (p / "scripts").is_dir() and (p / "state").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    return pptx_path.resolve().parent


def render_text(inv: Inventory) -> str:
    lines: list[str] = []
    pptx_name = Path(inv.pptx).name
    lines.append(
        f"== {pptx_name}  oleObjects={inv.summary['oleObjects_total']}  "
        f"bindings={inv.summary['bindings_total']}"
    )
    lines.append("")
    lines.append("OLEOBJECTS:")
    for a in inv.ole_anchors:
        slide = str(a.slide_num) if a.slide_num is not None else "?"
        binding = a.binding or "null"
        pos = f"({_emu_in(a.pos_emu[0])},{_emu_in(a.pos_emu[1])})" if a.pos_emu else "(?,?)"
        size = f"({_emu_in(a.size_emu[0])},{_emu_in(a.size_emu[1])})" if a.size_emu else "(?,?)"
        tcfield_count = len(a.tc_field_ids)
        flag = ""
        if a.slide_num is None:
            flag = "   <<< orphan"
        elif a.binding is None:
            flag = "   <<< no binding"
        lines.append(
            f"  {a.part:<18} {a.size_bytes:>8}b   slide={slide:<3} "
            f"binding={binding:<32} pos={pos}   size={size}   "
            f"tcfields={tcfield_count}{flag}"
        )
    lines.append("")
    lines.append("GAPS:")
    if inv.gaps:
        for g in inv.gaps:
            lines.append(f"  {g}")
    else:
        lines.append("  (none)")
    if inv.oddities:
        lines.append("")
        lines.append("ODDITIES:")
        for o in inv.oddities:
            lines.append(f"  {o}")
    lines.append("")
    s = inv.summary
    lines.append("SUMMARY:")
    lines.append(
        f"  oleObjects_total={s['oleObjects_total']}  "
        f"bound={s['oleObjects_bound']}  "
        f"orphan={s['oleObjects_orphan']}  "
        f"unbound_on_slide={s['oleObjects_unbound']}"
    )
    lines.append(
        f"  bindings_total={s['bindings_total']}  "
        f"chartlike={s['bindings_chartlike']}  "
        f"with_anchor={s['bindings_with_anchor']}  "
        f"without_anchor={s['bindings_without_anchor']}"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Inventory think-cell oleObject anchors in a .pptx and "
        "cross-reference against the deck-factory binding manifest.",
    )
    p.add_argument("pptx", type=Path)
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Override path to a binding_to_range_manifest.json. Default: "
        f"<repo>/{DEFAULT_MANIFEST_PATH} or fall back to "
        "scripts/add_chart_binding_named_ranges.py",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = p.parse_args(argv)

    if not args.pptx.is_file():
        sys.stderr.write(f"not a file: {args.pptx}\n")
        return 3

    try:
        inv = build_inventory(args.pptx, args.manifest)
    except (zipfile.BadZipFile, OSError) as e:
        sys.stderr.write(f"could not open pptx: {e}\n")
        return 3

    if args.json:
        sys.stdout.write(json.dumps(inv.to_dict(), indent=2))
        sys.stdout.write("\n")
    else:
        sys.stdout.write(render_text(inv))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
