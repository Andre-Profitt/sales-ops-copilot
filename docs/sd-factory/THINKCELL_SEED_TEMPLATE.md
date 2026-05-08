# think-cell LAND seed template

Status as of 2026-05-01: the LAND seed is ready for native think-cell chart and
text automation. Native think-cell `AddRangeData` table automation remains
blocked, but the Excel-only `AddRangeImage` table-image donor path is now proven.
The current 42-name seed still carries the eight table names as contract stubs
until the table-image donors are inserted into the layout/seed and updated from
Excel COM.

Update as of 2026-05-03: the production template role is now locked separately
from the think-cell seed role. `assets/LAND_template.pptx` is the clean SimCorp
shell and must contain zero think-cell ownership metadata. The think-cell
metadata is allowed only in the explicit seed/donor assets:
`assets/LAND_thinkcell_seed.pptx`,
`assets/LAND_thinkcell_seed_charts.pptx`, and
`assets/LAND_thinkcell_table_image_donor.pptx`. The production line enforces
this with `scripts/run_template_contract_gate.py` before deck generation.

Production deck path as of 2026-04-30:

```bash
.venv/bin/python scripts/build_land_presentation_decks.py --period 2026-Q2 --skip-seed
```

That builder creates the branded layout deck and validates the final package.
When `CHART_INJECTIONS` is non-empty it binds the seed through Windows
`ppttc.exe` and merges native think-cell chart shapes into the LAND layout
through PowerPoint COM. In the current publishable configuration,
`CHART_INJECTIONS` is empty because the donor chart output was weaker than
native PowerPoint table/bar replacements; the final deck is published directly
from the branded layout and must contain zero embedded donor chart parts.

Generated seed:

```bash
python3 scripts/build_thinkcell_seed_template.py --output assets/LAND_thinkcell_seed.pptx
```

The builder uses intact official think-cell donor slides from `_windows_test/official-*.potx`,
copies each donor slide as a whole OpenXML part graph, and rewrites the copied `think-cellXML`
CFB stream to the LAND AddRangeData name. It does not use `python-pptx` or PowerPoint UI
automation.

## Current coverage

- `assets/LAND_thinkcell_seed.pptx` contains all 42 LAND contract names.
- The 12 chart names are native think-cell chart objects:
  - `S04_PipeMovement`
  - `S05_PipelineByStage`
  - `S06_PipelineAging`
  - `S13_ForecastCategory`
  - `S15_ByOwner`
  - `S16_StageByIndustry`
  - `S17_TerritoryPerformance`
  - `S18_WinsLossesQTD`
  - `S19_Velocity`
  - `S21_ConcentrationRiskChart`
  - `S22_StaleActivity`
  - `S25_PipelineCreationVelocity`
- The text/KPI/footnote names are synthetic think-cell automation text fields.
- The 8 table names are currently off-slide automation text-field stubs, not native think-cell
  tables. This makes the strict 42-name contract present, but it is not the final table rendering
  path.

## Native table probe result

The native table route was probed from three independent angles and is blocked
for this install/API surface:

- Package evidence: `_windows_test/table-button-create-output.pptx`,
  `_windows_test/official-tables.potx`, and
  `_windows_test/official-useful-elements-tables.potx` contain `TCLayout`
  / `CSmartGrid` table-layout OLE streams, but no `m_strName`, datasheet,
  range-link, `PersistentType`, `AddRangeData`, or `m_bstrRangeName` surface.
- Raw name injection is unsafe: `_windows_test/probe_native_table_name_injection.py`
  injects `m_strName` into `CSmartGrid` / `CContainerSE`, and `ppttc.exe`
  wedges instead of binding the table.
- Live UI probes found no table automation naming path:
  `_windows_test/probe_table_minibar_uia.ps1`,
  `_windows_test/probe_table_shape_context_menu.ps1`,
  `_windows_test/probe_table_datasheet_from_selection.ps1`, and
  `_windows_test/probe_tc_table_shape_range_datasheet.ps1` only expose normal
  PowerPoint/formatting controls. No `Open Datasheet`, `AddRangeData Name`, or
  equivalent name editor appears for the ribbon-created table or selected cell
  shapes.

