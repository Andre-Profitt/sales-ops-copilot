#!/usr/bin/env python3
"""Probe API candidates that could become factory tools.

Targets:
1. tcserver.exe route enumeration — pull binary from VM, string-scan for routes
2. schemas.think-cell.com/api — POST a sample think-cellXML, see what it returns
3. static.think-cell.com/ppttc/template[2-5].pptx — download all 4, extract
   think-cellXML from each, inventory chart families per template

Output: state/thinkcell_bridge/factory_api_candidates/<ts>/factory_api_candidates.json
        + downloaded artifacts in subdirs
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import urllib.error as urlerror
import urllib.request as urlrequest
import zipfile
from pathlib import Path

try:
    import olefile  # type: ignore
except ImportError:
    print("Install: pip install olefile", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent


# Regex patterns reused across both ASCII and UTF-16LE decodings.
_ROUTE_RE = re.compile(
    r"(?<![A-Za-z0-9_])(/(?:api|v\d+|admin|auth|debug|metrics|health|status|ready|live|render|generate|update|files?|jobs?|portal|schemas?|spec|openapi|swagger|graphql|user|ws|info|version|tenant|partner|license|tcserver|ppttc|validate|preflight|preview|signed|upload|download|list|search|web|admin)[a-zA-Z0-9_/-]{1,80})"
)
_URL_RE = re.compile(r"https?://[A-Za-z0-9._/?=#&%+:-]{6,200}", re.IGNORECASE)
_METHOD_ROUTE_RE = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+(/[A-Za-z0-9_/-]{1,80})", re.IGNORECASE
)

# Verification needles — anchors that the UTF-16LE-only fix MUST surface.
# (Per probe_thinkcell_vm_native_auth_verify.ps1 lines 180-215.)
_VERIFICATION_NEEDLES: tuple[str, ...] = (
    "PpAICoreURL",
    "PpAICoreToken",
    "app.prod.ai.think-cell.com/core/",
    "oauth.canto.com",
    "api.gettyimages.com",
    "BCryptCreateHash",
    "BCryptHashData",
    "BCRYPT_SHA256_ALGORITHM",
    "BCRYPT_ALG_HANDLE_HMAC_FLAG",
    r"S:\tcaddin\PpAddIn",
    '"messages":',
)


def _scan_with_encoding(text: str, encoding: str) -> dict:
    """Apply every regex pattern to `text` and tag each finding with `encoding`."""
    routes = sorted(set(_ROUTE_RE.findall(text)))
    urls = sorted(set(_URL_RE.findall(text)))
    method_routes = sorted(set(_METHOD_ROUTE_RE.findall(text)))
    return {
        "encoding": encoding,
        "routes": routes,
        "urls": urls,
        "method_routes": [{"method": m.upper(), "path": p} for m, p in method_routes],
    }


def _strings_scan_tcserver(out_dir: Path) -> dict:
    """Pull tcserver.exe + ppttc.exe + tcasr.exe; string-scan for routes/URLs.

    Decodes each binary as BOTH ASCII and UTF-16LE, applies every regex against
    each decoding independently, and tags every finding with its source encoding.
    URL/route constants in tcaddin.dll (and adjacent think-cell binaries) are
    UTF-16LE-encoded; an ASCII-only scan misses them entirely.
    """
    out: dict = {
        "binaries": [],
        "all_routes": [],
        "all_urls": [],
        "post_routes": [],
        "tcserver_routes": [],
        "verification_summary": {},
    }
    binaries = [
        ("tcserver.exe", r"C:\Program Files (x86)\think-cell\tcserver.exe"),
        ("ppttc.exe", r"C:\Program Files (x86)\think-cell\ppttc.exe"),
        ("tcasr.exe", r"C:\Program Files (x86)\think-cell\tcasr.exe"),
        ("tcaddin.dll", r"C:\Program Files (x86)\think-cell\tcaddin.dll"),
    ]
    for name, remote_path in binaries:
        local = out_dir / name
        try:
            r = subprocess.run(
                ["scp", f"Windows-VM:{remote_path}", str(local)],
                text=True,
                capture_output=True,
                timeout=60,
                check=False,
            )
            if r.returncode != 0:
                out["binaries"].append({"name": name, "error": f"scp failed: {r.stderr[:200]}"})
                continue
            data = local.read_bytes()
            ascii_text = data.decode("ascii", errors="ignore")
            utf16_text = data.decode("utf-16-le", errors="ignore")

            # Run each regex independently against each decoding, tagging the source.
            ascii_scan = _scan_with_encoding(ascii_text, "ascii")
            utf16_scan = _scan_with_encoding(utf16_text, "utf-16-le")

            # Tagged findings: union with provenance preserved.
            tagged_routes: list[dict] = [
                {"value": v, "encoding": "ascii"} for v in ascii_scan["routes"]
            ] + [{"value": v, "encoding": "utf-16-le"} for v in utf16_scan["routes"]]
            tagged_urls: list[dict] = [
                {"value": v, "encoding": "ascii"} for v in ascii_scan["urls"]
            ] + [{"value": v, "encoding": "utf-16-le"} for v in utf16_scan["urls"]]
            tagged_method_routes: list[dict] = [
                {**mr, "encoding": "ascii"} for mr in ascii_scan["method_routes"]
            ] + [{**mr, "encoding": "utf-16-le"} for mr in utf16_scan["method_routes"]]

            # Flat dedup view (encoding-agnostic) — preserved for legacy callers.
            routes_flat = sorted({r["value"] for r in tagged_routes})
            urls_flat = sorted({u["value"] for u in tagged_urls})
            tc_urls_tagged = [u for u in tagged_urls if "think-cell" in u["value"]]
            tc_urls_flat = sorted({u["value"] for u in tc_urls_tagged})

            # Verification needle grep (mirrors auth_verify.ps1 utf16_strings_grep).
            verification_grep = {}
            for needle in _VERIFICATION_NEEDLES:
                verification_grep[needle] = {
                    "in_ascii": needle in ascii_text,
                    "in_utf16_le": needle in utf16_text,
                }

            entry = {
                "name": name,
                "size": len(data),
                "route_count": len(routes_flat),
                "routes": routes_flat[:200],
                "routes_tagged": tagged_routes[:400],
                "tc_url_count": len(tc_urls_flat),
                "tc_urls": tc_urls_flat,
                "tc_urls_tagged": tc_urls_tagged,
                "method_routes": [f"{mr['method']} {mr['path']}" for mr in tagged_method_routes][
                    :80
                ],
                "method_routes_tagged": tagged_method_routes[:160],
                "encoding_breakdown": {
                    "ascii": {
                        "route_count": len(ascii_scan["routes"]),
                        "url_count": len(ascii_scan["urls"]),
                        "method_route_count": len(ascii_scan["method_routes"]),
                    },
                    "utf-16-le": {
                        "route_count": len(utf16_scan["routes"]),
                        "url_count": len(utf16_scan["urls"]),
                        "method_route_count": len(utf16_scan["method_routes"]),
                    },
                },
                "verification_grep": verification_grep,
            }
            out["binaries"].append(entry)
            out["all_routes"].extend(routes_flat)
            out["all_urls"].extend(tc_urls_flat)
            if name == "tcserver.exe":
                out["tcserver_routes"] = routes_flat
                out["post_routes"] = [
                    f"{mr['method']} {mr['path']}"
                    for mr in tagged_method_routes
                    if mr["method"].upper() == "POST"
                ]
        except Exception as e:
            out["binaries"].append({"name": name, "error": f"{type(e).__name__}: {e}"})
    out["all_routes"] = sorted(set(out["all_routes"]))[:300]
    out["all_urls"] = sorted(set(out["all_urls"]))[:200]

    # Rolled-up verification summary across all binaries (which encoding hit which needle).
    summary: dict = {needle: {"ascii": [], "utf-16-le": []} for needle in _VERIFICATION_NEEDLES}
    for b in out["binaries"]:
        if "verification_grep" not in b:
            continue
        for needle, hits in b["verification_grep"].items():
            if hits.get("in_ascii"):
                summary[needle]["ascii"].append(b["name"])
            if hits.get("in_utf16_le"):
                summary[needle]["utf-16-le"].append(b["name"])
    out["verification_summary"] = summary
    return out


def _decode_response_body(raw: bytes) -> dict:
    """Decode an HTTP response body as both UTF-8 and UTF-16LE; tag each finding's encoding.

    Some think-cell endpoints return UTF-16LE-encoded XML — a UTF-8-only decode
    silently mangles the payload. Capture both decodings + the raw byte preview
    so the durable JSON artifact preserves enough provenance for later replay.
    """
    decodings: dict = {
        "raw_byte_preview_hex": raw[:64].hex(),
        "size": len(raw),
    }
    try:
        decodings["utf-8"] = raw.decode("utf-8", errors="replace")
    except Exception as e:
        decodings["utf-8_error"] = f"{type(e).__name__}: {e}"
    try:
        decodings["utf-16-le"] = raw.decode("utf-16-le", errors="replace")
    except Exception as e:
        decodings["utf-16-le_error"] = f"{type(e).__name__}: {e}"
    try:
        decodings["ascii"] = raw.decode("ascii", errors="ignore")
    except Exception as e:
        decodings["ascii_error"] = f"{type(e).__name__}: {e}"

    # Run regexes against each decoding, tagged with encoding.
    findings: list[dict] = []
    for enc_key in ("utf-8", "utf-16-le", "ascii"):
        text = decodings.get(enc_key)
        if not isinstance(text, str):
            continue
        urls = sorted(set(_URL_RE.findall(text)))
        routes = sorted(set(_ROUTE_RE.findall(text)))
        for u in urls:
            findings.append({"value": u, "kind": "url", "encoding": enc_key})
        for r in routes:
            findings.append({"value": r, "kind": "route", "encoding": enc_key})
    decodings["regex_findings_tagged"] = findings
    return decodings


def _probe_schemas_api_post(sample_xml: str) -> list[dict]:
    """Try various POST shapes against schemas.think-cell.com/api endpoints.

    Persists encoding-tagged decoded response bodies to the durable JSON
    artifact (UTF-8, UTF-16LE, ASCII) so future verification doesn't have to
    rerun ad-hoc `python -c '...'` probes off-script.
    """
    out = []
    targets = [
        ("https://schemas.think-cell.com/api", "application/xml"),
        ("https://schemas.think-cell.com/api", "text/xml"),
        ("https://schemas.think-cell.com/api", "application/json"),
        ("https://schemas.think-cell.com/api/validate", "application/xml"),
        ("https://schemas.think-cell.com/api/v1/validate", "application/xml"),
        ("https://schemas.think-cell.com/validate", "application/xml"),
        ("https://schemas.think-cell.com/api?action=validate", "application/xml"),
        ("https://schemas.think-cell.com/36264/api", "application/xml"),
        ("https://schemas.think-cell.com/next/api", "application/xml"),
    ]
    for url, ctype in targets:
        body_str = (
            sample_xml
            if ctype != "application/json"
            else json.dumps({"xml": sample_xml, "build": "36264"})
        )
        body_bytes = body_str.encode("utf-8")
        req = urlrequest.Request(url, method="POST", data=body_bytes)
        req.add_header("Content-Type", ctype)
        req.add_header("User-Agent", "tcw-factory-probe/1.0")
        rec: dict = {
            "url": url,
            "content_type": ctype,
            "status": None,
            "response_headers": {},
            "body_preview": None,
            "body_decodings": None,
            "error": None,
        }
        try:
            with urlrequest.urlopen(req, timeout=10) as r:
                rec["status"] = r.status
                rec["response_headers"] = dict(r.headers)
                raw = r.read(8192)
                rec["body_preview"] = raw[:2000].decode("utf-8", errors="replace")
                rec["body_decodings"] = _decode_response_body(raw)
        except urlerror.HTTPError as e:
            rec["status"] = e.code
            rec["response_headers"] = dict(e.headers) if e.headers else {}
            try:
                raw = e.read(8192)
                rec["body_preview"] = raw[:2000].decode("utf-8", errors="replace")
                rec["body_decodings"] = _decode_response_body(raw)
            except Exception:
                pass
        except Exception as e:
            rec["error"] = f"{type(e).__name__}: {e}"
        out.append(rec)
    return out


def _download_template(base_url: str, out_dir: Path) -> list[dict]:
    """Download static.think-cell.com/ppttc/template[N].pptx + extract think-cellXML."""
    results = []
    for n in range(1, 11):
        url = f"{base_url}/ppttc/template{n}.pptx"
        local = out_dir / f"template{n}.pptx"
        try:
            req = urlrequest.Request(url)
            req.add_header("User-Agent", "tcw-factory-probe/1.0")
            with urlrequest.urlopen(req, timeout=20) as r:
                if r.status != 200:
                    continue
                data = r.read()
            local.write_bytes(data)
            entry = {
                "template": f"template{n}.pptx",
                "url": url,
                "size": len(data),
                "ole_objects": [],
                "thinkcell_xml_count": 0,
                "tc_alternate_content_count": 0,
                "first_chart_classes": [],
            }
            with zipfile.ZipFile(local) as z:
                # Inventory OLE blobs and extract think-cellXML
                embeddings = sorted(
                    [
                        p
                        for p in z.namelist()
                        if p.startswith("ppt/embeddings/oleObject") and p.endswith(".bin")
                    ]
                )
                for emb in embeddings:
                    blob = z.read(emb)
                    try:
                        ole = olefile.OleFileIO(io.BytesIO(blob))
                        streams = ["/".join(s) for s in ole.listdir(streams=True)]
                        ole_record = {
                            "path": emb,
                            "size": len(blob),
                            "streams": streams,
                            "has_thinkcellxml": "think-cellXML" in streams,
                            "thinkcell_xml_size": 0,
                            "chart_classes": [],
                        }
                        if ole_record["has_thinkcellxml"]:
                            with ole.openstream("think-cellXML") as s:
                                xml = s.read().decode("utf-8", errors="replace")
                            ole_record["thinkcell_xml_size"] = len(xml)
                            entry["thinkcell_xml_count"] += 1
                            # Extract C++ chart classes
                            classes = sorted(set(re.findall(r"<(C[A-Z][a-zA-Z0-9]+)\b", xml)))
                            ole_record["chart_classes"] = classes[:30]
                            if not entry["first_chart_classes"]:
                                entry["first_chart_classes"] = classes[:20]
                            # Save the XML
                            xml_path = out_dir / f"template{n}_{emb.replace('/', '_')}.xml"
                            xml_path.write_text(xml, encoding="utf-8")
                            ole_record["xml_dump"] = str(xml_path)
                        ole.close()
                        entry["ole_objects"].append(ole_record)
                    except Exception as e:
                        entry["ole_objects"].append(
                            {"path": emb, "error": f"{type(e).__name__}: {e}"}
                        )
                # Count <mc:AlternateContent> blocks with think-cell content
                for slide in [
                    p
                    for p in z.namelist()
                    if p.startswith("ppt/slides/slide") and p.endswith(".xml")
                ]:
                    content = z.read(slide).decode("utf-8", errors="replace")
                    if "TCLayout" in content or "think-cell" in content:
                        entry["tc_alternate_content_count"] += content.count("TCLayout")
            results.append(entry)
        except urlerror.HTTPError as e:
            if e.code != 404:
                results.append(
                    {"template": f"template{n}.pptx", "url": url, "error": f"HTTP {e.code}"}
                )
            # 404 = end of enumeration
        except Exception as e:
            results.append(
                {"template": f"template{n}.pptx", "url": url, "error": f"{type(e).__name__}: {e}"}
            )
    return results


# Sample think-cellXML for the schema validation probe — use the smallest one we have
def _load_sample_xml() -> str:
    sample_dir = ROOT / "state" / "thinkcell_bridge" / "embedding_inspection"
    if sample_dir.exists():
        for d in sorted(sample_dir.iterdir(), reverse=True):
            xml_path = d / "cfb_think-cellXML.bin"
            if xml_path.exists() and xml_path.stat().st_size > 100:
                return xml_path.read_text(encoding="utf-8", errors="replace")[:50000]
    # Minimal fallback
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<root reqver="36264">'
        '<version val="36264"/>'
        '<CSmartGrid id="1"><m_olanguage>en-US</m_olanguage></CSmartGrid>'
        "</root>"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output or (
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "factory_api_candidates"
        / time.strftime("%Y%m%d-%H%M%S")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    payload: dict = {
        "schema": "simcorp-thinkcell-factory-api-candidates/v1",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Probe 1: tcserver.exe + ppttc.exe + tcasr.exe route extraction
    print("[probe1] pulling + string-scanning think-cell binaries")
    bin_dir = output_dir / "binaries"
    bin_dir.mkdir(parents=True, exist_ok=True)
    payload["binary_route_scan"] = _strings_scan_tcserver(bin_dir)

    # Probe 2: schemas.think-cell.com/api POST with sample think-cellXML
    print("[probe2] POSTing think-cellXML to schemas.think-cell.com/api variants")
    sample_xml = _load_sample_xml()
    payload["sample_xml_size"] = len(sample_xml)
    payload["schemas_api_post"] = _probe_schemas_api_post(sample_xml)

    # Probe 4: Download static.think-cell.com/ppttc/template[1-10].pptx
    print("[probe4] downloading + extracting public PPTTC templates")
    template_dir = output_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    payload["public_templates"] = _download_template("https://static.think-cell.com", template_dir)

    out_path = output_dir / "factory_api_candidates.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    # Summary
    print(f"\n[summary] wrote {out_path}")
    print("\n=== PROBE 1: tcserver.exe routes ===")
    for b in payload["binary_route_scan"]["binaries"]:
        if "error" in b:
            print(f"  {b['name']}: {b['error']}")
        else:
            print(
                f"  {b['name']} ({b['size']} bytes): {b['route_count']} routes, {b['tc_url_count']} tc URLs"
            )
    print("\n  tcserver routes (first 20):")
    for r in payload["binary_route_scan"]["tcserver_routes"][:20]:
        print(f"    {r}")
    print("\n  POST routes:")
    for pr in payload["binary_route_scan"]["post_routes"][:10]:
        print(f"    {pr}")
    print("\n=== PROBE 2: schemas.think-cell.com POST ===")
    for r in payload["schemas_api_post"]:
        if r.get("error"):
            print(f"  {r['url']} ({r['content_type']}): ERR {r['error']}")
        else:
            preview = (r.get("body_preview") or "")[:140].replace("\n", " ")
            print(f"  {r['status']} POST {r['url']} ({r['content_type']}): {preview}")
    print("\n=== PROBE 4: public PPTTC templates ===")
    for t in payload["public_templates"]:
        if t.get("error"):
            print(f"  {t['template']}: ERR {t['error']}")
        else:
            print(
                f"  {t['template']}: {t['size']} bytes, {t['thinkcell_xml_count']} think-cell charts, {t['tc_alternate_content_count']} TCLayout refs"
            )
            if t["first_chart_classes"]:
                print(f"    first classes: {t['first_chart_classes'][:15]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
