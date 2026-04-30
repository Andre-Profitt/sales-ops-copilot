# Handoff — think-cell `.ppttc` runtime audit for LAND-monthly

**For:** a fresh Claude/Codex session, no prior context.  
**Date:** 2026-04-30 late evening  
**Repo:** `~/code/apps/sales-ops-copilot/` on `main`  
**Current local head:** `86dc787` (`fix(deck): gate experimental think-cell template path`)  
**Operator:** Andre (apro@simcorp.com)

## TL;DR

The **data emitter is real**. The **auto-generated think-cell template is not production-valid yet**.

What is proven:

- `scripts/build_ppttc.py` reads the new per-director workbook data and emits valid `.ppttc` JSON.
- The official think-cell sample `.ppttc` opens successfully on this Mac.
- A minimal `.ppttc` that references `assets/LAND_template.pptx` with empty `data` also opens successfully.
- A plain director-specific `.pptx` with **no donor chart injection** opens in PowerPoint.
- The current donor-chart-generated `*-template.pptx` is rejected by think-cell during real `.ppttc` import:
  - **`The .ppttc file is bad. The template failed to load.`**
- That failure still happens on reduced diagnostic variants:
  - a filtered `.ppttc` with only `S04_PipeMovement`
  - a filtered `.ppttc` with only `S04_PipeMovement`, `S05_PipelineByStage`, `S06_PipelineAging`

So the remaining blocker is **not the data**, **not the host think-cell install**, and **not the base LAND deck itself**.  
The blocker is the **generated template content / donor-chart injection path**.

## Important correction

Earlier today the working assumption was:

- “the generated director-specific template is effectively wired”

That is **false**.

Directly opening the generated `.pptx` in PowerPoint is **not** enough to prove `.ppttc` compatibility. The real success gate is:

1. build `.ppttc`
2. open the `.ppttc`
3. think-cell imports the template without an error window
4. PowerPoint ends up with a real presentation open

The current generated template fails at step 3.

## Current code state

### `scripts/build_ppttc.py`

This file is real and useful.

- Emits `.ppttc` from:
  - `state/2026-Q2/<DirectorSlug>/land.model.xlsx`
  - `state/2026-Q2/<DirectorSlug>/land.xlsx`
  - `state/2026-Q2/<DirectorSlug>/trends.json`
  - `state/2026-Q2/<DirectorSlug>/brief.md`
- Builds a director-specific generated template when the default `assets/LAND_template.pptx` path is used.
- Filters emitted entries to the names actually backed by the generated template.
- **Now blocks the default generated-template path unless `--experimental-generated-template` is passed.**

Read first:

- [scripts/build_ppttc.py](/Users/test/code/apps/sales-ops-copilot/scripts/build_ppttc.py)
- especially:
  - top-level warning/docs at line 1
  - generated-template filtering around line 779
  - CLI gate around line 821

### `scripts/ppttc_template.py`

This file is where the risky path lives.

- `build_director_template(...)` clones the base deck and fills text/table slides.
- `_inject_donor_charts(...)` copies think-cell donor chart package parts into the target `.pptx`.
- `template_named_elements(...)` inspects embedded think-cell names.
- `_rewrite_relationships(...)` was fixed so repeated donor `rId`s reuse a single rel instead of duplicating `oleObject` rels.

Read first:

- [scripts/ppttc_template.py](/Users/test/code/apps/sales-ops-copilot/scripts/ppttc_template.py)
- especially:
  - `build_director_template(...)`
  - `template_named_elements(...)`
  - `_inject_donor_charts(...)`
  - `_rewrite_relationships(...)`

## Exact proven facts

### 1. Official think-cell sample works on this machine

Test path:

```bash
open "/Library/Application Support/Microsoft/think-cell/ppttc/sample.ppttc"
osascript -e 'tell application "Microsoft PowerPoint" to count presentations'
```

Observed:

- PowerPoint ended up with `1` presentation open.

This matters because it means the host install is capable of processing `.ppttc`.

### 2. The base LAND template opens normally in PowerPoint

Test path:

```bash
osascript -e 'tell application "Microsoft PowerPoint" to open POSIX file "/Users/test/code/apps/sales-ops-copilot/assets/LAND_template.pptx"'
```

