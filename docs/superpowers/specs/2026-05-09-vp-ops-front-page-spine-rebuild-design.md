# VP Ops Front-Page Spine Rebuild (PR1) — Design Spec

**Date:** 2026-05-09
**Track:** `track:rw`
**Status:** approved (brainstorm), pending implementation plan
**Owner:** Andre
**Predecessor work:** Codex's `303bc6b` (Zebra Exceptions lab proof) + Claude's `c419313..415bc37` (Zebra BI Knowledge Graph)
**Successor work:** PR2 spec (movement waterfall + gate-violation exception column + 5 new ARR/gate measures)

## Purpose

Replace the 26-card sprawl on the live `VP Ops Scorecard` page with two structured spines + one compact KPI strip, using Zebra BI Tables grammar that Codex already proved renders against the live RW semantic model.

PR1 ships the **exception spine** (stalled-deal grammar) and the **KPI strip**. Both are bindable to existing measures — no new DAX. PR2 will add the **movement spine** (waterfall over 4 new ARR-7d measures) and a **gate-violation column** (1 new measure that joins to `Stage_20_Approval__c`).

## Scope

**In scope (PR1):**

- Rewrite `scripts/sales/rw_compose_scorecard_home.py:PAGE = "VP Ops Scorecard"` around three sections (`_build_exception_spine`, `_build_movement_spine_placeholder`, `_build_kpi_strip`)
- Lab-first deploy: apply to `~/Downloads/rw-pbi-format-lab/rpt_vp_ops_scorecard_zebra_lab_20260509_pbip/` first, render-verify in Power BI Desktop, then promote to live Fabric workspace `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
- Delete the existing 26 KPI/RAG card builders that the current `rw_compose_scorecard_home.py` instantiates (no deprecation, no half-states)
- Use existing measures only — bindings are validated by `data/zebra_kg_rw/bindings.jsonl` (33/33 bound)
- Update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` with the rebuild's render proof + screenshot evidence

**Out of scope (deferred to PR2):**

- Movement waterfall — needs 4 new ARR-7d measures (`New Opps ARR 7d`, `Closed Won ARR 7d`, `Closed Lost ARR 7d`, `Backward Moves ARR 7d`) + start/end period boundaries
- Gate-violation exception column — needs 1 new measure `Commercial Approval Gate Exception ARR` that joins f_opportunity to the SF `Stage_20_Approval__c` field
- Margin review / KYC gate exceptions — sfkg shows zero SF coverage for these, so we'd be authoring measures with no underlying data; defer until SF closes that gap
- Re-styling of `What Changed`, `Forecast`, or any other tab — only `VP Ops Scorecard` page in this PR

## Non-goals

- Custom-visual color tuning — Zebra's defaults are good enough, and the spec's prior brainstorm rule applies (no theme remap, no NAVY substitution)
- Tracker/comments layer — the dynamic-comments template grammar is a v3 enhancement, not v1
- Workforce or other project overlays — PR1 is RW VP Ops only

## Background — what each finding tells us

**The Zebra Tables proof already works.** Codex's `303bc6b` lab proof renders Zebra BI Tables against the live RW semantic model with `d_region[region]` × `Exception ARR / Exception Opps Count / At Risk Opps ARR / Watch Opps ARR`. The Zebra license activated 2026-05-09 (trial expires 2026-06-08). The harness fix in `_pbir_helpers.py` (group projections under `Primary` instead of native-table-style `Primary` / `Secondary` split) is the binding pattern this spec lifts.

**`Exception ARR` semantics — internally consistent, but distinct from the brief.** The deployed RW DAX defines exceptions as **stage-age** (Watch = stages 3–4 stalled >14d; At Risk = stages 5–7 stalled >21d, both Land+Expand only). The morning-brief alert "Stage 3+ ≥$500k no Commercial Approval" defines exceptions as **gate violations** against `Stage_20_Approval__c`. Two non-overlapping lists. PR1 surfaces stage-age exceptions (which is what the existing measure carries); PR2 adds the gate-violation column so dashboard and alerts share grammar.

**LAND / EXPAND / Renewal split — already honored at the measure layer.** Both stage-age measures filter `motion_type IN { "Land", "Expand" }`. The cardinal rule (`APTS_Opportunity_ARR__c` for Land+Expand vs `APTS_Renewal_ACV__c` for Renewals; never blend) is preserved. PR1 inherits this; the spine does not introduce any cross-motion measure on the front page.

**sfkg gate coverage — Commercial Approval is well-instrumented in SF (257 reports, 28 dashboards), Margin and KYC are not.** This sets PR2's measure-authoring boundary: only the Commercial Approval gate has the underlying SF field coverage to author a meaningful Fabric measure against.

## Architecture

### Page layout (1280×720)

