# think-cell Automation API — Source Map

Date: 2026-05-01
Driver: Claude Opus 4.7 (deep API/manual link probe)
Companion: [`automation-api-surface.md`](automation-api-surface.md)

This is the structured link graph of every official source that informs the
SimCorp think-cell automation factory. It exists so future agents do not
re-discover what is already known and can tell, at a glance, whether a given
manual section is **production**, a **proof candidate** for the next probe,
**reference only**, **blocked**, or **not applicable** to SimCorp.

Every entry below is sourced from the official think-cell manual or from
Microsoft Learn pages explicitly linked from that manual. Third-party blogs,
GitHub samples, and StackOverflow threads are listed separately at the bottom
as `non-authoritative reference only` and are NOT encoded as factory rules.

## Status Legend

| Status            | Meaning                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------- |
| `production`      | Currently exercised by the SimCorp pipeline with bound-package and render evidence.      |
| `proof_candidate` | Officially documented; not yet exercised. A specific safe probe is named in the row.     |
| `reference_only`  | Useful background; not directly invokable as automation (UI flows, theory, terminology). |
| `blocked`         | Domain or platform constraint forbids using this lane today.                             |
| `not_applicable`  | Officially documented but irrelevant to SimCorp's directors-deck factory.                |

## think-cell Manual — API Hub Pages

| URL                                                                                                        | Why it matters                                                                                                                                                                              | Factory implication                                                                                                                         | Status            | Probe / Action                                                                                                                                  |
| ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| <https://www.think-cell.com/en/resources/manual/api>                                                       | Authoritative entry point. Confirms Windows-only, late binding, single `thinkcell.addin` ProgID, web-add-in block, and the four API areas (Excel/Style/Mekko/JSON).                         | Encode entry-point + late-binding rule into every probe and every automation script.                                                        | `production`      | Already encoded in `scripts/thinkcell_programmatic_probe.ps1` and surfaced in capability verdicts.                                              |
| <https://www.think-cell.com/en/resources/manual/introductionautomation>                                    | Names the two automation lanes (Excel-linked vs. JSON named-element) and the rules for naming chart, table, Harvey ball, checkbox, automation text field, table image.                      | Confirms the LAND seed naming contract: every named element in the seed must be set via the mini toolbar, not invented in JSON.             | `production`      | LAND seed proof loop already runs (42/42).                                                                                                      |
| <https://www.think-cell.com/en/resources/manual/exceldatalinks>                                            | UI-side counterpart of the Excel COM API. Documents how named ranges/links translate into AddRangeData/AddRangeImage call shape.                                                            | Anchor for "Use Datasheet Fill" rule that maps `fill` cells in `.ppttc` to actual chart segment colors.                                     | `reference_only`  | None; UI path, not automation entry. Cited in source map as the boundary the API replaces.                                                      |
| <https://www.think-cell.com/en/resources/manual/exceldataautomation>                                       | Full COM contract for `tcXlAddIn` and `tcUpdate`: PresentationFromTemplate, UpdateBatch, deprecated UpdateChart, target enum, transposed semantics, formatting rules.                       | Encodes the production update lane and locks `UpdateChart` out of the factory as deprecated.                                                | `production`      | Already proven for `CreateUpdate`/`AddRangeData`/`AddRangeImage`/`Send`. `PresentationFromTemplate` remains a proof candidate (see row below).  |
| <https://www.think-cell.com/en/resources/manual/exceldataautomation#sect_presentationfromtemplatefunction> | Single-call template + Excel sheet → presentation. Breaks Excel links on updated elements; supports multi-workbook chaining.                                                                | Could replace `.ppttc` entirely IF the SimCorp seed ever moves to live Excel-linked elements. Today it does not, so JSON wins.              | `proof_candidate` | Probe: open `template.pptx` + `data.xlsx` from /ppttc folder, call PresentationFromTemplate against tcXlAddIn, assert returned Presentation.    |
| <https://www.think-cell.com/en/resources/manual/exceldataautomation#sect_updatebatch>                      | Documents `CreateUpdate` → `AddRangeData(Target, Name, Range, Transposed)` / `AddRangeImage(Target, Name, Range)` → `Send`. Target enum: Presentation/SlideRange/Slide/Master/CustomLayout. | Production lane for SimCorp table-image refresh.                                                                                            | `production`      | Already proven by 19/19 table-image donor binding evidence.                                                                                     |
| <https://www.think-cell.com/en/resources/manual/exceldataautomation#sect_updatechartfunction>              | Deprecated single-chart update; superseded by UpdateBatch.                                                                                                                                  | Lock-out: must NOT be invoked. Probe records its presence but classifies it as deprecated.                                                  | `not_applicable`  | None.                                                                                                                                           |
| <https://www.think-cell.com/en/resources/manual/jsondataautomation>                                        | `.ppttc` shape, cell types, ppttc.exe CLI, sample.html browser flow, tcserver POST flow with MIME `application/vnd.think-cell.ppttc+json`.                                                  | Production wrapper. Encodes the `ppttc <input> -o <output>` invocation and the `tcserver` HTTP MIME contract for any future remote service. | `production`      | ppttc.exe proven by latest probe (banner + bound deck). tcserver remains a separate proof candidate (see row below).                            |
| <https://www.think-cell.com/en/resources/manual/style-files>                                               | Full XML structure of style files plus the four-method Style API (LoadStyle, LoadStyleForRegion, GetStyleName, RemoveStyles) and version compat rules.                                      | Style API governs SimCorp's brand-style layer if/when SimCorp ever swaps in a SimCorp-branded `.xml` style file via automation.             | `proof_candidate` | Runtime proof completed in `state/thinkcell_bridge/programmatic_lab/20260501-190411/`; all Style API steps passed on a transient presentation. Production brand use still needs a separate SimCorp style decision record. |
| <https://www.think-cell.com/en/resources/manual/import-mekko-graphics>                                     | `ImportMekkoGraphicsCharts(Shape[]) -> Slide` and `GetMekkoGraphicsXML(Shape) -> string`. Backup slide auto-inserted. `E_INVALIDARG (0x80070057)` on non-Mekko shapes.                      | Only relevant if SimCorp ever inherits a deck with Mekko Graphics charts. SimCorp uses think-cell native Mekko (QTR07) directly.            | `not_applicable`  | None unless a real Mekko Graphics donor PPTX shows up in `state/thinkcell_bridge/mekko_samples/`.                                               |

