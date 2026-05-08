# Research — what makes a think-cell template structurally valid

**Date:** 2026-04-30
**Author:** Claude (research-only, no code changes)
**For:** the team blocked on `The .ppttc file is bad. The template failed to load.`

## TL;DR

think-cell does **not** look up shapes by their PPTX `<p:cNvPr name="...">` attribute, by chart number, or by any visible PowerPoint property. It looks them up by a **think-cell-proprietary `m_strName` value embedded inside the slide XML** as an `a:tagSetData`-style attribute payload, and (presumably) cross-referenced from a **document-level LiteDB blob stored in `ppt/tags/tag1.xml` under the `EMPOWERCHARTSPROPERTIES_B_0` tag**. The donor-chart copy approach in `scripts/ppttc_template.py` produces neither of those, which is why the runtime rejects every variant — even one-chart subsets.

## Section 1 — file-level diff

|                                                           | Working `template.pptx` (think-cell sample)                                        | Failing `slide4-LAND-2026-Q2-template.pptx`                       |
| --------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Source                                                    | `/Library/Application Support/Microsoft/think-cell/ppttc/template.pptx`            | `/tmp/ppttc-singletons2/slide4/slide4-LAND-2026-Q2-template.pptx` |
| Total parts                                               | 123                                                                                | 207                                                               |
| Slides                                                    | 1                                                                                  | 28                                                                |
| `ppt/charts/chart*.xml`                                   | 2                                                                                  | 1                                                                 |
| `ppt/embeddings/oleObject*.bin`                           | 12                                                                                 | 1 (`oleObject3.bin`)                                              |
| `ppt/embeddings/Microsoft_Excel_Binary_Worksheet*.xlsb`   | 2                                                                                  | 1                                                                 |
| `ppt/tags/tag*.xml`                                       | 40                                                                                 | 30 (numbered `1, 4..32` — gap at 2, 3)                            |
| `ppt/tags/tag1.xml` size                                  | **37 436 bytes** (carries `EMPOWERCHARTSPROPERTIES_*` LiteDB blob)                 | **337 bytes** (just `THINKCELLUNDODONOTDELETE` stub)              |
| Content-types: `tag2.xml`, `tag3.xml`                     | registered as overrides                                                            | **NOT registered** (the override list jumps tag1 → tag4)          |
| Slide carries `<p:tag name="EMPOWERCHARTSPROPERTIES_*"/>` | yes, on tag1.xml at presentation rel                                               | no — `tag1.xml` is a slide-shape `THINKCELLUNDODONOTDELETE` stub  |
| `m_strName` occurrences across all slides                 | 3 in slide1 (`SlideTitle`, `LeftChartTitle`, `RightChartTitle`; charts also bound) | **0** across all 28 slides                                        |
| `PersistentType` occurrences                              | 3 in slide1                                                                        | **0**                                                             |
| docProps/custom.xml                                       | identical-shape SharePoint metadata                                                | identical-shape SharePoint metadata                               |
| customXml/item{1,2,3}.xml                                 | SharePoint `documentManagement` metadata only — **not** think-cell                 | same — **not** think-cell                                         |
| `[Content_Types].xml` writer                              | Microsoft (no `ns0:` prefixed default namespace, no self-closing space)            | python-pptx (`ns0:` prefix, `<ns0:Override … />` self-closing)    |

## Section 2 — XML-level differences in shared parts

### 2.1 `[Content_Types].xml`

Same MIME types are registered (presentation, slide, slideLayout, slideMaster, chart, oleObject, theme, tags, customXml, etc.). **No think-cell-specific MIME type is registered in either file.** That alone disproves the hypothesis "think-cell needs a `application/vnd.think-cell.*` content type."

The only structural difference is that the **failing file is missing `Override` entries for `tag2.xml` and `tag3.xml`**, but those tag files do not exist in the failing zip either, so this is consistent. It is not the bug.

### 2.2 `customXml/item*.xml`

Both files carry SharePoint `documentManagement` properties (`MediaServiceMetadata`, `TaxCatchAll`, `lcf76f155ced4ddcb4097134ff3c332f`). **Neither file uses `customXml/` for think-cell.** This kills the hypothesis "think-cell stores chart specs in customXml." It does not.

### 2.3 `ppt/_rels/presentation.xml.rels`

Both reference `tags/tag1.xml`. So the tag1 binding **is** wired in the failing file — but `tag1.xml` itself is the wrong content (337 bytes of `THINKCELLUNDODONOTDELETE` stub vs. 37 KB of LiteDB blob).

### 2.4 `ppt/tags/tag1.xml` — the core difference

Working tag1.xml contains **six** `<p:tag>` entries inside one `<p:tagLst>`:

```
EMPOWERCHARTSPROPERTIES_B_0           val=<32 KB base64 LiteDB blob>
EMPOWERCHARTSPROPERTIES_B_LENGTH      val=<integer>
EMPOWERCHARTSPROPERTIES_LASTWRITEDATE val=<datetime>
EMPOWERCHARTSPROPERTIES_SLOT          val=<int>
THINKCELLPRESENTATIONDONOTDELETE      val=<sentinel>
THINKCELLUNDODONOTDELETE              val=0
```

Failing tag1.xml contains **one**:

```
THINKCELLUNDODONOTDELETE              val=0
```

Decoding the working `EMPOWERCHARTSPROPERTIES_B_0` value as base64 yields a 24 576-byte LiteDB v3 binary file (header `** This is a LiteDB file **` is visible in the first decoded line). LiteDB is the embedded NoSQL store think-cell uses to persist style and chart-binding metadata at the presentation level.

### 2.5 Slide XML — chart-name binding

In the working `slide1.xml`, every named element carries an embedded `tagSetData` payload like:

```xml
<a:rPr ...>
  <a:tagSetData val="thinkcell&lt;?xml version=1.0 encoding=UTF-16?&gt;
                     &lt;root reqver=32687&gt;
                       &lt;PersistentType&gt;
                         …
                         &lt;m_strName&gt;SlideTitle&lt;/m_strName&gt;
                       &lt;/PersistentType&gt;
                     &lt;/root&gt;"/>
</a:rPr>
```

The `m_strName` value (`SlideTitle`, `LeftChartTitle`, `LeftChart`, `RightChart`, `RightChartTitle` in the sample) is **the name `.ppttc` matches against**. think-cell never reads `<p:cNvPr name="...">`.

Across all 28 slides of the failing template, occurrences of `m_strName` = 0, occurrences of `PersistentType` = 0. The donor-injected `Chart 22`, `Straight Connector 95`, etc. shape names are PowerPoint cosmetic labels and **carry no binding for think-cell**.

The `ppt/charts/chart1.xml` payloads in both files are vanilla DrawingML chart XML (no think-cell extension elements). So the chart XML is not where the binding lives either.

## Section 3 — hypotheses ranked by evidence

### H1 (strong, supported) — think-cell binds names through `m_strName` in slide XML and a presentation-level LiteDB blob; the donor-chart approach produces neither

Evidence:

- working sample: **3 `m_strName` entries in slide1** matching the four chart-binding names referenced in `sample.ppttc` (`SlideTitle`, `LeftChartTitle`, `RightChartTitle`, `LeftChart`/`RightChart` are the chart payload names)
- failing template: **0 `m_strName` entries** in any of 28 slides
- `ThinkcellBuilder` README confirms: _"think-cell binds data to objects purely by name … mistyped chart names are silently ignored"_ — but here every name is missing, not mistyped, so think-cell rejects the whole load instead of silently skipping

### H2 (medium) — `tag1.xml` LiteDB blob is the document-level registry of all named elements and must be present and self-consistent with the slide-level `m_strName` payloads

Evidence:

- the working blob is 24 KB of LiteDB-encoded data referenced from `ppt/_rels/presentation.xml.rels`
- the failing presentation rels still reference `tag1.xml` but the file is the wrong content (a slide-shape sentinel, not the document registry)
- LiteDB content includes a `CombiIndex=$.Name + '_' + $.Version"` index expression, strongly suggesting the registry indexes by Name

### H3 (weak) — donor `oleObject*.bin` parts carry serialized ActiveDocument state that includes the donor presentation's path/identity; cross-presentation reuse breaks that state

Evidence:

- `oleObject3.bin` in the failing file is `progId="TCLayout.ActiveDocument.1"`, the think-cell ActiveDocument marker
- the audit's "fixed duplicate `rId` rewrite" symptom is consistent with these OLE blobs being identity-bound
- but there is no direct evidence in the unzipped trees, and H1+H2 already fully explain the failure, so this is at most a secondary concern

## Section 4 — what the donor-chart approach would need to add

For the current `_inject_donor_charts(...)` path to produce a `.ppttc`-valid template, it would need to (in addition to copying chart parts and rewriting rels):

1. **Inject a `tagSetData` `<m_strName>{name}</m_strName>` payload** on every chart, text-field, table, Harvey-ball that the emitter targets. Encoding is UTF-8-safe XML inside an HTML-encoded UTF-16 declaration string, embedded into `a:rPr`/`a:endParaRPr` or comparable run-property elements on the bound shape. Writing this from outside think-cell means re-creating an undocumented, LiteDB-cross-referenced binary state.
2. **Reconstruct `ppt/tags/tag1.xml`** with the four `EMPOWERCHARTSPROPERTIES_*` entries and a valid LiteDB document containing one record per named element. Without internal knowledge of the LiteDB schema think-cell expects (collection names, document fields, version markers, the `CombiIndex` index definition observable in the working blob), this cannot be produced de novo.
3. **Update `[Content_Types].xml` and `presentation.xml.rels`** to register the rebuilt `tag1.xml` as a presentation-level tag part — easy once 1 and 2 are solved, irrelevant before.

