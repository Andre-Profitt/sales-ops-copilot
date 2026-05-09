# RW Zebra Native Conversion Audit

Generated: 2026-05-09

## Readout

The current native bridge is structurally useful, but it is not a fidelity
converter. Across the 20 Zebra source PBIX reports it uses only the mined Zebra
custom-visual rows and drops the rest of the report frame. That is enough for
translator plumbing, not enough for polished dashboard review.

| Metric | Value |
| --- | ---: |
| Source PBIX pages | 195 |
| Source visualContainers | 1729 |
| Source Zebra visualContainers mined | 360 |
| Dropped non-Zebra context visualContainers | 1369 |
| Native pages emitted after page-preserving fix | 180 |
| Native visualContainers emitted | 360 |
| Native fallback textboxes | 1 |
| Native off-canvas visuals | 0 |
| Native unresolved measure refs | 0 |
| Native placeholder column refs added by TMDL emitter | 186 |

## Template Gate

| Template | Source pages | Source VCs | Zebra rows | Coverage | Dropped ctx | Native pages | Native VCs | Fallbacks | Off-canvas | Verdict | Primary issue |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `cost-management-power-bi-template` | 17 | 148 | 31 | 20.9% | 117 | 16 | 31 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `saas-sales-power-bi-dashboard-template` | 10 | 97 | 28 | 28.9% | 69 | 10 | 28 | 1 | 0 | native-approx-only | 69 non-Zebra source visuals dropped |
| `social-media-power-bi-template` | 10 | 57 | 27 | 47.4% | 30 | 10 | 27 | 0 | 0 | native-approx-only | 30 non-Zebra source visuals dropped |
| `dynamic-comments-power-bi-template` | 15 | 149 | 23 | 15.4% | 126 | 14 | 23 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `hr-analytics-power-bi-template` | 7 | 136 | 23 | 16.9% | 113 | 5 | 23 | 0 | 0 | not-template-fidelity | 2 source pages have no mined Zebra visual |
| `consolidated-financials-power-bi-template` | 11 | 95 | 22 | 23.2% | 73 | 11 | 22 | 0 | 0 | native-approx-only | 73 non-Zebra source visuals dropped |
| `manufacturing-oee-power-bi-template` | 6 | 91 | 22 | 24.2% | 69 | 6 | 22 | 0 | 0 | native-approx-only | 69 non-Zebra source visuals dropped |
| `sales-dashboard-power-bi-template` | 13 | 139 | 22 | 15.8% | 117 | 12 | 22 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `brand-product-portfolio-analysis-fmcg-power-bi-template` | 12 | 83 | 21 | 25.3% | 62 | 11 | 21 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `sales-funnel-power-bi-template` | 6 | 104 | 20 | 19.2% | 84 | 5 | 20 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `brand-product-portfolio-analysis-automotive-power-bi-template` | 11 | 101 | 17 | 16.8% | 84 | 10 | 17 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `athletic-footwear-benchmarking-financial-analysis-template` | 14 | 114 | 16 | 14.0% | 98 | 12 | 16 | 0 | 0 | not-template-fidelity | 2 source pages have no mined Zebra visual |
| `food-beverage-financial-analysis-benchmarking-powerbi-template` | 14 | 114 | 16 | 14.0% | 98 | 12 | 16 | 0 | 0 | not-template-fidelity | 2 source pages have no mined Zebra visual |
| `annual-comparative-statement-power-bi-template` | 8 | 30 | 13 | 43.3% | 17 | 8 | 13 | 0 | 0 | native-approx-only | 17 non-Zebra source visuals dropped |
| `inventory-power-bi-template` | 8 | 49 | 13 | 26.5% | 36 | 8 | 13 | 0 | 0 | native-approx-only | 36 non-Zebra source visuals dropped |
| `working-capital-in-power-bi-template` | 5 | 40 | 12 | 30.0% | 28 | 5 | 12 | 0 | 0 | native-approx-only | 28 non-Zebra source visuals dropped |
| `income-statement-dashboard-in-power-bi` | 11 | 63 | 10 | 15.9% | 53 | 9 | 10 | 0 | 0 | not-template-fidelity | 2 source pages have no mined Zebra visual |
| `price-volume-mix-analysis-power-bi-template` | 8 | 41 | 9 | 22.0% | 32 | 7 | 9 | 0 | 0 | not-template-fidelity | 1 source pages have no mined Zebra visual |
| `daily-sales-flash-power-bi-dashboard` | 4 | 66 | 8 | 12.1% | 58 | 4 | 8 | 0 | 0 | native-approx-only | 58 non-Zebra source visuals dropped |
| `cost-benefit-analysis-power-bi-template` | 5 | 12 | 7 | 58.3% | 5 | 5 | 7 | 0 | 0 | native-approx-only | 5 non-Zebra source visuals dropped |

## Implication

Use this path only as `native-approx`. A reviewable Zebra-fidelity lab needs to
start from full `Report/Layout`, preserve non-Zebra page furniture, and keep the
Zebra visual packages/settings intact. An RW production dashboard should instead
lift selected Zebra patterns into purpose-built native pages with their own QA
screenshots.
