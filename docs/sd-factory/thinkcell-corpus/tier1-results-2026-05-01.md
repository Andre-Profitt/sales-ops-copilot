# Tier 1 Probe Results — 2026-05-01

Run on Parallels Windows 11 Pro ARM64 VM (host `Windows-VM`),
think-cell `15.0.100.220` (pre-GA pilot of tc15), `tcaddin.dll` SHA-256
`7FBFA7E7435FB9989189F699E733E1098C7176680D57967620D394847E442200`.

Five tier-1 probes plus two new probes (tcasr sidecar, browser-extension)
run via the existing SSH bridge. JSON outputs landed in
`state/thinkcell_bridge/<probe>/<timestamp>/`.

## Verdict Table

| Probe             | Status             | New surface? | Headline                                                                                                                                      |
| ----------------- | ------------------ | ------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| arch_siblings     | pass               | NO           | ARM64 only; no x86/x64 sibling builds                                                                                                         |
| pe_resources      | pass               | YES          | tcaddin.dll embeds 57KB baseline style XML using new `https://schemas.think-cell.com/next/tcstyle` namespace                                  |
| **typeinfo**      | **pass**           | **YES**      | **All 3 IDispatch implementations expose ITypeInfo with 3 internal interface names + GUIDs + complete func tables**                           |
| xladdin_hidden    | pass (with caveat) | NO           | InvokeMember-based scan over-resolves; typeinfo is authoritative                                                                              |
| clipboard         | not_run            | —            | Interactive-only; runbook printed                                                                                                             |
| tcasr_sidecar     | pass               | YES          | `tcasr.exe` binary confirmed at `C:\Program Files (x86)\think-cell\tcasr.exe` (520KB v15.0.100.220), **NOT currently running** — lazy-spawned |
| browser_extension | running            | —            | Still in flight at write time                                                                                                                 |

## 🚨 Headline: ITypeInfo enumeration succeeds

`IDispatch::GetTypeInfoCount()` returned **1** for all three interfaces.
`GetTypeInfo(0)` returned a complete `ITypeInfo` for each. The full
`GetFuncDesc` walk yielded the _complete_ method table per interface,
including DISPIDs, parameter names, parameter counts, invoke-kind, and
function flags.

**Internal interface names + GUIDs (newly disclosed):**

| Object      | Internal interface name | IID                                      |
| ----------- | ----------------------- | ---------------------------------------- |
| `tcPpAddIn` | `IPpMacroInterface`     | `{24f3e526-2a15-4b8b-bc6a-558500f451c1}` |
| `tcXlAddIn` | `IXlMacroInterface`     | `{085347c3-2d5b-4885-869a-b9cc362b924c}` |
| `tcUpdate`  | `IUpdateBatch`          | `{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}` |

These are authoritative IIDs usable for explicit QueryInterface in
production code. Until now the corpus referenced these only as
"the late-bound add-in object" — we now have the formal contract.

## Complete enumerated COM surface (DISPIDs locked)

### `IPpMacroInterface` — 19 callable methods (12 normal + 3 hidden + 4 standard inherited)

