"""Publish one Zebra template as a full-layout native Power BI lab report.

This is the SimCorp-safe bridge:

- preserve full source PBIX page layout and non-Zebra page furniture
- translate Zebra custom visual containers to native Power BI visuals
- remove Zebra custom visual packages so tenant custom-visual policy cannot block it
- bind to a matching structural semantic model

Names:
  SemanticModel: sm_zbr_native_layout_<slug>
  Report:        zbr_native_layout_<slug>
"""

from __future__ import annotations

import argparse
import base64
import copy
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.sales.rw_zebra_kg_fidelity_publish import (
    DEFAULT_SOURCE_DIR,
    LiveVerifyResult,
    get_item_definition,
)
from scripts.sales.rw_zebra_kg_publish_all_templates import (
    WORKSPACE_ID,
    build_definition_pbir,
    create_or_update_item,
    extra_columns_for_report,
    missing_report_refs,
    normalize_remaining_custom_visuals,
    workspace_name,
    _token,
)
from scripts.sales.rw_zebra_kg_test_dashboard import load_catalog
from scripts.sales.rw_zebra_kg_tmdl_emit import REPO_ROOT, emit_tmdl_parts, measure_count
from scripts.sales.rw_zebra_kg_translator import BindMap, translate_visual

OUT_PATH = REPO_ROOT / "data/zebra_kg/published/native_layout_templates.json"


@dataclass(frozen=True)
class NativeLayoutSource:
    slug: str
    pbix_path: Path
    source_report: dict[str, Any]
    native_report: dict[str, Any]
    static_resource_parts: dict[str, bytes]
    translated_custom_visuals: int
    native_fallback_textboxes: int

    @property
    def source_page_count(self) -> int:
        return len(self.source_report.get("sections") or [])

    @property
    def source_visual_count(self) -> int:
        return _visual_count(self.source_report)

    @property
    def native_page_count(self) -> int:
        return len(self.native_report.get("sections") or [])

    @property
    def native_visual_count(self) -> int:
        return _visual_count(self.native_report)


@dataclass(frozen=True)
class NativeLayoutGate:
    source_pages: int
    native_pages: int
    source_visuals: int
    native_visuals: int
    translated_custom_visuals: int
    native_fallback_textboxes: int
    static_resource_parts: int
    custom_visual_leftovers: int
    custom_resource_parts: int
    extra_columns: int
    unresolved_measure_refs: list[str]

    @property
    def publishable(self) -> bool:
        return (
            self.source_pages == self.native_pages
            and self.source_visuals == self.native_visuals
            and self.custom_visual_leftovers == 0
            and self.custom_resource_parts == 0
            and not self.unresolved_measure_refs
        )


@dataclass(frozen=True)
class PublishedNativeLayoutTemplate:
    slug: str
    semantic_model_id: str
    report_id: str
    url: str
    page_count: int
    visual_count: int
    static_resource_parts: int
    translated_custom_visuals: int
    measure_count: int


@dataclass(frozen=True)
class NativeLayoutVerifyResult:
    slug: str
    report_id: str
    format: str
    source_pages: int
    live_pages: int
    source_visuals: int
    live_visuals: int
    source_static_resource_parts: int
    live_static_resource_parts: int
    live_custom_resource_parts: int
    live_custom_visual_leftovers: int
    semantic_model_id_present: bool

    @property
    def passed(self) -> bool:
        return (
            self.source_pages == self.live_pages
            and self.source_visuals == self.live_visuals
            and self.source_static_resource_parts == self.live_static_resource_parts
            and self.live_custom_resource_parts == 0
            and self.live_custom_visual_leftovers == 0
            and self.semantic_model_id_present
        )


def _visual_count(report: dict[str, Any]) -> int:
    return sum(
        len(section.get("visualContainers") or []) for section in report.get("sections") or []
    )


