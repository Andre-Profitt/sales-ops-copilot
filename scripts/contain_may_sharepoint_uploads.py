#!/usr/bin/env python3
"""Quarantine May 2026 SharePoint deck uploads while publish gates are rerun."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

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
    / context_for_period(DEFAULT_PERIOD).sharepoint_containment_manifest_name
)


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
    return requests.get(
        f"{GRAPH_BASE}/drives/{drive_id}/{suffix}",
        headers=_headers(token),
        timeout=120,
    )


def _children(token: str, drive_id: str, folder: str) -> list[dict[str, Any]]:
    response = requests.get(
        f"{GRAPH_BASE}/drives/{drive_id}/root:/{folder}:/children"
        "?$select=id,name,size,lastModifiedDateTime,webUrl,file,folder",
        headers=_headers(token),
        timeout=120,
    )
    response.raise_for_status()
    return response.json().get("value", [])


def ensure_folder(token: str, drive_id: str, folder: str) -> dict[str, Any]:
    current = ""
    item: dict[str, Any] | None = None
    for segment in [part for part in folder.split("/") if part]:
        candidate = f"{current}/{segment}" if current else segment
        response = _graph_get(token, drive_id, candidate)
        if response.status_code == 200:
            item = response.json()
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
        item = created.json() if created.text else _graph_get(token, drive_id, candidate).json()
        current = candidate
    if item is None:
        raise RuntimeError(f"could not resolve folder: {folder}")
    return item


def move_item(token: str, drive_id: str, item_id: str, target_folder_id: str) -> dict[str, Any]:
    response = requests.patch(
        f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}",
        headers={**_headers(token), "Content-Type": "application/json"},
        json={"parentReference": {"id": target_folder_id}},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def upload_text(token: str, drive_id: str, path: str, text: str) -> dict[str, Any]:
    response = requests.put(
        f"{GRAPH_BASE}/drives/{drive_id}/root:/{path}:/content",
        headers={**_headers(token), "Content-Type": "text/plain"},
        data=text.encode("utf-8"),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def should_quarantine(item: dict[str, Any], suffixes: tuple[str, ...]) -> bool:
    if "file" not in item:
        return False
    name = str(item.get("name") or "")
    return any(name.endswith(suffix) for suffix in suffixes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--drive-id", default=DEFAULT_DRIVE_ID)
    parser.add_argument("--folder")
    parser.add_argument("--token", default=None)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()

    context = context_for_period(args.period)
    folder = args.folder or context.sharepoint_folder
    manifest_path = args.manifest or (
        ROOT / "state" / args.period / "__regional__" / context.sharepoint_containment_manifest_name
    )
    token = graph_token(args.token)
    now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    quarantine_name = f"_DRAFT_DO_NOT_USE_quarantined_{now}"
    quarantine_folder = f"{folder}/{quarantine_name}"
    items = _children(token, args.drive_id, folder)
    targets = [item for item in items if should_quarantine(item, context.sharepoint_publish_suffixes)]

    manifest: dict[str, Any] = {
        "status": "planned",
        "drive_id": args.drive_id,
        "folder": folder,
        "quarantine_folder": quarantine_folder,
        "period": args.period,
        "month_label": context.month_label,
        "execute": args.execute,
        "target_count": len(targets),
        "targets": [
            {
                "id": item["id"],
                "name": item["name"],
                "size": item.get("size"),
                "lastModifiedDateTime": item.get("lastModifiedDateTime"),
                "webUrl": item.get("webUrl"),
            }
            for item in targets
        ],
        "moved": [],
        "warning_file": None,
    }

    if args.execute:
        quarantine_item = ensure_folder(token, args.drive_id, quarantine_folder)
        for item in targets:
            moved = move_item(token, args.drive_id, item["id"], quarantine_item["id"])
            manifest["moved"].append(
                {
                    "name": moved.get("name"),
                    "id": moved.get("id"),
                    "webUrl": moved.get("webUrl"),
                    "parentReference": moved.get("parentReference"),
                }
            )
        warning = (
            f"{context.month_label} Sales Director deck assets were temporarily pulled for QA on "
            f"{now}. Do not use prior files until corrected/publish-gated copies are "
            "uploaded to this folder.\n"
        )
        warning_item = upload_text(
            token,
            args.drive_id,
            f"{folder}/{context.sharepoint_warning_filename}",
            warning,
        )
        manifest["warning_file"] = {
            "name": warning_item.get("name"),
            "id": warning_item.get("id"),
            "webUrl": warning_item.get("webUrl"),
        }
        manifest["status"] = "ok"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
