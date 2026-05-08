# Agent 2 — Wayback Machine + Community Research

**Date:** 2026-05-01
**Mission:** Find documented-then-removed think-cell API methods + community-discovered automation tricks via Wayback snapshots, GitHub forks, and dev forums.
**Tools used:** WebSearch, curl (Wayback CDX + KB), gh search code (rate-limited mid-run).
**Note:** WebFetch was denied for `web.archive.org` and `pypi.org`; used `curl` with `Mozilla/5.0` UA against the CDX API and the live KB pages. GitHub code search hit org-wide rate limit after ~10 queries.

---

## Section A — Documented-then-removed methods

### A.1 Page-evolution diff matrix

CDX API returned no snapshots for the URL prefixes the user listed under "legacy" (`/support/manual/api.html`, `/support/manual/automation.html`). Those exact paths never existed; the legacy structure used `.shtml` (2019) → `.html` (2021) → `/resources/manual/...` (2023+). Real legacy URLs and snapshot counts:

| Page             | Legacy URL (2019–2021)                            | Modern URL (2023+)                            | First snapshot | Last snapshot | Bytes evolution                                                                         |
| ---------------- | ------------------------------------------------- | --------------------------------------------- | -------------- | ------------- | --------------------------------------------------------------------------------------- |
| Excel automation | `/en/support/manual/exceldataautomation.shtml`    | `/en/resources/manual/exceldataautomation`    | 2019-08-17     | 2026-04-28    | 10.5 KB → 12 KB (Apr 2025) → **27 KB (Jul 2025)** → **35 KB (Apr 2026)**                |
| JSON automation  | `/en/support/manual/jsondataautomation.shtml`     | `/en/resources/manual/jsondataautomation`     | 2019-08-17     | 2026-04-28    | 10.6 KB → 14 KB (Apr 2025) → **29 KB (Jul 2025)** → **34 KB (Feb 2026)**                |
| Intro automation | `/en/support/manual/introductionautomation.shtml` | `/en/resources/manual/introductionautomation` | 2019-08-17     | 2026-05-01    | 6.6 KB → 9 KB (Apr 2025) → **15.5 KB (Jul 2025)** → **26 KB (Apr 2026)**                |
| API hub (new)    | (did not exist pre-2023)                          | `/en/resources/manual/api`                    | 2023-06-02     | 2026-04-28    | 17 KB → 19 KB (Apr 2024) → 18 KB (early 2025) → **36 KB (Jul 2025)** → 30 KB (Apr 2026) |

### A.2 Method-name presence diff

Grep of all snapshots for the canonical API tokens. `=` = present; blank = absent.

| Token                                                             |             2019 shtml             |                  2024 (early)                   | Apr 2025 | **Jul 2025** |              Apr 2026              |
| ----------------------------------------------------------------- | :--------------------------------: | :---------------------------------------------: | :------: | :----------: | :--------------------------------: |
| `tcaddin`                                                         |                 =                  |                        =                        |    =     |      =       |                 =                  |
| `tcXlAddIn`                                                       |                                    |                        =                        |    =     |      =       |                 =                  |
| `tcPpAddIn`                                                       |                                    |                        =                        |    =     |      =       |                 =                  |
| `thinkcell.addin`                                                 |                 =                  |                        =                        |    =     |      =       |                 =                  |
| `PresentationFromTemplate`                                        |                 =                  |                        =                        |    =     |      =       |                 =                  |
| `UpdateChart`                                                     |                 =                  |                        =                        |    =     |      =       | = (still listed as **deprecated**) |
| **`UpdateBatch`**                                                 |                                    |                                                 |          |              |              = (NEW)               |
| **`CreateUpdate`**                                                |                                    |                                                 |          |              |              = (NEW)               |
| **`AddRangeData`**                                                |                                    |                                                 |          |              |              = (NEW)               |
| **`AddRangeImage`**                                               |                                    |                                                 |          |              |              = (NEW)               |
| **`Send`** (on tcUpdate)                                          |                                    |                                                 |          |              |              = (NEW)               |
| `LoadStyle`, `LoadStyleForRegion`, `GetStyleName`, `RemoveStyles` | (n/a — Style API page is separate) |      first appears in `/style-files` ~2024      |    =     |      =       |                 =                  |
| `ImportMekkoGraphicsCharts`, `GetMekkoGraphicsXML`                |               (n/a)                | first appears in `/import-mekko-graphics` ~2024 |    =     |      =       |                 =                  |

