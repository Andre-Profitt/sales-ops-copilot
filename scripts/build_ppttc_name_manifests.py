#!/usr/bin/env python3
"""Build expected-name manifests from wired think-cell PowerPoint templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ppttc_template import template_named_elements

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "assets" / "thinkcell_manifests"
DEFAULT_TEMPLATES = (
    ROOT / "assets" / "LAND_thinkcell_seed.pptx",
    ROOT / "assets" / "LAND_thinkcell_seed_charts.pptx",
    ROOT / "assets" / "LAND_thinkcell_table_image_donor.pptx",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _slug(path: Path) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem).strip("-")


def build_manifest(template: Path, *, root: Path = ROOT, generated_at: str | None = None) -> dict[str, Any]:
    template = template.expanduser().resolve()
    names = sorted(template_named_elements(template))
    try:
        template_rel = str(template.relative_to(root))
    except ValueError:
        template_rel = str(template)
    return {
        "schema": "thinkcell-ppttc-expected-names/v1",
        "generated_at_utc": generated_at or _utc_now(),
        "template_path": str(template),
        "template_path_relative": template_rel,
        "template_filename": template.name,
        "template_sha256": _sha256(template),
        "expected_name_count": len(names),
        "expected_names": names,
    }


def write_manifest(
    template: Path,
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    allow_empty: bool = False,
    root: Path = ROOT,
    generated_at: str | None = None,
) -> Path:
    manifest = build_manifest(template, root=root, generated_at=generated_at)
    if not manifest["expected_names"] and not allow_empty:
        raise SystemExit(f"{template}: no think-cell automation names found")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{_slug(template)}.expected-names.json"
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "templates",
        nargs="*",
        type=Path,
        help="Wired PowerPoint templates to inspect. Defaults to known LAND assets.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated expected-name manifests.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Write a manifest even if a template has no discoverable names.",
    )
    args = parser.parse_args()

    templates = tuple(args.templates) if args.templates else DEFAULT_TEMPLATES
    outputs = [
        write_manifest(
            template,
            output_dir=args.output_dir,
            allow_empty=args.allow_empty,
        )
        for template in templates
    ]
    for path in outputs:
        print(path)
    print(f"built {len(outputs)} expected-name manifest(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
