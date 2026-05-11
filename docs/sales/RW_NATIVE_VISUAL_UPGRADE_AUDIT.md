# RW Native Visual Upgrade Audit

Generated: `2026-05-11T02:19:09Z`

This audit ranks where the dashboard is still underusing native Power BI/Zebra-derived visual grammar. It is not a basic correctness gate.

## Summary

- Findings: `2`
- Severity: info=0, low=1, medium=1, high=0, critical=0

## Target Visual Vocabulary

| Visual | Use for |
| --- | --- |
| `waterfallChart` | contribution bridges, gap explanations, renewal-base movement |
| `tableEx/pivotTable + field-value cell backgrounds` | product/segment/region/source heatmaps |
| `tableEx/pivotTable + dataBars` | variance matrices and Zebra bullet-bar equivalents |
| `tableEx + Zebra detail grammar` | action ledgers and accountable drill rows |
| `card + neutral Zebra-native grammar` | compact KPI spine only; not for explanatory card walls |

## Ranked Upgrade Queue

| Severity | Page | Current visual | Recommended visual | Finding | Next action |
| --- | --- | --- | --- | --- | --- |
| `medium` | VP Ops Scorecard | `clusteredBarChart` - Stage \| Open ARR (Land + Expand) | `waterfallChart or pivotTable heatmap` | A bar chart is carrying an executive value decomposition candidate. | Use a native bridge when explaining contribution; use heatmap when comparing slices. |
| `low` | VP Ops Scorecard | `clusteredBarChart` - Stage \| Open ARR (Land + Expand) | `same native visual with Zebra-native helper objects` | Decision visual is native but does not carry Zebra-derived grammar metadata. | Apply a shared Zebra-native helper if this visual remains in the executive path. |
