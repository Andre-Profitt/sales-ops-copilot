"""Save each Zebra template's schematic model as standalone reusable
artifacts at data/zebra_kg/schemas/<template_slug>/.

Per-template layout:
    <slug>/
      model.json           full structured model (all tables/columns/measures/rels)
      measures.csv         flat measure list with full DAX (greppable)
      relationships.json   all rels with cardinality + cross_filter + active + cols
      metadata.json        template_slug, source_pbix, pbixray_version, extraction_date
      tables/
        <table>.json       per-table: columns + measures filtered to this table

Reuses scripts.sales.rw_zebra_kg_datamodel.shape_datamodel for the actual
PBIX parse. This module just re-serializes the DataModel dataclass into
the per-template directory layout.

Usage:
    # single template (probe before scaling to 20)
    python3 -m scripts.sales.rw_zebra_kg_save_schemas \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --template sales-dashboard-power-bi-template \\
      --out-dir data/zebra_kg/schemas

    # all 20 templates (drop --template)
    python3 -m scripts.sales.rw_zebra_kg_save_schemas \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --out-dir data/zebra_kg/schemas
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from scripts.sales.rw_zebra_kg_datamodel import (
    DataModel,
    shape_datamodel,
    template_slug_from_pbix,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/files"
DEFAULT_OUT = REPO_ROOT / "data/zebra_kg/schemas"

# Filenames that are illegal or fragile on common filesystems — sanitize.
_FILE_SAFE_RE = re.compile(r"[^\w\-\. ]+")


def _safe_filename(name: str) -> str:
    """Make a string safe for use as a filename. Preserves spaces (Zebra
    table names like 'Key Measures' have them) but strips special chars."""
    safe = _FILE_SAFE_RE.sub("_", name).strip()
    return safe or "_unnamed"


def _resolve_pbix_path(path: Path, tmp_root: Path) -> Path | None:
    """Return a Path to a real .pbix file, extracting from a .zip if needed.
    Same logic as rw_zebra_kg_datamodel; reused here to keep this module
    self-contained when called on a single zip."""
    suffix = path.suffix.lower()
    if suffix == ".pbix":
        return path
    if suffix == ".zip":
        with zipfile.ZipFile(path) as zf:
            inner = next((n for n in zf.namelist() if n.lower().endswith(".pbix")), None)
            if inner is None:
                return None
            extracted = tmp_root / f"{path.stem}__{Path(inner).name}"
            with zf.open(inner) as src, extracted.open("wb") as dst:
                dst.write(src.read())
            return extracted
    return None


def serialize_model(dm: DataModel) -> dict[str, Any]:
    """Translate DataModel dataclass → plain dict for JSON output."""
    return {
        "template_slug": dm.template_slug,
        "table_count": len(dm.tables),
        "column_count": len(dm.columns),
        "measure_count": len(dm.measures),
        "relationship_count": len(dm.relationships),
        "tables": [{"name": t.name} for t in dm.tables],
        "columns": [
            {"table": c.table, "name": c.name, "data_type": c.data_type} for c in dm.columns
        ],
        "measures": [
            {
                "name": m.name,
                "table": m.table,
                "expression": m.expression,
                "format_string": m.format_string,
            }
            for m in dm.measures
        ],
        "relationships": [
            {
                "from_table": r.from_table,
                "from_col": r.from_col,
                "to_table": r.to_table,
                "to_col": r.to_col,
                "cardinality": r.cardinality,
                "cross_filter": r.cross_filter,
                "active": r.active,
            }
            for r in dm.relationships
        ],
    }


def per_table_views(dm: DataModel) -> dict[str, dict[str, Any]]:
    """Bucket columns + measures by their owning table."""
    tables_by_name: dict[str, dict[str, Any]] = {
        t.name: {"name": t.name, "columns": [], "measures": []} for t in dm.tables
    }
    for c in dm.columns:
        tables_by_name.setdefault(c.table, {"name": c.table, "columns": [], "measures": []})[
            "columns"
        ].append({"name": c.name, "data_type": c.data_type})
    for m in dm.measures:
        tables_by_name.setdefault(m.table, {"name": m.table, "columns": [], "measures": []})[
            "measures"
        ].append(
            {
                "name": m.name,
                "expression": m.expression,
                "format_string": m.format_string,
            }
        )
    return tables_by_name


def measures_csv_rows(dm: DataModel) -> list[dict[str, Any]]:
    """Flat per-measure rows for the greppable CSV."""
    return [
        {
            "table": m.name and m.table,
            "name": m.name,
            "expression": m.expression,
            "format_string": m.format_string,
        }
        for m in dm.measures
    ]


def relationships_with_topology(dm: DataModel) -> dict[str, Any]:
    """Same rels as model.json but with quick topology summary at the top."""
    by_dir: dict[str, int] = defaultdict(int)
    for r in dm.relationships:
        by_dir[r.cardinality] += 1
    return {
        "cardinality_counts": dict(by_dir),
        "bidirectional_count": sum(1 for r in dm.relationships if r.cross_filter == "both"),
        "inactive_count": sum(1 for r in dm.relationships if not r.active),
        "relationships": [
            {
                "from_table": r.from_table,
                "from_col": r.from_col,
                "to_table": r.to_table,
                "to_col": r.to_col,
                "cardinality": r.cardinality,
                "cross_filter": r.cross_filter,
                "active": r.active,
            }
            for r in dm.relationships
        ],
    }


def write_template_schema(dm: DataModel, out_dir: Path, source_pbix: Path) -> dict[str, int]:
    """Write the per-template directory layout. Returns a counts dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    # 1. model.json — full structured model
    (out_dir / "model.json").write_text(
        json.dumps(serialize_model(dm), indent=2, ensure_ascii=False) + "\n"
    )

    # 2. relationships.json — rels + topology summary
    (out_dir / "relationships.json").write_text(
        json.dumps(relationships_with_topology(dm), indent=2, ensure_ascii=False) + "\n"
    )

    # 3. measures.csv — flat greppable CSV
    rows = measures_csv_rows(dm)
    fieldnames = ["table", "name", "format_string", "expression"]
    with (out_dir / "measures.csv").open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    # 4. tables/<name>.json — per-table breakdown
    table_views = per_table_views(dm)
    written_tables = 0
    for tname, view in table_views.items():
        fname = _safe_filename(tname) + ".json"
        (tables_dir / fname).write_text(json.dumps(view, indent=2, ensure_ascii=False) + "\n")
        written_tables += 1

    # 5. metadata.json
    try:
        from importlib.metadata import version as _pkg_version

        pbixray_version = _pkg_version("pbixray")
    except Exception:
        pbixray_version = "unknown"
    # table_count derives from per-table view count (includes calculated
    # tables that pbixray.schema surfaces but pbixray.tables omits).
    (out_dir / "metadata.json").write_text(
        json.dumps(
            {
                "template_slug": dm.template_slug,
                "source_pbix": str(source_pbix),
                "extraction_date": dt.date.today().isoformat(),
                "pbixray_version": pbixray_version,
                "table_count": written_tables,
                "user_visible_table_count": len(dm.tables),
                "column_count": len(dm.columns),
                "measure_count": len(dm.measures),
                "relationship_count": len(dm.relationships),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    return {
        "tables": written_tables,
        "columns": len(dm.columns),
        "measures": len(dm.measures),
        "relationships": len(dm.relationships),
    }


def _adapter_from_pbixray(raw: Any) -> Any:
    """Wrap a pbixray.PBIXRay object so shape_datamodel can iterate it as
    list[dict] (pbixray returns DataFrames; same adapter pattern as
    rw_zebra_kg_datamodel.main)."""

    class _Adapter:
        tables = list(raw.tables)
        dax_measures = raw.dax_measures.to_dict("records")
        relationships = raw.relationships.to_dict("records")
        schema = raw.schema.to_dict("records")

    return _Adapter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="If set, only extract this single template_slug. Otherwise all PBIX/zip files in --source-dir.",
    )
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser()
    out_dir = args.out_dir.expanduser()

    candidates = sorted(p for p in source_dir.iterdir() if p.suffix.lower() in (".pbix", ".zip"))
    if args.template:
        candidates = [p for p in candidates if template_slug_from_pbix(p) == args.template]
        if not candidates:
            raise SystemExit(f"no PBIX/zip in {source_dir} matched template={args.template!r}")

    from pbixray import PBIXRay

    tmp_root = Path(tempfile.mkdtemp(prefix="zebra_kg_save_schemas_"))
    summary: list[dict[str, Any]] = []
    for path in candidates:
        slug = template_slug_from_pbix(path)
        try:
            pbix_path = _resolve_pbix_path(path, tmp_root)
            if pbix_path is None:
                print(f"  {slug}: no inner .pbix in {path.name}; skipping")
                continue
            raw = PBIXRay(str(pbix_path))
            dm = shape_datamodel(_adapter_from_pbixray(raw), template_slug=slug)
        except Exception as exc:
            print(f"  {slug}: FAILED {type(exc).__name__}: {exc}")
            continue

        template_dir = out_dir / slug
        counts = write_template_schema(dm, template_dir, source_pbix=path)
        summary.append({"template": slug, **counts, "path": str(template_dir)})
        print(
            f"  {slug:60} tables={counts['tables']:3} "
            f"cols={counts['columns']:4} measures={counts['measures']:3} "
            f"rels={counts['relationships']:3}"
        )

    print(f"\nwrote {len(summary)} template(s) to {out_dir}")


if __name__ == "__main__":
    main()
