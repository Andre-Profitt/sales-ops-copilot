# Handoff — think-cell Windows verdict

**Date:** 2026-04-30 late evening
**Purpose:** Lock in what was learned on the Windows VM so the next session doesn't redo this dead-end exploration.

## TL;DR

The Windows VM pivot validated **half** the architecture:

- `ppttc.exe` works on Windows (ARM via Prism x86 emulation). Exits 0, processes the JSON correctly.
- The other half — **programmatic creation of think-cell named shapes** — has **no COM API**. The think-cell addin's IDispatch surface only updates existing shapes; chart insertion is UI-only.

This is not a platform limitation we can engineer around. think-cell never exposed a `CreateChart` COM method.

The only proven path to a working pipeline is the one Codex's prior audit
(`docs/HANDOFF_THINKCELL_PPTTC_2026-04-30.md`) already named: **manually wire one template once**,
then use ppttc.exe for monthly refreshes forever.

## What was tested on Windows

### Setup state

- Parallels VM: TESTB04E, Windows 11 Pro ARM64, build 26200
- think-cell trial install: `C:\Program Files (x86)\think-cell\` (x86 build, runs via Prism)
- Office 365 with PowerPoint x64 + think-cell addin loaded (`thinkcell.addin connect=True`)
- SSH from Mac → VM via key auth, working
- Bundle directory: `_windows_test/` accessible via `\\Mac\Home\code\apps\sales-ops-copilot\_windows_test\`

### Test 1 — base template smoke (apparent pass, but trivial)

**Bundle:** `Jesper-Tyrer-LAND-2026-Q2.ppttc` + `LAND_template.pptx` (the 28-slide SimCorp deck with placeholder rectangles, no think-cell shapes).

**Result:** `ppttc.exe -o output.pptx` exited 0, 0B stderr, output PPTX produced.

**But on inspection** (md5 + structural diff):

- Output PPTX has different bytes from input (rels normalization + media renumbering)
- **Zero new think-cell embeddings**
- **Zero new tag files** (only the existing `tag1.xml`)
- **Cover placeholders unchanged** — `{director_name}`, `{period}`, `{scope_label}` still untouched

**Diagnosis:** ppttc.exe found zero of the 42 expected named shapes in the template, so it had nothing to bind data to. It silently produced a clean round-tripped copy. Exit-code-0 is misleading here; "success" without data injection is the failure mode for an empty template.

### Test 2 — donor-chart-injected template (failure, identical to Mac)

**Bundle:** `Jesper-donor-template.pptx` (output of `build_director_template(...)` + `_inject_donor_charts(...)` from `scripts/ppttc_template.py`) + matching `Jesper-donor.ppttc` with 12 named-shape entries.

**Result:** `ppttc.exe` exited 1 with error:

```
The .ppttc file is bad. The template failed to load.
```

This is the **same error Codex saw on Mac**. Confirms the donor-chart injection produces a structurally bad PPTX regardless of platform — not a Mac-specific quirk.

The donor template DOES contain 24 OLE embeddings + 200+ tag XML files (confirmed via unzip). think-cell loads them, decides they're invalid, aborts. Likely causes per Codex's research dossier (`docs/RESEARCH_THINKCELL_TEMPLATE_FORMAT.md`):

- Missing or corrupt LiteDB blob (think-cell stores its private state in tag1.xml as a LiteDB binary)
- Tag-to-shape ID mismatches
- OLE container relationship inconsistencies

This is a deep rabbit hole. Codex's prior audit explicitly recommended NOT going down it: *"Stop trying to ship the donor-chart-generated template as production."* That recommendation stands.

### Test 3 — COM API probe (architectural verdict)

Probed the `thinkcell.addin` IDispatch surface via `Application.COMAddIns("thinkcell.addin").Object`. Full method list:

| Method                              | Notes                                       |
| ----------------------------------- | ------------------------------------------- |
| ActivateAddIn(bool)                 | enable/disable                              |
| GetStyleName / Step2                | reads currently loaded brand style          |
| LoadStyle(IDispatch, string)        | loads brand style XML — useful for SimCorp brand file load |
| LoadStyleForRegion / Step2          | regional style overrides                    |
| RemoveStyles / Step2                | clears styles                               |
| **PresentationFromTemplateStep3**(string, byte[], ...) | this IS the .ppttc handler. ppttc.exe wraps this. |
| **UpdateChartStep3**(IDispatch, string, IUnknown) | updates ONE existing think-cell chart by name |
| **UpdateBatchStep3**(string[], IDispatch[], IDispatch[]) | updates MANY existing think-cell charts. Same primitive ppttc.exe uses internally. |
| ImportMekkoGraphicsCharts           | imports MekkoGraphics XML (one chart type)  |
| BainToolboxApplyShift / Rectangles  | Bain custom add-on, irrelevant              |
| ShowChartGallery(int×5)             | UI dialog only — not headless-callable      |
| StartTableInsertion()               | starts table insertion (likely UI-coupled)  |

**Critical observation:** every method that creates/touches a chart either operates on an *existing* shape (`UpdateChart*`, `UpdateBatch*`) or requires a UI dialog (`ShowChartGallery`). There is no `CreateChartFromScratch(slideIndex, chartType, dataRange, name)` method. **Programmatic creation of named think-cell shapes is not supported by the COM API.**

This is consistent with think-cell's documented integration model: data binding is automated; chart creation is a manual ribbon-driven workflow.

## What we ruled out (definitively)

- **AppleScript automation (Mac)** — dead. `RESEARCH_APPLESCRIPT_THINKCELL.md`.
- **Donor-chart injection (Mac OR Windows)** — dead. Same error on both.
- **PowerShell COM activation of `thinkcell.addin` directly** — fails with HRESULT 0x800700C1 (wrong arch on ARM PowerShell). Workaround is to go through PowerPoint's `COMAddIns.Object`, which we did successfully.
- **Programmatic shape creation via COM API** — does not exist.

## What's still open

### The only proven viable path: manual wiring + ppttc.exe refresh

1. Open `assets/LAND_template.pptx` in PowerPoint on the Windows VM.
2. Follow `docs/WIRING_QUICKREF.md` to manually insert and name 24 think-cell charts (~30 min).
3. **Critical names** (must match emitter contract from `_ppttc_entries_from_context(...)`):
   `S01_DirectorName`, `S01_Period`, `S01_ScopeLabel`, `S02_ExecSummaryLeft`/Right, `S04_PipeMovement`, `S05_PipelineByStage`, `S06_PipelineAging`, `S07_TopDealsLand`, `S08_TopDealsExpand`, `S09_PendingCommercialApproval`, `S11_RenewalPipeline`, `S12_GRRProxyTable`, `S12_GRRProxyFootnote`, `S13_ForecastCategory`, `S15_ByOwner`, `S16_StageByIndustry`, `S17_TerritoryPerformance`, `S18_WinsLossesQTD`, `S19_Velocity`, `S21_ConcentrationRiskChart`, `S22_StaleActivity`, `S24_AccountExpansion`, `S25_PipelineCreationVelocity`, `S26_ActionItems`, `S27_RisksOutlook`.
4. Load `assets/SimCorp-thinkcell-style.xml` via Tools → Change Style → Other.
5. Save as the manual template.
6. Then run:
   ```bash
   python3 scripts/build_ppttc.py \
     --all-directors \
     --period 2026-Q2 \
     --template /absolute/path/to/manually-wired-template.pptx
   ```
7. Each emitted `.ppttc` then drives a 5-second refresh per director on the VM.

### Time budget

- One-time wiring: ~30 min (Andre, on the VM)
- Per-director Save-As + Data Links Switch: ~10 min × 8 = ~80 min
- Monthly refresh forever: ~5 sec/director × 9 = ~45 sec total

### Trial deadline

Parallels Windows 11 ARM trial expires 14 days from install. As of 2026-04-30 we have ~13 days. After expiry, options are:

1. Buy Parallels (~$100/yr)
2. Provision a permanent Windows VM in Azure (already scaffolded — see `docs/AZURE_THINKCELL_VM.md` and `scripts/deploy_thinkcell_azure_vm.py`)

## Files Claude/Codex should read first (for the next session)

1. `docs/HANDOFF_THINKCELL_PPTTC_2026-04-30.md` — Codex's original audit (still definitive)
2. `docs/RESEARCH_THINKCELL_TEMPLATE_FORMAT.md` — m_strName + LiteDB internals
3. This file — Windows-side verdict
4. `_windows_test/probe_addin_object.ps1` — re-runnable COM probe
5. `_windows_test/run_donor_test.ps1` — proof of donor failure on Windows
6. `docs/WIRING_QUICKREF.md` — the click-by-click runbook for the manual wire

## Hard constraints (still apply)

- Do not pursue donor-chart injection further. Two independent platforms confirmed it's dead.
- Do not pivot to python-pptx (user has explicitly rejected this).
- Do not claim "the smoke test passed" without checking that data actually landed in the output. Exit 0 + 0B stderr is necessary but not sufficient.
- The build_ppttc.py default path remains gated behind `--experimental-generated-template`. Don't ungate it.