```
+─────────────────────────────────────────────────────────────────────────+
| Page title row (textbox)                                                |
| ──────────────────────────────────────────────────────────────────────  |
| EXCEPTION SPINE                                                         |
|   Zebra BI Tables: d_region[region]                                     |
|   × Exception ARR | At Risk Opps ARR | Watch Opps ARR | Exception Opps  |
|     Count                                                               |
|   Height: ~280 px                                                       |
| ──────────────────────────────────────────────────────────────────────  |
| MOVEMENT SPINE PLACEHOLDER                                              |
|   Empty rectangle with textbox: "Movement spine — see PR2"              |
|   Height: ~240 px                                                       |
| ──────────────────────────────────────────────────────────────────────  |
| KPI STRIP                                                               |
|   Zebra BI Cards row (or 4 native cards as fallback)                    |
|   × Total Closed Won ARR | Win Rate ARR | Stage Forward Pct (LE)        |
|     | Renewal Retention Pct (Period)                                    |
|   Height: ~140 px                                                       |
+─────────────────────────────────────────────────────────────────────────+
```

The placeholder section is intentional — it preserves vertical real-estate for PR2's waterfall and signals to the executive viewer that "what changed" is coming, rather than the rebuild looking permanently incomplete.

### Why these three sections

- **Exception spine first** — executives scan top-to-bottom; the highest-decision signal goes first. Stalled deals at high ARR are the immediate "act today" list.
- **Movement spine middle** (placeholder in PR1) — the "why is the pipeline at $X today" answer; a waterfall is the canonical Zebra grammar for this question.
- **KPI strip last** — context floor. Single-row glance KPIs that anchor the viewer in win-rate / retention / stage-progression health. Compact = no card-wall regression.

### Files modified

| File                                            | Change                                                                                                                                                            |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `scripts/sales/rw_compose_scorecard_home.py`    | Rewritten around 3 builders. Existing 26-card builders deleted. Existing `PAGE = "VP Ops Scorecard"` constant retained.                                           |
| `tests/sales/test_rw_compose_scorecard_home.py` | New tests for each builder; existing tests updated or deleted to match the new layout.                                                                            |
| `scripts/sales/rw_apply_zebra_lab_proof.py`     | Extended (or sibling script added) to apply the _full_ three-section layout to the lab PBIP, not just the single Zebra Exceptions visual that `303bc6b` produced. |
| `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`        | Append a "Front-page spine rebuild — PR1" section with render-proof screenshot path.                                                                              |

### Components

#### `_build_exception_spine(spec_table_id) -> dict`

Returns one PBIR `visualContainer` for a Zebra BI Tables visual. Lifts the binding pattern verbatim from `rw_apply_zebra_lab_proof.py`'s Zebra Exceptions visual (Codex `303bc6b`):

- visual type: `Zebra-BI-Tables` (custom visual GUID per `_pbir_helpers.py`)
- projection role: `Primary` (category + values combined under one role per the lab fix)
- bindings:
  - Category: `d_region[region]`
  - Values (in this order): `Exception ARR`, `At Risk Opps ARR`, `Watch Opps ARR`, `Exception Opps Count`
- position: x=0, y=64, w=1280, h=280
- formatting: Zebra's default IBCS palette (no theme override)

#### `_build_movement_spine_placeholder() -> dict`

Returns a single textbox visualContainer with the text "Movement spine — see PR2 (`Pipeline ARR last 7d` waterfall, pending new ARR-7d measures)". Position x=0, y=360, w=1280, h=240. Background light grey to read as "wireframe placeholder" not "empty space."

#### `_build_kpi_strip() -> list[dict]`

Returns 4 visualContainers, each a Zebra BI Card (or — fallback — a native `kpiVisual`):

| KPI               | Measure                          | Rationale                                                                                                                          |
| ----------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Closed Won FQTD   | `Total Closed Won ARR`           | Quarter-to-date wins, ARR — primary outcome KPI                                                                                    |
| Win Rate          | `Win Rate ARR`                   | Conversion health, ARR-weighted                                                                                                    |
| Stage Hygiene     | `Stage Forward Pct (LE)`         | Process governance — % stages moving forward (LE = leading edge)                                                                   |
| Renewal Retention | `Renewal Retention Pct (Period)` | Renewal health, ACV side. (Cross-motion KPI is OK on a _summary_ card row; the rule is no blending in compute, not no co-display.) |

Each card has: title, current value with format string from the measure's TMDL, sparkline over last 4 quarters, embedded variance arrow vs. PY. Cards are positioned: x=0/320/640/960, y=600, w=320, h=120.

### Data flow

```
rw_compose_scorecard_home.py (composer)
    │
    ├─ _build_exception_spine() ─► PBIR visualContainer (Zebra Tables)
    ├─ _build_movement_spine_placeholder() ─► PBIR visualContainer (textbox)
    └─ _build_kpi_strip() ─► 4 PBIR visualContainers (Zebra Cards / native KPIs)
        │
        └─► assembled into the "VP Ops Scorecard" section's visualContainers list

Lab apply:
    rw_apply_zebra_lab_proof.py --target lab_pbip
        ─► writes the new visualContainers into rpt_vp_ops_scorecard.Report/report.json
        ─► preserves Zebra license blob (existing behavior)
        ─► Power BI Desktop opens the lab → render proof → screenshot

Live promote:
    rw_push_report.py --workspace b66233d5-9d4a-44ba-89a8-b70206d98ae7 \
                      --report rpt_vp_ops_scorecard
        ─► uses same composer output, posts to Fabric REST
        ─► uses azure-identity/AzureCliCredential (existing auth path)
```

