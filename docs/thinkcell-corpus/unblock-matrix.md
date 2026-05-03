# think-cell Unblock Matrix

Date: 2026-05-01

This file separates three different meanings of "unblocked":

- Direct API unblocked: the think-cell/Office API exposes the capability and the
  SimCorp VM proof invoked it successfully.
- Factory unblocked: the monthly deck factory can deliver the business outcome
  through a proven donor, `.ppttc`, or Excel COM lane even if there is no direct
  creation API.
- Hard blocked: the platform or installed API surface forbids the capability.

## Current Verdict

| Lane | Factory status | Direct API status | Verdict |
|---|---:|---:|---|
| Native think-cell Mekko for SimCorp deck visuals | Unblocked | n/a | Use QTR07 sparingly when stage/industry or motion mix is genuinely dense. |
| Mekko Graphics import | Blocked | Blocked by missing donor | Only relevant for legacy Mekko Graphics-authored PPTX files. No sample exists in the VM. |
| Native editable think-cell tables | Blocked | Blocked | Do not use for production. Use Excel COM `AddRangeImage` table-image lane. |
| Office Web Add-ins | Hard blocked | Hard blocked | Use a local/VM bridge; do not plan around Office Web Add-ins reaching think-cell COM. |
| Programmatic chart creation | Functionally unblocked by donors | Not found | Use donor-and-rename / `.ppttc`; no `Create*Chart` or `Insert*Chart` COM method exists. |
| `tcserver.exe` HTTP service | Optional proof candidate | Observed, uninvoked | Inventory is done. Starting/registering it requires an explicit admin/server decision. |
| Style API | Unblocked for transient proof | Unblocked | Proven on a transient deck; SimCorp production style adoption needs a brand-style decision record. |

## Lane Notes

### Native think-cell Mekko

The SimCorp deck-factory Mekko use case is already unblocked through native
think-cell donor binding:

- Proof: `state/thinkcell_bridge/build_scaffold/2026-Q2/work/QTR07_StageIndustry_Mekko/QTR07_StageIndustry_Mekko-proof.json`
- Status: `pass`
- Bound deck: `state/thinkcell_bridge/build_scaffold/2026-Q2/work/QTR07_StageIndustry_Mekko/QTR07_StageIndustry_Mekko-2026-Q2-bound.pptx`

Do not confuse this with the Mekko Graphics import API. The latter imports
legacy Mekko Graphics charts into think-cell; it is not required for native
think-cell Mekko charts in the monthly factory.

### Mekko Graphics Import

Official surface:

- `tcPpAddIn.ImportMekkoGraphicsCharts(Shape[])`
- `tcPpAddIn.GetMekkoGraphicsXML(Shape)`

Current blocker: no real Mekko Graphics-authored PowerPoint donor exists in the
VM sample paths. The installed think-cell library has native think-cell Mekko
templates, but those are not Mekko Graphics charts.

Unblock gate:

1. Put a real legacy Mekko Graphics PPTX under
   `state/thinkcell_bridge/mekko_samples/`.
2. Run a PowerPoint COM probe that invokes `ImportMekkoGraphicsCharts`.
3. Assert that a backup slide is created, a native think-cell replacement exists,
   and `GetMekkoGraphicsXML` returns XML for the original shape.

Until that donor exists, this is correctly blocked and should not consume sprint
time.

### Native Editable think-cell Tables

The native editable table lane is still blocked. Earlier package and UI probes
showed that table objects expose `TCLayout` / `CSmartGrid` state, but not a
reliable named data-binding surface. Raw `m_strName` injection into table
payloads caused PowerPoint/think-cell repair prompts or broken sizing.

Production lane:

- Use Excel COM `CreateUpdate().AddRangeImage(...).Send()` for table-shaped
  artifacts.
- Treat the result as a linked table image, not a native editable think-cell
  table.

Evidence:

- Hybrid proof: `state/thinkcell_bridge/build_scaffold/2026-Q2/work/QTR12_StalePipeline_BarTable/QTR12_StalePipeline_BarTable-proof.json`
- Linked workbook: `state/2026-Q2/Jesper-Tyrer/factory/connected/connected_factory_table_images.xlsx`
- Linked deck: `state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2-table-image-linked.pptx`

Reopen this only if a human creates one real data-backed, named native think-cell
table donor that updates from Excel without repair prompts.

### Office Web Add-ins

Hard platform block. The official think-cell API is a Windows desktop COM API,
and Office Web Add-ins cannot interact with Office COM add-ins.

Usable unblock architecture:

- Web/UI layer submits a job to a local Windows VM worker.
- VM worker runs PowerPoint/Excel COM, `ppttc.exe`, or a future approved
  `tcserver.exe` service.
- Output PPTX returns to the web/UI layer.

Do not attempt a pure Office Web Add-in think-cell integration.

### Programmatic Chart Creation

Direct arbitrary chart creation remains unavailable. The probed COM surface does
not expose a `Create*Chart` or `Insert*Chart` method.

The hidden-surface probe also found no callable constructor. It scanned
`tcaddin.dll`, generated 3,200 candidate names, and checked them with
`IDispatch.GetIDsOfNames`. Internal ribbon strings such as `tc:ChartsGallery`,
`tc:Table`, `tglbtnWaterfall_onAction`, and
`CXlApplication::InsertChartToData` exist, but they returned
`DISP_E_UNKNOWNNAME` when checked against the public add-in objects.

Factory outcome is still unblocked through the donor bank:

- Copy native chart/donor object graphs from the SimCorp seed or stock `.potx`.
- Name the think-cell payload safely.
- Bind data with `.ppttc` or Excel COM.
- Render and assert the output.

This is how the current 12 quarter contracts reached L5 proof.

### `tcserver.exe`

`tcserver.exe` exists and is inventoried:

- Path: `C:\Program Files (x86)\think-cell\tcserver.exe`
- Version: `15.0.100.220`

It was not started or registered. That is intentional. First start can require
URL registration / UAC and changes the runtime architecture from local CLI/COM
to server mode.

Unblock gate:

1. Make an explicit decision to run a local HTTP render service.
2. Start/register `tcserver.exe` on the VM.
3. POST a known `.ppttc` payload with MIME
   `application/vnd.think-cell.ppttc+json`.
4. Compare output against the existing `ppttc.exe` bridge proof.

This is optional; it is not needed to complete the local monthly deck factory.

## Stop Rules

- Do not chase native editable think-cell tables until a clean manual donor
  exists.
- Do not plan around Office Web Add-ins for think-cell automation.
- Do not assume `.ppttc` can create missing chart objects; the named element
  must already exist in the template.
- Do not start/register `tcserver.exe` from unattended automation.
- Do not blend ARR and Renewal ACV in any chart, table, bridge, or KPI strip.

## Source Anchors

- Official API entry point: <https://www.think-cell.com/en/resources/manual/api>
- JSON Data Automation: <https://www.think-cell.com/en/resources/manual/jsondataautomation>
- Excel Data Automation: <https://www.think-cell.com/en/resources/manual/exceldataautomation>
- Mekko Graphics import: <https://www.think-cell.com/en/resources/manual/import-mekko-graphics>
