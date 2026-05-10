# RW Zebra Schema Architecture Review

This mines `data/zebra_kg/schemas/<slug>/model.json` across the Zebra template corpus for semantic-model patterns that should inform RW dashboard architecture.

## Corpus Summary

- Templates: 20
- Relationships: 133
- Single-direction relationships: 130
- Bidirectional relationships: 3
- Inactive relationships: 7
- Templates with calendar tables: 11
- Templates with role-playing dimensions: 2
- Templates with ordered dimensions: 2
- Templates with scenario columns: 12
- Templates with KPI metadata tables: 13

## RW Architecture Guidance

| Zebra pattern | Evidence | RW application |
| --- | --- | --- |
| `single_direction_star` | 130/133 relationships use single-direction filtering. | Keep RW relationships conservative and do not introduce bidirectional filters to make slicers feel easier. |
| `role_playing_dates` | 2/20 schemas use role-playing dimensions and 7 inactive relationships exist in the corpus. | Add explicit transition-date roles before exposing Stage Move FQ or Forecast Move FQ slicers. |
| `ordered_dimensions` | 2/20 schemas carry sort/order/rank columns on dimensions. | Promote stage order into a canonical d_stage dimension instead of relying on label sorting. |
| `scenario_as_axis` | 12/20 schemas carry scenario/version as data columns, while only 1 use scenario dimensions. | Treat Motion as a labeled analytic axis or explicit measure family, not a universal page slicer. |
| `kpi_dictionary` | 13/20 schemas include KPI/table metadata; sales-funnel uses KPI_ID with an inactive KPI relationship. | Keep RW KPI/page contracts executable and consider a future d_kpi metadata table for governed explorer behavior. |

## Sales Funnel Exemplar

- Fact tables: `Data`
- Dimension tables: `Country`, `Customer`, `KPIs`, `Products`
- KPI tables: `KPIs`
- Scenario columns: {"Data": ["Scenario"]}
- Ordered dimension columns: {"Products": ["Ranking"]}
- Long fact + KPI + scenario pattern: `True`

The direct RW lift is architectural, not literal: keep the KPI contract executable, treat motion/scenario as an explicit analytic axis, and move business ordering into dimensions.
