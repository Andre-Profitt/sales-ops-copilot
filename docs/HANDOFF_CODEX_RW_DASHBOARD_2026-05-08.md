# Handoff to Codex — RW VP Ops Dashboard visual polish

**Andre's frame:** "Whatever Claude did sucks lol." The data layer is solid. The visual layer is mediocre. Pick this up.

**Owner you're working for:** Andre (apro@simcorp.com). End consumer: Richard Wyeth, MD Sales Operations. The dashboard is `rpt_vp_ops_scorecard` in workspace `Salesforce Analytics - Sales Manager`.

---

## TL;DR

A consulting-grade design contract exists in `.superpowers/brainstorm/95130-1778258028/content/*.html` (open them in a browser). The deployed Power BI report has the right data + structure but visually still looks like "a bunch of numbers all over." Claude Code couldn't bridge the gap between HTML/CSS-mockup polish and what PBIR-Legacy + Fabric REST + macOS-arm64 can actually render. Three paths forward — see § Decisions needed. Pick one, execute.

---

## State of play (live, verified 2026-05-08 evening)

**Branches (both pushed):**

- `feat/track-rw-dashboard-foundation` → PR #1: <https://github.com/Andre-Profitt/sales-ops-copilot/pull/1> — 13 commits — foundation (5 PBIR builders + 5 redesign tabs + 43 net-new DAX measures)
- `feat/track-rw-tooling` → PR #2 stacked on #1: <https://github.com/Andre-Profitt/sales-ops-copilot/pull/2> — ~12 commits — validator + visual-schema KG + DAX verification recipes + capture CLI + composers for `What Changed` and `Forecast` tabs + first-pass theme + compact $ formatting

**Worktree:** `~/code/apps/sales-ops-copilot-rw/` (currently on `feat/track-rw-tooling`).

**Live Fabric:**

- Workspace: `b66233d5-9d4a-44ba-89a8-b70206d98ae7` (F64)
- Semantic model `sm_sales_kpis_rw` (`3c58b5dd-b321-4aaa-a5cd-fb73e474edbb`): **100 measures** across `f_opportunity` (59), `f_stage_transition` (36), `f_forecast_transition` (5)
- Report `rpt_vp_ops_scorecard` (`d7362a11-f3dd-4bd1-a69a-68c941c2598b`): **47 visualContainers** across 6 sections
  - `VP Ops Scorecard` — 26 visuals (FY26 page filter)
  - `What Changed` — 12 visuals
  - `Forecast` — 9 visuals
  - `Stage Hygiene` / `Renewals` / `Growth Mix` — empty
- Custom theme `RW SimCorp Consulting` is in the metadata but its visual effect is small (Power BI silently drops most properties at render time)

**Tests:** 19/19 pytest pass (`tests/sales/`).

---

## What's correct — don't redo

- **Data fidelity:** every Measure ref in every visualContainer resolves cleanly against the deployed model. `python3 -m scripts.sales.rw_validate --live` reports zero errors. Don't second-guess measures.
- **Cardinal SimCorp business rules:** ARR (Land+Expand) → `arr_org_ccy`. ACV (Renewal) → `acv_org_ccy`. Never blend. The model enforces this. The one exception is `Total Open Pipeline Value` which is explicitly cross-motion (SWITCH on motion_type) and labeled accordingly — use ONLY for cross-motion comparison visuals.
- **Schema deltas vs. plan drafts** (worth knowing because the original spec drafts had several wrong):
  - `f_stage_transition[direction]` is `"forward"`/`"backward"` (string), NOT `1`/`-1`
  - `transition_at` (NOT `transition_date`)
  - `days_in_prior_stage` (NOT `days_in_from_stage`)
  - `f_opportunity` has NO `stage_num` column — stage filters use `stage_name IN {...}` against verified `OpportunityStage` names
  - `last_stage_change_date` already on `f_opportunity`

---

## What's wrong (Andre's complaint, accurately)

The visual finish doesn't match the design contract. The brainstorm mockups specify:

