"""Build a lightweight knowledge graph from registry + slot map + corpus.

Nodes:
  story_goal:<id>       — derived from registry purpose + insight-title rules
  slide_variant:<sid>   — one per registry slide
  chart_kind:<kind>
  render_lane:<lane>
  named_element:<name>
  guardrail:<id>
  debris_signature:<id>

Edges:
  story_goal -> slide_variant  (supports)
  slide_variant -> chart_kind  (uses)
  slide_variant -> render_lane (routed_via)
  slide_variant -> named_element (binds_to)
  slide_variant -> guardrail   (must_pass)
  debris_signature -> slide_variant (contaminates)

Output: state/atlas/graph.json — adjacency list, lossless.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml
from pptx import Presentation

REPO = Path(__file__).resolve().parent.parent.parent

GUARDRAILS = [
    {"id": "arr_acv_separation", "label": "Land+Expand ARR vs Renewal ACV must not blend"},
    {"id": "currency_basis", "label": "FX-converted EUR/EUR M only"},
    {"id": "stage_basis", "label": "SimCorp 8-stage process"},
    {"id": "title_rule", "label": "Every analytic slide requires evidence-backed insight title"},
    {"id": "source_rule", "label": "Every analytic slide requires source note"},
    {"id": "no_debris", "label": "No dev instructions / lorem / donor placeholders"},
]

DEBRIS_PATTERNS = [
    r"\[think-cell\b.*?\]",
    r"paste from\b",
    r"no think-cell binding here",
    r"lorem ipsum",
    r"click to add",
    r"User count \[K\]",
    r"\[USD m\]",
    r"\bProduct A\b",
    r"\bBU1\b|\bBU2\b",
]


def _add_node(graph: dict, kind: str, key: str, **props) -> str:
    node_id = f"{kind}:{key}"
    if node_id not in graph["nodes"]:
        graph["nodes"][node_id] = {"kind": kind, "key": key, **props}
    return node_id


def _add_edge(graph: dict, frm: str, to: str, kind: str, **props) -> None:
    graph["edges"].append({"from": frm, "to": to, "kind": kind, **props})


def _scan_debris(pptx_path: Path) -> list[dict]:
    if not pptx_path.exists():
        return []
    prs = Presentation(str(pptx_path))
    findings: list[dict] = []
    for i, slide in enumerate(prs.slides, 1):
        for shape in slide.shapes:
            if shape.has_text_frame:
                t = shape.text_frame.text or ""  # type: ignore[attr-defined]
                for pat in DEBRIS_PATTERNS:
                    m = re.search(pat, t, re.IGNORECASE)
                    if m:
                        findings.append(
                            {
                                "pattern": pat,
                                "slide": i,
                                "snippet": t[: max(m.end() + 20, 80)],
                            }
                        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry", default="config/thinkcell/land_review_full_28.binding_registry.yml", type=Path
    )
    parser.add_argument(
        "--titles-rules", default="config/rules/land_review_insight_titles.yml", type=Path
    )
    parser.add_argument("--debris-pptx", default="assets/LAND_thinkcell_seed.pptx", type=Path)
    parser.add_argument("--out", default="state/atlas/graph.json", type=Path)
    args = parser.parse_args(argv)

    graph: dict = {"nodes": {}, "edges": []}

    registry = yaml.safe_load(args.registry.read_text())
    titles = (
        yaml.safe_load(args.titles_rules.read_text())
        if args.titles_rules.exists()
        else {"rules": {}, "defaults": {}}
    )

    # guardrails as fixed nodes
    for g in GUARDRAILS:
        _add_node(graph, "guardrail", g["id"], label=g["label"])

    # one slide_variant per registry slide
    for slide in registry["slides"]:
        sid = slide["slide_id"]
        purpose = slide.get("purpose", "")
        sv = _add_node(graph, "slide_variant", sid, purpose=purpose)

        # purpose -> story_goal (1:1 for MVP)
        sg = _add_node(graph, "story_goal", purpose, source="registry")
        _add_edge(graph, sg, sv, "supports")

        for el in slide.get("elements", []):
            ne = _add_node(graph, "named_element", el["name"], required=el.get("required", False))
            _add_edge(graph, sv, ne, "binds_to")
            ck = _add_node(graph, "chart_kind", el["kind"])
            _add_edge(graph, sv, ck, "uses")
            rl = _add_node(graph, "render_lane", el["lane"])
            _add_edge(graph, sv, rl, "routed_via")

        # guardrails apply to every analytic slide
        if not purpose.endswith("_divider") and purpose not in ("cover", "closing"):
            for g in GUARDRAILS:
                _add_edge(graph, sv, f"guardrail:{g['id']}", "must_pass")

    # title rules attach to slide_variant via story_goal label
    for sid, rules in (titles.get("rules") or {}).items():
        sv = f"slide_variant:{sid}"
        if sv not in graph["nodes"]:
            continue
        for rule in rules:
            tg = _add_node(
                graph,
                "story_goal",
                rule.get("id", "rule"),
                source="title_rules",
                severity=rule.get("severity"),
            )
            _add_edge(graph, tg, sv, "supports")

    # debris signatures from the contaminated seed
    debris = _scan_debris(args.debris_pptx)
    seen_patterns: set[str] = set()
    for d in debris:
        ds = _add_node(graph, "debris_signature", d["pattern"], example_snippet=d["snippet"][:200])
        if d["pattern"] in seen_patterns:
            continue
        seen_patterns.add(d["pattern"])
        # contaminate every slide_variant so debris scanner can use the graph as a deny-list
        for nid, n in graph["nodes"].items():
            if n["kind"] == "slide_variant":
                _add_edge(graph, ds, nid, "contaminates")

    # render summary
    summary = {
        "node_count": len(graph["nodes"]),
        "edge_count": len(graph["edges"]),
        "by_kind": {},
    }
    for n in graph["nodes"].values():
        summary["by_kind"][n["kind"]] = summary["by_kind"].get(n["kind"], 0) + 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, **graph}, indent=2))
    print(f"OK: {summary['node_count']} nodes / {summary['edge_count']} edges -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