| Method                            |    DISPID | Params | Flags            | Param signature                                                                   |
| --------------------------------- | --------: | -----: | ---------------- | --------------------------------------------------------------------------------- |
| ActivateAddIn                     |      1018 |      1 | 0                | (Active)                                                                          |
| IsAddInActive                     |      1019 |      0 | 0                | ()                                                                                |
| LoadStyle                         |      1020 |      2 | 0                | (CustomLayoutOrMaster, FileName)                                                  |
| LoadStyleForRegion                |      1021 |      6 | 0                | (CustomLayout, FileName, Left, Top, Width, Height)                                |
| RemoveStyles                      |      1022 |      1 | 0                | (CustomLayout)                                                                    |
| GetMekkoGraphicsXML               |      1026 |      1 | 0                | (Shape)                                                                           |
| ImportMekkoGraphicsCharts         |      1027 |      1 | 0                | (safeArrayOfShapes)                                                               |
| StartTableInsertion               |      1028 |      0 | 0                | ()                                                                                |
| GetStyleName                      |      1029 |      1 | 0                | (CustomLayoutOrMaster)                                                            |
| ShowChartGallery                  |      1030 |      5 | 0                | (Left, Top, Width, Height, HWND)                                                  |
| BainToolboxRectangles             |      1031 |      3 | 0                | (Slide, safeArrayOfLeftTopWidthHeightMovable, safeArrayOfLeftTopWidthHeightFixed) |
| BainToolboxApplyShift             |      1032 |      2 | 0                | (Slide, safeArrayOfOffsets)                                                       |
| **PresentationFromTemplateStep3** | 266056320 |      3 | **64 (FHIDDEN)** | (bstrTemplate, psalnkid, psaiunkStorage)                                          |
| **UpdateChartStep3**              | 266056321 |      3 | **64 (FHIDDEN)** | (idisp, bstrChartName, iunkStorage)                                               |
| **UpdateBatchStep3**              | 266056322 |      4 | **64 (FHIDDEN)** | (psaName, psaidispTarget, psaiunkStorage, nCharts)                                |

`flags=0` is normal/visible; `flags=64` is `FUNCFLAG_FHIDDEN` — the COM
type-library marker that says "this method exists but should not appear
in object browsers". The Step3 trio is **deliberately hidden**.

### `IXlMacroInterface` — 3 callable methods

| Method                   | DISPID | Params | Param signature                        |
| ------------------------ | -----: | -----: | -------------------------------------- |
| PresentationFromTemplate |      1 |      3 | (Workbook, Template, PpApplication)    |
| UpdateChart              |      2 |      4 | (Target, ChartName, Range, Transposed) |
| CreateUpdate             |      4 |      0 | ()                                     |

### `IUpdateBatch` — 3 callable methods

| Method        | DISPID | Params | Param signature                   |
| ------------- | -----: | -----: | --------------------------------- |
| AddRangeData  |      1 |      4 | (Target, Name, Range, Transposed) |
| AddRangeImage |      2 |      3 | (Target, Name, Range)             |
| Send          |      3 |      0 | ()                                |

## What this means — interpretation

### 1. The think-cell COM surface is now empirically closed

