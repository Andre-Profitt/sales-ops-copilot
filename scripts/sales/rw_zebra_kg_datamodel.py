"""Extract DAX measures, tables, columns, relationships from Zebra BI PBIX
templates and emit a parallel data-model graph alongside the existing
visual-side graph (which is produced by rw_zebra_template_miner.py).

Pipeline:
    PBIX zip --(pbixray)--> raw rows --(shape)--> DataModel dataclasses
        --(emit)--> nodes_datamodel.jsonl + edges_datamodel.jsonl + measure_catalog.csv

Usage:
    python3 -m scripts.sales.rw_zebra_kg_datamodel \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \\
      --out-dir data/zebra_kg

Notes on pbixray column names (probed 2026-05-09 against Zebra CRM Sales
pipeline demo v2.pbix):
  - dax_measures: TableName, Name, Expression, DisplayFolder, Description
    (no FormatString — .get("FormatString", "") returns "" for real files)
  - relationships: FromTableName, FromColumnName, ToTableName, ToColumnName,
    Cardinality (e.g. "M:1"), CrossFilteringBehavior (e.g. "Single"),
    IsActive (0/1 int)
  - schema: TableName, ColumnName, PandasDataType
  - tables: pandas.StringArray — list() converts to list[str]
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

# ---------- value objects ----------


@dataclass(frozen=True)
class Table:
    name: str


@dataclass(frozen=True)
class Column:
    table: str
    name: str
    data_type: str


@dataclass(frozen=True)
class Measure:
    name: str
    table: str
    expression: str
    format_string: str
    scenario: str | None = None  # "AC" | "PY" | "PL" | "FC" | None
    is_variance: bool = False


@dataclass(frozen=True)
class Relationship:
    from_table: str
    from_col: str
    to_table: str
    to_col: str
    cardinality: str  # "many_to_one" | "one_to_many" | "one_to_one" | "many_to_many"
    cross_filter: str  # "single" | "both"
    active: bool


@dataclass(frozen=True)
class DataModel:
    template_slug: str
    tables: list[Table] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)


# ---------- shaping ----------

_CARDINALITY_MAP = {
    "M:1": "many_to_one",
    "1:M": "one_to_many",
    "1:1": "one_to_one",
    "M:M": "many_to_many",
}

# pbixray uses "Single" / "Both" (capital first letter); the PBIX XML also
# contains "OneDirection" / "BothDirections" in some versions — cover both.
_CROSSFILTER_MAP = {
    "Single": "single",
    "Both": "both",
    "OneDirection": "single",
    "BothDirections": "both",
    "Automatic": "single",  # PBIX default for M:1 — treat as single
}


def _as_str(v: Any) -> str:
    """Coerce a value to str. pbixray returns float NaN for empty cells, and
    `nan or ""` is still nan because float NaN is truthy."""
    return v if isinstance(v, str) else ""


def shape_datamodel(pbix: Any, template_slug: str) -> DataModel:
    """Translate a pbixray.PBIXRay-shaped object into our DataModel dataclasses.

    `pbix` must expose: .tables (list[str]), .dax_measures (list[dict]),
    .relationships (list[dict]), .schema (list[dict]). Real pbixray and the
    test stub both satisfy this interface after the caller converts DataFrames
    to records (see integration test for the adapter pattern).
    """
    tables = [Table(name=t) for t in pbix.tables]

    columns = [
        Column(
            table=row["TableName"],
            name=row["ColumnName"],
            data_type=row.get("PandasDataType", "unknown"),
        )
        for row in pbix.schema
    ]

    measures = [
        Measure(
            name=row["Name"],
            table=row["TableName"],
            # pbixray returns NaN (float) for empty Expression/FormatString.
            # `nan or ""` is still nan (truthy), so coerce via isinstance.
            expression=_as_str(row.get("Expression")),
            format_string=_as_str(row.get("FormatString")),
        )
        for row in pbix.dax_measures
    ]

    relationships = [
        Relationship(
            from_table=row["FromTableName"],
            from_col=row["FromColumnName"],
            to_table=row["ToTableName"],
            to_col=row["ToColumnName"],
            cardinality=_CARDINALITY_MAP.get(row.get("Cardinality", ""), "unknown"),
            cross_filter=_CROSSFILTER_MAP.get(row.get("CrossFilteringBehavior", ""), "single"),
            active=bool(row.get("IsActive", True)),
        )
        for row in pbix.relationships
    ]

    return DataModel(
        template_slug=template_slug,
        tables=tables,
        columns=columns,
        measures=measures,
        relationships=relationships,
    )


# ---------- scenario / variance classification ----------

# Scenario tokens are matched as whole words anywhere in the measure name.
# Order matters: PY before AC because plain measures default to AC.
_SCENARIO_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("PY", re.compile(r"\b(PY|Prior Year|Last Year|LY|SPLY)\b", re.IGNORECASE)),
    ("PL", re.compile(r"\b(Plan|Budget|BU|Target)\b", re.IGNORECASE)),
    ("FC", re.compile(r"\b(Forecast|FC|Estimate|EST)\b", re.IGNORECASE)),
]

_VARIANCE_PATTERN = re.compile(r"\b(vs|var|variance|delta|diff|difference)\b", re.IGNORECASE)

# Inside a DAX expression, `[Foo Bar]` is a measure or column reference.
# We treat every match as a potential measure dependency and resolve later
# against the template's measure list (column refs without table-qualifier
# get filtered out at edge-emit time).
_DAX_MEASURE_REF = re.compile(r"\[([^\]]+)\]")


def classify_scenario(measure_name: str) -> str:
    """Return 'AC' (default) or 'PY'/'PL'/'FC' if name matches a scenario token."""
    for code, pat in _SCENARIO_PATTERNS:
        if pat.search(measure_name):
            return code
    return "AC"


def is_variance(measure_name: str) -> bool:
    return bool(_VARIANCE_PATTERN.search(measure_name))


# ---------- node / edge emission ----------

_IBCS_GLYPH = {"AC": "solid", "PY": "outlined", "PL": "hatched", "FC": "dotted"}


def _msr_id(slug: str, name: str) -> str:
    return f"msr:{slug}:{name}"


def _tbl_id(slug: str, name: str) -> str:
    return f"tbl:{slug}:{name}"


def _col_id(slug: str, table: str, name: str) -> str:
    return f"col:{slug}:{table}:{name}"


def _rel_id(slug: str, rel: Relationship) -> str:
    return f"rel:{slug}:{rel.from_table}.{rel.from_col}->{rel.to_table}.{rel.to_col}"


def iter_nodes(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    used_scenarios: set[str] = set()

    for t in dm.tables:
        yield {
            "id": _tbl_id(slug, t.name),
            "type": "Table",
            "name": t.name,
            "template": slug,
        }

    for c in dm.columns:
        yield {
            "id": _col_id(slug, c.table, c.name),
            "type": "Column",
            "table": c.table,
            "name": c.name,
            "data_type": c.data_type,
            "template": slug,
        }

    for m in dm.measures:
        scenario = classify_scenario(m.name)
        used_scenarios.add(scenario)
        yield {
            "id": _msr_id(slug, m.name),
            "type": "Measure",
            "name": m.name,
            "table": m.table,
            "expression": m.expression,
            "format_string": m.format_string,
            "scenario": scenario,
            "is_variance": is_variance(m.name),
            "template": slug,
        }

    for r in dm.relationships:
        yield {
            "id": _rel_id(slug, r),
            "type": "Relationship",
            "from": _tbl_id(slug, r.from_table),
            "to": _tbl_id(slug, r.to_table),
            "from_col": r.from_col,
            "to_col": r.to_col,
            "cardinality": r.cardinality,
            "cross_filter": r.cross_filter,
            "active": r.active,
            "template": slug,
        }

    # Scenario nodes are global (not template-scoped) — emit once per scenario
    # actually used. The iteration here is per-template, so emit-and-dedupe at
    # the writer layer.
    for scn in sorted(used_scenarios):
        yield {
            "id": f"scn:{scn}",
            "type": "Scenario",
            "code": scn,
            "ibcs_glyph": _IBCS_GLYPH.get(scn, ""),
        }


def iter_edges(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    measure_names = {m.name for m in dm.measures}

    for m in dm.measures:
        msr = _msr_id(slug, m.name)
        # depends_on edges
        for ref in _DAX_MEASURE_REF.findall(m.expression):
            if ref in measure_names and ref != m.name:
                yield {
                    "src": msr,
                    "dst": _msr_id(slug, ref),
                    "type": "depends_on",
                    "props": {},
                }
        # scenario_of edge
        scn = classify_scenario(m.name)
        yield {"src": msr, "dst": f"scn:{scn}", "type": "scenario_of", "props": {}}

    for r in dm.relationships:
        yield {
            "src": _tbl_id(slug, r.from_table),
            "dst": _tbl_id(slug, r.to_table),
            "type": "related_to",
            "props": {
                "cardinality": r.cardinality,
                "cross_filter": r.cross_filter,
                "active": r.active,
                "from_col": r.from_col,
                "to_col": r.to_col,
            },
        }


def measure_catalog_rows(dm: DataModel) -> Iterable[dict[str, Any]]:
    slug = dm.template_slug
    for m in dm.measures:
        yield {
            "template_slug": slug,
            "table": m.table,
            "name": m.name,
            "expression": m.expression,
            "format_string": m.format_string,
            "scenario": classify_scenario(m.name),
            "is_variance": is_variance(m.name),
        }


# ---------- writers ----------


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fp:
        for row in rows:
            fp.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            fp.write("\n")
            n += 1
    return n


def write_csv(path: Path, rows: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return 0
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    return len(rows)


def template_slug_from_pbix(path: Path) -> str:
    """Match the slug convention used by rw_zebra_template_miner.py."""
    return path.stem.split("__", 1)[0]


def _resolve_pbix_path(path: Path, tmp_root: Path) -> Path | None:
    """Return a Path to a real .pbix file, extracting from a .zip if needed.

    Zebra distributes templates as ``.zip`` archives containing an inner
    ``.pbix`` plus a sample workbook. This unwraps that to a temp file so
    pbixray can open it. Returns None if no .pbix is found.
    """
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument(
        "--analysis-dir",
        type=Path,
        required=True,
        help="Dir of existing visual-side miner output (read-only)",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser()
    out_dir = args.out_dir.expanduser()
    errors_log = out_dir / "extract_errors.log"
    out_dir.mkdir(parents=True, exist_ok=True)
    errors_log.write_text("")  # truncate per run

    from pbixray import PBIXRay  # imported here so unit tests don't need it

    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    all_catalog: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()

    candidates = sorted(p for p in source_dir.iterdir() if p.suffix.lower() in (".pbix", ".zip"))

    tmp_root = Path(tempfile.mkdtemp(prefix="zebra_kg_extract_"))
    for path in candidates:
        slug = template_slug_from_pbix(path)
        try:
            pbix_path = _resolve_pbix_path(path, tmp_root)
            if pbix_path is None:
                with errors_log.open("a", encoding="utf-8") as fp:
                    fp.write(f"{path.name}\tNoInnerPbix\tarchive contains no .pbix\n")
                continue
            raw = PBIXRay(str(pbix_path))

            # Adapter: pbixray returns DataFrames; shape_datamodel wants list[dict].
            class _Adapter:
                tables = list(raw.tables)
                dax_measures = raw.dax_measures.to_dict("records")
                relationships = raw.relationships.to_dict("records")
                schema = raw.schema.to_dict("records")

            dm = shape_datamodel(_Adapter, template_slug=slug)
        except Exception as exc:  # pbixray may raise many shapes
            with errors_log.open("a", encoding="utf-8") as fp:
                fp.write(f"{path.name}\t{type(exc).__name__}\t{exc}\n")
            continue

        for node in iter_nodes(dm):
            if node["id"] in seen_node_ids:
                continue
            seen_node_ids.add(node["id"])
            all_nodes.append(node)
        all_edges.extend(iter_edges(dm))
        all_catalog.extend(measure_catalog_rows(dm))

    n_nodes = write_jsonl(out_dir / "nodes_datamodel.jsonl", all_nodes)
    n_edges = write_jsonl(out_dir / "edges_datamodel.jsonl", all_edges)
    n_catalog = write_csv(out_dir / "measure_catalog.csv", all_catalog)

    print(
        f"templates: {len(candidates)}  nodes: {n_nodes}  edges: {n_edges}  measures: {n_catalog}"
    )
    print(f"errors logged: {errors_log}")


if __name__ == "__main__":
    main()
