# Agent 1 — think-cell Patent Filings

**Mission:** Find patent filings disclosing think-cell's internal architecture for their PowerPoint/Excel automation product.
**Date:** 2026-05-01
**Sources:** Justia Patents, FreePatentsOnline, Google Patents (via web search summaries). WebFetch was denied for this run, so all patent text quoted below is from cached search-engine summaries of the public Justia / FreePatentsOnline pages — not from primary-source PDFs. Re-verify any "Key disclosures" passage against `patents.google.com/patent/US<num>` before quoting in adversarial / legal contexts.

---

## Bottom-line up front

think-cell holds a **small, surgical patent portfolio (≈10 granted US patents + applications)** and the patents are almost entirely about **algorithms** (label placement, page-layout constraint solving, image-based chart-data extraction, agenda synchronization, pattern-driven canvas filling). They are **not architecture-disclosure patents**. None of them describe:

- the OOXML custom-XML-part schema think-cell writes into `.pptx`,
- the COM dispatch surface beyond what is already in `think-cell.com/en/resources/manual/api`,
- the JSON-to-PPTX server pipeline (`/automation`, used in JSON Data Automation),
- the Excel-PowerPoint cross-process linking protocol,
- ribbon callbacks, IDTExtensibility2, or the add-in registration chain,
- chart-shape serialization formats or how state is round-tripped through PowerPoint Save.

**The patents reveal almost nothing about API surface beyond the public docs.** They protect _math_, not _protocol_. The one partial exception is **US10789414 (pattern-based canvas filling)**, which describes a generalized "data sequence + formula sequence + canvas" model that is more abstract than anything in the public manual and hints at how the Excel→PowerPoint binding is conceptualized internally — but it stops well short of disclosing a wire format.

This matches think-cell's well-known posture: their engineers reverse-engineer Office and treat the resulting integration as a trade secret. Patents would force public disclosure, so the integration layer is deliberately kept out of the patent estate. **For deeper API surface discovery, patents are a dry hole; the productive vectors are (a) `pptx` binary inspection of `customXml/` parts, (b) COM TLB introspection of `tcPpAddIn` / `tcXlAddIn`, and (c) network capture of the `/automation` JSON server.**

---

## Total patent count

**~10 US patents/applications** identifiable as assigned to think-cell Software GmbH, plus the EP/PCT family members for several. The two German operating entities (`think-cell Software GmbH & Co. KG`, `think-cell Sales GmbH & Co. KG`, `think-cell Operations GmbH`) and the post-2021 Cinven holding structure do **not** appear as separate patent assignees on Justia — all filings are under "Think-Cell Software GmbH". No patent applications surfaced from 2021–2025; the public-facing patent activity appears to have slowed sharply after Cinven's 2021 majority investment.

---

## Patent table

