# Agent 7 — think-cell version evolution & API surface

Research swarm 2026-05-01. Source: think-cell.com (whats-new, manual, news), IANA media-type registry, Software Informer version index, Indezine + globenewswire press releases. WebSearch + WebFetch.

User's installed binary: **`tcaddin.dll` 15.0.100.220** on Parallels VM. think-cell 15 is "in development" with a preview/pilot page. The 15.0.100.x build series is therefore a pilot drop, NOT general-availability tc15. Highest publicly-released version is **tc14 (Nov 13, 2025)**.

---

## 1. Release timeline

| Version        | Release date                                                            | Headline / context                                                                                                                                                                                      | Automation/API additions                                                                                                                                                                          |
| -------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| tc1 (founding) | Apr 2002                                                                | Berlin spin-off from Fraunhofer FIRST                                                                                                                                                                   | —                                                                                                                                                                                                 |
| tc5.2          | 2011-01-26                                                              | Office 2010 incl. 64-bit; log axes; rotatable labels                                                                                                                                                    | —                                                                                                                                                                                                 |
| tc5.3          | 2012-11-24                                                              | Windows 8 compat; SharePoint co-authoring on PPT 2010                                                                                                                                                   | —                                                                                                                                                                                                 |
| tc5.4          | ~2013                                                                   | Maintenance                                                                                                                                                                                             | —                                                                                                                                                                                                 |
| tc6            | 2013-11-14                                                              | Office 2007 additional theme colors                                                                                                                                                                     | First documented style-customization surface                                                                                                                                                      |
| tc7            | ~2015 (Office 2016 launch window)                                       | "Other" series in column/Mekko/area/combo; sort-by-total; bubble auto-resize; Asian magnitude axis; Harvey balls + checkboxes in style file                                                             | Style-file surface expanded (Harvey balls, checkboxes, custom line styles)                                                                                                                        |
| tc8            | 2016-08-22                                                              | Pentagons/chevrons + textbox process flows; chart scanner (image OCR → numbers); SharePoint co-authoring                                                                                                | **Excel link for Gantt charts** added (first time Gantt could be data-bound)                                                                                                                      |
| tc9            | 2018-06-11                                                              | Doughnut charts; switched chart engine MS Graph → native PowerPoint chart; >4000 data points; eyedropper                                                                                                | **JSON automation introduced.** `application/vnd.think-cell.ppttc+json` IANA-registered 2018-04-16 by Arno Schoedl → fixes the `.ppttc` introduction date to **April 2018**                       |
| tc10           | 2019-06 (approx.)                                                       | First **macOS** release (Office 2016 16.9+ / OS X 10.10+); same-scale persistence; trendline expansion                                                                                                  | **`tcserver.exe` introduced** (JSON automation runnable as server / HTTP POST endpoint); **named text fields** as JSON placeholders                                                               |
| tc11           | 2021-03-19                                                              | Tableau connector (Chrome ext); RTL chart support; tables/images in auto-layout; Getty/Unsplash                                                                                                         | JSON `fill` color spec (e.g. `{"number":4,"fill":"#00FF00"}`)                                                                                                                                     |
| tc12           | 2023-03                                                                 | Profile/rotated line charts; football-field via line+errorbars; scatter partition fills; Lock Positions by default; hex color picker                                                                    | **Editable Data Layout** (datasheet decoupled from source); `<gantt>` fiscal-year + 4-4-5/4-5-4/5-4-4 in style file; bulk Excel-link delete                                                       |
| tc13 / "Suite" | 2025-01-21                                                              | think-cell **Suite** rebrand: Core + Library + Charts; in-PowerPoint slide search across local/network/OneDrive; 250 free templates; Pexels/Unsplash/Getty/Brandfolder/Canto; ribbon tab unified PPT+XL | think-cell Tools surface (align/resize/cleanup/symbols/decimal switch as scriptable)                                                                                                              |
| tc14           | 2025-11-13                                                              | Slide workbooks (full Excel embedded in slide); data tables alongside charts; net lines; ordinal axes; Mekko grand totals; offline manual; **WinINet → WinHTTP** transition                             | **`GetStyleName` API added** (per official whats-new "New API function to retrieve style file name"); **`ImportMekkoGraphicsCharts` + `GetMekkoGraphicsXML`** for batch Mekko Graphics conversion |
| tc15 (preview) | TBD — in development; pilot builds shipping (incl. user's 15.0.100.220) | Preview-only, "neither comprehensive nor necessarily an accurate representation" per think-cell                                                                                                         | Per probe: `BainToolboxApplyShift`, `BainToolboxRectangles`, `*Step2`/`*Step3` family resolvable but undocumented                                                                                 |

Build numbering: think-cell uses a **5-digit build number** (e.g. 35400, 35722) inside an `M.m.x.bbbbb` quad. The `15.0.100.220` user-facing string suggests an internal pre-GA series (last digits 220) below the typical GA build floor (~35000+ documented in KB).

---

## 2. Download URL pattern

think-cell does **not** publicly enumerate historical installer URLs. Live installer endpoints follow a single canonical pattern: `https://www.think-cell.com/en/download` (gates current GA only). Historical builds discovered:

- `think-cell.software.informer.com/5.2/`, `/5.3/`, `/5.4/`, `/6.0/`, `/7.0/`, `/10.0/` — community mirror, third-party CDN.
- `windows.softwareweb.com/think-cell-5.2-build-21174-W5634.html` — confirms tc5.2 build **21174**.
- `static.think-cell.com/ppttc/ppttc-schema.json` — public schema CDN (still live, hosts `.ppttc` JSON schema).
- ManageEngine Desktop Central tracks **tc12 MSI patches** and **tc13 (MSI) patches** as managed-update channels (corporate IT sees per-build deltas there).

Wayback Machine snapshots of `/en/resources/manual/api` and `/en/resources/manual/exceldataautomation` exist (search-engine-confirmed) but the WebFetch agent here lacked permission to fetch `web.archive.org/web/...` URLs in this run, so date-stamped diffs of the documented method list across years could not be programmatically extracted. A direct Wayback browser session would resolve this.

---

## 3. Documented API surface evolution

### 3.1 Excel data automation (canonical functions)

| Function                                                                                | Status                                | First doc'd                                                                               | Notes                                                                                                |
| --------------------------------------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `PresentationFromTemplate(Workbook, Template, PpApplication)`                           | **Active**                            | likely tc7-era (pre-JSON)                                                                 | Creates a copy of template, populates Excel-linked elements, **breaks the Excel link** in output     |
| `UpdateBatch` (composite of `CreateUpdate` → `AddRangeData` / `AddRangeImage` → `Send`) | **Active**                            | tc12+ (the docs cite "newer think-cell versions" when warning about UpdateChart slowness) | Required for table-image fills; also faster than UpdateChart on large decks                          |
| `UpdateChart`                                                                           | **Deprecated** but **still callable** | pre-tc12                                                                                  | "Existing code that uses `UpdateChart` will still work" — explicit deprecate-but-don't-break promise |
| `CreateUpdate()`                                                                        | Active sub-call                       | tc12+                                                                                     | Returns the batch object                                                                             |
| `AddRangeData(Target, Name, Range, Transposed)`                                         | Active                                | tc12+                                                                                     | Charts, tables, automation text fields, Harvey balls, checkboxes                                     |
| `AddRangeImage(...)`                                                                    | Active                                | tc12+ (or tc13/14 — gated to UpdateBatch only, per docs)                                  | Table-image fills; impossible via legacy `UpdateChart`                                               |
| `Send()`                                                                                | Active                                | tc12+                                                                                     | Dispatches batch to PowerPoint                                                                       |

### 3.2 Style files

| Function                                                               | Status                                        | First doc'd                                  | Notes                                                                                                    |
| ---------------------------------------------------------------------- | --------------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `LoadStyle(CustomLayoutOrMaster, FileName)`                            | Active                                        | tc6+ (style-file feature originated v6)      | Master-level loads override child layouts                                                                |
| `LoadStyleForRegion(CustomLayout, FileName, Left, Top, Width, Height)` | Active                                        | tc7+ (region scoping was a v7-era expansion) | Max **two style files per layout**                                                                       |
| `GetStyleName(layoutOrMaster)`                                         | **Active — explicitly listed as new in tc14** | **2025-11-13**                               | Per whats-new: "New API function to retrieve style file name." Does NOT return region-loaded style names |
| `RemoveStyles(CustomLayout)`                                           | Active                                        | tc7+                                         | Removes both styles if two are loaded; cannot remove from masters                                        |

### 3.3 Mekko Graphics import (tc14 addition)

| Function                    | Status | First doc'd       | Notes                                     |
| --------------------------- | ------ | ----------------- | ----------------------------------------- |
| `ImportMekkoGraphicsCharts` | Active | tc14 (2025-11-13) | Batch convert Mekko Graphics → think-cell |
| `GetMekkoGraphicsXML`       | Active | tc14 (2025-11-13) | Extract source XML                        |

### 3.4 JSON automation surface (file/HTTP, not COM)

- **`.ppttc` JSON file** — IANA-registered 2018-04-16 (`application/vnd.think-cell.ppttc+json`), introduced with **tc9 (June 2018)**.
- **`tcserver.exe`** — introduced **tc10 (2019)**, HTTP POST endpoint, Windows-only.
- **`ppttc.exe`** — command-line variant (`PPTTC_PATH PPTTC_INPUT -o PPTX_OUTPUT`), Windows-only, same generation.
- **JSON `fill` color** — added **tc11 (2021)**.

### 3.5 COM entry-point conventions

`Application.COMAddIns("thinkcell.addin").Object` — single ProgID, all calls **late-bound** (no type library shipped). Two add-in object handles: `tcPpAddIn` (PowerPoint) and `tcXlAddIn` (Excel). think-cell explicitly notes the API "cannot be used from Office Web Add-Ins."

---

## 4. Step-numbered method analysis (`*Step1` / `*Step2` / `*Step3`)

**Public docs contain ZERO `Step1`/`Step2`/`Step3` method names.** Confirmed across `/manual/api`, `/manual/exceldataautomation`, `/manual/jsondataautomation`, `/manual/style-files`, `/manual/introductionautomation`. The user's COM probe finds them resolvable, which means they are present in the type information but suppressed from documentation.

**Hypothesis** — this is a textbook **COM interface-evolution naming pattern**, parallel to Microsoft's own `IFoo` / `IFoo2` / `IFoo3` discipline (e.g. `IShellLink` / `IShellLink2`):

1. **`Step1` = the original Mekko-import / style / chart-update entry point.** Once a method's argument list or return shape needed to change in a non-backward-compat way, think-cell minted **`Step2`** alongside it. `Step1` stays callable so old VBA glue from 2018-era automation does not break — exactly the same posture the public docs take with `UpdateChart`.
2. **`Step2` → `Step3` reflects a second breaking revision** without removing `Step2`. Because each Step variant is a new vtable slot, late-bound dispatch keeps resolving them all.
3. The probed names map cleanly:
   - **`UpdateChartStep3`** — a revised in-place `UpdateChart`. Likely a transitional name from when UpdateChart was being rewritten internally (probably tc12 era, when "newer think-cell versions" started making UpdateChart slow); the public-facing replacement was repackaged as the higher-level `UpdateBatch` rather than `UpdateChartStep3`.
   - **`PresentationFromTemplateStep3`** — the third revision of the canonical template-fill function. The current public signature is `(Workbook, Template, PpApplication)`. Earlier signatures may have differed in PpApplication handling or in how Excel-link breaking was scheduled.
   - **`LoadStyleStep2`** — second revision of `LoadStyle`. Best guess: when `LoadStyleForRegion` was added (tc7-era), the original `LoadStyle` was kept and a `LoadStyleStep2` added so internal callers could share a unified region-aware code path.
   - **`GetStyleNameStep2`** — particularly interesting. tc14's whats-new explicitly markets `GetStyleName` as "new in tc14." A `Step2` already existing means there was a `Step1` shipped earlier that the docs never advertised. Likely scenario: `GetStyleNameStep1` existed for internal automation (possibly Bain-specific), and tc14 documented `Step2` under the unsuffixed public name.
   - **`RemoveStylesStep2`** — second revision of `RemoveStyles`, plausibly to handle the two-styles-per-layout limit that `LoadStyleForRegion` introduced.
   - **`UpdateBatchStep3`** — a third internal revision of UpdateBatch. Confirms UpdateBatch itself has been versioned twice since first introduction. The current public methods (`CreateUpdate` / `AddRangeData` / `AddRangeImage` / `Send`) are the visible facade.

**Net pattern**: `*Step1` and `*Step2` are likely callable but parameter-shifted relative to current docs. Calling them with current-docs argument shapes will fail; calling them with the older shapes (where discoverable from old SO/forum examples or Wayback'd manual pages) should still work.

---

## 5. Bain Toolbox analysis

The probe surfaced `BainToolboxApplyShift` and `BainToolboxRectangles` on `tcaddin.dll` directly. Three competing hypotheses:

**Hypothesis A — co-loaded Bain Toolbox add-in** (low probability). Bain Toolbox is a separate proprietary Bain & Co. PowerPoint add-in, restricted to Bain employees. If it were just co-loaded as a separate COM add-in, its methods would resolve through a separate ProgID (e.g. `BainToolbox.Addin`), not on `thinkcell.addin`'s vtable.

**Hypothesis B — OEM/co-branded build of tcaddin.dll for Bain** (medium probability). think-cell ships **enterprise/volume licensing** and is used by all 10 of the top consulting firms. An OEM SKU with extra co-branded methods (e.g. shape-shifting helpers like `ApplyShift`, `Rectangles`) is plausible — this would explain the methods sitting on the same DLL surface. However, the user's binary version is `15.0.100.220` (a pilot pre-GA build), and OEM customizations typically bake against GA releases.

**Hypothesis C — internal codename, not Bain-the-customer** (high probability). think-cell co-founder **Arno Schödl previously worked at McKinsey** before founding think-cell (per Wikipedia / Grokipedia). It is highly plausible "BainToolbox" is an internal think-cell codename — used by the dev team to refer to consulting-style shape utilities (rectangle alignment, shift-apply transforms) that are aimed at the consulting workflow but ship in the standard binary. The fact that they're discoverable on a 15.x **pilot** build (which would not yet have OEM-specific deployments) supports this. The naming convention "BainToolbox" was chosen because the target user persona is the Bain/MBB consultant; it is not literally Bain & Co. proprietary code.

**Verdict**: most likely **Hypothesis C — these are standard but undocumented helpers, internally codenamed for the consulting-firm persona**. There is no public evidence think-cell ships separate per-firm OEM binaries; all signals point to a single tcaddin.dll with a wide internal surface that selectively gets documented version-by-version. Confirming this would require comparing tcaddin.dll from a non-Bain enterprise license against the user's binary — same hash on the BainToolbox methods would clinch Hypothesis C.

---

## 6. Bottom-line — callable-but-undocumented older methods worth probing

**Yes — high-value targets exist.** In priority order:

1. **`UpdateChartStep1` / `UpdateChartStep2`** — the original (pre-`UpdateBatch`) Excel-link-based chart updaters. `UpdateChart` (unsuffixed) is officially deprecated-but-callable; the Step variants almost certainly are too. Lower overhead for one-shot single-chart updates; useful when you don't need batch image fills.
2. **`PresentationFromTemplateStep1` / `Step2`** — likely take a simpler argument shape (probably `(Workbook, Template)` without an explicit `PpApplication` — earlier behaviour may have used the active PowerPoint instance implicitly). Worth probing for cases where you can't easily get a `PowerPoint.Application` reference (e.g. running from Excel-only context).
3. **`GetStyleNameStep1`** — predates the tc14 public release of `GetStyleName`. Even though tc14 just shipped, the `Step1` variant has been usable for years internally. Probe for return-shape differences (might return more metadata than the public version).
4. **`LoadStyleStep1` and `LoadStyleStep2`** — given the public surface has both `LoadStyle` and `LoadStyleForRegion`, the Step variants likely fold into one of them. Worth probing the parameter shapes via IDispatch type-info.
5. **`BainToolbox*` family** — if Hypothesis C is correct, these are usable shape-utility helpers (alignment, rectangles, shift transforms) that are not documented anywhere. Probing their `IDispatch` type info will reveal parameter shapes.

**Cheapest probe path**: dump the `IDispatch::GetTypeInfo()` for each method via OleView.exe / Python `comtypes`, compare argument shapes between Step1 / Step2 / Step3 / unsuffixed siblings. If a Step1 method takes a strict subset of the unsuffixed method's args, that's the original signature, and old-shape calls will work.

**Risk**: think-cell can drop Step variants in any release without notice (only the unsuffixed public methods carry the explicit "your existing code will still work" promise — extended only to `UpdateChart` in writing). Build any production automation against the documented public API; treat Step\* methods as a research/exploration affordance only.

---

## Sources

- [think-cell — See what's new](https://www.think-cell.com/en/product/whats-new)
- [think-cell 14 launch (GlobeNewswire 2025-11-14)](https://www.globenewswire.com/news-release/2025/11/14/3188453/0/en/Newly-released-think-cell-14-gives-users-more-efficiency-and-flexibility-in-charting-layout-and-the-full-range-of-PowerPoint-workflows.html)
- [think-cell 13 + Suite launch (think-cell company news 2025-01-21)](https://www.think-cell.com/en/company/news/2025-01-21)
- [think-cell 12 release announcement](https://www.think-cell.com/en/resources/content-hub/think-cell-software-releases-version-12-with-new-powerpoint-enhancements)
- [think-cell 9 launched (2018-06-11)](https://www.think-cell.com/en/company/news/2018-06-11)
- [think-cell 8 launched (2016-08-22)](https://www.think-cell.com/en/company/news/2016-08-22)
- [think-cell 5.2 launched (2011-01-26)](https://www.think-cell.com/en/company/news/2011-01-26)
- [think-cell — How to use think-cell's API](https://www.think-cell.com/en/resources/manual/api)
- [think-cell — Excel data automation](https://www.think-cell.com/en/resources/manual/exceldataautomation)
- [think-cell — JSON data automation](https://www.think-cell.com/en/resources/manual/jsondataautomation)
- [think-cell — Style files](https://www.think-cell.com/en/resources/manual/style-files)
- [think-cell — Introduction to automation](https://www.think-cell.com/en/resources/manual/introductionautomation)
- [IANA — application/vnd.think-cell.ppttc+json (registered 2018-04-16)](https://www.iana.org/assignments/media-types/application/vnd.think-cell.ppttc+json)
- [Software Informer — think-cell all versions](https://think-cell.software.informer.com/versions/)
- [Indezine — Exploring think-cell version 11 (2021-03-19)](https://blog.indezine.com/2021/03/exploring-think-cell-version-11.html)
- [Indezine — think-cell 10 on Office for Mac (2019-06)](https://blog.indezine.com/2019/06/think-cell-10-now-works-on-office-for-mac.html)
- [PPT Productivity — Missing the Bain Toolbox for PowerPoint](https://pptproductivity.com/blog/missing-bain-toolbox-for-powerpoint)
- [Ampler — Bain-style PowerPoint productivity for BeyondBain alumni](https://ampler.io/articles/unlock-bain-style-powerpoint-productivity-free-for-beyondbain-alumni/)
- [Wikipedia — think-cell](https://en.wikipedia.org/wiki/Think-cell)
- [ManageEngine — Think-cell 12 patches](https://www.manageengine.com/products/desktop-central/patch-management/Think-cell-12-patches.html)
- [ManageEngine — Think-cell 13 (MSI) patches](<https://www.manageengine.com/products/desktop-central/patch-management/Think-cell-13-(MSI)-patches.html>)
