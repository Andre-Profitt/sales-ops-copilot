# think-cell COM Registry Probe

Date: 2026-05-01

This is the COM evidence pass for the installed Windows VM. It includes the
initial no-install registry probe plus the approved OleViewDotNet and Procmon
runs.

## Artifacts

- Latest JSON:
  `state/thinkcell_bridge/com_registry/20260501-201912/thinkcell_com_registry_probe.json`
- OleViewDotNet JSON:
  `state/thinkcell_bridge/oleviewdotnet/20260501-202858/thinkcell_oleviewdotnet_probe.json`
- Procmon report JSON:
  `state/thinkcell_bridge/procmon/20260501-203436/thinkcell_procmon_report.json`
- Procmon filtered summary JSON:
  `state/thinkcell_bridge/procmon/20260501-203436/thinkcell_procmon.filtered.summary.json`
- Procmon filtered CSV:
  `state/thinkcell_bridge/procmon/20260501-203436/thinkcell_procmon.filtered.csv`
- Probe harness:
  `scripts/probe_thinkcell_com_registry.ps1`
- OleViewDotNet harness:
  `scripts/probe_thinkcell_oleviewdotnet.ps1`
- Procmon harness:
  `scripts/procmon_thinkcell_trace.ps1`
- Runner:
  `scripts/run_thinkcell_com_registry_probe.py`
- OleViewDotNet runner:
  `scripts/run_thinkcell_oleviewdotnet_probe.py`
- Procmon runner:
  `scripts/run_thinkcell_procmon_trace.py`
- Procmon summary script:
  `scripts/analyze_thinkcell_procmon_trace.py`

## Tool Availability

Initially installed inspection tools found on the VM:

- `winget.exe`

Approved and added under `C:\tcw`:

- OleViewDotNet v1.11:
  `C:\tcw\oleviewdotnet`
- Sysinternals Process Monitor:
  `C:\tcw\procmon`

Windows SDK `oleview.exe` is still not installed. OleViewDotNet's GUI cannot
run over the SSH non-interactive session, but its PowerShell module works and
is the better machine-readable evidence path.

## Registry Findings

Registered think-cell-ish ProgIDs:

- `.ppttc` -> `thinkcell.ppttc`
- `thinkcell.ppttc`
- `thinkcell.addin`
- `thinkcell.addin.1`
- `think-cell Send With Gmail.Mailto`

Primary COM add-in CLSID:

- `{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1}`

CLSID backing:

- `InprocServer32`: `C:\Program Files (x86)\think-cell\arm64\tcaddin.dll`
- `ThreadingModel`: `Apartment`
- `ProgID`: `thinkcell.addin.1`
- `VersionIndependentProgID`: `thinkcell.addin`
- `TypeLib`: none registered
- `LocalServer32`: none registered

Office AddIns registration exists for both PowerPoint and Excel, in both native
and WOW6432Node hives, with `LoadBehavior = 3` and `CommandLineSafe = 1`.

Live COMAddIns check:

- PowerPoint exposes `thinkcell.addin`, connected, object type `System.__ComObject`.
- Excel exposes `thinkcell.addin`, connected, object type `System.__ComObject`.

## OleViewDotNet Findings

OleViewDotNet module result for `thinkcell.addin`:

- CLSID: `{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1}`
- Default server:
  `C:\Program Files (x86)\think-cell\arm64\tcaddin.dll`
- Server type: `InProcServer32`
- Threading model: `Apartment`
- ProgIDs: `thinkcell.addin`, `thinkcell.addin.1`
- TypeLib: none
- Factory interfaces: 0
- Interfaces loaded: 0
- AppID: none
- Auto-elevation: false
- Safe for scripting / initializing: false

This is a strong negative for a registered COM chart factory. OleViewDotNet
found the same single late-bound in-proc add-in class as the registry probe.

## Procmon Findings

The approved Procmon run captured PowerPoint startup and think-cell add-in
resolution, then exported the PML to CSV.

Key counts from the filtered capture:

- Filtered rows: 125,513
- `POWERPNT.EXE` rows: 86,207
- PowerPoint rows touching think-cell paths/registry: 801
- PowerPoint think-cell `NAME NOT FOUND` rows: 236
- Top think-cell path:
  `C:\Program Files (x86)\think-cell\arm64\tcaddin.dll`
- Top think-cell CLSID:
  `{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1}`

The relevant PowerPoint sequence is:

1. Enumerates `HKLM\Software\Microsoft\Office\PowerPoint\Addins`.
2. Finds `thinkcell.addin`.
3. Reads `LoadBehavior = 3`, `FriendlyName = think-cell`.
4. Resolves `HKCR\thinkcell.addin\CLSID`.
5. Resolves
   `HKCR\CLSID\{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1}\InprocServer32`.
6. Loads `tcaddin.dll`.

Procmon did not reveal a separate think-cell chart-factory CLSID. The
`NAME NOT FOUND` rows are normal COM lookup fallback across HKCU, ClickToRun,
and HKCR views before PowerPoint lands on the registered `thinkcell.addin`
class.

## Interpretation

This matches the official API design: think-cell exposes a late-bound COM
add-in object, not a type-library-backed object model. There is no separate
registered chart-factory CLSID, no registered TypeLib to browse, and no
registry evidence of a hidden `CreateChart`/`InsertChart` constructor surface.

That does not prove no internal constructor exists inside `tcaddin.dll`; it
does mean OleView-style COM browsing is unlikely to reveal more than the
late-bound `IDispatch` surface already enumerated by the hidden surface probe.

## Production Implication

Use the supported surfaces:

- PowerPoint `PresentationFromTemplateStep3`
- PowerPoint `UpdateBatchStep3`
- Excel `CreateUpdate`
- Excel update builder `AddRangeData`, `AddRangeImage`, `Send`
- `.ppttc` JSON with `ppttc.exe` / `tcserver.exe`

Do not plan the factory around discovering a registered COM chart constructor.
Keep the production lane as donor charts plus named elements plus `.ppttc` /
Excel range binding.

## Re-run Command

```bash
.venv/bin/python scripts/run_thinkcell_com_registry_probe.py

.venv/bin/python scripts/run_thinkcell_oleviewdotnet_probe.py

.venv/bin/python scripts/run_thinkcell_procmon_trace.py

.venv/bin/python scripts/analyze_thinkcell_procmon_trace.py \
  state/thinkcell_bridge/procmon/20260501-203436/thinkcell_procmon.filtered.csv
```