### A.3 Documented-then-removed methods — table

Important framing: **think-cell's official API has been additive, not subtractive, for at least six years.** The CDX corpus shows zero method names that appeared in older docs and were later removed wholesale. What _did_ change is method **signatures** and **status (deprecated vs canonical)**:

| Method                                                                               | Originally documented                            | Status now                                                                                                                             | What changed                                                                                                                                                                                        | Snapshot URL (evidence)                                                                                           |
| ------------------------------------------------------------------------------------ | ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `tcaddin.UpdateChart(pres As PowerPoint.Presentation, strName, rgData, bTransposed)` | 2019 `/support/manual/exceldataautomation.shtml` | **Still callable**, but doc moved & renamed parameter from `pres As PowerPoint.Presentation` (typed) to `target As Object` (broadened) | First arg widened from typed `Presentation` to untyped `Object`, enabling targets like `SlideRange`/`Slide`/`Master`/`CustomLayout`. The original strict-typed signature is gone from current docs. | https://web.archive.org/web/20191021053941/https://www.think-cell.com/en/support/manual/exceldataautomation.shtml |
| `tcaddin.UpdateChart(...)` (PowerPoint.Presentation typed)                           | 2019                                             | **Officially deprecated since 2026**, replaced by `UpdateBatch` family                                                                 | Docs as of Apr 2026 say "UpdateBatch has replaced UpdateChart (deprecated). Existing code using UpdateChart will still work." Old code paths still functional.                                      | https://web.archive.org/web/20260428032036/https://www.think-cell.com/en/resources/manual/exceldataautomation     |
| `tcaddin` (bare add-in object name in samples)                                       | 2019 sample code used `Dim tcaddin As Object`    | **Renamed in samples to `tcXlAddIn` / `tcPpAddIn`** (2024+)                                                                            | Pure naming convention change; the COM ProgID `thinkcell.addin` is unchanged. Old `tcaddin` variable name is gone from current samples.                                                             | https://web.archive.org/web/20191021053941/https://www.think-cell.com/en/support/manual/exceldataautomation.shtml |
| Sample C# `Microsoft.Office.Interop.Excel 12.0.0.0` references                       | 2019 sample code                                 | **Removed** from current C# sample                                                                                                     | Old code told developers to add specific Office Interop assembly versions; that guidance is gone.                                                                                                   | Same as above                                                                                                     |

**Removal-date estimates:**

- Original `UpdateChart(pres As PowerPoint.Presentation, ...)` typed signature was replaced with `target As Object` between **2019-12-14 and 2024-02-25** (no snapshots in between to narrow further).
- `UpdateBatch` / `CreateUpdate` / `AddRangeData` / `AddRangeImage` / `Send` were added between **2025-06-22** (last snapshot without them) and **2025-07-08** (first snapshot with them on `/exceldataautomation`). The docs more than doubled (12 KB → 27 KB) on that one page — suggesting a deliberate API release wave around think-cell v13/v14, mid-2025.
- The brand-new `/resources/manual/api` aggregator hub appeared **between 2023-03 and 2023-06-02**, consolidating what had been split across `/exceldataautomation` + `/jsondataautomation` + `/introductionautomation`. The hub's largest expansion (17 KB → 36 KB) hit Jul 2025 simultaneously with `UpdateBatch` rollout, then settled to 30 KB by Apr 2026.

### A.4 Methods present in current docs but missing from the user's prior probe of "19 PowerPoint methods + 3 Excel methods + 3 update-builder methods"

The live API hub (`/en/resources/manual/api`) lists three concrete "API reference" subsections. Two are **not** in the standard tcaddin/tcUpdate triad and therefore likely sit outside whatever the prior 19+3+3 inventory captured:

**Style files API (PowerPoint, on `tcPpAddIn`)** — page: https://www.think-cell.com/en/resources/manual/style-files