## Microsoft Learn — Cited Developer References

These links are referenced verbatim by the official API page and are required
context for any developer setup section. Status is `reference_only` for all of
them — they document Microsoft platform behavior that constrains how SimCorp
interacts with `tcPpAddIn` and `tcXlAddIn`.

| URL                                                                                                                                     | Why it matters                                                                         | Factory implication                                                                                                                                      |
| --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| <https://learn.microsoft.com/en-us/previous-versions/office/troubleshoot/office-developer/binding-type-available-to-automation-clients> | Defines early vs. late binding in Office Automation.                                   | Locks the rule: **always declare add-in vars as `Object` (VBA) or `dynamic`/`var` (C#)**. Never bind to a think-cell type library.                       |
| <https://learn.microsoft.com/office/vba/language/reference/user-interface-help/option-explicit-statement>                               | `Option Explicit` discipline.                                                          | Encode in any VBA example we ship: `Option Explicit` at top of every module.                                                                             |
| <https://learn.microsoft.com/dotnet/csharp/programming-guide/types/using-type-dynamic>                                                  | C# `dynamic` keyword behavior.                                                         | Encode in any C# example: `var tcXlAddIn = ...` or `dynamic tcXlAddIn = ...`. No COM type library reference for think-cell.                              |
| <https://learn.microsoft.com/en-us/dotnet/framework/interop/how-to-add-references-to-type-libraries>                                    | How to add Microsoft Office type libraries (Excel/PowerPoint/Office Object Libraries). | Required when the automation host uses early-bound Office types (e.g., `Excel.Workbook`, `PowerPoint.Presentation`). think-cell itself stays late-bound. |
| <https://learn.microsoft.com/previous-versions/visualstudio/visual-studio-2013/ee317478(v=vs.120)>                                      | Embed Interop Types option for Office version compatibility.                           | Default ON. Keep ON in any C# automation host project so a single binary works against multiple Office versions.                                         |
| <https://learn.microsoft.com/dotnet/framework/interop/how-to-map-hresults-and-exceptions>                                               | How COM HRESULTs map to .NET exceptions.                                               | Required to handle Mekko's `E_INVALIDARG (0x80070057)` and any other think-cell HRESULT cleanly in C# automation hosts.                                  |
| <https://learn.microsoft.com/visualstudio/vsto/configuring-a-computer-to-develop-office-solutions?view=vs-2022>                         | VSTO/Office Developer Tools install (overview).                                        | Not required for headless automation. Required only if SimCorp ever ships a VSTO add-in that wraps think-cell. Currently out of scope.                   |
| <https://learn.microsoft.com/visualstudio/vsto/how-to-configure-a-computer-to-develop-office-solutions?view=vs-2022>                    | VSTO setup how-to.                                                                     | Same as above; cited here for completeness.                                                                                                              |
| <https://learn.microsoft.com/office/vba/api/powerpoint.customlayout>                                                                    | PowerPoint `CustomLayout` object model.                                                | Required for `LoadStyleForRegion` and `RemoveStyles`: both take a `CustomLayout` reference, not a `Master`.                                              |
| <https://learn.microsoft.com/office/vba/api/powerpoint.master>                                                                          | PowerPoint `Master` object model.                                                      | Required for `LoadStyle` and `GetStyleName` on the master. **`RemoveStyles` cannot target a master** (manual rule).                                      |

