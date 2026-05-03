# think-cell VM/API Probe

Date: 2026-05-01

This note records the current Parallels Windows VM think-cell API surface and
the recommended operating model for SimCorp deck automation.

For the readable, manual-attributed automation/API hub (Excel data automation,
PowerPoint COM, JSON automation, capability verdicts), see
[`automation-api-surface.md`](automation-api-surface.md). This file remains
the **runtime evidence** companion: latest probe paths, machine surface,
discovered method names, and the operating-model implications.

## Latest Probe

Command:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --render
```

Latest output:

- JSON: `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json`
- Markdown: `state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.md`
- Bound PPTX: `state/thinkcell_bridge/programmatic_lab/20260501-190411/ppttc_bridge/Jesper-Tyrer-seed-bound.pptx`
- Render: `state/thinkcell_bridge/programmatic_lab/20260501-190411/render/`

Result: pass.

Checks that passed:

- Parallels Windows 11 VM running.
- SimCorp LAND seed has 42/42 named automation elements.
- Table-image donor bank has 19/19 valid donors.
- Salesforce Q2 fit context loaded: 314 publishable Q2 rows after removing 33
  internal/test rows.
- Windows PowerPoint/Excel COM probe passed.
- Strict `.ppttc` build emitted 42/42 entries.
- Windows `ppttc.exe` bridge produced a 28-slide, 25-embedding bound deck.
- Render smoke produced 28 PNG slides.

## Machine Surface

VM:

- Host alias: `Windows-VM`
- VM name: `Windows 11`
- OS: Microsoft Windows 11 Pro
- Architecture: ARM64 on Apple Silicon
- PowerShell: 5.1

think-cell:

- Install root: `C:\Program Files (x86)\think-cell`
- CLI: `C:\Program Files (x86)\think-cell\ppttc.exe`
- Local docs: `/Library/Application Support/Microsoft/think-cell/manual/`
- Local JSON schema: `/Library/Application Support/Microsoft/think-cell/ppttc/ppttc-schema.json`
- Local sample: `/Library/Application Support/Microsoft/think-cell/ppttc/sample.ppttc`
- Local sample template names: `SlideTitle`, `LeftChartTitle`,
  `RightChartTitle`, `LeftChart`, `RightChart`

## API Surface Found

PowerPoint add-in methods (`tcPpAddIn` via `Application.COMAddIns("thinkcell.addin").Object`):

Template/update lane:

- `PresentationFromTemplateStep3`
- `UpdateChartStep3`
- `UpdateBatchStep3`

Style files:

- `LoadStyle`, `LoadStyleStep2`
- `LoadStyleForRegion`, `LoadStyleForRegionStep2`
- `GetStyleName`, `GetStyleNameStep2`
- `RemoveStyles`, `RemoveStylesStep2`

Mekko Graphics import:

- `ImportMekkoGraphicsCharts`
- `GetMekkoGraphicsXML`

UI-only (not headless creation methods):

- `ShowChartGallery`
- `StartTableInsertion`

Add-in lifecycle / Bain toolbox:

- `ActivateAddIn`, `IsAddInActive`
- `BainToolboxApplyShift`, `BainToolboxRectangles`

Excel add-in methods (`tcXlAddIn`):

- `CreateUpdate` — entry point for batch updates.
- `PresentationFromTemplate` — open a presentation from a template.
- `UpdateChart` — **deprecated**; use `UpdateBatch` instead.

Excel update object methods (`tcUpdate`, returned by `CreateUpdate`):

- `AddRangeData(Target, Name, Range, Transposed)`
- `AddRangeImage(Target, Name, Range)` — only available through `UpdateBatch`.
- `Send()`

`Target` is one of: `Presentation`, `SlideRange`, `Slide`, `Master`,
`CustomLayout`. `Name` resolution is case-insensitive and must already exist
in the template; same names receive the same data.

Capability verdict (`proven` / `observed_uninvoked` / `blocked` / `not_found`):

| Capability                                | Status             | Manual Section                      | Notes                                                             |
| ----------------------------------------- | ------------------ | ----------------------------------- | ----------------------------------------------------------------- |
| `ppttc.exe` template update               | proven             | JSON Data Automation                | Production wrapper for native chart/text update.                  |
| `tcXlAddIn.CreateUpdate()`                | proven             | Excel Data Automation > UpdateBatch | Entry point for batch updates.                                    |
| `tcUpdate.AddRangeData`                   | proven             | Excel Data Automation > UpdateBatch | Native chart/text/table-data update.                              |
| `tcUpdate.AddRangeImage`                  | proven             | Excel Data Automation > UpdateBatch | Table-image lane. Only via UpdateBatch.                           |
| `tcUpdate.Send`                           | proven             | Excel Data Automation > UpdateBatch | Commits the queued updates.                                       |
| `tcXlAddIn.PresentationFromTemplate`      | observed_uninvoked | Excel Data Automation               | Use `.ppttc` wrapper instead.                                     |
| `tcXlAddIn.UpdateChart`                   | observed_uninvoked | Excel Data Automation               | Deprecated; do not invoke.                                        |
| `tcPpAddIn.UpdateBatchStep3`              | observed_uninvoked | API > PowerPoint                    | Internal; `ppttc.exe` is the wrapper.                             |
| `tcPpAddIn.UpdateChartStep3`              | observed_uninvoked | API > PowerPoint                    | Internal; not exercised.                                          |
| `tcPpAddIn.PresentationFromTemplateStep3` | observed_uninvoked | API > PowerPoint                    | Internal; not exercised.                                          |
| Style file methods                        | observed_uninvoked | API > Style files                   | `LoadStyle`/`GetStyleName`/`RemoveStyles`; no proof lane yet.     |
| Mekko Graphics import                     | observed_uninvoked | API > Mekko Graphics import         | `ImportMekkoGraphicsCharts`/`GetMekkoGraphicsXML`; no proof lane. |
| UI-only methods                           | observed_uninvoked | API > UI                            | `ShowChartGallery`/`StartTableInsertion`; not headless creation.  |
| Programmatic chart creation               | not_found          | (none)                              | No `Create*Chart`/`Insert*Chart` method on the COM surface.       |
| Native editable think-cell tables         | blocked            | API > UI                            | Domain-blocked; use Excel COM `AddRangeImage` table-image lane.   |
| Office Web Add-ins                        | blocked            | API > Limitations                   | Web add-ins cannot reach Office COM add-ins.                      |

> **Stop condition.** `observed_uninvoked` is **not production support**. Do
> not adopt one of these methods in a factory build until a proof lane (donor
> template + named element + bound output + rendered assertion) exists for
> that specific method.

## Best Use

Use the VM as an update runtime, not a chart factory.

Best lane for native charts and automation text:

1. Start with a PPTX that already contains named think-cell elements.
2. Generate strict `.ppttc` JSON with matching names.
3. Run `scripts/run_thinkcell_windows_bridge.py`.
4. Assert bound text/data in the output PPTX.
5. Render and inspect PNG output.

Best lane for table-heavy slides:

1. Use table-image donors, not native editable think-cell tables.
2. Build named Excel ranges from the connected factory workbook.
3. Use Excel COM `CreateUpdate().AddRangeImage(...).Send()`.
4. Verify PowerPoint object geometry and rendered visibility.

Best lane for new chart families:

1. Use stock `.potx` as donor/reference material.
2. Copy the donor to `.pptx`.
3. Patch or author a real `m_strName` name for the target object.
4. Bind with `.ppttc`.
5. Keep the proof separate from production deck polish.

## What Not To Do

- Do not expect `AddRangeData` to create missing charts.
- Do not expect the boolean argument on `AddRangeData` to mean
  create-if-missing.
- Do not treat stock `.potx` templates as direct `.ppttc` templates.
- Do not treat `ppttc.exe` exit code 0 as success without package assertions.
- Do not use native editable think-cell tables in production until a real named
  table donor updates reliably.
- Do not invest in reverse-engineering `PresentationFromTemplateStep3` unless a
  product requirement forces it; `ppttc.exe` is the stable wrapper today.

## Recommended Architecture

Keep three layers separate:

1. Data layer: Salesforce and workbook facts with ARR/ACV guardrails.
2. Seed layer: named think-cell/chart/table-image surfaces with proof JSON.
3. Presentation layer: production-polished slides inserted only after render QA.

For the quarter decks, the best immediate use is:

- QTR04 Scatter as a production-polish pilot for eligible directors.
- QTR05 FY26 Renewal Gantt as a production-polish pilot for eligible directors.
- QTR06 Q2 Renewal Gantt only for Sarah Pittroff, Dan Peppett, and Christian
  Ebbesen.
- QTR10/QTR11/QTR12 table-image and hybrid lanes as the safe table/triage
  pattern.

## Probe Commands

VM status:

```bash
prlctl list -a
```

Full lab:

```bash
.venv/bin/python scripts/thinkcell_programmatic_lab.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --render
```

Windows bridge:

```bash
.venv/bin/python scripts/run_thinkcell_windows_bridge.py \
  --ppttc state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.ppttc \
  --template assets/LAND_thinkcell_seed.pptx \
  --output state/thinkcell_bridge/manual_probe/Jesper-Tyrer-bound.pptx \
  --expect-text "Jesper Tyrer" \
  --expect-text "2026-Q2"
```

Inspect latest API surface:

```bash
jq '.probe.capabilities, [.probe.powerpoint.members[]?.name], [.probe.excel.update_members[]?.name]' \
  state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json
```

## Hard SimCorp Constraints

- ARR is Land + Expand only and uses `APTS_Opportunity_ARR__c`.
- Renewal ACV is Renewal only and uses `APTS_Renewal_ACV__c`.
- Never blend ARR and Renewal ACV.
- Use explicit Type filters.
- Use converted EUR for leadership figures.
- Use eligibility gates before deciding which visual a director gets.
