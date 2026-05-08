# think-cell JSON Data Automation Hub (`.ppttc`)

Date: 2026-05-01

This is the durable factory hub for think-cell JSON automation as used by the
SimCorp Sales Director deck factory. It is the single place to look up the
`.ppttc` contract, the current Windows VM/API runtime evidence, and the
factory adoption rules. Pair this with `automation-contract.md` and
`vm-api-probe.md`.

Companion machine index: `state/thinkcell_bridge/json_automation/knowledge_hub.json`.

## Authoritative Source

- think-cell user manual, "Automation with JSON data":
  <https://www.think-cell.com/en/resources/manual/jsondataautomation>

All semantic claims below are traceable to that page or to local probe
artifacts in `state/thinkcell_bridge/`. Do not invent semantics not present in
that page.

## Why This Hub Exists

We had three separate facts floating around the repo:

1. The official `.ppttc` contract.
2. A live Parallels Windows VM with `ppttc.exe` and the think-cell PowerPoint
   and Excel COM add-ins.
3. The QTR04/QTR05 stock-donor proofs that already write `.ppttc` payloads and
   bind them on that VM.

The hub joins them into one playbook so the factory does not re-discover them.

## Official `.ppttc` Semantics

think-cell's JSON automation:

- Fills PowerPoint templates with structured data.
- Reuses and reorders templates within one `.ppttc` file.
- Accepts local paths or remote URLs for both templates and JSON.
- Supports a web-service flow when think-cell server is licensed (we do not
  have think-cell server licensed in our environment).

Installation artifacts that prove the contract:

- Schema: `/Library/Application Support/Microsoft/think-cell/ppttc/ppttc-schema.json`
- Sample template: `/Library/Application Support/Microsoft/think-cell/ppttc/template.pptx`
- Sample payload: `/Library/Application Support/Microsoft/think-cell/ppttc/sample.ppttc`
- Sample template named elements: `SlideTitle`, `LeftChartTitle`,
  `RightChartTitle`, `LeftChart`, `RightChart`.

### `.ppttc` Anatomy

```text
[
  {
    "template": "<local path or remote URL>",
    "data": [
      { "name": "<named-element-in-template>", "table": [...] },
      { "name": "<another-named-element>",     "table": [...] }
    ]
  },
  { "template": "...", "data": [...] }
]
```

Rules:

- Root is an array of template objects.
- Order in the array drives slide order in the rendered presentation.
- `template` is a local path or a remote URL.
- On Windows, backslashes in the local path must be JSON-escaped (`\\`). On
  macOS, slashes are accepted directly.
- `data` is an array of `{ name, table }` objects.
- `name` matches a named think-cell element in the template (also the
  AddRangeData target name when binding via Excel COM).
- Two element objects sharing the same name receive the same `table` data.
- `table` mirrors the think-cell datasheet for the chart:
  - First row: categories with a leading `null` corner cell.
  - Subsequent rows: series labels in the first column, values to the right.
  - An empty row `[]` can be used intentionally to suppress a series and shift
    the color scheme.
  - Optional rows or columns must match the template datasheet schema or the
    bind fails.

### Cell Types

| Type         | Rule                                                                      |
| ------------ | ------------------------------------------------------------------------- |
| `string`     | Plain text label.                                                         |
| `number`     | Numeric value, no unit.                                                   |
| `date`       | ISO `YYYY-MM-DD` only.                                                    |
| `percentage` | Numeric only, no `%` sign. `50.0` means 50%.                              |
| `fill`       | Hex (`#RRGGBB`) or RGB; pair with a sibling value cell, never replace it. |
| `null`       | Empty cell. Used for the table corner and intentional gaps.               |

## VM/API Runtime Evidence

Source: `docs/thinkcell-corpus/vm-api-probe.md`,
`state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.md`,
`state/thinkcell_bridge/programmatic_lab/20260501-190411/thinkcell_programmatic_lab.json`.

What the latest probe proved:

