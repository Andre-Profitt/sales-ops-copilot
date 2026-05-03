#!/usr/bin/env python3
"""Phase 12 analyzer - extracts the four observables for the AI-only auth flow.

Inputs (under <capture>/):
  mitm.har               - HTTP archive, scoped to auth + AI subdomains only
  mitm.flow              - mitmproxy binary flow (optional)
  frida.log              - frida-trace text log
  aiauthentication.bin.captured - post-capture token snapshot (optional but useful)
  + dpapi_baseline pre-capture parsed JSON (optional, passed via --baseline)

Outputs (in <capture>/):
  findings.md            - human-readable summary
  observables.json       - machine-readable extraction
  replay_scaffold.py     - first-attempt programmatic replay (request body templated)

The four observables we MUST nail:

1. Authorization on app.prod.ai/core/    - exact header value, full headers
2. Auth-exchange flow at aiauthentication.appcom - method/path/req/resp
3. AI request body schema                - top-level JSON keys
4. HMAC moments from Frida               - what bytes BCryptHashData was called with,
                                           keyed against which Authorization header
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

HOST_AI_CORE = "app.prod.ai.think-cell.com"
HOST_AUTH_REFRESH = "aiauthentication.appcom.think-cell.com"
HOST_CDN_AUTH = "cdnauthentication.appcom.think-cell.com"


def _load_har(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        print(f"[phase12] mitm.har is invalid JSON: {e}", file=sys.stderr)
        return {}


def _entries(har: dict) -> list[dict]:
    return har.get("log", {}).get("entries", [])


def _host(url: str) -> str:
    m = re.match(r"https?://([^/]+)", url or "")
    return m.group(1) if m else ""


def _h(headers: list[dict], name: str) -> str | None:
    for hdr in headers or []:
        if hdr.get("name", "").lower() == name.lower():
            return hdr.get("value")
    return None


def _all_headers_dict(headers: list[dict]) -> dict:
    return {hdr.get("name", ""): hdr.get("value", "") for hdr in headers or []}


def _ai_core_calls(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        url = e.get("request", {}).get("url", "")
        if HOST_AI_CORE in url and "/core/" in url:
            out.append(e)
    return out


def _auth_refresh_calls(entries: list[dict]) -> list[dict]:
    out = []
    for e in entries:
        h = _host(e.get("request", {}).get("url", ""))
        if h in (HOST_AUTH_REFRESH, HOST_CDN_AUTH):
            out.append(e)
    return out


def _request_body_text(e: dict) -> str:
    return e.get("request", {}).get("postData", {}).get("text") or ""


def _response_body_text(e: dict) -> str:
    return e.get("response", {}).get("content", {}).get("text") or ""


def _try_json_keys(text: str) -> list[str] | None:
    if not text:
        return None
    s = text.strip()
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return list(obj.keys())
    return None


def _parse_frida(path: Path) -> list[dict]:
    if not path.exists():
        return []
    line_re = re.compile(r"^\s*(\d{1,2}:\d{2}:\d{2}\.\d{1,6})\s+(\S+!\S+)(.*)$")
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = line_re.match(line)
        if not m:
            continue
        ts, fn, tail = m.groups()
        module, func = fn.split("!", 1)
        rows.append({"ts": ts, "module": module, "func": func, "tail": tail.strip()})
    return rows


def _bcrypt_moments(frida: list[dict]) -> list[dict]:
    return [
        r
        for r in frida
        if r["func"] in ("BCryptCreateHash", "BCryptHashData", "BCryptFinishHash")
        or r["func"] == "CryptUnprotectData"
        or r["module"] == "tcaddin.dll"
    ]


def _winhttp_send_moments(frida: list[dict]) -> list[dict]:
    return [
        r
        for r in frida
        if r["func"] in ("WinHttpSendRequest", "WinHttpAddRequestHeaders", "WinHttpWriteData")
    ]


def _replay_scaffold(ai_call: dict | None, auth_call: dict | None) -> str:
    """Emit a first-pass requests.py script that templates the captured shapes.

    Critical caveats embedded as comments:
      - Authorization header is captured-time-bound; expires per DPAPI token
      - HMAC over body is signed with key derived from license; replay won't extend
      - This is a SHAPE template, not a functional client
    """
    if ai_call:
        ai_url = ai_call.get("request", {}).get("url", "<UNKNOWN>")
        ai_method = ai_call.get("request", {}).get("method", "POST")
        ai_headers = _all_headers_dict(ai_call.get("request", {}).get("headers", []))
        ai_body = _request_body_text(ai_call)[:1000]
    else:
        ai_url, ai_method, ai_headers, ai_body = "<NO_AI_CORE_CAPTURED>", "POST", {}, ""

    if auth_call:
        auth_url = auth_call.get("request", {}).get("url", "<UNKNOWN>")
        auth_method = auth_call.get("request", {}).get("method", "POST")
        auth_headers = _all_headers_dict(auth_call.get("request", {}).get("headers", []))
        auth_body = _request_body_text(auth_call)[:1000]
    else:
        auth_url, auth_method, auth_headers, auth_body = (
            "<NO_AUTH_REFRESH_CAPTURED>",
            "POST",
            {},
            "",
        )

    return f'''#!/usr/bin/env python3
"""Phase 12 replay scaffold (auto-generated from one capture).

