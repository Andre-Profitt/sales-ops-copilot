# think-cell Automation API Surface

Date: 2026-05-01

This is the stable readable hub for the think-cell automation/API surface as it
exists on the SimCorp Parallels Windows runtime. It pairs the official
think-cell manual with the COM surface our probe actually observes, and
classifies every capability as `proven`, `observed_uninvoked`, `blocked`, or
`not_found`.

Use this hub as the entry point before adopting any new automation lane.

## Sources

- API manual: <https://www.think-cell.com/en/resources/manual/api>
- Introduction to automation: <https://www.think-cell.com/en/resources/manual/introductionautomation>
- Excel data automation: <https://www.think-cell.com/en/resources/manual/exceldataautomation>
- JSON data automation: <https://www.think-cell.com/en/resources/manual/jsondataautomation>
- Style files: <https://www.think-cell.com/en/resources/manual/style-files>
- Mekko Graphics import: <https://www.think-cell.com/en/resources/manual/import-mekko-graphics>
- Companion source map: [`automation-api-source-map.md`](automation-api-source-map.md)
- Live probe: `scripts/thinkcell_programmatic_probe.ps1` (run via SSH to
  `Windows-VM`).
- Probe driver and report writer: `scripts/thinkcell_programmatic_lab.py`.
- Latest probe artifacts:
  - `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json`
  - `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.md`

## Platform & Entry Point

- The think-cell automation API is **Windows-only** and exposed exclusively
  through Office COM add-ins.
- Calls are **late-bound** through `IDispatch`; there is no think-cell type
  library to add as a project reference.
- **Office Web Add-ins cannot use this API**, because Office Web Add-ins do not
  have a path to interact directly with Office COM add-ins.
- PowerPoint entry point:
  `Application.COMAddIns("thinkcell.addin").Object` (`tcPpAddIn`).
- Excel entry point:
  `Application.COMAddIns("thinkcell.addin").Object` (`tcXlAddIn`).

## Developer Setup

Manual source: <https://www.think-cell.com/en/resources/manual/api> (Get
started + setup sections). All notes below are traceable to that page or to
Microsoft Learn pages it links explicitly.

### VBA host (PowerPoint or Excel)

- Place the macro inside the host whose `Application.COMAddIns` you intend to
  query. Acquiring `tcXlAddIn` from a PowerPoint VBA host requires a separate
  `Excel.Application` instance; acquiring `tcPpAddIn` from an Excel VBA host
  requires a separate `PowerPoint.Application` instance.
- Always declare the add-in reference as `Object` to force late binding:

  ```vb
  Dim tcaddin As Object
  Set tcaddin = Application.COMAddIns("thinkcell.addin").Object
  ```

- Add `Tools > References > Microsoft Excel 16.0 Object Library` (or the
  matching version) when using Excel types from a PowerPoint VBA project, and
  `Microsoft PowerPoint 16.0 Object Library` when using PowerPoint types from
  an Excel VBA project. Office 2013 = 15.0; Office 2016 and later = 16.0.
- Top every module with `Option Explicit` to require explicit declarations
  (Microsoft VBA reference; cited from the API page).
- Office types (e.g., `Excel.Workbook`, `PowerPoint.Presentation`) may be
  early-bound; only the think-cell `Object` reference must be late-bound.

### C# host (.NET, console or service)

- Add Microsoft Office type libraries via Visual Studio's
  `Project > Add COM Reference` (Reference Manager → COM > Type Libraries):
  `Microsoft Office <version> Object Library`,
  `Microsoft PowerPoint <version> Object Library`,
  `Microsoft Excel <version> Object Library`.
- Keep `Embed Interop Types = true` (Visual Studio default) so a single
  binary works against multiple Office versions (Microsoft Learn:
  Embed Interop Types).
- Acquire the add-in late-bound. `var` (or `dynamic`) is required because no
  think-cell type library exists:

  ```csharp
  var tcXlAddIn = xlapp.COMAddIns.Item("thinkcell.addin").Object;
  var tcUpdate = tcXlAddIn.CreateUpdate();
  ```

