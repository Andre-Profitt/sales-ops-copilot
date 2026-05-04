# LAND template rework plan — 2026-05-04

**Author:** Claude (deck-factory lane, sales-ops-copilot)
**Trigger:** Andre, 2026-05-04: "rework the template to fit this new workflow so it's actually logically sound and reusable"
**Pre-req:** 6-tool harness shipped (commits b3835c3 → a414313 on `origin/main`)
**Scope:** `assets/LAND_thinkcell_seed.pptx` only. The 9 director Excel models are untouched.

---

## 1. Mission, framed honestly

This is not a rebuild. It's a **consolidation + brand-align + verify**. The current seed renders correctly for all 9 directors today via positional binding — the rework targets are _quality_ issues (polish drift, theme defaults, orphan placeholders), not correctness blockers.

Four generations of debris have accumulated:

1. The original SimCorp template (clean)
2. `polish_pass.py` drift — added shapes, dark bars
3. `master_transplant.py` drift — Lorem ipsum from Sarah's masters
4. The Z-pass cleanup — stripped 12 Rechteck-137 blocks but missed others

Reworking blind is what got us here. **Every move from now goes through the harness gates before commit.**

---

## 2. Hard rules (from Andre's memory + this conversation)

- **Preserve template originals on slide 1 + slide 16/closing.** SimCorp template is the official brand pattern. No custom NAVY strips, no custom KPI tiles, no custom decision register on cover/closing.
- **Don't touch think-cell oleObject CFB streams.** Vendor-controlled.
- **No `--no-verify` commits, no `--force` pushes.** Every phase merges normally.
- **No comments unless WHY non-obvious.** No multi-paragraph docstrings.
- **Don't change viz types** (funnel/donut/bar/etc.) without explicit approval. Color and data only.
- **Numbers stay locked** — F-01/F-02 fixes (1000× scale errors) ride along; do not regress.

---

## 3. Risk-ordered phases — low risk first, value-fast

Each phase is a separate branch + PR. Rollback is `git checkout main`. No mega-commits.

### Phase 0 — Baseline + golden snapshot · ~15 min · Risk: zero

Lock in a known-good state we can always roll back to.

- Copy `assets/LAND_thinkcell_seed.pptx` → `assets/golden/LAND_thinkcell_seed.golden.pptx` (committed; immutable).
- Run all 6 gates on the seed, save reports under `state/template_rework/baseline/`:
  - `gate1.lint.json` (validate_pptx_strict)
  - `gate2.sdk.json` (roundtrip_pptx_openxmlsdk via run on VM)
  - `gate3.diff.json` (input vs SDK roundtrip)
  - `gate4.vision.json` (slides 1, 7, 13, 16, 22, 28 — representative sample)
  - `inventory.layouts.json`, `inventory.placeholders.json`, `inventory.runs.json`, `inventory.thinkcell.json`
- Visual smoke: render 1 director (Jesper) end-to-end via `factory.py` and eyeball the output deck. Confirms baseline still ships.

**Acceptance**: golden file committed, 8 baseline reports under `state/template_rework/baseline/`, Jesper render visually clean.

---

### Phase 1 — Brand-consistent text-color sweep · ~1h · Risk: low

The 168 inherited-color runs (25.7% of all runs) render as theme `tx1` = `#000000`. Sweep them with explicit SimCorp brand colors per rule.

**Rule book** (single source of truth, codify in script):

| Context                                      | Color                             | Rationale       |
| -------------------------------------------- | --------------------------------- | --------------- |
| Title text (sz ≥ 18 or in title placeholder) | `#083EA7` SimCorp navy            | brand primary   |
| Section header (sz 14-17)                    | `#1A1D31` near-black              | brand secondary |
| Body text (sz < 14)                          | `#1A1D31` near-black              | readability     |
| Caption / footer / page-num                  | `#666666` mid grey                | hierarchy       |
| Text on dark fill (bg luma < 0x33)           | `#FFFFFF` white                   | contrast        |
| tcfield runs (think-cell substitution)       | inherit shape parent's color rule | keep dynamic    |

**Approach**: build `scripts/template_color_sweep.py` — one-shot script, idempotent (re-runs are no-ops if colors already explicit). Operates on `<a:rPr>` elements; adds `<a:solidFill><a:srgbClr val="..."/></a:solidFill>` per the rule above. Does NOT modify shape fills, sizes, or fonts.

**Acceptance**:

- gate-1: warn count drops, 0 fails
- gate-2: parses, validation_errors unchanged from baseline
- gate-3: diff shows ONLY `+ a:solidFill` additions inside `<a:rPr>` — no element/structure changes
- gate-4: vision review on slides 1, 7, 13, 16, 22, 28 reports brand-color findings _resolved_, no new issues
- inventory_pptx_runs: `runs_without_explicit_color` drops from 168 to ≤ 5 (some intentionally inherited e.g. footer dynamic text)

---

### Phase 2 — Orphan placeholder cleanup · ~30 min · Risk: low-medium

