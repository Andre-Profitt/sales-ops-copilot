"""Tests for rw_zebra_kg_graphrag index builder + retriever."""

from __future__ import annotations

import json

import numpy as np

from scripts.sales.rw_zebra_kg_graphrag import chunk_markdown, build_index


SAMPLE_MD = """\
# Title

## §3 Column synthesis

The X,Y projection rule auto-derives `<x>-<y>` and `<x>-<y>-percent` columns.
Format codes: 0=integer, 1=signed, 2=percent.

## §6 Cards rendering

Cards composite tile = header textbox + value card + variance card.

### §6.1 Bullet markerStyle

markerStyle=5 produces the integrated bullet bar.
"""


def test_chunk_markdown_emits_one_node_per_h2_or_h3():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    sections = [c["section"] for c in chunks]
    assert "§3 Column synthesis" in sections
    assert "§6 Cards rendering" in sections
    assert "§6.1 Bullet markerStyle" in sections


def test_chunk_markdown_preserves_section_text():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    by_section = {c["section"]: c for c in chunks}
    assert "auto-derives" in by_section["§3 Column synthesis"]["text"]
    assert "markerStyle=5" in by_section["§6.1 Bullet markerStyle"]["text"]


def test_chunk_markdown_each_node_has_required_fields():
    chunks = chunk_markdown(SAMPLE_MD, source_doc="test.md")
    for c in chunks:
        assert set(c.keys()) >= {"id", "source_doc", "section", "anchor", "text"}


def test_build_index_writes_three_files(tmp_path):
    md_path = tmp_path / "sample.md"
    md_path.write_text(SAMPLE_MD)
    out_dir = tmp_path / "graphrag"
    build_index([md_path], out_dir, model_name="sentence-transformers/all-MiniLM-L6-v2")
    assert (out_dir / "nodes.jsonl").exists()
    assert (out_dir / "embeddings.npy").exists()
    assert (out_dir / "manifest.json").exists()


def test_build_index_node_count_matches_embedding_rows(tmp_path):
    md_path = tmp_path / "sample.md"
    md_path.write_text(SAMPLE_MD)
    out_dir = tmp_path / "graphrag"
    build_index([md_path], out_dir, model_name="sentence-transformers/all-MiniLM-L6-v2")
    nodes = [json.loads(l) for l in (out_dir / "nodes.jsonl").open()]
    emb = np.load(out_dir / "embeddings.npy")
    assert len(nodes) == emb.shape[0]
    assert emb.shape[1] == 384  # all-MiniLM-L6-v2 dim