- Handle COM errors via `System.Runtime.InteropServices.COMException`. Map
  HRESULTs per Microsoft Learn (e.g., `GetMekkoGraphicsXML` raises
  `E_INVALIDARG (0x80070057)` on a non-Mekko shape).
- For VSTO add-ins specifically (PowerPoint/Excel VSTO Add-in templates),
  install **Office Developer Tools for Visual Studio** from
  Settings > Apps > Visual Studio > Modify > Office/SharePoint development.
  Headless automation hosts do **not** need VSTO; only ship a VSTO project
  if SimCorp ever wraps think-cell behind a custom Office add-in.

### Office Web Add-ins (blocked)

Office Web Add-ins cannot interact with the Office application's object model
directly and cannot reach Office COM add-ins, so they cannot use the
think-cell API. Manual quote: _"think-cell's API cannot be used from Office
Web Add-Ins."_ This is a hard block, not a future capability.

### Cited Microsoft Learn references

- Early/late binding in Automation: <https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/binding-type-available-to-automation-clients>
- `Option Explicit` (VBA): <https://learn.microsoft.com/office/vba/language/reference/user-interface-help/option-explicit-statement>
- C# `dynamic` type: <https://learn.microsoft.com/dotnet/csharp/programming-guide/types/using-type-dynamic>
- Add type-library references: <https://learn.microsoft.com/en-us/dotnet/framework/interop/how-to-add-references-to-type-libraries>
- Embed Interop Types: <https://learn.microsoft.com/previous-versions/visualstudio/visual-studio-2013/ee317478(v=vs.120)>
- HRESULT ↔ .NET exception map: <https://learn.microsoft.com/dotnet/framework/interop/how-to-map-hresults-and-exceptions>
- VSTO setup overview: <https://learn.microsoft.com/visualstudio/vsto/configuring-a-computer-to-develop-office-solutions?view=vs-2022>
- VSTO setup how-to: <https://learn.microsoft.com/visualstudio/vsto/how-to-configure-a-computer-to-develop-office-solutions?view=vs-2022>
- PowerPoint `CustomLayout`: <https://learn.microsoft.com/office/vba/api/powerpoint.customlayout>
- PowerPoint `Master`: <https://learn.microsoft.com/office/vba/api/powerpoint.master>

## Excel Data Automation (`tcXlAddIn` / `tcUpdate`)

`tcXlAddIn` exposes:

- `PresentationFromTemplate` — opens a presentation from a think-cell
  template. **Observed** in the probe but **not yet exercised** by the SimCorp
  pipeline; the JSON-automation `ppttc.exe` lane is the production wrapper.
- `UpdateChart` — **deprecated** single-chart update. Do not invoke. Use
  `UpdateBatch` instead.
- `CreateUpdate` — returns a `tcUpdate` object that batches range/image
  updates. **Proven** in the SimCorp table-image lane.

`tcUpdate` exposes:

- `AddRangeData(Target, Name, Range, Transposed)` — binds an Excel range as
  datasheet content for a named chart/table element. **Proven**.
- `AddRangeImage(Target, Name, Range)` — binds an Excel range as an **image**
  into a named element. **Only available through `UpdateBatch`**, never
  directly. **Proven** for SimCorp table-image donors.
- `Send()` — commits all queued updates in the batch to PowerPoint. **Proven**.

`Target` is one of: `Presentation`, `SlideRange`, `Slide`, `Master`,
`CustomLayout`.

`Name` rules:

- Must already exist in the PowerPoint template as an `AddRangeData` or
  `AddRangeImage` name.
- Names are **case-insensitive**.
- If the same name appears in multiple template elements, every matching
  element receives the same data.
- `.ppttc` JSON automation and Excel COM share this name space; the SimCorp
  LAND seed is the source of truth for which names exist.

`Transposed` semantics differ by chart type:

- **Standard charts**: swaps series and categories.
- **Tables**: swaps row/column layout.
- **Gantt / timeline**: swaps activities and anchor points.
- **Scatter / bubble**: swaps data points and dimensions.

