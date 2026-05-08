# Template Visual Quality Audit - May 2026 Sales Director Factory

Date: 2026-05-03

## Verdict

The current deck system is production-safe and visually clean enough for review,
but it is not yet the best template we can make.

The strongest lane is the 28-slide linked deck: it has the cleanest
think-cell/table-image wiring, zero native PowerPoint tables, and all 19
table-image surfaces linked through the workbook. The 16-slide meeting-spine
deck is better for leadership review, but it deliberately rebuilds several
high-value slides with native PowerPoint shapes/tables for story clarity. That
means the final meeting spine is not pure think-cell end-to-end.

## Current Evidence

| Asset | Role | Slides | Named think-cell elements | Embedded OLE | Native PPT tables | Status |
|---|---|---:|---:|---:|---:|---|
| `assets/LAND_template.pptx` | SimCorp shell / visual source | 28 | 0 | 0 | 0 | Brand shell only; not a `.ppttc` automation template. |
| `assets/LAND_thinkcell_seed.pptx` | automation seed | 28 | 42 | 24 | 0 | Best named-element substrate. |
| `state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2-table-image-linked.pptx` | full linked deck | 28 | 19 | 20 | 0 | Best current think-cell/table-image production surface. |
| `state/2026-Q2/Jesper-Tyrer/factory/meeting-spine/Jesper-Tyrer-LAND-2026-Q2-meeting-spine.pptx` | 16-slide review spine | 16 | 12 | 13 | 5 | Stronger story spine; mixed think-cell + native PPT action layer. |

Rendered review artifact:

- `state/2026-Q2/Jesper-Tyrer/factory/original-comment-assessment/Jesper-Tyrer-2026-Q2-full-contact-sheet.jpg`

## Gates Rerun

```text
python3 scripts/build_thinkcell_visual_contract_plan.py --period 2026-Q2
status=pass directors=9 include=69 candidate=17 fallback=3

python3 scripts/build_thinkcell_template_intelligence_db.py --period 2026-Q2
summary={"candidate_blockers": 6, "candidates": 6, "contracts": 12, "templates": 62}

python3 scripts/validate_render_lane_contract.py --contract config/sd_factory_render_lane_contract.2026-Q2.json
render_lane_contract: pass
monthly_slots=42
component_proofs=17
table_image_contracts=9
```

Existing all-9 package gates are also green:

- `state/2026-Q2/__regional__/publish_gate_all_smoke/regional_publish_gate.json`: 9/9 pass.
- `state/2026-Q2/__regional__/visual_gate/review_package/review_package_visual_gate.json`: 9 decks, 16 slides each, render pass.

## What Uses think-cell Properly

- The seed deck has 42 named automation slots and is the right substrate for
  `.ppttc`/deterministic rendering.
- The full linked deck has 19 named table-image surfaces, each paired with an
  OLE/table-image object and workbook-defined source range.
- The render-lane contract now covers 42 monthly binding slots, 17 component
  proofs, and 9 table-image contracts.
- Bar/column, waterfall, Mekko, and core native chart lanes are proven at L5.
- Dense tables use Excel COM `AddRangeImage` by design. This is not a native
  editable think-cell table, but it is currently the only repeatable, audited,
  cross-region table lane.

## Where It Is Not Yet Best

1. The final meeting spine is mixed-mode.
   Slides 3, 4, 5, 7, and 14 are rebuilt with native PowerPoint tables/shapes
   by `meeting_spine_action_layer.py`. This improved the meeting narrative, but
   it weakens the claim that the final deck is deeply think-cell-native.

2. Scatter and timeline visuals are not production-promoted.
   The visual contract plan says several directors have data shapes for deal
   risk scatter and renewal timeline, but template intelligence blocks current
   candidate PPTX files because they still contain stock template residue.

3. Native editable think-cell tables remain blocked.
   Current tables are traceable and visually stable, but not editable think-cell
   tables. Do not represent them as native think-cell tables.

4. The visual system is clean but still conservative.
   The contact sheet reads as structured and executive-safe, but also white,
   table-heavy, and occasionally sparse. Slides 10 and 13 especially need a
   stronger proof object or tighter composition if we want a premium review
   spine.

5. Cover and closing slides are branded but generic.
   They are acceptable, not distinctive. A director-facing shell should make
   the first viewport feel like SimCorp operating intelligence, not only a
   corporate gradient.

