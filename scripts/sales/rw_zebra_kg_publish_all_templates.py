"""Publish all extracted Zebra templates as native Power BI reports in Fabric.

Path B:
  1. Emit one blank SemanticModel per Zebra template from
     data/zebra_kg/schemas/<slug>/.
  2. Translate the template's Zebra visualContainers to native PBIR-Legacy.
  3. Publish one Report bound to that matching SemanticModel.

Names:
  SemanticModel: sm_zbr_<slug>
  Report:        zbr_<slug>
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from azure.identity import AzureCliCredential

from scripts.sales._pbir_helpers import build_textbox_visual
from scripts.sales.rw_zebra_kg_test_dashboard import (
    list_templates,
    load_catalog,
    load_raw_rows,
    raw_to_layout_vc,
)
from scripts.sales.rw_zebra_kg_tmdl_emit import (
    REPO_ROOT,
    SCHEMAS_DIR,
    column_catalog,
    emit_tmdl_parts,
    measure_count,
)
from scripts.sales.rw_zebra_kg_translator import BindMap, translate_visual

FABRIC = "https://api.fabric.microsoft.com"
FABRIC_RES = "https://api.fabric.microsoft.com/.default"
WORKSPACE_ID = "b66233d5-9d4a-44ba-89a8-b70206d98ae7"
OUT_PATH = REPO_ROOT / "data/zebra_kg/published/all_templates.json"


@dataclass(frozen=True)
class PublishedTemplate:
    slug: str
    semantic_model_id: str
    report_id: str
    url: str
    vc_count: int
    measure_count: int


def _b64(text: str | dict) -> str:
    if isinstance(text, dict):
        text = json.dumps(text, indent=2, ensure_ascii=False)
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _token() -> str:
    return AzureCliCredential().get_token(FABRIC_RES).token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _wait_lro(resp: requests.Response, token: str) -> dict[str, Any]:
    if resp.status_code in (200, 201):
        return resp.json() if resp.text else {}
    if resp.status_code != 202:
        raise RuntimeError(f"Fabric REST {resp.status_code}: {resp.text[:1200]}")

    location = resp.headers.get("Location")
    op_id = resp.headers.get("x-ms-operation-id")
    if not location:
        location = f"{FABRIC}/v1/operations/{op_id}"
    retry_after = int(resp.headers.get("Retry-After", 3))
    while True:
        time.sleep(retry_after)
        poll = requests.get(location, headers=_headers(token))
        if poll.status_code == 401 and "TokenExpired" in poll.text:
            token = _token()
            poll = requests.get(location, headers=_headers(token))
        if poll.status_code >= 400:
            raise RuntimeError(f"LRO poll {poll.status_code}: {poll.text[:1200]}")
        body = poll.json() if poll.text else {}
        status = body.get("status")
        if status == "Succeeded":
            result_url = f"{location}/result"
            result = requests.get(result_url, headers=_headers(token))
            if result.status_code == 404 and op_id:
                result = requests.get(
                    f"{FABRIC}/v1/operations/{op_id}/result", headers=_headers(token)
                )
            if result.status_code in (200, 201):
                return result.json() if result.text else {}
            return body
        if status == "Failed":
            raise RuntimeError(f"LRO failed: {json.dumps(body, indent=2)[:1600]}")


def _definition(parts: dict[str, str], fmt: str) -> dict[str, Any]:
    return {
        "format": fmt,
        "parts": [
            {"path": path, "payload": _b64(text), "payloadType": "InlineBase64"}
            for path, text in parts.items()
        ],
    }


def list_items(token: str, item_type: str) -> list[dict[str, Any]]:
    url = f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/items?type={item_type}"
    out: list[dict[str, Any]] = []
    while url:
        resp = requests.get(url, headers=_headers(token))
        if resp.status_code >= 400:
            raise RuntimeError(f"list {item_type} failed {resp.status_code}: {resp.text[:1200]}")
        body = resp.json() if resp.text else {}
        out.extend(body.get("value", []))
        url = body.get("continuationUri")
    return out


def find_item(token: str, item_type: str, display_name: str) -> str | None:
    for item in list_items(token, item_type):
        if item.get("displayName") == display_name:
            return item.get("id")
    return None


def workspace_name(token: str) -> str:
    resp = requests.get(f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}", headers=_headers(token))
    if resp.status_code >= 400:
        raise RuntimeError(f"workspace get failed {resp.status_code}: {resp.text[:1200]}")
    return resp.json()["displayName"]


def create_or_update_item(
    *,
    token: str,
    item_type: str,
    display_name: str,
    definition: dict[str, Any],
    description: str,
) -> str:
    existing = find_item(token, item_type, display_name)
    if existing:
        resp = requests.post(
            f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/items/{existing}/updateDefinition"
            "?updateMetadata=true",
            headers=_headers(token),
            json={"definition": definition},
        )
        _wait_lro(resp, token)
        return existing

    resp = requests.post(
        f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/items",
        headers=_headers(token),
        json={
            "displayName": display_name,
            "type": item_type,
            "description": description[:256],
            "definition": definition,
        },
    )
    result = _wait_lro(resp, token)
    item_id = result.get("id") or result.get("item", {}).get("id")
    if not item_id:
        found = find_item(token, item_type, display_name)
        if found:
            return found
        raise RuntimeError(f"create {item_type} returned no id: {json.dumps(result)[:1200]}")
    return item_id


def build_definition_pbir(workspace_display_name: str, model_name: str, model_id: str) -> dict:
    connection_string = (
        f'Data Source="powerbi://api.powerbi.com/v1.0/myorg/{workspace_display_name}";'
        f"initial catalog={model_name};"
        f"integrated security=ClaimsToken;"
        f"semanticmodelid={model_id}"
    )
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/item/report/"
            "definitionProperties/2.0.0/schema.json"
        ),
        "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString": connection_string}},
    }


def build_report_platform(report_name: str, slug: str) -> dict:
    return {
        "$schema": (
            "https://developer.microsoft.com/json-schemas/fabric/"
            "gitIntegration/platformProperties/2.0.0/schema.json"
        ),
        "metadata": {
            "type": "Report",
            "displayName": report_name,
            "description": f"Native translated Zebra BI template report for {slug}.",
        },
        "config": {
            "version": "2.0",
            "logicalId": "00000000-0000-0000-0000-000000000000",
        },
    }


def translated_report(slug: str) -> tuple[dict[str, Any], int]:
    catalog = load_catalog(slug)
    bind_map = BindMap()
    pages: dict[str, list[dict]] = {}
    for raw in load_raw_rows(slug):
        page = raw.get("page_display_name") or raw.get("page_name") or "Page"
        pages.setdefault(page, []).extend(
            translate_visual(raw_to_layout_vc(raw), catalog, bind_map)
        )
    report = build_multi_page_report(slug, pages)
    normalize_remaining_custom_visuals(report)
    return report, sum(len(vcs) for vcs in pages.values())


def _page_name(display_name: str, used: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", display_name).strip("_") or "Page"
    name = base[:60]
    while name in used:
        name = f"{base[:50]}_{uuid.uuid4().hex[:8]}"
    used.add(name)
    return name


def _clamp_visual(vc: dict[str, Any]) -> dict[str, Any]:
    """Keep source visuals inside the 1280x720 template canvas."""
    x = float(vc.get("x", 0))
    y = float(vc.get("y", 0))
    w = float(vc.get("width", 0))
    h = float(vc.get("height", 0))
    if x < 0:
        w += x
        x = 0
    if y < 0:
        h += y
        y = 0
    w = max(1, min(w, 1280 - x))
    h = max(1, min(h, 720 - y))
    vc["x"], vc["y"], vc["width"], vc["height"] = x, y, w, h
    config = vc.get("config")
    if isinstance(config, str):
        try:
            cfg = json.loads(config)
            position = cfg.get("layouts", [{}])[0].get("position")
            if isinstance(position, dict):
                position.update({"x": x, "y": y, "width": w, "height": h})
                vc["config"] = json.dumps(cfg, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return vc


def build_multi_page_report(slug: str, pages: dict[str, list[dict]]) -> dict[str, Any]:
    used: set[str] = set()
    sections = []
    for ordinal, (display_name, vcs) in enumerate(pages.items()):
        sections.append(
            {
                "name": _page_name(display_name, used),
                "displayName": display_name,
                "displayOption": 1,
                "filters": "[]",
                "height": 720,
                "width": 1280,
                "ordinal": ordinal,
                "visualContainers": [_clamp_visual(vc) for vc in vcs],
                "config": json.dumps({"visibility": 0}),
            }
        )
    return {
        "config": json.dumps(
            {
                "version": "5.43",
                "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
                "activeSectionIndex": 0,
                "defaultDrillFilterOtherVisuals": True,
                "linguisticSchemaSyncVersion": 0,
                "settings": {"useStylableVisualContainerHeader": True},
            }
        ),
        "layoutOptimization": 0,
        "resourcePackages": [],
        "sections": sections,
    }


def _is_untranslated_custom_visual(visual_type: str) -> bool:
    return (
        visual_type.startswith("ZebraBI")
        or visual_type.startswith("zebraBi")
        or (visual_type.startswith("waterfall") and visual_type != "waterfallChart")
    )


def normalize_remaining_custom_visuals(report: dict[str, Any]) -> None:
    """Replace rare untranslatable Zebra custom visual leftovers with textboxes.

    This publish path intentionally ships native Power BI reports without
    custom visual packages. If a source visual cannot resolve enough fields for
    the translator to synthesize a native equivalent, keep the canvas footprint
    and remove the unresolved field bindings so Fabric does not render
    field-not-found placeholders.
    """
    for section in report.get("sections", []):
        replaced: list[dict[str, Any]] = []
        for vc in section.get("visualContainers", []):
            config = vc.get("config")
            visual_type = ""
            if isinstance(config, str):
                try:
                    visual_type = (json.loads(config).get("singleVisual") or {}).get(
                        "visualType", ""
                    )
                except json.JSONDecodeError:
                    visual_type = ""
            if not _is_untranslated_custom_visual(visual_type):
                replaced.append(vc)
                continue
            replaced.append(
                build_textbox_visual(
                    "Native fallback: source Zebra visual had unresolved bindings",
                    x=vc.get("x", 0),
                    y=vc.get("y", 0),
                    w=max(vc.get("width", 260), 180),
                    h=max(vc.get("height", 44), 44),
                    font_size_pt=9,
                    color="#666666",
                    bold=False,
                )
            )
        section["visualContainers"] = replaced


def _iter_query_refs(report: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for section in report.get("sections", []):
        for vc in section.get("visualContainers", []):
            config = vc.get("config")
            if not isinstance(config, str):
                continue
            try:
                cfg = json.loads(config)
            except json.JSONDecodeError:
                continue
            projections = (cfg.get("singleVisual") or {}).get("projections") or {}
            for vals in projections.values():
                for val in vals or []:
                    ref = val.get("queryRef") if isinstance(val, dict) else None
                    if isinstance(ref, str):
                        refs.append(ref)
    return refs


def validate_report_refs(slug: str, report: dict[str, Any]) -> None:
    missing = missing_report_refs(slug, report)
    if missing:
        sample = ", ".join(sorted(set(missing))[:12])
        raise RuntimeError(f"{slug}: unresolved report refs: {sample}")


def missing_report_refs(slug: str, report: dict[str, Any]) -> list[str]:
    catalog = load_catalog(slug)
    measures = {
        (table, measure)
        for measure, table in catalog.measure_to_table.items()
    }
    columns = {
        (table, column)
        for table, names in column_catalog(slug).items()
        for column in names
    }
    missing = []
    for ref in _iter_query_refs(report):
        if "." not in ref:
            continue
        table, field = ref.split(".", 1)
        if (table, field) not in measures and (table, field) not in columns:
            missing.append(ref)
    return missing


def extra_columns_for_report(slug: str, report: dict[str, Any]) -> dict[str, set[str]]:
    measure_names = set(load_catalog(slug).measure_to_table)
    extra: dict[str, set[str]] = {}
    for ref in missing_report_refs(slug, report):
        table, field = ref.split(".", 1)
        if field in measure_names:
            continue
        extra.setdefault(table, set()).add(field)
    return extra


def report_definition_parts(
    *,
    slug: str,
    report_name: str,
    model_name: str,
    model_id: str,
    workspace_display_name: str,
    report: dict[str, Any] | None = None,
    vc_count: int | None = None,
) -> tuple[dict[str, str], int]:
    if report is None or vc_count is None:
        report, vc_count = translated_report(slug)
    unresolved_measures = [
        ref
        for ref in missing_report_refs(slug, report)
        if ref.split(".", 1)[1] in set(load_catalog(slug).measure_to_table)
    ]
    if unresolved_measures:
        sample = ", ".join(sorted(set(unresolved_measures))[:12])
        raise RuntimeError(f"{slug}: unresolved measure refs after translation: {sample}")
    return (
        {
            "definition.pbir": json.dumps(
                build_definition_pbir(workspace_display_name, model_name, model_id),
                indent=2,
            ),
            "report.json": json.dumps(report, indent=2, ensure_ascii=False),
            ".platform": json.dumps(build_report_platform(report_name, slug), indent=2),
        },
        vc_count,
    )


def publish_template(token: str, slug: str, workspace_display_name: str) -> PublishedTemplate:
    model_name = f"sm_zbr_{slug}"
    report_name = f"zbr_{slug}"

    report, vc_count = translated_report(slug)
    extra_columns = extra_columns_for_report(slug, report)
    sm_parts = emit_tmdl_parts(slug, display_name=model_name, extra_columns=extra_columns)
    sm_id = create_or_update_item(
        token=token,
        item_type="SemanticModel",
        display_name=model_name,
        definition=_definition(sm_parts, "TMDL"),
        description=f"Blank semantic model for Zebra template {slug}.",
    )

    report_parts, vc_count = report_definition_parts(
        slug=slug,
        report_name=report_name,
        model_name=model_name,
        model_id=sm_id,
        workspace_display_name=workspace_display_name,
        report=report,
        vc_count=vc_count,
    )
    report_id = create_or_update_item(
        token=token,
        item_type="Report",
        display_name=report_name,
        definition=_definition(report_parts, "PBIR-Legacy"),
        description=f"Native translated Zebra template report for {slug}.",
    )
    url = f"https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/reports/{report_id}"
    return PublishedTemplate(
        slug=slug,
        semantic_model_id=sm_id,
        report_id=report_id,
        url=url,
        vc_count=vc_count,
        measure_count=measure_count(slug),
    )


def write_summary(rows: list[PublishedTemplate]) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    existing.update(
        {
            row.slug: {
                "semantic_model_id": row.semantic_model_id,
                "report_id": row.report_id,
                "url": row.url,
                "vc_count": row.vc_count,
                "measure_count": row.measure_count,
            }
            for row in rows
        }
    )
    OUT_PATH.write_text(
        json.dumps(existing, indent=2)
        + "\n",
        encoding="utf-8",
    )


def default_slugs() -> list[str]:
    return [slug for slug, _count in list_templates()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--workspace-id", default=WORKSPACE_ID)
    parser.add_argument("--template", action="append", dest="templates")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    global WORKSPACE_ID
    WORKSPACE_ID = args.workspace_id

    slugs = args.templates or default_slugs()
    if args.limit:
        slugs = slugs[: args.limit]
    missing = [slug for slug in slugs if not (SCHEMAS_DIR / slug).exists()]
    if missing:
        raise SystemExit(f"missing schema slug(s): {missing}")

    if args.dry_run:
        for slug in slugs:
            report, vc_count = translated_report(slug)
            extra_columns = extra_columns_for_report(slug, report)
            parts = emit_tmdl_parts(slug, extra_columns=extra_columns)
            unresolved_measures = [
                ref
                for ref in missing_report_refs(slug, report)
                if ref.split(".", 1)[1] in set(load_catalog(slug).measure_to_table)
            ]
            if unresolved_measures:
                sample = ", ".join(sorted(set(unresolved_measures))[:12])
                raise RuntimeError(f"{slug}: unresolved measure refs: {sample}")
            print(
                f"{slug:62s} tmdl_parts={len(parts):3d} "
                f"vcs={vc_count:3d} measures={measure_count(slug):3d} "
                f"extra_cols={sum(len(v) for v in extra_columns.values()):2d}"
            )
        return

    token = _token()
    ws_name = workspace_name(token)
    rows: list[PublishedTemplate] = []
    for slug in slugs:
        print(f"\n=== {slug} ===")
        token = _token()
        row = publish_template(token, slug, ws_name)
        rows.append(row)
        write_summary(rows)
        print(f"sm={row.semantic_model_id} report={row.url}")
    print(f"\nsummary: {OUT_PATH}")


if __name__ == "__main__":
    main()