## PowerPoint API (`tcPpAddIn`)

Update lane (used internally by the JSON automation wrapper; **observed but
uninvoked** from SimCorp Python):

- `PresentationFromTemplateStep3`
- `UpdateChartStep3`
- `UpdateBatchStep3`

Style files (**observed but uninvoked**):

- `LoadStyle`
- `LoadStyleForRegion`
- `GetStyleName`
- `RemoveStyles`
- (and `Step2` siblings)

Mekko Graphics import (**observed but uninvoked**):

- `ImportMekkoGraphicsCharts`
- `GetMekkoGraphicsXML`

UI-only (these are not headless creation methods; do not treat as automation):

- `ShowChartGallery`
- `StartTableInsertion`

Do **not** assume any of these create charts. The probe finds zero COM methods
matching `Create*Chart` or `Insert*Chart`. Programmatic chart creation is
`not_found`.

## JSON Data Automation (`.ppttc`)

`.ppttc` is the JSON wrapper SimCorp uses today. Shape:

- Root: array of template objects.
- Each template object has `template` (local path or remote URL) and `data`
  (array of `{name, table}` objects).
- Template ordering drives slide order in the rendered presentation.

Datasheet table rules:

- First row is categories with a leading `null` cell (the corner).
- Subsequent rows carry series labels in the first column then values.
- An empty row `[]` intentionally suppresses a series and shifts the color
  scheme.
- Optional rows/columns must match the template datasheet schema, otherwise
  binding fails.

Cell types:

- `string`
- `number`
- `date` — ISO `YYYY-MM-DD` only
- `percentage` — numeric, no `%` sign (`50.0` means 50%)
- `fill` — hex (`#RRGGBB`) or RGB; **pair** with a sibling value cell, never
  replace it
- `null` — empty cell, used for the table corner and intentional gaps

`ppttc.exe` CLI form (Windows automation scripts):

```text
ppttc.exe <input.ppttc> -o <output.pptx>
```

`tcserver.exe` HTTP form (Windows server, optional, requires UAC to register
URL):

- Method: `POST`
- MIME type: `application/vnd.think-cell.ppttc+json`
- Body: `.ppttc` JSON content
- Response: `.pptx` file download

## Official Examples

These examples are quoted from the official manual and serve as the canonical
reference for any SimCorp wrapper code. Each example links the surface section
above to a copy/pastable shape.

### `tcXlAddIn.PresentationFromTemplate` — VBA

Manual: <https://www.think-cell.com/en/resources/manual/exceldataautomation#sect_presentationfromtemplatefunction>

```vb
Option Explicit

Sub PresentationFromTemplate_Sample()
    Dim rng As Excel.Range
    Set rng = ActiveWorkbook.Sheets(1).Cells(3, 8)

    Dim tcXlAddIn As Object
    Set tcXlAddIn = Application.COMAddIns("thinkcell.addin").Object

    Dim ppapp As Object
    Set ppapp = New PowerPoint.Application

    Dim i As Integer
    For i = 1 To 10
        rng.Value = i
        Dim pres As PowerPoint.Presentation
        Set pres = tcXlAddIn.PresentationFromTemplate( _
            Excel.ActiveWorkbook, "template.pptx", ppapp _
        )
        pres.SaveAs "C:\Samples\PresentationFromTemplate\output_" & i & ".pptx"
        pres.Close
    Next
End Sub
```

### `tcXlAddIn.PresentationFromTemplate` — C#

```csharp
using PowerPoint = Microsoft.Office.Interop.PowerPoint;
using Excel = Microsoft.Office.Interop.Excel;

var xlapp = new Excel.Application { Visible = true };
var tcXlAddIn = xlapp.COMAddIns.Item("thinkcell.addin").Object;
var workbook = xlapp.Workbooks.Open(@"C:\Samples\PresentationFromTemplate\data.xlsx");
var ppapp = new PowerPoint.Application();
for (var i = 1; i <= 10; ++i)
{
    workbook.Sheets[1].Cells[3, 8] = i;
    PowerPoint.Presentation presentation = tcXlAddIn.PresentationFromTemplate(
        workbook,
        @"C:\Samples\PresentationFromTemplate\template.pptx",
        ppapp);
    presentation.SaveAs(@"C:\Samples\PresentationFromTemplate\output" + i + ".pptx");
    presentation.Close();
}
```

