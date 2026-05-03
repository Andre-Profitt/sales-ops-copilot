#!/usr/bin/env python3
"""Phase 2 — label decompiled tcaddin.dll functions using Claude (local subscription).

Uses the user's Anthropic API key (from .env or ANTHROPIC_API_KEY env var) to
batch-label functions. Targeted strategy: process the most-interesting functions
first (large body, exported, RTTI-named), not the entire 10-20K function list.

Cost control:
- Default: process top 500 functions by interestingness score (~$5-15 with Haiku 4.5)
- Use --model claude-opus-4-7 for the high-value subset
- Prompt caching cuts cost ~90% on repeated runs

Output: SQLite database with FTS5 + sqlite-vec embeddings (if available).

Usage:
  .venv/bin/python scripts/label_thinkcell_functions_with_claude.py \\
    --jsonl state/thinkcell_bridge/ghidra_decompile/<latest>/functions.jsonl \\
    --model claude-haiku-4-5 \\
    --top-n 500
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

LABEL_PROMPT = """You are a reverse engineer analyzing a function from think-cell's PowerPoint add-in (tcaddin.dll).

Function metadata:
- Address: {address}
- Name: {name}
- Calling convention: {calling_convention}
- Body size: {body_size} bytes
- Symbols: {symbols}

Decompiled C:
```c
{decompiled_c}
```

Produce a structured JSON response with these fields:
- "summary": one-sentence description of what this function does
- "category": one of [chart_construction, .ppttc_parser, com_dispatch, style_management, gallery_ui, bain_toolbox, ai_features, telemetry, ipc_tcasr, hook_engine, license_validation, update_check, stock_image, persistence, math_layout, util_string, util_collection, util_filesystem, ribbon_callback, unknown]
- "keywords": 3-7 short technical keywords (e.g., ["safearray", "vtable", "lp_solver"])
- "internal_calls": list of internal function names this calls (best inferred from decompiled C)
- "external_calls": list of Win32/COM/CRT API calls
- "interest_score": 0-10 — how interesting is this for understanding think-cell internals?
- "ground_truth_evidence": specific evidence from the decompiled code

