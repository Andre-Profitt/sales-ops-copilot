#!/usr/bin/env python3
"""JA3/JA4 TLS-fingerprint bypass probe against app.prod.ai.think-cell.com.

Hypothesis: the uniform 403/146B nginx response we get from httpx is partly
explained by TLS-fingerprint blocking. Python httpx has a very distinctive
JA3 fingerprint that WAFs commonly flag.

This probe uses `tls-client` (a Python wrapper for bogdanfinn/tls-client,
a Go library that mimics real browser TLS handshakes) to send requests
that look like Chrome/Firefox/Safari/Edge to network-fingerprint observers.

If the 403/146B baseline becomes a different status (401, 200, different body
size, different content), the gate is fingerprint-based. We'd still need
the actual auth (Phase 12) — but we'd know the exact rejection layer.

Tries multiple browser profiles in case one matches what tcaddin.dll uses
(probably WinHTTP, which doesn't have a published profile — but Chrome on
Windows ARM64 is the closest browser-shaped client).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tls_client
except ImportError:
    print("FAILED: pip install tls-client", file=sys.stderr)
    sys.exit(2)


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "ai_ja3_probe"
TARGET = "https://app.prod.ai.think-cell.com"

# tls-client supported profiles. We want a spread that covers:
# - Chrome (default WAF target)
# - Firefox (different stack)
# - Safari (Apple TLS)
# - Edge (often closest to Office/WinHTTP)
# - okhttp4_android (mobile-app fingerprint, sometimes whitelisted)
# Profile names from bogdanfinn/tls-client
PROFILES = [
    "chrome_124",
    "chrome_120",
    "chrome_117",
    "firefox_123",
    "firefox_117",
    "safari_17_0",
    "safari_ios_17_0",
    "okhttp4_android_13",
    "opera_91",
]

PATHS = [
    "/",
    "/core/",
    "/core/v1/chat/completions",
    "/core/health",
    "/core/version",
    "/.well-known/openid-configuration",
]


def probe_one(profile: str, path: str) -> dict[str, Any]:
    started = dt.datetime.now(tz=dt.timezone.utc)
    try:
        session = tls_client.Session(client_identifier=profile, random_tls_extension_order=True)
        resp = session.get(
            TARGET + path,
            headers={"User-Agent": "Mozilla/5.0 (compatible; tc-ja3-probe/0.1)"},
        )
        body_bytes = (
            resp.content
            if isinstance(resp.content, (bytes, bytearray))
            else (resp.text or "").encode()
        )
        return {
            "profile": profile,
            "path": path,
            "status": resp.status_code,
            "body_size": len(body_bytes),
            "headers": dict(resp.headers) if hasattr(resp, "headers") else {},
            "body_head": body_bytes[:300].decode("utf-8", errors="replace"),
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }
    except Exception as e:
        return {
            "profile": profile,
            "path": path,
            "error": f"{type(e).__name__}: {str(e)[:120]}",
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }


def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== JA3/JA4 fingerprint probe: {len(PROFILES)} profiles × {len(PATHS)} paths ===\n")

    results = []
    for profile in PROFILES:
        for path in PATHS:
            r = probe_one(profile, path)
            results.append(r)
            if "error" in r:
                tag = f"ERR  {r['error'][:60]}"
            else:
                tag = f"{r['status']:3} {r['body_size']:6}B"
            print(f"  {profile:25} {path:40} {tag}")

    out_path = out_dir / "results.json"
    out_path.write_text(
        json.dumps(
            {
                "schema": "tc-ai-ja3-probe/v1",
                "timestamp_utc": ts,
                "target": TARGET,
                "profiles": PROFILES,
                "paths": PATHS,
                "results": results,
            },
            indent=2,
        )
    )

    # ---------- Anomaly extraction ----------
    print(f"\nWrote {out_path}\n")
    print("=== Status / size distribution per profile ===")
    by_profile: dict[str, dict[tuple[Any, Any], int]] = {}
    for r in results:
        if "error" in r:
            key: tuple[Any, Any] = ("error", 0)
        else:
            key = (r["status"], r["body_size"])
        by_profile.setdefault(r["profile"], {})
        by_profile[r["profile"]][key] = by_profile[r["profile"]].get(key, 0) + 1
    for profile, dist in by_profile.items():
        print(f"  {profile:25}  {dict(sorted(dist.items()))}")

    # Compare against the httpx baseline (403/146)
    baseline = (403, 146)
    breakthrough = [
        r for r in results if "error" not in r and (r["status"], r["body_size"]) != baseline
    ]
    print("\n=== Responses different from httpx baseline (403/146B) ===")
    if not breakthrough:
        print("  (none — fingerprint bypass did not move the needle)")
    else:
        for r in breakthrough:
            head_oneline = (r["body_head"].splitlines() or [""])[0][:120]
            print(
                f"  [{r['status']:3}] {r['profile']:25} {r['path']:40} {r['body_size']:6}B  {head_oneline}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