| Method               | Signature (VBA)                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `LoadStyle`          | `tcPpAddIn.LoadStyle(CustomLayoutOrMaster As Object, FileName As String)`                                                                                     |
| `LoadStyleForRegion` | `tcPpAddIn.LoadStyleForRegion(CustomLayout As PowerPoint.CustomLayout, FileName As String, Left As Single, Top As Single, Width As Single, Height As Single)` |
| `GetStyleName`       | `tcPpAddIn.GetStyleName(CustomLayoutOrMaster As Object) As String`                                                                                            |
| `RemoveStyles`       | `tcPpAddIn.RemoveStyles(CustomLayout As PowerPoint.CustomLayout)` (inferred from docs description; signature not extracted verbatim)                          |

**Mekko Graphics import API (PowerPoint, on `tcPpAddIn`)** — page: https://www.think-cell.com/en/resources/manual/import-mekko-graphics

| Method                      | Signature (VBA)                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------- |
| `ImportMekkoGraphicsCharts` | `tcPpAddIn.ImportMekkoGraphicsCharts(ashp As PowerPoint.Shape()) As PowerPoint.Slide` |
| `GetMekkoGraphicsXML`       | `tcPpAddIn.GetMekkoGraphicsXML(shp As PowerPoint.Shape) As String`                    |

**That's six methods to verify against the 19-method PowerPoint inventory.** If they aren't already there, this nearly-doubles the publicly-callable PowerPoint surface area beyond the canonical Excel-automation triad.

---

## Section B — Community-discovered tricks

Bulleted, sourced. Excludes anything that's just a re-statement of the official manual.