| #   | Patent / Pub #                               | Title                                                                | Filing / Issue                       | Inventors                                                       | Status      | Abstract summary                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | API-discovery relevance                                                                                                                                                                                                                                                                      |
| --- | -------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------ | --------------------------------------------------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **US 7,478,328 B2**                          | Method of entering a presentation into a computer                    | Filed 2004-02-17 / Issued 2009-01-13 | Hannebauer, Schöch, Schödl                                      | Granted     | Dynamic grid: graphical objects added to a logical container (empty slide); grid records constraints; constraint solver auto-lays-out the slide.                                                                                                                                                                                                                                                                                                                                                                                               | **Low–Med.** Discloses the constraint-solver paradigm but not the on-disk representation or COM surface.                                                                                                                                                                                     |
| 2   | **US 7,716,578 B2**                          | Display method (labeled column chart)                                | Filed 2006-09-14 / Issued 2010-05-11 | Theophil, Schoedl, Hannebauer                                   | Granted     | GUI displays labeled column chart with N labels; user edits one label; labeling algorithm regenerates the modified chart.                                                                                                                                                                                                                                                                                                                                                                                                                      | **Low.** Pure UI/algorithm.                                                                                                                                                                                                                                                                  |
| 3   | **US 7,757,179 B2**                          | Display method (labeled scatter chart)                               | Issued 2010-07-13                    | Schödl, Schöch, Hannebauer                                      | Granted     | Same pattern as #2, scatter chart variant.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | **Low.**                                                                                                                                                                                                                                                                                     |
| 4   | **US 8,458,587 B2**                          | Method of entering page layout constraints into a computer           | — / Issued ~2013-06-04               | Theophil, Ziegler, Schödl, Hannebauer                           | Granted     | Container + graphical objects + object gridlines delimiting "important graphical features"; gridline span = where object and gridline overlap or intersect.                                                                                                                                                                                                                                                                                                                                                                                    | **Med.** This is the closest the portfolio gets to an internal data model — gridline-based object representation with span semantics.                                                                                                                                                        |
| 5   | **US 8,847,986 B2** (≈ pub US 2013/0194297)  | Method of solving a set of page layout constraints                   | Issued 2014-09-30                    | Schödl (sole)                                                   | Granted     | Constraints partitioned into groups by type → each transformed into a _resource constraint_ → groups assigned priorities → each group solved simultaneously by a resource-allocation algorithm; under-constrained gridline pairs are detected and an additional constraint inserted before re-solving.                                                                                                                                                                                                                                         | **Med.** Reveals the architecture of think-cell layout's solver pipeline: typed constraint groups + priority + simultaneous resource allocation + iterative repair. Useful for understanding _why_ certain layouts behave as they do, not for API hooking.                                   |
| 6   | **US 10,140,512 B2** (≈ pub US 2018/0211108) | Image analysis method / chart analysis method and system (bar chart) | Filed 2017-01-25 / Issued 2018-11-27 | Schoedl, Schöch, Hannebauer (later cont. adds Lahmann, Nordhus) | Granted     | Receive digital image of bar chart with "o-bars"; provide hypothesis charts each specifying a sequence of "h-bars," a category grouping, and an injective mapping o→h; pick the hypothesis whose h-bars best match the o-bars (position, color, texture).                                                                                                                                                                                                                                                                                      | **Low.** Computer-vision algorithm, no integration surface.                                                                                                                                                                                                                                  |
| 7   | **US 10,331,761 B2**                         | Method for efficient agenda drafting, synchronization and display    | Filed 2010-02-02 / Issued 2019-06-25 | Lahmann, Nordhus, Schodl                                        | Granted     | Visual document elements = agendas + topic boxes; user command (insert/delete/edit) auto-propagates within the same document section, synchronizing all agendas/overviews/topic boxes; synchronized elements are displayed.                                                                                                                                                                                                                                                                                                                    | **Low.** Describes a behavior, not the storage.                                                                                                                                                                                                                                              |
| 8   | **US 10,496,695 B2** (≈ pub US 2017/0351708) | Automated data extraction from scatter plot images                   | Filed 2017-06-05 / Issued 2019-12-03 | Lahmann, Schoedl, Ringenberg                                    | Granted     | Receive image → identify pixel sets (groups of adjacent pixels) → generate per-series templates depicting one data-point symbol → match templates against target image (similarity threshold) → assign matched points to data series → return points. Supports grayscale & multi-channel; uses edge-image derivative for contour mapping.                                                                                                                                                                                                      | **Low.** CV pipeline.                                                                                                                                                                                                                                                                        |
| 9   | **US 10,776,448 B2**                         | Cell-based computing platform                                        | Issued 2020-09-15                    | Schoedl (sole)                                                  | Granted     | Cell-based computing platform "specifically usable for website development and management"; cells respond to external devices/programs/operations such that changes in a cell's value parameter dynamically trigger an external response.                                                                                                                                                                                                                                                                                                      | **Low.** This appears to be an Arno-Schödl-personal-project filing on a generalized reactive-cell model rather than a think-cell-product patent. Possibly the conceptual ancestor of the JSON Data Automation server's update model, but the spec is too abstract to pin to product surface. |
| 10  | **US 10,789,414 B2**                         | Pattern-based filling of a canvas with data and formula              | Issued 2020-09-29                    | Schödl (likely sole)                                            | Granted     | Receive data sequences + formula sequences (formulas reference data values); GUI lets user define a _pattern_ containing data elements and formula elements + their spatial relationship; pattern is applied to a canvas of an electronic document repeatedly, filling canvas cells with values or formulas until one of the sequences is exhausted. Pattern can be authored _directly in the canvas_ via drag-and-drop (no separate design environment). Per-element formatting (font, color, size, background) is captured into the pattern. | **High.** Closest the portfolio gets to disclosing an internal abstraction over the Excel/PowerPoint canvas. See "Key disclosures" below.                                                                                                                                                    |
| 11  | **US 2018/0189248 A1**                       | Automated data extraction from a chart (capture module / system)     | Pub. 2018-07-05                      | Lahmann, Schoedl, Ringenberg                                    | Application | Computer system: processors + screen-capture module + screens. Capture module renders a GUI letting user drag a frame over any on-screen chart — _application-agnostic, local-or-remote_. When the frame goes still, system auto-screenshots, runs image analysis, displays overlay GUI elements indicating identified chart elements; if the user resizes/moves the frame the analysis aborts and restarts on next stable selection.                                                                                                          | **Low–Med.** Discloses the chart-capture tool's UX state machine.                                                                                                                                                                                                                            |

