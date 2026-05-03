#!/usr/bin/env python3
"""Generate strongly-typed C# interop interfaces from the typeinfo probe JSON.

Produces a `.cs` file containing:
- `IPpMacroInterface` with [Guid("...")] [InterfaceType(...)]
- `IXlMacroInterface`
- `IUpdateBatch`

Each method uses the parameter names + counts captured by the typeinfo probe.
Parameter types are typed as `object` for safe-array params and best-guess
managed types otherwise (the typelib doesn't carry full TYPEDESC type info
in our probe output, so this is a starting point — runtime marshaling will
sort the rest via late-binding-on-typed-interface).

Output: `state/thinkcell_bridge/csharp_interop/<run>/Thinkcell.Interop.cs`
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TI_ROOT = ROOT / "state" / "thinkcell_bridge" / "typeinfo"


def _newest(p: Path) -> Path | None:
    candidates = [c for c in p.iterdir() if c.is_dir()] if p.exists() else []
    return sorted(candidates, reverse=True)[0] if candidates else None


def _safe_param_name(name: str | None, idx: int) -> str:
    if not name:
        return f"arg{idx}"
    safe = re.sub(r"\W", "_", name)
    if safe and safe[0].isdigit():
        safe = "_" + safe
    return safe


def _guess_type(param_name: str | None) -> str:
    if not param_name:
        return "object"
    n = param_name.lower()
    if n.startswith("bstr") or n in ("filename", "name", "chartname"):
        return "string"
    if n.startswith("psa") or "safearray" in n or "array" in n:
        return "object"
    if n in ("hwnd", "wflags"):
        return "int"
    if n in ("active",) or n.startswith("b") and len(n) <= 2:
        return "bool"
    if n in ("left", "top", "width", "height"):
        return "double"
    if n in ("transposed",):
        return "bool"
    return "object"


def _emit_interface(target: dict) -> str:
    iname = target.get("type_name") or target["label"]
    iid = target.get("type_guid") or "00000000-0000-0000-0000-000000000000"
    label = target.get("label", iname)
    funcs = target.get("funcs", []) or []
    out: list[str] = []
    out.append(
        f"    /// <summary>think-cell interface for {label} (probed {time.strftime('%Y-%m-%d')}).</summary>"
    )
    out.append("    [ComImport]")
    out.append(f'    [Guid("{iid}")]')
    out.append("    [InterfaceType(ComInterfaceType.InterfaceIsDual)]")
    out.append(f"    public interface {iname} {{")
    seen_methods = set()
    standard_idispatch = {
        "QueryInterface",
        "AddRef",
        "Release",
        "GetTypeInfoCount",
        "GetTypeInfo",
        "GetIDsOfNames",
        "Invoke",
    }
    for f in funcs:
        name = f.get("name")
        if not name or name in standard_idispatch or name in seen_methods:
            continue
        seen_methods.add(name)
        memid = f.get("memid")
        flags = f.get("flags", 0) or 0
        param_names = f.get("param_names", []) or []
        params = []
        for i, pn in enumerate(param_names):
            sn = _safe_param_name(pn, i)
            ptype = _guess_type(pn)
            params.append(f"{ptype} {sn}")
        param_str = ", ".join(params)
        attrs: list[str] = []
        if memid is not None:
            attrs.append(f"DispId({memid})")
        if flags & 0x40:
            out.append("        // FUNCFLAG_FHIDDEN — deliberately hidden in typelib")
        for a in attrs:
            out.append(f"        [{a}]")
        out.append(f"        object {name}({param_str});")
    out.append("    }")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--typeinfo-run", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    ti_run = args.typeinfo_run or _newest(TI_ROOT)
    if not ti_run:
        raise SystemExit(f"no typeinfo runs under {TI_ROOT}")
    json_path = ti_run / "thinkcell_typeinfo_probe.json"
    if not json_path.exists():
        raise SystemExit(f"missing JSON: {json_path}")

    data = json.loads(json_path.read_text(encoding="utf-8-sig"))
    out_dir = args.output or (ROOT / "state" / "thinkcell_bridge" / "csharp_interop" / ti_run.name)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_cs = out_dir / "Thinkcell.Interop.cs"

    body = "\n\n".join(_emit_interface(t) for t in data.get("targets", []))
    cs = f"""// Auto-generated from typeinfo probe {ti_run.name}.
// Do not edit by hand — regenerate via:
//   .venv/bin/python scripts/generate_thinkcell_csharp_interop.py
//
// Notes:
// - Parameter types are best-guess from name patterns; the typelib does
//   not always carry full TYPEDESC info reachable through the
//   System.Runtime.InteropServices.ComTypes.ITypeInfo probe.
// - All methods return `object` because real return types are VARIANT in
//   the underlying COM dispatch interface.
// - FHIDDEN methods are emitted with a comment marker; do not invoke
//   them in production without a proof-write that defines expected behavior.
//
// Usage:
//   var ppt = new PowerPoint.Application();
//   var addinObj = ppt.COMAddIns.Item("thinkcell.addin").Object;
//   var tcPp = (Thinkcell.Interop.IPpMacroInterface)addinObj;
//   tcPp.LoadStyle(layout, fileName);

using System;
using System.Runtime.InteropServices;

namespace Thinkcell.Interop {{

{body}
}}
"""
    out_cs.write_text(cs, encoding="utf-8")
    print(f"wrote {out_cs}")
    print(f"interfaces: {[t.get('type_name') for t in data.get('targets', [])]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
