# Sales Director Deck Factory Durable Plan

This plan converts the May 2026 sprint into a repeatable monthly reporting
factory. The goal is not another one-off APAC rescue; the goal is a controlled
Salesforce -> Excel -> think-cell/PowerPoint -> SharePoint production system
that can run every month with proof artifacts.

## Current Baseline

- May 2026 / `2026-Q2` is the only certified production lane.
- Latest green integrated run:
  `state/2026-Q2/__regional__/production_runs/20260503-133927/manifest.json`.
- Current production command:
  `.venv/bin/python scripts/run_regional_production_line.py --period 2026-Q2 --jobs 4`.
- SharePoint validation is live and green: 37 expected assets, no stale files,
  no missing files, no size mismatches.
- The production line now starts with `template_contract_gate`, which enforces
  that `assets/LAND_template.pptx` is a clean SimCorp shell and that think-cell
  metadata only lives in explicit seed/donor assets.
- The review-package brand gate now also blocks missing PowerPoint support
  parts/relationships (`theme`, `viewProps`, `presProps`, `tableStyles`), so a
  zip-valid deck that would still trigger PowerPoint repair cannot pass.
- Table/action visuals are Excel-driven linked table images. They are
  traceable and production-useful, but they are not native editable think-cell
  tables.
- think-cell corpus scaffold now has build levels `L0` through `L5`, 12 quarter
  seed contracts, and a graph/RAG corpus of stock template evidence.
- Proof phase is closed. All 12 quarter visual contracts are L5-proven
  (`l5_proven/pass`) as of 2026-05-01, and all 12 sit on the protect-lane
  rotation queue (re-asserted on each rebuild, not re-authored). Source:
  `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
  and the 12 `state/thinkcell_bridge/build_scaffold/2026-Q2/work/<contract>/<contract>-proof.json`
  artifacts. The next operating mode is production-polish insertion pilots, not
  more proof chasing.

## What Caused Drift

1. Delivery and platform engineering were mixed in the same loop. We built
   slides, fixed data truth, investigated think-cell, and published SharePoint
   assets without a stable work queue.
2. Scripts grew around incidents. Some names still say `may`, while the
   orchestrator is becoming period-aware.
3. Deck quality was validated late. Text, APAC intel coverage, visual render,
   SharePoint containment, and evidence upload are now gates, but they were not
   part of the original production path.
4. think-cell authoring was treated as a binary unlock. The real model is
   layered: stock donor retrieval, named seed authoring, data binding, rendered
   proof, then production insertion.
5. Excel traceability and presentation polish were both mandatory, but they
   need separate contracts. Workbook formulas prove facts; PowerPoint/think-cell
   contracts prove presentation surfaces.

## Target Architecture

Keep existing top-level scripts as compatibility wrappers, but move durable
logic into a package-shaped factory:

```text
scripts/sd_factory/
  context/          period, director, SharePoint, folder, and snapshot rules
  extract/          Salesforce snapshots, filters, currency basis, as-of manifests
  model/            connected Excel workbook contracts and formula/audit sheets
  visuals/          think-cell KG/RAG planner, seed contracts, donor selection
  powerpoint/       deck assembly, table-image linking, native seed insertion
  qa/               fact gates, workbook gates, render gates, visual checks
  publish/          Downloads and SharePoint containment/upload/validation
  orchestration/    step runner, manifests, retries, resumable work queue
```

Target configuration layout:

```text
config/sales_director_factory/
  periods/2026-Q2.may.json
  directors.json
  sharepoint.json
  slide_contracts.json
  visual_style.json
  agent_roles.json
```

Target state layout:

```text
state/<period>/<DirectorSlug>/
  source/           raw extracts, filtered rows, Salesforce report evidence
  model/            workbook inputs and formula-driven outputs
  visuals/          per-contract chart/table datasets and proof payloads
  deck/             generated PPTX variants
  qa/               fact, workbook, visual, and publish reports

state/<period>/__regional__/
  production_runs/
  publish_gate/
  visual_gate/
  sharepoint/
  agent_runs/
