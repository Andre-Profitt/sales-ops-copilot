"""Query the Template Atlas corpus.

Two query modes:
  --query "natural language"  -> embeds via Azure OpenAI, then cosine search
  --query-vector "f1,f2,..."   -> bypasses embedding (used by tests)

Optional filters:
  --role <r>          one of canonical_brand_reference / visual_inspiration /
                      negative_example / spec / domain_knowledge / graph_seed
  --type <t>          pptx_slide / md_section / yaml_node
  --top-k N           default 5

Output: JSON list of top-K hits, each {id, score, source, slide, role, type, text}.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _load_corpus(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _embed_text_via_apro(text: str) -> list[float]:
    """Embed via Azure OpenAI text-embedding-3-small using the project's apro-openai.

    Imported lazily so tests can run without azure-identity available.
    """
    from azure.identity import AzureCliCredential
    from openai import AzureOpenAI

    cred = AzureCliCredential()
    token = cred.get_token("https://cognitiveservices.azure.com/.default")
    client = AzureOpenAI(
        azure_endpoint=os.environ.get(
            "APRO_OPENAI_ENDPOINT", "https://apro-openai.openai.azure.com/"
        ),
        azure_ad_token=token.token,
        api_version="2024-08-01-preview",
    )
    resp = client.embeddings.create(
        input=text,
        model=os.environ.get("APRO_EMBED_DEPLOYMENT", "text-embedding-3-small"),
    )
    return list(resp.data[0].embedding)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--query", default=None)
    parser.add_argument("--query-vector", default=None)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--role", default=None)
    parser.add_argument("--type", dest="type_", default=None)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.query and not args.query_vector:
        sys.stderr.write("require --query or --query-vector\n")
        return 2

    if args.query_vector:
        qv = [float(x) for x in args.query_vector.split(",")]
    else:
        qv = _embed_text_via_apro(args.query)

    rows = _load_corpus(args.corpus)
    if args.role:
        rows = [r for r in rows if r.get("role") == args.role]
    if args.type_:
        rows = [r for r in rows if r.get("type") == args.type_]

    scored = []
    for r in rows:
        emb = r.get("embedding")
        if not emb:
            continue
        scored.append((_cosine(qv, emb), r))
    scored.sort(key=lambda x: x[0], reverse=True)

    hits = []
    for score, r in scored[: args.top_k]:
        hit = {k: v for k, v in r.items() if k != "embedding"}
        hit["score"] = round(score, 4)
        hits.append(hit)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(hits, indent=2))
    print(f"OK: {len(hits)} hits to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
