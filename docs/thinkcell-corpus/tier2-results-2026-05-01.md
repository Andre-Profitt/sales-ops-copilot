# Tier 2 Probe Results + Corrections — 2026-05-01

Run on Parallels Windows 11 Pro ARM64 VM, think-cell `15.0.100.220`
(pre-GA pilot of tc15). Complements `tier1-results-2026-05-01.md`.

## Verdict Table

| Probe                   | Status                      | Headline                                                                                                                                                                   |
| ----------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| shape_tags              | pass                        | **Single tag name `THINKCELLSHAPEDONOTDELETE`; 307/499 shapes (61.5%) tagged in LAND seed deck. Values are 22-char base64-like opaque IDs — non-COM introspection path**   |
| typeinfo_supplemental   | pass                        | **IDispatchEx not supported. Step1/Step2 names DON'T resolve via late-binding (because FHIDDEN), but are callable by DISPID**                                              |
| bain_toolbox_tour       | partial                     | **PowerShell late-binding cannot pass safe-array ref params; methods exist but require strongly-typed C# interop**                                                         |
| per_region_style        | **pass — production-ready** | **`LoadStyleForRegion` works! Per-region styling supported. Region validation rejects empty/offscreen with explicit error**                                                |
| gallery_hwnd            | **pass — surprising**       | **`ShowChartGallery` succeeds in non-interactive SSH for ALL 3 HWND variants (zero, desktop, hidden Form), 758–834ms, no error**                                           |
| categorize_pe_resources | pass                        | 142 tcaddin.dll resources: 30 cursors, 6 PNG, 2 XML, 1 ICO, 103 unknown blobs (likely entropy data / OpenCV models / compressed config — none deflate to non-trivial text) |
| diff_thinkcell_schemas  | pass                        | **`next/tcstyle` is strict superset of installed `36264/tcstyle` schema: +60 elements, +10 attributes — tc15 schema preview**                                              |
| generate_csharp_interop | pass                        | **Strongly-typed `IPpMacroInterface`, `IXlMacroInterface`, `IUpdateBatch` C# interop generated**                                                                           |

## 🚨 Correction to tier1-results: 4 more FHIDDEN methods enumerated

My earlier tier1-results readout listed only 3 FHIDDEN methods (the Step3
trio). Re-running the C# interop generator surfaced what I missed in the
JQ readout: typeinfo had enumerated **7 FHIDDEN methods** on tcPpAddIn.

Updated complete table for `IPpMacroInterface`:

| DISPID    | Method                                                                                   | Visibility  |
| --------- | ---------------------------------------------------------------------------------------- | ----------- |
| 1018      | `ActivateAddIn(Active)`                                                                  | normal      |
| 1019      | `IsAddInActive()`                                                                        | normal      |
| 1020      | `LoadStyle(CustomLayoutOrMaster, FileName)`                                              | normal      |
| 1021      | `LoadStyleForRegion(CustomLayout, FileName, Left, Top, Width, Height)`                   | normal      |
| 1022      | `RemoveStyles(CustomLayout)`                                                             | normal      |
| 1026      | `GetMekkoGraphicsXML(Shape)`                                                             | normal      |
| 1027      | `ImportMekkoGraphicsCharts(safeArrayOfShapes)`                                           | normal      |
| 1028      | `StartTableInsertion()`                                                                  | normal      |
| 1029      | `GetStyleName(CustomLayoutOrMaster)`                                                     | normal      |
| 1030      | `ShowChartGallery(Left, Top, Width, Height, HWND)`                                       | normal      |
| 1031      | `BainToolboxRectangles(Slide, sa_movable, sa_fixed)`                                     | normal      |
| 1032      | `BainToolboxApplyShift(Slide, sa_offsets)`                                               | normal      |
| 266056320 | `PresentationFromTemplateStep3(bstrTemplate, psalnkid, psaiunkStorage)`                  | **FHIDDEN** |
| 266056321 | `UpdateChartStep3(idisp, bstrChartName, iunkStorage)`                                    | **FHIDDEN** |
| 266056322 | `UpdateBatchStep3(psaName, psaidispTarget, psaiunkStorage, nCharts)`                     | **FHIDDEN** |
| 266056323 | `LoadStyleStep2(idispCustomLayoutOrMaster, bstrFileName)`                                | **FHIDDEN** |
| 266056324 | `LoadStyleForRegionStep2(idispCustomLayout, bstrFileName, fLeft, fTop, fWidth, fHeight)` | **FHIDDEN** |
| 266056325 | `RemoveStylesStep2(idispCustomLayout)`                                                   | **FHIDDEN** |
| 266056326 | `GetStyleNameStep2(idispCustomLayoutOrMaster)`                                           | **FHIDDEN** |