```

Do not mass-move files until wrappers and tests exist. The first refactor should
create package modules and route one low-risk lane through them, then migrate
the rest.

## Long-Running Workstreams

| Workstream                       | Outcome                                                                                                                                                                                                                                                                                    | Gate                                                                                                                                                                                                                                                                                                                                                                                                                                                              |                                                       Est. |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------: |
| W0 May containment               | Existing May package stays green while scaffolding changes land.                                                                                                                                                                                                                           | `--sharepoint-validate` passes.                                                                                                                                                                                                                                                                                                                                                                                                                                   |                                                       done |
| W1 Factory package skeleton      | Shared context, runner, path, and artifact helpers replace ad hoc script globals.                                                                                                                                                                                                          | Scaffold tests pass and existing production scripts are unchanged.                                                                                                                                                                                                                                                                                                                                                                                                |                                                       done |
| W2 Period/month roll             | New period can be added through config, not code edits.                                                                                                                                                                                                                                    | `--period <new>` plan-only succeeds and refuses uncertified publish.                                                                                                                                                                                                                                                                                                                                                                                              |                                                   2-4 days |
| W3 Contract work queue           | think-cell KG/scaffold emits an executable build queue.                                                                                                                                                                                                                                    | Queue JSON has dependencies, owners, gates, artifacts, and stop conditions.                                                                                                                                                                                                                                                                                                                                                                                       |                                                       done |
| W4 L4 seed authoring lane        | Named seed PPTX library exists for priority contracts.                                                                                                                                                                                                                                     | 12/12 contracts at L5 proven as of 2026-05-01; see `state/thinkcell_bridge/build_scaffold/2026-Q2/work/*-proof.json`.                                                                                                                                                                                                                                                                                                                                             |                                                       done |
| W5 L5 binding proof lane         | Every visual contract has bound-output proof.                                                                                                                                                                                                                                              | 12/12 contracts at L5 proven as of 2026-05-01; see `state/thinkcell_bridge/build_scaffold/2026-Q2/work/*-proof.json`.                                                                                                                                                                                                                                                                                                                                             |                                                       done |
| W6 Agent orchestration           | Codex/Claude/VM work is split into durable specialist jobs.                                                                                                                                                                                                                                | Agent runs append manifests and never overwrite unrelated artifacts.                                                                                                                                                                                                                                                                                                                                                                                              |                                                   1-3 days |
| W7 Production ops                | Monthly run is resumable, archived, and publish-gated.                                                                                                                                                                                                                                     | One command produces local package and optional SharePoint publish evidence.                                                                                                                                                                                                                                                                                                                                                                                      |                                                   2-4 days |
| W8 Deck design hardening         | Deck reads as sales-director ready, not generated.                                                                                                                                                                                                                                         | Template contract gate blocks contaminated shell assets; brand-style gate blocks curved/rounded PowerPoint geometry, non-brand fonts, tiny text, off-scale font sizes, stale think-cell ownership metadata, and missing PowerPoint support relationships that trigger repair prompts. Current and prior-month contact sheets are compared; material layout/style drift requires human acknowledgement before publish.                                                     | template/style/repair gates done; MoM gate tuning remains |
| W9 Period rollover certification | New monthly/quarterly periods are certified before refresh or publish.                                                                                                                                                                                                                     | Plan-only harness asserts folder names, snapshot math, Salesforce filters, director roster, and publish block for uncertified periods.                                                                                                                                                                                                                                                                                                                            |                                                   2-4 days |
| W10 Insertion-pilot lane         | Two pilot candidates (QTR04, QTR05) are rendered side-by-side with current Q2 deck pages and judged for leadership decision improvement before any deck insertion. Production polish for QTR04/QTR05; the other 10 contracts stay on protect-lane and are not pilot candidates this round. | Pilot manifest exists under `state/<period>/__regional__/thinkcell_insertion_pilot/<run_id>/`, prior-month MoM design gate (W8) is acknowledged, ARR/ACV/Type filters preserved, EUR FX-converted aggregates used, no native think-cell table sneaks in. SharePoint upload is blocked until BOTH (a) the P0 publish-gate hardening lands AND (b) at least one-director (Jesper Tyrer) pilot record asserts leadership decision improvement vs. the current slide. | candidate_created_decision_blocked (QTR04 clean candidate, 2026-05-03) |

## Agentic Framework

Use a manifest-driven work queue. Agents should not free-form edit the deck
factory. Each job gets inputs, outputs, gates, and a stop rule.

Roles:

- Orchestrator: owns the run manifest, dependency graph, retries, and final
  status.
- Data Auditor: validates Salesforce filters, ARR/ACV separation, internal/test
  account exclusion, and weighted versus unweighted labels.
- Workbook Engineer: owns formula-driven Excel outputs, named ranges, and audit
  tabs.
- Think-cell Seedsmith: uses KG/RAG donor evidence to create or verify named
  seed PPTX surfaces.
- Binding Engineer: runs `.ppttc` or Excel UpdateBatch and emits L5 proof.
- Deck Designer: polishes slide composition against SimCorp visual conventions.
- QA Gatekeeper: runs fact, workbook, deck, render, APAC-intel, and SharePoint
  gates.
- Publisher: quarantines stale SharePoint assets, uploads only passed assets,
  and validates live folder state.

Each agent job should write:

```json
{
  "job_id": "2026-Q2.QTR02.seed_authoring",
  "role": "Think-cell Seedsmith",
  "inputs": [],
  "outputs": [],
  "gates": [],
  "status": "planned|running|pass|fail|blocked",
  "stop_conditions": [],
  "evidence": []
}
```

## think-cell / Graph RAG Capability Upgrades

The graph/RAG work should become a builder, not only a search tool.

Immediate upgrades:

1. Build queue generator: convert `thinkcell_build_scaffold.json` into ordered
   seed-authoring and proof jobs.
2. Negative evidence memory: record failed donors, broken naming attempts, and
   known non-automation templates so future agents stop relitigating them.
3. Seed verifier: inspect PPTX package and/or COM metadata for expected
   AddRangeData/AddRangeImage names before any production bind.
4. L5 proof runner: bind a contract, render output, assert expected labels and
   values, then write `*-proof.json`.
5. Donor ranking feedback: when a donor succeeds or fails, write that outcome
   back to the KG as evidence.
6. Design token extraction: compare successful SimCorp slides to stock
   think-cell donors and store style rules separately from data rules.
7. Prompt pack generator: for each contract, emit a compact Codex/Claude prompt
   containing only relevant donors, gates, and source facts.

Insertion-pilot order (proof phase closed 2026-05-01):

All 12 contracts are L5-proven (`l5_proven/pass`) per
`state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`.
The next operating mode is production polish on insertion candidates, not more
proofs.

W10 harness state (2026-05-03): `candidate_created_decision_blocked` for
Jesper QTR04.
`scripts/run_thinkcell_insertion_pilot.py` now runs in two read/plan modes
(`--plan-only` and `--promote`). Plan-only does deep preflight against the L5
proof artifacts and emits an executable `vm_insertion_commands.sh` plus a
`MANUAL_POWERPOINT_STEPS.md` per run dir. Promote mode validates VM/manual
candidate PPTX files (zip readable, slides present, no native PowerPoint
tables) and sets per-contract `candidate_created` / `awaiting_vm_insertion` /
`candidate_invalid`. The harness never opens Office on its own; it is always
`publishable: false`.

Current QTR04 run:
`state/2026-Q2/__regional__/thinkcell_insertion_pilot/20260503-qtr04-clean-scatter/`.
The candidate is clean enough to validate as a native think-cell chart surface:
one slide, no native PowerPoint table, no stock placeholder/comment residue,
and ARR/Type/ACV guardrails preserved. The decision record blocks production
insertion because the inherited stock donor grammar still does not produce a
leadership-better probability-vs-ARR inspection map versus the current
meeting-spine slide.

1. Pilot `QTR04_DealRisk_Scatter` first for Jesper Tyrer behind the existing
   publish/visual gates. Patrick Gaughan stays on the ranked-risk table
   fallback (positive ARR has only one distinct value per
   `thinkcell_quarter_salesforce_fit.json`).
2. Pilot `QTR05_FY26RenewalTimeline_Gantt` second for Jesper Tyrer behind the
   same gates. Adam Steinhouse stays on the renewal watchlist table fallback
   (FY26 close dates collapse to a single 2026-12-31 entry).
3. `QTR12_StalePipeline_BarTable` stays on the universal spine but is not a
   pilot candidate; the hybrid bar + table-image lane is already proven.
4. `QTR06_Q2RenewalTimeline_Gantt` stays narrow (Sarah Pittroff, Dan Peppett,
   Christian Ebbesen only); do not universalize.
5. `QTR07_StageIndustry_Mekko` stays appendix-only and density-gated.
6. Native think-cell editable tables remain blocked. Table-image via Excel COM
   `AddRangeImage` is the only proven table lane.

## Restructure Plan

Phase 1: Add package helpers without moving behavior.

- Create `scripts/sd_factory/context.py` by wrapping `period_context.py`.
- Create `scripts/sd_factory/artifacts.py` for path construction.
- Create `scripts/sd_factory/runner.py` for step execution and manifests.
- Keep top-level script entrypoints unchanged.

Phase 2: Move SharePoint and package gates.

- Move containment/upload/validation into `scripts/sd_factory/publish/`.
- Keep `scripts/upload_may_*` wrappers for compatibility.
- Add tests proving wrapper commands still call the same production functions.

Phase 3: Move QA gates.

- Move review package, visual render, row-filter, APAC-intel, and goal audits
  into `scripts/sd_factory/qa/`.
- Add one `factory verify` command that runs fast non-Office gates.

Phase 4: Move think-cell bridge.

- Move corpus/scaffold/proof logic into `scripts/sd_factory/visuals/`.
- Add a contract work queue generator and L5 proof registry.

Phase 5: Certify next monthly period.

- Add a new period config.
- Run `--plan-only`, then one-director source-only, then one-director full
  refresh, then all-director package, then SharePoint dry-run, then publish.

## Immediate Next 48 Hours

1. Add the build queue generator for think-cell contracts. Done:
   `.venv/bin/python scripts/build_thinkcell_work_queue.py --period 2026-Q2`.
2. Create `scripts/sd_factory/` with context/artifact/runner helpers and leave
   top-level wrappers intact. Done for the minimal scaffold.
3. Add a `factory doctor` command that checks Python deps, LibreOffice,
   pdftoppm, Azure CLI token, Windows VM bridge config, and latest green
   manifests. Current first-pass command:
   `.venv/bin/python scripts/sd_factory_doctor.py --period 2026-Q2`.
4. Add a `factory plan --period 2026-Q2` command that prints planned steps
   without touching decks or SharePoint.
5. Run the insertion-pilot harness for `QTR04_DealRisk_Scatter` and
   `QTR05_FY26RenewalTimeline_Gantt` against Jesper Tyrer's current Q2 deck
   pages.
   - Plan-only:
     `.venv/bin/python scripts/run_thinkcell_insertion_pilot.py --period 2026-Q2 --director-slug Jesper-Tyrer --contracts QTR04_DealRisk_Scatter QTR05_FY26RenewalTimeline_Gantt --plan-only`.
     Reads scaffold + L5 proofs, runs deep preflight, writes manifest +
     `vm_insertion_commands.sh` + `MANUAL_POWERPOINT_STEPS.md` under
     `state/2026-Q2/__regional__/thinkcell_insertion_pilot/<run_id>/`.
   - Insert (run separately on a host with Office + think-cell): execute the
     emitted `vm_insertion_commands.sh` on the Windows VM bridge or follow
     `MANUAL_POWERPOINT_STEPS.md` on Mac/Windows PowerPoint with think-cell
     installed; never run Office from the harness host.
   - Promote (after candidates are produced):
     `.venv/bin/python scripts/run_thinkcell_insertion_pilot.py --period 2026-Q2 --director-slug Jesper-Tyrer --contracts QTR04_DealRisk_Scatter QTR05_FY26RenewalTimeline_Gantt --promote --run-id <same-run-id>`.
     Validates each candidate PPTX (zip readable, slides present, no native
     PowerPoint tables) and rewrites the manifest with
     `candidate_created` / `awaiting_vm_insertion` / `candidate_invalid` per
     contract. Render side-by-side contact sheets, decide leadership value per
     HANDOFF section "How To Use The Proofs" step 5, and only then consider
     deck insertion behind the existing factory/publish gates.
6. Add the period-roll certification harness before any non-May refresh or
   publish.
7. Add the MoM contact-sheet design gate so W8 has an objective pre-publish
   stop condition.
8. Update docs only after each command passes; avoid another narrative-only
   drift loop.

## Non-Negotiable Gates

- ARR and ACV never blend. ARR is Land + Expand only and uses
  `APTS_Opportunity_ARR__c`. Renewal ACV is Renewal only and uses
  `APTS_Renewal_ACV__c`.
- Every Type-bearing report has explicit Type filters. Type-bearing ARR visuals
  require `Type IN ('Land','Expand')`; Type-bearing ACV visuals require
  `Type = 'Renewal'`.
- Headline currency uses FX-converted EUR aggregates from Salesforce report
  fields (`s!APTS_Opportunity_ARR_c`, `s!APTS_Renewal_ACV_c`); raw multi-currency
  SOQL `SUM` over unconverted rows is forbidden for any leadership figure.
- Weighted and unweighted numbers are labeled at the tile/table/chart level.
- Test, SimCorp, and internal `SC` account/opportunity pollution is filtered.
- Every deck has a source workbook, table-source workbook, production manifest,
  visual gate, and SharePoint validation when published.
- `--refresh-source` cannot package stale PowerPoint links.
- Unsupported periods fail closed until period config and freshness gates are
  certified.
- Native think-cell editable tables remain blocked. Table-image via Excel COM
  `AddRangeImage` is the only proven table lane. Insertion pilot rejects any
  deck whose pilot slide uses native think-cell table elements; native-table
  resolution is open R&D, not a production lane.
- Native think-cell charts are not production until (a) L5 proof passes for the
  contract AND (b) an insertion-pilot record exists asserting leadership
  decision improvement vs. the current slide. L5 proof alone is sufficient for
  protect-lane reference, not for production deck insertion.
- SharePoint upload of any insertion-pilot output is blocked until BOTH (a) the
  P0 publish-gate hardening lands (gate_hardening ASSERTION_BACKLOG A-1,
  B-1/B-2/B-3, C-1/C-2, D-1/D-2/D-3, E-1/E-2) AND (b) at least one-director
  pilot record (Jesper Tyrer first) asserts leadership decision improvement.
  Pilot output stays under `state/<period>/__regional__/thinkcell_insertion_pilot/`
  until both conditions are met.
- `sd_factory_doctor.py` must be clean or warning-only before launching
  long-running Office/VM work. A missing unrelated analytics dependency is a
  warning; missing render, package, manifest, or SharePoint proof is critical.
- A new month or quarter is not production because `period_context.py` can
  format labels. It is production only after the period-roll certification
  harness passes and publish remains blocked until that certification exists.

## Definition Of Done

The durable factory is ready when a new monthly cycle can be run as:

```bash
.venv/bin/python scripts/run_regional_production_line.py \
  --period <certified-period> \
  --refresh-source \
  --full-table-image-refresh \
  --jobs 4

.venv/bin/python scripts/run_regional_production_line.py \
  --period <certified-period> \
  --jobs 6 \
  --sharepoint-publish
```

and the resulting status report proves:

- 9/9 decks built and packaged.
- Source, workbook, deck, visual, and SharePoint gates passed.
- Every visual has a contract, source range, and proof artifact.
- Every think-cell visual that lands in production has both a `*-proof.json`
  AND an insertion-pilot record under
  `state/<period>/__regional__/thinkcell_insertion_pilot/<run_id>/`.
- Every published file is expected, current, and traceable.