### `tcXlAddIn.UpdateBatch` (`CreateUpdate` / `AddRangeData` / `AddRangeImage` / `Send`) — VBA

Manual: <https://www.think-cell.com/en/resources/manual/exceldataautomation#sect_updatebatch>

```vb
Option Explicit

Sub UpdateBatch_Sample()
    Dim rngTitle As Excel.Range
    Set rngTitle = ActiveWorkbook.Sheets(1).Range("A1")
    Dim rngChart As Excel.Range
    Set rngChart = ActiveWorkbook.Sheets(1).Range("A2:D5")
    Dim rngTableAsImage As Excel.Range
    Set rngTableAsImage = ActiveWorkbook.Sheets(1).Range("A7:D10")

    Dim tcXlAddIn As Object
    Set tcXlAddIn = Application.COMAddIns("thinkcell.addin").Object

    Dim ppapp As Object
    Set ppapp = New PowerPoint.Application

    Dim pres As PowerPoint.Presentation
    Set pres = ppapp.Presentations.Open( _
        Filename:="C:\Samples\UpdateBatch\template.pptx", _
        Untitled:=msoTrue, _
        WithWindow:=msoFalse)

    Dim tcUpdate As Object
    Set tcUpdate = tcXlAddIn.CreateUpdate

    Call tcUpdate.AddRangeData(pres, "Title", rngTitle, False)
    Call tcUpdate.AddRangeData(pres, "Chart1", rngChart, False)
    Call tcUpdate.AddRangeImage(pres, "TableAsImage1", rngTableAsImage)
    Call tcUpdate.Send

    pres.SaveAs ("C:\Samples\UpdateBatch\template_updated.pptx")
    pres.Close
    ppapp.Quit
End Sub
```

### `tcXlAddIn.UpdateBatch` — C#

```csharp
PowerPoint.Application ppapp = new PowerPoint.Application();
PowerPoint.Presentation presentation = ppapp.Presentations.Open(
    @"C:\Samples\UpdateBatch\template.pptx",
    Office.MsoTriState.msoFalse,
    Office.MsoTriState.msoTrue);

Excel.Application xlapp = new Excel.Application { Visible = true };
Excel.Workbook workbook = xlapp.Workbooks.Open(
    @"C:\Samples\UpdateBatch\data.xlsx",
    Office.MsoTriState.msoFalse,
    Office.MsoTriState.msoTrue);
Excel.Worksheet worksheet = workbook.Sheets[1];

var tcXlAddIn = xlapp.COMAddIns.Item("thinkcell.addin").Object;
var tcUpdate = tcXlAddIn.CreateUpdate();

tcUpdate.AddRangeData(presentation, "SlideTitle", worksheet.get_Range("A1"), true);
tcUpdate.AddRangeData(presentation, "Chart1",     worksheet.get_Range("A2", "D5"), true);
tcUpdate.AddRangeImage(presentation, "TableAsImage1", worksheet.get_Range("A7", "D10"));
tcUpdate.Send();

presentation.SaveAs(@"C:\Samples\UpdateBatch\template_updated.pptx");
presentation.Close();
```

### Style API (`LoadStyle` / `LoadStyleForRegion` / `GetStyleName` / `RemoveStyles`) — VBA

Manual: <https://www.think-cell.com/en/resources/manual/style-files>