- RAG-tinted card backgrounds (At Risk on `#fee` w/ `#c33` accent border, Watch on `#fff8e6`/`#d80`, Healthy on `#eef9ee`/`#393`)
- Section header textboxes (`RISK BAND` / `CHANGE BUCKETS` / `DETAIL` in 10px uppercase muted)
- Cards with primary 28-32px number + secondary 11px gray line, NOT stacked count+ARR pairs
- Inline RAG colors on table cells for threshold-crossable columns
- Compact `$` formatting (`$2.5M` not `$2,547,381`) — partially shipped via measure formatString change

Power BI from the Fabric REST API on macOS-arm64 **silently rejects** most of the per-visual `objects` configuration that would deliver these. Theme JSON gets accepted at API level but the renderer drops fields it doesn't recognize. Without a Windows PBI Desktop to validate against, every guess is a 30-minute deploy-and-eyeball cycle.

---

## Why this is hard from this Mac

| Constraint                                                               | Effect                                                                                                                     |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Tenant has `executeQueries` REST disabled (`PowerBIFeatureDisabled`)     | No programmatic DAX eval; only path is eyeballing live cards or running a Fabric notebook                                  |
| sempy desktop is broken on macOS arm64 (Linux x86_64 .NET assembly)      | `pip install semantic-link` works but `evaluate_dax` raises `FileLoadException`. `dotnet@8` install does NOT fix it.       |
| No PBI Desktop on macOS                                                  | Can't visually author + validate themes / objects shapes; can't use the schema validator that catches malformed properties |
| Fabric reorders `report.json.sections` alphabetically post-push          | Any positional `sections[0]` access breaks. All scripts now look up by `displayName`.                                      |
| PBIR `singleVisual.objects` schema is undocumented at the property level | Hand-rolling color/font/padding for cards is guess-and-check                                                               |

These are recorded in:

- `~/.claude/projects/-Users-test/memory/feedback_fabric_section_reorder_2026-05-08.md`
- `~/.claude/projects/-Users-test/memory/feedback_sempy_desktop_macos_arm64_2026-05-08.md`
- `~/.claude/projects/-Users-test/memory/feedback_sf_pgv_rest_api_blocked_2026-04-29.md`

---

## Files to read first

In priority order — **read these before editing anything**:

1. `.superpowers/brainstorm/95130-1778258028/content/*.html` (6 files) — **the visual contract**. Open in a browser.
2. `docs/sales/RW_VISUAL_DESIGN_SPEC.md` — distilled tokens from the mockups (RAG palette, neutrals, typography, card/table patterns)
3. `docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md` — structural redesign spec (4 tabs, layout standards)
4. `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` — running build journal; ends with What Changed + Forecast composition notes
5. `docs/sales/RW_DAX_VERIFICATION.md` — recipes for measure verification (REST disabled; use probe-card spot-check or Fabric notebook)
6. `themes/rw_simcorp_consulting.json` — first-pass theme; partially honored
7. `scripts/sales/_pbir_helpers.py` — the only place visualContainer JSON is constructed. 5 builders + page management + objects-aware card variant.
8. `scripts/sales/_pbir_shapes.py` — visual-schema KG. SHAPES has 4 entries. PENDING list catalogs ~17 unverified PBI visualTypes (waterfall, gauge, kpi, multiRowCard, textbox, etc.)
9. `scripts/sales/rw_compose_what_changed.py` and `rw_compose_forecast.py` — current composer scripts
10. `scripts/sales/rw_capture_visual.py` — list/extract live visuals; the CLI for the "browser-author + capture" loop

Memory entries that bear on this work:

- `project_rw_dashboard_progress_2026-05-08.md` — current session state
- `project_rw_design_contract_2026-05-08.md` — the brainstorm-mockups-as-design-contract finding
- `feedback_simcorp_arr_acv_separation.md` — never blend ARR/ACV
- `project_simcorp_funnel_skip_2026-05-06.md` — ~70% close-wons skip Stage 4 (relevant for Tab 3 caveats)

---

## The three paths Andre is weighing

### Path A — Windows + PBI Desktop (recommended by Claude)

Andre opens `rpt_vp_ops_scorecard` in PBI Desktop on Windows, formats one card the way it should look (RAG background, 28pt number, 11px secondary line, 10px uppercase label), saves the report. You then:

1. Pull report.json via Fabric REST `getDefinition`
2. Find the formatted card via `rw_capture_visual --extract`
3. Capture its `singleVisual.objects` block into `_pbir_shapes.py`
4. Generalize into a `build_kpi_card` builder in `_pbir_helpers.py`
5. Re-compose all 47 visuals using the new builder
6. Push back

This is the highest-leverage path because the captured shape is renderer-validated by definition.

**Risk:** depends on Andre having Windows access. If not, this path is closed.

### Path B — Pivot deliverable to Streamlit / HTML

Build a Streamlit app or static HTML report that pulls from the same Fabric Lakehouse + Salesforce data and renders the brainstorm-mockup-fidelity layout in actual HTML/CSS. Host on Tailscale or push to SharePoint as a refreshed snapshot.

**Pros:** the look is achievable because it's literally HTML/CSS. Brainstorm mockups become production-ready in hours.

**Cons:** not Richard's expected medium. He wants a Power BI report he can open from Fabric.

### Path C — Stop chasing the mockup; ship the cleanest possible PBI dashboard

Accept PBI's native rendering. Use only the formatting controls that demonstrably work via REST. Drop the RAG-tinted cards / section textboxes / count+ARR consolidation as out-of-reach. Polish what's polishable: spacing, alignment, table column widths, format strings, slicer placement.

Output looks like a competent PBI dashboard, not a McKinsey-grade exec scorecard.

---

## Concrete asks for Codex

Pick one:

1. **Argue for a different path I haven't listed.** You may see something Claude missed.
2. **Execute Path A** if Andre has Windows access — you'd be writing the prompt for a Windows session, then resuming after capture is done.
3. **Execute Path B** — scaffold the Streamlit app under `~/code/apps/sales-ops-copilot-rw/dashboard_streamlit/` consuming the same Lakehouse data.
4. **Execute Path C** — enumerate exactly what's polishable from REST and ship those without overpromising.
5. **Code-review the existing branches.** Flag mistakes in DAX / measure logic / schema assumptions / memory-vs-reality drift. The `rw_validate.py` only checks measure-ref existence; it doesn't check semantic correctness.

Whichever you pick: **commit small, push frequently, and update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md`** with what you did + what's deferred.

---

## Cardinal rules to inherit

(These are in `~/.codex/AGENTS.md` already, restating for safety.)

- ARR (Land+Expand) and ACV (Renewal) NEVER blend. The model has separate measures. Use `Total Open Pipeline Value` only for cross-motion comparison visuals (it's a SWITCH on motion_type).
- Don't trust positional `sections[0]` — always look up by displayName (Fabric reorders).
- Don't waste time on `pip install sempy` for desktop DAX eval; it's broken on macOS arm64. Use the Fabric notebook recipe in `RW_DAX_VERIFICATION.md` or stick with probe-card.
- `executeQueries` REST is tenant-disabled. Don't retry it.
- Pre-flight every `report.json` push with `validate_visual_dict` from `rw_validate.py`. Catches measure typos before LRO.

---

## Auth setup you'll need

- `az account show` should report `APRO@simcorp.com`. If not, `az login`.
- Fabric REST tokens come from `AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default")`.
- `sf` CLI is auth'd as `apro@simcorp.com` against preprod org. `sf data query` works.

---

## Worktree hygiene

The repo has parallel tracks. **You're on `track:rw`**. Don't touch:

- `scripts/workforce/` (track:workforce) — uncommitted changes there are someone else's WIP
- `~/crm-analytics/` (paused 2026-04-28 per memory)
- The LAND deck factory work on `feat/land-review-factory-rebuild`

`docs/AGENT_COORDINATION.md` is the source of truth for track boundaries.

---

## When you're done

1. Update `docs/sales/RW_VPOPS_DASHBOARD_BUILD.md` with a 2026-05-XX section
2. Add a memory entry at `~/.claude/projects/-Users-test/memory/project_rw_<topic>_2026-05-XX.md` and index in `MEMORY.md`
3. Open a third PR stacked on #2, OR layer commits onto `feat/track-rw-tooling` if scope is small
4. Tell Andre what to eyeball before you mark it complete
