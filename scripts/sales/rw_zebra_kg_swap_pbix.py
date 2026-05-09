"""Swap Zebra custom visuals → native equivalents inside a PBIX file,
re-zip, and (optionally) upload to a Fabric workspace.

Translation:
    ZebraBITables*       → tableEx with IBCS-ordered columns (Cat + AC/PY/PL/FC)
    zebraBiCards* (1 measure, no category)  → native card
    zebraBiCards* (multi-measure / has category) → multiRowCard
    waterfall*           → native waterfallChart (true bridge w/ up/down/total)

The pipeline: scan first (resolve Calendar-equivalent table, build qref→
real-table map, count visual-type families), then per-visual rewrite using
translate_visual so all per-family logic lives in rw_zebra_kg_translator.

Usage:
    # single file, no upload
    python3 -m scripts.sales.rw_zebra_kg_swap_pbix \\
      --pbix path/to/source.pbix --out /tmp/native.pbix

    # single file, upload to Fabric workspace
    python3 -m scripts.sales.rw_zebra_kg_swap_pbix \\
      --pbix path/to/source.pbix --out /tmp/native.pbix \\
      --upload --workspace b66233d5-... --name zbr-foo-native

    # batch — every PBIX/zip in a dir, swap and upload
    python3 -m scripts.sales.rw_zebra_kg_swap_pbix \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --out-dir /tmp/zebra_native/ \\
      --upload --workspace b66233d5-... --name-prefix zbr-
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import time
import zipfile
from collections import defaultdict
from pathlib import Path

from scripts.sales.rw_zebra_kg_translator import (
    BindMap,
    MeasureCatalog,
    translate_visual,
)

QREF_WRAP = re.compile(
    r"^(Sum|Min|Max|Count|Average|Distinct count|CountNonNull|Median|StandardDeviation|Variance)\((.+)\)$"
)


def _resolve_pbix(path: Path, tmp: Path) -> Path | None:
    if path.suffix.lower() == ".pbix":
        return path
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            inner = next((n for n in zf.namelist() if n.lower().endswith(".pbix")), None)
            if not inner:
                return None
            out = tmp / f"{path.stem}__{Path(inner).name}"
            with zf.open(inner) as src, out.open("wb") as dst:
                dst.write(src.read())
            return out
    return None


def _build_resolution_map(pbix: Path) -> dict:
    """Probe the PBIX data model to find Calendar alias + tables/cols/measures."""
    from pbixray import PBIXRay

    raw = PBIXRay(str(pbix))
    cols_by_table = defaultdict(set)
    for r in raw.schema.to_dict("records"):
        cols_by_table[r["TableName"]].add(r["ColumnName"])
    measures_by_table = defaultdict(set)
    for r in raw.dax_measures.to_dict("records"):
        measures_by_table[r["TableName"]].add(r["Name"])
    all_tables = set(raw.tables) | set(cols_by_table) | set(measures_by_table)

    calendar_alias = next(
        (
            t
            for t, cols in cols_by_table.items()
            if {"Month", "Year"}.issubset(cols) or {"MonthNo", "Year"}.issubset(cols)
        ),
        None,
    )
    return {
        "all_tables": all_tables,
        "cols_by_table": cols_by_table,
        "measures_by_table": measures_by_table,
        "calendar_alias": calendar_alias,
    }


def _catalog_from_rmap(rmap: dict) -> MeasureCatalog:
    """rmap['measures_by_table'] is {table: set(measure_names)}; flatten to catalog."""
    by_scenario: dict[str, str] = {}
    measure_to_table: dict[str, str] = {}
    for tbl, names in (rmap.get("measures_by_table") or {}).items():
        for n in names:
            by_scenario[n] = n
            measure_to_table[n] = tbl
    return MeasureCatalog(by_scenario=by_scenario, measure_to_table=measure_to_table)


def swap_layout(layout: dict, rmap: dict) -> dict:
    """Walk every visualContainer in a Layout dict; swap Zebra → native in-place.
    Returns stats dict."""
    stats = defaultdict(int)
    for sec in layout.get("sections", []):
        new = []
        for vc in sec.get("visualContainers", []):
            cstr = vc.get("config")
            if not isinstance(cstr, str):
                new.append(vc)
                stats["kept"] += 1
                continue
            try:
                cfg = json.loads(cstr)
            except (ValueError, json.JSONDecodeError):
                new.append(vc)
                stats["kept"] += 1
                continue
            sv = cfg.get("singleVisual") or {}
            vt = sv.get("visualType", "")  # noqa: F841 — kept for potential future use

            catalog = _catalog_from_rmap(rmap)
            bm = BindMap()  # PBIX path: no overlay; identity binding
            translated = translate_visual(vc, catalog, bm)
            # translate_visual returns [src_vc] on pass-through or family failure;
            # don't double-count untranslated visuals.
            if len(translated) == 1 and translated[0] is vc:
                new.append(vc)
                stats["kept"] += 1
            else:
                new.extend(translated)
                stats.setdefault("translated", 0)
                stats["translated"] += len(translated)
            continue
        sec["visualContainers"] = new
    return dict(stats)


def swap_pbix(src_pbix: Path, out_pbix: Path) -> dict:
    """Read src_pbix, swap Zebra visuals in Layout, write out_pbix. Returns stats."""
    tmp = Path(tempfile.mkdtemp(prefix="zbr_swap_"))
    work = tmp / "extract"
    work.mkdir()
    with zipfile.ZipFile(src_pbix) as zf:
        zf.extractall(work)

    rmap = _build_resolution_map(src_pbix)
    layout_path = work / "Report/Layout"
    layout = json.loads(layout_path.read_bytes().decode("utf-16-le"))
    stats = swap_layout(layout, rmap)
    layout_path.write_bytes(json.dumps(layout, ensure_ascii=False).encode("utf-16-le"))

    if out_pbix.exists():
        out_pbix.unlink()
    out_pbix.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src_pbix) as src_zf:
        names = src_zf.namelist()
        with zipfile.ZipFile(out_pbix, "w", zipfile.ZIP_DEFLATED) as out_zf:
            for n in names:
                full = work / n
                if full.exists() and full.is_file():
                    out_zf.write(full, n)
                else:
                    out_zf.writestr(n, src_zf.read(n))
    shutil.rmtree(tmp)
    stats["calendar_alias"] = rmap["calendar_alias"] or ""
    return stats


def upload_pbix(pbix: Path, workspace: str, display_name: str) -> str | None:
    """Upload via Fabric REST imports endpoint. Returns report_id on success."""
    import requests
    from azure.identity import AzureCliCredential

    token = (
        AzureCliCredential().get_token("https://analysis.windows.net/powerbi/api/.default").token
    )
    r = requests.post(
        f"https://api.powerbi.com/v1.0/myorg/groups/{workspace}/imports"
        f"?datasetDisplayName={display_name}&nameConflict=CreateOrOverwrite",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (pbix.name, pbix.open("rb"), "application/octet-stream")},
    )
    if r.status_code >= 300:
        print(f"  upload POST {r.status_code}: {r.text[:300]}")
        return None
    imp_id = r.json()["id"]
    for _ in range(30):
        time.sleep(3)
        s = requests.get(
            f"https://api.powerbi.com/v1.0/myorg/groups/{workspace}/imports/{imp_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        if s.get("importState") in ("Succeeded", "Failed"):
            break
    if s.get("importState") != "Succeeded":
        print(f"  import failed: {s}")
        return None
    rep = (s.get("reports") or [{}])[0]
    return rep.get("id")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("--pbix", type=Path, default=None, help="Single source PBIX")
    ap.add_argument("--source-dir", type=Path, default=None, help="Batch: dir of .pbix/.zip files")
    ap.add_argument("--out", type=Path, default=None, help="Single-file output PBIX")
    ap.add_argument("--out-dir", type=Path, default=None, help="Batch: output dir")
    ap.add_argument("--upload", action="store_true")
    ap.add_argument("--workspace", type=str, default=None)
    ap.add_argument("--name", type=str, default=None, help="Single-file dataset display name")
    ap.add_argument(
        "--name-prefix", type=str, default="zbr-", help="Batch name prefix (default 'zbr-')"
    )
    args = ap.parse_args()

    if args.pbix and args.out:
        targets = [(args.pbix, args.out, args.name or args.out.stem)]
    elif args.source_dir and args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix="zbr_swap_batch_"))
        files = sorted(
            p
            for p in args.source_dir.expanduser().iterdir()
            if p.suffix.lower() in (".pbix", ".zip")
        )
        targets = []
        for p in files:
            real = _resolve_pbix(p, tmp)
            if not real:
                print(f"skip {p.name}: no inner .pbix")
                continue
            slug = p.stem.split("__", 1)[0]
            out_pbix = args.out_dir.expanduser() / f"{args.name_prefix}{slug}.pbix"
            targets.append((real, out_pbix, f"{args.name_prefix}{slug}-native"))
    else:
        ap.error("provide --pbix + --out OR --source-dir + --out-dir")

    for src, out, dsname in targets:
        print(f"\n--- {src.name} ---")
        stats = swap_pbix(src, out)
        print(f"  stats: {stats}")
        print(f"  out:   {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")
        if args.upload and args.workspace:
            rep_id = upload_pbix(out, args.workspace, dsname)
            if rep_id:
                print(f"  open: https://app.powerbi.com/groups/{args.workspace}/reports/{rep_id}")


if __name__ == "__main__":
    main()
