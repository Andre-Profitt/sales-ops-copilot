# Sales Director Factory Rendering Strategy

Date: 2026-05-03

## Decision

The 9-director monthly Sales Director deck factory is a compute-and-bind system,
not a generative slide-authoring system.

Use `.ppttc` / `ppttc.exe` and the Windows think-cell bridge as the production
rendering substrate. Use the strongest available reasoning model upstream,
preferably GPT-5.5 in Andre's current stack, to decide story, wording, and
chart-class choices from a grounded context pack. Then bind deterministic
payloads through `.ppttc` or Excel COM. Do not base the monthly factory on
`tc.ai` ribbon workflows.

## Why

Monthly Sales Director decks need reproducibility, auditability, speed, and
headless execution. Salesforce computes the facts, the template pre-decides the
layout, and the recurring narrative patterns can be generated before rendering.

`.ppttc` is the receipt: it records the exact named-element bindings that
produced the deck. The same payload and template should produce byte-stable or
package-stable output, and the output can be validated by package assertions,
render checks, and publish gates.

This is not an anti-AI decision. It is a separation of concerns: GPT-5.5 should
do the thinking, sharpening, and narrative drafting; `.ppttc` / Excel COM should
do the reproducible rendering. `tc.ai` is useful for interactive one-off work,
narrative exploration, and ribbon-side refinement. GPT-5.5 can sit above that
workflow as the external brain that prepares prompts, checks outputs, and drives
PowerPoint/ribbon interactions when a human-in-the-loop pass is useful.

The constraint is reproducibility. Unless think-cell exposes a model/plugin hook,
GPT-5.5 is not literally replacing the model inside `tc.ai`; it is orchestrating
or pre-composing around it. `tc.ai` itself remains stochastic, quota-bound,
account-authenticated, and currently ribbon/UI-led. Those properties make it a
poor foundation for a monthly executive reporting factory, even if GPT-5.5 uses
it as an interactive surface.

## Rendering Lanes

| Lane | Factory Role | Status |
|---|---|---|
| `.ppttc` via `ppttc.exe` | Primary substrate for named think-cell charts, automation text fields, and deterministic template binding. | Production |
| Excel COM `UpdateBatch` / `AddRangeImage` | Primary lane for table-shaped artifacts and image-table refresh. | Production |
| PowerPoint COM merge | Controlled post-bind insertion/merge step for native think-cell chart shapes into branded LAND decks. | Production |
| Python package/OLE splice | Mac-side fallback and research lane for tc-aicore experiments; not the production substrate until it passes the same gates. | Fallback |
| GPT-5.5 / Claude / Codex | Planner and narrative generator before binding; GPT-5.5 is preferred for story sharpening when available. Output must be cached and bound deterministically. | Upstream |
| GPT-5.5-assisted `tc.ai` ribbon pass | Optional human-in-the-loop refinement surface. GPT-5.5 can prepare prompts, critique `tc.ai` output, and capture accepted wording. | Interactive assist |
| `tc.ai` ribbon workflow | Interactive convenience for one-off decks or exploration; not monthly production. | Nice-to-have |

## Control Rules

- `.ppttc` cannot create missing chart objects. Named think-cell elements must
  already exist in the seed/template.
- Native editable think-cell tables remain blocked. Use Excel COM
  `AddRangeImage` for table-shaped artifacts.
- Do not judge success by `ppttc.exe` exit code alone. Require named-element
  contract validation, bound-package assertions, rendered-slide checks, and the
  regional publish gate.
- Do not blend ARR and Renewal ACV. ARR is Land+Expand only via
  `APTS_Opportunity_ARR__c`; Renewal ACV is Renewal only via
  `APTS_Renewal_ACV__c`.
- AI-generated text must be treated as source material, not a source of truth.
  Cache it, bind it, and validate it against the fact pack / workbook.
- GPT-5.5 reduces hallucination risk, but it does not replace gates. Every
  generated title, S02 bullet, risk statement, and chart recommendation must
  carry supporting fact IDs or workbook references before it can be bound.
- GPT-5.5 may choose among known chart classes, binding slots, and render lanes;
  it must not invent unsupported metrics, prior-period comparisons, or new
  think-cell capabilities outside the schema/contract context.
- A GPT-5.5-assisted `tc.ai` ribbon pass is admissible only as an exploratory
  or editorial step. Accepted text or chart choices must be copied back into the
  run artifact with evidence references before production binding.

## Operating Model

1. Refresh Salesforce source and connected workbooks.
2. Build a grounded AI context pack: validated fact pack, workbook excerpts,
   SimCorp rules, `tcxml`/think-cell capability vocabulary, and the render-lane
   contract.
3. Ask GPT-5.5 for structured narrative/chart-selection JSON with evidence
   references and explicit nulls where facts are unavailable.
4. Persist the GPT-5.5 output into the run artifact, then generate
   deterministic `.ppttc` payloads from computed facts and cached narrative
   strings.
5. Validate `.ppttc` against the named seed contract.
6. Render through Windows `ppttc.exe`.
7. Refresh table-image ranges through Excel COM where required.
8. Merge into the branded LAND layout where required.
9. Run package, visual, fact, ARR/ACV, period-label, freshness, and publish
   gates.
10. Publish only when the gates pass.

## Implications For `tc-aicore`

`tc-aicore` should not become a parallel 8-director rendering factory. Its role
is to modularize and improve the factory:

- adopt the 9-director production registry, including Mourad / MEA;
- emit `.ppttc` or Excel COM payloads as a first-class output;
- use Graph-RAG to choose the rendering lane per slot;
- reuse the regional publish gate standard;
- use GPT-5.5 as the preferred title, S02 summary, risk narrative, and chart
  grammar planner when available;
- keep AI title and summary generation as cached, validated input to
  deterministic binding;
- keep OLE splice builders as fallback/proof machinery until they reach the
  same L4/L5 proof and publish-gate standard as the production lane.

## Immediate Workstreams

1. **Render-lane contract**
   - Produce a machine-readable slot map:
     `slot_id -> primary_lane -> template_name -> proof_artifact -> fallback`.
   - Success gate: every slot has exactly one primary production lane or an
     explicit blocked/fallback status.

2. **Registry convergence**
   - Compare `tc_aicore.simcorp_kg` with `scripts/_directors.py`.
   - Success gate: production monthly target is 9 directors in both systems.

3. **tc-aicore publish-gate wrapper**
   - Wrap the regional gate principles for tc-aicore outputs: forbidden text,
     ARR/ACV labels, period labels, workbook errors, hyperlinks, render sanity,
     and freshness.
   - Success gate: a tc-aicore deck cannot be called shippable until this gate
     passes.

4. **AI-to-binding discipline**
   - Generate AI title/S02 text upstream, cache it in the run artifact, and bind
     it through `.ppttc` / deterministic deck edits.
   - Status: partially closed on 2026-05-03 in `tc-aicore`; AI enrichment now
     writes a cached artifact and validates evidence refs before title/S02
     splicing. Production all-9 manifest integration remains.

5. **Fact completion**
   - Wire `OpportunityFieldHistory` for slipped ARR / slip velocity.
   - Status: closed on 2026-05-03 in `tc-aicore`; S04 now computes slipped ARR
     from in-quarter `CloseDate` changes that move Land/Expand opportunities
     out of period.

## Non-Goals

- Do not pursue native editable think-cell tables without a real manually named,
  data-backed donor that updates cleanly without repair prompts.
- Do not build around Office Web Add-ins for think-cell automation.
- Do not start or register `tcserver.exe` without an explicit architecture
  decision.
- Do not make `tc.ai` a dependency for monthly production.