def load_native_layout_source(
    slug: str,
    source_dir: Path = DEFAULT_SOURCE_DIR,
) -> NativeLayoutSource:
    pbix_path = source_dir.expanduser() / f"{slug}.pbix"
    if not pbix_path.exists():
        raise FileNotFoundError(f"missing extracted PBIX: {pbix_path}")

    with zipfile.ZipFile(pbix_path) as pbix:
        source_report = json.loads(pbix.read("Report/Layout").decode("utf-16-le"))
        static_resources = {
            member.removeprefix("Report/"): pbix.read(member)
            for member in pbix.namelist()
            if member.startswith("Report/StaticResources/")
        }

    native_report = copy.deepcopy(source_report)
    _remove_custom_visual_resource_packages(native_report)
    translated = _translate_zebra_visuals(slug, native_report)
    normalize_remaining_custom_visuals(native_report)
    return NativeLayoutSource(
        slug=slug,
        pbix_path=pbix_path,
        source_report=source_report,
        native_report=native_report,
        static_resource_parts=static_resources,
        translated_custom_visuals=translated,
        native_fallback_textboxes=_native_fallback_textbox_count(native_report),
    )


def _remove_custom_visual_resource_packages(report: dict[str, Any]) -> None:
    packages = []
    for package in report.get("resourcePackages") or []:
        resource_package = package.get("resourcePackage") or {}
        if resource_package.get("type") == 0:
            continue
        packages.append(package)
    report["resourcePackages"] = packages
    report["publicCustomVisuals"] = []


def _translate_zebra_visuals(slug: str, report: dict[str, Any]) -> int:
    catalog = load_catalog(slug)
    bind_map = BindMap()
    translated_count = 0
    for section in report.get("sections") or []:
        translated_vcs = []
        for visual in section.get("visualContainers") or []:
            out = translate_visual(visual, catalog, bind_map)
            if not (len(out) == 1 and out[0] is visual):
                translated_count += len(out)
            translated_vcs.extend(out)
        section["visualContainers"] = translated_vcs
    return translated_count


def _visual_type(visual: dict[str, Any]) -> str:
    config = visual.get("config")
    if not isinstance(config, str):
        return ""
    try:
        return (json.loads(config).get("singleVisual") or {}).get("visualType", "")
    except json.JSONDecodeError:
        return ""


def _is_custom_visual_leftover(visual_type: str) -> bool:
    return (
        visual_type.startswith("ZebraBI")
        or visual_type.startswith("zebraBi")
        or (visual_type.startswith("waterfall") and visual_type != "waterfallChart")
    )


def _custom_visual_leftover_count(report: dict[str, Any]) -> int:
    return sum(
        1
        for section in report.get("sections") or []
        for visual in section.get("visualContainers") or []
        if _is_custom_visual_leftover(_visual_type(visual))
    )


def _native_fallback_textbox_count(report: dict[str, Any]) -> int:
    total = 0
    for section in report.get("sections") or []:
        for visual in section.get("visualContainers") or []:
            if _visual_type(visual) != "textbox":
                continue
            config = visual.get("config")
            if isinstance(config, str) and "Native fallback" in config:
                total += 1
    return total


def native_layout_gate(source: NativeLayoutSource) -> NativeLayoutGate:
    missing = missing_report_refs(source.slug, source.native_report)
    measure_names = set(load_catalog(source.slug).measure_to_table)
    unresolved_measure_refs = sorted(
        {ref for ref in missing if "." in ref and ref.split(".", 1)[1] in measure_names}
    )
    extra_columns = extra_columns_for_report(source.slug, source.native_report)
    return NativeLayoutGate(
        source_pages=source.source_page_count,
        native_pages=source.native_page_count,
        source_visuals=source.source_visual_count,
        native_visuals=source.native_visual_count,
        translated_custom_visuals=source.translated_custom_visuals,
        native_fallback_textboxes=source.native_fallback_textboxes,
        static_resource_parts=len(source.static_resource_parts),
        custom_visual_leftovers=_custom_visual_leftover_count(source.native_report),
        custom_resource_parts=sum(
            1 for path in source.static_resource_parts if path.startswith("CustomVisuals/")
        ),
        extra_columns=sum(len(cols) for cols in extra_columns.values()),
        unresolved_measure_refs=unresolved_measure_refs,
    )


