"""Publish one Zebra template as a full-layout fidelity lab report.

This is deliberately separate from ``rw_zebra_kg_publish_all_templates``. The
native publisher translates mined Zebra visual fragments into native visuals.
This publisher preserves the source PBIX report frame: pages, all
visualContainers, static resources, and custom visual packages.

Names:
  SemanticModel: sm_zbr_fidelity_<slug>
  Report:        zbr_fidelity_<slug>

Start with one template and inspect it before expanding the lane.
"""

from __future__ import annotations

import argparse
import base64
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from scripts.sales.rw_zebra_kg_publish_all_templates import (
    FABRIC,
    WORKSPACE_ID,
    build_definition_pbir,
    create_or_update_item,
    extra_columns_for_report,
    list_items,
    missing_report_refs,
    workspace_name,
    _headers,
    _token,
)
from scripts.sales.rw_zebra_kg_test_dashboard import load_catalog
from scripts.sales.rw_zebra_kg_tmdl_emit import REPO_ROOT, emit_tmdl_parts, measure_count

DEFAULT_SOURCE_DIR = (
    Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/pbix-extracted"
)
OUT_PATH = REPO_ROOT / "data/zebra_kg/published/fidelity_templates.json"


@dataclass(frozen=True)
class FidelitySource:
    slug: str
    pbix_path: Path
    report: dict[str, Any]
    resource_parts: dict[str, bytes]

    @property
    def page_count(self) -> int:
        return len(self.report.get("sections") or [])

    @property
    def visual_count(self) -> int:
        return sum(len(section.get("visualContainers") or []) for section in self.report.get("sections") or [])


@dataclass(frozen=True)
class FidelityGate:
    source_pages: int
    source_visuals: int
    resource_parts: int
    custom_visual_parts: int
    static_resource_parts: int
    extra_columns: int
    unresolved_measure_refs: list[str]

    @property
    def publishable(self) -> bool:
        return not self.unresolved_measure_refs


@dataclass(frozen=True)
class PublishedFidelityTemplate:
    slug: str
    semantic_model_id: str
    report_id: str
    url: str
    page_count: int
    visual_count: int
    resource_parts: int
    measure_count: int


@dataclass(frozen=True)
class LiveVerifyResult:
    slug: str
    report_id: str
    format: str
    source_pages: int
    live_pages: int
    source_visuals: int
    live_visuals: int
    source_resource_parts: int
    live_resource_parts: int
    missing_resource_parts: list[str]
    extra_resource_parts: list[str]
    semantic_model_id_present: bool

    @property
    def passed(self) -> bool:
        return (
            self.source_pages == self.live_pages
            and self.source_visuals == self.live_visuals
            and not self.missing_resource_parts
            and self.semantic_model_id_present
        )


def load_fidelity_source(slug: str, source_dir: Path = DEFAULT_SOURCE_DIR) -> FidelitySource:
    pbix_path = source_dir.expanduser() / f"{slug}.pbix"
    if not pbix_path.exists():
        raise FileNotFoundError(f"missing extracted PBIX: {pbix_path}")

    with zipfile.ZipFile(pbix_path) as pbix:
        report = json.loads(pbix.read("Report/Layout").decode("utf-16-le"))
        sanitize_report_layout(report)
        resources = {
            member.removeprefix("Report/"): pbix.read(member)
            for member in pbix.namelist()
            if _is_report_resource(member)
        }
    return FidelitySource(slug=slug, pbix_path=pbix_path, report=report, resource_parts=resources)


def _is_report_resource(member: str) -> bool:
    return member.startswith("Report/StaticResources/") or member.startswith(
        "Report/CustomVisuals/"
    )


def sanitize_report_layout(report: dict[str, Any]) -> None:
    """Strip license-like object groups while preserving source layout geometry."""
    for section in report.get("sections") or []:
        for visual in section.get("visualContainers") or []:
            config = visual.get("config")
            if not isinstance(config, str):
                continue
            try:
                parsed = json.loads(config)
            except json.JSONDecodeError:
                continue
            single_visual = parsed.get("singleVisual") or {}
            _strip_license_groups(single_visual.get("objects"))
            visual["config"] = json.dumps(parsed, ensure_ascii=False)


def _strip_license_groups(objects: Any) -> None:
    if not isinstance(objects, dict):
        return
    for key in list(objects):
        lowered = key.lower()
        if "license" in lowered or "activation" in lowered:
            objects.pop(key, None)


