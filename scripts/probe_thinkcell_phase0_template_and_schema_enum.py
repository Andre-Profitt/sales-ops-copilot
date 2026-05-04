#!/usr/bin/env python3
"""Phase 0c — enumerate public think-cell template + schema URLs.

Mac-side, pure HTTP HEAD. Tests:
- static.think-cell.com/ppttc/template[1-50].pptx + sample[1-50].pptx
- schemas.think-cell.com/<build>/tcstyle.xsd for known build numbers
- schemas.think-cell.com/next/tcstyle (and .xsd variant)
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import sys
import time
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest


ROOT = Path(__file__).resolve().parent.parent

# Build numbers seen in settings.xml + binary version + endver attr + log
KNOWN_BUILDS = ["32687", "36264", "38409", "1000220", "100220", "next"]


def _head(url: str, timeout: int = 8) -> dict:
    out = {
        "url": url,
        "status": None,
        "size": None,
        "content_type": None,
        "etag": None,
        "error": None,
    }
    req = urlrequest.Request(url, method="HEAD")
    req.add_header("User-Agent", "tcw-phase0-template-probe/1.0")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as r:
            out["status"] = r.status
            out["size"] = r.headers.get("Content-Length")
            out["content_type"] = r.headers.get("Content-Type")
            out["etag"] = r.headers.get("ETag")
    except urlerror.HTTPError as e:
        out["status"] = e.code
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _get_first_bytes(url: str, max_bytes: int = 2000) -> dict:
    out = {"url": url, "status": None, "preview": None, "error": None}
    req = urlrequest.Request(url, method="GET")
    req.add_header("User-Agent", "tcw-phase0-template-probe/1.0")
    req.add_header("Range", f"bytes=0-{max_bytes}")
    try:
        with urlrequest.urlopen(req, timeout=10) as r:
            out["status"] = r.status
            data = r.read(max_bytes)
            try:
                out["preview"] = data.decode("utf-8", errors="replace")[:1500]
            except Exception:
                out["preview"] = data[:200].hex()
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _enumerate_templates() -> list[dict]:
    base = "https://static.think-cell.com/ppttc"
    candidates = []
    for n in range(1, 51):
        candidates.append(f"{base}/template{n}.pptx")
        candidates.append(f"{base}/sample{n}.pptx")
    candidates.append(f"{base}/")
    candidates.append(f"{base}/index.html")
    candidates.append(f"{base}/manifest.json")
    candidates.append(f"{base}/templates.json")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(_head, candidates):
            results.append(r)
    return results


def _enumerate_schemas() -> list[dict]:
    base = "https://schemas.think-cell.com"
    candidates = []
    for build in KNOWN_BUILDS:
        candidates.append(f"{base}/{build}/tcstyle.xsd")
        candidates.append(f"{base}/{build}/tcstyle")
        candidates.append(f"{base}/{build}/")
    candidates.append(f"{base}/")
    candidates.append(f"{base}/index.html")
    candidates.append(f"{base}/manifest.json")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        for r in ex.map(_head, candidates):
            results.append(r)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output = args.output
    if output is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output = (
            ROOT
            / "state"
            / "thinkcell_bridge"
            / "phase0_template_schema"
            / stamp
            / "phase0_template_schema_probe.json"
        )
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print("[phase0c] enumerating templates", flush=True)
    templates = _enumerate_templates()
    template_hits = [t for t in templates if t["status"] == 200]

    print("[phase0c] enumerating schemas", flush=True)
    schemas = _enumerate_schemas()
    schema_hits = [s for s in schemas if s["status"] == 200]

    print("[phase0c] fetching schema previews for hits", flush=True)
    schema_bodies = []
    for s in schema_hits:
        if s["url"].endswith(".xsd") or s["url"].endswith("/tcstyle"):
            schema_bodies.append(_get_first_bytes(s["url"]))

    payload = {
        "schema": "simcorp-thinkcell-phase0-template-schema/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "templates": {
            "candidates_tested": len(templates),
            "hits": template_hits,
            "all_results": templates,
        },
        "schemas": {
            "candidates_tested": len(schemas),
            "hits": schema_hits,
            "previews": schema_bodies,
            "all_results": schemas,
        },
    }
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[phase0c] wrote {output}")
    print(f"[phase0c] template hits: {len(template_hits)}")
    for t in template_hits:
        print(f"  - {t['url']} ({t.get('size', '?')} bytes)")
    print(f"[phase0c] schema hits: {len(schema_hits)}")
    for s in schema_hits:
        print(f"  - {s['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
