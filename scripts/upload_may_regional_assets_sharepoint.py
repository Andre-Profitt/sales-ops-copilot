#!/usr/bin/env python3
"""Upload all May 2026 regional Sales Director deck assets to SharePoint."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import requests

from _directors import canonical_directors
from period_context import DEFAULT_PERIOD, context_for_period


ROOT = Path(__file__).resolve().parent.parent
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_DRIVE_ID = "b!NFdN4U0FoUmZxNNOBNAFO95fRH4lEKdPm1y4Rq_UXNSNhf32U6-8R7dL79jOAP15"
DEFAULT_FOLDER = context_for_period(DEFAULT_PERIOD).sharepoint_folder
DEFAULT_MANIFEST = (
    ROOT
    / "state"
    / DEFAULT_PERIOD
    / "__regional__"
    / context_for_period(DEFAULT_PERIOD).sharepoint_upload_manifest_name
)


def slugify(value: str) -> str:
    return value.replace(" ", "-")


def graph_token(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    proc = subprocess.run(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://graph.microsoft.com",
            "--query",
            "accessToken",
            "-o",
            "tsv",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "failed to acquire Graph token via az")
    token = proc.stdout.strip()
    if not token:
        raise RuntimeError("Graph token was empty")
    return token


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _graph_get(token: str, drive_id: str, path: str) -> requests.Response:
    suffix = f"root:/{path}" if path else "root"
    return requests.get(f"{GRAPH_BASE}/drives/{drive_id}/{suffix}", headers=_headers(token), timeout=120)


def ensure_folder(token: str, drive_id: str, folder: str) -> None:
    current = ""
    for segment in [part for part in folder.split("/") if part]:
        candidate = f"{current}/{segment}" if current else segment
        response = _graph_get(token, drive_id, candidate)
        if response.status_code == 200:
            current = candidate
            continue
        if response.status_code != 404:
            response.raise_for_status()
        parent_url = (
            f"{GRAPH_BASE}/drives/{drive_id}/root/children"
            if not current
            else f"{GRAPH_BASE}/drives/{drive_id}/root:/{current}:/children"
        )
        created = requests.post(
            parent_url,
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"name": segment, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
            timeout=120,
        )
        if created.status_code not in {200, 201, 409}:
            created.raise_for_status()
        current = candidate


def upload_file(token: str, drive_id: str, folder: str, source: Path, publish_name: str) -> dict[str, Any]:
    upload_path = f"{folder}/{publish_name}"
    size = source.stat().st_size
    headers = _headers(token)
    if size < 4 * 1024 * 1024:
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{upload_path}:/content"
        with source.open("rb") as handle:
            response = requests.put(
                url,
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=handle,
                timeout=300,
            )
        response.raise_for_status()
        mode = "single_put"
    else:
        session_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{upload_path}:/createUploadSession"
        session = requests.post(
            session_url,
            headers=headers,
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=300,
        )
        session.raise_for_status()
        upload_url = session.json()["uploadUrl"]
        chunk_size = 10 * 1024 * 1024
        with source.open("rb") as handle:
            offset = 0
            while offset < size:
                chunk = handle.read(chunk_size)
                end = offset + len(chunk) - 1
                response = requests.put(
                    upload_url,
                    headers={"Content-Range": f"bytes {offset}-{end}/{size}"},
                    data=chunk,
                    timeout=300,
                )
                response.raise_for_status()
                offset += len(chunk)
        mode = "chunked"
    return {
        "publish_name": publish_name,
        "source_path": str(source),
        "sharepoint_path": upload_path,
        "size_bytes": size,
        "mode": mode,
    }


def delete_if_exists(token: str, drive_id: str, path: str) -> dict[str, Any] | None:
    response = _graph_get(token, drive_id, path)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    item = response.json()
    delete_response = requests.delete(
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item['id']}",
        headers=_headers(token),
        timeout=120,
    )
    if delete_response.status_code not in {200, 202, 204}:
        delete_response.raise_for_status()
    return {"name": item.get("name"), "id": item.get("id"), "webUrl": item.get("webUrl")}


def planned_assets(period: str) -> list[tuple[Path, str]]:
    context = context_for_period(period)
    assets: list[tuple[Path, str]] = []
    for director in canonical_directors():
        name = str(director["name"])
        territory = str(director["scope_label"])
        slug = slugify(name)
        director_dir = ROOT / "state" / period / slug
        connected_dir = director_dir / "factory" / "connected"
        deck = director_dir / "factory" / "meeting-spine" / f"{slug}-LAND-{period}-meeting-spine.pptx"
        audit_workbook = connected_dir / "connected_factory.xlsx"
        table_source_workbook = connected_dir / "connected_factory_table_images.xlsx"
        assets.append((deck, f"{name} {territory} LAND Meeting Spine - {context.month_label}.pptx"))
        assets.append((audit_workbook, f"{name} {territory} Connected Excel Audit Workbook - {context.month_label}.xlsx"))
        assets.append((table_source_workbook, f"{name} {territory} PowerPoint Table Source Workbook - {context.month_label}.xlsx"))
    report_sources = [
        ROOT / "state" / period / "__regional__" / "production_status" / "regional_production_status.md",
        ROOT / "state" / period / "__regional__" / "production_status" / "regional_production_status.json",
        ROOT / "state" / period / "__regional__" / "meeting_spine" / "meeting_spine_manifest.json",
        ROOT / "state" / period / "__regional__" / "meeting_spine" / "meeting_spine_smoke_report.md",
        ROOT / "state" / period / "__regional__" / "publish_gate" / "regional_publish_gate.md",
        ROOT / "state" / period / "__regional__" / "goal_audit" / "regional_deck_goal_audit.md",
        ROOT / "state" / period / "__regional__" / "visual_gate" / "review_package" / "review_package_visual_gate.md",
        ROOT / "state" / period / "__regional__" / "visual_gate" / "review_package" / "review_package_visual_gate.json",
        ROOT / "state" / period / "__regional__" / "sharepoint_containment_manifest.json",
        ROOT / "state" / period / "__regional__" / context.sharepoint_upload_manifest_name,
    ]
    assets.extend((path, path.name) for path in report_sources if path.exists())
    return assets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--drive-id", default=DEFAULT_DRIVE_ID)
    parser.add_argument("--folder")
    parser.add_argument("--token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    context = context_for_period(args.period)
    folder = args.folder or context.sharepoint_folder
    manifest_path = args.manifest or (
        ROOT / "state" / args.period / "__regional__" / context.sharepoint_upload_manifest_name
    )
    assets = planned_assets(args.period)
    missing = [str(path) for path, _ in assets if not path.exists()]
    if missing:
        raise SystemExit("missing upload asset(s): " + ", ".join(missing))

    manifest: dict[str, Any] = {
        "status": "planned" if args.dry_run else "running",
        "drive_id": args.drive_id,
        "folder": folder,
        "period": args.period,
        "month_label": context.month_label,
        "dry_run": args.dry_run,
        "planned": [
            {
                "publish_name": name,
                "source_path": str(path),
                "sharepoint_path": f"{folder}/{name}",
                "size_bytes": path.stat().st_size,
            }
            for path, name in assets
        ],
        "uploaded": [],
    }

    token: str | None = None
    if not args.dry_run:
        token = graph_token(args.token)
        ensure_folder(token, args.drive_id, folder)
        for path, name in assets:
            manifest["uploaded"].append(upload_file(token, args.drive_id, folder, path, name))
        warning_path = f"{folder}/{context.sharepoint_warning_filename}"
        manifest["deleted_warning"] = delete_if_exists(token, args.drive_id, warning_path)
        manifest["status"] = "ok"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if token:
        upload_file(token, args.drive_id, folder, manifest_path, manifest_path.name)
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
