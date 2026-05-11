"""Mine Zebra BI template PBIX files into sanitized RW design artifacts.

This intentionally mines report grammar, not proprietary bypass material:

- visual types, pages, positions, projection roles, and textbox labels
- sanitized object group/property names
- graph nodes/edges for template -> page -> visual -> role -> field

It does not persist Zebra license keys. Any object group containing "license"
is dropped from pattern outputs.

Usage:
    python3 -m scripts.sales.rw_zebra_template_miner \
      --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
      --out-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any

ZEBRA_MARKERS = ("zebra", "waterfall")


@dataclass(frozen=True)
class PbixLayout:
    template_slug: str
    archive_path: Path
    pbix_name: str
    layout: dict[str, Any]


def template_slug(path: Path) -> str:
    """Infer the Zebra template slug from the downloaded file name."""
    return path.stem.split("__", 1)[0]


def load_layout(raw_pbix: bytes) -> dict[str, Any]:
    """Read Report/Layout from a PBIX byte string."""
    with zipfile.ZipFile(io.BytesIO(raw_pbix)) as pbix:
        return json.loads(pbix.read("Report/Layout").decode("utf-16-le"))


def iter_pbix_layouts(source_dir: Path) -> list[PbixLayout]:
    """Return every PBIX layout found in a directory of .zip/.pbix files."""
    layouts: list[PbixLayout] = []
    for path in sorted(source_dir.glob("*")):
        if path.suffix.lower() == ".pbix":
            layouts.append(
                PbixLayout(
                    template_slug=template_slug(path),
                    archive_path=path,
                    pbix_name=path.name,
                    layout=load_layout(path.read_bytes()),
                )
            )
            continue
        if path.suffix.lower() != ".zip":
            continue
        with zipfile.ZipFile(path) as outer:
            for member in outer.namelist():
                if member.lower().endswith(".pbix"):
                    layouts.append(
                        PbixLayout(
                            template_slug=template_slug(path),
                            archive_path=path,
                            pbix_name=Path(member).name,
                            layout=load_layout(outer.read(member)),
                        )
                    )
    return layouts


def parse_config(visual_container: dict[str, Any]) -> dict[str, Any]:
    config = visual_container.get("config")
    if isinstance(config, str):
        try:
            return json.loads(config)
        except json.JSONDecodeError:
            return {}
    return config or {}


def projection_roles(single_visual: dict[str, Any]) -> dict[str, list[str]]:
    roles: dict[str, list[str]] = {}
    for role, values in (single_visual.get("projections") or {}).items():
        refs = [value.get("queryRef") for value in values if value.get("queryRef")]
        if refs:
            roles[role] = refs
    return roles


def textbox_text(single_visual: dict[str, Any]) -> str:
    values: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if "textRuns" in node:
                for run in node.get("textRuns") or []:
                    value = run.get("value")
                    if isinstance(value, str):
                        values.append(value)
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    if single_visual.get("visualType") == "textbox":
        walk(single_visual.get("objects", {}))
    return " ".join(unescape(" ".join(values)).split())


def sanitized_object_groups(single_visual: dict[str, Any]) -> dict[str, list[str]]:
    """Return only object group/property names, excluding license groups."""
    out: dict[str, list[str]] = {}
    for group, instances in (single_visual.get("objects") or {}).items():
        if "license" in group.lower():
            continue
        props: set[str] = set()
        for instance in instances or []:
            props.update((instance.get("properties") or {}).keys())
        out[group] = sorted(props)
    return out


def is_zebra_visual(visual_type: str) -> bool:
    lower = visual_type.lower()
    return any(marker in lower for marker in ZEBRA_MARKERS)


def mine_layouts(layouts: list[PbixLayout]) -> dict[str, list[dict[str, Any]]]:
    template_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []
    visual_rows: list[dict[str, Any]] = []
    patterns: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_ids: set[str] = set()

    def node(node_id: str, kind: str, **props: Any) -> None:
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"id": node_id, "kind": kind, **props})

    def edge(source: str, relationship: str, target: str, **props: Any) -> None:
        edges.append(
            {
                "source": source,
                "relationship": relationship,
                "target": target,
                **props,
            }
        )

    by_template: dict[str, Counter[str]] = {}
    by_template_pages: Counter[str] = Counter()
    by_template_visuals: Counter[str] = Counter()
    by_template_zebra: Counter[str] = Counter()

    for pbix in layouts:
        template_id = f"template:{pbix.template_slug}"
        node(
            template_id,
            "template",
            slug=pbix.template_slug,
            archive=str(pbix.archive_path),
            pbix=pbix.pbix_name,
        )
        by_template.setdefault(pbix.template_slug, Counter())
        for section in pbix.layout.get("sections", []):
            page_name = section.get("displayName") or section.get("name")
            page_id = f"{template_id}/page:{page_name}"
            node(
                page_id,
                "page",
                name=page_name,
                template=pbix.template_slug,
                width=section.get("width"),
                height=section.get("height"),
            )
            edge(template_id, "HAS_PAGE", page_id)
            page_counter: Counter[str] = Counter()
            by_template_pages[pbix.template_slug] += 1
            for index, visual_container in enumerate(section.get("visualContainers", [])):
                config = parse_config(visual_container)
                single_visual = config.get("singleVisual", {})
                visual_type = single_visual.get("visualType") or "<none>"
                visual_id = f"{page_id}/visual:{index}"
                roles = projection_roles(single_visual)
                position = (
                    config.get("layouts", [{}])[0].get("position", {})
                    if config.get("layouts")
                    else {}
                )
                node(
                    visual_id,
                    "visual",
                    visualType=visual_type,
                    page=page_name,
                    template=pbix.template_slug,
                    x=position.get("x", visual_container.get("x")),
                    y=position.get("y", visual_container.get("y")),
                    width=position.get("width", visual_container.get("width")),
                    height=position.get("height", visual_container.get("height")),
                )
                edge(page_id, "HAS_VISUAL", visual_id)
                for role, refs in roles.items():
                    role_id = f"role:{role}"
                    node(role_id, "visual_role", name=role)
                    edge(visual_id, "HAS_ROLE", role_id)
                    for ref in refs:
                        field_id = f"template_field:{ref}"
                        node(field_id, "template_field", name=ref)
                        edge(visual_id, "USES_FIELD", field_id, role=role)
                visual_rows.append(
                    {
                        "template_slug": pbix.template_slug,
                        "archive": str(pbix.archive_path),
                        "pbix": pbix.pbix_name,
                        "page": page_name,
                        "visual_index": index,
                        "visual_type": visual_type,
                        "x": position.get("x", visual_container.get("x")),
                        "y": position.get("y", visual_container.get("y")),
                        "width": position.get("width", visual_container.get("width")),
                        "height": position.get("height", visual_container.get("height")),
                        "roles_json": json.dumps(roles, ensure_ascii=False),
                        "text": textbox_text(single_visual),
                    }
                )
                if is_zebra_visual(visual_type):
                    by_template_zebra[pbix.template_slug] += 1
                    patterns.append(
                        {
                            "template_slug": pbix.template_slug,
                            "pbix": pbix.pbix_name,
                            "page": page_name,
                            "visual_index": index,
                            "visual_type": visual_type,
                            "roles": roles,
                            "object_groups": sanitized_object_groups(single_visual),
                        }
                    )
                page_counter[visual_type] += 1
                by_template[pbix.template_slug][visual_type] += 1
                by_template_visuals[pbix.template_slug] += 1
            page_rows.append(
                {
                    "template_slug": pbix.template_slug,
                    "pbix": pbix.pbix_name,
                    "page": page_name,
                    "total_visuals": sum(page_counter.values()),
                    "zebra_visuals": sum(
                        count for vt, count in page_counter.items() if is_zebra_visual(vt)
                    ),
                    "visual_counts_json": json.dumps(page_counter, sort_keys=True),
                }
            )

    for slug, counts in sorted(by_template.items()):
        template_rows.append(
            {
                "template_slug": slug,
                "pages": by_template_pages[slug],
                "visuals": by_template_visuals[slug],
                "zebra_visuals": by_template_zebra[slug],
                "visual_counts_json": json.dumps(counts, sort_keys=True),
            }
        )

    return {
        "template_summary": template_rows,
        "page_visual_summary": page_rows,
        "visual_inventory": visual_rows,
        "zebra_visual_patterns": patterns,
        "graph_nodes": nodes,
        "graph_edges": edges,
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        if not rows:
            handle.write("")
            return
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_outputs(outputs: dict[str, list[dict[str, Any]]], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "template_summary.csv", outputs["template_summary"])
    write_csv(out_dir / "page_visual_summary.csv", outputs["page_visual_summary"])
    write_csv(out_dir / "visual_inventory.csv", outputs["visual_inventory"])
    (out_dir / "zebra_visual_patterns.json").write_text(
        json.dumps(outputs["zebra_visual_patterns"], indent=2),
        encoding="utf-8",
    )
    (out_dir / "graph_nodes.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in outputs["graph_nodes"]) + "\n",
        encoding="utf-8",
    )
    (out_dir / "graph_edges.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in outputs["graph_edges"]) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/files",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path.home() / "Downloads/rw-zebra-bi-template-research-20260509/analysis",
    )
    args = parser.parse_args()

    layouts = iter_pbix_layouts(args.source_dir.expanduser())
    outputs = mine_layouts(layouts)
    write_outputs(outputs, args.out_dir.expanduser())
    print(
        "mined "
        f"{len(layouts)} pbix file(s), "
        f"{len(outputs['visual_inventory'])} visual(s), "
        f"{len(outputs['zebra_visual_patterns'])} zebra visual pattern(s)"
    )
    print(args.out_dir.expanduser())


if __name__ == "__main__":
    main()