Step 2 is the structural blocker: the LiteDB blob is binary, undocumented, and validated by think-cell at `.ppttc` import. Replicating it without a `.NET` LiteDB writer plus reverse-engineered schema is out of scope.

ThinkcellBuilder explicitly disclaims this in its README: _"It is currently impossible to derive the types or names of think-cell objects … in a template programmatically."_ The library only writes the JSON side; **template authorship is delegated to PowerPoint with think-cell installed.**

## Section 5 — alternative architectures

### A1 (recommended, matches the handoff) — manually-seeded immutable base template

Author **one** template `.pptx` in PowerPoint with think-cell installed. For each named element the emitter targets, select it, type the name into the **AddRangeData Name** mini-toolbar field, press Enter. Save. That single `.pptx` is the immutable input to `build_ppttc.py --template …`. think-cell writes the `m_strName` payloads and the `tag1.xml` LiteDB blob automatically; the Python pipeline never has to.

This is what the existing handoff already recommends (`/Users/test/code/apps/sales-ops-copilot/docs/HANDOFF_THINKCELL_PPTTC_2026-04-30.md` "Fastest path to green"). The research above provides the why: there is no programmatic way to produce the `m_strName`/LiteDB pair from scratch.

For SimCorp brand fidelity, load `assets/SimCorp-thinkcell-style.xml` into think-cell before saving (think-cell **Style** menu → **Load style file**) so the saved template carries SimCorp colors/fonts.

### A2 (fallback) — donor-style POTX as base, manual element-name pass per template

think-cell ships donor POTX files at `/Library/Application Support/Microsoft/think-cell/templates/think-cell Charts/{Bar, Column, Waterfall, …}/*.potx`. Open the closest matching one, replace cosmetic content, name each chart, save as the project's template. Same A1 mechanism, lower starting effort if the donor matches the desired chart types (Bar, Column for `S04`–`S08`; Waterfall for `S04_PipeMovement` specifically).

### A3 (experimental, not recommended now) — driver script that opens the manually-seeded base in PowerPoint via AppleScript / OLE, programmatically renames shapes via the think-cell COM API (Windows only), saves a director-specific copy

The `UpdateBatch` API documented at <https://www.think-cell.com/en/resources/manual/updatebatch> exposes methods to add ranges and refresh data, but **does not expose `m_strName` mutation** — names are still set through the UI mini-toolbar. So this path also collapses back to A1 + manual naming for distinct templates. Not worth pursuing unless think-cell publishes a programmatic naming API.

### A4 (not recommended) — abandon think-cell, render via vanilla python-pptx

Already ruled out by hard constraint in the handoff: _"Do not pivot to native python-pptx charts."_ Listed only for completeness.

## Pointers

- Working template: `/Library/Application Support/Microsoft/think-cell/ppttc/template.pptx` (referenced by `/Library/Application Support/Microsoft/think-cell/ppttc/sample.ppttc`)
- Failing template: `/tmp/ppttc-singletons2/slide4/slide4-LAND-2026-Q2-template.pptx`
- Unzipped trees: `/tmp/working_tcl/`, `/tmp/failing_tcl/`
- Slide-level binding: `m_strName` inside `tagSetData` payloads in `/tmp/working_tcl/ppt/slides/slide1.xml` (search for `PersistentType`)
- Doc-level binding: `EMPOWERCHARTSPROPERTIES_B_0` LiteDB blob in `/tmp/working_tcl/ppt/tags/tag1.xml`
- Build code that needs no change: `/Users/test/code/apps/sales-ops-copilot/scripts/build_ppttc.py`
- Build code that should not be salvaged: `_inject_donor_charts(...)` in `/Users/test/code/apps/sales-ops-copilot/scripts/ppttc_template.py`
- think-cell JSON automation manual: <https://www.think-cell.com/en/resources/manual/jsondataautomation>
- think-cell Excel automation (covers the AddRangeData Name UI step): <https://www.think-cell.com/en/resources/manual/exceldataautomation>
- ThinkcellBuilder (Python lib, JSON-only, confirms templates must be authored in PowerPoint): <https://github.com/Philistino/ThinkcellBuilder>

## Honest caveat

The LiteDB blob inside `EMPOWERCHARTSPROPERTIES_B_0` was decoded only enough to confirm the LiteDB header, file size, and one observable index expression (`CombiIndex=$.Name + '_' + $.Version`). The full document schema was not reverse-engineered. H2 ("the blob is the registry") is therefore a strong inference from format and naming rather than a fully decoded structural proof. H1 alone (the `m_strName` absence in every slide) is enough to explain why the failing template loads as zero named elements and is rejected.