### Card deletion list (the 26 that go away)

The existing `rw_compose_scorecard_home.py` instantiates a card wall. Per the brainstorm rule "Don't keep the card wall and just swap visual types," PR1 deletes (not deprecates) the 26 builders. The exact list belongs in the implementation plan; the spec just commits to the policy.

## Error handling

- **Lab apply errors** — if the Zebra license blob is missing in the lab PBIP, `rw_apply_zebra_lab_proof.py` already logs a warning and proceeds. Reuse that pattern. Don't fail the apply just because license validation deferred to first Desktop open.
- **Live push errors** — Fabric REST throws on schema drift (e.g., a referenced measure that's been renamed). The composer must validate every measure name it emits against `fetch_measures_by_table()` output before pushing. If a measure is missing, FAIL FAST with a clear error pointing at the missing measure name.
- **Render-proof gate** — the spec REQUIRES a Desktop screenshot of the lab PBIP rendering before the live push runs. No "shipped, will verify later" — the lab proof is the precondition for live promote.

## Testing

- `tests/sales/test_rw_compose_scorecard_home.py`:
  - `test_compose_emits_three_top_level_sections` — verifies the assembled section has exactly: 1 exception Zebra Table + 1 placeholder textbox + 4 KPI cards (= 6 visualContainers + page title textbox = 7 total). NOT 26.
  - `test_exception_spine_binds_existing_measures` — every measure name in the spine's value projections appears in `fetch_measures_by_table()`'s output.
  - `test_kpi_strip_binds_existing_measures` — same check for the strip.
  - `test_movement_placeholder_is_textbox_not_zebra` — confirms PR1 doesn't accidentally ship a half-built waterfall.
  - `test_no_card_wall_residue` — assert that none of the deleted 26-card builder names are still present in the composer module.

- Render proof — manual, but documented in `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` per the lab-first protocol.

- Pre-commit secret scan — match the existing pattern from Codex's `303bc6b`: scan `scripts/sales/`, `tests/sales/`, `docs/sales/` for the Zebra trial token substring before commit.

## Deployment sequence

1. Implementation plan (next) — TDD, bite-sized.
2. Land all changes on `feat/track-rw-tooling` (continues the existing track:rw branch).
3. Apply to lab PBIP (`rw_apply_zebra_lab_proof.py` extended for the three-section layout).
4. Open lab in Power BI Desktop on the Parallels VM (32 GB / 8 CPU, just resized). Verify render. Capture screenshot to `~/.frontier/artifacts/rw_vpops_spine_rebuild_<date>.png`.
5. Update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`.
6. Run full `pytest tests/sales/`.
7. Push to remote — Codex reviews at branch level.
8. After Codex review: promote to live Fabric (`rw_push_report.py`).
9. Smoke-check live workspace; confirm no Renewal ACV blending in the rendered cards (visual confirmation of the cardinal rule).

## Open questions deferred to plan

- Whether the KPI strip uses Zebra BI Cards (custom visual, license-bound) or native `kpiVisual` (no license dependency, simpler render). Recommendation: Zebra Cards for consistency with the spine; native fallback if Cards have a binding quirk we hit during the lab apply. Decide post-lab.
- Whether `rw_apply_zebra_lab_proof.py` is extended in-place or a sibling script `rw_apply_spine_rebuild.py` is added. Decide based on the diff size during implementation.

## Risk register

| Risk                                                                            | Likelihood | Mitigation                                                                                                                               |
| ------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Zebra Cards binding quirk (only Tables proved so far)                           | Medium     | Lab-first protocol catches this; native fallback documented as a switch                                                                  |
| Existing front-page consumers break (other reports referencing this page name?) | Low        | Page name unchanged (`VP Ops Scorecard`); only inner visualContainer set is rewritten                                                    |
| Trial license expiry mid-build                                                  | Low        | 30-day window (expires 2026-06-08); PR1 + PR2 both fit comfortably                                                                       |
| Cardinal rule violation (Renewal ACV blended into ARR)                          | Low        | All four spine + strip measures already isolate Land+Expand or Renewal cleanly; verified by reading deployed DAX                         |
| Codex and Claude touching the composer in parallel                              | Medium     | Coordinate via PR review on branch tip (push frequency is the signal); spec is committed before code so there's a single source of truth |

## Out-of-scope reminders

- No DAX authoring in PR1.
- No Workforce / Forecast / What Changed tab edits — VP Ops Scorecard page only.
- No theme JSON changes — the existing theme is the brand pattern per memory.
- No PBIX export attempts — `getDefinition` is the only push path that works against the tenant; no Desktop-export fallback.
