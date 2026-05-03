#!/usr/bin/env python3
"""Extract a slide-level corpus from installed think-cell templates.

This does not rebuild any SimCorp deck. It inspects think-cell's stock `.potx`
templates as OpenXML packages and, where possible, reads embedded OLE/CFB
`think-cellXML` streams to learn which slides are useful as chart donors,
table references, design references, or dead ends.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import struct
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_ROOT = Path("/Library/Application Support/Microsoft/think-cell/templates")
DEFAULT_OUTPUT_DIR = ROOT / "state" / "thinkcell_bridge" / "slide_corpus"

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

CFB_MAGIC = bytes.fromhex("d0cf11e0a1b11ae1")
FREESECT = 0xFFFFFFFF
ENDOFCHAIN = 0xFFFFFFFE
FATSECT = 0xFFFFFFFD
DIFSECT = 0xFFFFFFFC


@dataclass
class OleProbe:
    part: str
    size_bytes: int
    is_cfb: bool
    streams: list[str] = field(default_factory=list)
    thinkcellxml_readable: bool = False
    thinkcellxml_bytes: int = 0
    m_str_name_values: list[str] = field(default_factory=list)
    thinkcell_classes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SlideProbe:
    template: str
    family: str
    slide_number: int
    slide_part: str
    title_guess: str
    use_class: str
    donor_score: int
    simcorp_fit: str
    text: list[str]
    shape_names: list[str]
    shape_count: int
    chart_refs: int
    graphic_frames: int
    pictures: int
    native_tables: int
    ole_shape_count: int
    ole_parts: list[OleProbe]
    rel_chart_parts: list[str]
    rel_image_parts: list[str]
    rel_ole_parts: list[str]
    signals: list[str]


@dataclass
class TemplateSummary:
    template: str
    family: str
    slide_count: int
    ole_parts: int
    readable_thinkcellxml_parts: int
    native_tables: int
    chart_refs: int
    use_classes: dict[str, int]
    top_slide_numbers: list[int]


class CfbReader:
    def __init__(self, data: bytes) -> None:
        if data[:8] != CFB_MAGIC:
            raise ValueError("not a CFB document")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
        self.num_fat_sectors = struct.unpack_from("<I", data, 0x2C)[0]
        self.first_dir_sector = struct.unpack_from("<I", data, 0x30)[0]
        self.mini_cutoff = struct.unpack_from("<I", data, 0x38)[0]
        self.first_mini_fat_sector = struct.unpack_from("<I", data, 0x3C)[0]
        self.num_mini_fat_sectors = struct.unpack_from("<I", data, 0x40)[0]
        self.fat = self._read_fat()
        self.entries = self._read_directory()
        self.root_entry = next((entry for entry in self.entries if entry["type"] == 5), None)
        self.mini_fat = self._read_mini_fat()
        self.mini_stream = self._read_root_mini_stream()

    def stream_names(self) -> list[str]:
        return sorted(str(entry["name"]) for entry in self.entries if entry["type"] == 2)

    def read_stream(self, name: str) -> bytes | None:
        entry = next((item for item in self.entries if item["type"] == 2 and item["name"] == name), None)
        if not entry:
            return None
        size = int(entry["size"])
        start = int(entry["start"])
        if size < self.mini_cutoff and self.mini_stream:
            return self._read_mini_stream(start, size)
        if start in (FREESECT, ENDOFCHAIN):
            return b""
        return self._read_sectors(self._sector_chain(start))[:size]

    def _read_fat(self) -> list[int]:
        difat = list(struct.unpack_from("<109I", self.data, 0x4C))
        fat: list[int] = []
        for sector_id in difat:
            if sector_id in (FREESECT, ENDOFCHAIN, FATSECT, DIFSECT):
                continue
            offset = self._sector_offset(sector_id)
            entries_per_sector = self.sector_size // 4
            fat.extend(struct.unpack_from(f"<{entries_per_sector}I", self.data, offset))
            if len(fat) >= self.num_fat_sectors * entries_per_sector:
                break
        return fat

    def _read_mini_fat(self) -> list[int]:
        if self.first_mini_fat_sector in (FREESECT, ENDOFCHAIN) or self.num_mini_fat_sectors == 0:
            return []
        sectors = self._sector_chain(self.first_mini_fat_sector)
        if self.num_mini_fat_sectors:
            sectors = sectors[: self.num_mini_fat_sectors]
        raw = self._read_sectors(sectors)
        count = len(raw) // 4
        return list(struct.unpack_from(f"<{count}I", raw, 0))

    def _read_root_mini_stream(self) -> bytes:
        if not self.root_entry:
            return b""
        start = int(self.root_entry["start"])
        size = int(self.root_entry["size"])
        if start in (FREESECT, ENDOFCHAIN) or size <= 0:
            return b""
        return self._read_sectors(self._sector_chain(start))[:size]

    def _read_directory(self) -> list[dict[str, Any]]:
        directory = self._read_sectors(self._sector_chain(self.first_dir_sector))
        entries = []
        for offset in range(0, len(directory), 128):
            entry = directory[offset : offset + 128]
            if len(entry) < 128:
                continue
            name_len = struct.unpack_from("<H", entry, 64)[0]
            if name_len < 2:
                continue
            name = entry[: name_len - 2].decode("utf-16le", "ignore")
            obj_type = entry[66]
            start = struct.unpack_from("<I", entry, 116)[0]
            size = struct.unpack_from("<Q", entry, 120)[0]
            entries.append({"name": name, "type": obj_type, "start": start, "size": size})
        return entries

    def _read_mini_stream(self, start: int, size: int) -> bytes:
        if start in (FREESECT, ENDOFCHAIN) or not self.mini_fat:
            return b""
        chunks = []
        sector = start
        while sector not in (FREESECT, ENDOFCHAIN):
            offset = sector * self.mini_sector_size
            chunks.append(self.mini_stream[offset : offset + self.mini_sector_size])
            if sector >= len(self.mini_fat):
                break
            sector = self.mini_fat[sector]
        return b"".join(chunks)[:size]

    def _sector_chain(self, start_sector: int) -> list[int]:
        chain: list[int] = []
        sector = start_sector
        seen: set[int] = set()
        while sector not in (FREESECT, ENDOFCHAIN):
            if sector in seen or sector >= len(self.fat):
                break
            seen.add(sector)
            chain.append(sector)
            sector = self.fat[sector]
        return chain

    def _sector_offset(self, sector_id: int) -> int:
        return (sector_id + 1) * self.sector_size

    def _read_sectors(self, sectors: list[int]) -> bytes:
        chunks = []
        for sector in sectors:
            offset = self._sector_offset(sector)
            chunks.append(self.data[offset : offset + self.sector_size])
        return b"".join(chunks)


def _slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _rels_part(slide_part: str) -> str:
    directory, filename = slide_part.rsplit("/", 1)
    return f"{directory}/_rels/{filename}.rels"


def _resolve_part(base_part: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base_dir = base_part.rsplit("/", 1)[0]
    parts: list[str] = []
    for piece in f"{base_dir}/{target}".split("/"):
        if piece in ("", "."):
            continue
        if piece == "..":
            if parts:
                parts.pop()
            continue
        parts.append(piece)
    return "/".join(parts)


def _family(relative: str) -> str:
    parts = relative.split("/")
    if relative.startswith("think-cell Charts/") and len(parts) > 1:
        return "Charts/" + parts[1]
    if relative.startswith("Useful Elements/") and len(parts) > 2:
        return "Useful/" + parts[1]
    return parts[0]


def _text_values(root: ET.Element, limit: int = 80) -> list[str]:
    values: list[str] = []
    for node in root.iter(f"{{{A_NS}}}t"):
        value = (node.text or "").strip()
        if value and value not in values:
            values.append(value)
            if len(values) >= limit:
                break
    return values


def _shape_names(root: ET.Element, limit: int = 120) -> list[str]:
    values: list[str] = []
    for node in root.iter(f"{{{P_NS}}}cNvPr"):
        value = (node.get("name") or "").strip()
        if value and value not in values:
            values.append(value)
            if len(values) >= limit:
                break
    return values


def _relationship_map(zf: ZipFile, slide_part: str) -> dict[str, dict[str, str]]:
    rels_name = _rels_part(slide_part)
    if rels_name not in zf.namelist():
        return {}
    root = ET.fromstring(zf.read(rels_name))
    rels = {}
    for rel in root:
        rel_id = rel.get("Id")
        if not rel_id:
            continue
        rels[rel_id] = {
            "type": rel.get("Type", ""),
            "target": rel.get("Target", ""),
            "target_mode": rel.get("TargetMode", ""),
        }
    return rels


def _ole_parts_from_slide(zf: ZipFile, slide_part: str, root: ET.Element) -> list[str]:
    rels = _relationship_map(zf, slide_part)
    parts: list[str] = []
    for ole in root.iter(f"{{{P_NS}}}oleObj"):
        rid = ole.get(f"{{{R_NS}}}id")
        if not rid or rid not in rels:
            continue
        rel = rels[rid]
        if rel.get("target_mode") == "External":
            continue
        target = rel.get("target", "")
        if target:
            parts.append(_resolve_part(slide_part, target))
    for rel in rels.values():
        if not rel.get("type", "").endswith("/oleObject") or rel.get("target_mode") == "External":
            continue
        target = rel.get("target", "")
        if target:
            part = _resolve_part(slide_part, target)
            if part not in parts:
                parts.append(part)
    return parts


def _related_parts(zf: ZipFile, slide_part: str, suffix: str) -> list[str]:
    out: list[str] = []
    for rel in _relationship_map(zf, slide_part).values():
        if not rel.get("type", "").endswith(suffix) or rel.get("target_mode") == "External":
            continue
        target = rel.get("target", "")
        if target:
            out.append(_resolve_part(slide_part, target))
    return sorted(set(out))


def _probe_ole(part: str, data: bytes) -> OleProbe:
    probe = OleProbe(part=part, size_bytes=len(data), is_cfb=data[:8] == CFB_MAGIC)
    if not probe.is_cfb:
        return probe
    try:
        cfb = CfbReader(data)
        probe.streams = cfb.stream_names()
        tc = cfb.read_stream("think-cellXML")
        if tc is None:
            return probe
        probe.thinkcellxml_readable = True
        probe.thinkcellxml_bytes = len(tc)
        text = tc.decode("utf-8", "ignore")
        probe.m_str_name_values = sorted(
            {value.strip() for value in re.findall(r"<m_strName>(.*?)</m_strName>", text) if value.strip()}
        )
        probe.thinkcell_classes = _class_signals(text)
        probe.flags = _thinkcell_flags(text)
    except Exception as exc:  # noqa: BLE001 - corpus extraction should keep going.
        probe.error = f"{type(exc).__name__}: {exc}"
    return probe


def _class_signals(text: str) -> list[str]:
    candidates = set(re.findall(r"</?(C[A-Za-z0-9_]+|TC[A-Za-z0-9_]+)", text))
    important = {
        item
        for item in candidates
        if item
        in {
            "CChart",
            "CSeries",
            "CValueAxis",
            "CCategoryAxis",
            "CWaterfall",
            "CMekko",
            "CSmartGrid",
            "CContainerSE",
            "CGantt",
            "TCLayout",
            "CLabel",
            "CLegend",
            "CGridline",
            "CSegment",
            "CScatter",
            "CBubble",
        }
        or any(token in item.lower() for token in ("chart", "series", "axis", "mekko", "gantt", "grid", "label"))
    }
    return sorted(important)[:40]


def _thinkcell_flags(text: str) -> list[str]:
    checks = {
        "has_m_strName": "m_strName",
        "empty_m_strName": "<m_strName></m_strName>",
        "has_datasheet_hint": "DataSheet",
        "has_range_name_hint": "RangeName",
        "has_excel_range_hint": "m_bstrRange",
        "has_smart_grid": "CSmartGrid",
        "has_tclayout": "TCLayout",
        "has_mekko": "Mekko",
        "has_gantt": "Gantt",
        "has_waterfall": "Waterfall",
    }
    return [label for label, needle in checks.items() if needle in text]


def _signals(
    *,
    relative: str,
    text: list[str],
    ole_parts: list[OleProbe],
    native_tables: int,
    chart_refs: int,
    pictures: int,
) -> list[str]:
    joined = " ".join(text).lower()
    flat_flags = {flag for ole in ole_parts for flag in ole.flags}
    family = relative.lower()
    out: list[str] = []
    if chart_refs or "chart" in family or any("chart" in cls.lower() for ole in ole_parts for cls in ole.thinkcell_classes):
        out.append("chart_reference")
    if native_tables or "tables" in family or "table" in joined or "smart_grid" in " ".join(flat_flags):
        out.append("table_reference")
    if "agenda" in family or "agenda" in joined:
        out.append("agenda")
    if "timeline" in family or "milestone" in family or "gantt" in " ".join(flat_flags).lower():
        out.append("timeline_or_gantt")
    if "waterfall" in family:
        out.append("waterfall")
    if "mekko" in family:
        out.append("mekko")
    if "scatter" in family or "bubble" in family:
        out.append("scatter_bubble")
    if "map" in family:
        out.append("map")
    if "funnel" in family:
        out.append("funnel")
    if "traffic" in family or "thermometer" in family or "gauge" in family:
        out.append("decorative_metric")
    if pictures and not chart_refs:
        out.append("visual_asset")
    if any(ole.thinkcellxml_readable for ole in ole_parts):
        out.append("readable_thinkcellxml")
    if any(ole.m_str_name_values for ole in ole_parts):
        out.append("named_automation")
    elif any("empty_m_strName" in ole.flags for ole in ole_parts):
        out.append("unnamed_donor_candidate")
    return sorted(set(out))


def _title_guess(text: list[str], slide_number: int) -> str:
    for value in text:
        cleaned = re.sub(r"\s+", " ", value).strip()
        if len(cleaned) >= 3 and not cleaned.lower().startswith("lorem"):
            return cleaned[:120]
    return f"Slide {slide_number}"


def _classify_slide(relative: str, signals: list[str], ole_parts: list[OleProbe], native_tables: int) -> tuple[str, int, str]:
    signal_set = set(signals)
    readable = any(ole.thinkcellxml_readable for ole in ole_parts)
    unnamed_tc = any("empty_m_strName" in ole.flags for ole in ole_parts)
    score = 0
    if readable:
        score += 30
    if unnamed_tc:
        score += 25
    if "chart_reference" in signal_set:
        score += 20
    if "table_reference" in signal_set:
        score += 15
    if "timeline_or_gantt" in signal_set or "waterfall" in signal_set or "scatter_bubble" in signal_set:
        score += 10
    if "decorative_metric" in signal_set or "funnel" in signal_set:
        score -= 20
    if native_tables:
        score += 5

    family = relative.lower()
    if "think-cell charts" in family and readable:
        use_class = "native_chart_donor_candidate"
        simcorp_fit = "high"
    elif "tables" in family and (readable or native_tables):
        use_class = "table_reference_or_donor_probe"
        simcorp_fit = "medium"
    elif "timeline" in family or "milestone" in family:
        use_class = "timeline_reference"
        simcorp_fit = "conditional"
    elif "funnel" in family or "traffic" in family or "thermometer" in family or "gauge" in family:
        use_class = "avoid_by_default"
        simcorp_fit = "low"
    elif "agenda" in family or "process" in family or "matrix" in family:
        use_class = "layout_reference"
        simcorp_fit = "conditional"
    elif readable:
        use_class = "thinkcell_object_reference"
        simcorp_fit = "conditional"
    else:
        use_class = "design_reference"
        simcorp_fit = "low"
    return use_class, max(score, 0), simcorp_fit


def analyze_template(path: Path, template_root: Path) -> tuple[TemplateSummary, list[SlideProbe]]:
    relative = path.relative_to(template_root).as_posix()
    slides: list[SlideProbe] = []
    with ZipFile(path) as zf:
        names = zf.namelist()
        slide_parts = sorted(
            [name for name in names if re.match(r"ppt/slides/slide\d+\.xml$", name)],
            key=_slide_sort_key,
        )
        for slide_part in slide_parts:
            slide_number = _slide_sort_key(slide_part)
            root = ET.fromstring(zf.read(slide_part))
            text = _text_values(root)
            shape_names = _shape_names(root)
            chart_refs = sum(1 for _ in root.iter(f"{{{C_NS}}}chart"))
            graphic_frames = sum(1 for _ in root.iter(f"{{{P_NS}}}graphicFrame"))
            pictures = sum(1 for _ in root.iter(f"{{{P_NS}}}pic"))
            native_tables = sum(1 for _ in root.iter(f"{{{A_NS}}}tbl"))
            ole_part_names = [part for part in _ole_parts_from_slide(zf, slide_part, root) if part in names]
            ole_parts = [_probe_ole(part, zf.read(part)) for part in ole_part_names]
            sig = _signals(
                relative=relative,
                text=text,
                ole_parts=ole_parts,
                native_tables=native_tables,
                chart_refs=chart_refs,
                pictures=pictures,
            )
            use_class, donor_score, simcorp_fit = _classify_slide(relative, sig, ole_parts, native_tables)
            slides.append(
                SlideProbe(
                    template=relative,
                    family=_family(relative),
                    slide_number=slide_number,
                    slide_part=slide_part,
                    title_guess=_title_guess(text, slide_number),
                    use_class=use_class,
                    donor_score=donor_score,
                    simcorp_fit=simcorp_fit,
                    text=text[:40],
                    shape_names=shape_names[:80],
                    shape_count=sum(1 for _ in root.iter(f"{{{P_NS}}}cNvPr")),
                    chart_refs=chart_refs,
                    graphic_frames=graphic_frames,
                    pictures=pictures,
                    native_tables=native_tables,
                    ole_shape_count=sum(1 for _ in root.iter(f"{{{P_NS}}}oleObj")),
                    ole_parts=ole_parts,
                    rel_chart_parts=_related_parts(zf, slide_part, "/chart"),
                    rel_image_parts=_related_parts(zf, slide_part, "/image"),
                    rel_ole_parts=sorted(set(ole_part_names)),
                    signals=sig,
                )
            )
    summary = summarize_template(relative, slides, len([name for name in names if name.startswith("ppt/embeddings/")]))
    return summary, slides


def summarize_template(relative: str, slides: list[SlideProbe], package_ole_count: int) -> TemplateSummary:
    use_classes: dict[str, int] = {}
    for slide in slides:
        use_classes[slide.use_class] = use_classes.get(slide.use_class, 0) + 1
    top = sorted(slides, key=lambda slide: (-slide.donor_score, slide.slide_number))[:8]
    return TemplateSummary(
        template=relative,
        family=_family(relative),
        slide_count=len(slides),
        ole_parts=package_ole_count,
        readable_thinkcellxml_parts=sum(
            1 for slide in slides for ole in slide.ole_parts if ole.thinkcellxml_readable
        ),
        native_tables=sum(slide.native_tables for slide in slides),
        chart_refs=sum(slide.chart_refs for slide in slides),
        use_classes=dict(sorted(use_classes.items())),
        top_slide_numbers=[slide.slide_number for slide in top if slide.donor_score > 0],
    )


def write_markdown(summaries: list[TemplateSummary], slides: list[SlideProbe], out_path: Path) -> None:
    total_readable = sum(summary.readable_thinkcellxml_parts for summary in summaries)
    lines = [
        "# think-cell Slide-Level Corpus",
        "",
        f"- Templates: `{len(summaries)}`",
        f"- Slides: `{len(slides)}`",
        f"- Readable think-cellXML OLE parts: `{total_readable}`",
        "",
        "## Family Summary",
        "",
        "| Template | Slides | OLE | Readable tcXML | Native tables | Charts | Top slides | Classes |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for summary in sorted(summaries, key=lambda item: item.template):
        classes = ", ".join(f"{k}:{v}" for k, v in summary.use_classes.items())
        top = ", ".join(str(item) for item in summary.top_slide_numbers[:8])
        lines.append(
            f"| `{summary.template}` | {summary.slide_count} | {summary.ole_parts} | "
            f"{summary.readable_thinkcellxml_parts} | {summary.native_tables} | "
            f"{summary.chart_refs} | {top or '-'} | {classes} |"
        )
    lines.extend(
        [
            "",
            "## Highest-Scoring Slides",
            "",
            "| Score | Template | Slide | Class | Fit | Title | Signals |",
            "|---:|---|---:|---|---|---|---|",
        ]
    )
    top_slides = sorted(slides, key=lambda slide: (-slide.donor_score, slide.template, slide.slide_number))[:80]
    for slide in top_slides:
        signals = ", ".join(slide.signals)
        title = slide.title_guess.replace("|", "/")
        lines.append(
            f"| {slide.donor_score} | `{slide.template}` | {slide.slide_number} | "
            f"{slide.use_class} | {slide.simcorp_fit} | {title} | {signals} |"
        )
    lines.extend(
        [
            "",
            "## Extraction Verdict",
            "",
            "- Stock templates are still not `.ppttc` automation templates because they carry no production `m_strName` names.",
            "- Slides with readable `think-cellXML` and empty `m_strName` values are the most useful donor/reference material.",
            "- Native think-cell tables remain a donor-probe target, not a production lane, unless a real named data-backed table donor is captured.",
            "- Decorative metric widgets, funnels, ratings, hand-drawn objects, and quote layouts should stay out of Sales Director operating reviews by default.",
        ]
    )
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def write_csv(slides: list[SlideProbe], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "template",
                "family",
                "slide_number",
                "title_guess",
                "use_class",
                "donor_score",
                "simcorp_fit",
                "chart_refs",
                "native_tables",
                "ole_parts",
                "readable_thinkcellxml",
                "signals",
            ],
        )
        writer.writeheader()
        for slide in slides:
            writer.writerow(
                {
                    "template": slide.template,
                    "family": slide.family,
                    "slide_number": slide.slide_number,
                    "title_guess": slide.title_guess,
                    "use_class": slide.use_class,
                    "donor_score": slide.donor_score,
                    "simcorp_fit": slide.simcorp_fit,
                    "chart_refs": slide.chart_refs,
                    "native_tables": slide.native_tables,
                    "ole_parts": len(slide.ole_parts),
                    "readable_thinkcellxml": sum(1 for ole in slide.ole_parts if ole.thinkcellxml_readable),
                    "signals": ";".join(slide.signals),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    templates = sorted(args.template_root.rglob("*.potx"))
    if not templates:
        raise SystemExit(f"no .potx templates found under {args.template_root}")

    summaries: list[TemplateSummary] = []
    slides: list[SlideProbe] = []
    for template in templates:
        summary, slide_rows = analyze_template(template, args.template_root)
        summaries.append(summary)
        slides.extend(slide_rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "thinkcell-slide-corpus/v1",
        "template_root": str(args.template_root),
        "template_count": len(summaries),
        "slide_count": len(slides),
        "summaries": [asdict(item) for item in summaries],
        "slides": [asdict(item) for item in slides],
    }
    json_path = args.output_dir / "thinkcell_slide_corpus.json"
    md_path = args.output_dir / "thinkcell_slide_corpus.md"
    csv_path = args.output_dir / "thinkcell_slide_index.csv"
    json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_markdown(summaries, slides, md_path)
    write_csv(slides, csv_path)
    print(f"templates={len(summaries)} slides={len(slides)}")
    print(f"json={json_path}")
    print(f"markdown={md_path}")
    print(f"csv={csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
