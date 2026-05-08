# think-cell Template Corpus for SimCorp

Date: 2026-05-01

This corpus turns the installed think-cell pre-populated template library into
SimCorp-specific guidance for Sales Ops, Commercial leadership, QBR, ExCo, and
director-review decks.

## Source Artifacts

- Stock think-cell templates:
  `/Library/Application Support/Microsoft/think-cell/templates`
- Raw local inventory:
  `state/thinkcell_bridge/template_catalog/thinkcell_template_catalog.md`
- Machine inventory:
  `state/thinkcell_bridge/template_catalog/thinkcell_template_catalog.json`
- Visual contact sheet:
  `state/thinkcell_bridge/template_catalog/thinkcell_template_contact_sheet.png`
- SimCorp selection map:
  `config/thinkcell_template_selection.may_2026.json`
- SimCorp LAND seed:
  `assets/LAND_thinkcell_seed.pptx`
- SimCorp table-image donor:
  `assets/LAND_thinkcell_table_image_donor.pptx`
- Connected factory contract:
  `config/connected_thinkcell_factory.jesper_apac.json`

## Evidence Summary

The installed library contains 62 `.potx` template files, 497 slides, 69
chart references, 337 OLE embedding parts, and zero named `m_strName`
automation payloads.

That means the stock think-cell templates are not drop-in `.ppttc` automation
templates. They are visual references and donor sources. The actual SimCorp
automation lane is the generated LAND seed, which contains 42 named elements,
and the table-image donor lane, which uses Excel COM `AddRangeImage`.

As of 2026-05-01, the 2026-Q2 scaffold has 12/12 quarter contracts at
`l5_proven/pass`: native chart seed-renaming lanes, stock Scatter/Gantt donor
lanes, table-image lanes, and the stale-pipeline hybrid lane.

## Operating Conclusion

Use think-cell templates in three distinct ways:

1. Visual grammar: borrow the chart family, spacing, annotation, and label
   conventions.
2. Donor object source: copy intact chart object graphs into a SimCorp seed,
   then name the object in the think-cell CFB payload.
3. Corpus guidance: select chart families by SimCorp decision question and
   metric rules, not by what looks good in the stock gallery.

Do not treat the stock templates as production-ready SimCorp assets. They are
templateware until the object is tied to a named range, a validation rule, and a
SimCorp metric basis.

## Non-Negotiable SimCorp Rules

- ARR means Land + Expand only and uses `APTS_Opportunity_ARR__c`.
- Renewal ACV means Renewal only and uses `APTS_Renewal_ACV__c`.
- Never blend ARR and ACV in one metric, chart, total, KPI strip, or bridge.
- Type-bearing ARR visuals require `Type IN ('Land','Expand')`.
- Type-bearing ACV visuals require `Type = 'Renewal'`.
- Headline Salesforce currency figures must use FX-converted EUR reporting
  aggregates or an explicit conversion lane.
- The SimCorp 8-stage process is stage-explicit. It is not a generic funnel.
- Land Commercial Approval uses `Stage_20_Approval__c`; approval exceptions
  should be shown as named-deal evidence, not generic process art.

## Corpus Files

- `HANDOFF.md`: start-here orientation for future sessions.
- `HANDOFF_SLIDE_BUILD_2026-05-02.md`: context-reset handoff for using the
  graph/RAG and visual contract plan to build better Sales Director slides.
- `INFRA_CAPABILITY_PLAN_2026-05-02.md`: capability-aware builder plan for
  using Python, `tcrender`, Windows `ppttc.exe`, Excel COM, `tc_com_driver`,
  `tcxml`, VBA, C#, optional AI Core enrichment, donor/seed proofs,
  table-image lanes, and research-only surfaces without drifting into fake
  slide drawing.
- `TEMPLATE_INTELLIGENCE_DB_2026-05-03.md`: normalized SQLite/report layer
  that joins template catalog, selected families, capability map, L5 proofs,
  visual decisions, and insertion candidates before any candidate slide can be
  promoted into a deck.