def _b64_payload(value: str | dict[str, Any] | bytes) -> str:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, dict):
        raw = json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")
    else:
        raw = value.encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def _definition(parts: dict[str, str | dict[str, Any] | bytes], fmt: str) -> dict[str, Any]:
    return {
        "format": fmt,
        "parts": [
            {"path": path, "payload": _b64_payload(payload), "payloadType": "InlineBase64"}
            for path, payload in parts.items()
        ],
    }


def build_report_platform(report_name: str, slug: str) -> dict[str, Any]:
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/"
            "gitIntegration/platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": "Report",
            "displayName": report_name,
            "description": f"Full-layout native Power BI conversion for Zebra template {slug}.",
        },
        "config": {
            "version": "2.0",
            "logicalId": "00000000-0000-0000-0000-000000000000",
        },
    }


def report_definition_parts(
    *,
    source: NativeLayoutSource,
    report_name: str,
    model_name: str,
    model_id: str,
    workspace_display_name: str,
) -> dict[str, str | dict[str, Any] | bytes]:
    parts: dict[str, str | dict[str, Any] | bytes] = {
        "definition.pbir": build_definition_pbir(workspace_display_name, model_name, model_id),
        "report.json": json.dumps(source.native_report, indent=2, ensure_ascii=False),
        ".platform": build_report_platform(report_name, source.slug),
    }
    parts.update(dict(sorted(source.static_resource_parts.items())))
    return parts


def publish_template(
    *,
    token: str,
    slug: str,
    source_dir: Path,
    workspace_display_name: str,
) -> PublishedNativeLayoutTemplate:
    source = load_native_layout_source(slug, source_dir)
    gate = native_layout_gate(source)
    if not gate.publishable:
        raise RuntimeError(f"{slug}: native-layout gate failed: {gate}")

    model_name = f"sm_zbr_native_layout_{slug}"
    report_name = f"zbr_native_layout_{slug}"
    extra_columns = extra_columns_for_report(slug, source.native_report)

    sm_parts = emit_tmdl_parts(slug, display_name=model_name, extra_columns=extra_columns)
    sm_id = create_or_update_item(
        token=token,
        item_type="SemanticModel",
        display_name=model_name,
        definition=_definition(sm_parts, "TMDL"),
        description=f"Blank semantic model for full-layout native Zebra conversion {slug}.",
    )
    report_id = create_or_update_item(
        token=token,
        item_type="Report",
        display_name=report_name,
        definition=_definition(
            report_definition_parts(
                source=source,
                report_name=report_name,
                model_name=model_name,
                model_id=sm_id,
                workspace_display_name=workspace_display_name,
            ),
            "PBIR-Legacy",
        ),
        description=f"Full-layout native Power BI conversion for Zebra template {slug}.",
    )
    return PublishedNativeLayoutTemplate(
        slug=slug,
        semantic_model_id=sm_id,
        report_id=report_id,
        url=f"https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{report_id}",
        page_count=source.native_page_count,
        visual_count=source.native_visual_count,
        static_resource_parts=len(source.static_resource_parts),
        translated_custom_visuals=source.translated_custom_visuals,
        measure_count=measure_count(slug),
    )


def write_summary(row: PublishedNativeLayoutTemplate) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    existing[row.slug] = {
        "semantic_model_id": row.semantic_model_id,
        "report_id": row.report_id,
        "url": row.url,
        "page_count": row.page_count,
        "visual_count": row.visual_count,
        "static_resource_parts": row.static_resource_parts,
        "translated_custom_visuals": row.translated_custom_visuals,
        "measure_count": row.measure_count,
    }
    OUT_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def load_summary(slug: str) -> dict[str, Any]:
    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return data[slug]


def _decode_part_text(part: dict[str, Any]) -> str:
    return base64.b64decode(part["payload"]).decode("utf-8")


def _parts_by_path(definition: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        part["path"]: part
        for part in definition.get("definition", {}).get("parts", [])
        if isinstance(part.get("path"), str)
    }