Observed:

- `LAND_template` opened as a presentation.

### 3. The base LAND template also works as a bare `.ppttc` template substrate

Diagnostic artifact:

- `/tmp/land-empty.ppttc`

Contents:

```json
[
  {
    "template": "/Users/test/code/apps/sales-ops-copilot/assets/LAND_template.pptx",
    "data": []
  }
]
```

Observed:

- think-cell opened it without a `Grant File Access` or `think-cell Message` error
- PowerPoint ended up with `1` open presentation (`Presentation1`)

This matters because it proves the base LAND deck is a valid `.ppttc` template substrate. The problem starts when we try to synthesize named think-cell elements programmatically.

### 4. A no-injection director template opens normally in PowerPoint

Diagnostic artifact:

- `/tmp/ppttc-audit-noinject/Jesper-Tyrer-noinject-LAND-2026-Q2-template.pptx`

Observed:

- This opens directly in PowerPoint.

This matters because it isolates the failure away from the general “clone deck + fill tables/text” path.

### 5. The generated donor-chart template fails during real `.ppttc` import

Real test path:

```bash
open "/Users/test/code/apps/sales-ops-copilot/state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.ppttc"
```

Observed:

- PowerPoint first asks for file access to the generated `Jesper-Tyrer-LAND-2026-Q2-template.pptx`
- after granting access, think-cell shows:

```text
The .ppttc file is bad. The template failed to load.
```

### 6. Reduced subsets still fail

I built filtered diagnostic `.ppttc` files against reduced generated templates:

- `/tmp/slide4-filtered.ppttc`
- `/tmp/first3-filtered.ppttc`

These reference:

- `/tmp/ppttc-singletons2/slide4/slide4-LAND-2026-Q2-template.pptx`
- `/tmp/ppttc-groups/first3/first3-LAND-2026-Q2-template.pptx`

Observed after file access grant:

- same think-cell message:

```text
The .ppttc file is bad. The template failed to load.
```

This is the strongest current evidence that **even the one-chart donor-copy approach is not yet valid as a `.ppttc` template**.

## Commits that matter

Top-of-stack, in order:

- `f1bf219` — `feat(deck): build think-cell ppttc emitter`
- `f4cb1f0` — `feat(deck): build director-specific think-cell templates`
- `86dc787` — `fix(deck): gate experimental think-cell template path`

## What changed in the latest audit

### Good fixes

1. **Relationship rewrite bug fixed**

- repeated donor `rId`s were creating duplicate `oleObject` rels
- fixed in `scripts/ppttc_template.py`

2. **Generated template names are now discoverable**

- `template_named_elements(...)` added
- used to filter generated `.ppttc` payloads to only backed names

3. **Broken default path is now gated**

The default CLI path no longer pretends to be production-ready.

This now fails loudly:

```bash
python3 scripts/build_ppttc.py --director "Jesper Tyrer" --period 2026-Q2
```

Observed message:

```text
The default auto-generated think-cell template path is still experimental...
```

Research-only path still exists:

```bash
python3 scripts/build_ppttc.py \
  --director "Jesper Tyrer" \
  --period 2026-Q2 \
  --experimental-generated-template
```

### Still open

1. **Primary blocker**

- generated donor-chart template rejected by real think-cell import

2. **Slide 11 is still not native think-cell**

- `Renewal Pipeline` is still rendered by `_fill_renewal_pipeline_slide(...)`
- that is a PowerPoint table, not a think-cell table + Harvey balls

3. **Style is not programmatically enforced**

- `assets/SimCorp-thinkcell-style.xml` still has to already be loaded into the real saved template
- JSON automation does not solve this by itself

4. **Custom-template validation is weak**

- custom `--template` paths are only checked for “has any named elements”
- not “covers the whole intended contract”

## Current emitter contract

The current emitter can produce **42** named payload entries for a full manual template path.

Representative names:

```text
S01_DirectorName
S01_Period
S01_ScopeLabel
S02_ExecSummaryLeft
S02_ExecSummaryRight
S04_PipeMovement
S05_PipelineByStage
S06_PipelineAging
S07_TopDealsLand
S08_TopDealsExpand
S09_PendingCommercialApproval
S11_RenewalPipeline
S12_GRRProxyTable
S12_GRRProxyFootnote
S13_ForecastCategory
S15_ByOwner
S16_StageByIndustry
S17_TerritoryPerformance
S18_WinsLossesQTD
S19_Velocity
S21_ConcentrationRiskChart
S22_StaleActivity
S24_AccountExpansion
S25_PipelineCreationVelocity
S26_ActionItems
S27_RisksOutlook
... plus the S21 and S23 text/table KPI fields
```

The current **generated experimental template** only backs **12 chart names**:

```text
S04_PipeMovement
S05_PipelineByStage
S06_PipelineAging
S13_ForecastCategory
S15_ByOwner
S16_StageByIndustry
S17_TerritoryPerformance
S18_WinsLossesQTD
S19_Velocity
S21_ConcentrationRiskChart
S22_StaleActivity
S25_PipelineCreationVelocity
```

Do not confuse those 12 with the intended full automation contract.

## Recommended mission for Claude

### Fastest path to green

Stop trying to ship the donor-chart-generated template as production.

Keep `assets/LAND_template.pptx` as the substrate. It already survives `.ppttc` creation.

Instead:

1. Create or save **one real manually wired think-cell template** in PowerPoint.
2. Use real think-cell objects in that template.
3. Name them to match the emitter contract from `_ppttc_entries_from_context(...)`.
4. Load `assets/SimCorp-thinkcell-style.xml` into that template before saving it.
5. Then run:

```bash
python3 scripts/build_ppttc.py \
  --all-directors \
  --period 2026-Q2 \
  --template /absolute/path/to/manual-thinkcell-template.pptx
```

6. Then verify by opening one emitted `.ppttc`.

That is the fastest route to an honest production result.

### If Claude insists on salvaging donor injection

Then force this proof order:

1. one generated template
2. one named chart
3. one filtered `.ppttc`
4. real `.ppttc` open
5. zero think-cell error windows

Do **not** scale to multi-slide templates until step 4 works for the one-chart case.  
Right now, the one-chart case still fails.

## Practical notes for local testing

### Use the shell/Terminal automation lane

Terminal already has Apple Events access to PowerPoint and `System Events`. That is useful for:

- checking `count presentations`
- listing PowerPoint windows
- clicking `Grant File Access`

### Real `.ppttc` open path

Use:

```bash
open /path/to/file.ppttc
```

Do **not** treat `open -a PowerPoint file.ppttc` or direct `.pptx` open as a valid end-to-end think-cell test.

### First-open file access prompt

PowerPoint may require manual file access grant to a newly generated template path.  
That is normal. The important part is what happens **after** access is granted.

## Files Claude should read first

1. [docs/WIRING_QUICKREF.md](/Users/test/code/apps/sales-ops-copilot/docs/WIRING_QUICKREF.md)
2. [docs/THINKCELL_SETUP.md](/Users/test/code/apps/sales-ops-copilot/docs/THINKCELL_SETUP.md)
3. [scripts/build_ppttc.py](/Users/test/code/apps/sales-ops-copilot/scripts/build_ppttc.py)
4. [scripts/ppttc_template.py](/Users/test/code/apps/sales-ops-copilot/scripts/ppttc_template.py)
5. [docs/CODEX_REVIEW_2026-04-30.md](/Users/test/code/apps/sales-ops-copilot/docs/CODEX_REVIEW_2026-04-30.md)

## Hard constraints

- Do not tell Andre it works unless a real `.ppttc` opens into a real presentation.
- Do not ship the generated donor-chart template path as production.
- Do not push to origin.
- Do not pivot to native python-pptx charts.
- Do not ignore Slide 11 if the goal is “fully native think-cell”.

## Suggested first command for Claude

If Claude wants the fastest honest reproduction:

```bash
cd ~/code/apps/sales-ops-copilot
. .venv/bin/activate
python3 scripts/build_ppttc.py --director "Jesper Tyrer" --period 2026-Q2
```

Expected result right now:

- explicit failure telling you the generated template path is experimental

That gate is intentional and correct.
