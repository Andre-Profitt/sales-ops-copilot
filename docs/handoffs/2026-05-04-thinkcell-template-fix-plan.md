# Engineer handoff — surgical fix plan for SimCorp LAND deck factory template + think-cell pipeline

Date: 2026-05-04
Owner intent: Build a reusable, SimCorp-branded, think-cell-enabled monthly LAND review deck factory for all 9 directors. Stop producing one-off Patrick decks.

## Executive decision

The broken pieces are concentrated in the template/render boundary, not the data layer. Keep the working ETL/model/trends/brief/harness pieces. Replace the contaminated seed and make think-cell bindings a governed contract.

Target pipeline:

```text
model.xlsx + trends.json + brief.md
        -> deck_plan.json
        -> land_review_full_28.binding_registry.yml
        -> .ppttc payload
        -> think-cell ppttc.exe render on Windows VM
        -> Excel COM AddRangeImage refresh for table-shaped artifacts
        -> binding-level render evidence report
        -> publish gate
        -> pptx/pdf package for each director
```

## What to keep

- `state/2026-Q2/<director>/land.model.xlsx` and the named-range model layer.
- `state/2026-Q2/<director>/trends.json` and `brief.md` as source artifacts.
- `scripts/build_ppttc.py` as the starting point for `.ppttc` generation.
- `libs/tcrender/` Mac-to-Windows render bridge.
- Strict workbook/pptx numeric and publish validators.
- The clean SimCorp canonical template as the brand/layout source.

## What to quarantine immediately

Move these out of the production path:

```text
assets/LAND_thinkcell_seed.pptx
assets/LAND_thinkcell_seed.pre-stripdev.pptx
failed Patrick variants
experimental polish/master-transplant/donor-splice outputs
```

New folder:

```text
assets/legacy/do_not_use_in_factory/
```

Add a README explaining that these are forensic references only.

## What to build instead

Create a new canonical think-cell seed:

```text
assets/templates/land_review_full_28/
  LAND_review_full_28.clean_skeleton.pptx
  LAND_review_full_28.tcseed.pptx
  LAND_review_full_28.seed_contract.yml
  LAND_review_full_28.named_element_inventory.json
  LAND_review_full_28.seed_certification.md
```

### Critical rule

Do not synthesize native think-cell chart objects from scratch in Python for production. The production template must already contain real, named think-cell elements. Programmatic scripts may build the PowerPoint skeleton, but the think-cell elements must be created, named, opened, saved, and certified through PowerPoint + think-cell on the Windows VM.

## Manual template-steward procedure

1. Open the clean SimCorp LAND canonical deck in PowerPoint.
2. Build the 28-slide skeleton using approved SimCorp layouts.
3. Insert think-cell charts only where the registry says `lane: ppttc`.
4. For each chart, select the chart -> mini toolbar -> AddRangeData Name -> enter the exact registry name.
5. Insert automation text fields for titles, subtitles, source notes, footnotes, KPI card values, and narrative boxes.
6. For each automation text field, use the exact registry name.
7. For table-shaped artifacts, create a temporary Excel range image and assign AddRangeImage Name using the exact registry name.
8. Save as `LAND_review_full_28.tcseed.pptx`.
9. Reopen in PowerPoint. Confirm no repair prompt.
10. Run named-element inventory and template preflight.
11. Certify only when required names, no-debris checks, and render canary pass.

## Required implementation patches

### PR 1 — Template quarantine and factory default

Files:

```text
assets/legacy/do_not_use_in_factory/README.md
scripts/factory.py
scripts/build_ppttc.py
```

Changes:

- Move current debris seed to legacy.
- Change factory default template from `assets/LAND_thinkcell_seed.pptx` to `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx`.
- Add an explicit `--allow-legacy-seed` flag if anyone tries to use the old seed.
- Fail if the selected template path includes `legacy`, `pre-strip`, `shipping`, `polish`, `transplant`, or `Patrick-Gaughan` unless `--experimental` is supplied.

Acceptance:

```bash
python scripts/factory.py --period 2026-Q2 --directors Patrick-Gaughan --dry-run
```

Must report the clean seed path and must fail if the old seed is selected without override.

### PR 2 — Binding registry

Add:

```text
config/thinkcell/land_review_full_28.binding_registry.yml
schemas/thinkcell_binding_registry.schema.json
scripts/validate_thinkcell_binding_registry.py
```

The registry owns:

- slide ID
- element name
- element kind
- render lane
- source workbook sheet/range or `trends.json` path
- required/optional status
- evidence rule
- fallback lane

No renderer code should contain hard-coded slide names once this exists.

Acceptance:

```bash
python scripts/validate_thinkcell_binding_registry.py \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml
```

Must fail on duplicate names, missing slide IDs, unsupported lane, unsupported element kind, missing required evidence, or use of ARR/ACV-mixing fields.

### PR 3 — Template contract/preflight

Add:

```text
scripts/verify_thinkcell_template_contract.py
```

Inputs:

```text
--template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx
--registry config/thinkcell/land_review_full_28.binding_registry.yml
```

Checks:

- Every required `ppttc` element exists in the think-cell named-element inventory.
- Every required `table_image` AddRangeImage name exists.
- Every title/source/footnote automation text field exists.
- No dev instruction strings.
- No donor placeholder labels like `User count [K]`, `[USD m]`, `Product A`, `BU1`, `BU2`.
- No `Lorem ipsum`, `Click to add`, or internal test accounts.
- No off-canvas shapes unless explicitly whitelisted.
- No hidden light-blue instruction rectangles.

Acceptance:

```bash
python scripts/verify_thinkcell_template_contract.py \
  --template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --out state/2026-Q2/__regional__/template_contract_report.json
```

Must output:

```json
{
  "status": "pass",
  "required_elements_missing": [],
  "forbidden_text": [],
  "debris_shapes": []
}
```

### PR 4 — `.ppttc` builder uses registry, not hard-coded bindings

Modify:

```text
scripts/build_ppttc.py
```

Add:

```text
--registry config/thinkcell/land_review_full_28.binding_registry.yml
--emit-evidence-manifest
```

Output per director:

```text
state/2026-Q2/<director>/<director>-LAND-2026-Q2.ppttc
state/2026-Q2/<director>/render_evidence_manifest.json
```

Rules:

- Top-level `.ppttc` is an array with one template object.
- Every data item must have a `name` matching the registry.
- Every required registry binding must produce a data item or an explicit blocked/suppressed record.
- Every insight title must include evidence references.
- Every source note must be bound.
- Numeric fields must use explicit units: EUR, EUR M, %, days, count.

Acceptance:

```bash
python scripts/build_ppttc.py \
  --director "Patrick Gaughan" \
  --period 2026-Q2 \
  --template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --emit-evidence-manifest
```

Must produce `.ppttc`, pass JSON schema, and have 0 unbound required elements.

### PR 5 — Separate table-image refresh from chart/text render

Add or formalize:

```text
scripts/windows/refresh_thinkcell_table_images.ps1
scripts/refresh_thinkcell_table_images.py
```

Render sequence:

1. `ppttc.exe` fills charts and text fields.
2. Excel COM `UpdateBatch` fills AddRangeImage table artifacts.
3. Save as final deck.

COM behavior:

- Open rendered PPTX headless.
- Open connected workbook.
- Create think-cell update object.
- For each registry element with `lane: excel_updatebatch_image`, call `AddRangeImage(pres, name, range)`.
- Send update.
- Save.

Acceptance:

```bash
python scripts/refresh_thinkcell_table_images.py \
  --pptx state/2026-Q2/Patrick-Gaughan/rendered_stage1.pptx \
  --workbook state/2026-Q2/Patrick-Gaughan/connected_factory.xlsx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --out state/2026-Q2/Patrick-Gaughan/rendered_final.pptx
```

Must verify that every required table image exists on the correct slide and meets size/aspect gates.

### PR 6 — Replace ratio verifier with binding-level verifier

Modify or replace:

```text
libs/tcrender/tcrender/verify.py
scripts/verify_render_bindings.py
```

The current global `min_match_ratio` verifier must not be the publish gate. It can remain as a diagnostic.

New report:

```json
{
  "status": "pass",
  "template": "LAND_review_full_28.tcseed.pptx",
  "ppttc": "Patrick-Gaughan-LAND-2026-Q2.ppttc",
  "bindings": [
    {
      "name": "S05_Title",
      "kind": "text",
      "required": true,
      "status": "pass",
      "evidence": "exact text found on slide 5"
    },
    {
      "name": "S05_PipelineByStage",
      "kind": "chart",
      "required": true,
      "status": "pass",
      "evidence": "category labels found and donor placeholders absent"
    }
  ],
  "hard_rules": {
    "arr_acv_separation": "pass",
    "source_notes": "pass",
    "forbidden_text": "pass",
    "period_label": "pass"
  }
}
```

Acceptance:

- A deck can only publish if every required binding passes.
- Missing title/source/action bindings are fatal.
- Missing optional visual bindings may fallback but must be explicit.
- No global ratio threshold is allowed as the only pass condition.

### PR 7 — Insight titles are generated before render

Add:

```text
config/rules/land_review_insight_titles.yml
scripts/build_insight_titles.py
```

Rules:

- Every analytic slide must receive a full-sentence title.
- Every title must cite one or more metric IDs.
- Titles are bound to `S##_Title` fields through `.ppttc`.
- If a rule cannot fire, use a deterministic fallback title plus a warning.

Acceptance:

```bash
python scripts/build_insight_titles.py \
  --period 2026-Q2 \
  --director "Patrick Gaughan" \
  --out state/2026-Q2/Patrick-Gaughan/insight_titles.json
```

Must produce no empty titles and no worksheet-name titles like `Pipeline by stage` unless intentionally allowed for divider/closing slides.

### PR 8 — One orchestrator for the full template/render lane

Add:

```text
scripts/run_land_review_full_28_pipeline.py
```