```vb
Option Explicit

Sub Style_Sample()
    Dim tcPpAddIn As Object
    Set tcPpAddIn = Application.COMAddIns("thinkcell.addin").Object

    Dim master As Master
    Set master = Application.ActivePresentation.Designs(1).SlideMaster
    Dim layout As CustomLayout
    Set layout = master.CustomLayouts(2)

    Dim style As String
    style = "C:\Program Files (x86)\think-cell\styles\Default.xml"

    ' 1. Load master-level style FIRST.
    Call tcPpAddIn.LoadStyle(master, style)
    ' 2. Optional layout-level style overrides master for this layout.
    Call tcPpAddIn.LoadStyle(layout, style)
    ' 3. Region-scoped style for this layout (run AFTER all LoadStyle calls).
    Call tcPpAddIn.LoadStyleForRegion(layout, style, _
        0, 0, layout.Width / 2, layout.Height)
    ' 4. Read back the active style name on the master.
    Debug.Print tcPpAddIn.GetStyleName(master)
    ' 5. RemoveStyles only on a layout — masters must always retain a style.
    Call tcPpAddIn.RemoveStyles(layout)
End Sub
```

Style API contract (manual):

- Maximum **two** style files per layout: one `LoadStyle` + one `LoadStyleForRegion`.
- `LoadStyleForRegion` must run **after** all `LoadStyle` calls.
- `RemoveStyles` cannot be called on a `Master`.
- `GetStyleName` does **not** return the name of a style loaded via
  `LoadStyleForRegion`.
- Loading a newer-build style file into an older think-cell raises an error.

### Mekko Graphics import (`ImportMekkoGraphicsCharts` / `GetMekkoGraphicsXML`) — VBA

Manual: <https://www.think-cell.com/en/resources/manual/import-mekko-graphics>

```vb
Option Explicit

Sub Mekko_Import_Sample()
    Dim tcPpAddIn As Object
    Set tcPpAddIn = Application.COMAddIns("thinkcell.addin").Object

    Dim slide As PowerPoint.Slide
    Set slide = Application.ActivePresentation.Slides(1)

    Dim shapes() As PowerPoint.Shape
    ReDim shapes(0 To slide.Shapes.Count - 1)
    Dim i As Long
    For i = 0 To slide.Shapes.Count - 1
        Set shapes(i) = slide.Shapes(i + 1)
    Next

    ' Returns Nothing if no shapes were Mekko Graphics charts.
    Dim backup As PowerPoint.Slide
    Set backup = tcPpAddIn.ImportMekkoGraphicsCharts(shapes)

    ' Read XML for a specific Mekko shape (raises E_INVALIDARG on a non-Mekko shape).
    Dim xml As String
    On Error Resume Next
    xml = tcPpAddIn.GetMekkoGraphicsXML(slide.Shapes(1))
End Sub
```

### JSON automation — `ppttc.exe` CLI

```bat
:: Invoke from any Windows automation script.
"C:\Program Files (x86)\think-cell\ppttc.exe" path\to\input.ppttc -o path\to\output.pptx
```

### JSON automation — `tcserver.exe` HTTP

```text
POST http://server.local:8080/
Content-Type: application/vnd.think-cell.ppttc+json
Body: <.ppttc JSON>
Response: binary .pptx
```

Operating notes:

- `tcserver.exe` requires UAC approval to _Register URL_ on first start. Do
  NOT register URLs from automation; this is an explicit administrator step.
- The installation ships a self-test page at the registered root URL that
  demonstrates an `XMLHttpRequest`-based POST + file download.

## Capability Verdicts

