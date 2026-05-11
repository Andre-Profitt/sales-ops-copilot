"""Mine every Zebra-custom-visual configuration across all 20 templates.

For each visualContainer in each Zebra PBIX whose visualType is a Zebra
custom visual (ZebraBITables, zebraBiCards, waterfall family), dump:

- Full singleVisual.projections (which projection roles are used + queryRefs)
- Full singleVisual.objects (every objects.<group>, every property, every value)
- Decoded chartSettings.columnSettings (the IBCS rendering grammar)
- Position metadata
- Source template + page

Output: data/zebra_kg/infrastructure/raw_configs.jsonl — one row per
Zebra visualContainer.

Also extracts each .pbiviz.json + package.json from the CustomVisuals/
directory inside the PBIX zips → data/zebra_kg/infrastructure/visual_packages.json
with capabilities + dataView mapping declarations per Zebra visual.

Usage:
    python3 -m scripts.sales.rw_zebra_kg_infra_miner \\
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \\
      --out-dir data/zebra_kg/infrastructure
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/files"
DEFAULT_OUT = REPO_ROOT / "data/zebra_kg/infrastructure"

ZEBRA_VISUALTYPE_PREFIXES = (
    "ZebraBITables",
    "zebraBiCards",
    "ZebraBICharts",
    "waterfall",
)


def _resolve_pbix(path: Path, tmp_root: Path) -> Path | None:
    if path.suffix.lower() == ".pbix":
        return path
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            inner = next((n for n in zf.namelist() if n.lower().endswith(".pbix")), None)
            if not inner:
                return None
            extracted = tmp_root / f"{path.stem}__{Path(inner).name}"
            with zf.open(inner) as src, extracted.open("wb") as dst:
                dst.write(src.read())
            return extracted
    return None


def _template_slug(path: Path) -> str:
    return path.stem.split("__", 1)[0]


def _is_zebra_visualtype(vt: str) -> str | None:
    """Return the visual family name (ZebraBITables / ZebraBICards / etc.)
    if this visualType is a Zebra custom visual; None otherwise."""
    if not isinstance(vt, str):
        return None
    if vt.startswith("ZebraBITables"):
        return "ZebraBITables"
    if vt.startswith("zebraBiCards"):
        return "ZebraBICards"
    if vt.startswith("ZebraBICharts"):
        return "ZebraBICharts"
    if vt.startswith("waterfall"):
        return "ZebraWaterfall"
    return None


def _unwrap_literal(node: Any) -> Any:
    """Power BI wraps configuration values in `expr.Literal.Value` shapes,
    sometimes with single-quote padding. Decode common shapes; return the
    raw value if not wrappable."""
    if isinstance(node, dict):
        if "expr" in node and isinstance(node["expr"], dict):
            lit = node["expr"].get("Literal") or {}
            if "Value" in lit:
                v = lit["Value"]
                if isinstance(v, str):
                    if v.startswith("'") and v.endswith("'"):
                        v = v[1:-1]
                    # Try JSON decode for embedded structured values
                    if v.startswith("{") or v.startswith("["):
                        try:
                            return json.loads(v)
                        except json.JSONDecodeError:
                            return v
                    return v
                return v
            if "Boolean" in node["expr"]:
                return bool(node["expr"]["Boolean"])
        # Recurse into dict shapes
        return {k: _unwrap_literal(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_unwrap_literal(x) for x in node]
    return node


def _decode_objects_block(objects: dict[str, Any] | None) -> dict[str, Any]:
    """Decode singleVisual.objects into a structured-value dict.
    Each top-level key (e.g., 'chartSettings') has a list of entries; each
    entry has a 'properties' dict whose values are wrapped expressions.
    Unwrap them to bare values where possible."""
    if not objects:
        return {}
    out: dict[str, Any] = {}
    for group_name, entries in objects.items():
        decoded_entries = []
        for entry in entries or []:
            if not isinstance(entry, dict):
                continue
            props = entry.get("properties") or {}
            decoded_props = {k: _unwrap_literal(v) for k, v in props.items()}
            decoded_entry = {**entry, "properties": decoded_props}
            decoded_entries.append(decoded_entry)
        out[group_name] = decoded_entries
    return out


def _projection_summary(projections: dict[str, Any] | None) -> dict[str, list[str]]:
    """Return {role_name: [queryRef, ...]} per projection role."""
    if not projections:
        return {}
    out: dict[str, list[str]] = {}
    for role, projs in projections.items():
        refs: list[str] = []
        for p in projs or []:
            qref = p.get("queryRef")
            if isinstance(qref, str):
                refs.append(qref)
        out[role] = refs
    return out


def mine_pbix(pbix: Path, out_rows: list, slug: str) -> int:
    """Append per-Zebra-visualContainer rows to out_rows. Returns count."""
    with zipfile.ZipFile(pbix) as zf:
        layout = json.loads(zf.read("Report/Layout").decode("utf-16-le"))

    n = 0
    for sec in layout.get("sections", []):
        for vc in sec.get("visualContainers", []):
            cstr = vc.get("config")
            if not isinstance(cstr, str):
                continue
            try:
                cfg = json.loads(cstr)
            except json.JSONDecodeError:
                continue
            sv = cfg.get("singleVisual") or {}
            vt = sv.get("visualType", "")
            family = _is_zebra_visualtype(vt)
            if not family:
                continue

            row = {
                "template_slug": slug,
                "page_name": sec.get("name", ""),
                "page_display_name": sec.get("displayName", ""),
                "visual_family": family,
                "visual_type_full": vt,
                "position": {
                    "x": vc.get("x", 0),
                    "y": vc.get("y", 0),
                    "w": vc.get("width", 0),
                    "h": vc.get("height", 0),
                },
                "projections": _projection_summary(sv.get("projections")),
                "objects": _decode_objects_block(sv.get("objects")),
            }
            out_rows.append(row)
            n += 1
    return n


def mine_visual_packages(pbix: Path) -> list[dict]:
    """Extract pbiviz.json + package.json metadata for each CustomVisual
    folder in the PBIX zip. Returns list of {visual_guid, package_json,
    pbiviz_summary} entries."""
    out = []
    with zipfile.ZipFile(pbix) as zf:
        names = zf.namelist()
        guids = set()
        for n in names:
            if n.startswith("Report/CustomVisuals/"):
                parts = n.split("/", 3)
                if len(parts) >= 3:
                    guids.add(parts[2])
        for guid in sorted(guids):
            entry = {"visual_guid": guid}
            pkg_name = f"Report/CustomVisuals/{guid}/package.json"
            pbiviz_name = f"Report/CustomVisuals/{guid}/resources/{guid}.pbiviz.json"
            if pkg_name in names:
                try:
                    entry["package_json"] = json.loads(zf.read(pkg_name).decode("utf-8"))
                except Exception as exc:
                    entry["package_json_error"] = str(exc)
            if pbiviz_name in names:
                try:
                    raw = zf.read(pbiviz_name)
                    pviz = json.loads(raw.decode("utf-8"))
                    # The .pbiviz.json is large (contains the visual's JS code); slim
                    # to just the metadata keys we care about.
                    summary = {
                        "visual": {
                            k: pviz.get("visual", {}).get(k)
                            for k in (
                                "name",
                                "displayName",
                                "guid",
                                "visualClassName",
                                "version",
                                "description",
                                "supportUrl",
                                "gitHubUrl",
                            )
                        },
                        "apiVersion": pviz.get("apiVersion"),
                        "author": pviz.get("author"),
                        "stringResources": list((pviz.get("stringResources") or {}).keys())[:5],
                        "capabilities": pviz.get("capabilities", {}),
                    }
                    entry["pbiviz_summary"] = summary
                except Exception as exc:
                    entry["pbiviz_error"] = str(exc)
            out.append(entry)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    source_dir = args.source_dir.expanduser()
    out_dir = args.out_dir.expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    tmp_root = Path(tempfile.mkdtemp(prefix="zbr_infra_miner_"))
    candidates = sorted(p for p in source_dir.iterdir() if p.suffix.lower() in (".pbix", ".zip"))

    raw_rows: list[dict] = []
    packages_by_template: dict[str, list[dict]] = {}
    for path in candidates:
        slug = _template_slug(path)
        pbix = _resolve_pbix(path, tmp_root)
        if pbix is None:
            print(f"  {slug}: no inner .pbix; skipping")
            continue
        try:
            n = mine_pbix(pbix, raw_rows, slug)
            pkgs = mine_visual_packages(pbix)
            packages_by_template[slug] = pkgs
            zebra_pkgs = [
                p
                for p in pkgs
                if any(s in p["visual_guid"] for s in ("Zebra", "zebra", "waterfall"))
            ]
            print(
                f"  {slug:60} zebra_visuals={n:3}  custom_pkgs={len(pkgs):2} (zebra={len(zebra_pkgs)})"
            )
        except Exception as exc:
            print(f"  {slug}: FAILED {type(exc).__name__}: {exc}")
            continue

    raw_path = out_dir / "raw_configs.jsonl"
    with raw_path.open("w", encoding="utf-8") as fp:
        for row in raw_rows:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nwrote {raw_path}: {len(raw_rows)} rows")

    pkg_path = out_dir / "visual_packages.json"
    pkg_path.write_text(json.dumps(packages_by_template, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {pkg_path}: {sum(len(v) for v in packages_by_template.values())} visual packages across {len(packages_by_template)} templates"
    )

    shutil.rmtree(tmp_root)


if __name__ == "__main__":
    main()