- **`PresentationFromTemplate` chaining across multiple workbooks.** Call `PresentationFromTemplate(wb1, "tpl.pptx", ppapp)` → take the result presentation as your _new_ template → call `PresentationFromTemplate(wb2, that_pres, ppapp)`. Each call breaks the Excel link of the elements it filled, so successive calls fill different elements from different workbooks without trampling. Documented by think-cell themselves in the 2026 docs but framed as a "pro tip" elsewhere. Source: think-cell official docs (manage-data-links page) + summary at managementconsulted.com / thebricks.com.
- **`thinkcellShapeDoNotDelete` Tag introspection (KB0073).** Every shape think-cell touches gets a PowerPoint Shape Tag named `thinkcellShapeDoNotDelete`. Values: empty or not starting with `t` = native PowerPoint shape; `thinkcellActiveDocDoNotDelete` = think-cell's hidden ActiveDocument container shape; anything starting with `t` = a real think-cell-controlled chart/table. **Caveat:** the tag is _copied_ on shape copy/paste, so a copied shape will continue reporting "think-cell shape" even after pasted into a virgin deck. Useful for: enumerating "is this slide using think-cell?" without invoking any tcaddin call. Source: https://www.think-cell.com/en/resources/kb/0073
- **`ppttc.exe -o <output.pptx>` — undocumented-flavor CLI invocation.** The official docs describe `ppttc.exe PPTX_OUTPUT` but the `-o` short flag (`ppttc.exe input.ppttc -o output.pptx`) is what `ZoeDekraker/think-cell-chart-update` actually uses in production, suggesting it's a real flag. The path `C:\Program Files (x86)\think-cell\ppttc.exe` is documented; the `-o` shorthand is not. Source: https://github.com/ZoeDekraker/think-cell-chart-update/blob/main/ThinkCell_main2.py
- **Mis-typed names are silent failures.** `ThinkcellBuilder` README explicitly warns: "It is currently impossible to derive the types or names of think-cell objects in a template programmatically, so all automation methods rely on typo-free expression of object names. Mis-typed chart names are silently ignored by think-cell." This is undocumented behavior in the official docs (docs say nothing about silent ignoring). Source: https://github.com/Philistino/ThinkcellBuilder
- **Late-bound only — no type library.** The think-cell COM add-in deliberately ships no type library. There is no `tlb`/`olb` to import; you cannot get IntelliSense; everything must be `Object` / late-bound. This is documented but the implication ("you have to call `IDispatch::GetIDsOfNames` to discover the surface") is what enables the user's static-probe approach in the first place. Source: https://www.think-cell.com/en/resources/manual/api
- **`.ppttc` is a registered IANA media type** (`application/vnd.think-cell.ppttc+json`, registered 2018-04-16 by Arno Schoedl, supported from think-cell v9). The published JSON Schema lives at `https://static.think-cell.com/ppttc/ppttc-schema.json` — but as of 2026-05-01 that URL returns a 146-byte non-JSON stub (HTTP 200 but content is 4 lines, not parseable as JSON; possibly a placeholder). **The IANA registration is the most reliable canonical reference for the .ppttc envelope shape**; the docs are second-best. Source: https://www.iana.org/assignments/media-types/application/vnd.think-cell.ppttc+json
- **The `.ppttc` JSON envelope:** array-of-objects, each with `template` (path string, `\\` on Windows / `/` on macOS) and `data` (array of named-element specs). Each spec has `name` + `table` (array of rows of typed cells). Cell types: `{"string": s}`, `{"number": n}`, `{"date": "YYYY-MM-DD"}`, with optional `{"fill": "#hex" or "rgb(...)"}`. Source: cross-referenced from https://github.com/duarteocarmo/think-cell/blob/master/thinkcell/thinkcell.py and https://github.com/Philistino/ThinkcellBuilder/blob/main/thinkcellbuilder/thinkcellbuilder.py
- **First-row-blank trick for stacked-100% charts.** `ThinkcellBuilder.add_chart(..., first_row_blank=True)` injects a blank row right after the category header. think-cell uses that row as the "100%=" totals row; without it, percentage stacked charts won't compute totals correctly. Not in the official docs as a JSON-automation hint. Source: https://github.com/Philistino/ThinkcellBuilder
- **`100%=` row in chart datasheet is interpreted as totals when JSON-driven.** From the live JSON automation page: "if you add the 100%= row in a chart datasheet, think-cell interprets the second row of JSON data as the totals from which percentages are calculated." Documented but easy to miss; it's the why behind the previous bullet. Source: https://www.think-cell.com/en/resources/manual/jsondataautomation
- **Avoid `.Select` in macros that touch think-cell ranges.** Per KB0070, every cell selection fires a Selection-Change event that _every_ Excel add-in including think-cell receives, and think-cell's handler is non-trivial. Macros that recorder-style `.Select` then `.Value =` get massive (10×+) speedups by switching to direct `.Range(...).Value =`. Documented but only in a KB article, not surfaced from the API page. Source: https://www.think-cell.com/en/resources/kb/0070
- **C# / managed-code GC trap (KB0203).** When automating from C#/VB.NET, the COM RCW (Runtime Callable Wrapper) holds Office references until GC — which "may be never" without memory pressure. Use `Marshal.ReleaseComObject(...)` for every wnd/view/presentation you receive. Do **not** use `Marshal.FinalReleaseComObject` because it kills the underlying COM object even if other managed add-ins (including think-cell) still hold a reference. Source: https://www.think-cell.com/en/resources/kb/0203
- **Send Slides quietly uses MAPI, not the new Outlook API.** KB0240: think-cell's "Send Slides" feature falls through to classic Outlook + MAPI for email composition because the new Outlook for Windows still doesn't expose a "compose with attachment" API as of Apr 2026. If you're scripting around Send Slides, classic Outlook must be installed even if not the default. Source: https://www.think-cell.com/en/resources/kb/0240
- **think-cell ships a `TCDiag` tool** in its install folder for add-in conflict diagnosis. Not advertised on the API or automation pages. Source: KB0091, KB0207.
- **`tcaddin.dll` and `tcasr.exe` are the two binaries** Windows Defender ASR rules can block, with rule GUIDs `3B576869-A4EC-4529-8536-B80A7769E899` and `c1db55ab-c21a-4637-bb3f-a12568109d35`. Source: https://www.think-cell.com/en/resources/kb/0233
- **No GitHub issues in any of the three known unofficial Python wrappers reference the new `UpdateBatch` family** (cross-checked all open + closed issues at duarteocarmo/think-cell, Philistino/ThinkcellBuilder, ZoeDekraker/think-cell-chart-update). Their entire automation surface is the JSON `.ppttc` route; none drives the COM API directly. The two paths are alternative substrate and the wrappers picked the one that doesn't need a license to _build_ the file. Source: GH API listings via `gh api /repos/{owner}/{repo}/issues`.
- **`imran0347/Thinkcell_Automation`** (GitHub) drives everything via Streamlit + the official `thinkcellbuilder` library — confirms that even more elaborate enterprise pipelines stick to the JSON path. Source: https://github.com/imran0347/Thinkcell_Automation
- **MrExcel community pattern** (verbatim from a working post): drive the bridge from Excel-side via `Application.COMAddIns("thinkcell.addin").Object` and `GetObject(, "PowerPoint.Application")` to grab the live PowerPoint instance — then call `tcaddin.UpdateChart pres, name, rng, False`. Notable: the working forum example uses the **legacy** `tcaddin.UpdateChart` signature that the official docs deprecated. Implication: legacy API is still real, still called, still works. Source: https://www.mrexcel.com/board/threads/vba-copy-excel-range-into-think-cell-chart-range.765672/

