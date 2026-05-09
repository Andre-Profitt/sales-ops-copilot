# data/zebra_kg_rw/

RW binding overlay — links Zebra template elements to RW tabs/fields/measures.
Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`.

## Files

- `bindings.jsonl` — RWBinding nodes with status: bound | unbound | needs_measure
- `rw_targets.csv` — flat view: RW tab × element × source visual_id × status

Both gitignored. Regenerate with:

`python3 -m scripts.sales.rw_zebra_kg_bind --out-dir data/zebra_kg_rw`
