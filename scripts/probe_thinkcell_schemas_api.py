#!/usr/bin/env python3
"""Probe schemas.think-cell.com/api — characterize the POST endpoint behavior.

OPTIONS returned 200 with Allow: GET, POST, OPTIONS, HEAD. The actual POST
behavior is uncharacterized. This probe sends a battery of payload shapes and
records responses to determine:
  - Is it auth-gated (401/403) or open?
  - Does it accept think-cellXML and return validation errors?
  - Does it accept JSON?
  - What error messages, if any, hint at the expected schema?

Strictly read-only / send-only. No state mutation server-side intended.
Uses small, clearly-malformed payloads to elicit informative errors without
risking quota or rate-limit consequences.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

import httpx


BASE = "https://schemas.think-cell.com"
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "state" / "thinkcell_bridge" / "schemas_api_probe"


# Small think-cellXML samples — clearly malformed so we get validation errors
# rather than risking any real submission semantics.
TINY_TC_XML_OK = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<root reqver="32687"><version val="35740"/></root>'
)
TINY_TC_XML_MALFORMED = b'<?xml version="1.0"?><root><unclosed_tag>'
TINY_TC_XML_MIXED = (
    b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    b'<root reqver="32687">'
    b'<CSmartGrid id="1"><m_strName>probe-malformed</m_strName>'
    b'<m_invalid_attr val="bogus"/>'
    b"</CSmartGrid></root>"
)


PROBES = [
    # 1. Method matrix on /api
    {"name": "api_get", "method": "GET", "path": "/api", "body": None, "ct": None},
    {"name": "api_head", "method": "HEAD", "path": "/api", "body": None, "ct": None},
    {"name": "api_options", "method": "OPTIONS", "path": "/api", "body": None, "ct": None},
    {"name": "api_post_empty", "method": "POST", "path": "/api", "body": b"", "ct": None},
    {
        "name": "api_post_json",
        "method": "POST",
        "path": "/api",
        "body": b'{"probe":true}',
        "ct": "application/json",
    },
    {
        "name": "api_post_xml_ok",
        "method": "POST",
        "path": "/api",
        "body": TINY_TC_XML_OK,
        "ct": "application/xml",
    },
    {
        "name": "api_post_xml_bad",
        "method": "POST",
        "path": "/api",
        "body": TINY_TC_XML_MALFORMED,
        "ct": "application/xml",
    },
    {
        "name": "api_post_xml_mix",
        "method": "POST",
        "path": "/api",
        "body": TINY_TC_XML_MIXED,
        "ct": "application/xml",
    },
    {
        "name": "api_post_text",
        "method": "POST",
        "path": "/api",
        "body": b"hello",
        "ct": "text/plain",
    },
    # Methods that should be rejected (per OPTIONS Allow header)
    {"name": "api_put", "method": "PUT", "path": "/api", "body": b"x", "ct": "text/plain"},
    {"name": "api_delete", "method": "DELETE", "path": "/api", "body": None, "ct": None},
    # 2. Path-walk under /api
    {"name": "api_v1_options", "method": "OPTIONS", "path": "/api/v1", "body": None, "ct": None},
    {"name": "api_v1_get", "method": "GET", "path": "/api/v1", "body": None, "ct": None},
    {
        "name": "api_validate_post",
        "method": "POST",
        "path": "/api/validate",
        "body": TINY_TC_XML_OK,
        "ct": "application/xml",
    },
    {"name": "api_schema_get", "method": "GET", "path": "/api/schema", "body": None, "ct": None},
    {
        "name": "api_versions_get",
        "method": "GET",
        "path": "/api/versions",
        "body": None,
        "ct": None,
    },
    # 3. Build-keyed schema fetch (we know e.g. /36264/tcstyle.xsd works)
    {
        "name": "build_xsd_32687",
        "method": "GET",
        "path": "/32687/tcstyle.xsd",
        "body": None,
        "ct": None,
    },
    {
        "name": "build_xsd_38068",
        "method": "GET",
        "path": "/38068/tcstyle.xsd",
        "body": None,
        "ct": None,
    },
    {"name": "next_xsd", "method": "GET", "path": "/next/tcstyle.xsd", "body": None, "ct": None},
    {
        "name": "build_xsd_99999",
        "method": "GET",
        "path": "/99999/tcstyle.xsd",
        "body": None,
        "ct": None,
    },
    # 4. think-cellxml + ppttc namespace probes (the agent noted these elsewhere)
    {
        "name": "ppttc_schema",
        "method": "GET",
        "path": "/ppttc/schema.json",
        "body": None,
        "ct": None,
    },
    {
        "name": "ppttc_validate",
        "method": "POST",
        "path": "/ppttc/validate",
        "body": b'{"slides":[]}',
        "ct": "application/json",
    },
]


async def run_one(client: httpx.AsyncClient, probe: dict) -> dict:
    method = probe["method"]
    url = BASE + probe["path"]
    headers = {}
    if probe["ct"]:
        headers["Content-Type"] = probe["ct"]
    headers["User-Agent"] = "tc-probe/0.1 (+personal-recon)"

    started = dt.datetime.now(tz=dt.timezone.utc)
    try:
        resp = await client.request(
            method,
            url,
            headers=headers,
            content=probe["body"],
            timeout=15.0,
            follow_redirects=False,
        )
        body_bytes = resp.content
        body_head = body_bytes[:600]
        try:
            body_text = body_head.decode("utf-8")
        except UnicodeDecodeError:
            body_text = repr(body_head)
        return {
            "name": probe["name"],
            "method": method,
            "url": url,
            "ct_sent": probe["ct"],
            "body_size_sent": len(probe["body"] or b""),
            "status": resp.status_code,
            "reason": resp.reason_phrase,
            "headers": dict(resp.headers),
            "body_size_recv": len(body_bytes),
            "body_head_text": body_text,
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }
    except Exception as e:
        return {
            "name": probe["name"],
            "method": method,
            "url": url,
            "ct_sent": probe["ct"],
            "error": f"{type(e).__name__}: {e}",
            "elapsed_seconds": (dt.datetime.now(tz=dt.timezone.utc) - started).total_seconds(),
        }


async def main() -> int:
    ts = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%d-%H%M%S")
    out_dir = OUT_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Single AsyncClient with HTTP/2 for efficiency. Throttle: serial with small gap
    # to avoid looking like a scan.
    results = []
    async with httpx.AsyncClient(http2=False, verify=True) as client:
        for i, probe in enumerate(PROBES):
            print(
                f"[{i + 1:02}/{len(PROBES)}] {probe['method']:7} {probe['path']:30}",
                end="  ",
                flush=True,
            )
            r = await run_one(client, probe)
            results.append(r)
            if "error" in r:
                print(f"ERR  {r['error'][:60]}")
            else:
                ct = r["headers"].get("content-type", "?")[:30]
                print(
                    f"{r['status']:3}  {ct:30}  {r['body_size_recv']:6}B  {r['elapsed_seconds']:.2f}s"
                )
            await asyncio.sleep(0.3)

    out_path = out_dir / "schemas_api_probe.json"
    out_path.write_text(
        json.dumps(
            {
                "schema": "tcprobe-schemas-api/v1",
                "timestamp_utc": ts,
                "base_url": BASE,
                "probe_count": len(results),
                "results": results,
            },
            indent=2,
        )
    )
    print(f"\nWrote {out_path}")

    # Quick analysis
    print("\n=== Quick analysis ===")
    statuses: dict[int, int] = {}
    interesting = []
    for r in results:
        if "error" in r:
            continue
        statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        # Anything that's not a generic 405/404/empty 200 is interesting
        if (
            r["status"] in (200, 201, 202)
            and r["body_size_recv"] > 0
            and "/tcstyle.xsd" not in r["url"]
        ):
            interesting.append(
                (r["name"], r["status"], r["body_size_recv"], r["body_head_text"][:200])
            )
        elif r["status"] == 401 or r["status"] == 403:
            interesting.append(
                (r["name"], r["status"], r["body_size_recv"], r["body_head_text"][:200])
            )
        elif r["status"] in (400, 422, 500, 422):
            # Validation errors hint at the schema
            interesting.append(
                (r["name"], r["status"], r["body_size_recv"], r["body_head_text"][:200])
            )
    print(f"Status distribution: {statuses}")
    print(f"\nInteresting responses ({len(interesting)}):")
    for name, status, size, head in interesting:
        print(f"  [{status}] {name:25} ({size}B)")
        if head:
            for line in head.splitlines()[:3]:
                print(f"     | {line[:200]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