## think-cell Manual — Style File Schema References

The Style API takes XML files validated against the bundled XSD set. Future
proof rows must be able to find the correct sample style file before invoking
`LoadStyle` on a temp presentation.

| URL or Path                                                                    | Why it matters                                                       | Factory implication                                                                        | Status            |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------- |
| <https://www.think-cell.com/en/resources/manual/style-files#sect_xmlstructure> | Full XML structure with required ordering, fill/line/marker schemes. | Reference for any future SimCorp-branded style XML.                                        | `reference_only`  |
| `/Library/Application Support/Microsoft/think-cell/styles/`                    | Local installed showcase + default styles.                           | Source of safe inputs for `LoadStyle` / `LoadStyleForRegion` proof on a temp presentation. | `production`      |
| `/Library/Application Support/Microsoft/think-cell/xml-schemas/tcstyle.xsd`    | XSD for style validation.                                            | Useful for any in-process linting if SimCorp ever authors custom styles.                   | `reference_only`  |

## think-cell Manual — JSON Automation Surface References

| URL or Path                                                                 | Why it matters                                                          | Factory implication                                                                                                                            | Status            |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| <https://www.think-cell.com/en/resources/manual/jsondataautomation>         | Full ppttc + tcserver contract.                                         | Production lane.                                                                                                                               | `production`      |
| `/Library/Application Support/Microsoft/think-cell/ppttc/ppttc-schema.json` | Local JSON Schema for `.ppttc` validation.                              | Future basis for JA-02 (schema validation backlog item).                                                                                       | `proof_candidate` |
| `/Library/Application Support/Microsoft/think-cell/ppttc/sample.ppttc`      | Reference payload exercising every cell type.                           | Use as smoke test for any `.ppttc` validator we ship.                                                                                          | `production`      |
| `/Library/Application Support/Microsoft/think-cell/ppttc/template.pptx`     | Reference template with named elements (`SlideTitle`, `LeftChart`, ...) | Use to prove `PresentationFromTemplate` end-to-end without touching the SimCorp LAND seed.                                                     | `proof_candidate` |
| `/Library/Application Support/Microsoft/think-cell/ppttc/sample.html`       | Browser → `.ppttc` download → think-cell handler flow.                  | Pattern for any future SimCorp web tool. Not currently in scope.                                                                               | `reference_only`  |
| `tcserver.exe` (next to ppttc.exe in install root)                          | HTTP server: `POST` `application/vnd.think-cell.ppttc+json` → `.pptx`.  | Could power a server-side render service. Out of scope today; proof candidate is **inventory only** (path/version), not registration or start. | `proof_candidate` |

## Adoption Matrix — Current SimCorp Disposition