| Capability                                                    | Status                            | Manual Section                      | Notes                                                         |
| ------------------------------------------------------------- | --------------------------------- | ----------------------------------- | ------------------------------------------------------------- |
| `ppttc.exe` template update                                   | `proven`                          | JSON Data Automation                | Production wrapper for native chart/text update.              |
| `tcXlAddIn.CreateUpdate()`                                    | `proven`                          | Excel Data Automation > UpdateBatch | Entry point for batch updates.                                |
| `tcUpdate.AddRangeData`                                       | `proven`                          | Excel Data Automation > UpdateBatch | Native chart/text/table-data update.                          |
| `tcUpdate.AddRangeImage`                                      | `proven`                          | Excel Data Automation > UpdateBatch | Table-image lane. Only via UpdateBatch.                       |
| `tcUpdate.Send`                                               | `proven`                          | Excel Data Automation > UpdateBatch | Commits the batch.                                            |
| `tcXlAddIn.PresentationFromTemplate`                          | `observed_uninvoked`              | Excel Data Automation               | Use the `.ppttc` wrapper instead.                             |
| `tcXlAddIn.UpdateChart`                                       | `observed_uninvoked` (deprecated) | Excel Data Automation               | Do not invoke.                                                |
| `tcPpAddIn.UpdateBatchStep3`                                  | `observed_uninvoked`              | API > PowerPoint                    | Internal; `ppttc.exe` is the wrapper.                         |
| `tcPpAddIn.UpdateChartStep3`                                  | `observed_uninvoked`              | API > PowerPoint                    | Internal; not exercised.                                      |
| `tcPpAddIn.PresentationFromTemplateStep3`                     | `observed_uninvoked`              | API > PowerPoint                    | Internal; not exercised.                                      |
| `tcPpAddIn.LoadStyle` / `LoadStyleForRegion` / `GetStyleName` / `RemoveStyles` | `proven` | API > Style files | Runtime-proven on a transient presentation; SimCorp brand-deck adoption still requires a separate decision record. |
| `tcPpAddIn.ImportMekkoGraphicsCharts` / `GetMekkoGraphicsXML` | `blocked`                         | API > Mekko Graphics import         | No Mekko Graphics donor PPTX exists on the runtime.           |
| `tcPpAddIn.ShowChartGallery` / `StartTableInsertion`          | `observed_uninvoked` (UI-only)    | API > UI                            | Not headless creation; SimCorp does not invoke.               |
| `tcserver.exe` HTTP service                                   | `observed_uninvoked`              | JSON Data Automation                | Inventoried only; no URL registration or service start.       |
| Programmatic chart creation                                   | `not_found`                       | (none)                              | No `Create*Chart` / `Insert*Chart` method on the COM surface. |
| Native editable think-cell tables                             | `blocked`                         | API > UI                            | Domain-blocked; use Excel COM `AddRangeImage`.                |
| Office Web Add-ins                                            | `blocked`                         | API > Limitations                   | Web add-ins cannot reach Office COM add-ins.                  |

Status meaning:

- **proven** — exercised by the SimCorp pipeline with bound-package/render
  evidence or by a dedicated runtime proof with an asserted side effect.
- **observed_uninvoked** — present on the COM surface, but no proof lane yet.
  Treat as inert capability, not production support.
- **blocked** — domain or platform constraint forbids using this lane today.
- **not_found** — no matching method exists on the COM surface; do not plan
  builds around it.

## Adoption Matrix

This table is the SimCorp factory disposition for each automation lane. It
joins the Capability Verdicts above with operating constraints, current
artifact evidence, and the next concrete action.