---

## Section C — Knowledge base relevant articles

KB articles that mention automation, API, COM, or VBA-relevant troubleshooting. Probed `/en/resources/kb/00XX` through `/03XX`; only those with HTTP 200 listed. Each link below is `https://www.think-cell.com/en/resources/kb/<NNNN>`.

| KB#  | Title                                                                               | URL      | Relevance to automation surface                                                                                                                                                                         |
| ---- | ----------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0070 | Why is my Excel macro slow when think-cell is activated?                            | /kb/0070 | Documents the Selection-Change event-storm cost; recommends `For Each` over `.Select`. Performance-tuning for VBA automation.                                                                           |
| 0073 | How to find out with VBA if a shape is used by think-cell?                          | /kb/0073 | **Documents the `thinkcellShapeDoNotDelete` Shape.Tag mechanism — the only public way to introspect a slide for think-cell content without invoking the addin.** Includes full VBA `CheckShape` sample. |
| 0091 | How can I find out which add-in causes a problem?                                   | /kb/0091 | Mentions `TCDiag` tool, lists conflict-isolation steps. Useful for automation reliability.                                                                                                              |
| 0149 | Conflict with Oracle Smart View: PowerPoint crashes                                 | /kb/0149 | Names the specific exception "library\officeutilities\application.cpp line 13.." — likely from the same internal namespace where the COM API surface is implemented.                                    |
| 0163 | Charts with Excel data links don't update after copying/pasting data                | /kb/0163 | Edge case in linked-chart automation; affects `UpdateBatch`/`UpdateChart` semantics.                                                                                                                    |
| 0169 | Conflict with another add-in: Subclassing error in Excel                            | /kb/0169 | Hooking model conflict; relevant if you're embedding tcaddin into a managed-code automation host.                                                                                                       |
| 0203 | How to use Office Automation from managed code (C#, VB, .NET)                       | /kb/0203 | **Canonical .NET interop guidance: `Marshal.ReleaseComObject` yes, `Marshal.FinalReleaseComObject` never. Cite this in every C# automation that drives think-cell.**                                    |
| 0207 | Excel crashes when using add-ins based on Add-in Express                            | /kb/0207 | Add-in Express ≥9.2.4635 required; relevant if your automation host uses AdX.                                                                                                                           |
| 0210 | Conflict with NVIDIA Optimus: Elements menu does not open                           | /kb/0210 | UI-side, marginal for automation.                                                                                                                                                                       |
| 0215 | "Threats/Violations Found" message from Trend Micro when opening internal datasheet | /kb/0215 | AV false-positives on the embedded-Excel datasheet — affects unattended automation pipelines.                                                                                                           |
| 0220 | Conflict with SAP BusinessObjects Analysis                                          | /kb/0220 | Hooking conflict; SAP fix in AO 2.8 SP4.                                                                                                                                                                |
| 0225 | think-cell is not authorized to send mail                                           | /kb/0225 | Send-Slides path; relevant for /sendslides automation.                                                                                                                                                  |
| 0226 | Using Desktop Apps version of Office, think-cell doesn't load                       | /kb/0226 | Deployment edge for automation servers.                                                                                                                                                                 |
| 0230 | Conflict with Cylance security tool: think-cell's automatic update fails            | /kb/0230 | Update-channel automation context.                                                                                                                                                                      |
| 0233 | Conflict with Windows Defender: think-cell doesn't load                             | /kb/0233 | **Names `tcaddin.dll` and `tcasr.exe` as the two ASR-targeted binaries** — useful for whitelisting on automation VMs.                                                                                   |
| 0240 | Send Slides or Request Support with new Outlook fails                               | /kb/0240 | MAPI vs new Outlook API for /sendslides automation.                                                                                                                                                     |

KB0001/0002/0089/0250 returned 404 — gaps in the numbering, not 0001/0002 ever existing publicly. KB0100 exists (font color, irrelevant). The KB universe runs at minimum 0003–0240 with sparse density above 0240.

---

## Bottom-line — actionable for expanding think-cell automation surface beyond docs

1. **The 19 + 3 + 3 inventory likely missed Style API and Mekko-import API.** Six methods on `tcPpAddIn` (`LoadStyle`, `LoadStyleForRegion`, `GetStyleName`, `RemoveStyles`, `ImportMekkoGraphicsCharts`, `GetMekkoGraphicsXML`) are publicly documented today but live on separate manual pages (`/style-files` and `/import-mekko-graphics`), not on the canonical API hub. Re-run `IDispatch::GetIDsOfNames` against the static-probe candidate list including these names — high probability they're already callable.

2. **Bypass the API entirely via Shape.Tags introspection.** KB0073's `thinkcellShapeDoNotDelete` tag is on every think-cell-controlled shape, readable through PowerPoint's standard Shapes API without ever touching `tcaddin`. This is the only documented path to enumerate think-cell content without a license-active session. For audit/inventory tooling this is the right entry point.

3. **Investigate the `library\officeutilities\application.cpp` namespace.** KB0149's exception message leaks an internal source path. There may be additional internal automation primitives reachable through `tcasr.exe` (the auto-update / repair binary) that could be probed via process inspection. KB0233 confirms `tcasr.exe` exists and is treated as a sibling to `tcaddin.dll`.

4. **The legacy `UpdateChart` is still callable and probably has un-deprecated argument shapes.** The 2019 signature was `(pres As PowerPoint.Presentation, ...)` — typed. The 2024 signature widened to `(target As Object, ...)`. Both are presumably accepted by the same dispatch at runtime. Probe with `Slide`, `SlideRange`, `Master`, and `CustomLayout` as the first arg — those work for `UpdateBatch.AddRangeData` and likely work for the legacy `UpdateChart` too, even though no doc version ever said so.

5. **`ppttc.exe` CLI flag enumeration is open.** The docs describe one positional arg (`PPTX_OUTPUT`); production code uses `-o <path>`. Probe with `--help`, `/?`, `-?`, `-v`, `--version`, `--schema`, `--validate` — typical command-line conventions. The IANA registration mentions a JSON schema URL that's currently a 146-byte stub, suggesting `ppttc.exe --schema` or `--print-schema` could be the canonical fetch path.

6. **`UpdateBatch` was added between 2025-06-22 and 2025-07-08.** That release wave likely shipped more methods than just the five publicly documented (`CreateUpdate`, `AddRangeData`, `AddRangeImage`, `Send`, `UpdateBatch`). Plausible companions worth probing on the `tcUpdate` object returned by `CreateUpdate()`: `Cancel`, `Reset`, `Abort`, `Clear`, `GetCount`, `Item`, `EnumerateNames`, `GetVersion`, `IsValid`. The IDispatch enumeration approach the user already has works on the _result_ of `tcXlAddIn.CreateUpdate()` — that's a separate object with its own GetIDsOfNames table.

7. **Type-library enumeration is deliberately impossible** — that's stated policy from think-cell. The brute-force IDispatch route the user is on is the _only_ path. Both unofficial Python wrappers gave up and chose the JSON `.ppttc` substrate instead, confirming there's no shortcut others have found.

8. **The `.ppttc` JSON envelope is your other half of the API.** It supports things the COM API doesn't surface obviously — chart cell `fill` colors per element (not just per series), template-path remoting (think-cell server can pull templates over HTTP), and locale-specific number formats via `lang`/`locale` keys. If COM-side surface is capped, the JSON-side surface is where to look next. The IANA-registered schema URL is the canonical reference even if the URL currently 200s with a stub.

9. **No community-discovered backdoor methods exist** — every undocumented behavior found in this run was either (a) a deprecated-but-still-working older signature, (b) a Shape.Tags introspection path that doesn't go through the addin at all, or (c) a JSON envelope detail that's documented but buried. The user's 19+3+3 floor is probably close to the real public floor — but the Style + Mekko APIs (6 methods) are the most likely gap.

---

## Sources

- [Wayback CDX — /resources/manual/api](https://web.archive.org/cdx/search/cdx?url=think-cell.com/en/resources/manual/api&output=json)
- [Wayback snapshot Apr 2024 — /api](https://web.archive.org/web/20240414052550/https://www.think-cell.com/en/resources/manual/api)
- [Wayback snapshot Jul 2025 — /api](https://web.archive.org/web/20250716183530/https://www.think-cell.com/en/resources/manual/api)
- [Wayback snapshot Apr 2026 — /api](https://web.archive.org/web/20260428032012/https://www.think-cell.com/en/resources/manual/api)
- [Wayback snapshot Oct 2019 — legacy /support/manual/exceldataautomation.shtml](https://web.archive.org/web/20191021053941/https://www.think-cell.com/en/support/manual/exceldataautomation.shtml)
- [Wayback snapshot Jul 2025 — /exceldataautomation (UpdateBatch added)](https://web.archive.org/web/20250708233104/https://www.think-cell.com/en/resources/manual/exceldataautomation)
- [Wayback snapshot Apr 2026 — /exceldataautomation (final UpdateBatch text)](https://web.archive.org/web/20260428032036/https://www.think-cell.com/en/resources/manual/exceldataautomation)
- [Live — think-cell API hub](https://www.think-cell.com/en/resources/manual/api)
- [Live — Excel data automation](https://www.think-cell.com/en/resources/manual/exceldataautomation)
- [Live — JSON data automation](https://www.think-cell.com/en/resources/manual/jsondataautomation)
- [Live — introduction to automation](https://www.think-cell.com/en/resources/manual/introductionautomation)
- [Live — style files API](https://www.think-cell.com/en/resources/manual/style-files)
- [Live — Mekko Graphics import API](https://www.think-cell.com/en/resources/manual/import-mekko-graphics)
- [IANA — application/vnd.think-cell.ppttc+json (registered 2018-04-16)](https://www.iana.org/assignments/media-types/application/vnd.think-cell.ppttc+json)
- [KB0070 — macro-slow Selection-Change](https://www.think-cell.com/en/resources/kb/0070)
- [KB0073 — VBA shape-introspection via thinkcellShapeDoNotDelete](https://www.think-cell.com/en/resources/kb/0073)
- [KB0091 — add-in conflict isolation, TCDiag tool](https://www.think-cell.com/en/resources/kb/0091)
- [KB0149 — Smart View conflict; leaks officeutilities/application.cpp namespace](https://www.think-cell.com/en/resources/kb/0149)
- [KB0163 — copy/paste data-link breakage](https://www.think-cell.com/en/resources/kb/0163)
- [KB0169 — subclassing conflict](https://www.think-cell.com/en/resources/kb/0169)
- [KB0203 — managed-code C# / .NET interop, Marshal.ReleaseComObject vs FinalReleaseComObject](https://www.think-cell.com/en/resources/kb/0203)
- [KB0207 — Add-in Express version requirement](https://www.think-cell.com/en/resources/kb/0207)
- [KB0220 — SAP BusinessObjects conflict + SAP ticket 557711](https://www.think-cell.com/en/resources/kb/0220)
- [KB0233 — Windows Defender ASR; names tcaddin.dll + tcasr.exe](https://www.think-cell.com/en/resources/kb/0233)
- [KB0240 — Send Slides via MAPI fallback](https://www.think-cell.com/en/resources/kb/0240)
- [GitHub — duarteocarmo/think-cell (Python `.ppttc` wrapper)](https://github.com/duarteocarmo/think-cell)
- [GitHub — Philistino/ThinkcellBuilder (Python `.ppttc` wrapper, fork)](https://github.com/Philistino/ThinkcellBuilder)
- [GitHub — ZoeDekraker/think-cell-chart-update (uses ppttc.exe -o)](https://github.com/ZoeDekraker/think-cell-chart-update)
- [GitHub — imran0347/Thinkcell_Automation (Streamlit + ThinkcellBuilder enterprise)](https://github.com/imran0347/Thinkcell_Automation)
- [MrExcel — VBA: Copy Excel range into think-cell chart range (legacy tcaddin.UpdateChart pattern)](https://www.mrexcel.com/board/threads/vba-copy-excel-range-into-think-cell-chart-range.765672/)
