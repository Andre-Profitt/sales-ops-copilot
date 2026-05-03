#!/usr/bin/env python3
"""Upload mutable May regional gate evidence after a production run."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from period_context import DEFAULT_PERIOD, context_for_period
from upload_may_regional_assets_sharepoint import (
    DEFAULT_DRIVE_ID,
    graph_token,
    upload_file,
)


ROOT = Path(__file__).resolve().parent.parent


def evidence_assets(period: str) -> list[Path]:
    regional = ROOT / "state" / period / "__regional__"
    return [
        regional / "production_status" / "regional_production_status.md",
        regional / "production_status" / "regional_production_status.json",
        regional / "visual_gate" / "review_package" / "review_package_visual_gate.md",
        regional / "visual_gate" / "review_package" / "review_package_visual_gate.json",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--drive-id", default=DEFAULT_DRIVE_ID)
    parser.add_argument("--folder")
    parser.add_argument("--token")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    context = context_for_period(args.period)
    folder = args.folder or context.sharepoint_folder
    manifest_path = args.manifest or (
        ROOT / "state" / args.period / "__regional__" / "sharepoint_evidence_upload_manifest.json"
    )
    assets = evidence_assets(args.period)
    missing = [str(path) for path in assets if not path.exists()]
    if missing:
        raise SystemExit("missing evidence asset(s): " + ", ".join(missing))

    manifest: dict[str, Any] = {
        "status": "planned" if args.dry_run else "running",
        "period": args.period,
        "month_label": context.month_label,
        "drive_id": args.drive_id,
        "folder": folder,
        "dry_run": args.dry_run,
        "planned": [
            {
                "publish_name": path.name,
                "source_path": str(path),
                "sharepoint_path": f"{folder}/{path.name}",
                "size_bytes": path.stat().st_size,
            }
            for path in assets
        ],
        "uploaded": [],
    }
    if not args.dry_run:
        token = graph_token(args.token)
        for path in assets:
            manifest["uploaded"].append(upload_file(token, args.drive_id, folder, path, path.name))
        manifest["status"] = "ok"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