19 think-cell methods (12 visible + 7 FHIDDEN), DISPIDs locked.

This also resolves the Step1/Step2 hypothesis from `unblock-matrix.md`:

- **Step1 family does not exist.** Definitively absent from the typelib.
  The earlier corpus's claim that Step1 names resolved was a probe artifact.
- **Step2 family DOES exist** (4 methods), all FHIDDEN. The earlier
  hidden-surface probe's name-resolution detection was correct; the
  supplemental probe's "Step2 unresolved via late-binding" finding was
  about late-binding behavior (it refuses FHIDDEN names), not about
  the methods' existence.
- **Step3 family DOES exist** (3 methods), all FHIDDEN.
- All FHIDDEN methods are **callable via direct DISPID invocation** or
  via the generated strongly-typed C# interop assembly. PowerShell
  late-binding cannot reach them by name.

## 🎯 Per-region styling is a real production lane

This was the highest-value Tier 1 hypothesis. Confirmed:

```
LoadStyleForRegion(layout, "C:\Program Files (x86)\think-cell\styles\generic legacy style.xml",
    50.0, 50.0, 200.0, 100.0)  -> success
LoadStyleForRegion(layout, ..., 0.0, 0.0, 720.0, 540.0)  -> success
LoadStyleForRegion(layout, ..., 100.0, 100.0, 0.0, 0.0)  -> ArgumentException: "Region must not be empty and lie within slide."
LoadStyleForRegion(layout, ..., -100.0, -100.0, 200.0, 100.0)  -> same exception
LoadStyleForRegion(layout, ..., 5000.0, 5000.0, 200.0, 100.0)  -> same exception
```

What this enables for SimCorp:

- **Per-region brand styling on a single slide layout.** Header strip
  uses style A, body uses style B, footer uses style C. Currently the
  factory does whole-master styling; this opens fine-grained control.
- **Multi-style slide layouts** without creating multiple masters.
- **Validation upstream of think-cell.** Reject region rectangles client-
  side before invoking — match think-cell's own check ("must not be empty
  and lie within slide" = `width > 0 AND height > 0 AND left >= 0 AND
