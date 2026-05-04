#!/usr/bin/env python3
"""Audit per-slide think-cell anchor wiring — gate-5 of the deck-factory harness.

Companion to validate_pptx_strict.py (lint), inventory_pptx_thinkcell.py
(count + map), diff_oxml.py, visual_review_pptx.py (vision), and
vm/roundtrip_pptx_openxmlsdk.ps1 (SDK validation).

Where the inventory tool reports *what* anchors exist and *which* slide they
sit on, this auditor verifies every anchor is *internally consistent* after
injection: chart-pair, exact-once shape reference, on-canvas position,
binding match in the manifest, ECMA-376 §A.2 GUID casing in <a:fld id>,
fld id uniqueness within chart and within slide, and cNvPr name conformance.

The motivating bug: the SDK pptx oracle surfaced lowercase GUIDs in
<a:fld id="..."> on slides 26/27 (e.g. {3d9aaf61-2f34-46d4-88b5-bec854bc4703}).
ECMA-376 §A.2 requires brace-wrapped uppercase hex; lowercase is the
class of drift that triggers PowerPoint's open-repair-close pass.

Exit codes:  0 clean / 1 fail-level / 2 warn-only / 3 could-not-open.
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
NS_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"p": NS_P, "a": NS_A, "r": NS_R, "pr": NS_PKG}

REL_OLE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject"
REL_CHART = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart"

DEFAULT_SLIDE_W_EMU = 12192000
DEFAULT_SLIDE_H_EMU = 6858000

SLIDE_PART_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
OLE_PART_RE = re.compile(r"^ppt/embeddings/(oleObject\d+\.bin)$")
CHART_PART_RE = re.compile(r"^ppt/charts/(chart\d+\.xml)$")
OLE_TARGET_RE = re.compile(r"embeddings/(oleObject\d+\.bin)$")
CHART_TARGET_RE = re.compile(r"charts/(chart\d+\.xml)$")
GUID_UPPER_RE = re.compile(r"^\{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}\}$")

THINKCELL_CNVPR_NAME = "think-cell data - do not delete"
THINKCELL_PROGID = "TCLayout.ActiveDocument.1"

DEFAULT_MANIFEST_PATH = (
    "state/thinkcell_bridge/excel_named_ranges/20260504T000502Z/binding_to_range_manifest.json"
)

SEV_FAIL, SEV_WARN, SEV_INFO = "fail", "warn", "info"
SEV_RANK = {SEV_FAIL: 3, SEV_WARN: 2, SEV_INFO: 1}

FIX_UPPERCASE_GUID = (
    "uppercase the GUID per ECMA-376 §A.2: "
    "{[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}}. "
    "lowercase IDs trigger PowerPoint's repair pass."
)


@dataclass
class Finding:
    rule: str
    severity: str
    location: str
    message: str
    fix_hint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SlideUnit:
    slide_num: int
    slide_part: str
    ole_part: str | None = None
    chart_part: str | None = None
    binding: str | None = None
    binding_resolved: bool = False
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["findings"] = [f.to_dict() for f in self.findings]
        return d

    def emit(
        self, rule: str, severity: str, location: str, message: str, fix_hint: str = ""
    ) -> None:
        self.findings.append(Finding(rule, severity, location, message, fix_hint))


@dataclass
class AuditReport:
    pptx: str
    slide_units: list[SlideUnit] = field(default_factory=list)
    extra_findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pptx": self.pptx,
            "slide_units": [u.to_dict() for u in self.slide_units],
            "extra_findings": [f.to_dict() for f in self.extra_findings],
            "summary": self.summary,
        }

    def all_findings(self) -> list[Finding]:
        out: list[Finding] = [f for u in self.slide_units for f in u.findings]
        out.extend(self.extra_findings)
        return out


def _detect_repo_root(pptx_path: Path) -> Path:
    p = pptx_path.resolve().parent
    for _ in range(8):
        if (p / "scripts").is_dir() and (p / "state").is_dir():
            return p
        if p.parent == p:
            break
        p = p.parent
    return pptx_path.resolve().parent


def _load_manifest_names(repo_root: Path, override_path: Path | None) -> set[str]:
    """Binding names from the manifest. JSON snapshot preferred; fall back to
    importing _BINDING_TO_RANGE_MANIFEST from add_chart_binding_named_ranges.py.
    """
    if override_path is not None:
        with override_path.open() as f:
            return {b.get("name", "") for b in json.load(f).get("bindings", []) if b.get("name")}
    json_path = repo_root / DEFAULT_MANIFEST_PATH
    if json_path.is_file():
        with json_path.open() as f:
            names = {b.get("name", "") for b in json.load(f).get("bindings", []) if b.get("name")}
        if names:
            return names
    py_path = repo_root / "scripts" / "add_chart_binding_named_ranges.py"
    if not py_path.is_file():
        return set()
    spec_globals: dict[str, Any] = {"__name__": "_audit_loader", "__file__": str(py_path)}
    src = py_path.read_text()
    cut = src.find("\ndef ", src.find("_BINDING_TO_RANGE_MANIFEST"))
    exec(compile(src[: cut if cut >= 0 else len(src)], str(py_path), "exec"), spec_globals)
    raw = spec_globals.get("_BINDING_TO_RANGE_MANIFEST", [])
    return {b.get("name", "") for b in raw if b.get("name")}


def _read_slide_size(zf: zipfile.ZipFile) -> tuple[int, int]:
    try:
        root = etree.fromstring(zf.read("ppt/presentation.xml"))
    except (KeyError, etree.XMLSyntaxError):
        return (DEFAULT_SLIDE_W_EMU, DEFAULT_SLIDE_H_EMU)
    sld = root.find("p:sldSz", NS)
    if sld is None:
        return (DEFAULT_SLIDE_W_EMU, DEFAULT_SLIDE_H_EMU)
    try:
        return (
            int(sld.get("cx") or DEFAULT_SLIDE_W_EMU),
            int(sld.get("cy") or DEFAULT_SLIDE_H_EMU),
        )
    except ValueError:
        return (DEFAULT_SLIDE_W_EMU, DEFAULT_SLIDE_H_EMU)


def _parse_slide_rels(rels_xml: bytes) -> dict[str, dict[str, str]]:
    """{rId: {type, target_filename}} for ole + chart relationships."""
    try:
        root = etree.fromstring(rels_xml)
    except etree.XMLSyntaxError:
        return {}
    out: dict[str, dict[str, str]] = {}
    for rel in root.iter("{%s}Relationship" % NS_PKG):
        rtype = rel.get("Type") or ""
        rid = rel.get("Id") or ""
        target = rel.get("Target") or ""
        if rtype == REL_OLE:
            m = OLE_TARGET_RE.search(target)
            if m:
                out[rid] = {"type": "ole", "target": m.group(1)}
        elif rtype == REL_CHART:
            m = CHART_TARGET_RE.search(target)
            if m:
                out[rid] = {"type": "chart", "target": m.group(1)}
    return out


@dataclass
class _SlideShapeMeta:
    ole_refs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    fld_ids: list[tuple[str, str]] = field(default_factory=list)


def _parse_slide_shapes(slide_xml: bytes) -> _SlideShapeMeta:
    """Walk a slide once: capture <p:oleObj> refs (de-duped per graphicFrame —
    mc:Choice + mc:Fallback wrap two siblings under one frame) and every
    <a:fld id>.
    """
    meta = _SlideShapeMeta()
    try:
        root = etree.fromstring(slide_xml)
    except etree.XMLSyntaxError:
        return meta

    seen_gf: dict[str, set[int]] = {}
    for ole in root.iter("{%s}oleObj" % NS_P):
        rid = ole.get("{%s}id" % NS_R) or ""
        if not rid:
            continue
        gf = None
        cur = ole
        for _ in range(8):
            cur = cur.getparent()
            if cur is None:
                break
            if cur.tag == "{%s}graphicFrame" % NS_P:
                gf = cur
                break
        if gf is not None:
            key = id(gf)
            if key in seen_gf.get(rid, set()):
                continue
            seen_gf.setdefault(rid, set()).add(key)
        info: dict[str, Any] = {
            "prog_id": ole.get("progId"),
            "oleobj_name": ole.get("name"),
            "cnvpr_name": None,
            "cnvpr_id": None,
            "pos_emu": None,
            "size_emu": None,
        }
        if gf is not None:
            cnv = gf.find("p:nvGraphicFramePr/p:cNvPr", NS)
            if cnv is not None:
                info["cnvpr_name"] = cnv.get("name")
                info["cnvpr_id"] = cnv.get("id")
            xfm = gf.find("p:xfrm", NS)
            if xfm is not None:
                off = xfm.find("a:off", NS)
                ext = xfm.find("a:ext", NS)
                try:
                    if off is not None:
                        info["pos_emu"] = (int(off.get("x") or 0), int(off.get("y") or 0))
                    if ext is not None:
                        info["size_emu"] = (int(ext.get("cx") or 0), int(ext.get("cy") or 0))
                except ValueError:
                    pass
        meta.ole_refs.setdefault(rid, []).append(info)

    for fld in root.iter("{%s}fld" % NS_A):
        fid = fld.get("id") or ""
        if fid:
            meta.fld_ids.append((fid, "slide-body"))
    return meta


def _collect_chart_fld_ids(chart_xml: bytes) -> list[str]:
    try:
        root = etree.fromstring(chart_xml)
    except etree.XMLSyntaxError:
        return []
    return [fld.get("id") or "" for fld in root.iter("{%s}fld" % NS_A) if fld.get("id")]


def _on_canvas(
    pos: tuple[int, int] | None, size: tuple[int, int] | None, canvas_w: int, canvas_h: int
) -> tuple[bool, str]:
    if pos is None or size is None:
        return False, "missing xfrm/ext"
    x, y = pos
    cx, cy = size
    if x < 0 or y < 0:
        return False, f"negative offset x={x} y={y}"
    if cx <= 0 or cy <= 0:
        return False, f"non-positive extent cx={cx} cy={cy}"
    if x + cx > canvas_w:
        return False, f"frame extends past canvas: x+cx={x + cx} > {canvas_w}"
    if y + cy > canvas_h:
        return False, f"frame extends past canvas: y+cy={y + cy} > {canvas_h}"
    return True, "ok"


def _short_guid_list(ids: list[str], cap: int = 3) -> str:
    return ", ".join(ids[:cap]) + (f", ... ({len(ids) - cap} more)" if len(ids) > cap else "")


def audit(pptx_path: Path, manifest_override: Path | None) -> AuditReport:
    repo_root = _detect_repo_root(pptx_path)
    manifest_names = _load_manifest_names(repo_root, manifest_override)
    report = AuditReport(pptx=str(pptx_path))

    with zipfile.ZipFile(pptx_path) as z:
        names = z.namelist()
        canvas_w, canvas_h = _read_slide_size(z)
        ole_parts = {m.group(1): n for n in names for m in [OLE_PART_RE.match(n)] if m}
        chart_parts = {m.group(1): n for n in names for m in [CHART_PART_RE.match(n)] if m}
        slide_nums = sorted(int(m.group(1)) for n in names for m in [SLIDE_PART_RE.match(n)] if m)

        ole_used: set[str] = set()
        for slide_num in slide_nums:
            slide_part = f"ppt/slides/slide{slide_num}.xml"
            rels_part = f"ppt/slides/_rels/slide{slide_num}.xml.rels"
            if slide_part not in names or rels_part not in names:
                continue
            rels = _parse_slide_rels(z.read(rels_part))
            ole_rels = {rid: r["target"] for rid, r in rels.items() if r["type"] == "ole"}
            chart_rels = {rid: r["target"] for rid, r in rels.items() if r["type"] == "chart"}
            if not ole_rels:
                continue
            shape_meta = _parse_slide_shapes(z.read(slide_part))

            for rid, ole_filename in ole_rels.items():
                ole_used.add(ole_filename)
                chart_filename = next(iter(chart_rels.values()), None)
                expected_prefix = f"S{slide_num:02d}_"
                slide_binding = next(
                    (n for n in sorted(manifest_names) if n.startswith(expected_prefix)), None
                )
                unit = SlideUnit(
                    slide_num=slide_num,
                    slide_part=slide_part,
                    ole_part=ole_filename,
                    chart_part=chart_filename,
                    binding=slide_binding,
                    binding_resolved=slide_binding is not None,
                )
                _check_anchor_has_chart_pair(unit, chart_rels, ole_filename)
                _check_anchor_referenced_once(unit, shape_meta, rid, ole_filename)
                _check_anchor_position_on_canvas(unit, shape_meta, rid, canvas_w, canvas_h)
                _check_anchor_binding_recoverable(unit, manifest_names, expected_prefix)
                _check_anchor_cnvpr_name(unit, shape_meta, rid)

                chart_fld_ids: list[str] = []
                if chart_filename and chart_filename in chart_parts:
                    chart_fld_ids = _collect_chart_fld_ids(z.read(chart_parts[chart_filename]))
                    _check_chart_fld_ids_unique(unit, chart_fld_ids, chart_filename)
                    for fid in chart_fld_ids:
                        shape_meta.fld_ids.append((fid, f"chart:{chart_filename}"))

                _check_chart_fld_ids_uppercase(unit, shape_meta.fld_ids, chart_filename)
                _check_slide_fld_ids_unique(unit, shape_meta.fld_ids)
                report.slide_units.append(unit)

        # Slides with no anchor but with lowercase fld IDs (e.g. seed slides 26/27).
        for slide_num in slide_nums:
            if any(u.slide_num == slide_num for u in report.slide_units):
                continue
            slide_part = f"ppt/slides/slide{slide_num}.xml"
            if slide_part not in names:
                continue
            extra = _parse_slide_shapes(z.read(slide_part))
            if not extra.fld_ids:
                continue
            bad = [fid for fid, _src in extra.fld_ids if not GUID_UPPER_RE.match(fid)]
            if bad:
                report.extra_findings.append(
                    Finding(
                        rule="chart.fld-ids-uppercase",
                        severity=SEV_FAIL,
                        location=f"slide {slide_num} (no anchor)",
                        message=(
                            f"{len(bad)} of {len(extra.fld_ids)} fld ids violate uppercase "
                            f"GUID pattern: {_short_guid_list(bad)}"
                        ),
                        fix_hint=FIX_UPPERCASE_GUID,
                    )
                )

        for ole_part in sorted(ole_parts):
            if ole_part not in ole_used:
                report.extra_findings.append(
                    Finding(
                        rule="anchor.has-chart-pair",
                        severity=SEV_FAIL,
                        location=f"ppt/embeddings/{ole_part}",
                        message=f"oleObject {ole_part} is not referenced by any slide rels (orphan)",
                        fix_hint="remove the orphan part or wire it to a slide via _rels.",
                    )
                )

    counts = {SEV_FAIL: 0, SEV_WARN: 0, SEV_INFO: 0}
    by_rule: dict[str, int] = {}
    for f in report.all_findings():
        counts[f.severity] = counts.get(f.severity, 0) + 1
        by_rule[f.rule] = by_rule.get(f.rule, 0) + 1
    report.summary = {
        "anchors_audited": len(report.slide_units),
        "ole_parts_total": len(ole_parts),
        "chart_parts_total": len(chart_parts),
        "slides_total": len(slide_nums),
        "fail": counts[SEV_FAIL],
        "warn": counts[SEV_WARN],
        "info": counts[SEV_INFO],
        "by_rule": by_rule,
        "canvas_emu": [canvas_w, canvas_h],
    }
    return report


def _check_anchor_has_chart_pair(
    unit: SlideUnit, chart_rels: dict[str, str], ole_filename: str
) -> None:
    loc = f"slide {unit.slide_num} :: {ole_filename}"
    if not chart_rels:
        unit.emit(
            "anchor.has-chart-pair",
            SEV_FAIL,
            loc,
            "oleObject anchor has no paired chart{i}.xml part referenced from this slide",
            "add a relationship of type .../relationships/chart pointing at "
            "ppt/charts/chartN.xml in the slide's _rels.",
        )
    else:
        unit.emit("anchor.has-chart-pair", SEV_INFO, loc, f"paired with {unit.chart_part}")


def _check_anchor_referenced_once(
    unit: SlideUnit, shape_meta: _SlideShapeMeta, rid: str, ole_filename: str
) -> None:
    loc = f"slide {unit.slide_num} :: {ole_filename}"
    n = len(shape_meta.ole_refs.get(rid, []))
    if n == 0:
        unit.emit(
            "anchor.referenced-once",
            SEV_FAIL,
            loc,
            f"rId {rid} declares oleObject but no <p:oleObj> on the slide references it",
            f"ensure a graphicFrame/AlternateContent/Choice/oleObj exists with r:id={rid}",
        )
    elif n > 1:
        unit.emit(
            "anchor.referenced-once",
            SEV_FAIL,
            loc,
            f"oleObject rId {rid} is referenced {n} times on the slide",
            "deduplicate p:oleObj references; one ole anchor must have exactly one shape.",
        )
    else:
        unit.emit("anchor.referenced-once", SEV_INFO, loc, "oleObject referenced exactly once")


def _check_anchor_position_on_canvas(
    unit: SlideUnit, shape_meta: _SlideShapeMeta, rid: str, canvas_w: int, canvas_h: int
) -> None:
    refs = shape_meta.ole_refs.get(rid, [])
    if not refs:
        return
    info = refs[0]
    loc = f"slide {unit.slide_num} :: {unit.ole_part}"
    ok, why = _on_canvas(info.get("pos_emu"), info.get("size_emu"), canvas_w, canvas_h)
    if ok:
        unit.emit("anchor.position-on-canvas", SEV_INFO, loc, "anchor inside canvas")
    else:
        unit.emit(
            "anchor.position-on-canvas",
            SEV_WARN,
            loc,
            f"anchor off-canvas: {why} (canvas {canvas_w}x{canvas_h} EMU)",
            "adjust p:graphicFrame/p:xfrm/a:off + a:ext so the frame fits inside p:sldSz.",
        )


def _check_anchor_binding_recoverable(
    unit: SlideUnit, manifest_names: set[str], expected_prefix: str
) -> None:
    loc = f"slide {unit.slide_num} :: {unit.ole_part}"
    if not manifest_names:
        unit.emit(
            "anchor.binding-recoverable",
            SEV_INFO,
            loc,
            "manifest unavailable; skipping binding lookup",
        )
        return
    matches = sorted(n for n in manifest_names if n.startswith(expected_prefix))
    if not matches:
        unit.emit(
            "anchor.binding-recoverable",
            SEV_INFO,
            loc,
            f"no manifest binding starts with {expected_prefix}",
            "confirm slide number convention; rename binding or correct the slide layout.",
        )
    elif len(matches) > 1:
        unit.emit(
            "anchor.binding-recoverable",
            SEV_INFO,
            loc,
            f"multiple manifest bindings match {expected_prefix}: {matches}",
        )
    else:
        unit.emit("anchor.binding-recoverable", SEV_INFO, loc, f"binding {matches[0]} resolves")


def _check_anchor_cnvpr_name(unit: SlideUnit, shape_meta: _SlideShapeMeta, rid: str) -> None:
    refs = shape_meta.ole_refs.get(rid, [])
    if not refs:
        return
    info = refs[0]
    name, prog = info.get("cnvpr_name") or "", info.get("prog_id") or ""
    loc = f"slide {unit.slide_num} :: {unit.ole_part}"
    if name == THINKCELL_CNVPR_NAME and prog == THINKCELL_PROGID:
        unit.emit("anchor.cnvpr-name-consistent", SEV_INFO, loc, f"cNvPr={name!r} progId={prog!r}")
    else:
        unit.emit(
            "anchor.cnvpr-name-consistent",
            SEV_INFO,
            loc,
            f"unusual think-cell anchor metadata: cNvPr={name!r} progId={prog!r} "
            f"(expected name={THINKCELL_CNVPR_NAME!r} progId={THINKCELL_PROGID!r})",
            "manual review; non-conforming anchors usually mean a non-think-cell ole part.",
        )


def _check_chart_fld_ids_uppercase(
    unit: SlideUnit, fld_ids: list[tuple[str, str]], chart_filename: str | None
) -> None:
    if not fld_ids:
        return
    bad = [(fid, src) for fid, src in fld_ids if not GUID_UPPER_RE.match(fid)]
    target = f"slide {unit.slide_num}" + (f" / chart {chart_filename}" if chart_filename else "")
    if not bad:
        unit.emit(
            "chart.fld-ids-uppercase",
            SEV_INFO,
            target,
            f"all {len(fld_ids)} fld ids match ECMA-376 §A.2 uppercase pattern",
        )
        return
    breakdown: dict[str, int] = {}
    for _fid, src in bad:
        breakdown[src] = breakdown.get(src, 0) + 1
    unit.emit(
        "chart.fld-ids-uppercase",
        SEV_FAIL,
        target,
        f"{len(bad)} of {len(fld_ids)} fld ids violate uppercase GUID pattern "
        f"({', '.join(f'{s}={n}' for s, n in sorted(breakdown.items()))}): "
        f"{_short_guid_list([fid for fid, _ in bad])}",
        FIX_UPPERCASE_GUID,
    )


def _check_chart_fld_ids_unique(
    unit: SlideUnit, chart_fld_ids: list[str], chart_filename: str
) -> None:
    if not chart_fld_ids:
        return
    seen: dict[str, int] = {}
    for fid in chart_fld_ids:
        seen[fid] = seen.get(fid, 0) + 1
    dups = sorted(fid for fid, n in seen.items() if n > 1)
    loc = f"chart {chart_filename}"
    if not dups:
        unit.emit("chart.fld-ids-unique", SEV_INFO, loc, f"all {len(chart_fld_ids)} fld ids unique")
    else:
        unit.emit(
            "chart.fld-ids-unique",
            SEV_FAIL,
            loc,
            f"duplicate fld ids in chart: {_short_guid_list(dups)}",
            "regenerate or remap fld ids so each is unique within the chart part.",
        )


def _check_slide_fld_ids_unique(unit: SlideUnit, fld_ids: list[tuple[str, str]]) -> None:
    if not fld_ids:
        return
    by_id: dict[str, list[str]] = {}
    for fid, src in fld_ids:
        by_id.setdefault(fid, []).append(src)
    dups = {fid: srcs for fid, srcs in by_id.items() if len(srcs) > 1}
    loc = f"slide {unit.slide_num}"
    if not dups:
        unit.emit(
            "slide.fld-ids-unique-within-slide",
            SEV_INFO,
            loc,
            f"all {len(fld_ids)} fld ids unique across slide+chart",
        )
    else:
        unit.emit(
            "slide.fld-ids-unique-within-slide",
            SEV_FAIL,
            loc,
            f"{len(dups)} duplicate fld id(s) across slide+chart: {_short_guid_list(sorted(dups))}",
            "duplicate IDs cause think-cell to substitute the wrong field; remap one side.",
        )


_RULES_PER_UNIT = (
    "anchor.has-chart-pair",
    "anchor.referenced-once",
    "anchor.position-on-canvas",
    "anchor.binding-recoverable",
    "chart.fld-ids-uppercase",
    "chart.fld-ids-unique",
    "slide.fld-ids-unique-within-slide",
    "anchor.cnvpr-name-consistent",
)


def render_text(report: AuditReport, quiet: bool) -> str:
    s = report.summary
    lines: list[str] = [
        f"== {Path(report.pptx).name}  oleObjects={s.get('ole_parts_total', 0)}  "
        f"charts={s.get('chart_parts_total', 0)}  slides={s.get('slides_total', 0)}",
        "",
    ]
    for unit in report.slide_units:
        unit_failed = any(f.severity == SEV_FAIL for f in unit.findings)
        if quiet and not unit_failed:
            continue
        lines.append(
            f"SLIDE {unit.slide_num:>2}   binding={unit.binding or '?':<24}  "
            f"oleObject={unit.ole_part}  chart={unit.chart_part or '?'}"
        )
        by_rule: dict[str, list[Finding]] = {}
        for f in unit.findings:
            by_rule.setdefault(f.rule, []).append(f)
        for rule in _RULES_PER_UNIT:
            findings = by_rule.get(rule, [])
            if not findings:
                continue
            top = max(findings, key=lambda f: SEV_RANK.get(f.severity, 0))
            passed = top.severity == SEV_INFO
            if quiet and passed:
                continue
            mark = "[OK]  " if passed else f"[{top.severity.upper()}]"
            lines.append(f"  {mark} {rule}  {top.message}")
        lines.append("")
    if report.extra_findings:
        lines.append("EXTRA:")
        for f in report.extra_findings:
            lines.append(f"  [{f.severity.upper()}] {f.rule}  {f.location}  {f.message}")
        lines.append("")
    lines.append("SUMMARY")
    lines.append(
        f"  fail={s.get('fail', 0)}  warn={s.get('warn', 0)}  info={s.get('info', 0)}  "
        f"anchors_audited={s.get('anchors_audited', 0)}"
    )
    failed_rules = {
        r: c
        for r, c in s.get("by_rule", {}).items()
        if any(f.rule == r and f.severity != SEV_INFO for f in report.all_findings())
    }
    if failed_rules:
        lines.append(
            "  rules with non-info findings: "
            + "  ".join(f"{r}={c}" for r, c in sorted(failed_rules.items()))
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Audit per-slide think-cell anchor wiring in a .pptx — gate-5.",
    )
    p.add_argument("pptx", type=Path)
    p.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help=f"Override path to a binding_to_range_manifest.json. "
        f"Default: <repo>/{DEFAULT_MANIFEST_PATH}",
    )
    p.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    p.add_argument(
        "--quiet",
        action="store_true",
        help="Only emit slide units that contain a fail or warn finding.",
    )
    args = p.parse_args(argv)

    if not args.pptx.is_file():
        sys.stderr.write(f"not a file: {args.pptx}\n")
        return 3
    try:
        report = audit(args.pptx, args.manifest)
    except (zipfile.BadZipFile, OSError) as e:
        sys.stderr.write(f"could not open pptx: {e}\n")
        return 3

    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), indent=2) + "\n")
    else:
        sys.stdout.write(render_text(report, args.quiet) + "\n")

    if report.summary.get("fail", 0):
        return 1
    if report.summary.get("warn", 0):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
