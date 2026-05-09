"""RW Power BI dashboard workbench.

This is the higher-leverage loop for moving the RW VP Ops report past basic
cards:

1. Snapshot the live report.
2. Open the PBIP in Power BI Desktop and format one representative visual.
3. Save the PBIP.
4. Diff the saved Desktop report.json against the snapshot.
5. Promote the captured renderer-authored objects block into _pbir_shapes.py
   and _pbir_helpers.py.

Usage:
    python3 -m scripts.sales.rw_dashboard_harness snapshot --source live --label before_rag
    python3 -m scripts.sales.rw_dashboard_harness inventory --source desktop --page "What Changed"
    python3 -m scripts.sales.rw_dashboard_harness audit --source desktop
    python3 -m scripts.sales.rw_dashboard_harness diff --before <snapshot.json> --after-desktop
    python3 -m scripts.sales.rw_dashboard_harness extract --source desktop --page "What Changed" --name e337
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DESKTOP_REPORT = (
    Path.home()
    / "Downloads"
    / "rw-pbi-format-lab"
    / "rpt_vp_ops_scorecard_live_pbip"
    / "rpt_vp_ops_scorecard.Report"
    / "report.json"
)
DEFAULT_OUT_DIR = Path("output") / "rw_dashboard_harness"
CANVAS_W = 1280
CANVAS_H = 720


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    return cleaned.strip("_")[:90] or "untitled"


def stable_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def hash_obj(data: Any) -> str:
    return hashlib.sha256(stable_json(data).encode("utf-8")).hexdigest()[:16]


def load_report_from_path(path: Path) -> dict:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def load_report(source: str, path: Path | None = None) -> dict:
    if source == "live":
        from scripts.sales.rw_validate import fetch_live_report

        return fetch_live_report()
    if source == "desktop":
        return load_report_from_path(path or DEFAULT_DESKTOP_REPORT)
    if source == "path":
        if path is None:
            raise ValueError("--path is required when --source path")
        return load_report_from_path(path)
    raise ValueError(f"unknown source: {source}")


def decode_config(vc: dict) -> dict:
    raw = vc.get("config", {})
    return json.loads(raw) if isinstance(raw, str) else raw


def encode_config(config: dict) -> str:
    return json.dumps(config, separators=(",", ":"), ensure_ascii=False)


def visual_name(vc: dict) -> str:
    return str(decode_config(vc).get("name", ""))


def visual_type(vc: dict) -> str:
    return str(decode_config(vc).get("singleVisual", {}).get("visualType", ""))


def aliases(config: dict) -> dict[str, str]:
    rows = config.get("singleVisual", {}).get("prototypeQuery", {}).get("From", [])
    return {row.get("Name"): row.get("Entity") for row in rows}


def field_refs(vc: dict) -> list[str]:
    config = decode_config(vc)
    alias_map = aliases(config)
    out: list[str] = []
    for selected in config.get("singleVisual", {}).get("prototypeQuery", {}).get("Select", []):
        if "Measure" in selected:
            node = selected["Measure"]
            source = node.get("Expression", {}).get("SourceRef", {}).get("Source")
            table = alias_map.get(source, "?")
            out.append(f"M:{table}.{node.get('Property')}")
        elif "Column" in selected:
            node = selected["Column"]
            source = node.get("Expression", {}).get("SourceRef", {}).get("Source")
            table = alias_map.get(source, "?")
            out.append(f"C:{table}.{node.get('Property')}")
    return out


def display_titles(vc: dict) -> list[str]:
    config = decode_config(vc)
    props = config.get("singleVisual", {}).get("columnProperties", {})
    return [
        str(value.get("displayName"))
        for value in props.values()
        if isinstance(value, dict) and value.get("displayName")
    ]


def object_keys(vc: dict) -> list[str]:
    objects = decode_config(vc).get("singleVisual", {}).get("objects", {})
    return sorted(objects) if isinstance(objects, dict) else []


def visual_summary(page: str, vc: dict) -> dict:
    config = decode_config(vc)
    sv = config.get("singleVisual", {})
    objects = sv.get("objects", {})
    return {
        "page": page,
        "name": config.get("name"),
        "type": sv.get("visualType"),
        "title": " | ".join(display_titles(vc)),
        "x": vc.get("x"),
        "y": vc.get("y"),
        "width": vc.get("width"),
        "height": vc.get("height"),
        "z": vc.get("z"),
        "fields": field_refs(vc),
        "object_keys": object_keys(vc),
        "has_objects": bool(objects),
        "objects_hash": hash_obj(objects) if objects else "",
        "visual_hash": hash_obj(normalize_visual(vc)),
    }


def iter_visuals(report: dict, page_filter: str | None = None):
    for section in report.get("sections", []):
        page = section.get("displayName") or section.get("name") or ""
        if page_filter and page != page_filter:
            continue
        for vc in section.get("visualContainers", []):
            yield page, vc


def normalize_visual(vc: dict) -> dict:
    out = dict(vc)
    config = decode_config(vc)
    out["config"] = config
    return out


def visual_match_key(page: str, vc: dict) -> tuple[str, str]:
    return (page, visual_name(vc))


def visual_fallback_key(page: str, vc: dict) -> tuple:
    return (
        page,
        visual_type(vc),
        round(float(vc.get("x") or 0), 1),
        round(float(vc.get("y") or 0), 1),
        round(float(vc.get("width") or 0), 1),
        round(float(vc.get("height") or 0), 1),
        tuple(field_refs(vc)),
    )


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_inventory(out_dir: Path, summaries: list[dict], label: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{label}.inventory.json"
    csv_path = out_dir / f"{label}.inventory.csv"
    write_json(json_path, summaries)
    columns = [
        "page",
        "name",
        "type",
        "title",
        "x",
        "y",
        "width",
        "height",
        "fields",
        "object_keys",
        "objects_hash",
        "visual_hash",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for row in summaries:
            flat = dict(row)
            flat["fields"] = ";".join(row["fields"])
            flat["object_keys"] = ";".join(row["object_keys"])
            writer.writerow({key: flat.get(key, "") for key in columns})
    return json_path, csv_path


def inventory(report: dict, page: str | None = None) -> list[dict]:
    return [visual_summary(page_name, vc) for page_name, vc in iter_visuals(report, page)]


def print_inventory_summary(summaries: list[dict]) -> None:
    by_page = Counter(row["page"] for row in summaries)
    by_type = Counter(row["type"] for row in summaries)
    print(f"visuals: {len(summaries)}")
    print("by page:")
    for page, count in sorted(by_page.items()):
        print(f"  {page}: {count}")
    print("by type:")
    for kind, count in sorted(by_type.items()):
        print(f"  {kind}: {count}")


def audit(report: dict) -> list[str]:
    findings: list[str] = []
    sections = report.get("sections", [])
    for section in sections:
        page = section.get("displayName") or section.get("name") or ""
        visuals = section.get("visualContainers", [])
        if not visuals:
            findings.append(f"[empty-page] {page}: no visuals")
        for vc in visuals:
            summary = visual_summary(page, vc)
            right = float(vc.get("x") or 0) + float(vc.get("width") or 0)
            bottom = float(vc.get("y") or 0) + float(vc.get("height") or 0)
            label = f"{page}/{summary['name']} ({summary['type']})"
            if right > CANVAS_W or bottom > CANVAS_H:
                findings.append(
                    f"[canvas-overflow] {label}: ends at {right:.0f}x{bottom:.0f}"
                )
            if summary["type"] == "card" and not summary["has_objects"]:
                findings.append(f"[plain-card] {label}: no renderer-authored objects block")
            if summary["type"] == "tableEx" and not summary["has_objects"]:
                findings.append(f"[plain-table] {label}: no table formatting objects block")
    return findings


def visual_map(report: dict) -> dict[tuple[str, str], tuple[str, dict]]:
    out = {}
    fallback = {}
    for page, vc in iter_visuals(report):
        key = visual_match_key(page, vc)
        if key[1]:
            out[key] = (page, vc)
        fallback[("__fallback__", stable_json(visual_fallback_key(page, vc)))] = (page, vc)
    out.update({key: value for key, value in fallback.items() if key not in out})
    return out


def compare_reports(before: dict, after: dict) -> dict:
    before_by_name = {
        visual_match_key(page, vc): (page, vc)
        for page, vc in iter_visuals(before)
        if visual_name(vc)
    }
    after_by_name = {
        visual_match_key(page, vc): (page, vc)
        for page, vc in iter_visuals(after)
        if visual_name(vc)
    }

    before_fallback = {visual_fallback_key(page, vc): (page, vc) for page, vc in iter_visuals(before)}
    after_fallback = {visual_fallback_key(page, vc): (page, vc) for page, vc in iter_visuals(after)}

    changed = []
    added = []
    removed = []
    matched_before: set[tuple[str, str]] = set()
    matched_after: set[tuple[str, str]] = set()

    for key, before_item in before_by_name.items():
        after_item = after_by_name.get(key)
        if not after_item:
            continue
        matched_before.add(key)
        matched_after.add(key)
        before_page, before_vc = before_item
        after_page, after_vc = after_item
        if hash_obj(normalize_visual(before_vc)) != hash_obj(normalize_visual(after_vc)):
            changed.append(change_record(before_page, before_vc, after_page, after_vc))

    for key, before_item in before_by_name.items():
        if key in matched_before:
            continue
        fallback_key = visual_fallback_key(*before_item)
        after_item = after_fallback.get(fallback_key)
        if after_item:
            before_page, before_vc = before_item
            after_page, after_vc = after_item
            if hash_obj(normalize_visual(before_vc)) != hash_obj(normalize_visual(after_vc)):
                changed.append(change_record(before_page, before_vc, after_page, after_vc))
        else:
            removed.append(visual_summary(*before_item))

    for key, after_item in after_by_name.items():
        if key not in matched_after and visual_fallback_key(*after_item) not in before_fallback:
            added.append(visual_summary(*after_item))

    return {"changed": changed, "added": added, "removed": removed}


def change_record(before_page: str, before_vc: dict, after_page: str, after_vc: dict) -> dict:
    before_config = decode_config(before_vc)
    after_config = decode_config(after_vc)
    before_sv = before_config.get("singleVisual", {})
    after_sv = after_config.get("singleVisual", {})
    return {
        "before": visual_summary(before_page, before_vc),
        "after": visual_summary(after_page, after_vc),
        "container_changed": {
            key: {"before": before_vc.get(key), "after": after_vc.get(key)}
            for key in ("x", "y", "width", "height", "z")
            if before_vc.get(key) != after_vc.get(key)
        },
        "single_visual_keys_changed": sorted(
            key for key in set(before_sv) | set(after_sv) if before_sv.get(key) != after_sv.get(key)
        ),
        "objects_before": before_sv.get("objects", {}),
        "objects_after": after_sv.get("objects", {}),
        "after_visual_container": normalize_visual(after_vc),
    }


def emit_candidates(diff: dict, out_dir: Path) -> Path:
    candidate_dir = out_dir / "candidates" / timestamp()
    candidate_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# RW visual candidates", ""]
    for idx, record in enumerate(diff["changed"], start=1):
        after = record["after"]
        prefix = f"{idx:02d}_{slug(after['page'])}_{slug(after['name'] or 'visual')}"
        visual_path = candidate_dir / f"{prefix}.visual_container.json"
        objects_path = candidate_dir / f"{prefix}.objects.json"
        write_json(visual_path, record["after_visual_container"])
        write_json(objects_path, record["objects_after"])
        lines.extend(
            [
                f"## {idx}. {after['page']} / {after['name']}",
                "",
                f"- type: `{after['type']}`",
                f"- title: `{after['title']}`",
                f"- fields: `{'; '.join(after['fields'])}`",
                f"- changed keys: `{', '.join(record['single_visual_keys_changed'])}`",
                f"- objects: `{objects_path.name}`",
                f"- visual: `{visual_path.name}`",
                "",
            ]
        )
    (candidate_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")
    return candidate_dir


def resolve_after_path(args: argparse.Namespace) -> Path:
    if args.after_desktop:
        return DEFAULT_DESKTOP_REPORT
    return args.after


def cmd_snapshot(args: argparse.Namespace) -> None:
    report = load_report(args.source, args.path)
    label = slug(args.label or f"{args.source}_{timestamp()}")
    out_dir = args.out_dir / "snapshots"
    report_path = out_dir / f"{label}.report.json"
    write_json(report_path, report)
    summaries = inventory(report, args.page)
    json_path, csv_path = write_inventory(out_dir, summaries, label)
    print(f"snapshot: {report_path}")
    print(f"inventory json: {json_path}")
    print(f"inventory csv: {csv_path}")
    print_inventory_summary(summaries)


def cmd_inventory(args: argparse.Namespace) -> None:
    report = load_report(args.source, args.path)
    summaries = inventory(report, args.page)
    label = slug(args.label or f"{args.source}_{timestamp()}")
    json_path, csv_path = write_inventory(args.out_dir / "inventory", summaries, label)
    print(f"inventory json: {json_path}")
    print(f"inventory csv: {csv_path}")
    print_inventory_summary(summaries)


def cmd_audit(args: argparse.Namespace) -> None:
    report = load_report(args.source, args.path)
    findings = audit(report)
    out_path = args.out_dir / "audit" / f"{slug(args.label or args.source)}.audit.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(findings) + ("\n" if findings else ""), encoding="utf-8")
    print(f"audit: {out_path}")
    if not findings:
        print("no findings")
        return
    for finding in findings:
        print(finding)


def cmd_diff(args: argparse.Namespace) -> None:
    before = load_report_from_path(args.before)
    after = load_report_from_path(resolve_after_path(args))
    diff = compare_reports(before, after)
    out_dir = args.out_dir / "diffs"
    label = slug(args.label or timestamp())
    diff_path = out_dir / f"{label}.diff.json"
    write_json(diff_path, diff)
    print(f"diff: {diff_path}")
    print(
        f"changed={len(diff['changed'])} added={len(diff['added'])} removed={len(diff['removed'])}"
    )
    for record in diff["changed"]:
        after_summary = record["after"]
        keys = ", ".join(record["single_visual_keys_changed"])
        print(f"changed: {after_summary['page']} / {after_summary['name']} / {keys}")
    if args.emit_candidates and diff["changed"]:
        print(f"candidates: {emit_candidates(diff, args.out_dir)}")


def cmd_extract(args: argparse.Namespace) -> None:
    report = load_report(args.source, args.path)
    matches = []
    for page, vc in iter_visuals(report, args.page):
        name = visual_name(vc)
        title = " ".join(display_titles(vc))
        if args.name and not name.startswith(args.name) and args.name not in title:
            continue
        matches.append((page, vc))
    if not matches:
        raise SystemExit("no matching visual found")
    if len(matches) > 1 and not args.all:
        for page, vc in matches:
            summary = visual_summary(page, vc)
            print(
                f"{summary['page']} {summary['name']} {summary['type']} "
                f"{summary['title']} {summary['fields']}"
            )
        raise SystemExit("multiple matches; pass a longer --name or --all")
    payloads = []
    for page, vc in matches:
        normalized = normalize_visual(vc)
        if args.objects_only:
            normalized = decode_config(vc).get("singleVisual", {}).get("objects", {})
        payloads.append({"page": page, "visual": normalized})
    print(json.dumps(payloads[0] if len(payloads) == 1 else payloads, indent=2))


def add_source_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source", choices=("live", "desktop", "path"), default="desktop")
    parser.add_argument("--path", type=Path, help="report.json path when --source path")
    parser.add_argument("--page", help="Optional page displayName filter")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--label", help="Output label")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_snapshot = sub.add_parser("snapshot", help="Save report.json plus inventory")
    add_source_args(p_snapshot)
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_inventory = sub.add_parser("inventory", help="Write visual inventory JSON/CSV")
    add_source_args(p_inventory)
    p_inventory.set_defaults(func=cmd_inventory)

    p_audit = sub.add_parser("audit", help="Flag visual finish gaps")
    add_source_args(p_audit)
    p_audit.set_defaults(func=cmd_audit)

    p_diff = sub.add_parser("diff", help="Diff two report.json files")
    p_diff.add_argument("--before", type=Path, required=True)
    after = p_diff.add_mutually_exclusive_group(required=True)
    after.add_argument("--after", type=Path)
    after.add_argument("--after-desktop", action="store_true")
    p_diff.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p_diff.add_argument("--label", help="Output label")
    p_diff.add_argument("--emit-candidates", action="store_true")
    p_diff.set_defaults(func=cmd_diff)

    p_extract = sub.add_parser("extract", help="Extract one visual from live/desktop/path")
    add_source_args(p_extract)
    p_extract.add_argument("--name", help="Visual name prefix or title substring")
    p_extract.add_argument("--objects-only", action="store_true")
    p_extract.add_argument("--all", action="store_true")
    p_extract.set_defaults(func=cmd_extract)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