CAVEATS:
- Authorization header below is captured-bound. Will expire per DPAPI token's
  `expires` field. Without replicating the auth-refresh signing (HMAC over what?
  with what key?) this is a one-shot.
- This is a SHAPE template for the AI-core request, not a functional client.
- License/EULA: personal use only. Don't run from SimCorp prod. Don't share.
"""
import requests

# ---- Auth refresh shape (captured) ----
AUTH_URL    = {auth_url!r}
AUTH_METHOD = {auth_method!r}
AUTH_HEADERS = {json.dumps(auth_headers, indent=4)}
AUTH_BODY = {auth_body!r}

# ---- AI core call shape (captured) ----
AI_URL    = {ai_url!r}
AI_METHOD = {ai_method!r}
AI_HEADERS = {json.dumps(ai_headers, indent=4)}
AI_BODY = {ai_body!r}


def replay_ai_call_once():
    """One-shot replay - works only while the captured Authorization is valid."""
    r = requests.request(AI_METHOD, AI_URL, headers=AI_HEADERS, data=AI_BODY, timeout=30)
    return r.status_code, r.headers, r.text[:2000]


def request_token_refresh():
    """Replay the auth-refresh shape - whether it actually re-issues a token
    depends on the body containing the right HMAC signature, which we don't
    yet know how to compute. This is for shape verification only."""
    r = requests.request(AUTH_METHOD, AUTH_URL, headers=AUTH_HEADERS, data=AUTH_BODY, timeout=30)
    return r.status_code, r.headers, r.text[:2000]


if __name__ == "__main__":
    print("== AI core replay (one-shot) ==")
    s, h, b = replay_ai_call_once()
    print(f"status={{s}}")
    print(f"headers={{dict(h)}}")
    print(f"body[:2000]={{b}}")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture", type=Path, required=True, help="Directory containing mitm.har, frida.log"
    )
    parser.add_argument(
        "--baseline", type=Path, default=None, help="Optional pre-capture DPAPI baseline JSON"
    )
    args = parser.parse_args()

    cap = args.capture.expanduser().resolve()
    if not cap.is_dir():
        raise SystemExit(f"capture dir not found: {cap}")

    print(f"[phase12] reading captures from {cap}")
    har = _load_har(cap / "mitm.har")
    entries = _entries(har)
    frida = _parse_frida(cap / "frida.log")

    ai_core = _ai_core_calls(entries)
    auth_refresh = _auth_refresh_calls(entries)
    bcrypt = _bcrypt_moments(frida)
    winhttp_send = _winhttp_send_moments(frida)

    # --- Observable 1: Authorization on app.prod.ai/core/
    auth_obs: list[dict] = []
    for e in ai_core:
        req_headers = _all_headers_dict(e.get("request", {}).get("headers", []))
        auth_obs.append(
            {
                "url": e.get("request", {}).get("url"),
                "method": e.get("request", {}).get("method"),
                "all_request_headers": req_headers,
                "authorization_header_value": req_headers.get("Authorization"),
                "credential_carrier_candidates": {
                    k: v
                    for k, v in req_headers.items()
                    if any(
                        t in k.lower()
                        for t in (
                            "auth",
                            "token",
                            "license",
                            "key",
                            "cookie",
                            "x-tc",
                            "x-thinkcell",
                        )
                    )
                },
            }
        )

    # --- Observable 2: Auth-exchange shape
    refresh_obs: list[dict] = []
    for e in auth_refresh:
        req = e.get("request", {})
        resp = e.get("response", {})
        refresh_obs.append(
            {
                "method": req.get("method"),
                "url": req.get("url"),
                "request_headers": _all_headers_dict(req.get("headers", [])),
                "request_body_text": _request_body_text(e),
                "request_body_json_keys": _try_json_keys(_request_body_text(e)),
                "response_status": resp.get("status"),
                "response_headers": _all_headers_dict(resp.get("headers", [])),
                "response_body_text": _response_body_text(e)[:4000],
                "response_body_json_keys": _try_json_keys(_response_body_text(e)),
                "response_set_cookie": _h(resp.get("headers", []), "Set-Cookie"),
            }
        )

    # --- Observable 3: AI body schema
    body_obs: list[dict] = []
    for e in ai_core:
        body = _request_body_text(e)
        body_obs.append(
            {
                "url": e.get("request", {}).get("url"),
                "request_body_size": len(body),
                "request_body_json_keys": _try_json_keys(body),
                "request_body_first_500": body[:500],
            }
        )

    # --- Observable 4: HMAC moments (timing-correlated)
    bcrypt_obs = {
        "total_events": len(bcrypt),
        "by_func": dict(Counter(r["func"] for r in bcrypt)),
        "by_module": dict(Counter(r["module"] for r in bcrypt)),
        "first_50_events": bcrypt[:50],
        "winhttp_send_count": len(winhttp_send),
    }

    # --- Optional: compare to DPAPI baseline
    baseline_diff = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        post_path = cap / "aiauthentication.bin.captured"
        if post_path.exists():
            baseline_diff = {
                "baseline_fields": baseline.get("field_names"),
                "baseline_expires": baseline.get("expires_summary"),
                "post_capture_blob_size": post_path.stat().st_size,
                "note": "Compare baseline_fields to post-refresh; same fields = simple replacement, "
                "different fields = new auth scheme post-refresh.",
            }

    observables = {
        "schema": "thinkcell-phase12-observables/v1",
        "capture_dir": str(cap),
        "analyzed_at_utc": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "ai_core_call_count": len(ai_core),
            "auth_refresh_call_count": len(auth_refresh),
            "frida_event_count": len(frida),
            "bcrypt_event_count": len(bcrypt),
            "winhttp_send_count": len(winhttp_send),
        },
        "observable_1_authorization": auth_obs,
        "observable_2_auth_exchange": refresh_obs,
        "observable_3_ai_body_schema": body_obs,
        "observable_4_bcrypt_moments": bcrypt_obs,
        "baseline_diff": baseline_diff,
    }

    out_json = cap / "observables.json"
    out_json.write_text(json.dumps(observables, indent=2, default=str), encoding="utf-8")
    print(f"[phase12] wrote {out_json}")

    # --- findings.md
    md = [
        "# Phase 12 - AI auth flow capture findings",
        "",
        f"Capture: `{cap}`",
        f"Analyzed: {observables['analyzed_at_utc']}",
        "",
    ]
    md.append("## Summary")
    s = observables["summary"]
    md += [
        f"- AI core calls: **{s['ai_core_call_count']}**",
        f"- Auth-refresh calls: **{s['auth_refresh_call_count']}**",
        f"- Frida events: **{s['frida_event_count']}** "
        f"(BCrypt: {s['bcrypt_event_count']}, WinHttpSend: {s['winhttp_send_count']})",
        "",
    ]

    md.append("## Observable 1 - Authorization on AI core")
    if not auth_obs:
        md.append(
            "- NONE captured. The trigger may not have hit `/core/`. Check the AI feature you used."
        )
    for i, a in enumerate(auth_obs, 1):
        md += [
            f"### AI core request {i}",
            f"- URL: `{a['url']}`",
            f"- Authorization header: `{a['authorization_header_value']}`",
            f"- Credential-carrier candidates: `{a['credential_carrier_candidates']}`",
            "",
        ]

    md.append("## Observable 2 - Auth exchange")
    if not refresh_obs:
        md.append(
            "- NONE captured (no aiauthentication.appcom traffic). Did the token-delete force a refresh?"
        )
    for i, r in enumerate(refresh_obs, 1):
        md += [
            f"### Refresh exchange {i}",
            f"- `{r['method']} {r['url']}` -> {r['response_status']}",
            f"- Request body keys: `{r['request_body_json_keys']}`",
            f"- Request body (first 400): `{(r['request_body_text'] or '')[:400]}`",
            f"- Response body keys: `{r['response_body_json_keys']}`",
            f"- Response body (first 1000): `{(r['response_body_text'] or '')[:1000]}`",
            "",
        ]

    md.append("## Observable 3 - AI request body schema")
    for i, b in enumerate(body_obs, 1):
        md += [
            f"### AI request {i}",
            f"- Body size: {b['request_body_size']}",
            f"- Top-level JSON keys: `{b['request_body_json_keys']}`",
            f"- First 500 chars: `{b['request_body_first_500']}`",
            "",
        ]

    md.append("## Observable 4 - BCrypt moments")
    md.append(f"- {bcrypt_obs['total_events']} events")
    md.append(f"- By func: `{bcrypt_obs['by_func']}`")
    md.append(f"- By module: `{bcrypt_obs['by_module']}`")
    md.append("")
    md.append(
        "Cross-reference: each `WinHttpSendRequest` to the AI core should be preceded "
        "by `BCryptCreateHash`+`BCryptHashData`+`BCryptFinishHash` calls. The bytes "
        "passed to `BCryptHashData` are the canonical-request material; the key passed "
        "to `BCryptCreateHash` is the signing key."
    )

    if baseline_diff:
        md.append("")
        md.append("## DPAPI baseline diff")
        md.append(f"- Baseline fields: `{baseline_diff['baseline_fields']}`")
        md.append(f"- Baseline expires: `{baseline_diff['baseline_expires']}`")
        md.append(f"- Post-capture blob size: {baseline_diff['post_capture_blob_size']}")

    (cap / "findings.md").write_text("\n".join(md), encoding="utf-8")
    print(f"[phase12] wrote {cap / 'findings.md'}")

    # Replay scaffold
    scaffold = _replay_scaffold(
        ai_core[0] if ai_core else None, auth_refresh[0] if auth_refresh else None
    )
    (cap / "replay_scaffold.py").write_text(scaffold, encoding="utf-8")
    print(f"[phase12] wrote {cap / 'replay_scaffold.py'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
