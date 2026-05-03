#!/usr/bin/env python3
"""Inventory installed think-cell templates and render a decision contact sheet."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
import textwrap
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZipFile

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE_ROOT = Path("/Library/Application Support/Microsoft/think-cell/templates")
DEFAULT_OUT = ROOT / "state" / "thinkcell_bridge" / "template_catalog"

A_NS = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
C_NS = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
P_NS = "{http://schemas.openxmlformats.org/presentationml/2006/main}"

RENDER_CANDIDATES = (
    "think-cell Charts/Bar, Column/Bar, Column.potx",
    "think-cell Charts/Waterfall/Waterfall.potx",
    "think-cell Charts/Line, Area/Line, Area.potx",
    "think-cell Charts/Scatter, Bubble/Scatter, Bubble.potx",
    "think-cell Charts/Timeline, Gantt/Timeline, Gantt.potx",
    "think-cell Charts/Mekko/Mekko.potx",
    "think-cell Charts/Annotations/Annotations.potx",
    "think-cell Charts/Pie, Doughnut/Pie, Doughnut.potx",
    "Tables/Tables.potx",
    "Useful Elements/Tables/Tables.potx",
    "Dashboards, Statistics/Dashboards, Statistics.potx",
    "Timelines, Milestones, Project Planning/Timelines, Milestones, Project Planning.potx",
    "Agendas, Schedules, Timetables/Agendas, Schedules, Timetables.potx",
    "Useful Elements/Diagrams/Progress Bars, Gauge/Progress Bars, Gauges.potx",
    "Useful Elements/Traffic Lights/Traffic Lights.potx",
    "Useful Elements/Call-outs, Stickers/Callouts, Comments.potx",
    "Useful Elements/Sections, Columns, Rows/Sections.potx",
    "Maps/Maps.potx",
    "Matrices, SWOT Analyses/Matrices, SWOT Analyses.potx",
    "Processes, Flow Charts, Phases/Processes, Flow Charts, Phases.potx",
)


@dataclass
class TemplateInfo:
    relative_path: str
    slide_count: int
    text_sample: list[str]
    chart_refs: int
    graphic_frames: int
    pictures: int
    ole_objects: int
    tag_files: int
    named_thinkcell_payloads: int
    render_candidate: bool


def _slide_sort_key(name: str) -> int:
    match = re.search(r"slide(\d+)\.xml$", name)
    return int(match.group(1)) if match else 0


def _extract_text(root: ET.Element) -> list[str]:
    texts: list[str] = []
    for node in root.iter(f"{A_NS}t"):
        value = (node.text or "").strip()
        if value and value not in texts:
            texts.append(value)
    return texts


def analyze_template(path: Path, template_root: Path) -> TemplateInfo:
    relative = path.relative_to(template_root).as_posix()
    slide_text: list[str] = []
    chart_refs = 0
    graphic_frames = 0
    pictures = 0
    named_payloads = 0
    with ZipFile(path) as zf:
        names = zf.namelist()
        slide_names = sorted(
            [name for name in names if re.match(r"ppt/slides/slide\d+\.xml$", name)],
            key=_slide_sort_key,
        )
        for slide_name in slide_names:
            root = ET.fromstring(zf.read(slide_name))
            if len(slide_text) < 24:
                for text in _extract_text(root):
                    if text not in slide_text:
                        slide_text.append(text)
                    if len(slide_text) >= 24:
                        break
            chart_refs += sum(1 for _ in root.iter(f"{C_NS}chart"))
            graphic_frames += sum(1 for _ in root.iter(f"{P_NS}graphicFrame"))
            pictures += sum(1 for _ in root.iter(f"{P_NS}pic"))
            xml = ET.tostring(root, encoding="unicode")
            named_payloads += xml.count("m_strName")
        ole_objects = len([name for name in names if name.startswith("ppt/embeddings/")])
        tag_files = len([name for name in names if name.startswith("ppt/tags/tag")])
    return TemplateInfo(
        relative_path=relative,
        slide_count=len(slide_names),
        text_sample=slide_text[:12],
        chart_refs=chart_refs,
        graphic_frames=graphic_frames,
        pictures=pictures,
        ole_objects=ole_objects,
        tag_files=tag_files,
        named_thinkcell_payloads=named_payloads,
        render_candidate=relative in RENDER_CANDIDATES,
    )


def render_candidate(path: Path, template_root: Path, out_dir: Path) -> Path | None:
    relative = path.relative_to(template_root).as_posix()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", relative).strip("-")
    render_dir = out_dir / "renders" / slug
    render_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_dir), str(path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pdfs = list(tmp_dir.glob("*.pdf"))
        if not pdfs:
            return None
        pdf_path = render_dir / f"{slug}.pdf"
        shutil.copy2(pdfs[0], pdf_path)
        subprocess.run(
            ["pdftoppm", "-png", "-r", "92", "-f", "1", "-l", "3", str(pdf_path), str(render_dir / "page")],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    pages = sorted(render_dir.glob("page-*.png"))
    return pages[0] if pages else None


def make_contact_sheet(entries: list[tuple[TemplateInfo, Path]], out_path: Path) -> None:
    thumb_w, thumb_h = 360, 203
    label_h = 64
    pad = 18
    cols = 4
    rows = (len(entries) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (thumb_h + label_h + pad) + pad), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 15)
        small = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 12)
    except OSError:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    for index, (info, image_path) in enumerate(entries):
        col = index % cols
        row = index // cols
        x = pad + col * (thumb_w + pad)
        y = pad + row * (thumb_h + label_h + pad)
        image = Image.open(image_path).convert("RGB")
        image.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (thumb_w, thumb_h), "#f5f7fa")
        frame.paste(image, ((thumb_w - image.width) // 2, (thumb_h - image.height) // 2))
        sheet.paste(frame, (x, y))
        draw.rectangle([x, y, x + thumb_w, y + thumb_h], outline="#d6dcea", width=1)
        label = info.relative_path.replace(".potx", "")
        label = label.replace("think-cell Charts/", "")
        lines = textwrap.wrap(label, width=42)[:2]
        draw.text((x, y + thumb_h + 8), "\n".join(lines), fill="#1a1d31", font=font)
        meta = f"{info.slide_count} slides | charts {info.chart_refs} | tags {info.tag_files}"
        draw.text((x, y + thumb_h + 44), meta, fill="#666666", font=small)
    sheet.save(out_path)


def write_markdown(inventory: list[TemplateInfo], out_path: Path, contact_sheet: Path | None) -> None:
    lines = [
        "# think-cell Template Catalog Inventory",
        "",
        "Generated from the local think-cell install. This is an inventory artifact; selection guidance is in `docs/THINKCELL_TEMPLATE_SELECTION_MAY_2026.md`.",
        "",
    ]
    if contact_sheet:
        lines += [f"Visual contact sheet: `{contact_sheet.relative_to(ROOT)}`", ""]
    lines += [
        "| Template | Slides | Charts | Graphic frames | OLE | Tags | Named tc payloads | Sample text |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for info in sorted(inventory, key=lambda item: item.relative_path):
        sample = "; ".join(info.text_sample[:4]).replace("|", "/")
        lines.append(
            f"| `{info.relative_path}` | {info.slide_count} | {info.chart_refs} | "
            f"{info.graphic_frames} | {info.ole_objects} | {info.tag_files} | "
            f"{info.named_thinkcell_payloads} | {sample} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template-root", type=Path, default=DEFAULT_TEMPLATE_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    templates = sorted(args.template_root.rglob("*.potx"))
    inventory = [analyze_template(path, args.template_root) for path in templates]
    (args.out_dir / "thinkcell_template_catalog.json").write_text(
        json.dumps([asdict(item) for item in inventory], indent=2),
        encoding="utf-8",
    )

    rendered: list[tuple[TemplateInfo, Path]] = []
    if not args.skip_render:
        for info in inventory:
            if not info.render_candidate:
                continue
            image_path = render_candidate(args.template_root / info.relative_path, args.template_root, args.out_dir)
            if image_path:
                rendered.append((info, image_path))

    contact_sheet = args.out_dir / "thinkcell_template_contact_sheet.png" if rendered else None
    if contact_sheet:
        make_contact_sheet(rendered, contact_sheet)
    elif args.skip_render and (args.out_dir / "thinkcell_template_contact_sheet.png").exists():
        contact_sheet = args.out_dir / "thinkcell_template_contact_sheet.png"
    write_markdown(inventory, args.out_dir / "thinkcell_template_catalog.md", contact_sheet)

    print(f"Templates inventoried: {len(inventory)}")
    if contact_sheet:
        print(f"Contact sheet: {contact_sheet}")
    print(f"Markdown: {args.out_dir / 'thinkcell_template_catalog.md'}")
    print(f"JSON: {args.out_dir / 'thinkcell_template_catalog.json'}")


if __name__ == "__main__":
    main()