Order:

```text
1. validate model/workbook/numeric sanity
2. validate registry
3. validate template contract
4. build insight titles
5. build deck_plan.json
6. build .ppttc
7. render via Windows ppttc.exe
8. refresh AddRangeImage table images
9. verify binding-level render evidence
10. run publish gate
11. export pptx/pdf package
12. write manifest
```

Canary command:

```bash
python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors Patrick-Gaughan \
  --strict
```

All-director command:

```bash
python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors all \
  --jobs 6 \
  --strict
```

## Slide lane map

| Slide | Purpose | Primary lane | Required names |
|---:|---|---|---|
| 1 | Cover | ppttc text | S01_DirectorName, S01_Period, S01_ScopeLabel |
| 2 | Exec summary | ppttc text | S02_Title, S02_ExecSummaryLeft, S02_ExecSummaryRight, S02_Source |
| 3 | Pipeline divider | static/ppttc text | S03_Title |
| 4 | Pipe movement | ppttc chart | S04_Title, S04_PipeMovement, S04_Source |
| 5 | Pipeline by stage | ppttc chart | S05_Title, S05_PipelineByStage, S05_Source |
| 6 | Pipeline aging | ppttc chart | S06_Title, S06_PipelineAging, S06_Source |
| 7 | Top deals — Land | Excel AddRangeImage | S07_Title, S07_TopDealsLand_IMG, S07_Source |
| 8 | Top deals — Expand | Excel AddRangeImage | S08_Title, S08_TopDealsExpand_IMG, S08_Source |
| 9 | Pending approval | Excel AddRangeImage | S09_Title, S09_PendingCommercialApproval_IMG, S09_Source |
| 10 | Retention divider | static/ppttc text | S10_Title |
| 11 | Renewal pipeline | Excel AddRangeImage | S11_Title, S11_RenewalPipeline_IMG, S11_Source |
| 12 | GRR proxy | Excel AddRangeImage + text | S12_Title, S12_GRRProxyTable_IMG, S12_Footnote |
| 13 | Forecast category | ppttc chart | S13_Title, S13_ForecastCategory, S13_Source |
| 14 | Territory divider | static/ppttc text | S14_Title |
| 15 | By owner | ppttc chart | S15_Title, S15_ByOwner, S15_Source |
| 16 | Stage × Industry | ppttc stacked chart; Mekko P1 | S16_Title, S16_StageByIndustry, S16_Source |
| 17 | Territory performance | ppttc chart | S17_Title, S17_TerritoryPerformance, S17_Source |
| 18 | Wins/losses QTD | ppttc chart | S18_Title, S18_WinsLossesQTD, S18_Source |
| 19 | Velocity | ppttc chart | S19_Title, S19_Velocity, S19_Source |
| 20 | Risks divider | static/ppttc text | S20_Title |
| 21 | Concentration risk | chart + image table | S21_Title, S21_ConcentrationRiskChart, S21_ConcentrationTable_IMG, S21_Source |
| 22 | Stale activity | ppttc chart | S22_Title, S22_StaleActivity, S22_Source |
| 23 | Sales velocity formula | ppttc text/scalars | S23_Title, S23_OppCount, S23_WinRate, S23_AvgDealSize, S23_CycleLength, S23_SalesVelocity |
| 24 | Account expansion | Excel AddRangeImage | S24_Title, S24_AccountExpansion_IMG, S24_Source |
| 25 | Pipeline creation velocity | ppttc line/column | S25_Title, S25_PipelineCreationVelocity, S25_Source |
| 26 | Action items | Excel AddRangeImage | S26_Title, S26_ActionItems_IMG, S26_Source |
| 27 | Risks & outlook | ppttc text | S27_Title, S27_RisksOutlook, S27_Source |
| 28 | Closing | static | none |

## Hard publish-blocking rules

- No deck ships from `assets/LAND_thinkcell_seed.pptx`.
- No deck ships if a required named think-cell element is missing.
- No `.ppttc` entry is allowed without a registry match.
- No required registry entry is allowed without a `.ppttc` or AddRangeImage update.
- No analytic slide ships without an insight title and source note.
- No Land+Expand ARR mixed with Renewal ACV.
- No pipeline metric without explicit Type filter.
- No unlabeled weighted/unweighted ARR.
- No currency aggregation without conversion metadata.
- No stage labels outside the SimCorp 8-stage process.
- No donor placeholder labels or dev instructions in final PPTX.
- No PowerPoint repair prompt on open.

## Definition of done

Patrick canary:

```text
status: pass
required template elements missing: 0
required ppttc bindings missing: 0
required table images missing: 0
forbidden text findings: 0
Excel error tokens: 0
ARR/ACV hard-rule failures: 0
PowerPoint repair prompt: no
PDF export: pass
```

All-director release:

```text
9/9 directors pass strict pipeline
Each director has: pptx, pdf, deck_plan.json, ppttc, evidence_manifest.json, qa_report.json
No deck uses legacy seed
No deck uses failed Patrick artifacts
```
