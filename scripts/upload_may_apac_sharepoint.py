#!/usr/bin/env python3
"""Upload May 2026 APAC deck assets to the Sales Director SharePoint folder."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_DRIVE_ID = "b!NFdN4U0FoUmZxNNOBNAFO95fRH4lEKdPm1y4Rq_UXNSNhf32U6-8R7dL79jOAP15"
DEFAULT_FOLDER = "General/Book of Business/Sales Director Reporting/Q2 2026/May 2026"
DEFAULT_DECK = ROOT / "state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.pptx"
DEFAULT_WORKBOOK = ROOT / "state/2026-Q2/Jesper-Tyrer/factory/connected/connected_factory.xlsx"
DEFAULT_MANIFEST = ROOT / "state/2026-Q2/Jesper-Tyrer/factory/sharepoint/may_2026_apac_upload_manifest.json"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drive-id", default=DEFAULT_DRIVE_ID)
    parser.add_argument("--folder", default=DEFAULT_FOLDER)
    parser.add_argument("--deck", type=Path, default=DEFAULT_DECK)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--token", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()

    deck = args.deck.expanduser().resolve()
    workbook = args.workbook.expanduser().resolve()
    assets = [
        (deck, "Jesper Tyrer APAC LAND Territory Review - May 2026.pptx"),
        (workbook, "Jesper Tyrer APAC Connected Excel Source - May 2026.xlsx"),
    ]
    missing = [str(path) for path, _ in assets if not path.exists()]
    if missing:
        raise SystemExit("missing upload asset(s): " + ", ".join(missing))

    manifest: dict[str, Any] = {
        "status": "planned" if args.dry_run else "running",
        "drive_id": args.drive_id,
        "folder": args.folder,
        "dry_run": args.dry_run,
        "planned": [
            {
                "publish_name": name,
                "source_path": str(path),
                "sharepoint_path": f"{args.folder}/{name}",
                "size_bytes": path.stat().st_size,
            }
            for path, name in assets
        ],
        "uploaded": [],
    }

    if not args.dry_run:
        token = graph_token(args.token)
        ensure_folder(token, args.drive_id, args.folder)
        for path, name in assets:
            manifest["uploaded"].append(upload_file(token, args.drive_id, args.folder, path, name))
        manifest["status"] = "ok"

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