def fidelity_gate(source: FidelitySource) -> FidelityGate:
    missing = missing_report_refs(source.slug, source.report)
    measure_names = set(load_catalog(source.slug).measure_to_table)
    unresolved_measure_refs = sorted(
        {ref for ref in missing if "." in ref and ref.split(".", 1)[1] in measure_names}
    )
    extra_columns = extra_columns_for_report(source.slug, source.report)
    return FidelityGate(
        source_pages=source.page_count,
        source_visuals=source.visual_count,
        resource_parts=len(source.resource_parts),
        custom_visual_parts=sum(1 for path in source.resource_parts if path.startswith("CustomVisuals/")),
        static_resource_parts=sum(1 for path in source.resource_parts if path.startswith("StaticResources/")),
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
            {
                "path": path,
                "payload": _b64_payload(payload),
                "payloadType": "InlineBase64",
            }
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
            "description": f"Full-layout Zebra BI fidelity lab report for {slug}.",
        },
        "config": {
            "version": "2.0",
            "logicalId": "00000000-0000-0000-0000-000000000000",
        },
    }


def report_definition_parts(
    *,
    source: FidelitySource,
    report_name: str,
    model_name: str,
    model_id: str,
    workspace_display_name: str,
) -> dict[str, str | dict[str, Any] | bytes]:
    parts: dict[str, str | dict[str, Any] | bytes] = {
        "definition.pbir": build_definition_pbir(workspace_display_name, model_name, model_id),
        "report.json": json.dumps(source.report, indent=2, ensure_ascii=False),
        ".platform": build_report_platform(report_name, source.slug),
    }
    parts.update(dict(sorted(source.resource_parts.items())))
    return parts


def publish_template(
    *,
    token: str,
    slug: str,
    source_dir: Path,
    workspace_display_name: str,
) -> PublishedFidelityTemplate:
    source = load_fidelity_source(slug, source_dir)
    gate = fidelity_gate(source)
    if not gate.publishable:
        sample = ", ".join(gate.unresolved_measure_refs[:12])
        raise RuntimeError(f"{slug}: unresolved measure refs block fidelity publish: {sample}")

    extra_columns = extra_columns_for_report(slug, source.report)
    model_name = f"sm_zbr_fidelity_{slug}"
    report_name = f"zbr_fidelity_{slug}"

    sm_parts = emit_tmdl_parts(slug, display_name=model_name, extra_columns=extra_columns)
    sm_id = create_or_update_item(
        token=token,
        item_type="SemanticModel",
        display_name=model_name,
        definition=_definition(sm_parts, "TMDL"),
        description=f"Blank semantic model for Zebra fidelity lab template {slug}.",
    )

    rpt_parts = report_definition_parts(
        source=source,
        report_name=report_name,
        model_name=model_name,
        model_id=sm_id,
        workspace_display_name=workspace_display_name,
    )
    report_id = create_or_update_item(
        token=token,
        item_type="Report",
        display_name=report_name,
        definition=_definition(rpt_parts, "PBIR-Legacy"),
        description=f"Full-layout Zebra BI fidelity lab report for {slug}.",
    )
    return PublishedFidelityTemplate(
        slug=slug,
        semantic_model_id=sm_id,
        report_id=report_id,
        url=f"https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{report_id}",
        page_count=source.page_count,
        visual_count=source.visual_count,
        resource_parts=len(source.resource_parts),
        measure_count=measure_count(slug),
    )


def write_summary(row: PublishedFidelityTemplate) -> None:
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
        "resource_parts": row.resource_parts,
        "measure_count": row.measure_count,
    }
    OUT_PATH.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def load_summary(slug: str) -> dict[str, Any]:
    if not OUT_PATH.exists():
        raise FileNotFoundError(f"missing fidelity summary: {OUT_PATH}")
    data = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    if slug not in data:
        raise KeyError(f"{slug} not in {OUT_PATH}")
    return data[slug]