- Parallels Windows 11 VM is running and healthy.
- `ppttc.exe` is healthy at `C:\Program Files (x86)\think-cell\ppttc.exe`.
- PowerPoint COM exposes `PresentationFromTemplateStep3`, `UpdateChartStep3`,
  `UpdateBatchStep3`.
- Excel COM exposes `CreateUpdate`, `AddRangeData`, `AddRangeImage`, `Send`.
- LAND seed has 42/42 named automation elements.
- Table-image donor bank has 19/19 valid donors.
- Strict `.ppttc` build emitted 42/42 entries for Jesper Tyrer.
- Windows bridge produced a 28-slide bound PPTX with 25 embeddings, no missing
  slides.
- Render smoke produced 28 PNG slides.
- Style API methods `GetStyleName`, `LoadStyle`, `LoadStyleForRegion`, and
  `RemoveStyles` passed on a transient presentation using installed showcase
  style XML; this proves runtime availability, not production SimCorp brand use.
- `tcserver.exe` is present and inventoried, but was not registered or started.
- No reliable programmatic chart creation API is exposed.

What this changes:

- `.ppttc` is the safe wrapper for native chart and text updates against named
  donor templates. Use it.
- The VM is an update runtime, not a chart factory. Chart object creation
  remains UI/donor/manual-authoring driven.
- Excel COM `AddRangeImage` is the proven lane for table-image refresh; it is
  not replaced by `.ppttc`.

## Factory Adoption: Decision Matrix

| Lane                                            | Use when                                                                                                         | Do not use when                                                                                      | Status                                                            |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| Native think-cell chart via `.ppttc`            | A donor or seed PPTX already contains a named think-cell chart object that matches the SimCorp visual contract.  | The chart object does not yet exist; `.ppttc` cannot create charts.                                  | Proven for 10/12 quarter contracts as of 2026-Q2.                 |
| Table-image via Excel COM `AddRangeImage`       | Slide must show a table-shaped artifact (action register, commercial approval gap, top deals, renewal pipeline). | Native editable think-cell tables are required; that lane is blocked.                                | Proven for QTR10, QTR11, and the table portion of QTR12.          |
| Native editable think-cell tables               | Never (current state).                                                                                           | Always; blocked until a real named, data-backed table donor binds without PowerPoint repair prompts. | Blocked.                                                          |
| Merge candidate charts into meeting-spine deck  | Never via JSON automation.                                                                                       | Always; that is owned by the deck assembly/insertion pipeline, not `.ppttc`.                         | Pilot in `state/2026-Q2/__regional__/thinkcell_insertion_pilot/`. |
| Remote/web-service `.ppttc` (think-cell server) | Never (current state).                                                                                           | Always; SimCorp environment has not licensed think-cell server.                                      | Out of scope.                                                     |

## What JSON Automation Does Not Solve

- It does not create missing chart objects in a template. Chart creation stays
  in the UI or via a manually authored donor.
- It does not solve native editable think-cell tables. That route is
  separately blocked.
- It does not merge candidate charts into the meeting-spine deck. That is a
  separate insertion lane.
- It does not remove the requirement for a leadership/visual decision record
  before production insertion.
- It does not replace the Excel traceability layer that proves the underlying
  numbers.

## Stop Conditions

Stop the lane immediately if any of these are true:

- Success is being judged solely on `ppttc.exe` exit code 0. Require bound
  package text/data assertions and rendered PNG visibility.
- A payload blends ARR (`Type IN ('Land','Expand')`) with Renewal ACV
  (`Type = 'Renewal'`).
- The headline currency basis is raw multi-currency SOQL `SUM` rather than
  FX-converted EUR Salesforce report aggregates (`s!field`).
- A JSON payload tries to invent a named element that does not exist in the
  donor template. `.ppttc` cannot create chart objects.
- Anyone proposes `m_strName` injection into table-related streams (`CSmartGrid`
  / `CContainerSE`) or claims that a boolean flag on `AddRangeData` creates
  charts/tables. Both are documented dead ends.
- A candidate is being inserted into a production deck without a leadership
  /visual decision record.

## Relationship to QTR04/QTR05 Successful Candidate Run