| Lane                                  | Status               | Why                                                                                                                                                                                                             |
| ------------------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ppttc.exe` (CLI)                     | `production`         | The SimCorp deck factory binds named elements in the LAND seed via `ppttc.exe` end-to-end with bound-package + render assertions.                                                                               |
| Excel COM `UpdateBatch` (table-image) | `production`         | The SimCorp factory uses `tcUpdate.AddRangeImage`/`AddRangeData`/`Send` for the 19 table-image donors that drive QTR10/QTR11/QTR12.                                                                             |
| Excel COM `PresentationFromTemplate`  | `proof_candidate`    | Documented and observed on the COM surface. Could replace bespoke `.ppttc` for Excel-linked seeds. No current SimCorp need; revisit if a fully Excel-linked seed gets authored.                                 |
| Style API (Load/Remove/GetStyleName)  | `proof_candidate`    | Runtime-proven on a transient presentation using installed showcase style in `20260501-190411`; still not production for SimCorp-branded decks until a brand-style decision record exists.                     |
| Mekko Graphics import API             | `not_applicable`     | SimCorp authors think-cell-native Mekko charts (QTR07). No SimCorp deck imports from Mekko Graphics. Re-enable only if a Mekko Graphics donor PPTX is ever added under `state/thinkcell_bridge/mekko_samples/`. |
| `tcserver` HTTP service               | `proof_candidate`    | Inventory only today. No `Register URL`, no service start, no UAC prompt. Promote only after a SimCorp leadership decision authorizes a server-side render service.                                             |
| Office Web Add-ins                    | `blocked` (platform) | Web add-ins cannot reach Office COM add-ins per the API page. Hard block.                                                                                                                                       |
| Native editable think-cell tables     | `blocked` (domain)   | Manual binding fails to bind cleanly without PowerPoint repair prompts. Use the Excel COM `AddRangeImage` lane instead.                                                                                         |
| Programmatic chart creation           | `not_found`          | No `Create*Chart` / `Insert*Chart` method exists on the COM surface. Donor-and-rename remains the only chart-creation lane.                                                                                     |

## Probe Coverage Map

For each `proof_candidate` above the corresponding probe / artifact lives at:

| Candidate                                                                        | Probe location                                                                                                               |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `PresentationFromTemplate`                                                       | Future: extend `scripts/thinkcell_programmatic_probe.ps1` to load `/ppttc/template.pptx` against a synthetic Excel sheet.    |
| Style API (`GetStyleName` / `LoadStyle` / `LoadStyleForRegion` / `RemoveStyles`) | `scripts/thinkcell_programmatic_probe.ps1` -> `Invoke-StyleProofProbe`; latest lab `20260501-190411` records `pass` for all steps in JSON `style_proof`. |
| `ppttc.exe` schema validation (JA-02)                                            | Future Python validator that consumes `/ppttc/ppttc-schema.json`.                                                            |
| `tcserver.exe` inventory                                                         | `scripts/thinkcell_programmatic_probe.ps1` → `Get-TcServerInventory` (added 2026-05-01); results in lab JSON `tcserver`.     |
| Mekko Graphics import                                                            | Blocked at sample stage. Probe records `samples_present=false` and skips invocation.                                         |

## Non-Authoritative References (do NOT encode as factory rules)

These are useful background only. They are NOT used to set probe expectations
or factory verdicts. Promote a row out of this list only after re-confirming
the same fact in the official manual or Microsoft Learn.

- StackOverflow / GitHub samples that wrap `tcXlAddIn.UpdateChart` (deprecated). Already-deprecated by the manual; ignore.
- Third-party VSTO tutorials that hard-code Office 16.0 PIA references. SimCorp uses `dynamic`/late binding instead.
- Blog posts that call `ppttc.exe` with undocumented flags. The manual specifies only `<input>` and `-o <output>`; do not invent flags.

## Hard SimCorp Constraints (Repeat)

- ARR is Land + Expand only via `APTS_Opportunity_ARR__c`.
- Renewal ACV is Renewal only via `APTS_Renewal_ACV__c`.
- Never blend ARR and Renewal ACV.
- Headline EUR figures use FX-converted Salesforce report aggregates, not raw multi-currency SOQL `SUM`.
- The VM is the **update runtime**, not a chart factory.
