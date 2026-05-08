# think-cell Template Intelligence DB

Date: 2026-05-03

Purpose: stop treating think-cell template/candidate existence as enough to
build slides. The template intelligence DB is the decision layer that tells the
deck factory which template family, contract, proof, candidate, and lane can be
used, and what blocks promotion.

## Command

```bash
.venv/bin/python scripts/build_thinkcell_template_intelligence_db.py --period 2026-Q2
```

Outputs:

- `state/thinkcell_bridge/template_intelligence/2026-Q2/thinkcell_template_intelligence.sqlite`
- `state/thinkcell_bridge/template_intelligence/2026-Q2/thinkcell_template_intelligence_report.json`
- `state/thinkcell_bridge/template_intelligence/2026-Q2/thinkcell_template_intelligence_report.md`

## Sources Joined

- Stock template catalog:
  `state/thinkcell_bridge/template_catalog/thinkcell_template_catalog.json`
- SimCorp selection map:
  `config/thinkcell_template_selection.may_2026.json`
- Capability map:
  `docs/thinkcell-corpus/thinkcell_infra_capability_map.json`
- L5 scaffold:
  `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.json`
- Per-director visual decisions:
  `state/2026-Q2/__regional__/thinkcell_visual_plan/thinkcell_visual_contract_plan.json`
- Insertion-pilot manifests under:
  `state/2026-Q2/__regional__/thinkcell_insertion_pilot/*/manifest.json`

## Tables

- `template_catalog`: local stock `.potx` evidence, including slide count,
  chart refs, OLE parts, tag files, and named automation payload count.
- `selected_family`: SimCorp family posture and use cases from the curated
  selection map.
- `capability`: production/proof/research/blocked capability registry.
- `contract`: quarter visual contracts, supported lane, guardrail, fallback,
  readiness, proof status, and proof artifact references.
- `director_decision`: per-director decision joined to a recommendation and
  next action.
- `candidate_artifact`: insertion-pilot candidate PPTX audits, including zip
  validity, slide count, embeddings, placeholder/template residue, and
  promotion grade.

## Current Verdict

The DB confirms the correct infra posture:

- Stock think-cell templates are visual/donor references, not direct `.ppttc`
  automation templates. The catalog has zero named `m_strName` automation
  payloads.
- Bar/Column, Waterfall, and Mekko are seeded/proven lanes.
- Tables remain blocked as native editable think-cell objects; use the
  table-image lane.
- Scatter/Bubble and Timeline/Gantt are candidate lanes that require clean
  named donor output plus a promotion record before insertion.
- Current Jesper QTR04/QTR05 candidate PPTX files are zip-clean but not
  promotion-ready because they still contain stock template residue such as
  placeholder titles, lorem text, sample company labels, and think-cell help
  text.

## Builder Rule

The regional deck builder must consume this DB or equivalent report before it
inserts any candidate think-cell slide. A candidate is not usable until:

1. The contract is L5-proven and the director data-shape gate passes.
2. The candidate PPTX is zip-clean and renderable.
3. The candidate audit has zero forbidden template residue.
4. The business guardrail preserves ARR versus Renewal ACV separation.
5. A promotion record exists for the target spine position.

Until those gates pass, the production deck should keep the safe meeting-spine
fallback rather than inserting templateware.
