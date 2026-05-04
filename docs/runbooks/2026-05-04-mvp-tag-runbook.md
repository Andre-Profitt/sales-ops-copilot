# LAND Review Factory MVP-tag runbook

Three tasks gating `land_review_full_28-mvp-v1`:

1. **PR 4.3** — Wire `tcseed.pptx` on Windows-VM (one-time, manual)
2. **PR 7.3** — Patrick canary smoke (after #1)
3. **PR 10.1** — 9-director acceptance + tag (after #2)

All three require the Mac-side branch `feat/land-review-factory-rebuild` on origin (already pushed; 45 commits).

---

## Step 1 — Wire `tcseed.pptx` on Windows-VM (steward, ~2–3 hr)

The clean 28-slide skeleton is already on disk: `assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx`. You insert + name Think-Cell elements once; the result becomes `tcseed.pptx`.

### 1.1 — ferry skeleton to VM

```bash
scp assets/templates/land_review_full_28/LAND_review_full_28.clean_skeleton.pptx \
    Windows-VM:/Users/Public/Documents/tcseed_build/
```

### 1.2 — produce the wire-checklist (do this now, before opening PowerPoint)

```bash
.venv/bin/python -c "
import yaml
r = yaml.safe_load(open('config/thinkcell/land_review_full_28.binding_registry.yml'))
for s in r['slides']:
    for el in s['elements']:
        if el['lane'] in ('ppttc_text', 'ppttc_chart', 'excel_table_image'):
            print(f\"{s['slide_id']}  {el['lane']:18}  {el['name']}  ({el['kind']})\")
" > /tmp/tcseed_checklist.txt
wc -l /tmp/tcseed_checklist.txt    # ~70 elements expected
```

Print or open this checklist alongside PowerPoint while wiring.

### 1.3 — open the skeleton in PowerPoint on the VM

- Verify: 28 slides, no PowerPoint repair prompt, SimCorp brand visible.
- If repair prompts: stop, escalate. Skeleton is supposed to be clean.

### 1.4 — wire `ppttc_text` elements first (fastest)

For each `ppttc_text` row in the checklist (cover fields, titles, source notes, footnotes, KPI scalars, narrative boxes):

1. Click the existing placeholder text frame on that slide
2. Think-Cell mini-toolbar → "Add text field" (automation text)
3. AddRangeData Name dialog → enter the registry name **exactly** (e.g., `S01_DirectorName`)
4. Save (Ctrl+S)

Tick the checklist line as you go. Atlas-assisted approach — query for canonical SimCorp positioning before placing each:

```bash
# (run on Mac, before each wiring batch)
.venv/bin/python scripts/atlas/atlas_query.py \
  --corpus state/atlas/corpus.jsonl \
  --query-vector "1.0,0.0,0.0,0.0,0.0" \
  --role canonical_brand_reference \
  --top-k 3 \
  --out /tmp/precedent.json
# requires live embeddings to be useful — see Step 0 below
```

### 1.5 — wire `ppttc_chart` elements

For each `ppttc_chart` row (S04 waterfall, S05/S06/S15/S17/S22 horizontal bar, S13/S18 column, S16 stacked bar, S21 chart, S25 line/column):

1. Insert → Think-Cell → match `kind` to chart type:
   - `bar_chart` → Stacked bar (horizontal)
   - `column_chart` → Stacked column (vertical)
   - `waterfall_chart` → Waterfall
   - `stacked_bar_chart` → 100% stacked bar
   - `line_chart` → Line
2. AddRangeData Name → registry name (e.g., `S05_PipelineByStage`)
3. Add a default 2×2 datasheet so Think-Cell saves the chart skeleton
4. Save

### 1.6 — wire `excel_table_image` placeholders

For each `excel_table_image` row (S07/S08/S09/S11/S12/S21/S24/S26):

1. Insert any temporary picture on the slide
2. Selection Pane → set shape **name** to the registry name (e.g., `S07_TopDealsLand_Image`)
3. Right-click → Think-Cell → "Add Range Image" → registry name
4. Save

### 1.7 — save final tcseed

`File → Save As → LAND_review_full_28.tcseed.pptx` in `/Users/Public/Documents/tcseed_build/`.

### 1.8 — reopen verification

Close PowerPoint completely. Reopen `tcseed.pptx`. **Verify:** no repair prompt. Think-Cell loads cleanly. All named elements visible in Selection Pane.

### 1.9 — ferry back to Mac

```bash
scp Windows-VM:/Users/Public/Documents/tcseed_build/LAND_review_full_28.tcseed.pptx \
    assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx
```

### 1.10 — run contract preflight

```bash
.venv/bin/python scripts/verify_thinkcell_template_contract.py \
  --template assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  --registry config/thinkcell/land_review_full_28.binding_registry.yml \
  --out state/2026-Q2/__regional__/template_contract_report.json
```

Expected: `OK: N/N required shapes present, no forbidden text (patterns: atlas)`. If `required_elements_missing` is non-empty, return to step 1.4 and wire the missing names. Iterate until pass.

### 1.11 — capture inventory + cert

```bash
.venv/bin/python -c "
from pptx import Presentation
import json
prs = Presentation('assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx')
inv = []
for i, slide in enumerate(prs.slides, 1):
    for shape in slide.shapes:
        inv.append({'slide': i, 'name': shape.name, 'type': str(shape.shape_type)})
print(json.dumps(inv, indent=2))
" > assets/templates/land_review_full_28/LAND_review_full_28.named_element_inventory.json
```

Then write `LAND_review_full_28.seed_certification.md` with steward name, build host, dates, contract verifier output, and the reopen-check confirmation.

### 1.12 — commit

```bash
git add \
  assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
  assets/templates/land_review_full_28/LAND_review_full_28.named_element_inventory.json \
  assets/templates/land_review_full_28/LAND_review_full_28.seed_certification.md
git commit -m "feat(template): certified tcseed.pptx + inventory + steward certification"
git push
```

---

## Step 0 (optional) — Refresh atlas live embeddings before wiring

Atlas precedent queries (used in Step 1.4) are most useful with live embeddings. Refresh:

```
! az login --tenant "aa81b43f-3969-4fd4-80c9-84c411508d82" --scope "https://cognitiveservices.azure.com/.default"
```

Then:

```bash
.venv/bin/python scripts/atlas/build_atlas_corpus.py
```

Expected: `embedded N/N` progress lines; final `OK: 651 chunks -> state/atlas/corpus.jsonl` (chunk count may vary slightly as `~/Downloads/042026 Sales Operations Reporting.pptx` evolves).

Without live embeddings, `atlas_query.py --query-vector` still works for tests but `--query "<NL>"` does not.

---

## Step 2 — Patrick canary smoke (after Step 1)

### 2.1 — capture SSIM golden BEFORE any data binding

Render the bare tcseed (no data yet, Think-Cell will show empty datasheets) once and save it as the golden:

```bash
mkdir -p state/2026-Q2/__regional__/ssim_baselines
cp assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx \
   state/2026-Q2/__regional__/ssim_baselines/tcseed_golden.pptx
```

### 2.2 — run the orchestrator on Patrick

```bash
.venv/bin/python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors Patrick-Gaughan \
  --strict 2>&1 | tee state/2026-Q2/__regional__/patrick_canary_$(date +%Y%m%d-%H%M).log
```

Expected order of step-banners:

- `==> validate_registry` — pass
- `==> verify_template_contract` — pass
- `==> Patrick Gaughan :: source_notes` — pass
- `==> Patrick Gaughan :: insight_titles` — depends on whether `metrics.json` exists; OK if it falls back to defaults
- `==> Patrick Gaughan :: ppttc` — pass; emits `state/2026-Q2/Patrick-Gaughan/Patrick-Gaughan-LAND-2026-Q2.ppttc` and `render_evidence_manifest.json`
- `==> Patrick Gaughan :: render` — depends on `python -m tcrender` CLI surface; if it fails, see 2.3
- `==> Patrick Gaughan :: refresh_images` — runs the new file-based PS1
- `==> Patrick Gaughan :: verify` — binding-level evidence check

### 2.3 — render fallback (if `python -m tcrender` doesn't expose the CLI)

The `libs/tcrender/` package exists but the orchestrator assumes a `tcrender` CLI module. If the entry point isn't registered, run the existing tcrender bridge directly:

```bash
# Adapt to whatever scripts/.../render command tcrender currently exposes;
# the orchestrator's `python -m tcrender` is a placeholder per the plan.
```

Inspect `libs/tcrender/tcrender/__main__.py` (if present) or `libs/tcrender/setup.py` / `pyproject.toml` for the actual entry point.

### 2.4 — visual regression vs baseline (after first successful render)

Once `state/2026-Q2/Patrick-Gaughan/rendered_final.pptx` exists, capture it as the Patrick golden:

```bash
cp state/2026-Q2/Patrick-Gaughan/rendered_final.pptx \
   state/2026-Q2/__regional__/ssim_baselines/Patrick-Gaughan_golden.pptx
```

On subsequent runs:

```bash
.venv/bin/python scripts/ssim_visual_regression.py \
  --baseline state/2026-Q2/__regional__/ssim_baselines/Patrick-Gaughan_golden.pptx \
  --candidate state/2026-Q2/Patrick-Gaughan/rendered_final.pptx \
  --out state/2026-Q2/Patrick-Gaughan/ssim_report.json \
  --threshold 0.92
```

### 2.5 — visual spot-check

Open `rendered_final.pptx` in Keynote/Preview/PowerPoint. **Verify:**

- 28 slides
- No PowerPoint repair prompt
- Cover shows `Patrick Gaughan` and `2026-Q2` in the right placeholders
- Every analytic slide has a non-empty title and source note
- Charts on S04/S05/S06/S13/S15/S16/S17/S18/S19/S21/S22/S25 show real data
- Table images on S07/S08/S09/S11/S12/S21/S24/S26 show real rows

Commit any state files you want preserved.

---

## Step 3 — 9-director acceptance + tag (after Step 2)

### 3.1 — preflight all 9 directors have prerequisites

```bash
for d in Megan-Miceli Patrick-Gaughan Jesper-Tyrer Sarah-Pittroff Francois-Thaury Dan-Peppett Christian-Ebbesen Mourad Adam-Steinhouse; do
  for f in land.model.xlsx trends.json brief.md; do
    test -f "state/2026-Q2/$d/$f" && echo "OK $d/$f" || echo "MISSING $d/$f"
  done
done
```

Any MISSING must be regenerated through the existing per-director ETL before proceeding.

### 3.2 — run all-director strict batch

```bash
.venv/bin/python scripts/run_land_review_full_28_pipeline.py \
  --period 2026-Q2 \
  --directors all \
  --jobs 4 \
  --strict 2>&1 | tee state/2026-Q2/__regional__/run_log_$(date +%Y%m%d-%H%M).log
```

### 3.3 — inspect summary

```bash
cat state/2026-Q2/__regional__/land_review_full_28_run_summary.json | \
  jq '{passed, failed, directors: [.directors[] | {director, status, first_failure}]}'
```

Expected: `passed: 9, failed: 0`.

### 3.4 — per-director artifact check

```bash
for d in Megan-Miceli Patrick-Gaughan Jesper-Tyrer Sarah-Pittroff Francois-Thaury Dan-Peppett Christian-Ebbesen Mourad Adam-Steinhouse; do
  echo "=== $d ==="
  for f in \
    "${d}-LAND-2026-Q2.ppttc" \
    render_evidence_manifest.json \
    rendered_stage1.pptx \
    rendered_final.pptx \
    qa_report.json \
    insight_titles.json \
    source_notes.json
  do
    test -f "state/2026-Q2/$d/$f" && echo "  OK $f" || echo "  MISSING $f"
  done
done
```

### 3.5 — spot-check 3 decks visually

Open Patrick, Jesper, Adam `rendered_final.pptx`. Same checklist as Step 2.5.

### 3.6 — migrate legacy seeds (now safe)

```bash
git mv assets/LAND_thinkcell_seed.pptx assets/legacy/do_not_use_in_factory/
git mv assets/LAND_thinkcell_seed.pre-stripdev.pptx assets/legacy/do_not_use_in_factory/
git mv assets/LAND_thinkcell_seed_polished.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed_polished_v2.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed_charts.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_thinkcell_seed.pre-jinja-cleanup.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git mv assets/LAND_seed_thinkcell.pptx assets/legacy/do_not_use_in_factory/ 2>/dev/null || true
git commit -m "chore(legacy): quarantine debris seeds; new factory is sole production lane"
```

### 3.7 — update legacy README

Edit `assets/legacy/do_not_use_in_factory/README.md`:

- Change "Not yet moved" section → "Moved on YYYY-MM-DD after PR 10 acceptance"
- Add SHA of each moved file (`shasum *.pptx`)

### 3.8 — tag the release

```bash
git tag -a land_review_full_28-mvp-v1 -m "MVP land_review_full_28 factory: 9/9 directors pass strict pipeline"
git push origin main --tags
```

(Or push the tag without merging if you want to stay on the feature branch:

````bash
git push origin land_review_full_28-mvp-v1
```)

---

## Acceptance criteria (Definition of Done)

- [ ] Registry validates clean
- [ ] tcseed contract passes (0 missing required, 0 forbidden text)
- [ ] All 9 directors complete (`passed: 9, failed: 0`)
- [ ] All 9 decks open without repair prompt
- [ ] Every analytic slide has insight title
- [ ] Every analytic slide has source note
- [ ] No deck uses the old seed (legacy quarantined under `assets/legacy/`)
- [ ] ARR/ACV separation enforced
- [ ] Binding-level verifier is the publish gate (`tcrender.verify` raises `DeprecationWarning`)
- [ ] Tag pushed
````