12 chart slides carry an orphan `Title 4` placeholder not declared on `slideLayout7`. Decision: **remove** (chart slides have proper title from layout7's `Title Placeholder`, the `Title 4` is leftover from a prior polish_pass).

**Approach**: `scripts/template_remove_orphans.py` — for each slide, find `<p:sp>` with `<p:ph>` matching no layout placeholder, remove the shape. Idempotent.

**Acceptance**:

- gate-1: orphan count drops from 12 to 0
- gate-3: diff shows only `<p:sp>` removals on the 12 chart slides
- gate-4 vision: chart slides unchanged or improved hierarchy
- inventory_pptx_placeholders: orphan = 0

---

### Phase 3 — Title-slide artifact verification · ~15 min · Risk: zero (verification only)

Vision gate caught literal `<S01_DirectorName>`, `<S01_Period>`, `<S01_ScopeLabel>` on the bare seed. Two possibilities:

- **(a)** PowerPoint substitutes these tcfields at render time → seed is correct, bug is a LibreOffice rendering artifact (we use LibreOffice for vision gate). No fix needed; document it.
- **(b)** Seed has actual unsubstituted literal text `<S01_...>` (not real `<a:fld>` elements) → fix by replacing literal text with proper tcfield elements.

**Approach**: `scripts/inventory_pptx_runs.py --json assets/LAND_thinkcell_seed.pptx | jq` for slide 1 — if `source=tcfield`, it's case (a). If `source=literal`, it's case (b).

**Acceptance**: case identified, decision documented. No edit if (a). If (b), tcfield substitution restored.

---

### Phase 4 — Off-canvas brand-bar cleanup · ~30 min · Risk: low

8 slides have a 2.19in × 0.11in shape at y=7.87in on a 7.50in slide — extends 0.37in past the bottom canvas. Likely a brand bar from prior polish_pass that mismeasured the bottom anchor.

**Approach**: `scripts/template_fix_offcanvas.py` — for each shape past the bottom edge, either snap y to `slide_h - shape_h` (move inside) or delete (if it's redundant with master-level brand-bar). Decision via visual review of slide 11 (representative).

**Acceptance**:

- gate-1: off-canvas warn count drops to 0
- gate-4 vision: slides 7, 8, 9, 11, 12, 21, 24, 26 show no rendering change OR cleaner footer

---

### Phase 5 — Production verification · ~30 min · Risk: zero (read-only)

Run all 9 directors through `factory.py` with the reworked template. Visual eyeball representative slides per director (1, 7, 13, 16, 22, 28). All harness gates per director.

**Acceptance**:

- 9 of 9 directors render to clean .pptx
- gate-1, gate-2, gate-3 reports clean per director
- gate-4 vision review on Jesper, Sarah, Patrick, Megan (4 production directors) — no fail-level findings
- Diff against pre-rework golden render: only the intended changes show up

---

## 4. Deferred — for post-Monday

Reasonable engineering says skip these for the deadline.

| Item                                                                                      | Why deferred                                                                                                                                                                 | Future trigger                                                     |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| **Theme major/minor font replacement** (MS Sans Serif → SimCorp brand font, if specified) | High risk: changes every text run on every slide. Brand decision pending.                                                                                                    | Andre confirms target font; ~1h to script + verify                 |
| **Dead-layout prune** (29 of 34)                                                          | Pure hygiene; zero rendering impact today. PowerPoint-Mac may complain about relationship reshuffling.                                                                       | Post-Monday housekeeping pass                                      |
| **Lowercase `<a:fld>` GUIDs → uppercase**                                                 | Vendor-controlled (think-cell wrote them). Could break think-cell substitution at render time. Monitor for repair-pass behavior, fix only if it becomes a real ship blocker. | Excel/PPT actually does open-repair-close on the production decks  |
| **7 missing oleObject anchors** (S07/S08/S09/S11/S12/S24/S26)                             | Native_fallback PNG rendering already proven for these slides. Adding think-cell anchors needs vendor SDK calls (PowerPoint COM in interactive Session 1).                   | We want native think-cell editability for these slides post-render |
| **Visual SSIM gate**                                                                      | Vision gate (gate-4) covers the same ground at higher fidelity. SSIM catches pixel drift; vision catches semantic drift.                                                     | Quality framework needs cheap regression detection                 |

---

## 5. Sequencing for Monday EOD

```
TODAY (Sat evening)
  Phase 0: baseline + golden + smoke ............... ~15 min
  Phase 1: color sweep ............................. ~1 hour
  Phase 2: orphan cleanup .......................... ~30 min
  ↳ buffer for harness debug ....................... ~30 min

SUNDAY
  Phase 3: title-slide verification ................ ~15 min
  Phase 4: off-canvas cleanup ...................... ~30 min
  Phase 5: 9-director production verification ...... ~30 min
  ↳ buffer for fixes ............................... ~1 hour
  ↳ Andre review + approve ......................... ~variable

MONDAY
  Buffer + Andre's school-project work
  Ship by EOD
```

**Total focused work**: ~3.25 hours for phases 0-5. Buffer + verification fold in naturally.

---

## 6. Decision the plan needs from Andre

Before Phase 0 kicks off:

1. **Approve the rule book in §3 Phase 1** (title=navy, body=near-black, footer=mid-grey, on-dark=white, tcfield=inherit). Single column override OK.
2. **Confirm orphan `Title 4` removal in Phase 2** is right call (alternative: preserve as a chart-title slot — but inventory shows they're empty / leftover from polish_pass).
3. **Pick** — Phase 5 (theme font / layout prune) deferred is OK, or include for Monday?

Default-and-announce: assume yes to (1) and (2), defer (3) to post-Monday. Andre redirects with a single word.

---

## 7. What we are not doing — and why

- **Not rebuilding from scratch.** The current seed renders correctly for 9 directors today. Rebuild = 8h+ + risk; rework = 3h + verifiable.
- **Not touching the think-cell binding wiring.** That's the most fragile surface and gate-4 vision will catch any drift on the rendered side; structural validators catch the XML side. We don't touch what works.
- **Not changing fonts mid-run.** One font for headers, one for body, both already used. Brand-font swap is its own phase, deferred.
- **Not pruning dead layouts now.** Hygiene cleanup post-Monday — zero rendering value, non-zero PowerPoint-Mac relationship-reshuffle risk.