Pilot manifest:
`state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260501-213522Z-claude-writer-pilot/manifest.json`

Both contracts reached `candidate_created` for Jesper Tyrer using the same
JSON-automation lane:

1. Copy the stock think-cell donor `.potx` to a SimCorp-owned `.pptx`.
2. Convert content type from template to presentation.
3. Patch the empty `m_strName` on the donor object to a SimCorp contract name.
4. Generate a strict `.ppttc` payload from the connected factory workbook
   rows.
5. Run the Windows `ppttc.exe` bridge.
6. Assert bound-package text/data, then render and inspect PNGs.

| Contract                          | Donor family                      | Bound deck                                                                                                                                          | Candidate PPTX                                                                                                                                                                                       |
| --------------------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `QTR04_DealRisk_Scatter`          | think-cell Charts/Scatter, Bubble | `state/thinkcell_bridge/build_scaffold/2026-Q2/work/QTR04_DealRisk_Scatter/QTR04_DealRisk_Scatter-stock-donor-2026-Q2-bound.pptx`                   | `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260501-213522Z-claude-writer-pilot/Jesper-Tyrer/QTR04_DealRisk_Scatter/Jesper-Tyrer-QTR04_DealRisk_Scatter-candidate.pptx`                   |
| `QTR05_FY26RenewalTimeline_Gantt` | think-cell Charts/Timeline, Gantt | `state/thinkcell_bridge/build_scaffold/2026-Q2/work/QTR05_FY26RenewalTimeline_Gantt/QTR05_FY26RenewalTimeline_Gantt-stock-donor-2026-Q2-bound.pptx` | `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260501-213522Z-claude-writer-pilot/Jesper-Tyrer/QTR05_FY26RenewalTimeline_Gantt/Jesper-Tyrer-QTR05_FY26RenewalTimeline_Gantt-candidate.pptx` |

What this proves:

- Stock `.potx` files are not direct `.ppttc` templates. They become bindable
  only after copy-to-`.pptx`, content-type fix, and `m_strName` patch.
- Once named, `.ppttc` JSON correctly fills the donor object end to end on the
  VM.
- Bound-package assertions plus PNG render are the only acceptable success
  signal.

Note for the Gantt: header strings such as `Close Date` or `ACV` may not
survive into bound slide XML. Assert on surviving terms (`Renewal`, account
names) instead.

## Implementation Backlog

Tracked in `state/thinkcell_bridge/json_automation/knowledge_hub.json`
under `implementation_backlog`. Concise list:

1. **JA-01** JSON payload generator from connected factory workbook (partial;
   per-contract proof scripts already emit `.ppttc`; lift a shared writer).
2. **JA-02** Schema validation against `ppttc-schema.json` (pending).
3. **JA-03** Per-contract JSON payload linting against SimCorp guardrails
   (ARR/ACV separation, Type filters, EUR basis, no orphan named elements)
   (pending).
4. **JA-04** Artifact registry for `(template, ppttc, bound_pptx, render_dir)`
   triples per run (pending).
5. **JA-05** Decision-record requirement before production deck insertion
   (pending).

## Hard Business Rules

- ARR uses `APTS_Opportunity_ARR__c` with `Type IN ('Land','Expand')`.
- Renewal ACV uses `APTS_Renewal_ACV__c` with `Type = 'Renewal'`.
- Never blend ARR and Renewal ACV in any chart, total, KPI strip, or bridge.
- Headline figures use FX-converted EUR Salesforce report aggregates
  (`s!field`); raw multi-currency SOQL `SUM` is forbidden.
- Table-image `AddRangeImage` remains the table lane.
- The VM is the update runtime, not the chart factory.

## Where To Read Next

- `automation-contract.md` for what is automatable and what is blocked.
- `vm-api-probe.md` for the current Windows VM API surface and operating
  model.
- `build-scaffold.md` for L0-L5 build levels and proof state.
- `graph-rag.md` for graph queries against the corpus.
- `state/thinkcell_bridge/json_automation/knowledge_hub.json` for the
  machine-readable companion.
