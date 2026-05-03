#!/usr/bin/env python3
"""Phase 2 — label decompiled tcaddin.dll functions using `claude` CLI (Max subscription).

Refactored from the API-based labeler: now uses the `claude` CLI binary which
authenticates via the user's Anthropic Max subscription. No paid API tokens.

Strategy:
- Process functions in BATCHES (50 per CLI invocation) to amortize startup cost
- Each batch is one `claude -p '<prompt>'` call
- Targeted: top-N functions by interestingness, default 500
- For 500 functions @ 50/batch = 10 invocations
- Output: SQLite database with labels + FTS5 index

Usage:
  .venv/bin/python scripts/label_thinkcell_functions_with_claude_cli.py \\
    --jsonl state/thinkcell_bridge/ghidra_decompile/<run>/functions.jsonl \\
    --top-n 500 --batch-size 50

Env: requires `claude` CLI on PATH (logged in via Max subscription).
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BATCH_PROMPT_TEMPLATE = """You are a reverse engineer analyzing functions from think-cell's PowerPoint add-in (tcaddin.dll).

For each function below, produce ONE structured JSON object with these fields:
- "address": the function address as given
- "summary": one-sentence description of what this function does
- "category": one of [chart_construction, ppttc_parser, com_dispatch, style_management, gallery_ui, bain_toolbox, ai_features, telemetry, ipc_tcasr, hook_engine, license_validation, update_check, stock_image, persistence, math_layout, util_string, util_collection, util_filesystem, ribbon_callback, http_client, hmac_auth, cfb_serializer, thinkcellxml, unknown]
- "keywords": 3-7 short technical keywords
- "internal_calls": list of internal function names this calls (best inferred from the code)
- "external_calls": list of Win32/COM/CRT API calls
- "interest_score": 0-10
- "ground_truth_evidence": brief evidence quote from the decompiled code

Output MUST be a JSON array of these objects, one per function, in the same order.
Output ONLY the JSON array. No prose, no markdown fences.

Functions to label:

{functions}
"""

FUNCTION_TEMPLATE = """### Function {idx}
- address: {address}
- name: {name}
- calling_convention: {calling_convention}
- body_size: {body_size}
- symbols: {symbols}

```c
{decompiled_c}
```
"""


def _interestingness_score(fn: dict) -> int:
    score = 0
    name = fn.get("name", "") or ""
    body = int(fn.get("body_size", 0) or 0)
    if "::" in name:
        score += 5
    if not name.startswith("FUN_"):
        score += 3
    if body > 200:
        score += 1
    if body > 1000:
        score += 2
    nlower = name.lower()
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
        "flaticon",
        "http",
        "request",
        "hmac",
        "sign",
        "token",
        "cloud",
        "send",
        "fetch",
        "cfb",
        "ole",
        "smart",
        "sequence",
        "container",
    ]
    for k in keywords:
        if k in nlower:
            score += 2
    # Match known C++ class names from the corpus extraction
    chart_class_seeds = [
        "CSmartGrid",
        "CContainerSE",
        "CSequenceChart",
        "CPPTLine",
        "CPPTPolyline",
        "CPPTRectangle",
        "CDataAxis",
        "CGridline",
        "CVariableSource",
        "CTextVariable",
        "CSLTBSizeCalculator",
    ]
    for c in chart_class_seeds:
        if c.lower() in nlower:
            score += 4
            break
    return min(score, 15)


def _claude_cli_available() -> bool:
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=10, check=False
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_claude_cli(prompt: str, *, timeout: int = 600) -> dict:
    """Invoke `claude -p` (one-shot prompt) and return its stdout."""
    out = {"stdout": None, "stderr": None, "returncode": None, "error": None}
    try:
        r = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out["stdout"] = r.stdout
        out["stderr"] = r.stderr
        out["returncode"] = r.returncode
    except subprocess.TimeoutExpired:
        out["error"] = "timeout"
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _parse_label_array(text: str) -> list[dict]:
    """Extract JSON array from claude's output. Tolerates code fences and prose."""
    if not text:
        return []
    # Strip markdown fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"```\s*$", "", text)
    # Find first [ ... ] block
    m = re.search(r"\[\s*\{[\s\S]*\}\s*\]", text)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return []


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


