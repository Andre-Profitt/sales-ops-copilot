"""Swap Zebra custom visuals → native equivalents inside a PBIX file,
re-zip, and (optionally) upload to a Fabric workspace.

Translation:
    ZebraBITables*       → tableEx with IBCS-ordered columns (Cat + AC/PY/PL/FC)
    zebraBiCards* (1 measure, no category)  → native card
    zebraBiCards* (multi-measure / has category) → multiRowCard
    waterfall*           → native waterfallChart (true bridge w/ up/down/total)

The pipeline: scan first (resolve Calendar-equivalent table, build qref→
real-table map, count visual-type families), then per-visual rewrite using
the helpers in scripts.sales._pbir_helpers + a small visualType-rebrand
trick for waterfall/multiRowCard variants.

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

from scripts.sales._pbir_helpers import (
    build_card_visual_with_objects,
    build_table_style_objects,
    build_table_visual,
)

VAL_ROLES = ("Values", "PreviousYear", "Plan", "Forecast")
CAT_ROLES = ("Category", "Group")
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


def _resolve_qref(qref: str, rmap: dict) -> tuple[str, str] | None:
    if not isinstance(qref, str):
        return None
    m = QREF_WRAP.match(qref)
    inner = m.group(2) if m else qref
    if "." not in inner:
        return None
    t, f = inner.split(".", 1)
    t, f = t.strip(), f.strip()
    if t in rmap["all_tables"] and (
        f in rmap["cols_by_table"].get(t, set()) or f in rmap["measures_by_table"].get(t, set())
    ):
        return (t, f)
    if t == "Calendar" and rmap["calendar_alias"]:
        if f in rmap["cols_by_table"].get(rmap["calendar_alias"], set()):
            return (rmap["calendar_alias"], f)
    return None


def _role_refs(sv: dict, roles: tuple, rmap: dict) -> list[tuple[str, str]]:
    out = []
    for role in roles:
        for p in (sv.get("projections") or {}).get(role, []) or []:
            r = _resolve_qref(p.get("queryRef"), rmap)
            if r and r not in out:
                out.append(r)
    return out


def _visualtype_swap(config_str: str, new_type: str, role_renames: dict | None = None) -> str:
    cfg = json.loads(config_str)
    sv = cfg.get("singleVisual", {})
    sv["visualType"] = new_type
    if role_renames and "projections" in sv:
        merged = {}
        for old_role, projs in (sv["projections"] or {}).items():
            new_role = role_renames.get(old_role, old_role)
            merged.setdefault(new_role, []).extend(projs or [])
        sv["projections"] = merged
    return json.dumps(cfg, ensure_ascii=False)


def swap_layout(layout: dict, rmap: dict) -> dict:
    """Walk every visualContainer in a Layout dict; swap Zebra → native in-place.
    Returns stats dict."""
    stats = defaultdict(int)
    for sec in layout.get("sections", []):
        new = []
        for vc in sec.get("visualContainers", []):
            x = vc.get("x", 0)
            y = vc.get("y", 0)
            w = vc.get("width", 100)
            h = vc.get("height", 100)
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
            vt = sv.get("visualType", "")

            if "waterfall" in vt:
                cat = _role_refs(sv, CAT_ROLES, rmap)
                val = _role_refs(sv, VAL_ROLES, rmap)
                if not cat or not val:
                    new.append(vc)
                    stats["wf_skipped"] += 1
                    continue
                ct, cf = cat[0]
                vt2, vf2 = val[0]
                cols = [
                    {"table": ct, "field": cf, "kind": "column", "title": cf},
                    {"table": vt2, "field": vf2, "kind": "measure", "title": vf2},
                ]
                scaffold = build_table_visual(
                    name=f"wf_{int(x)}_{int(y)}",
                    columns=cols,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                )
                # Rebrand to native waterfallChart, split projections back into Cat / Y
                cfg2 = json.loads(scaffold["config"])
                sv2 = cfg2["singleVisual"]
                sv2["visualType"] = "waterfallChart"
                vals = sv2["projections"].get("Values", [])
                cat_p, y_p = [], []
                for p in vals:
                    qr = p.get("queryRef", "")
                    if "." in qr:
                        pt, pf = qr.split(".", 1)
                        if pf in rmap["measures_by_table"].get(pt, set()):
                            y_p.append(p)
                        else:
                            cat_p.append(p)
                sv2["projections"] = {"Category": cat_p, "Y": y_p}
                scaffold["config"] = json.dumps(cfg2, ensure_ascii=False)
                new.append(scaffold)
                stats["waterfall→native"] += 1

            elif "zebraBiCards" in vt:
                cat = _role_refs(sv, CAT_ROLES, rmap)
                val = _role_refs(sv, VAL_ROLES, rmap)
                if not val:
                    new.append(vc)
                    stats["card_skipped"] += 1
                    continue
                if len(val) == 1 and not cat:
                    t, f = val[0]
                    new.append(
                        build_card_visual_with_objects(
                            measure_table=t,
                            measure_name=f,
                            display_title=f,
                            x=x,
                            y=y,
                            w=w,
                            h=h,
                        )
                    )
                    stats["card→card"] += 1
                else:
                    cols = []
                    for t, f in cat[:1]:
                        cols.append({"table": t, "field": f, "kind": "column", "title": f})
                    for t, f in val:
                        cols.append({"table": t, "field": f, "kind": "measure", "title": f})
                    scaffold = build_table_visual(
                        name=f"mrc_{int(x)}_{int(y)}", columns=cols, x=x, y=y, w=w, h=h
                    )
                    scaffold["config"] = _visualtype_swap(scaffold["config"], "multiRowCard")
                    new.append(scaffold)
                    stats["card→multiRow"] += 1

            elif "ZebraBITables" in vt:
                cat = _role_refs(sv, CAT_ROLES, rmap)
                val = _role_refs(sv, VAL_ROLES, rmap)
                if not val:
                    new.append(vc)
                    stats["tbl_skipped"] += 1
                    continue
                cols = []
                for t, f in cat[:2]:
                    cols.append({"table": t, "field": f, "kind": "column", "title": f})
                for t, f in val:
                    cols.append({"table": t, "field": f, "kind": "measure", "title": f})
                new.append(
                    build_table_visual(
                        name=f"tbl_{int(x)}_{int(y)}",
                        columns=cols,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        objects=build_table_style_objects(font_size=9),
                    )
                )
                stats["tbl→tableEx"] += 1
            else:
                new.append(vc)
                stats["kept"] += 1
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
