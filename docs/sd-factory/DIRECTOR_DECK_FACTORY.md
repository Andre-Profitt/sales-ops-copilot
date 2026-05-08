# Director LAND Deck Factory

The current production entrypoint is:

```bash
.venv/bin/python scripts/run_regional_production_line.py --period 2026-Q2 --jobs 6
```

This is the validated May 2026 lane for the 9 Sales Director LAND meeting-spine
decks. It packages the current linked decks, runs publish gates, audits APAC
coverage, validates the Downloads package, and writes the run manifest.

## Current Status

- Validated period: `2026-Q2` / May 2026 only.
- Salesforce snapshot date: `2026-04-30`.
- Kickoff date: `2026-05-01`.
- Review package: `/Users/test/Downloads/May 2026 Meeting Spine Candidates`.
- Latest green production run:
  `state/2026-Q2/__regional__/production_runs/20260501-153635/manifest.json`.
- Latest SharePoint validation:
  `state/2026-Q2/__regional__/sharepoint_may_2026_validation_manifest.json`.
- Latest full all-director table-image refresh:
  `state/2026-Q2/__regional__/table_image_factory_runs/20260501-132714/manifest.json`.
- Latest APAC patch refresh after the freshness gate:
  `state/2026-Q2/__regional__/table_image_factory_runs/20260501-134515/manifest.json`.

Run the status report before presenting or uploading:

```bash
.venv/bin/python scripts/report_regional_production_status.py --period 2026-Q2
```

It writes:

- `state/2026-Q2/__regional__/production_status/regional_production_status.json`
- `state/2026-Q2/__regional__/production_status/regional_production_status.md`

## ETL Path

1. Salesforce-derived source artifacts:
   `trends.json`, `brief.md`, `land.xlsx`, `land.model.xlsx`.
2. Connected formula/audit workbook:
   `factory/connected/connected_factory.xlsx`.
3. think-cell table-image source workbook:
   `factory/connected/connected_factory_table_images.xlsx`.
4. PowerPoint linked table-image refresh through the Windows VM.
5. Mac PowerPoint finalization for think-cell carryover and exact geometry.
6. Source-aware text polish.
7. 16-slide regional meeting-spine deck build.
8. Programmatic linked-action layer from `scripts/meeting_spine_action_layer.py`
   for Q1 accountability, May forecast quality, Q2 deal inspection, renewal
   watchlist, and Salesforce-linked action register.
9. Publish gate, APAC strict intel audit, regional goal audit.
10. Downloads review package validation.
11. Render-based visual gate for every packaged meeting-spine deck.
12. SharePoint containment/upload/validation when publishing.

The table visuals are Excel-driven linked table images. They are traceable to
the connected workbook and robust enough for the current deck factory, but they
are not native think-cell table objects.

## Commands

Fast gate/package run using current Excel and linked-deck artifacts:

```bash
.venv/bin/python scripts/run_regional_production_line.py --period 2026-Q2 --jobs 6
```

Fast gate/package run plus live SharePoint validation:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --jobs 6 \
  --sharepoint-validate
```

Full publish run: local gates, stale SharePoint containment, upload, and live
SharePoint validation:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --jobs 6 \
  --sharepoint-publish
```

Refresh only the Salesforce-derived source and connected workbooks, then stop:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --refresh-source \
  --source-only \
  --jobs 4
```

One-director full raw-to-PPT pilot:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --director-slug Jesper-Tyrer \
  --refresh-source \
  --full-table-image-refresh \
  --jobs 2
```

All-director full raw-to-PPT refresh:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --refresh-source \
  --full-table-image-refresh \
  --jobs 4
```

Plan the full refresh without writing artifacts:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --refresh-source \
  --full-table-image-refresh \
  --jobs 4 \
  --plan-only
```

## Guardrails

- `--refresh-source` is blocked unless paired with `--source-only` or
  `--full-table-image-refresh`; this prevents fresh Excel from being packaged
  with stale PowerPoint links.
- `--plan-only` does not write run directories.
- Unsupported periods fail intentionally. Quarter-roll logic is not certified
  beyond May 2026 / `2026-Q2`.
- The publish gate checks freshness order across source artifacts, connected
  workbook, table-image workbook, and linked PPTX.
- Forbidden deck text includes test accounts, exaggerated probability values,
  placeholder section titles, Office subtitle placeholders, `#NAME`, and
  `#NULL`.
- ARR and ACV remain separated: Land+Expand ARR is unweighted unless explicitly
  labeled otherwise; Renewal is ACV-only.

## Gates

The top-level production line currently runs:

1. `build_regional_intelligence_specs.py`
2. `polish_regional_linked_deck_text.py`
3. `fix_table_image_aspect_ratios.py`
4. `build_regional_meeting_spine_decks.py`
5. internal meeting-spine smoke check
6. `run_regional_deck_publish_gate.py`
7. APAC strict original-intel coverage audit on the full linked deck
8. APAC strict original-intel coverage audit on the meeting spine
9. `audit_regional_decks_against_goals.py`
10. Downloads package copy
11. `validate_may_review_package.py`
12. `run_review_package_visual_gate.py`
13. optional SharePoint containment/upload/validation when `--sharepoint-publish`
    or `--sharepoint-validate` is used
14. final production-status report copy into the review package
15. post-status SharePoint evidence refresh and final validation when
    `--sharepoint-publish` is used

The full table-image refresh adds:

1. `land_brief.py` source refresh with the pinned snapshot date
2. `run_land_to_deck.py --validate-only`
3. `build_connected_factory_workbook.py`
4. `run_regional_table_image_factory.py --refresh-existing --finalize-close`

## Residual Risks

- Current table output is linked table-image based, not native think-cell table
  insertion.
- The full refresh still depends on Windows PowerPoint/think-cell automation and
  Mac PowerPoint finalization.
- Q3/month-roll has not been certified; add the next period only after source
  windows, package naming, freshness gates, and quarter labels are validated.

## SharePoint Publish

The May 2026 folder is:

`General/Book of Business/Sales Director Reporting/Q2 2026/May 2026`

Publish sequence:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period 2026-Q2 \
  --jobs 6 \
  --sharepoint-publish
```

The upload publishes each director's final meeting-spine deck, connected Excel
audit workbook, PowerPoint table-source workbook, and the gate evidence files.
Folder, warning-file, and manifest names now come from `period_context.py` so
the SharePoint lane is no longer manually hardcoded to the May folder inside
the upload, containment, and validation scripts.
After the production-status report is generated, the publish command refreshes
the mutable evidence files on SharePoint and re-runs validation so the uploaded
status points at the actual final run.

The lower-level commands remain available for targeted repair:

```bash
.venv/bin/python scripts/contain_may_sharepoint_uploads.py --execute
.venv/bin/python scripts/upload_may_regional_assets_sharepoint.py --period 2026-Q2
.venv/bin/python scripts/validate_may_sharepoint_upload.py --period 2026-Q2 --upload-manifest
```

## Legacy Lane

`scripts/director_deck_factory.py` and
`scripts/run_regional_table_image_factory.py` remain useful lower-level tools,
but they are no longer the primary production command. Use the regional
production line unless debugging one substage.
