"""Semantic retriever over the Zebra + native PBI infrastructure atlases.

Chunks the two markdown files at heading boundaries, embeds with
sentence-transformers all-MiniLM-L6-v2, persists to data/zebra_kg/graphrag/.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.1
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

_HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)\s*$")


def chunk_markdown(text: str, source_doc: str) -> list[dict]:
    """Chunk markdown by H2/H3 headings.

    Each chunk: {id, source_doc, section, anchor, text}. id is a content hash.
    """
    lines = text.splitlines()
    chunks: list[dict] = []
    current: dict | None = None
    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current is not None:
                current["text"] = current["text"].strip()
                chunks.append(current)
            section = m.group(2).strip()
            anchor = re.sub(r"[^a-z0-9]+", "-", section.lower()).strip("-")
            current = {
                "id": "",
                "source_doc": source_doc,
                "section": section,
                "anchor": anchor,
                "text": "",
            }
        elif current is not None:
            current["text"] += line + "\n"
    if current is not None:
        current["text"] = current["text"].strip()
        chunks.append(current)
    for c in chunks:
        h = hashlib.sha1((c["source_doc"] + c["section"] + c["text"]).encode()).hexdigest()[:16]
        c["id"] = h
    return chunks


def build_index(
    md_paths: list[Path],
    out_dir: Path,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> None:
    """Chunk all markdown files, embed, persist to out_dir.

    Writes nodes.jsonl, embeddings.npy, manifest.json.
    """
    from sentence_transformers import SentenceTransformer

    out_dir.mkdir(parents=True, exist_ok=True)
    nodes: list[dict] = []
    for p in md_paths:
        nodes.extend(chunk_markdown(p.read_text(), source_doc=p.name))
    model = SentenceTransformer(model_name)
    texts = [n["text"] for n in nodes]
    emb = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

    nodes_path = out_dir / "nodes.jsonl"
    with nodes_path.open("w") as f:
        for n in nodes:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")
    np.save(out_dir / "embeddings.npy", emb.astype("float32"))
    manifest = {
        "model": model_name,
        "node_count": len(nodes),
        "embedding_dim": int(emb.shape[1]) if len(emb) else 0,
        "sources": [str(p) for p in md_paths],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))


import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    id: str
    source_doc: str
    section: str
    anchor: str
    text: str
    score: float


_MODEL_CACHE: dict[str, object] = {}


def _load_model(name: str):
    if name not in _MODEL_CACHE:
        from sentence_transformers import SentenceTransformer

        _MODEL_CACHE[name] = SentenceTransformer(name)
    return _MODEL_CACHE[name]


def retrieve(
    intent: str,
    index_dir: Path = Path("data/zebra_kg/graphrag"),
    top_k: int = 5,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> list[Chunk]:
    """Cosine-similarity rank atlas chunks against the intent query."""
    nodes_path = index_dir / "nodes.jsonl"
    emb_path = index_dir / "embeddings.npy"
    if not nodes_path.exists() or not emb_path.exists():
        raise FileNotFoundError(
            f"GraphRAG index missing under {index_dir}. Run "
            f"`python -m scripts.sales.rw_zebra_kg_graphrag build` first."
        )
    nodes = [json.loads(l) for l in nodes_path.open()]
    emb = np.load(emb_path)
    model = _load_model(model_name)
    q = model.encode([intent], convert_to_numpy=True)[0]
    q_norm = q / (np.linalg.norm(q) + 1e-12)
    e_norm = emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-12)
    scores = e_norm @ q_norm
    top_idx = np.argsort(-scores)[:top_k]
    return [
        Chunk(
            id=nodes[i]["id"],
            source_doc=nodes[i]["source_doc"],
            section=nodes[i]["section"],
            anchor=nodes[i]["anchor"],
            text=nodes[i]["text"],
            score=float(scores[i]),
        )
        for i in top_idx
    ]


def _cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build", help="Build the index from the two atlas markdowns")
    q = sub.add_parser("query", help="Query the index")
    q.add_argument("intent", help="Free-text intent query")
    q.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if args.cmd == "build":
        build_index(
            [
                Path("docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md"),
                Path("docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md"),
            ],
            Path("data/zebra_kg/graphrag"),
        )
    elif args.cmd == "query":
        for c in retrieve(args.intent, top_k=args.top_k):
            print(f"[{c.score:.3f}] {c.source_doc} :: {c.section}")
            print(c.text[:200].replace("\n", " "))
            print()


if __name__ == "__main__":
    _cli()
