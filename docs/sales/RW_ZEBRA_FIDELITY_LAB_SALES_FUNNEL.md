# RW Zebra Fidelity Lab - Sales Funnel

Date: 2026-05-09

## Decision

Use `sales-funnel-power-bi-template` as the one high-fidelity bridge specimen.
Do not expand to the other Zebra templates until this specimen is visually
reviewed and the same gates are repeatable.

This template is the right first specimen because it is closest to RW's pipeline
and stage-movement use case, and it has a clean model reconciliation profile:
only one placeholder column is needed and there are no unresolved measure refs.

## Live Artifact

- Report: `zbr_fidelity_sales-funnel-power-bi-template`
- Semantic model: `sm_zbr_fidelity_sales-funnel-power-bi-template`
- Workspace: `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
- URL: https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/02edc230-461b-4ffb-b1cc-cb9e067fa66a

## What Changed

The native bulk bridge translated only mined Zebra visual fragments. This lab
preserves the source PBIX report frame:

- all report pages
- all visualContainers, Zebra and non-Zebra
- static resources
- Zebra custom visual packages
- source report theme/resource package references
- source geometry

License-like object groups are stripped from visual config before publish.

## Gate Results

Artifacts:

- `scripts/sales/rw_zebra_kg_fidelity_publish.py`
- `tests/sales/test_rw_zebra_kg_fidelity_publish.py`
- `data/zebra_kg/published/fidelity_templates.json`
- `data/zebra_kg/published/fidelity_sales-funnel-power-bi-template_verify.json`

Local source gate:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_fidelity_publish \
  --dry-run \
  --template sales-funnel-power-bi-template
```

Result:

```text
pages=6 visuals=104 resources=19 custom_visual_parts=6 static_resources=13 extra_cols=1 unresolved_measure_refs=0
```

Live Fabric round-trip gate:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_fidelity_publish \
  --verify-live \
  --template sales-funnel-power-bi-template
```

Result:

```text
live_verify=pass format=PBIR-Legacy pages=6/6 visuals=104/104 resources=19/19 missing_resources=0 semantic_model_bound=True
```

## Acceptance Before Scaling

This one template is not "done" until visual review confirms the rendered
dashboard looks materially closer to the Zebra source than the native bulk
approximation. The engineering bridge is now preserving the report definition;
the next gate is renderer fidelity in Fabric or Power BI Desktop.

Scale rule: the next template can only be added after the previous one passes
the same source gate, live round-trip gate, and screenshot/visual review gate.
