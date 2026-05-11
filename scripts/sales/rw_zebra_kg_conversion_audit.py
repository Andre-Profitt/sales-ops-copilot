"""Audit the Zebra-template -> Power BI native conversion bridge.

This is a conversion-quality harness, not a publisher. It compares:

- full source PBIX Report/Layout geometry
- the mined Zebra-only visual corpus used by the native translator
- the native report.json emitted by rw_zebra_kg_publish_all_templates

The goal is to make lossiness explicit before a bulk publish is treated as
reviewable dashboard output.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_conversion_audit
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from scripts.sales.rw_zebra_kg_publish_all_templates import (
    missing_report_refs,
    translated_report,
)
from scripts.sales.rw_zebra_kg_test_dashboard import list_templates, load_raw_rows
from scripts.sales.rw_zebra_kg_test_dashboard import load_catalog
from scripts.sales.rw_zebra_kg_tmdl_emit import REPO_ROOT, measure_count
from scripts.sales.rw_zebra_template_miner import (
    is_zebra_visual,
    iter_pbix_layouts,
    parse_config,
    textbox_text,
)

DEFAULT_SOURCE_DIR = (
    Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/pbix-extracted"
)
DEFAULT_OUT_JSON = REPO_ROOT / "data/zebra_kg/published/conversion_audit.json"
DEFAULT_OUT_MD = REPO_ROOT / "docs/sales/RW_ZEBRA_NATIVE_CONVERSION_AUDIT.md"


@dataclass(frozen=True)
class SourceStats:
    pages: int
    visuals: int
    zebra_visuals: int
    custom_visual_packages: int
    visual_type_counts: dict[str, int]


@dataclass(frozen=True)
class NativeStats:
    pages: int
    visuals: int
    off_canvas_visuals: int
    fallback_textboxes: int
    custom_visual_leftovers: int
    unresolved_measure_refs: int
    placeholder_column_refs: int
    visual_type_counts: dict[str, int]


@dataclass(frozen=True)
class AuditRow:
    slug: str
    source: SourceStats
    raw_zebra_rows: int
    raw_zebra_pages: int
    native: NativeStats
    measures: int
    lost_context_visuals: int
    lost_source_pages: int
    fidelity_coverage_pct: float
    review_verdict: str
    primary_issue: str


def _visual_type(visual_container: dict[str, Any]) -> str:
    return (parse_config(visual_container).get("singleVisual") or {}).get(
        "visualType", "<none>"
    )


def _source_stats(layout: dict[str, Any], archive_path: Path) -> SourceStats:
    counts: Counter[str] = Counter()
    pages = layout.get("sections") or []
    visuals = 0
    zebra_visuals = 0
    for section in pages:
        for vc in section.get("visualContainers") or []:
            visual_type = _visual_type(vc)
            counts[visual_type] += 1
            visuals += 1
            if is_zebra_visual(visual_type):
                zebra_visuals += 1
    return SourceStats(
        pages=len(pages),
        visuals=visuals,
        zebra_visuals=zebra_visuals,
        custom_visual_packages=_custom_visual_package_count(archive_path),
        visual_type_counts=dict(counts),
    )


def _custom_visual_package_count(path: Path) -> int:
    # The package count is best-effort. Direct PBIX files are zip archives, but
    # malformed or encrypted examples should not block the bridge audit.
    import zipfile

    try:
        with zipfile.ZipFile(path) as zf:
            roots = {
                member.split("/", 3)[2]
                for member in zf.namelist()
                if member.startswith("Report/CustomVisuals/")
                and len(member.split("/", 3)) >= 3
            }
    except zipfile.BadZipFile:
        return 0
    return len(roots)


def _native_stats(slug: str, report: dict[str, Any]) -> NativeStats:
    counts: Counter[str] = Counter()
    visuals = 0
    off_canvas = 0
    fallback_textboxes = 0
    custom_leftovers = 0
    for section in report.get("sections") or []:
        canvas_w = float(section.get("width") or 1280)
        canvas_h = float(section.get("height") or 720)
        for vc in section.get("visualContainers") or []:
            visual_type = _visual_type(vc)
            counts[visual_type] += 1
            visuals += 1
            x = float(vc.get("x") or 0)
            y = float(vc.get("y") or 0)
            w = float(vc.get("width") or 0)
            h = float(vc.get("height") or 0)
            if x < 0 or y < 0 or x + w > canvas_w + 0.1 or y + h > canvas_h + 0.1:
                off_canvas += 1
            if visual_type == "textbox" and "Native fallback" in textbox_text(
                parse_config(vc).get("singleVisual") or {}
            ):
                fallback_textboxes += 1
            if _is_untranslated_custom_visual(visual_type):
                custom_leftovers += 1
    measure_names = set(load_catalog(slug).measure_to_table)
    missing_refs = missing_report_refs(slug, report)
    unresolved_measure_refs = [
        ref for ref in missing_refs if ref.split(".", 1)[1] in measure_names
    ]
    placeholder_column_refs = [
        ref for ref in missing_refs if ref.split(".", 1)[1] not in measure_names
    ]
    return NativeStats(
        pages=len(report.get("sections") or []),
        visuals=visuals,
        off_canvas_visuals=off_canvas,
        fallback_textboxes=fallback_textboxes,
        custom_visual_leftovers=custom_leftovers,
        unresolved_measure_refs=len(unresolved_measure_refs),
        placeholder_column_refs=len(placeholder_column_refs),
        visual_type_counts=dict(counts),
    )


def _is_untranslated_custom_visual(visual_type: str) -> bool:
    return (
        visual_type.startswith("ZebraBI")
        or visual_type.startswith("zebraBi")
        or (visual_type.startswith("waterfall") and visual_type != "waterfallChart")
    )


def _raw_zebra_pages(rows: list[dict[str, Any]]) -> int:
    return len(
        {
            row.get("page_display_name") or row.get("page_name") or "Page"
            for row in rows
        }
    )


def audit_templates(source_dir: Path) -> list[AuditRow]:
    layouts = {pbix.template_slug: pbix for pbix in iter_pbix_layouts(source_dir)}
    rows: list[AuditRow] = []
    for slug, _count in list_templates():
        if slug not in layouts:
            raise RuntimeError(f"{slug}: no source PBIX layout under {source_dir}")
        source = _source_stats(layouts[slug].layout, layouts[slug].archive_path)
        raw_rows = load_raw_rows(slug)
        report, _vc_count = translated_report(slug)
        native = _native_stats(slug, report)
        lost_context = max(0, source.visuals - len(raw_rows))
        lost_pages = max(0, source.pages - _raw_zebra_pages(raw_rows))
        coverage = round((len(raw_rows) / source.visuals) * 100, 1) if source.visuals else 0.0
        verdict, issue = _verdict(source, native, lost_context, lost_pages)
        rows.append(
            AuditRow(
                slug=slug,
                source=source,
                raw_zebra_rows=len(raw_rows),
                raw_zebra_pages=_raw_zebra_pages(raw_rows),
                native=native,
                measures=measure_count(slug),
                lost_context_visuals=lost_context,
                lost_source_pages=lost_pages,
                fidelity_coverage_pct=coverage,
                review_verdict=verdict,
                primary_issue=issue,
            )
        )
    return rows


def _verdict(
    source: SourceStats,
    native: NativeStats,
    lost_context: int,
    lost_pages: int,
) -> tuple[str, str]:
    if native.unresolved_measure_refs:
        return "blocked", f"{native.unresolved_measure_refs} unresolved measure refs"
    if native.custom_visual_leftovers:
        return "blocked", f"{native.custom_visual_leftovers} custom visuals still present"
    if native.off_canvas_visuals:
        return "blocked", f"{native.off_canvas_visuals} off-canvas visuals"
    if lost_pages:
        return "not-template-fidelity", f"{lost_pages} source pages have no mined Zebra visual"
    if lost_context:
        return "native-approx-only", f"{lost_context} non-Zebra source visuals dropped"
    if source.custom_visual_packages and native.custom_visual_leftovers == 0:
        return "native-approx-only", "custom visual packages intentionally omitted"
    return "structural-pass", "no structural bridge issue detected"


def write_json(rows: list[AuditRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(row) for row in rows], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_markdown(rows: list[AuditRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    totals = _totals(rows)
    table = "\n".join(_markdown_row(row) for row in rows)
    path.write_text(
        f"""# RW Zebra Native Conversion Audit

