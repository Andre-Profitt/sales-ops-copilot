#!/usr/bin/env python3
"""Query the local think-cell knowledge graph RAG index."""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_KG_DIR = ROOT / "state" / "thinkcell_bridge" / "knowledge_graph"


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _score_docs(query: str, docs: list[dict[str, Any]]) -> list[tuple[float, dict[str, Any]]]:
    q_terms = _tokens(query)
    if not q_terms:
        return []
    q_counts = Counter(q_terms)
    doc_freq: Counter[str] = Counter()
    for doc in docs:
        doc_freq.update(set(doc.get("terms", [])))
    total_docs = max(len(docs), 1)
    scored = []
    for doc in docs:
        terms = Counter(doc.get("terms", []))
        title_terms = set(_tokens(doc.get("title", "")))
        text = doc.get("text", "").lower()
        score = 0.0
        for term, q_count in q_counts.items():
            if terms[term] == 0 and term not in text:
                continue
            idf = math.log((1 + total_docs) / (1 + doc_freq[term])) + 1
            score += (1 + math.log(1 + terms[term])) * idf * q_count
            if term in title_terms:
                score += 2.5 * idf
            if term in text:
                score += 0.5
        phrase = query.lower().strip()
        if len(phrase) >= 4 and phrase in text:
            score += 8
        if score:
            scored.append((score, doc))
    return sorted(scored, key=lambda item: (-item[0], item[1].get("title", "")))


def _neighbors(node_ids: list[str], edges: list[dict[str, Any]], nodes: dict[str, dict[str, Any]], limit: int) -> list[str]:
    seen: set[str] = set()
    lines: list[str] = []
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if source not in node_ids and target not in node_ids:
            continue
        other = target if source in node_ids else source
        key = f"{source}|{edge['relation']}|{target}"
        if key in seen:
            continue
        seen.add(key)
        other_node = nodes.get(other, {})
        source_node = nodes.get(source, {})
        target_node = nodes.get(target, {})
        lines.append(
            f"{source_node.get('label', source)} --{edge['relation']}--> "
            f"{target_node.get('label', target)}"
        )
        if len(lines) >= limit:
            break
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--kg-dir", type=Path, default=DEFAULT_KG_DIR)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--neighbors", type=int, default=12)
    parser.add_argument("--kind", action="append", help="Restrict retrieval to one document kind. Can be repeated.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    args = parser.parse_args()

    rag = json.loads((args.kg_dir / "thinkcell_graph_rag_index.json").read_text(encoding="utf-8"))
    nodes = {row["id"]: row for row in _load_jsonl(args.kg_dir / "thinkcell_kg_nodes.jsonl")}
    edges = _load_jsonl(args.kg_dir / "thinkcell_kg_edges.jsonl")
    docs = rag["documents"]
    if args.kind:
        kinds = {kind.lower() for kind in args.kind}
        docs = [doc for doc in docs if str(doc.get("kind", "")).lower() in kinds]
    scored = _score_docs(args.query, docs)[: args.limit]
    results = []
    for score, doc in scored:
        node_ids = doc.get("node_ids", [])
        results.append(
            {
                "score": round(score, 3),
                "id": doc["id"],
                "kind": doc["kind"],
                "title": doc["title"],
                "text": doc["text"],
                "node_ids": node_ids,
                "neighbors": _neighbors(node_ids, edges, nodes, args.neighbors),
            }
        )
    if args.json:
        print(json.dumps({"query": args.query, "results": results}, indent=2))
        return 0

    print(f"# think-cell KG Query: {args.query}\n")
    if not results:
        print("No matches.")
        return 1
    for index, result in enumerate(results, start=1):
        snippet = re.sub(r"\s+", " ", result["text"]).strip()[:420]
        print(f"## {index}. {result['title']}")
        print(f"- Score: `{result['score']}`")
        print(f"- Kind: `{result['kind']}`")
        print(f"- Snippet: {snippet}")
        if result["neighbors"]:
            print("- Graph context:")
            for line in result["neighbors"][: args.neighbors]:
                print(f"  - {line}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