| Lane                                                                          | Status               | Current SimCorp use                                                                                       | Promotion criteria                                                                                                                                                                                                                       | Next action                                                                                                                                   |
| ----------------------------------------------------------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `ppttc.exe` (CLI)                                                             | `production`         | LAND seed binding for all directors; 28-slide bound deck + 28 PNG render evidence per latest probe.       | n/a — already canonical.                                                                                                                                                                                                                 | Maintain bound-package + render assertions on every run.                                                                                      |
| Excel COM `UpdateBatch` (table-image)                                         | `production`         | 19/19 table-image donors bound for QTR10 / QTR11 / QTR12 hybrid.                                          | n/a — already canonical.                                                                                                                                                                                                                 | Keep the donor bank in sync with the connected factory workbook.                                                                              |
| Excel COM `PresentationFromTemplate`                                          | `proof_candidate`    | Not invoked. Method present on `tcXlAddIn`. Sample `template.pptx` + named elements ship with think-cell. | A SimCorp seed must be authored as Excel-linked elements (rather than `.ppttc`-named only) before this lane buys anything over `ppttc.exe`.                                                                                              | Out-of-band: probe against installed `template.pptx` + a synthetic `.xlsx`. Do not build a SimCorp seed for it yet.                           |
| Style API (`LoadStyle`, `LoadStyleForRegion`, `GetStyleName`, `RemoveStyles`) | `runtime_proven`     | Not used in SimCorp deck builds yet; all four methods passed on a transient presentation in the latest lab. | Before production use, attach a SimCorp-approved style XML and run on a disposable copy of a SimCorp-branded deck master. Do not modify brand assets from the probe. | Keep `Invoke-StyleProofProbe` in the runtime lab; add a separate brand-style decision record before any production deck invocation. |
| Mekko Graphics import API                                                     | `not_applicable`     | SimCorp authors think-cell-native Mekko (QTR07) directly; no Mekko Graphics donor exists.                 | A real Mekko Graphics chart must appear in `state/thinkcell_bridge/mekko_samples/` before invocation.                                                                                                                                    | Probe inventories `mekko_samples` and records `samples_present=false`. No invocation.                                                         |
| `tcserver.exe` HTTP service                                                   | `proof_candidate`    | Not invoked. Inventory only.                                                                              | A SimCorp leadership decision is required before any URL registration or service start. Then build a SimCorp HTTP client per the manual MIME contract.                                                                                   | `Get-TcServerInventory` (added 2026-05-01) records path, version, and size; **does not register or start the server**.                        |
| Office Web Add-ins                                                            | `blocked` (platform) | n/a                                                                                                       | Officially blocked by the API page. Do not plan around it.                                                                                                                                                                               | None.                                                                                                                                         |
| Native editable think-cell tables                                             | `blocked` (domain)   | Replaced by Excel COM `AddRangeImage` table-image donors.                                                 | A real named, data-backed table donor must bind without PowerPoint repair prompts before reconsidering. Not currently feasible.                                                                                                          | None until evidence changes.                                                                                                                  |
| Programmatic chart creation                                                   | `not_found`          | n/a                                                                                                       | The COM surface does not expose a `Create*Chart` / `Insert*Chart` method. Donor-and-rename is the only chart-creation lane.                                                                                                              | None.                                                                                                                                         |

## Stop Conditions

- Observed-uninvoked methods are **not production support**: do not adopt them
  in a factory build until a proof lane (donor template + named element +
  bound output + rendered assertion) exists for that specific method.
- Stop if any payload blends ARR (`Type IN ('Land','Expand')`) with Renewal
  ACV (`Type = 'Renewal'`).
- Stop if a JSON payload tries to invent a named element that does not exist
  in the donor template; `.ppttc` cannot create chart objects.
- Stop if attempting to bind native editable think-cell tables; use the
  table-image lane.
- Stop if a headline currency basis is raw multi-currency SOQL `SUM` rather
  than FX-converted EUR Salesforce report aggregates (`s!field`).

## How to Refresh This Hub

1. Confirm the Parallels Windows VM is running.
2. Run the lab driver:

   ```bash
   .venv/bin/python scripts/thinkcell_programmatic_lab.py \
     --period 2026-Q2 \
     --director-slug Jesper-Tyrer \
     --render
   ```

3. Inspect the new probe artifact under
   `state/thinkcell_bridge/programmatic_lab/<stamp>/`.
4. If the probe surfaces a method this hub does not list, add it to the
   relevant section here and to `scripts/thinkcell_programmatic_probe.ps1`
   `Script:PptMethodGroups` / `ExcelAddinGroups` / `ExcelUpdateGroups` so
   future runs categorize it consistently.
5. Refresh the knowledge hub machine index at
   `state/thinkcell_bridge/json_automation/knowledge_hub.json` with the new
   latest probe path.
6. Regenerate the knowledge graph:

   ```bash
   .venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
   ```

## Hard SimCorp Constraints (Repeat)

- ARR is Land + Expand only via `APTS_Opportunity_ARR__c`.
- Renewal ACV is Renewal only via `APTS_Renewal_ACV__c`.
- Never blend ARR and Renewal ACV.
- Always set explicit `Type` filters on Salesforce reports.
- Use FX-converted EUR aggregates for leadership figures, not raw SOQL `SUM`.
- The VM is the **update runtime**, not a chart factory.
