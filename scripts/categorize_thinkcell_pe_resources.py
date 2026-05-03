#!/usr/bin/env python3
"""Categorize the dumped tcaddin.dll PE resources by file-magic signature.

Reads the latest pe_resources probe output and walks the corresponding
dumps/<binary>/ directory. For each .bin file:
- Detects compression / file-format magic (zlib, gzip, zstd, PE, CFB, ZIP, PDF, PNG, JPEG, etc.)
- For zlib-compressed files: attempts decompression and re-classifies the inflated payload
- For likely cursor/icon files: records header info
- For unknown bytes: records first-32-byte hex + entropy

Output: state/thinkcell_bridge/pe_resources/<latest>/categorized_resources.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PE = ROOT / "state" / "thinkcell_bridge" / "pe_resources"


def _entropy(buf: bytes) -> float:
    if not buf:
        return 0.0
    counts = [0] * 256
    for b in buf:
        counts[b] += 1
    n = len(buf)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def _magic(buf: bytes) -> dict[str, object]:
    head = buf[:32] if buf else b""
    out: dict[str, object] = {"head_hex": head.hex()}
    if len(buf) >= 4:
        b0, b1, b2, b3 = buf[0], buf[1], buf[2], buf[3]
        if b0 == 0x78 and b1 in (0x9C, 0xDA, 0x5E, 0x01):
            out["format"] = "zlib"
        elif b0 == 0x1F and b1 == 0x8B:
            out["format"] = "gzip"
        elif buf.startswith(b"\x28\xb5\x2f\xfd"):
            out["format"] = "zstd"
        elif buf.startswith(b"MZ"):
            out["format"] = "PE/MZ"
        elif buf.startswith(b"PK\x03\x04"):
            out["format"] = "ZIP/OOXML"
        elif buf.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
            out["format"] = "CFB"
        elif buf.startswith(b"%PDF"):
            out["format"] = "PDF"
        elif buf.startswith(b"\x89PNG\r\n\x1a\n"):
            out["format"] = "PNG"
        elif buf.startswith(b"\xff\xd8\xff"):
            out["format"] = "JPEG"
        elif buf.startswith(b"GIF8"):
            out["format"] = "GIF"
        elif buf.startswith(b"OggS"):
            out["format"] = "Ogg"
        elif buf.startswith(b"<?xml") or buf.startswith(b"\xef\xbb\xbf<?xml"):
            out["format"] = "XML"
        elif buf[:1] == b"{" or buf[:1] == b"[":
            out["format"] = "JSON?"
        elif buf.startswith(b"\x00\x00\x01\x00"):
            out["format"] = "ICO"
        elif buf.startswith(b"\x00\x00\x02\x00"):
            out["format"] = "CUR"
        elif buf.startswith(b"BM"):
            out["format"] = "BMP"
        elif buf.startswith(b"\x4d\x53\x43\x46"):
            out["format"] = "MSCF/CAB"
        elif buf.startswith(b"\xff\xfe") or buf.startswith(b"\xfe\xff"):
            out["format"] = "UTF-16 BOM"
        else:
            # Heuristic: high-printable-ASCII = text
            text_chars = sum(1 for b in buf[:200] if 32 <= b < 127 or b in (9, 10, 13))
            sample = buf[:200]
            if sample and text_chars * 100 // max(1, len(sample)) > 80:
                out["format"] = "ASCII text"
            else:
                out["format"] = "unknown"
    out["entropy"] = round(_entropy(buf[: min(4096, len(buf))]), 3)
    return out


def _try_inflate(buf: bytes) -> tuple[bytes, str] | None:
    if not buf:
        return None
    try:
        decompressor = zlib.decompressobj()
        out = decompressor.decompress(buf)
        if out:
            return out, "raw_zlib"
    except zlib.error:
        pass
    try:
        out = zlib.decompress(buf, -15)
        if out:
            return out, "raw_deflate"
    except zlib.error:
        pass
    return None


def _classify_one(path: Path) -> dict:
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    info = {
        "path": str(path),
        "size": len(raw),
        "sha256": sha,
    }
    info.update(_magic(raw))

    # Try to peel zlib-wrapped payloads
    if info.get("format") in ("zlib", "gzip", "unknown"):
        inflated = _try_inflate(raw)
        if inflated:
            payload, mode = inflated
            info["inflated_size"] = len(payload)
            info["inflated_mode"] = mode
            info["inflated_magic"] = _magic(payload)
            preview = payload[:300]
            try:
                info["inflated_text_preview"] = preview.decode("utf-8", errors="replace")
            except Exception:
                pass
    return info


def _newest_pe_dir(state_root: Path) -> Path:
    runs = sorted([p for p in state_root.iterdir() if p.is_dir()], reverse=True)
    if not runs:
        raise SystemExit(f"no pe_resources runs under {state_root}")
    return runs[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pe-state-root",
        type=Path,
        default=DEFAULT_PE,
        help="Root containing timestamped pe_resources runs.",
    )
    parser.add_argument(
        "--run",
        type=Path,
        default=None,
        help="Specific run directory (defaults to newest under --pe-state-root).",
    )
    args = parser.parse_args()

    run_dir = (
        args.run.expanduser().resolve()
        if args.run
        else _newest_pe_dir(args.pe_state_root.expanduser().resolve())
    )
    dumps_root = run_dir / "dumps"
    if not dumps_root.exists():
        raise SystemExit(f"no dumps/ under {run_dir}")

    by_binary: dict[str, list[dict]] = {}
    for binary_dir in sorted(p for p in dumps_root.iterdir() if p.is_dir()):
        entries = []
        for f in sorted(binary_dir.iterdir()):
            if not f.is_file():
                continue
            try:
                entries.append(_classify_one(f))
            except Exception as exc:
                entries.append({"path": str(f), "error": str(exc)})
        by_binary[binary_dir.name] = entries

    out: dict = {
        "schema": "simcorp-thinkcell-pe-resource-categorization/v1",
        "run_dir": str(run_dir),
        "binaries": by_binary,
        "summary": {},
    }
    for bname, entries in by_binary.items():
        formats: dict[str, int] = {}
        inflated_formats: dict[str, int] = {}
        for e in entries:
            fmt = e.get("format", "unknown")
            formats[fmt] = formats.get(fmt, 0) + 1
            if "inflated_magic" in e:
                inflated_formats[e["inflated_magic"].get("format", "unknown")] = (
                    inflated_formats.get(e["inflated_magic"].get("format", "unknown"), 0) + 1
                )
        out["summary"][bname] = {
            "count": len(entries),
            "formats": formats,
            "inflated_formats": inflated_formats,
            "max_size": max((e.get("size", 0) for e in entries), default=0),
            "total_size": sum(e.get("size", 0) for e in entries),
        }

    out_path = run_dir / "categorized_resources.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print()
    print("=== Summary ===")
    for bname, s in out["summary"].items():
        print(f"\n{bname}: {s['count']} files, {s['total_size']} bytes total")
        for fmt, c in sorted(s["formats"].items(), key=lambda kv: -kv[1]):
            print(f"  {fmt:30s}  {c}")
        if s["inflated_formats"]:
            print("  (after deflate:)")
            for fmt, c in sorted(s["inflated_formats"].items(), key=lambda kv: -kv[1]):
                print(f"    {fmt:28s}  {c}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
