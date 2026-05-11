# RW Zebra Native Layout Bridge - Sales Funnel

Date: 2026-05-09

## Decision

The SimCorp-safe bridge is **native layout**, not custom-visual fidelity.

The previous fidelity report preserved Zebra custom visuals and therefore can be
blocked by tenant custom-visual policy. The native-layout bridge keeps the full
source report frame, then replaces only Zebra custom visuals with native Power
BI visuals.

## Live Artifact

- Report: `zbr_native_layout_sales-funnel-power-bi-template`
- Semantic model: `sm_zbr_native_layout_sales-funnel-power-bi-template`
- Workspace: `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
- URL: https://app.fabric.microsoft.com/groups/b66233d5-9d4a-44ba-89a8-b70206d98ae7/reports/7483393a-17ff-42e8-9e46-97a425cd6b94

## What This Bridge Preserves

- all source pages
- all source visualContainer slots
- non-Zebra page furniture: textboxes, images, shapes, buttons, slicer shells
- source static resources and theme resources
- semantic model binding through `definition.pbir`

## What This Bridge Removes

- `CustomVisuals/*` report definition parts
- custom visual resource packages from `report.json`
- Zebra visual types in report visualContainers

Zebra visual containers are translated to native Power BI equivalents:

- Zebra BI Cards -> native `multiRowCard`
- Zebra BI Tables -> native `tableEx`
- Zebra waterfall -> native `waterfallChart`

## Gate Results

Source/native local gate:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_native_layout_publish \
  --dry-run \
  --template sales-funnel-power-bi-template
```

Result:

```text
pages=6/6 visuals=104/104 translated_custom_visuals=20 fallback_textboxes=0 static_resources=13 custom_visual_leftovers=0 custom_resource_parts=0 extra_cols=1 unresolved_measure_refs=0
```

Live Fabric round-trip gate:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_native_layout_publish \
  --verify-live \
  --template sales-funnel-power-bi-template
```

Result:

```text
native_layout_verify=pass format=PBIR-Legacy pages=6/6 visuals=104/104 static_resources=13/13 custom_resources=0 custom_visual_leftovers=0 semantic_model_bound=True
```

## Scale Rule

This is the bridge pattern to use for SimCorp. Add the next template only after
the Sales Funnel native-layout report passes human visual review. Each template
must pass the same gates before publish:

- page count preserved
- visual count preserved
- static resources preserved
- custom resource parts equal zero
- custom visual leftovers equal zero
- unresolved measure refs equal zero