def get_item_definition(token: str, item_id: str) -> dict[str, Any]:
    resp = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/items/{item_id}/getDefinition",
        headers=_headers(token),
    )
    if resp.status_code in (200, 201):
        return resp.json()
    if resp.status_code != 202:
        raise RuntimeError(f"getDefinition failed {resp.status_code}: {resp.text[:1200]}")

    location = resp.headers.get("Location")
    operation_id = resp.headers.get("x-ms-operation-id")
    if not location:
        location = f"{FABRIC}/v1/operations/{operation_id}"
    retry_after = int(resp.headers.get("Retry-After", 3))

    while True:
        time.sleep(retry_after)
        poll = requests.get(location, headers=_headers(token))
        if poll.status_code == 401 and "TokenExpired" in poll.text:
            token = _token()
            poll = requests.get(location, headers=_headers(token))
        if poll.status_code >= 400:
            raise RuntimeError(f"getDefinition poll failed {poll.status_code}: {poll.text[:1200]}")
        body = poll.json() if poll.text else {}
        if body.get("status") == "Succeeded":
            result = requests.get(f"{location}/result", headers=_headers(token))
            if result.status_code == 404 and operation_id:
                result = requests.get(
                    f"{FABRIC}/v1/operations/{operation_id}/result",
                    headers=_headers(token),
                )
            if result.status_code >= 400:
                raise RuntimeError(
                    f"getDefinition result failed {result.status_code}: {result.text[:1200]}"
                )
            return result.json()
        if body.get("status") == "Failed":
            raise RuntimeError(f"getDefinition LRO failed: {json.dumps(body)[:1600]}")


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
    source: FidelitySource,
    definition: dict[str, Any],
    report_id: str,
    semantic_model_id: str,
) -> LiveVerifyResult:
    parts = _parts_by_path(definition)
    if "report.json" not in parts:
        raise RuntimeError("live report definition has no report.json part")
    if "definition.pbir" not in parts:
        raise RuntimeError("live report definition has no definition.pbir part")

    live_report = json.loads(_decode_part_text(parts["report.json"]))
    definition_pbir = _decode_part_text(parts["definition.pbir"])
    source_resources = set(source.resource_parts)
    live_resources = {
        path
        for path in parts
        if path.startswith("StaticResources/") or path.startswith("CustomVisuals/")
    }
    return LiveVerifyResult(
        slug=source.slug,
        report_id=report_id,
        format=definition.get("definition", {}).get("format", ""),
        source_pages=source.page_count,
        live_pages=len(live_report.get("sections") or []),
        source_visuals=source.visual_count,
        live_visuals=sum(
            len(section.get("visualContainers") or [])
            for section in live_report.get("sections") or []
        ),
        source_resource_parts=len(source_resources),
        live_resource_parts=len(live_resources),
        missing_resource_parts=sorted(source_resources - live_resources),
        extra_resource_parts=sorted(live_resources - source_resources),
        semantic_model_id_present=semantic_model_id in definition_pbir,
    )


def verify_live_template(slug: str, source_dir: Path) -> LiveVerifyResult:
    summary = load_summary(slug)
    source = load_fidelity_source(slug, source_dir)
    definition = get_item_definition(_token(), summary["report_id"])
    return verify_definition_parts(
        source=source,
        definition=definition,
        report_id=summary["report_id"],
        semantic_model_id=summary["semantic_model_id"],
    )


def write_verify_result(result: LiveVerifyResult) -> None:
    path = REPO_ROOT / f"data/zebra_kg/published/fidelity_{result.slug}_verify.json"
    path.write_text(json.dumps(result.__dict__, indent=2) + "\n", encoding="utf-8")


def _smoke_existing_items() -> str:
    token = _token()
    report_names = sorted(
        item.get("displayName", "")
        for item in list_items(token, "Report")
        if str(item.get("displayName", "")).startswith("zbr_fidelity_")
    )
    return "\n".join(report_names)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--template", default="sales-funnel-power-bi-template")
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--workspace-id", default=WORKSPACE_ID)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verify-live", action="store_true")
    parser.add_argument("--list-existing", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_existing:
        print(_smoke_existing_items())
        return

    import scripts.sales.rw_zebra_kg_publish_all_templates as native_publish

    native_publish.WORKSPACE_ID = args.workspace_id
    global WORKSPACE_ID
    WORKSPACE_ID = args.workspace_id

    if args.verify_live:
        result = verify_live_template(args.template, args.source_dir)
        write_verify_result(result)
        print(
            f"{result.slug} live_verify={'pass' if result.passed else 'fail'} "
            f"format={result.format} pages={result.live_pages}/{result.source_pages} "
            f"visuals={result.live_visuals}/{result.source_visuals} "
            f"resources={result.live_resource_parts}/{result.source_resource_parts} "
            f"missing_resources={len(result.missing_resource_parts)} "
            f"semantic_model_bound={result.semantic_model_id_present}"
        )
        if not result.passed:
            raise SystemExit(3)
        return

    source = load_fidelity_source(args.template, args.source_dir)
    gate = fidelity_gate(source)
    print(
        f"{source.slug} pages={gate.source_pages} visuals={gate.source_visuals} "
        f"resources={gate.resource_parts} custom_visual_parts={gate.custom_visual_parts} "
        f"static_resources={gate.static_resource_parts} extra_cols={gate.extra_columns} "
        f"unresolved_measure_refs={len(gate.unresolved_measure_refs)}"
    )
    if gate.unresolved_measure_refs:
        print("blocked unresolved measure refs:")
        for ref in gate.unresolved_measure_refs[:25]:
            print(f"  {ref}")
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
