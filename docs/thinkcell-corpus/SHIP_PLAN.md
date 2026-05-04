# SHIP_PLAN — LAND deck factory

**Status doc for the actual deliverable.** Single canonical plan. Read alongside `MASTER_STATE.md` (which is the broader research / intel tracker).

Last updated: 2026-05-03.

---

## Goal

Programmatically generate **9 director-specific LAND review decks** (SD-monthly cadence) from Salesforce-derived data. One populated `.pptx` per director, on demand, headless, deterministic. Personal-automation use, single-user license.

## Pipeline (canonical)

```
Salesforce (per director)
   ↓ existing builders
state/2026-Q2/<Director>/land.model.xlsx          # Pivots sheet = Source-of-truth numbers
   ↓ scripts/build_ppttc.py
state/2026-Q2/<Director>/<Director>-LAND-2026-Q2.ppttc   # 42 named bindings per director
   ↓ scripts/build_ppttc_demo.py + libs/tcrender
   (Mac-side: scp .ppttc + template -> VM tempdir)
   (VM-side:  ppttc.exe demo.ppttc -o output.pptx)
   (Mac-side: scp <- output.pptx to _windows_test/)
state/2026-Q2/<Director>/decks/<Director>-LAND-2026-Q2-<ts>.pptx   (target output)
```

**Per-director cadence**: ~3.5 seconds. **9 directors**: ~30 seconds total Mac-side.

## Production routes (disambiguated)

| Lib                  | Role                                                                  | When to use                                                                                                 |
| -------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `libs/tcrender`      | **Production** — Mac-side wrapper around `ppttc.exe` over SSH         | The factory pipeline. Default route.                                                                        |
| `libs/tc_com_driver` | Utility / research — pywin32 wrapper around 25 think-cell COM methods | Bespoke `UpdateBatch.AddRangeData` flows, interactive PowerPoint sessions, COM probes. NOT for bulk render. |
| `libs/tcxml`         | Format introspection — read/write think-cellXML CFB streams           | Inspecting / mutating chart format details. Diagnostic and research.                                        |

## Current readiness — by component (2026-05-03)

| Component                                     | State                                                                                        | Owner                                                                                                   |
| --------------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| SF -> land.model.xlsx                         | ✅ existing                                                                                  | Andre (rerun on data refresh)                                                                           |
| land.model.xlsx -> .ppttc                     | ✅ working, 42 bindings/director, **F-01/F-02 critical numeric bugs fixed 2026-05-03**       | `scripts/build_ppttc.py`                                                                                |
| .ppttc -> bound .pptx                         | ✅ 3-7 second render                                                                         | `libs/tcrender`                                                                                         |
| Mac<->VM bridge                               | ✅ deterministic, scp+ssh                                                                    | `tcrender.SSHTransport`                                                                                 |
| Director scoping                              | ✅ verified (32/42 bindings differ Jesper vs Sarah)                                          | n/a                                                                                                     |
| **Template <-> binding wiring**               | 🟡 **21/32 wired** in `assets/LAND_thinkcell_seed.pptx`; 11 chart anchors still missing      | **Andre (interactive on VM)** — see `TEMPLATE_WIRING_CHECKLIST.md`                                      |
| Default template path in build_ppttc.py       | 🟡 still points at empty `assets/LAND_template.pptx`; should switch to `LAND_thinkcell_seed` | minor — `--template` override works                                                                     |
| **Jinja pre-pass for `{director_name}` etc.** | ✅ shipped — `tcrender.template_prep`; slide 1 now resolves "Jesper Tyrer / 2026-Q2 / APAC"  | done                                                                                                    |
| **Output verification harness**               | ✅ shipped — `tcrender.verify`; gates render with binding-evidence match-ratio               | done                                                                                                    |
| `build_ppttc.py` test coverage                | ✅ 24-test suite + `_validate_ppttc_shape` validator; **2 critical bugs found + fixed**      | done — F-01/F-02 inline-fixed; 13 other findings tracked at `state/thinkcell_bridge/build_ppttc_audit/` |
| Production-route disambiguation               | ✅ CLAUDE.mds updated                                                                        | done                                                                                                    |
| Output archival                               | 🟡 in-progress (Tier 3 subagent: `archive.py` + state/<period>/<dir>/decks/<ts>/)            | code subagent                                                                                           |
| Quality gate (verify + jinja-leak + brand)    | 🟡 in-progress (Tier 3 subagent: `quality.py`)                                               | code subagent                                                                                           |
| Monthly diff tooling                          | 🟡 in-progress (Tier 3 subagent: `scripts/diff_director_decks.py`)                           | code subagent                                                                                           |
| 9-director factory CLI                        | 🟡 in-progress (Tier 3 subagent: `scripts/factory.py`)                                       | code subagent                                                                                           |
| Distribution (Teams / SharePoint)             | ❌ not started                                                                               | deferred to Tier 3.5                                                                                    |

## Critical path (in order)

The pipeline is currently a Ferrari engine wired to a steering wheel that isn't connected to the wheels. Fix the connection:

1. **Jinja pre-pass** (in flight) — substitute `{director_name}` / `{period}` / `{scope_label}` placeholders in the template before ppttc.exe sees it. Pure code. Ships director name + period + scope on cover slide today.

2. **Output verification harness** (in flight) — fail loud if rendered .pptx is missing director-specific content. No more silent-fail "exit 0 on empty deck."

3. **Template wiring** (interactive — Andre) — open `assets/LAND_template.pptx` in PowerPoint on the VM, set `AddRangeData Name` via mini-toolbar on each text field that should receive a binding, add think-cell chart anchors for chart slides. **This is the gating step**. See `TEMPLATE_WIRING_CHECKLIST.md`.

4. **build_ppttc.py audit** (in flight) — surface hidden brittleness in the 30+ entry functions. Add basic regression tests + ppttc-schema validation.

5. **Re-run all 9 directors** after #1-#3 are done. Verify each output contains director-specific evidence strings via the verify harness.

6. **Archival + diff** (deferred) — output decks land in `state/2026-Q2/<Director>/decks/<ts>/`. Build a diff tool that compares this month's deck to last month's per director.

## Acceptance criteria for "first ship"

- [ ] Run `build_ppttc_demo.py --ppttc <jesper> --template-override <wired template>` produces a .pptx where:
  - [ ] Slide 1 cover shows "Jesper Tyrer / 2026-Q2 / APAC" (no `{director_name}` literals)
  - [ ] At least 3 chart slides display real chart data (not empty placeholders)
  - [ ] `verify_render` returns `passed=True` with `match_ratio >= 0.7`
- [ ] All 4 currently-built directors render without exception
- [ ] No silent-fail: pipeline raises if rendered output is missing director-specific content
- [ ] `pytest libs/tcrender/tests/ scripts/test_build_ppttc.py -x -q` passes

## Non-goals (explicit)

- ❌ Per-chart 1-line takeaways (the OTHER session's track). Defer until first ship is real.
- ❌ tc.ai integration. The factory doesn't need it; .ppttc is sufficient.
- ❌ More chart-format research (Phase 12 capture, Ghidra labeling). Foundation work, not blocking.
- ❌ Adding directors / quarters until 1-of-9 ships cleanly with real content.
- ❌ Refactoring `build_ppttc.py` entry functions. Surgical guards only.

## Risks

1. **Template wiring is manual + interactive.** Can't be automated. Andre's bandwidth gates progress. ~2-4 hours of PowerPoint mini-toolbar work.
2. **Hidden data quality issues** in build_ppttc.py — the OTHER session traced 1 of 42 bindings. We don't know what's brittle in the other 41.
3. **Multiple route confusion** — if anyone uses `tc_com_driver` for bulk render, drift starts. Mitigated by CLAUDE.md updates (just landed).
4. **No alerting on stale data** — if SF query fails or land.model.xlsx is stale, pipeline runs cleanly with old numbers. Mitigated only weakly by output verification (which checks structure, not staleness).

## Decisions log

| Date       | Decision                                                          | Rationale                                                                                                                                                                                                                                                                                         |
| ---------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-05-03 | `tcrender` is production; `tc_com_driver` is utility              | Two routes for the same job creates drift. ppttc.exe is documented + headless + 3s.                                                                                                                                                                                                               |
| 2026-05-03 | Defer per-chart takeaways                                         | Polishing language on a deck with no real content was the OTHER session's wrong path. Get content rendering first.                                                                                                                                                                                |
| 2026-05-03 | Template wiring is interactive (Andre's)                          | Mini-toolbar on chart anchors / text fields can't be set programmatically. Documented in `TEMPLATE_WIRING_CHECKLIST.md`.                                                                                                                                                                          |
| 2026-05-03 | F-01/F-02 critical numeric bugs fixed inline                      | `_eur_millions_for_k_scaled_donor` divided by 1_000 (gave kEUR labeled mEUR — 1000× wrong); `_for_k_scaled_donor` multiplied by 1_000 (gave 11600 for 11.6%); `_velocity_chart_entry` multiplied days by 1_000. Audit-found, fixed same-day. Affected 5 of 42 bindings (S18, S19, S21Chart, S25). |
| 2026-05-03 | Switch wired template to `assets/LAND_thinkcell_seed.pptx`        | Template audit found 21/32 bindings already wired in this file (12 charts, 308 tags); the empty `LAND_template.pptx` was being used by mistake. Re-rendered all 4 directors against the wired template — "Jesper Tyrer" + EUR values + 13 oleObject charts now appear.                            |
| 2026-05-03 | Tier 3 (production essentials) is the last code track before ship | Archival, monthly diff, quality gate, factory CLI. After Tier 3 + Andre's Tier 2 visual polish, v1 ships.                                                                                                                                                                                         |

---

## How to extend this plan

1. After each subagent reports, mark the row in "Current readiness" green.
2. After Andre completes template wiring, mark that row green and run all 9 directors.
3. Append decisions to the log with date + rationale.
4. When ALL acceptance criteria check, archive this doc as `SHIP_PLAN_2026-Q2_DONE.md` and start a new one for next quarter's improvements.