Generated: {date.today().isoformat()}

## Readout

The current native bridge is structurally useful, but it is not a fidelity
converter. Across the 20 Zebra source PBIX reports it uses only the mined Zebra
custom-visual rows and drops the rest of the report frame. That is enough for
translator plumbing, not enough for polished dashboard review.

| Metric | Value |
| --- | ---: |
| Source PBIX pages | {totals["source_pages"]} |
| Source visualContainers | {totals["source_visuals"]} |
| Source Zebra visualContainers mined | {totals["raw_zebra_rows"]} |
| Dropped non-Zebra context visualContainers | {totals["lost_context_visuals"]} |
| Native pages emitted after page-preserving fix | {totals["native_pages"]} |
| Native visualContainers emitted | {totals["native_visuals"]} |
| Native fallback textboxes | {totals["fallback_textboxes"]} |
| Native off-canvas visuals | {totals["off_canvas_visuals"]} |
| Native unresolved measure refs | {totals["unresolved_measure_refs"]} |
| Native placeholder column refs added by TMDL emitter | {totals["placeholder_column_refs"]} |

## Template Gate

| Template | Source pages | Source VCs | Zebra rows | Coverage | Dropped ctx | Native pages | Native VCs | Fallbacks | Off-canvas | Verdict | Primary issue |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
{table}

