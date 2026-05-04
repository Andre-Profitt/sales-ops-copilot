"""Tests for atlas_query.py.

The query CLI returns ranked candidates for a given query. For tests
we use a tiny in-process corpus to avoid hitting Azure OpenAI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
SCRIPT = REPO / "scripts" / "atlas" / "atlas_query.py"


def test_query_returns_ranked_candidates(tmp_path: Path) -> None:
    """A query against a synthetic corpus returns the most relevant chunks first."""
    corpus = tmp_path / "corpus.jsonl"
    # synthetic chunks with pre-baked unit-vector embeddings (3-d for tests)
    rows = [
        {
            "id": "c1",
            "source": "canonical_land",
            "slide": 5,
            "type": "pptx_slide",
            "text": "pipeline by stage horizontal bar SimCorp",
            "embedding": [1.0, 0.0, 0.0],
        },
        {
            "id": "c2",
            "source": "canonical_land",
            "slide": 7,
            "type": "pptx_slide",
            "text": "top deals table SimCorp brand",
            "embedding": [0.0, 1.0, 0.0],
        },
        {
            "id": "c3",
            "source": "current_seed_debris",
            "slide": 7,
            "type": "pptx_slide",
            "text": "[think-cell TABLE WITH FORMATTING - datalinked]",
            "embedding": [0.0, 0.0, 1.0],
        },
    ]
    corpus.write_text("\n".join(json.dumps(r) for r in rows))

    out = tmp_path / "result.json"
    proc = subprocess.run(
        [
            PY,
            str(SCRIPT),
            "--corpus",
            str(corpus),
            "--query-vector",
            "1.0,0.0,0.0",
            "--top-k",
            "2",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    res = json.loads(out.read_text())
    assert res[0]["id"] == "c1"
    assert len(res) == 2


def test_filter_by_role(tmp_path: Path) -> None:
    """Querying with role=negative_example only returns debris sources."""
    corpus = tmp_path / "corpus.jsonl"
    rows = [
        {
            "id": "c1",
            "source": "canonical_land",
            "role": "canonical_brand_reference",
            "slide": 5,
            "type": "pptx_slide",
            "text": "x",
            "embedding": [1.0, 0.0],
        },
        {
            "id": "c2",
            "source": "current_seed_debris",
            "role": "negative_example",
            "slide": 7,
            "type": "pptx_slide",
            "text": "[think-cell ...]",
            "embedding": [1.0, 0.0],
        },
    ]
    corpus.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "r.json"
    proc = subprocess.run(
        [
            PY,
            str(SCRIPT),
            "--corpus",
            str(corpus),
            "--query-vector",
            "1.0,0.0",
            "--top-k",
            "5",
            "--role",
            "negative_example",
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    assert proc.returncode == 0
    res = json.loads(out.read_text())
    assert len(res) == 1
    assert res[0]["id"] == "c2"