def _label_batch(batch: list[dict], db: sqlite3.Connection) -> int:
    """Label one batch via claude CLI; write results to DB. Returns count of labeled."""
    func_blocks = []
    for i, fn in enumerate(batch, 1):
        # Truncate decompiled C to keep prompt size manageable
        c = (fn.get("decompiled_c", "") or "")[:4000]
        func_blocks.append(
            FUNCTION_TEMPLATE.format(
                idx=i,
                address=fn.get("address", "?"),
                name=fn.get("name", "?"),
                calling_convention=fn.get("calling_convention", "?"),
                body_size=fn.get("body_size", "?"),
                symbols=",".join(fn.get("symbols", []) or []),
                decompiled_c=c,
            )
        )
    prompt = BATCH_PROMPT_TEMPLATE.format(functions="\n".join(func_blocks))
    res = _run_claude_cli(prompt)
    if res["returncode"] != 0 or not res["stdout"]:
        cur = db.cursor()
        for fn in batch:
            cur.execute(
                "UPDATE functions SET label_error=?, label_at=? WHERE address=?",
                (
                    f"cli_failed: {res.get('error') or res.get('stderr', '')[:200]}",
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    fn.get("address"),
                ),
            )
        db.commit()
        return 0
    labels = _parse_label_array(res["stdout"])
    if not labels:
        cur = db.cursor()
        for fn in batch:
            cur.execute(
                "UPDATE functions SET label_error=?, label_at=? WHERE address=?",
                (
                    "parse_failed",
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    fn.get("address"),
                ),
            )
        db.commit()
        return 0
    cur = db.cursor()
    by_addr = {fn.get("address"): fn for fn in batch}
    n_labeled = 0
    for label in labels:
        addr = label.get("address")
        if addr not in by_addr:
            continue
        cur.execute(
            """UPDATE functions SET
            label_json=?, label_summary=?, label_category=?, label_keywords=?,
            interest_score=?, label_at=? WHERE address=?""",
            (
                json.dumps(label),
                label.get("summary"),
                label.get("category"),
                ",".join(label.get("keywords", []) or []),
                label.get("interest_score"),
                time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                addr,
            ),
        )
        n_labeled += 1
    db.commit()
    return n_labeled


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--top-n", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not _claude_cli_available() and not args.dry_run:
        raise SystemExit("`claude` CLI not on PATH. Install + login first.")

    db_path = args.db or args.jsonl.parent / "functions.db"
    db = _setup_db(db_path)

    funcs = []
    with args.jsonl.open() as f:
        for line in f:
            try:
                funcs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    print(f"[label-cli] loaded {len(funcs)} functions from {args.jsonl}", flush=True)

    for fn in funcs:
        fn["interestingness"] = _interestingness_score(fn)
    funcs.sort(key=lambda x: -x["interestingness"])
    selected = funcs[: args.top_n]
    print(f"[label-cli] selected top {len(selected)} by interestingness", flush=True)

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
    print(f"[label-cli] wrote {len(funcs)} rows to {db_path}", flush=True)

    if args.dry_run:
        print("[label-cli] dry-run; sample top 20:")
        for fn in selected[:20]:
            print(f"  score={fn['interestingness']:2d} {fn.get('address')} {fn.get('name')}")
        return 0

    total_labeled = 0
    n_batches = (len(selected) + args.batch_size - 1) // args.batch_size
    for i in range(0, len(selected), args.batch_size):
        batch = selected[i : i + args.batch_size]
        bi = i // args.batch_size + 1
        print(f"[label-cli] batch {bi}/{n_batches} ({len(batch)} funcs)", flush=True)
        n = _label_batch(batch, db)
        total_labeled += n
        print(f"[label-cli]   labeled: {n}/{len(batch)} (cumulative: {total_labeled})", flush=True)
    print(f"\n[label-cli] done. {total_labeled}/{len(selected)} functions labeled.")
    print(f"[label-cli] db: {db_path}")
    print(
        f"\nQuery via: sqlite3 {db_path} \"SELECT * FROM functions_fts WHERE functions_fts MATCH 'chart constructor';\""
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