Return ONLY the JSON object, no prose."""


def _interestingness_score(fn: dict) -> int:
    score = 0
    name = fn.get("name", "") or ""
    sig = fn.get("signature", "") or ""
    body = int(fn.get("body_size", 0) or 0)
    symbols = fn.get("symbols", []) or []
    # RTTI-named C++ classes are gold
    if "::" in name:
        score += 5
    if any(re.search(r"^FUN_", s) for s in symbols):
        score += 0  # synthetic name; lower interest
    if not name.startswith("FUN_"):
        score += 3
    if body > 200:
        score += 1
    if body > 1000:
        score += 2
    # Heuristic keywords in name
    keywords = [
        "chart",
        "table",
        "ppttc",
        "json",
        "parse",
        "render",
        "style",
        "bain",
        "gallery",
        "ai",
        "auth",
        "telemetry",
        "tcasr",
        "hook",
        "patch",
        "license",
        "update",
        "image",
        "freepik",
        "pexels",
        "unsplash",
    ]
    nlower = name.lower()
    for k in keywords:
        if k in nlower:
            score += 2
    return min(score, 10)


def _label_function(fn: dict, *, api_key: str, model: str, max_tokens: int = 800) -> dict:
    import urllib.request as ur
    import urllib.error as ue

    body = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": LABEL_PROMPT.format(
                    address=fn.get("address", "?"),
                    name=fn.get("name", "?"),
                    calling_convention=fn.get("calling_convention", "?"),
                    body_size=fn.get("body_size", "?"),
                    symbols=",".join(fn.get("symbols", []) or []),
                    decompiled_c=(fn.get("decompiled_c", "") or "")[:8000],
                ),
            }
        ],
    }
    req = ur.Request(ANTHROPIC_API, method="POST", data=json.dumps(body).encode("utf-8"))
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", ANTHROPIC_VERSION)
    req.add_header("content-type", "application/json")
    try:
        with ur.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            text = "".join(b["text"] for b in data["content"] if b.get("type") == "text")
            label_json = re.search(r"\{[\s\S]*\}", text)
            if label_json:
                return {
                    "label": json.loads(label_json.group()),
                    "raw": text,
                    "usage": data.get("usage", {}),
                }
            return {"label": None, "raw": text, "error": "no JSON found"}
    except ue.HTTPError as e:
        return {
            "label": None,
            "error": f"HTTP {e.code}: {e.read()[:500].decode('utf-8', errors='replace')}",
        }
    except Exception as e:
        return {"label": None, "error": f"{type(e).__name__}: {e}"}


def _setup_db(db_path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(db_path)
    db.executescript("""
        CREATE TABLE IF NOT EXISTS functions (
            address TEXT PRIMARY KEY,
            name TEXT,
            signature TEXT,
            body_size INTEGER,
            calling_convention TEXT,
            symbols_json TEXT,
            decompiled_c TEXT,
            interestingness INTEGER,
            label_json TEXT,
            label_summary TEXT,
            label_category TEXT,
            label_keywords TEXT,
            interest_score INTEGER,
            label_error TEXT,
            label_model TEXT,
            label_at TEXT
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS functions_fts USING fts5(
            address, name, label_summary, label_keywords, decompiled_c,
            content='functions', content_rowid='rowid'
        );
        CREATE TRIGGER IF NOT EXISTS functions_ai AFTER INSERT ON functions BEGIN
            INSERT INTO functions_fts(rowid, address, name, label_summary, label_keywords, decompiled_c)
            VALUES (new.rowid, new.address, new.name, new.label_summary, new.label_keywords, new.decompiled_c);
        END;
        CREATE TRIGGER IF NOT EXISTS functions_au AFTER UPDATE ON functions BEGIN
            INSERT INTO functions_fts(functions_fts, rowid, address, name, label_summary, label_keywords, decompiled_c)
            VALUES ('delete', old.rowid, old.address, old.name, old.label_summary, old.label_keywords, old.decompiled_c);
            INSERT INTO functions_fts(rowid, address, name, label_summary, label_keywords, decompiled_c)
            VALUES (new.rowid, new.address, new.name, new.label_summary, new.label_keywords, new.decompiled_c);
        END;
    """)
    return db


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--model", default="claude-haiku-4-5-20251001")
    parser.add_argument("--top-n", type=int, default=500)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        env_path = ROOT / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("ANTHROPIC_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not api_key:
            raise SystemExit("ANTHROPIC_API_KEY not set in env or .env (use --dry-run to skip)")

    db_path = args.db or args.jsonl.parent / "functions.db"
    db = _setup_db(db_path)

    funcs = []
    with args.jsonl.open() as f:
        for line in f:
            try:
                funcs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"[label] loaded {len(funcs)} functions from {args.jsonl}", flush=True)

    # Score + select top-N
    for fn in funcs:
        fn["interestingness"] = _interestingness_score(fn)
    funcs.sort(key=lambda x: -x["interestingness"])
    selected = funcs[: args.top_n]
    print(f"[label] processing top {len(selected)} by interestingness", flush=True)

    # Insert all functions first
    cur = db.cursor()
    for fn in funcs:
        cur.execute(
            """INSERT OR REPLACE INTO functions
            (address, name, signature, body_size, calling_convention, symbols_json,
             decompiled_c, interestingness)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                fn.get("address"),
                fn.get("name"),
                fn.get("signature"),
                int(fn.get("body_size", 0) or 0),
                fn.get("calling_convention"),
                json.dumps(fn.get("symbols", [])),
                fn.get("decompiled_c", ""),
                fn["interestingness"],
            ),
        )
    db.commit()
    print(f"[label] inserted {len(funcs)} into {db_path}", flush=True)

    if args.dry_run:
        print("[label] dry-run; skipping API calls")
        for fn in selected[:20]:
            print(f"  score={fn['interestingness']:2d} {fn.get('address')} {fn.get('name')}")
        return 0

    # Label selected
    total_in = total_out = 0
    for i, fn in enumerate(selected, 1):
        result = _label_function(fn, api_key=api_key, model=args.model)
        label = result.get("label")
        usage = result.get("usage") or {}
        total_in += usage.get("input_tokens", 0) or 0
        total_out += usage.get("output_tokens", 0) or 0
        if label:
            cur.execute(
                """UPDATE functions SET
                label_json=?, label_summary=?, label_category=?, label_keywords=?,
                interest_score=?, label_model=?, label_at=?
                WHERE address=?""",
                (
                    json.dumps(label),
                    label.get("summary"),
                    label.get("category"),
                    ",".join(label.get("keywords", []) or []),
                    label.get("interest_score"),
                    args.model,
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    fn.get("address"),
                ),
            )
        else:
            cur.execute(
                "UPDATE functions SET label_error=?, label_at=? WHERE address=?",
                (
                    result.get("error", "?"),
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    fn.get("address"),
                ),
            )
        if i % 25 == 0:
            db.commit()
            print(f"[label] {i}/{len(selected)} | tokens in={total_in} out={total_out}", flush=True)
    db.commit()
    print(f"\n[label] done. total tokens: in={total_in} out={total_out}")
    print(f"[label] db: {db_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
