# think-cell Hidden Surface Probe

Date: 2026-05-01

This probe looked for a hidden or undocumented chart-construction API beyond
the official update/binding surface.

## Artifacts

- Hidden surface JSON:
  `state/thinkcell_bridge/hidden_surface/20260501-195238/thinkcell_hidden_surface_probe.json`
- UI entrypoint smoke JSON:
  `state/thinkcell_bridge/hidden_surface/20260501-195408/thinkcell_ui_entrypoint_probe.json`
- Dynamic Office/COM ETW trace JSON:
  `state/thinkcell_bridge/dynamic_trace/20260501-200951/thinkcell_ui_dynamic_trace.json`
- Dynamic trace CSV/XML:
  `state/thinkcell_bridge/dynamic_trace/20260501-200951/thinkcell_ui_dynamic_trace_events.csv`
  and `state/thinkcell_bridge/dynamic_trace/20260501-200951/thinkcell_ui_dynamic_trace_events.xml`
- COM registry / OleView-lite JSON:
  `state/thinkcell_bridge/com_registry/20260501-201912/thinkcell_com_registry_probe.json`
- Probe harness:
  `scripts/probe_thinkcell_hidden_surface.ps1`
- Runner:
  `scripts/run_thinkcell_hidden_surface_probe.py`

## Method

The hidden-surface probe used safe name resolution rather than execution:

1. Enumerate visible PowerPoint, Excel, and Excel update-builder COM members.
2. Scan installed think-cell binaries, prioritizing `tcaddin.dll`, for
   command-like strings and ribbon callback names.
3. Generate 3,200 candidate names from binary strings and common constructor
   patterns.
4. Check each candidate with `IDispatch.GetIDsOfNames`.

`GetIDsOfNames` is important: it answers whether a name is dispatch-callable
without invoking the method. This avoids accidentally opening UI insertion mode
or mutating a deck.

## Result

No headless chart constructor was found.

Resolved PowerPoint add-in names:

- `ActivateAddIn`
- `BainToolboxApplyShift`
- `BainToolboxRectangles`
- `GetMekkoGraphicsXML`
- `GetStyleName`
- `GetStyleNameStep2`
- `ImportMekkoGraphicsCharts`
- `IsAddInActive`
- `LoadStyle`
- `LoadStyleForRegion`
- `LoadStyleForRegionStep2`
- `LoadStyleStep2`
- `PresentationFromTemplateStep3`
- `RemoveStyles`
- `RemoveStylesStep2`
- `ShowChartGallery`
- `StartTableInsertion`
- `UpdateBatchStep3`
- `UpdateChartStep3`

Resolved Excel add-in names:

- `CreateUpdate`
- `PresentationFromTemplate`
- `UpdateChart`

Resolved Excel update-builder names:

- `AddRangeData`
- `AddRangeImage`
- `Send`

Constructor-like callable names found: none.

## Useful Internal Clues

`tcaddin.dll` does contain internal/ribbon strings:

- `tc:ChartsGallery`
- `tc:Table`
- `tc:NamedTextField`
- `StartTableInsertion`
- `ShowChartGallery`
- `tglbtnWaterfall_onAction`
- `tglbtnGantt_onAction`
- `tglbtnMekkoArea_onAction`
- `tglbtnMekkoXY_onAction`
- `tglbtnScatter_onAction`
- `tglbtnTable_onAction`
- `CXlApplication::InsertChartToData`

These are useful for understanding the add-in architecture, but they did not
resolve as callable methods on the public PowerPoint add-in, Excel add-in, or
Excel update-builder COM objects. Candidate names such as `InsertChartToData`,
`ChartsGallery`, `ChartToDataDialog`, `tglbtnWaterfall_onAction`,
`SetAutomationName`, `SetElementName`, and `RenameElement` returned
`DISP_E_UNKNOWNNAME` (`0x80020006`).

## UI Entrypoint Smoke

A disposable UI-entrypoint smoke attempted custom ribbon IDs and the two known
UI-only methods:

- `CommandBars.ExecuteMso("tc:ChartsGallery")`
- `CommandBars.ExecuteMso("tc:ElementsGallery")`
- `CommandBars.ExecuteMso("tc:Table")`
- `CommandBars.ExecuteMso("tc:ChartToDataDialog")`
- `tcPpAddIn.StartTableInsertion()`
- `tcPpAddIn.ShowChartGallery(100,100,700,500,0)`

No shape was created. The smoke is not a production proof because PowerPoint
returned COM/RPC errors for part of the UI path, but it supports the same
directional conclusion: the ribbon callbacks are UI infrastructure, not a
headless constructor contract.

## Dynamic Trace

The SSH-driven dynamic trace could not exercise true desktop insertion, but it
did capture a useful negative result:

- WPR `GeneralProfile` was rejected by the VM with `0x80070032`.
- The fallback `logman` ETW trace succeeded with Office, COMRuntime, OLE, and
  OfficeLogging providers.
- Trace size: 9.3 MB ETL, converted to 13 MB CSV and 32 MB XML.
- Both `StartTableInsertion()` and `ShowChartGallery(...)` returned
  `0x800706BA` / RPC server unavailable under the non-interactive SSH session.
- The trace confirms PowerPoint loaded `thinkcell.addin` from `tcaddin.dll`
  version `15.0.100.220`.
- The trace showed Office automation exceptions around the failed UI path, but
  no headless shape creation and no chart/ole package output.

Interpretation: the UI methods need a real interactive desktop and are not a
headless factory API. A future Procmon/API Monitor pass should be manual,
desktop-driven, and treated as evidence gathering only.

## COM Registry / OleView-Lite

The registry probe found the same architecture OleView would likely show:

- ProgID `thinkcell.addin` / `thinkcell.addin.1`.
- CLSID `{D52B1FA2-1EF8-4035-9DA6-8AD0F40267A1}`.
- `InprocServer32` points to
  `C:\Program Files (x86)\think-cell\arm64\tcaddin.dll`.
- `ThreadingModel` is `Apartment`.
- No registered TypeLib.
- No registered LocalServer32.
- No separate registered chart factory CLSID.
- PowerPoint and Excel both expose a connected live `COMAddIns("thinkcell.addin")`
  object.

This supports the current production stance: late-bound add-in methods are the
public automation surface; direct chart construction is not registered as a COM
object model.

## Production Implication

Do not spend sprint time searching for a hidden `CreateChart` API unless new
evidence appears from think-cell support or a different installed version.

The production factory should continue to use:

- donor object graphs from the SimCorp seed or stock `.potx` templates,
- safe name patching of existing think-cell payloads,
- `.ppttc` binding for native charts/text,
- Excel COM `AddRangeImage` for table-shaped outputs,
- render and repair/open smoke gates before publishing.

## Re-run Commands

```bash
.venv/bin/python scripts/run_thinkcell_hidden_surface_probe.py \
  --max-binary-strings 2400 \
  --max-dispatch-candidates 3200

.venv/bin/python scripts/run_thinkcell_ui_entrypoint_probe.py

.venv/bin/python scripts/run_thinkcell_ui_dynamic_trace.py

.venv/bin/python scripts/run_thinkcell_com_registry_probe.py
```