- `thinkcell_infra_capability_map.json`: machine-readable registry seed for
  production/proof/research/blocked think-cell automation capabilities and the
  Jesper promotion gate.
- `template-family-map.md`: interpreted family-by-family guidance.
- `simcorp-application-matrix.md`: mapping from SimCorp use cases to visual
  lanes, eligibility gates, and avoid rules.
- `automation-contract.md`: what can be automated safely and what remains
  blocked.
- `json-data-automation-hub.md`: durable factory hub for think-cell `.ppttc`
  JSON automation - official semantics, VM/API runtime evidence, decision
  matrix, and stop conditions. Companion machine index at
  `state/thinkcell_bridge/json_automation/knowledge_hub.json`.
- `graph-rag.md`: local graph/RAG usage for template, donor, proof, and
  Salesforce-fit retrieval.
- `build-scaffold.md`: L0-L5 build gates and the current 12/12 L5 proof state.
- `vm-api-probe.md`: latest Parallels Windows VM probe runtime evidence (paths,
  machine surface, operating-model implications).
- `automation-api-surface.md`: stable readable hub for the think-cell
  automation/API surface (Excel data automation, PowerPoint COM, JSON
  automation, capability verdicts) attributed to the official manual. Now
  includes Developer Setup (VBA/C#/VSTO/late binding/HRESULT/web add-in
  block), Official Examples (PresentationFromTemplate, UpdateBatch, Style
  API, Mekko, JSON CLI/HTTP), and an Adoption Matrix per lane.
- `automation-api-source-map.md`: structured link graph from every official
  manual page and Microsoft Learn reference to its factory implication +
  status (`production`, `proof_candidate`, `reference_only`, `blocked`,
  `not_applicable`) and probe coverage.
- `unblock-matrix.md`: explicit verdict table for the contested lanes
  (Mekko import, native editable tables, Office Web Add-ins, direct chart
  creation, `tcserver.exe`, and style API).
- `hidden-surface-probe.md`: bounded reverse-engineering probe for hidden
  constructor/ribbon surfaces; confirms no callable headless chart constructor
  through `IDispatch`.
- `com-registry-probe.md`: registry, OleViewDotNet, live COMAddIns, and
  Procmon evidence; confirms the VM exposes one late-bound think-cell add-in
  CLSID backed by `tcaddin.dll`, with no registered TypeLib or separate
  chart-factory CLSID.
- `interactive-ui-path-probe.md`: desktop-console UI follow-up; proves
  `StartTableInsertion()` plus a scripted canvas click can create a native
  think-cell `CSmartGrid`, but also confirms it is unnamed and not yet a
  production `.ppttc` table lane.
- `github-surface-scan.md`: official think-cell GitHub org and third-party
  `.ppttc` writer scan. Confirms GitHub does not expose a chart factory, but
  does provide useful design references for stricter internal writer/linter
  scaffolding.
- `ppttc-validator.md`: reusable `.ppttc` lint gate for structure, duplicate
  names, and expected-name manifest drift before files go through the Windows
  VM bridge.
- `workplan.md`: current workstreams, commands, and non-goals.
- `manifest.json`: tracked corpus manifest for future agents.
- `state/thinkcell_bridge/knowledge_corpus/simcorp_thinkcell_corpus.json`:
  local machine-readable index for future agents and scripts. This lives under
  `state/`, which is intentionally gitignored.

## How Future Agents Should Use This

Start from the decision question, then choose the visual family:

- "What changed?" usually means Waterfall.
- "Where is value concentrated?" usually means ranked Bar/Column or Scatter.
- "Which deals need action?" usually means table or decision register.
- "What happens when?" means Timeline/Gantt only when dates differ materially.
- "What is the mix?" means stacked Bar/Column first; Mekko only when both
  dimensions matter and the matrix is dense.

If a visual cannot pass its eligibility gate, fall back to a table or simpler
bar chart. The deck should preserve trust over novelty.