## Recommended Upgrade Plan

### P0 - lock honesty and gates

- Rename the lane explicitly in docs and manifests:
  `think-cell/table-image linked deck` and `mixed-mode meeting spine`.
- Add a meeting-spine audit gate that reports native PPT table slides and
  distinguishes deliberate action-layer rebuilds from accidental regressions.
- Keep the current all-9 package green while doing this.

### P1 - improve the actual template

- Promote one clean scatter donor for Q2 deal risk.
  Rebuild the QTR04 candidate with zero placeholder/template residue, bind it
  from the named range, render it, and create a promotion record.
- Promote one clean timeline/Gantt donor only where renewal dates are
  materially distinct.
  Do not use timelines for generic month-end action lists.
- Convert the meeting-spine rebuilt slides to either:
  1. promoted think-cell/native chart surfaces, or
  2. explicitly governed native editorial slides with no pretend think-cell
     status.

### P2 - design polish

- Replace heavy table-first slides with a stronger chart-plus-evidence rhythm
  where the data shape supports it.
- Tighten whitespace on slides 10 and 13.
- Upgrade cover/closing to a more distinctive SimCorp operating-review shell.
- Reduce purple table headers; use SimCorp blue/navy as default and reserve
  purple/coral for emphasis and risk.

## Bottom Line

For deterministic monthly production, the current template is good enough to
ship a review package. For a best-in-class monthly deck factory, the next step
is not more generic template styling. It is promoting clean, governed think-cell
scatter/timeline donors and making the meeting-spine action layer either
think-cell-backed or explicitly editorial-native.

## Polished V2 Pilot

Added on 2026-05-03:

- `scripts/meeting_spine_action_layer.py` now rebuilds slide 2 as an operating
  summary instead of preserving the prior table-heavy summary.
- Slide 4 now adds a forecast-composition proof object.
- Slide 5's Q2 close inspection map is visually strengthened with a May
  decision window and EUR 1M reference line.
- Slide 7 now adds a renewal timing proof when renewal dates are distinct; it
  suppresses the timeline when dates do not justify it.
- The action layer smoke-applied cleanly to all 9 directors using copied decks.

Pilot artifacts:

- `state/2026-Q2/Jesper-Tyrer/factory/polish/Jesper-Tyrer-LAND-2026-Q2-meeting-spine-polished-v2.pptx`
- `state/2026-Q2/Jesper-Tyrer/factory/polish/Jesper-Tyrer-2026-Q2-polished-v2-contact-sheet.jpg`
- `state/2026-Q2/Jesper-Tyrer/factory/polish/annotated-assessment-v2/Jesper-Tyrer-2026-Q2-annotated-original-assessment.json`

V2 verification:

```text
python3 -m py_compile scripts/meeting_spine_action_layer.py
python3 -m ruff check scripts/meeting_spine_action_layer.py
python3 scripts/render_deck_for_review.py <polished-v2.pptx> --output-dir <rendered-v2>
python3 scripts/assess_deck_against_annotated_original.py --target-deck <polished-v2.pptx>
```

Results:

- Render smoke: pass, 16 rendered slides.
- Rebekka-comment assessment: 13 covered, 2 manual visual-review items, 1
  covered by omission for churn source governance.
- All-9 copied-deck action-layer smoke: pass.

## Polished V2 Production Promotion

Promoted on 2026-05-03 through the full regional production line.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-123609/manifest.json`
- `state/2026-Q2/__regional__/production_runs/20260503-123609/production_summary.md`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates`

Promotion command:

```text
python3 scripts/run_regional_production_line.py --period 2026-Q2 --jobs 4
```

Production results:

- Full production line: pass.
- Meeting-spine build and smoke: pass.
- Regional publish gate: 9/9 pass.
- APAC strict-intel full audit: pass.
- APAC strict-intel meeting-spine audit: pass.
- Downloads review package validation: pass, 9 decks present.
- Review package visual gate: pass, 9 decks x 16 slides rendered with no
  reported visual problems.

One regression was caught before promotion: the polished action layer had
changed exact APAC audit language for Q1 slips, deckwide ARR basis, and Q2
close-date guardrails. The deck builder now preserves those phrases inside the
rebuilt slides while keeping the polished proof objects.

## QTR04 Native think-cell Scatter Pilot

Added on 2026-05-03 after production promotion.