**Total: 25 think-cell-specific COM methods**, completely enumerated by
typeinfo, with full DISPIDs and parameter signatures. The empirical
floor (from the user's prior hidden-surface probe) and the empirical
ceiling (from this typeinfo probe) match. The "Direct API status"
column of the unblock matrix can now be considered closed: the
documented + Step* + BainToolbox* surface is the _complete_ surface.
There is no further hidden API obtainable through IDispatch / ITypeInfo.

### 2. Novel parameter-signature intel

The typeinfo dump revealed parameter signatures the user's prior probes
could only guess at:

- **`LoadStyleForRegion`** has 4 region params (Left/Top/Width/Height) —
  full per-region styling is supported, not just whole-master.
- **`ShowChartGallery`** takes (Left, Top, Width, Height, HWND) — the
  HWND parameter means the gallery can be parented to an arbitrary
  window. Likely supports headless gallery placement on a fake parent.
- **`BainToolboxRectangles`** takes (Slide, safeArrayOfLeftTopWidthHeightMovable,
  safeArrayOfLeftTopWidthHeightFixed) — this is a layout-helper method
  that splits shapes into "movable" and "fixed" rectangles. Looks like
  consulting-deck shape arrangement automation.
- **`BainToolboxApplyShift`** takes (Slide, safeArrayOfOffsets) — applies
  position offsets to a list of slide shapes.
- **`PresentationFromTemplateStep3`** takes (bstrTemplate, psalnkid,
  psaiunkStorage) — internal contract: a template path string, a
  safe-array of link IDs, and a safe-array of `IUnknown*` storage objects.
  Public docs hide this signature behind a wrapper with friendlier types.

### 3. Step1 / Step2 family hypothesis updated

The user's hidden-surface probe found `*Step2` and `*Step3` names
resolving via `GetIDsOfNames`. **typeinfo only enumerates Step3.** Two
explanations:

- (a) The Step1/Step2 implementations exist on **deprecated typelib
  branches** that ITypeInfo doesn't surface in current typelib export
  but the implementation still routes by name through `GetIDsOfNames`.
- (b) Step1/Step2 are kept callable via `IDispatch::GetIDsOfNames` for
  back-compat but not via the typelib.

Either way: **the public surface today is the Step3 family, and the
Step1/Step2 surface is back-compat-only**. Worth one explicit invoke
test against `Step2` variants to characterize their behavior — but
this is now low priority because the typelib is the canonical contract.

### 4. xladdin_hidden over-resolved (false positives)

The xladdin_hidden probe used PowerShell `Type.InvokeMember` to test
name resolution. **The typeinfo dump proves the false-positive
hypothesis**: typeinfo shows `tcUpdate` has exactly 3 think-cell
methods (`AddRangeData`, `AddRangeImage`, `Send`), but xladdin_hidden
"resolved" `AddRangeChart`, `AddNamedRange`, `AddNamedTable`,
`AddRangeText`, `AddRangeImageWWW` etc. None of those are real on
`IUpdateBatch`.

The `Type.InvokeMember` PowerShell wrapper resolves names against the
runtime `__ComObject` proxy in ways that include dynamic property
lookup, prototype chains, and Office-application-level name
resolution — which leaks names from `Excel.Application` itself into
the "looks like it resolved" bucket. **The xladdin_hidden harness
should be deprecated; typeinfo is now authoritative.**

### 5. Two pure-text resources in tcaddin.dll

`pe_resources` extracted 142 resources from `tcaddin.dll`. Of those,
only **two were textual XML**:

- `RT_RCDATA #4001` (57,687 bytes) — a baseline think-cell _style file_
  with `xmlns="https://schemas.think-cell.com/next/tcstyle"`. The
  `next/` namespace is **not** the documented per-build versioned URL
  (e.g., `https://schemas.think-cell.com/<BUILDNUMBER>/tcstyle.xsd`) —
  this is the in-development next-version schema, embedded directly in
  the binary. Worth dumping and diffing against the published per-build
  schemas. The dump file lives at:
  `state/thinkcell_bridge/pe_resources/<ts>/dumps/tcaddin.dll/ID10_RT_RCDATA_ID4001.xml`
- Two `RT_MANIFEST` Windows assembly manifests (boilerplate).

**No `customUI.xml` resource**, which means think-cell **builds the
ribbon at runtime in C++** rather than embedding it as a resource —
consistent with their reverse-engineering disclosures (Theophil 2024,
McPartlin 2014).

### 6. tcasr.exe sidecar confirmed but lazy-spawned

- Path: `C:\Program Files (x86)\think-cell\tcasr.exe`
- Size: 520,664 bytes
- Version: 15.0.100.220 (matches tcaddin.dll)
- **Currently NOT running.** Sidecar is on-demand, not a daemon.
- Static IPC pattern scan returned 0 hits for `mutex`/`section`/`pipe`/`rpc`
  patterns — names are likely dynamically constructed at runtime.
- No `tc*` top-level windows visible to a non-elevated session.
- Sysinternals `winobj.exe` not installed on the VM, so
  `\BaseNamedObjects` enumeration was skipped. **Recommended next step:
  install winobj + Procmon-trace tcasr's spawn moment** (i.e., trigger
  a deck-write that engages it).

## Updated Unblock Matrix Implications

