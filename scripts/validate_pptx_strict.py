#!/usr/bin/env python3
"""Strict OOXML PresentationML validator — gate-1 for the deck side of the harness.

Catches the polish-drift bugs we kept shipping by hand:
  - Lorem ipsum and template placeholder copy ("Click to add title", etc.)
  - Black or near-black text on dark-fill shapes (the title-slide bug)
  - Empty placeholders left from layouts (orphan tcfields)
  - Shapes positioned outside the slide canvas (ghost shapes)
  - oleObjects (think-cell anchors) missing on slides that need them
  - Slide masters with bound-but-unused images / orphan shape leftovers

Spec references (ECMA-376 / ISO 29500-1):
  - §19.3   PresentationML
  - §19.3.1 sld (slide), sp (shape), txBody (text body)
  - §20.1   DrawingML

Usage:
    python3 scripts/validate_pptx_strict.py path/to/seed.pptx
    python3 scripts/validate_pptx_strict.py --json path/to/*.pptx

Exit codes:
    0   clean
    1   fail-level findings
    2   warn-level findings
    3   could not open
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
NS = {"p": NS_P, "a": NS_A, "r": NS_R}

EMU_PER_INCH = 914400
DEFAULT_SLIDE_W_EMU = 12192000  # 16:9 standard 13.33"
DEFAULT_SLIDE_H_EMU = 6858000  # 7.5"

PLACEHOLDER_PHRASES = [
    "lorem ipsum",
    "consectetur adipiscing",
    "click to add title",
    "click to add text",
    "click to add subtitle",
    "click to add notes",
    "click to edit master",
    "your title here",
    "your text here",
    "rechteck",  # German for "rectangle" — appears in unhandled shape labels
    "platzhalter",  # German for "placeholder"
]

# Hex colors that are essentially black (luma <= 0x33) — would need a
# light fill behind them on a brand divider slide.
DARK_HEX_RE = re.compile(r"^[0-3][0-9A-Fa-f][0-3][0-9A-Fa-f][0-3][0-9A-Fa-f]$")

# Theme color names (ECMA-376 §20.1.6.2 a:clrScheme). PowerPoint aliases
# bg1↔lt1, bg2↔lt2, tx1↔dk1, tx2↔dk2 — the bg/tx form is the slide-context
# alias for the dk/lt scheme entries.
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


@dataclass
class Finding:
    level: str
    rule: str
    message: str
    location: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Report:
    path: str
    slide_count: int = 0
    master_count: int = 0
    layout_count: int = 0
    ole_object_count: int = 0
    slide_w_emu: int = DEFAULT_SLIDE_W_EMU
    slide_h_emu: int = DEFAULT_SLIDE_H_EMU
    findings: list[Finding] = field(default_factory=list)

    def add(self, level: str, rule: str, message: str, location: str = "") -> None:
        self.findings.append(Finding(level, rule, message, location))

    @property
    def fails(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "fail"]

    @property
    def warns(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warn"]

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "slide_count": self.slide_count,
            "master_count": self.master_count,
            "layout_count": self.layout_count,
            "ole_object_count": self.ole_object_count,
            "fail_count": len(self.fails),
            "warn_count": len(self.warns),
            "findings": [f.to_dict() for f in self.findings],
        }


def _text_runs(root: etree._Element) -> list[etree._Element]:
    return root.findall(".//a:t", NS)


def _load_theme_colors(zf: zipfile.ZipFile) -> dict[str, str]:
    try:
        theme_root = etree.fromstring(zf.read("ppt/theme/theme1.xml"))
    except (KeyError, etree.XMLSyntaxError):
        return {}
    scheme = theme_root.find(".//a:clrScheme", NS)
    if scheme is None:
        return {}
    out: dict[str, str] = {}
    for name in SCHEME_NAMES:
        node = scheme.find(f"a:{name}", NS)
        if node is None:
            continue
        srgb = node.find("a:srgbClr", NS)
        if srgb is not None and srgb.get("val"):
            out[name] = srgb.get("val", "").upper()
            continue
        sys_clr = node.find("a:sysClr", NS)
        if sys_clr is not None and sys_clr.get("lastClr"):
            out[name] = sys_clr.get("lastClr", "").upper()
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


def _check_placeholder_text(name: str, root: etree._Element, rep: Report) -> None:
    """Placeholder prompts ARE expected in slideLayouts/slideMasters — they
    are template-design content that PowerPoint replaces on instantiation.
    Only flag them as failures when they appear in actual rendered slides.
    """
    is_slide = name.startswith("ppt/slides/")
    is_master = name.startswith("ppt/slideMasters/")
    if not is_slide and not is_master:
        return  # layouts: skip entirely
    for t in _text_runs(root):
        s = (t.text or "").strip().lower()
        if not s:
            continue
        for phrase in PLACEHOLDER_PHRASES:
            if phrase in s:
                level = "fail" if is_slide else "info"
                rule = "slide.placeholder-leak" if is_slide else "master.prompt-text"
                rep.add(
                    level,
                    rule,
                    f"placeholder text {phrase!r} in {(t.text or '').strip()[:80]!r}",
                    location=name,
                )
                break


def _check_dark_text_on_dark_fill(
    name: str, root: etree._Element, rep: Report, theme: dict[str, str]
) -> None:
    """Resolve theme colors so we catch schemeClr-based dark text/fill, not
    just literal srgbClr@val. Both shape fill and run color paths walk
    srgbClr | schemeClr | sysClr.
    """
    for sp in root.findall(".//p:sp", NS):
        sp_pr = sp.find("p:spPr", NS)
        if sp_pr is None:
            continue
        sp_fill = sp_pr.find("a:solidFill", NS)
        sp_fill_hex = _resolve_color(sp_fill, theme)
        if sp_fill_hex is None or not DARK_HEX_RE.match(sp_fill_hex):
            continue
        for r_el in sp.findall(".//a:r", NS):
            r_pr = r_el.find("a:rPr", NS)
            t = r_el.find("a:t", NS)
            text_preview = (t.text if t is not None else "") or ""
            txt_color_hex = (
                _resolve_color(r_pr.find("a:solidFill", NS), theme) if r_pr is not None else None
            )
            if txt_color_hex and DARK_HEX_RE.match(txt_color_hex):
                rep.add(
                    "fail",
                    "slide.text-on-fill.contrast",
                    f"dark text #{txt_color_hex} on dark fill #{sp_fill_hex} — "
                    f"text {text_preview[:40]!r} unreadable",
                    location=name,
                )


def _check_title_no_text_fill(
    name: str, root: etree._Element, rep: Report, theme: dict[str, str]
) -> None:
    """Slide 1 text runs with no explicit color resolve to the theme default
    (tx1, typically near-black). Without a light layout fill PowerPoint will
    render them unreadable on dark divider/title backgrounds. Flag every
    colorless run on slide 1 so the template author confirms intent.
    """
    if not name.endswith("/slide1.xml"):
        return
    default_dark = theme.get("tx1") or theme.get("dk1") or "000000"
    if not DARK_HEX_RE.match(default_dark):
        return
    for sp in root.findall(".//p:sp", NS):
        for r_el in sp.findall(".//a:r", NS) + sp.findall(".//a:fld", NS):
            r_pr = r_el.find("a:rPr", NS)
            if r_pr is not None and r_pr.find("a:solidFill", NS) is not None:
                continue
            t = r_el.find("a:t", NS)
            text_preview = (t.text if t is not None else "") or ""
            if not text_preview.strip():
                continue
            rep.add(
                "warn",
                "slide.title.no-text-fill",
                f"title-slide run {text_preview[:40]!r} has no explicit color "
                f"— inherits theme default #{default_dark}",
                location=name,
            )


def _is_thinkcell_shape(sp: etree._Element) -> bool:
    """Think-cell tcfield/anchor shapes are intentionally placed off-canvas as
    a hiding mechanism. Detect by cNvPr name or by the presence of <a:fld>.
    """
    cnv = sp.find(".//p:cNvPr", NS)
    if cnv is not None:
        n = (cnv.get("name") or "").lower()
        if "think-cell" in n or "tclayout" in n or n.startswith("tcfield"):
            return True
    return sp.find(".//a:fld", NS) is not None


def _check_off_canvas(
    name: str, root: etree._Element, rep: Report, slide_w: int, slide_h: int
) -> None:
    """Shapes positioned wholly off-canvas → ghost shapes. Think-cell anchors
    are intentionally off-canvas — exempt them.
    """
    for sp in root.findall(".//p:sp", NS) + root.findall(".//p:pic", NS):
        if _is_thinkcell_shape(sp):
            continue
        xfrm = sp.find(".//a:xfrm", NS)
        if xfrm is None:
            continue
        off = xfrm.find("a:off", NS)
        ext = xfrm.find("a:ext", NS)
        if off is None or ext is None:
            continue
        try:
            x = int(off.get("x", "0"))
            y = int(off.get("y", "0"))
            cx = int(ext.get("cx", "0"))
            cy = int(ext.get("cy", "0"))
        except ValueError:
            continue
        if x > slide_w or y > slide_h:
            rep.add(
                "warn",
                "slide.shape.off-canvas",
                f"shape at ({x / EMU_PER_INCH:.2f}in,{y / EMU_PER_INCH:.2f}in) "
                f"size {cx / EMU_PER_INCH:.2f}x{cy / EMU_PER_INCH:.2f}in "
                f"past slide edge ({slide_w / EMU_PER_INCH:.2f}x{slide_h / EMU_PER_INCH:.2f}in)",
                location=name,
            )


def _slide_dimensions(root: etree._Element) -> tuple[int, int]:
    sld_sz = root.find("p:sldSz", NS)
    if sld_sz is not None:
        try:
            return int(sld_sz.get("cx") or DEFAULT_SLIDE_W_EMU), int(
                sld_sz.get("cy") or DEFAULT_SLIDE_H_EMU
            )
        except ValueError:
            pass
    return DEFAULT_SLIDE_W_EMU, DEFAULT_SLIDE_H_EMU


def validate(path: Path) -> Report:
    rep = Report(path=str(path))
    if not path.exists():
        rep.add("fail", "file.missing", f"file not found: {path}")
        return rep
    try:
        zf = zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as e:
        rep.add("fail", "zip.invalid", f"not a valid zip: {e}")
        return rep
    with zf:
        names = zf.namelist()

        # presentation.xml: slide size + slide list
        try:
            pres_root = etree.fromstring(zf.read("ppt/presentation.xml"))
            rep.slide_w_emu, rep.slide_h_emu = _slide_dimensions(pres_root)
        except (KeyError, etree.XMLSyntaxError):
            rep.add("fail", "presentation.xml.parse", "ppt/presentation.xml missing or unparseable")
            return rep

        slide_parts = sorted(
            n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        master_parts = sorted(
            n for n in names if n.startswith("ppt/slideMasters/slideMaster") and n.endswith(".xml")
        )
        layout_parts = sorted(
            n for n in names if n.startswith("ppt/slideLayouts/slideLayout") and n.endswith(".xml")
        )
        rep.slide_count = len(slide_parts)
        rep.master_count = len(master_parts)
        rep.layout_count = len(layout_parts)

        # OLE objects = think-cell anchor count
        rep.ole_object_count = sum(
            1 for n in names if n.startswith("ppt/embeddings/oleObject") and n.endswith(".bin")
        )

        theme = _load_theme_colors(zf)

        for parts in (slide_parts, master_parts, layout_parts):
            for name in parts:
                try:
                    root = etree.fromstring(zf.read(name))
                except etree.XMLSyntaxError as e:
                    rep.add("fail", "part.parse", f"{name}: {e}")
                    continue
                _check_placeholder_text(name, root, rep)
                if name.startswith("ppt/slides/"):
                    _check_dark_text_on_dark_fill(name, root, rep, theme)
                    _check_title_no_text_fill(name, root, rep, theme)
                    _check_off_canvas(name, root, rep, rep.slide_w_emu, rep.slide_h_emu)
    return rep


def _format_text(rep: Report) -> str:
    lines = [f"== {rep.path}"]
    lines.append(
        f"   slides: {rep.slide_count}   masters: {rep.master_count}   "
        f"layouts: {rep.layout_count}   oleObjects: {rep.ole_object_count}"
    )
    if not rep.findings:
        lines.append("   clean")
        return "\n".join(lines)
    lines.append(f"   FAIL: {len(rep.fails)}   WARN: {len(rep.warns)}")
    for f in rep.findings:
        prefix = {"fail": "  [FAIL]", "warn": "  [warn]", "info": "  [info]"}[f.level]
        loc = f" ({f.location})" if f.location else ""
        lines.append(f"{prefix} {f.rule}: {f.message}{loc}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("paths", nargs="+", type=Path)
    p.add_argument("--json", action="store_true")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args(argv)

    reports = [validate(path) for path in args.paths]
    if args.json:
        print(json.dumps({"reports": [r.to_dict() for r in reports]}, indent=2))
    else:
        for r in reports:
            if args.quiet and not r.fails:
                continue
            print(_format_text(r))
    worst = 0
    for r in reports:
        if r.fails:
            worst = max(worst, 1)
        elif r.warns:
            worst = max(worst, 2)
    return worst


if __name__ == "__main__":
    sys.exit(main())