def verify_definition_parts(
    *,
    source: NativeLayoutSource,
    definition: dict[str, Any],
    report_id: str,
    semantic_model_id: str,
) -> NativeLayoutVerifyResult:
    parts = _parts_by_path(definition)
    live_report = json.loads(_decode_part_text(parts["report.json"]))
    definition_pbir = _decode_part_text(parts["definition.pbir"])
    live_static_resources = {
        path for path in parts if path.startswith("StaticResources/")
    }
    live_custom_resources = {
        path for path in parts if path.startswith("CustomVisuals/")
    }
    return NativeLayoutVerifyResult(
        slug=source.slug,
        report_id=report_id,
        format=definition.get("definition", {}).get("format", ""),
        source_pages=source.native_page_count,
        live_pages=len(live_report.get("sections") or []),
        source_visuals=source.native_visual_count,
        live_visuals=_visual_count(live_report),
        source_static_resource_parts=len(source.static_resource_parts),
        live_static_resource_parts=len(live_static_resources),
        live_custom_resource_parts=len(live_custom_resources),
        live_custom_visual_leftovers=_custom_visual_leftover_count(live_report),
        semantic_model_id_present=semantic_model_id in definition_pbir,
    )


def verify_live_template(slug: str, source_dir: Path) -> NativeLayoutVerifyResult:
    summary = load_summary(slug)
    source = load_native_layout_source(slug, source_dir)
    definition = get_item_definition(_token(), summary["report_id"])
    return verify_definition_parts(
        source=source,
        definition=definition,
        report_id=summary["report_id"],
        semantic_model_id=summary["semantic_model_id"],
    )


def write_verify_result(result: NativeLayoutVerifyResult) -> None:
    path = REPO_ROOT / f"data/zebra_kg/published/native_layout_{result.slug}_verify.json"
    path.write_text(json.dumps(result.__dict__, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--template", default="sales-funnel-power-bi-template")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--workspace-id", default=WORKSPACE_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-live", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import scripts.sales.rw_zebra_kg_publish_all_templates as native_publish

    native_publish.WORKSPACE_ID = args.workspace_id
    global WORKSPACE_ID
    WORKSPACE_ID = args.workspace_id

    if args.verify_live:
        result = verify_live_template(args.template, args.source_dir)
        write_verify_result(result)
        print(
            f"{result.slug} native_layout_verify={'pass' if result.passed else 'fail'} "
            f"format={result.format} pages={result.live_pages}/{result.source_pages} "
            f"visuals={result.live_visuals}/{result.source_visuals} "
            f"static_resources={result.live_static_resource_parts}/{result.source_static_resource_parts} "
            f"custom_resources={result.live_custom_resource_parts} "
            f"custom_visual_leftovers={result.live_custom_visual_leftovers} "
            f"semantic_model_bound={result.semantic_model_id_present}"
        )
        if not result.passed:
            raise SystemExit(3)
        return

    source = load_native_layout_source(args.template, args.source_dir)
    gate = native_layout_gate(source)
    print(
        f"{source.slug} pages={gate.native_pages}/{gate.source_pages} "
        f"visuals={gate.native_visuals}/{gate.source_visuals} "
        f"translated_custom_visuals={gate.translated_custom_visuals} "
        f"fallback_textboxes={gate.native_fallback_textboxes} "
        f"static_resources={gate.static_resource_parts} "
        f"custom_visual_leftovers={gate.custom_visual_leftovers} "
        f"custom_resource_parts={gate.custom_resource_parts} "
        f"extra_cols={gate.extra_columns} "
        f"unresolved_measure_refs={len(gate.unresolved_measure_refs)}"
    )
    if not gate.publishable:
        raise SystemExit(2)
    if args.dry_run:
        return

    token = _token()
    row = publish_template(
        token=token,
        slug=args.template,
        source_dir=args.source_dir,
        workspace_display_name=workspace_name(token),
    )
    write_summary(row)
    print(row.url)


if __name__ == "__main__":
    main()
