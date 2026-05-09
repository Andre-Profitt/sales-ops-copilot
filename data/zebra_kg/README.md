# data/zebra_kg/

Generated artifacts from the Zebra BI knowledge-graph extraction.
Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`.

## Files

- `nodes_datamodel.jsonl` — Measure, Table, Column, Relationship, Scenario, StyleToken nodes
- `edges_datamodel.jsonl` — depends_on, related_to, scenario_of, resolves_to, uses_token
- `measure_catalog.csv` — flat catalog of every DAX measure across the 20 PBIX templates
- `style_tokens.json` — deduped style token catalog with usage counts and canonical flags

All four files are gitignored. Regenerate with:

````bash
python3 -m scripts.sales.rw_zebra_kg_datamodel \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --analysis-dir ~/Downloads/rw-zebra-bi-template-research-20260509/analysis \
  --out-dir data/zebra_kg

python3 -m scripts.sales.rw_zebra_kg_tokens \
  --source-dir ~/Downloads/rw-zebra-bi-template-research-20260509/files \
  --out-dir data/zebra_kg
```
````
