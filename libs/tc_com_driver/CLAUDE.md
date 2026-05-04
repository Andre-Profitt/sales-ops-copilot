# tc_com_driver

Python wrapper around think-cell's documented COM dispatch surface.

## Production usage

`tc_com_driver` is the COM-dispatch utility surface — use it for bespoke chart
updates (`UpdateBatch.AddRangeData`, `IXlMacroInterface.PresentationFromTemplate`,
etc.), interactive PowerPoint sessions, and research probes against the live
add-in.

For the LAND deck factory pipeline (`.ppttc` -> bound `.pptx`), use
`libs/tcrender` instead — it's the documented vendor-sanctioned headless
render path (`ppttc.exe <input.ppttc> -o <output.pptx>`) and is what the
9-director SD-monthly cadence runs through.

This lib is utility-not-production: keep it for COM-only flows and one-off
operations. The API documented below is unchanged.

## What this is

A `pywin32`-based client that drives think-cell's add-in from Python on a
licensed Windows VM, the same way `python-pptx` wraps PowerPoint or any
`comtypes` script wraps another Office add-in. Vendor-sanctioned `IDispatch`
surface only — no reverse engineering, no custom protocols.

## Three dispatch interfaces wrapped

Source-of-truth typeinfo dump:
`state/thinkcell_bridge/typeinfo/20260501-215903/thinkcell_typeinfo_probe.json`.
Cross-check against the auto-generated C# interop in
`state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`.

| Interface           | IID                                      | Methods wrapped |
| ------------------- | ---------------------------------------- | --------------- |
| `IPpMacroInterface` | `{24f3e526-2a15-4b8b-bc6a-558500f451c1}` | 19              |
| `IXlMacroInterface` | `{085347c3-2d5b-4885-869a-b9cc362b924c}` | 3               |
| `IUpdateBatch`      | `{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}` | 3               |

(19 + 3 + 3 = 25 user-visible methods. The 12 `IDispatch`/`IUnknown`
plumbing methods plus 7 FHIDDEN `Step*` variants are exposed as `_step*`
private methods on `PpAddIn` for advanced callers — see typeinfo for
calling conventions.)

## Requirements

- Windows (10/11 or Server). `ThinkCellClient.connect()` raises
  `WrongPlatformError` on macOS / Linux.
- A licensed think-cell installation registered as a PowerPoint COM add-in.
- An open PowerPoint instance (or one we can launch). Excel is launched on
  demand by think-cell when `presentation_from_template` is called.
- `pywin32 >= 308`.

## Install (editable, inside parent venv)

```powershell
# On the Windows VM
cd C:\path\to\sales-ops-copilot
.venv\Scripts\pip install -e libs\tc_com_driver
```

```bash
# On Mac (skips pywin32 via env marker; smoke test verifies WrongPlatformError)
cd ~/code/apps/sales-ops-copilot
.venv/bin/pip install -e libs/tc_com_driver
```

## Usage

```python
from tc_com_driver import ThinkCellClient

with ThinkCellClient.connect() as client:
    assert client.pp.is_add_in_active()

    # Generate deck from an Excel template + workbook
    pres = client.xl.presentation_from_template(
        workbook=excel_workbook,
        template=r"C:\templates\monthly_review.pptx",
        powerpoint_app=client.powerpoint,
    )

    # Bulk-update charts
    batch = client.xl.create_update()
    batch.add_range_data(target=pres, name="ARRByRegion", range=arr_range)
    batch.add_range_data(target=pres, name="WinRate", range=winrate_range)
    batch.send()
```

## Tests

- Mac: `tests/test_smoke_mac.py` — imports + `WrongPlatformError` path.
- Windows VM: `tests/test_smoke_vm.py` — connect, find add-in, call
  `is_add_in_active()`. Andre runs interactively.

## Out of scope

No CLI. No auth/crypto/HTTP/network code. No writes outside the COM surface.

## See also

- `libs/tcxml/` — reader/writer for think-cell's CFB-wrapped chart XML
  (separate concern: post-build inspection of `.pptx` artifacts).
- `state/thinkcell_bridge/MASTER_STATE.md` (if present) for the broader
  bridge program state.