Run artifacts:

- `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260503-qtr04-clean-scatter/manifest.json`
- `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260503-qtr04-clean-scatter/Jesper-Tyrer/QTR04_DealRisk_Scatter/decision_record.json`
- `state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260503-qtr04-clean-scatter/Jesper-Tyrer/QTR04_DealRisk_Scatter/side_by_side_contact_sheet.jpg`

What improved:

- `scripts/prove_thinkcell_stock_donor_contract.py` now rebuilds QTR04 from a
  clean one-slide Scatter/Bubble donor instead of preserving the stock second
  slide and placeholder comments.
- The QTR04 `.ppttc` payload now follows think-cell's documented scatter data
  shape: one row per point, with deal label, probability, ARR, push pressure,
  and readiness group.
- Fresh QTR04 proof is back to `pass`: seed, payload, Windows `ppttc.exe`
  bridge, bound package assertion, render, and rendered visibility.
- Fresh insertion pilot is `candidate_created`: the candidate PPTX is zip
  readable, has one slide, contains no native PowerPoint table, and preserves
  ARR/Type/ACV guardrails.

Decision:

- Production insertion is blocked.
- Reason: the candidate is now a clean native think-cell chart surface, but the
  inherited stock donor grammar still does not create a leadership-better
  probability-vs-ARR inspection map than the current meeting-spine slide.
  The side-by-side record is the evidence. Do not replace slide 5 with QTR04
  until the donor grammar or chart configuration produces the intended axes
  and named-deal readability.

## Branding Correction: Squared Proof Panels

Added on 2026-05-03 after review feedback that curved/rounded boxes do not fit
the expected SimCorp deck language.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-125209/manifest.json`
- `state/2026-Q2/__regional__/production_runs/20260503-125209/production_summary.md`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates`

What changed:

- `scripts/meeting_spine_action_layer.py` now uses square-cornered rectangles
  for the reusable soft panels and status labels.
- The full 9-director package was rebuilt and passed all 17 production gates.
- Package-level XML verification checked 9 PPTX files and found `roundRect=0`.

## Brand Style Gate + Type Scale

Added on 2026-05-03 after review feedback that the deck needs stronger SimCorp
brand discipline and more consistent text sizing.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-130335/manifest.json`
- `state/2026-Q2/__regional__/brand_style_gate/review_package/review_package_brand_style_gate.json`
- `state/2026-Q2/__regional__/brand_style_gate/review_package/review_package_brand_style_gate.md`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates`

What changed:

- `scripts/meeting_spine_action_layer.py` now normalizes all explicit text runs
  across the meeting-spine deck to the approved type scale:
  `5.5, 6, 6.5, 7, 8, 8.5, 9, 9.5, 10, 10.5, 11.5, 12, 14, 15, 16, 18, 24`.
- `scripts/run_review_package_brand_style_gate.py` blocks rounded/curved
  PowerPoint geometry, non-brand explicit fonts, text below 5.5pt, and
  off-scale font sizes before package publish.
- `scripts/run_may_regional_production_line.py` now runs
  `review_package_brand_style_gate` after the render visual gate and copies the
  report into the review package.
- The full 9-director package was rebuilt and passed all 18 production gates.
- Gate result: 9/9 decks passed, 0 rounded geometry findings, 0 warnings, and
  17 approved font sizes per deck.

## Stale think-cell Ownership Scrub

Added on 2026-05-03 after PowerPoint showed the think-cell warning:
`Selected elements were changed without think-cell`.

Root cause:

- Several retained table-image slides carried invisible
  `think-cell data - do not delete` OLE objects and
  `THINKCELLSHAPEDONOTDELETE` tags even though the user-visible surface was a
  static picture or native PowerPoint table.
- That made think-cell treat non-think-cell table/image surfaces as
  think-cell-owned after Python edited the deck.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-131520/manifest.json`
- `state/2026-Q2/__regional__/production_runs/20260503-131520/production_summary.md`
- `state/2026-Q2/__regional__/brand_style_gate/review_package/review_package_brand_style_gate.json`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates`

What changed:

- `scripts/scrub_stale_thinkcell_metadata.py` removes stale think-cell OLE
  shapes, tag relationships, presentation/master/layout think-cell tags, and
  orphaned think-cell embedding parts from generated meeting-spine decks.