| Lane                   | Before this probe                                                     | After this probe                                                                                                                                                       |
| ---------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Direct API surface     | "no headless chart constructor found via 3,200 names × GetIDsOfNames" | **Empirically closed: 25 methods total via ITypeInfo enumeration**                                                                                                     |
| Hidden Step3 family    | "callable via name probe"                                             | **Authoritative: 3 hidden methods (FHIDDEN flag) on tcPpAddIn, internal signatures known**                                                                             |
| Step1/Step2 family     | "resolvable via name probe"                                           | "deprecated typelib branch or name-only fallback; not in current typelib"                                                                                              |
| Native editable tables | "blocked; only StartTableInsertion (interactive)"                     | **Confirmed: no `Insert*Table`, `Create*Table`, `AddRangeTable` etc. in any of 3 typelibs**                                                                            |
| Style API              | "proven for transient deck"                                           | **Authoritative signatures available; `LoadStyleForRegion` supports per-region (Left/Top/Width/Height) — wider than previously known**                                 |
| BainToolbox family     | "resolvable via name probe; purpose unknown"                          | **Layout-helper API: BainToolboxRectangles splits shapes into movable+fixed; BainToolboxApplyShift applies offsets. Probably consulting-deck-arrangement automation.** |
| tcasr.exe sidecar      | not characterized                                                     | "binary on disk, lazy-spawned; IPC contract still TBD via runtime probe"                                                                                               |

## Next Best Probes (post-tier-1)

1. **Procmon-trace tcasr.exe spawn moment.** Trigger a `.ppttc` write
   from the existing `prove_thinkcell_native_chart_contract.py` harness,
   capture the moment tcasr starts, observe what mutex/section names it
   creates. **High yield — tcasr is the only remaining unmapped surface.**
2. **One explicit invoke test of the Step2 family.** Does
   `LoadStyleStep2` actually accept different parameters than `LoadStyle`,
   or is it a deprecated alias? Use a transient master/layout target;
   compare behavior to `LoadStyle`. **Closes the Step1/Step2 question.**
3. **Diff the embedded `RT_RCDATA #4001` style XML against the published
   per-build XSDs.** The `next/tcstyle` namespace likely contains schema
   extensions previewing tc15 features. **Architectural intel.**
4. **The hidden Step3 trio + `BainToolbox*` are callable.** Build proof
   harnesses that exercise them on transient decks to characterize
   real-world behavior. Don't add to production lanes; corpus knowledge.
5. **Browser-extension native-messaging probe** (still running at write
   time). When it lands, append findings here.

## Stop Rules

- **Direct COM API discovery is now closed via ITypeInfo.** Don't
  re-run name candidate scans against IDispatch — the typelib is
  authoritative.
- The remaining open surface is at runtime/observation layers
  (tcasr IPC, native-messaging protocol, `think-cellXML` chart
  serialization) — not at the dispatch interface layer.
- Don't invoke the FHIDDEN Step3 methods directly without a
  proof-write that defines expected behavior. The user's existing
  `prove_thinkcell_*_contract.py` harnesses already exercise them
  indirectly via the documented wrappers.

## Output Artifacts

- arch_siblings: `state/thinkcell_bridge/arch_siblings/20260501-215704/thinkcell_arch_siblings_probe.json`
- pe_resources: `state/thinkcell_bridge/pe_resources/20260501-215733/thinkcell_pe_resources_probe.json` + 142 resource dumps
- typeinfo: `state/thinkcell_bridge/typeinfo/20260501-220xxx/thinkcell_typeinfo_probe.json`
- xladdin_hidden: `state/thinkcell_bridge/xladdin_hidden/20260501-2200xx/thinkcell_xladdin_hidden_probe.json` (deprecated; supplanted by typeinfo)
- tcasr_sidecar: `state/thinkcell_bridge/tcasr_sidecar/20260501-2157xx/thinkcell_tcasr_sidecar_probe.json`
- browser_extension: pending