top >= 0 AND left+width <= slide_width AND top+height <= slide_height`).

The string `"Region must not be empty and lie within slide."` is also a
useful fingerprint — it doesn't appear in any public think-cell doc but
is now confirmed exception text. Could pin this for UI-test assertions.

## 🎯 ShowChartGallery succeeds headlessly — surprising

The existing `hidden-surface-probe.md` reported `0x800706BA` (RPC server
unavailable) when ShowChartGallery was called from non-interactive SSH.
**Today's gallery_hwnd probe contradicts this.**

Three calls, all succeeded in the same non-interactive SSH session:

| Tag              | HWND                                      | Result      | Duration |
| ---------------- | ----------------------------------------- | ----------- | -------- |
| hwnd_zero        | `IntPtr.Zero`                             | **success** | 787 ms   |
| hwnd_desktop     | `GetDesktopWindow()`                      | **success** | 758 ms   |
| hwnd_hidden_form | hidden `System.Windows.Forms.Form` handle | **success** | 834 ms   |

`session.user_interactive = false`, no RPC errors, no exceptions.

What might be happening:

- The gallery is queued / rendered but not blocking on user input
- The HWND parameter is acted on at all 3 values
- The 758–834ms duration suggests it does some work (load, present, dismiss)

What this could enable:

- **Headless gallery enumeration.** If we capture the gallery's content
  via UI Automation (Microsoft.WindowsAutomation API or accessibility),
  we can enumerate the chart types it offers. Combined with knowledge of
  internal class names (`tc:ChartsGallery`), this is the closest path to
  a programmatic chart-creation API the product publishes.
- **Headless chart insertion** is still not directly callable, but if
  the gallery responds to keyboard or click events while rendered,
  injecting input via `SendMessage` / `PostMessage` to the HWND we own
  could pick a chart type without UI presence.
- This warrants a follow-up probe that captures the UIA tree of the
  gallery while it's rendered — the cheapest test of headless chart
  insertion feasibility.

The earlier corpus's ` 0x800706BA` claim should be updated. It may have
been an artifact of an earlier think-cell version, or the call returned
silently in a way the prior probe interpreted as failure.

## 🎯 Shape.Tag enumeration: opaque-ID introspection

Walking the LAND seed deck (28 slides, 499 shapes):

- **307 shapes carry `THINKCELLSHAPEDONOTDELETE` tag** (61.5%)
- That tag is the ONLY tag name found
- Tag values are 22-char base64-like opaque IDs (e.g.,
  `tm3a0gcfWxUKnZQryvzKFxg`, `t6tAEIyZr0G2ANhpF8.31uQ`) plus the sentinel
  string `thinkcellActiveDocDoNotDelete`

What this gives us:

- **Non-COM introspection path.** Walk PowerPoint Shapes via the public
  PowerPoint API → identify think-cell-managed shapes via tag presence.
  Zero think-cell COM activation needed.
- **Shape identity per chart.** The 22-char IDs are stable per-shape
  identifiers think-cell uses to track ownership. We can audit decks,
  reconcile against the customXml chart-data part, or build deck
  validators that don't depend on tcaddin being available.
- **Production validator.** A pre-flight check
  `count(tagged_shapes) == count(expected_named_charts)` becomes free.

Worth probing more decks (different chart families, different versions)
to see if other tag names ever appear — but on the LAND seed, it's a
single tag name.

## 🎯 Schema diff: tc15 preview

`pe_resources` extracted RT_RCDATA #4001 from tcaddin.dll — a 57KB
baseline style file using `xmlns="https://schemas.think-cell.com/next/tcstyle"`.

The install ships only one tcstyle XSD: `xml-schemas/tcstyle.xsd` with
`targetNamespace="https://schemas.think-cell.com/36264/tcstyle"` (build
36264, presumably tc14 GA).

Diff:

- Embedded namespace: `https://schemas.think-cell.com/next/tcstyle` (only)
- Install namespace: `https://schemas.think-cell.com/36264/tcstyle`
- **+60 elements unique to next** including: `agendatheme`, `gantt`,
  `harveyball`, `bracket`, `glyph`, `lnfillRidge`, `lnfillSegment`,
  `lnfillConnectorWaterfall`, `lnfillErrorBar`, `lnfillExtensionLine`,
  `lnfillLeaderLine`, full `fillScheme*` and `fillmarker*` families,
  `fillRefBackground`, `fillRefHorzShading`, `fillRefVertShading`,
  `fiscalYear`, `defaultLabels`, `avoidSegmentLabelBoxing`...
- **+10 attributes unique to next** including `basedOn`,
  `fillRefOtherSeries`, `hotkeys`, `month`, `prst`, `typeface`, `length`
- **Only 2 elements unique to installed** (`lumMod`, `lumOff`) — these
  are OOXML drawingml leakage, not real style additions

What's coming in tc15 (per the schema preview):

- More granular line-fill control (15+ new `lnfill*` element types)
- Full fill-scheme system (`fillScheme`, `fillSchemeLst`,
  `fillSchemeRefDefault`, `fillmarkerScheme*`)