Conclusion: programmatic native table naming is not credible without first
obtaining a real data-backed, AddRangeData-named think-cell table donor. The
current seed should be treated as native charts/text plus table placeholders,
not as a finished native-table seed.

## Verified commands

```bash
python3 scripts/build_thinkcell_seed_template.py --output assets/LAND_thinkcell_seed.pptx

.venv/bin/python scripts/build_ppttc.py \
  --director "Jesper Tyrer" \
  --period 2026-Q2 \
  --template assets/LAND_thinkcell_seed.pptx \
  --strict-template

.venv/bin/python scripts/build_ppttc.py \
  --all-directors \
  --period 2026-Q2 \
  --template assets/LAND_thinkcell_seed.pptx \
  --strict-template

python3 scripts/run_thinkcell_windows_bridge.py \
  --ppttc state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.ppttc \
  --template assets/LAND_thinkcell_seed.pptx \
  --output _windows_test/jesper-land-seed-output.pptx \
  --expect-text "Jesper Tyrer" \
  --expect-text "2026-Q2" \
  --expect-text "Opening pipe (start of 2026-Q2)" \
  --expect-text "12883634.81"
```

Seed/bridge results on 2026-04-30:

- Strict template check passed.
- Strict template build passed for all 9 canonical directors.
- `ppttc.exe` on Windows VM exited `0`.
- Output deck: `_windows_test/jesper-land-seed-output.pptx`
- Output deck has 28 slides, 24 embedding parts, and all 42 named elements.
- The slide 4 pipe movement data was actually bound: the output XML contains
  `Opening pipe (start of 2026-Q2)` and `12883634.81`.
- The seed bridge can still bind the 42-name contract for future native-chart
  work, but the publishable Jesper deck now uses generated native PowerPoint
  table/bar replacements instead of merged donor chart objects.

Current Jesper publishable deck result on 2026-04-30:

- `scripts/director_deck_factory.py --skip-source --skip-seed` passes.
- Final deck has 28 slides, 0 embedding parts, and 54 native table XML nodes.
- The rendered QA output has 28 nonblank PNG slide images.
- Visible tables remain generated PowerPoint tables. The eight think-cell table
  names in the seed are contract stubs only.

## Remaining gap

Native think-cell table objects still need either:

1. a real named think-cell table donor, then the same CFB/XML rename path, or
2. a UI/mini-toolbar wire pass for the eight table objects if the add-in exposes
   `AddRangeData Name` on a different table variant, or
3. a pipeline decision to keep tables as native PowerPoint tables populated before `.ppttc`
   chart refresh.

Do not present the current table stubs as production-native think-cell tables.
Do not use raw `m_strName` injection into `CSmartGrid`/`CContainerSE`; it is a
known bad path.

## Table-image donor result

The usable table donor is not a native editable think-cell table. It is a
think-cell `Table as Image` object created from Excel and updated through Excel
COM `CreateUpdate().AddRangeImage(...)`.

Artifacts:

- Reusable named donor: `assets/LAND_thinkcell_table_image_donor.pptx`
- Raw donor from UI probe: `_windows_test/table-image-donor-raw.pptx`
- Named donor proof: `_windows_test/table-image-donor-named.pptx`
- Updated proof deck: `_windows_test/table-image-donor-updated.pptx`
- Creation harness: `_windows_test/create_table_image_donor_probe.ps1`
- COM proof harness: `_windows_test/test_addrangeimage_donor.ps1`

Verified proof:

- `template_named_elements(assets/LAND_thinkcell_table_image_donor.pptx)` returns
  `ProbeTableImage`.
- `_windows_test/test_addrangeimage_donor.ps1` opens the donor and calls
  `CreateUpdate().AddRangeImage(pres, "ProbeTableImage", Range("A1:D5"))`.
- The proof log reports `scheduled_addrangeimage=true`, `send_ok=true`, and
  saves `_windows_test/table-image-donor-updated.pptx`.
- The updated deck changes `ppt/embeddings/oleObject2.bin` and
  `ppt/media/image2.emf`, proving the table image refreshed from Excel.

Important constraint:

- `.ppttc` JSON did **not** update this donor; `_windows_test/table-image-donor.ppttc`
  produced an output deck but did not inject the test row text. The table-image
  lane must therefore be driven by Excel COM `AddRangeImage`, not `ppttc.exe`.