## Implication

Use this path only as `native-approx`. A reviewable Zebra-fidelity lab needs to
start from full `Report/Layout`, preserve non-Zebra page furniture, and keep the
Zebra visual packages/settings intact. An RW production dashboard should instead
lift selected Zebra patterns into purpose-built native pages with their own QA
screenshots.
""",
        encoding="utf-8",
    )


def _totals(rows: list[AuditRow]) -> dict[str, int]:
    return {
        "source_pages": sum(row.source.pages for row in rows),
        "source_visuals": sum(row.source.visuals for row in rows),
        "raw_zebra_rows": sum(row.raw_zebra_rows for row in rows),
        "lost_context_visuals": sum(row.lost_context_visuals for row in rows),
        "native_pages": sum(row.native.pages for row in rows),
        "native_visuals": sum(row.native.visuals for row in rows),
        "fallback_textboxes": sum(row.native.fallback_textboxes for row in rows),
        "off_canvas_visuals": sum(row.native.off_canvas_visuals for row in rows),
        "unresolved_measure_refs": sum(row.native.unresolved_measure_refs for row in rows),
        "placeholder_column_refs": sum(row.native.placeholder_column_refs for row in rows),
    }


def _markdown_row(row: AuditRow) -> str:
    return (
        f"| `{row.slug}` "
        f"| {row.source.pages} "
        f"| {row.source.visuals} "
        f"| {row.raw_zebra_rows} "
        f"| {row.fidelity_coverage_pct:.1f}% "
        f"| {row.lost_context_visuals} "
        f"| {row.native.pages} "
        f"| {row.native.visuals} "
        f"| {row.native.fallback_textboxes} "
        f"| {row.native.off_canvas_visuals} "
        f"| {row.review_verdict} "
        f"| {row.primary_issue} |"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--out-md", type=Path, default=DEFAULT_OUT_MD)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = audit_templates(args.source_dir.expanduser())
    write_json(rows, args.out_json)
    write_markdown(rows, args.out_md)
    totals = _totals(rows)
    print(
        "audited "
        f"{len(rows)} templates; "
        f"source_vcs={totals['source_visuals']} "
        f"raw_zebra_rows={totals['raw_zebra_rows']} "
        f"dropped_context={totals['lost_context_visuals']} "
        f"unresolved_measure_refs={totals['unresolved_measure_refs']} "
        f"off_canvas={totals['off_canvas_visuals']}"
    )
    print(args.out_md)


if __name__ == "__main__":
    main()