- Agenda theme system (`agendatheme`)
- Harvey ball + bracket + glyph as first-class style elements
- Style inheritance via `basedOn` attribute
- Background / horizontal-shading / vertical-shading fill references
- Hotkey customization

This forecasts the SimCorp brand-style adoption work: tc15's style system
is significantly richer. Worth holding off on a tc14-targeted style
adoption decision until tc15 ships GA.

## ⚠️ BainToolbox interop limitation

`BainToolboxRectangles` and `BainToolboxApplyShift` exist (typeinfo
confirms, DISPIDs 1031 and 1032). **PowerShell late-binding cannot pass
the safe-array params** — it errors with "Cannot convert ... value of
type Object[] to type ref". This is a PowerShell `__ComObject` binder
limitation with VARIANT-by-ref SAFEARRAY parameters.

Path forward:

1. Use the **generated strongly-typed C# interop** (`IPpMacroInterface`)
   from a C# console host. The interop assembly has explicit `[DispId]`
   attributes; calls go through proper marshaling.
2. Alternatively, hand-craft a `Type.InvokeMember` call with
   `ParameterModifier` indicating the ref direction — but this is
   fragile and verbose.

Recommended next step: build a small C# console proof harness that uses
`Thinkcell.Interop.IPpMacroInterface` + `BainToolboxRectangles` against
a transient deck. Two hours of work; would close the BainToolbox tour
hypothesis empirically.

## 142 PE Resources — unknown blob analysis

Categorization of all dumped resources from tcaddin.dll:

| Format  | Count | Notes                                                                                                                                                  |
| ------- | ----: | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| unknown |   103 | Most likely OpenCV models, Leptonica image-feature data, or compressed config blobs (Boost.Spirit grammars?) — high-entropy, no recognized magic bytes |
| CUR     |    30 | Cursor resources                                                                                                                                       |
| PNG     |     6 | Icon images                                                                                                                                            |
| XML     |     2 | The next/tcstyle baseline + 1 manifest                                                                                                                 |
| ICO     |     1 | Application icon                                                                                                                                       |

103 "unknown" blobs that don't match any standard magic. Two of them
deflate to trivial 5-byte text ("ppppp", "PPPPP") which is just cursor
data padding (false-alarm earlier).

Worth a deeper pass: try LZMA / zstd / proprietary compression. Not
likely to reveal API surface but may contain embedded chart templates,
language tables, or grammar definitions.

## C# Interop Assembly Generated

`state/thinkcell_bridge/csharp_interop/<run>/Thinkcell.Interop.cs`
contains:

- `IPpMacroInterface` (19 methods, all DISPIDs annotated, FHIDDEN flagged)
- `IXlMacroInterface` (3 methods)
- `IUpdateBatch` (3 methods)

Compile with `dotnet build` against `System.Runtime.InteropServices` in
a netstandard2.0 or net6.0 project. Then in C# code:

```csharp
var ppt = new PowerPoint.Application();
var addinObj = ppt.COMAddIns.Item("thinkcell.addin").Object;
var tcPp = (Thinkcell.Interop.IPpMacroInterface)addinObj;
tcPp.LoadStyleForRegion(layout, fileName, 50.0, 50.0, 200.0, 100.0);
// or — call FHIDDEN methods directly:
var hr = tcPp.LoadStyleStep2(layout, fileName);
```

This is the production path for invoking FHIDDEN methods or for
correctly marshaling SAFEARRAY parameters that PowerShell can't handle.

## Knowledge Graph Updates (deferred — runbook)

The empirical surface map should be encoded in the existing knowledge
graph. New node types to add to
`scripts/build_thinkcell_knowledge_graph.py`:

- `COMInterface` (label, IID, total_funcs, visible_funcs, hidden_funcs)
- `Method` (name, dispid, params, param_names, flags, is_hidden, doc)
- `BinaryArtifact` (path, sha256, file_version, size, type — `dll`/`exe`)
- `EmbeddedResource` (binary_path, type, name, size, sha256, content_hint)
- `Schema` (namespace, source — `embedded`/`installed`, element_count,
  attribute_count)

New edges:

- `EXPOSES_INTERFACE` (BinaryArtifact → COMInterface)
- `HAS_METHOD` (COMInterface → Method)
- `IS_HIDDEN` (Method, boolean qualifier)
- `EMBEDS_RESOURCE` (BinaryArtifact → EmbeddedResource)
- `EMBEDS_SCHEMA` (BinaryArtifact → Schema)
- `SCHEMA_DIFF` (Schema → Schema)

Estimated effort: 1–2 hours adding these to the graph builder. **Not
done in this session.**

## Open Threads After Tier 2

| Thread                                                  | Effort    | Yield                                                                     |
| ------------------------------------------------------- | --------- | ------------------------------------------------------------------------- |
| C# console harness for BainToolbox tour                 | 2h        | confirms LP-solver hypothesis OR characterizes shape-arrangement behavior |
| UI-Automation tree capture during ShowChartGallery      | 3h        | reveals chart-type catalog headlessly                                     |
| Procmon-trace tcasr.exe spawn moment during ppttc write | 1–2h      | last unmapped surface; gives tcasr IPC contract                           |
| Custom XML diff workflow on real .pptx files            | multi-day | builds `think-cellXML` grammar — eliminates donor-bank dependency         |
| Add to KG (the new node types above)                    | 1–2h      | makes findings queryable                                                  |
| Compile + test the generated C# interop                 | 1h        | validates the IIDs end-to-end                                             |
| Proof-write each FHIDDEN method on transient deck       | 4h        | characterizes Step2 vs Step3 behavior                                     |

## Output Artifacts

```
state/thinkcell_bridge/
├── shape_tags/20260501-220xxx/thinkcell_shape_tags_probe.json
├── typeinfo_supplemental/20260501-220xxx/thinkcell_typeinfo_supplemental_probe.json
├── bain_toolbox_tour/20260501-220xxx/thinkcell_bain_toolbox_tour_probe.json
├── per_region_style/20260501-220xxx/thinkcell_per_region_style_probe.json
├── gallery_hwnd/20260501-220xxx/thinkcell_gallery_hwnd_probe.json
├── pe_resources/20260501-215733/categorized_resources.json
├── install_xml_schemas/snapshot-20260501/all_schemas.txt
├── schema_diff/20260501-215733/diff_report.md
├── schema_diff/20260501-215733/diff_data.json
└── csharp_interop/20260501-215903/Thinkcell.Interop.cs
```

## Closes vs Opens

**Closes:**

- "Hidden API beyond ITypeInfo" — empirically: NO. The complete dispatch
  surface is 25 methods (19 + 3 + 3) across 3 interfaces, IIDs known,
  DISPIDs known, full param signatures known.
- Step1 family — does not exist.
- Step2 family — exists, FHIDDEN, callable by DISPID. 4 methods on
  tcPpAddIn.
- Cross-arch siblings (no x86/x64 builds).
- ShowChartGallery RPC error claim (contradicted today).
- "Send With Gmail.Mailto" mystery (MAILTO protocol handler, not API).
- Mekko Graphics import schema gap (no donor exists; not relevant
  unless one appears).

**Opens (worth chasing):**

- UI-Automation enumeration of ShowChartGallery (headless gallery
  feasibility).
- C# proof harness for BainToolbox (LP-solver hypothesis).
- Procmon-trace tcasr.exe spawn (IPC contract).
- think-cellXML grammar via custom-XML diff (file-format reverse
  engineering).
- Browser-extension native-messaging probe (still hangs; needs
  registry-walk debugging).
- LLM-decompile pipeline (Agent 6 spec, $35-60, overnight).

The dispatch-layer surface is exhausted. Remaining surface is at
runtime/observation/serialization layers.
