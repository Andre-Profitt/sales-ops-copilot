# Handoff — programmatic think-cell template wiring

**For:** a frontier-tier GPT/Claude session, no prior context.
**Date:** 2026-04-30 late evening
**Author of this handoff:** Claude Opus 4.7 (1M context). Operator: Andre (apro@simcorp.com).
**Repo:** `~/code/apps/sales-ops-copilot/` on `main` (56 commits ahead of origin/main; do not push).
**Windows VM:** Parallels, hostname `TESTB04E`, accessible from Mac via `ssh Windows-VM`. Trial expires ~2026-05-13.

## Codex continuation update

After this handoff was written, Codex found and verified a programmatic seed path
for native think-cell charts and automation text fields:

- Builder: `scripts/build_thinkcell_seed_template.py`
- CFB patch helper: `scripts/thinkcell_cfb.py`
- Seed artifact: `assets/LAND_thinkcell_seed.pptx`
- Status doc: `docs/THINKCELL_SEED_TEMPLATE.md`

The seed contains the full 42-name contract and passes strict `.ppttc` generation
plus Windows `ppttc.exe` execution. The native chart objects bind real data; the
eight table names are currently off-slide automation text-field stubs, not native
think-cell tables.

Codex also built the current production deck path:

- Batch builder: `scripts/build_land_presentation_decks.py`
- Merge helper: `_windows_test/merge_charts_into_layout.ps1`
- Command: `.venv/bin/python scripts/build_land_presentation_decks.py --period 2026-Q2 --skip-seed`
- Output: `state/2026-Q2/<Director>/<Director>-LAND-2026-Q2.pptx`

This path binds `assets/LAND_thinkcell_seed.pptx` through Windows `ppttc.exe`,
then uses PowerPoint COM to merge the native think-cell chart shapes into the
branded LAND layout deck. All 9 2026-Q2 director decks passed final validation:
28 slides, 24 embedding parts, expected director/period text present, and no
donor boilerplate sentinel text.

Native think-cell table creation/naming was also probed more deeply and remains
blocked. The useful installed table donors and a ribbon-created table expose
`TCLayout` / `CSmartGrid` OLE state but no `m_strName`, datasheet, range-link, or
AddRangeData-name surface. Raw `m_strName` injection into `CSmartGrid` /
`CContainerSE` wedges `ppttc.exe`. Live UIA probes of the table mini toolbar,
right-click menus, selected table cells, and selected element ranges did not
surface `Open Datasheet` or `AddRangeData Name`.

Current practical path: use the batch builder above. It gives presentation-ready
LAND decks with native think-cell chart objects and generated PowerPoint tables.
Only revisit native think-cell tables if a real manually named data-backed
think-cell table donor becomes available.

## Mission

We have a working data pipeline that emits `.ppttc` (think-cell JSON automation) per director. The
pipeline is blocked on **one structural step**: getting a fully named think-cell automation surface
into a PowerPoint template (`assets/LAND_template.pptx`). The current emitter produces 42 named
payload entries per director; the manually wired template needs matching named elements for those
entries, including chart/table objects, text-linked cells, KPI notes, and footnotes. With the named
elements present, every monthly refresh cycle is fully automated by `ppttc.exe` (proven,
5 sec/director). Without them, ppttc.exe runs but injects no data — the template has nothing to bind
to.

**Your job:** find a programmatic path to seed those named elements, OR prove definitively (with new
evidence I missed) that no such path exists. If you confirm no path exists, the fallback is a
~30-min manual UI wire on the VM that the operator will perform.

I have **exhausted what I can find** with the tools at my disposal. I'm asking a stronger model
because I may have missed an angle in:

- think-cell's actual COM/automation documentation (I did not have web access to search think-cell's KB articles)
- direct OOXML structural authoring (I tried it via Codex's donor-chart approach which is broken; a smarter author might fix it)
- the third SAFEARRAY parameter of `PresentationFromTemplateStep3` which I never decoded
- VBA-level integration (I probed PowerShell COM but not VBA-inside-PowerPoint)
- the now-confirmed local think-cell docs/templates/ppttc samples (listed below but not deeply analyzed)

## Why this matters

This is a SimCorp internal Sales Director Monthly LAND review pipeline. Once unblocked, monthly
production cycles drop from a multi-day manual click-fest to a 5-minute fully-automated job for 9
directors. The data plumbing (Salesforce → Excel models → JSON envelope → think-cell JSON) is
already built and tested; only the template-wiring gate is blocking real-world use.

## Current state — what works, what doesn't

### Works (validated end-to-end)

- `scripts/build_ppttc.py` emits valid `.ppttc` JSON for any director from per-director
  `state/2026-Q2/<Director>/{land.model.xlsx, land.xlsx, trends.json, brief.md}`.
- 9 director-specific data envelopes are real and contract-validated
  (`scripts/validate_workbook_contract.py`, 9/9 green).
- `ppttc.exe` (Windows) accepts the emitted JSON, parses it, and round-trips a PPTX.
- Excel-side think-cell COM addin is reachable, callable, and exposes `CreateUpdate()`,
  `AddRangeData(...)`, `Send()`, `PresentationFromTemplate(...)`.
- PowerPoint-side addin is reachable via `Application.COMAddIns("thinkcell.addin").Object` and
  exposes `UpdateChartStep3`, `UpdateBatchStep3`, `PresentationFromTemplateStep3`, `LoadStyle`,
  etc.
- Brand style file `assets/SimCorp-thinkcell-style.xml` is valid (loads fine in interactive
  PowerPoint).

### Doesn't work (the blocker)

- The 28-slide `assets/LAND_template.pptx` has **zero** named think-cell automation elements. It has
  PowerPoint placeholder rectangles (`Content Placeholder 1`, `Text Placeholder 2`, etc.) and
  literal `{director_name}`/`{period}`/`{scope_label}` text tokens.
- `ppttc.exe` runs against this template and exits 0, but produces a PPTX byte-equivalent to the
  input (only rels/media renumbering changes). No data is bound. No charts are created.
- Codex's donor-chart-injection approach (`scripts/ppttc_template.py:_inject_donor_charts`) fails
  on **both Mac and Windows** — confirmed with HRESULT 0x80070570 ("file is corrupted and
  unreadable") on Windows COM open, and `"The .ppttc file is bad. The template failed to load."`
  on ppttc.exe. The donor-injected PPTX has 24 OLE embeddings + 200+ tag XML files but think-cell
  refuses to parse it. Cause: malformed LiteDB blob in `ppt/tags/tag1.xml` and/or
  shape↔tag↔rel inconsistencies. Codex's prior audit explicitly recommended NOT pursuing further.

## The 42-name contract

The emitter (`scripts/build_ppttc.py:_ppttc_entries_from_context`) produces 42 named payload
entries for all 9 current directors (verified 2026-04-30 with the project venv). The template's
named elements must match these names exactly:

```
S01_DirectorName
S01_Period
S01_ScopeLabel
S02_ExecSummaryLeft
S02_ExecSummaryRight
S04_PipeMovement
S05_PipelineByStage
S06_PipelineAging
S07_TopDealsLand
S08_TopDealsExpand
S09_PendingCommercialApproval
S11_RenewalPipeline
S12_GRRProxyFootnote
S12_GRRProxyTable
S13_ForecastCategory
S15_ByOwner
S16_StageByIndustry
S17_TerritoryPerformance
S18_WinsLossesQTD
S19_Velocity
S21_ConcentrationRiskChart
S21_ConcentrationTable
S21_LargestAccount
S21_LargestArr
S21_LargestShare
S21_ThresholdFlag
S22_StaleActivity
S22_StaleActivityFootnote
S23_AvgCycleDaysNote
S23_AvgCycleDaysValue
S23_AvgDealSizeNote
S23_AvgDealSizeValue
S23_OpenOppsNote
S23_OpenOppsValue
S23_VelocityNote
S23_VelocityValue
S23_WinRateNote
S23_WinRateValue
S24_AccountExpansion
S25_PipelineCreationVelocity
S26_ActionItems
S27_RisksOutlook
```

Mix of think-cell chart types: waterfall (S04), bar (S05/S06/S15/S22), table (S07/S08/S09/S11/S12/S24/S26), mekko (S16),
combo bar+line (S19/S25), 100%-stacked (S21), grouped column (S18), text-linked (S01/S02/S23/S27).
Full slide-by-slide binding spec: `docs/WIRING_QUICKREF.md`.

## The COM API surface (decoded)

Probed via PowerShell on the Windows VM. Two distinct addins, different methods:

### Excel side: `xlApp.COMAddIns["thinkcell.addin"].Object`

```
CreateUpdate() -> IDispatch                        // returns Update builder
PresentationFromTemplate(IDispatch, string, IDispatch) -> IDispatch
    // (workbook, templatePath, pptApplication) -> Presentation
    // Note: error msg confirms 3rd arg is "PowerPoint._Application object"
UpdateChart(IDispatch, string, IDispatch, bool) -> void
    // (slideOrPres, chartName, range, ?)
```

### Update object (returned by `CreateUpdate()`)

```
AddRangeData(IDispatch, string, IDispatch, bool) -> void
    // (target, name, range, ?)
    //   target: must be PPT.Presentation, Slide, CustomLayout, Master, or SlideRange
    //   name: chart name (string)
    //   range: must be Excel.Range
    //   bool: NOT "create-if-missing" — confirmed empirically
AddRangeImage(IDispatch, string, IDispatch) -> void
Send() -> void
    // commits the batch; errors with exact missing-name list if names not found
```

### PowerPoint side: `pptApp.COMAddIns["thinkcell.addin"].Object`

```
ActivateAddIn(bool)
GetStyleName(IDispatch), GetStyleNameStep2(IDispatch) -> string
LoadStyle(IDispatch, string)             // load brand style XML
LoadStyleStep2(IDispatch, string)
LoadStyleForRegion / Step2(IDispatch, string, float, float, float, float)
RemoveStyles / Step2(IDispatch)
PresentationFromTemplateStep3(string, byte[], ???) -> IDispatch  // ppttc.exe wraps this
UpdateChartStep3(IDispatch, string, IUnknown)
UpdateBatchStep3(string[], IDispatch[], IDispatch[])
ImportMekkoGraphicsCharts(IDispatch[]) -> IDispatch  // creates Mekko from XML — chart-type-specific!
ShowChartGallery(int, int, int, int, int) -> bool   // UI dialog only
StartTableInsertion()                                // begins table insertion (UI-coupled?)
GetMekkoGraphicsXML(IDispatch) -> string
BainToolboxApplyShift / BainToolboxRectangles        // Bain custom, irrelevant
IsAddInActive() -> bool
```

**Critical observation:** `ImportMekkoGraphicsCharts` is the ONLY method that takes an array of
inputs and returns chart objects — it CREATES charts from MekkoGraphics XML. **This suggests
think-cell can construct chart shapes from XML, just for the Mekko type.** No equivalent
`ImportXxxCharts` for waterfall, bar, table, etc. is exposed.

## What I tried — full evidence trail

All test scripts are in `_windows_test/`. Each is re-runnable via:

```bash
ssh Windows-VM 'powershell -NoProfile -ExecutionPolicy Bypass -File "\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\<scriptname>.ps1"'
```

### 1. Base smoke (`_windows_test/run_test.ps1`)

`ppttc.exe LAND_template.pptx Jesper-Tyrer-LAND-2026-Q2.ppttc -o output.pptx` → exit 0, 0B
stderr, output PPTX produced. **But:** byte-equivalent to template (only rels/media renumbering
differs). Cover placeholders untouched. No new embeddings/tags. Conclusion: ppttc.exe processed
clean, but the template had zero named automation elements for it to bind to.

### 2. Donor-template test (`_windows_test/run_donor_test.ps1`)

Generated donor template via
`python3 scripts/build_ppttc.py --director "Jesper Tyrer" --period 2026-Q2 --experimental-generated-template`
which produces `state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2-template.pptx` (9.4 MB,
24 OLE embeddings, 200+ tag XML files via `scripts/ppttc_template.py:_inject_donor_charts`).

Result: `ppttc.exe` exits 1 with `"The .ppttc file is bad. The template failed to load."` Same
error Codex saw on Mac. Confirmed not platform-specific.

Stage-2 attempt (`_windows_test/test_addrangedata_donor.ps1`): tried opening the donor template
via the COM `PresentationFromTemplate` API directly. Failed with HRESULT 0x80070570 "file is
corrupted and unreadable." So the donor template is structurally bad, full stop.

### 3. COM API decoding (`_windows_test/probe_*.ps1`, `test_addrangedata_v[123].ps1`)

Probed all method signatures via .NET reflection on the COM IDispatch surfaces. Discovered the
full method list above. Tested `AddRangeData` with multiple argument-order permutations against
multiple target types until error messages converged on the correct API shape:

```
AddRangeData(target, name, range, bool)
  target ∈ {Presentation, Slide, CustomLayout, Master, SlideRange}
```

### 4. Definitive test (`_windows_test/test_addrangedata_v3.ps1`)

Boot Excel + workbook, boot PowerPoint via COM, call
`tc.PresentationFromTemplate(wb, "C:\tcw\LAND_template.pptx", ppt)` → returns valid
`Presentation1` with 28 slides. Call
`update.AddRangeData(slide4, "S04_PipeMovement", range, $true)` → no exception. Call
`update.Send()` → **fails with**:

```
PowerPoint elements with the following names were not found: s04_pipemovement.
```

Slide 4 still has only its 5 original placeholder shapes — no chart was created. **Definitively
confirms the bool flag is NOT "create-if-missing."** AddRangeData strictly requires the named
shape to pre-exist.

### 5. Application.Run() probe (`_windows_test/probe_excel_addin.ps1`)

Tried invoking documented function names via `xlApp.Run("...")`:
`ThinkCellInsertChart`, `tcInsertChart`, `ThinkCellAddDataRange`, `tcAddDataRange`,
`AddDataRange`, `InsertChart`, `ThinkCellLinkToPowerPoint`, `tcLinkToPowerPoint`. **All failed
with "Cannot run the macro."** No legacy VBA-callable function names work via this path.

## What's definitively ruled out

- **Donor-chart OOXML injection (Codex's approach)**: produces a structurally-corrupt PPTX that
  PowerPoint COM refuses to even open. Codex's audit said "stop" — confirmed twice now.
- **`AddRangeData` chart creation via the bool flag**: the flag is NOT "create-if-missing."
  Empirically, Send() errors with the missing-name message when the shape doesn't pre-exist.
- **`Application.Run` of legacy VBA names**: none registered.
- **AppleScript driving Mac PowerPoint**: dead — see `docs/RESEARCH_APPLESCRIPT_THINKCELL.md`.
- **PowerShell ARM64 direct COM activation of `thinkcell.addin`**: HRESULT 0x800700C1 (wrong
  arch). Workaround: route through PowerPoint/Excel `COMAddIns.Object` (works fine).
- **python-pptx pivot**: out of scope. Operator has explicitly rejected this. The product
  requirement is **native think-cell charts**, not raster/native-pptx fallbacks.

## What I might have missed (worth your investigation)

### A. The third SAFEARRAY arg of `PresentationFromTemplateStep3`

PowerPoint addin signature: `PresentationFromTemplateStep3(string, byte[], ???)`. ppttc.exe
wraps this. We know args 1+2 are template path + JSON-as-bytes. Arg 3 is a SAFEARRAY of unknown
type. **If it's a SAFEARRAY of "chart definitions to create", that's the missing API.**

I never decoded it. A frontier model with web access could:

1. Search think-cell's developer KB for "PresentationFromTemplateStep3"
2. Try varying types in the third array (strings? IDispatches? bytes? structured records?)
3. Compare against ppttc.exe's binary calls — maybe via ProcMon or API hooking on the VM

### B. think-cell's installed manual / xml-schemas folders

The install at `C:\Program Files (x86)\think-cell\` contains:

- `manual/` — HTML docs. Confirmed files include `*-api.html`, `*-jsondataautomation.html`,
  `*-exceldataautomation.html`, and `*-import-mekko-graphics.html`.
- `templates/` — sample `.potx` templates, including `think-cell Charts\Waterfall`,
  `think-cell Charts\Bar, Column`, `think-cell Charts\Mekko`, etc. These may show valid native
  think-cell OOXML/tag structure.
- `ppttc/` — official JSON automation sample files:
  `ppttc-schema.json`, `sample.html`, `sample.ppttc`, `template.pptx`.
- `xml-schemas/` — confirmed XSDs are `dml-*.xsd`, `shared-*.xsd`, and `tcstyle.xsd`; I did
  **not** see a ppttc/chart-creation schema there in the first listing.

Re-run listing command if needed:

```powershell
$root = "C:\Program Files (x86)\think-cell"
foreach ($sub in "manual","templates","ppttc","xml-schemas") {
  Get-ChildItem (Join-Path $root $sub) -Recurse -File | Select FullName,Length
}
```

The official sample `ppttc\template.pptx` and the chart `.potx` templates are now the most
promising local references for a minimum correct named think-cell object.

### C. VBA inside PowerPoint vs. PowerShell COM

I drove the addin from PowerShell ARM64 via Excel/PowerPoint COM. The VBA IDE inside PowerPoint
sometimes exposes additional members (e.g. `Application.Run` pickling, ribbon CommandBars,
EventTrust permissions) that PowerShell-from-outside doesn't see. **Try writing a `.vbs` or
`.bas` macro file, loading it into PowerPoint VBE on the VM, and calling its private APIs.** In
particular:

- `ActivePresentation.Slides(4).Shapes.AddOLEObject(..., ClassName:="thinkcell.???")` — does
  any think-cell ProgID respond as an OLE class? Try `thinkcell.chart`, `thinkcell.waterfall`,
  etc.
- `Application.CommandBars.ExecuteMso(idMso)` for any think-cell ribbon command IDs. Search the
  install dir and Office addin manifests/resources for customUI; the confirmed `xml-schemas/`
  folder only contained DML/shared/style XSDs, not ribbon XML.

### D. The Mekko import method

`ImportMekkoGraphicsCharts(SAFEARRAY(IDispatch))` is the ONLY chart-creation method exposed.
It's restricted to Mekko but the existence of the method proves the addin CAN create chart
shapes from definitions. **Find what input format it expects** (probably MekkoGraphics XML —
their other product) and check if there's a similar undocumented method for other chart types.
The sister method `GetMekkoGraphicsXML(IDispatch)` returns the XML for an existing Mekko chart
— get one from a sample template and reverse-engineer its format.

### E. Direct PPTX OOXML authoring — but smarter than donor injection

Codex's `_inject_donor_charts` failed because the donor LiteDB blob in `tag1.xml` is malformed.
If you can:

1. Save a real, manually-wired think-cell template (with one chart) from PowerPoint
2. Diff its OOXML against the base template
3. Identify the exact set of parts that constitute "one named think-cell chart"
4. Author those parts programmatically with correct LiteDB serialization

…you have the unblock. This is hard but tractable — it's just understanding the binary
serialization. The relevant references in this repo:

- `scripts/ppttc_template.py` — current donor approach (broken)
- `docs/RESEARCH_THINKCELL_TEMPLATE_FORMAT.md` — Codex's research on `m_strName` + LiteDB

LiteDB is open-source (.NET). You can read its source to understand the serialization format
of `tag1.xml`'s embedded blob.

### F. UI Automation (.NET UIA / SendKeys)

Pure mechanical: drive PowerPoint's ribbon clicks via `System.Windows.Automation`. This is
slow, brittle, and platform-locked, but it IS automation. Engineering cost: ~6-12 hours for a
robust harness. Not a clever solution — a brute-force one. Operator may accept this fallback
if all "clever" paths fail.

## Files to read first

In priority order:

1. `docs/HANDOFF_THINKCELL_PPTTC_2026-04-30.md` — Codex's prior runtime audit (definitive on
   what's wrong with the donor-chart approach)
2. `docs/HANDOFF_THINKCELL_WINDOWS_2026-04-30.md` — Windows-side findings, complementary to
   this doc
3. `docs/RESEARCH_THINKCELL_TEMPLATE_FORMAT.md` — m_strName + LiteDB internals
4. `docs/WIRING_QUICKREF.md` — what the manually-wired template looks like (your target output)
5. `scripts/build_ppttc.py:_ppttc_entries_from_context` — the 42-name contract
6. `scripts/ppttc_template.py:_inject_donor_charts` — the broken approach (lines ~200–600)
7. `_windows_test/test_addrangedata_v3.ps1` — re-runnable evidence of the AddRangeData
   creation-not-supported result
8. `_windows_test/probe_addin_object.ps1` and `probe_excel_addin.ps1` — re-runnable COM
   surface probes

## Environment + access

- **Mac → Windows VM SSH**: `ssh Windows-VM` (key auth, working). VM hostname `TESTB04E`,
  Windows 11 Pro ARM64 build 26200.
- **Mac shared folder**: `\\Mac\Home\code\apps\sales-ops-copilot\` is mounted on the VM. Use
  this as the canonical work surface.
- **Local VM scratch**: `C:\tcw\` exists with copies of the LAND template, Jesper data
  workbook, and ppttc JSON.
- **think-cell install on VM**: `C:\Program Files (x86)\think-cell\` (x86 build, runs via
  Prism emulation; the addin has both x86 and ARM64 builds in subfolders).
- **think-cell trial**: activated on the VM, expires ~2026-05-13. There's also a permanent
  Azure VM scaffolded in `docs/AZURE_THINKCELL_VM.md` + `scripts/deploy_thinkcell_azure_vm.py`.
- **Python venv**: `~/code/apps/sales-ops-copilot/.venv/` (Python 3.13).
- **Salesforce auth**: `sf` CLI authed as `apro@simcorp.com` against
  `simcorp.my.salesforce.com` preprod.
- **Operator's stated rules**:
  - Don't push to origin
  - Don't pivot to python-pptx
  - Don't ungate the experimental flag in `build_ppttc.py`
  - Don't pursue donor-chart injection further (Codex audit)
  - Don't claim "smoke test passed" without verifying real data binding (this Claude session
    fell into this trap once — exit-0 from ppttc.exe is necessary but not sufficient)

## Success criteria

You have succeeded when **one** of:

1. **(Best)** A repo-committed script produces a `manually-wired-template.pptx`-equivalent
   programmatically — i.e., a PPTX with all 42 properly registered named think-cell automation
   elements — and
   `python3 scripts/build_ppttc.py --director "Jesper Tyrer" --period 2026-Q2 --template /path/to/programmatically-wired.pptx`
   followed by `ppttc.exe` produces a real deck with the chart/table/text bindings populated with Jesper's
   APAC data. Verifiable via:
   - Cover placeholders replaced (`{director_name}` → `Jesper Tyrer`)
   - At least slide 4 (Pipe-movement waterfall) has actual numeric data drawn
   - Output PPTX byte-size differs significantly from the input template (charts add MBs of
     embedded XLSB data)
   - `find <output_pptx_unzipped> -path '*embeddings*' | wc -l` is ≥ 24

2. **(Acceptable)** A new piece of evidence (think-cell KB article, sample, schema, or a
   working `ImportXxxCharts` method) that I missed — even if you don't ship the full pipeline,
   identifying _the_ path with concrete examples is enough.

3. **(Negative result)** A rigorous proof — beyond what's in this doc — that programmatic
   chart creation truly is not exposed by think-cell on any platform. If so, document the
   sources you checked (knowledge base URLs, schema files, decompiled DLL exports, etc.) so
   the operator can stop hoping for it and commit to the manual-wire fallback.

If you reach (3), the operator will spend ~30 min wiring the template manually on the VM via
`docs/WIRING_QUICKREF.md`, save it, and the pipeline will run automated forever after that
one-time cost.

## Hard constraints (non-negotiable)

- **No `git push`**. The operator pushes manually.
- **No `pip install` of new top-level deps without operator approval.**
- **No pivoting to python-pptx native charts.** Operator has rejected this multiple times. The
  product requirement is real think-cell objects.
- **No claiming success without real evidence of data binding.** Exit-0 from ppttc.exe alone
  is insufficient (see §"Doesn't work" above for how this trap snared the prior session).
- **Run on Windows VM only.** Mac is architecturally blocked (no think-cell COM surface).
- **Be honest about uncertainty.** If you have a hypothesis, mark it as a hypothesis. If
  evidence is circumstantial, say so. The operator has been burned by AI-generated
  overconfidence — stay grounded.