- The scrub round-trips the cleaned deck through `python-pptx` so the package
  remains renderable by LibreOffice and PowerPoint.
- `scripts/build_regional_meeting_spine_decks.py` runs the scrub during every
  meeting-spine build and fails if any stale think-cell tokens remain.
- `scripts/run_review_package_brand_style_gate.py` now fails the review package
  if stale think-cell ownership metadata survives.

Result:

- Full 9-director run passed all 18 gates.
- Package verification found 0 stale think-cell ownership tokens across all 9
  decks.
- Surface truth for each current meeting-spine deck: 5 native PowerPoint
  tables, 7 static table-image pictures, 0 embedded OLE objects, and 0 native
  PowerPoint chart objects. In other words, the current review package is now
  honest: it is not pretending table-image surfaces are editable think-cell
  elements.

## Template Contract Gate

Added on 2026-05-03 after reviewing the source assets behind the warning.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-132317/manifest.json`
- `state/2026-Q2/__regional__/production_runs/20260503-132317/production_summary.md`
- `state/2026-Q2/__regional__/template_contract_gate.json`
- `state/2026-Q2/__regional__/template_contract_gate.md`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates/template_contract_gate.md`

What changed:

- `assets/LAND_template.pptx` is now the clean SimCorp shell only: 28 slides,
  0 named think-cell elements, 0 embedded OLE objects, 0 native charts, and 0
  stale think-cell ownership tokens.
- `assets/LAND_thinkcell_seed.pptx` and
  `assets/LAND_thinkcell_seed_charts.pptx` remain the native chart/text
  automation seeds. They are allowed to carry think-cell metadata because that
  is their role.
- `assets/LAND_thinkcell_table_image_donor.pptx` remains a one-slide donor for
  the Excel COM `AddRangeImage` lane.
- `assets/LAND_seed_thinkcell.pptx` is explicitly classified as a legacy
  experimental asset and must not be used as the production template.
- `scripts/build_land_template.py` now scrubs the generated shell before
  saving it as the template.
- `scripts/run_template_contract_gate.py` validates the template asset roles,
  and `scripts/run_may_regional_production_line.py` runs that gate as the first
  production step.

Result:

- Full 9-director run passed all 19 production gates, starting with
  `template_contract_gate`.
- `assets/LAND_template.pptx` and the current review-package Jesper deck both
  verify at 0 stale think-cell ownership tokens.
- This fixes the template lock issue. It does not convert the current
  meeting-spine visuals into native editable think-cell visuals; that remains
  the governed insertion-pilot/native-donor workstream.

## PowerPoint Repair Regression Fix

Added on 2026-05-03 after PowerPoint reported:
`PowerPoint found a problem with content`.

Root cause:

- The first stale think-cell scrub pruned every relationship that was not
  directly referenced by an `r:id` attribute.
- That was too aggressive. PowerPoint uses presentation-level relationships
  such as `theme`, `viewProps`, `presProps`, and `tableStyles` without direct
  `r:id` references from `presentation.xml`.
- Removing those relationships left a zip-valid deck that Python and
  LibreOffice could parse, but PowerPoint had to repair.

Fix:

- `scripts/scrub_stale_thinkcell_metadata.py` now removes only the known stale
  think-cell tag relationships and unreferenced OLE object relationships.
- It preserves normal PowerPoint support relationships even when they are not
  referenced by `r:id`.
- `scripts/run_review_package_brand_style_gate.py` now fails if any packaged
  deck is missing `theme`, `viewProps`, `presProps`, or `tableStyles` support
  parts/relationships.

Run artifacts:

- `state/2026-Q2/__regional__/production_runs/20260503-133927/manifest.json`
- `state/2026-Q2/__regional__/production_runs/20260503-133927/production_summary.md`
- `state/2026-Q2/__regional__/brand_style_gate/review_package/review_package_brand_style_gate.json`
- `/Users/test/Downloads/May 2026 Meeting Spine Candidates/Jesper-Tyrer-LAND-2026-Q2-meeting-spine.pptx`

Result:

- Full 9-director production line passed all 19 gates.
- All 9 packaged decks have 0 stale think-cell ownership tokens, 0 embedded OLE
  objects, 0 `ppt/tags` parts, and no missing PowerPoint support parts.
- The final packaged Jesper deck opened in PowerPoint without the repair
  suffix and without the think-cell carryover warning.