(Patent #6 and #7 are sometimes also indexed under their pre-grant publication numbers — e.g. US 2018/0211108 for #6 and US 2017/0351708 for the scatter-plot family. They are the same inventions.)

### Inventors observed across the portfolio

- **Arno Schödl** (CTO, co-founder) — present on nearly every patent, sole inventor on #5, #9.
- **Markus Hannebauer** (CEO, co-founder) — co-inventor on #1, #2, #3, #4, #6.
- **Sebastian Theophil** — co-inventor on #2 and #4 (the layout / constraint patents). Matches his published HU-Berlin PhD on "Sketching Slides — interactive creation and automatic solution of constrained document layout problems."
- **Volker Christian Schöch** — co-inventor on #1, #3, #6.
- **Valentin Ziegler** — co-inventor on #4 only.
- **Dominik Lahmann, Philipp Nordhus, Jordan Ringenberg** — all on the post-2017 chart-vision / agenda patents (#6 cont., #7, #8, #11). This is the chart-data-extraction sub-team.
- **"Matthias Hofmann"** — _not_ found as a think-cell patent inventor. The hits on Justia for that name are mechanical engineering (underwater turbine sealing systems) and a Boehmert & Boehmert patent attorney — both unrelated.

### Alternative-assignee check

Searched `think-cell Sales GmbH`, `think-cell Operations GmbH`, `think-cell Holding`, post-Cinven holding entities — no patent filings under any of these names. All IP is under **Think-Cell Software GmbH**. The Cinven 2021 announcement explicitly highlighted "valuable and patent-protected IP" as an investment thesis but no new filings appear in 2021–2025 search results.

---

## Key disclosures (high-relevance patents only)

### US 10,789,414 B2 — Pattern-based filling of a canvas with data and formula

This is the most architecturally revealing patent in the portfolio because it abstracts the Excel-data-link mechanism into a formal model.

**Quoted passages (from Justia summary of the granted text):**

> "[A] computer-implemented method that includes receiving one or more data sequences and formula sequences, each formula referencing one or more of the data values; providing a GUI enabling a user to define a pattern including at least one data element representing a data sequence and at least one formula element representing a formula sequence, the GUI enabling the user to define the spatial relationship of the data elements and formula elements in the pattern, applying the pattern on a canvas of an electronic document multiple times, thereby filling canvas elements mapped to a data element with data values and filling canvas elements mapped to a formula element with formulas or formula results, until all data values of one of the data sequences or all formulas of one of the formula sequences have been filled once into the canvas."

> "The GUI … is configured such that the user is allowed to select a canvas element within a block of canvas cells that represents a first sequence and to drop the selected canvas element in the neighborhood of another block of canvas elements that represents a second sequence."

> "The canvas elements of the selected block are analyzed to identify elements comprising data values, which are represented as data sequences, and to identify canvas elements comprising formulas, which are represented as formula sequences."

> "The format of individual canvas elements — such as font color, type and size, background color, and the like — may be used as the format assigned to the element of the pattern generated for representing said data sequence or formula sequence."

**What this implies for API surface beyond the public docs:**

- Internally, the Excel-side data-link object is modeled as **(data sequence) ⊕ (formula sequence) ⊕ (pattern)** — three first-class entities with spatial-relationship metadata.
- Pattern application is **iterative and bounded by sequence exhaustion**, which is consistent with how `AddRangeData` / `UpdateBatch` behave in the public JSON/COM API but more general.
- Format (font, color, size, background) is _part of the pattern_, not separately serialized — so when you reverse-engineer a `.pptx` you should expect formatting to ride alongside the data binding rather than living in a sibling part.

The patent does **not** disclose:

- the on-disk representation of the pattern,
- the COM interface used to author or apply patterns,
- whether patterns survive a Save→Reopen round-trip in pure PowerPoint without the add-in,
- any wire format between Excel and PowerPoint processes.

### US 8,458,587 B2 — Page-layout constraints (gridline-span model)

> "The page layout constraints define constraints between gridlines of a container representing a page layout; the container holds graphical objects, each with a set of object gridlines for delimiting important graphical features, where each gridline's span corresponds to either where the object and gridline overlap or intersect."

This formalizes think-cell's internal layout primitive: **container ⊃ graphical-object ⊃ object-gridlines-with-span**. It is the in-memory shape of every think-cell slide. If you are reverse-engineering the shape data, expect:

- a "container" object per slide,
- per-shape gridline arrays with `(min, max)` span tuples,
- typed constraints between gridlines (the typing is what enables the priority-grouped solver in US 8,847,986).

### US 8,847,986 B2 — Layout-constraint solver pipeline

> "Dividing the set of page layout constraints into groups dependent upon the type of constraint, where each constraint is a member of only one of the groups… transforming each constraint of each group into a resource constraint, assigning a priority to each group, and then solving each group in the order of priority using a resource allocation algorithm — with all members of a chosen group solved simultaneously."

> "Assigning an individual scale variable to each member of a group to form a set of scale variables, then repeatedly maximizing the scale variables up to an upper bound, choosing binding constraints, and replacing scale variables accordingly."

> "Under-constrained conditions between pairs of gridlines after solving all groups [are addressed] by inserting an additional constraint and repeating the solving process."

This is the algorithmic core of what think-cell's marketing calls "automatic slide layout." It is a typed-priority-group resource-allocation solver with iterative repair on under-constrained dimensions. Useful for behavioral understanding, not API hooking.

### US 10,776,448 B2 — Cell-based computing platform (Schödl, sole inventor)

Worth flagging because the abstract is _unusually_ general:

> "The invention relates to a cell-based computing platform that may be specifically used for website development and management. This cell-based computing platform may further be responsive to an external device, program, or operation such that changes in the value parameter of one or more cells may dynamically trigger an external response."

This patent is hard to map to a shipping think-cell product feature — there is no public think-cell "website development" product. Two interpretations:

1. **Defensive filing** to cover the conceptual generalization of a reactive-cell graph (likely tied to the JSON Data Automation server's update model, where JSON inputs trigger PPTX outputs).
2. **Personal Schödl filing** assigned to the company, possibly a parked R&D direction (web-authoring tool from cells).

Either way it is the only patent in the estate that hints at think-cell having an architectural model for a **reactive cell graph with external-event triggers** — which is the closest thing in the patent record to a "server-side automation" disclosure. But the patent says nothing concrete about HTTP, JSON, the `/automation` endpoint, or the PPTX-generator wire format.

---

## Cross-check against API-discovery flags

Asked whether any patent discloses each of these:

| Architectural area                                                   | Disclosed?                                                                                                                                                               |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Chart serialization formats (e.g. on-disk JSON/XML for chart shapes) | **No.** US 10,789,414 hints at a pattern model but not the wire format.                                                                                                  |
| Office add-in architecture (IDTExtensibility2, ribbon, registration) | **No.** Zero coverage.                                                                                                                                                   |
| OOXML custom XML parts                                               | **No.** Not mentioned in any patent.                                                                                                                                     |
| COM dispatch tables                                                  | **No.** Patents do not enumerate any COM interfaces beyond what is already public (`tcPpAddIn`, `tcXlAddIn`).                                                            |
| Ribbon callbacks                                                     | **No.**                                                                                                                                                                  |
| Automation protocols                                                 | **Partial.** US 10,776,448 sketches an abstract reactive-cell+external-trigger model. US 10,789,414 sketches the pattern-application loop. Neither discloses a protocol. |
| JSON-to-PPTX transformation                                          | **No.** The public manual page on JSON Data Automation describes more than any patent.                                                                                   |

---

## Bottom-line: do these patents reveal API surface beyond the public docs?

**Effectively no.** The patent estate is built around four algorithm clusters:

1. **Layout constraint solving** (US 7,478,328 / 8,458,587 / 8,847,986) — math, not API.
2. **Label-placement** for column and scatter charts (US 7,716,578 / 7,757,179) — algorithmic.
3. **Image-based chart-data extraction** (US 10,140,512 / 10,496,695 / US 2018/0189248 / US 2018/0211108) — CV pipeline, not protocol.
4. **Document-structure synchronization and pattern-driven canvas authoring** (US 10,331,761 / 10,776,448 / 10,789,414) — abstract data models, not wire formats.

The deliberate gaps are consistent with a strategy of patenting algorithms (which must eventually be public anyway in academic talks — Theophil and Schödl regularly publish at C++ and graphics conferences) while keeping the **integration surface** (OOXML embedding, COM dispatch, file-format round-tripping, server JSON pipeline) as **trade secrets**. Cinven's 2021 due-diligence presumably incentivized continuing this posture.

**Recommended next vectors for API-surface research (out of scope for this agent):**

- Static analysis: unzip a `.pptx` containing a think-cell chart and inspect `customXml/itemN.xml` and `ppt/embeddings/*.xlsx` parts.
- Dynamic analysis: `OleView` / `tlbinf32` against `tcPpAddIn` / `tcXlAddIn` to enumerate the COM dispatch table beyond the publicly documented methods.
- Network capture: instrument the JSON Data Automation server (`https://server.think-cell.com/automation/` per the public manual) and diff request/response shapes against the documented `AddRangeData` / `UpdateBatch` / `Send` surface.
- Binary symbol mining: `dumpbin /exports` on `tcaddin.dll` (or its current name) to enumerate exported entry points.

---

## Sources

- [Patents Assigned to think-cell Software GmbH — Justia](https://patents.justia.com/assignee/think-cell-software-gmbh)
- [Arno Schoedl Inventions — Justia](https://patents.justia.com/inventor/arno-schoedl)
- [Arno Schödl Inventions — Justia (alt diacritic)](https://patents.justia.com/inventor/arno-sch-dl)
- [Markus Hannebauer Inventions — Justia](https://patents.justia.com/inventor/markus-hannebauer)
- [Dominik Lahmann Inventions — Justia](https://patents.justia.com/inventor/dominik-lahmann)
- [Philipp Nordhus Inventions — Justia](https://patents.justia.com/inventor/philipp-nordhus)
- [US 10,789,414 — Pattern-based filling of a canvas (Justia)](https://patents.justia.com/patent/10789414)
- [US 2018/0211108 — Chart Analysis Method and System (FreePatentsOnline)](https://www.freepatentsonline.com/y2018/0211108.html)
- [US 2018/0189248 — Automated Data Extraction from a Chart (FreePatentsOnline)](https://www.freepatentsonline.com/y2018/0189248.html)
- [US 2017/0351708 — Automated Data Extraction from Scatter Plot Images (FreePatentsOnline)](https://www.freepatentsonline.com/y2017/0351708.html)
- [US 2013/0194297 — Method of Solving Page Layout Constraints (FreePatentsOnline)](https://www.freepatentsonline.com/y2013/0194297.html)
- [Cinven majority investment in think-cell (2021)](https://www.cinven.com/news-insights/cinven-to-make-a-majority-investment-in-think-cell/)
- [think-cell API public manual](https://www.think-cell.com/en/resources/manual/api)
- [think-cell JSON Data Automation public manual](https://www.think-cell.com/en/resources/manual/jsondataautomation)
- [Sebastian Theophil — think-cell senior engineer profile / dissertation](https://www.think-cell.com/en/company/news/2005-08-22)
