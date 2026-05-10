# RW Cross-Graph Upgrade Target Plan

Generated: `2026-05-10T21:54:50Z`

This compares three graphs: Zebra template/visual grammar, the live RW Power BI artifact graph, and the RW KPI coverage graph. The target is not more cosmetic styling; it is a better executive operating system with Zebra-grade scenario, variance, and bridge semantics.

## Readout

- Live PBI graph verdict: `needs_source_or_model_work`
- Live PBI footprint: `7` pages, `126` visuals
- PBI cleanup counts: `{'info': 0, 'low': 0, 'medium': 5, 'high': 4, 'critical': 0}`
- Zebra mined visual corpus: `360` visuals
- RW KPI surface: `25` clean out of `31` KPIs
- Target plan: `2` P0, `4` P1, `2` P2

## Core Graph Signals

| Signal | Evidence | Meaning |
| --- | --- | --- |
| `bridge_gap` | Live PBI has 0 native waterfall/bridge visuals; Zebra corpus has 140/360 waterfall visuals. | RW pages are not yet using Zebra's bridge/decomposition grammar for executive variance stories. |
| `card_weight` | Live PBI card share is 34/126; Zebra card share is 74/360. | Cards are acceptable for a KPI spine, but the target state should move more meaning into variance tables and bridges. |
| `ibcs_table_base` | Live PBI already has 16 native table/matrix visuals and Zebra has 146 table visuals. | The native tableEx path is the right base; the next lift is scenario columns, variance deltas, and action-ledger ordering. |

## Zebra Patterns To Transfer

| Pattern | Evidence | RW application |
| --- | --- | --- |
| `scenario_variance_columns` | Zebra top comparison keys include actual, previousYear, plan, forecast, actual-plan, actual-previousYear, and variance-percent columns. | Forecast, Growth Mix, Renewals, and Scorecard need AC/PL/PY/FC-style measures where source data supports them. |
| `ibcs_table_ordering` | Zebra Tables -> tableEx/pivotTable ordered Category/Group, AC, PY, PL, FC, then synthesized delta and delta % columns. | Make variance tables the primary diagnostic surface, not secondary tables below KPI cards. |
| `waterfall_bridge` | Zebra Waterfall -> native waterfallChart where Category is axis and AC/bridge measure is Y. | Use bridge visuals for Forecast gap, Renewal base movement, and Growth contribution decomposition. |
| `neutral_kpi_tile` | Zebra Cards -> textbox header + value card + variance card composite; keep AC primary and PY/PL/FC comparator in corner. | Keep KPI cards neutral and compact; reserve color for thin accents, variance arrows, or RAG text. |
| `static_furniture` | Textboxes/shapes near each visual are normalized and preserved as page section furniture, not dropped. | Retain section headers and furniture as layout structure, but avoid decorative card stacks. |

## Ranked Upgrade Opportunities

### 1. Forecast — `forecast_scenario_spine` (P0)

- Owner lane: data model + BI surface
- Zebra pattern: `scenario_variance_columns + waterfall_bridge`
- Target state: Forecast becomes a scenario spine: actual/won ARR, open value, target/plan, submitted forecast, coverage gap, and forecast accuracy are shown as variance table plus bridge, not proxy cards.

**Graph evidence**
- PBI graph: Forecast has high cleanup findings for pipeline coverage and forecast accuracy.
- KPI graph: pipeline_coverage_3x status is surfaced_partial.
- KPI graph: forecast_accuracy status is surfaced_partial.
- Zebra graph: AC/PL/FC scenario pairings and synthesized variance columns are core patterns.

**Data/model work**
- Stage a quota/target denominator and create `Pipeline Coverage Ratio`.
- Stage ForecastingItem or snapshot history for true submitted-forecast accuracy.
- Add forecast-transition date role before adding movement-period slicers.

**BI surface work**
- Replace proxy-first slip cards with an AC/PL/FC variance table.
- Add a Forecast gap bridge: plan/quota -> closed won ARR -> open value -> remaining gap.
- Keep `Total Open Pipeline Value` visibly labeled ARR+ACV when used cross-motion.

**Acceptance**
- Forecast page has zero high data-surface findings.
- `Forecast Accuracy` and `Pipeline Coverage Ratio` are real measures, not proxy labels.
- Visual QA, unit policy, metric basis, and semantic-filter gates remain clear at high severity.

### 2. Growth Mix — `growth_mix_trusted_segmentation` (P0)

- Owner lane: source data + BI surface
- Zebra pattern: `variance_table + waterfall_bridge`
- Target state: Growth Mix explains contribution, not just values: Land, Expand, Partner, Axioma, SaaS, PS attach, Synergy, and one-off revenue become a governed mix matrix and contribution bridge.

**Graph evidence**
- PBI graph: Growth Mix has a high finding for Synergy deals won.
- KPI graph: synergy_deals_won status is surfaced_partial.
- KPI graph: synergy_deals_pipe status is partial_data_or_measure_gap.
- Zebra graph: variance tables and bridge charts are the dominant pattern for explaining mix shifts.

**Data/model work**
- Stage a trusted Synergy flag for won and open pipeline.
- Identify and stage one-off/non-recurring revenue source fields.
- Keep Land and Expand written out and separate from Renewal ACV.

**BI surface work**
- Add Synergy won/open rows to the strategic mix table once the flag exists.
- Add a contribution bridge by growth source and motion.
- Move proxy Land won count out of the Synergy slot once real Synergy measures exist.

**Acceptance**
- `synergy_deals_won` and `synergy_deals_pipe` are no longer proxy/model gaps.
- Growth Mix has explicit source/motion labels and no ARR/Renewal ACV blending.
- The page still passes visual QA with zero medium+ findings.

### 3. Renewals — `renewal_base_bridge` (P1)

- Owner lane: semantic model + BI surface
- Zebra pattern: `waterfall_bridge + variance_table`
- Target state: Renewals becomes an active-base bridge: active-base ARR -> expiring base -> at-risk base -> won/lost renewal ACV -> retained base and indexation/uplift. Renewal ACV and active-base ARR stay separated.

**Graph evidence**
- PBI graph: Renewals is visually clean but still uses only one chart and one detail table.
- KPI graph: indexation_arr_growth status is surfaced_partial.
- Zebra graph: 140 waterfall visuals in the corpus indicate bridge/decomposition is a first-class executive pattern.

**Data/model work**
- Stage indexation/uplift or contract price-change fields.
- Verify active Asset/Subscription base grain and renewal linkage.
- Add renewal-base variance measures without mixing Renewal ACV into ARR.

**BI surface work**
- Replace the single at-risk bar emphasis with an active-base waterfall/bridge.
- Keep the account detail ledger as drill path, not as the primary story.
- Add an indexation/uplift row only after source data is real.

**Acceptance**
- `indexation_arr_growth` no longer shows missing source data.
- Renewals has an explicit bridge visual or bridge-equivalent native table.
- Renewal ACV and active-base ARR labels remain visibly distinct.

### 4. Renewals / Product Mix — `product_segment_retention_churn` (P1)

- Owner lane: semantic model + BI surface
- Zebra pattern: `scenario_variance_columns + ibcs_table_ordering + heatmap matrix`
- Target state: Build both views: (1) product x segment x region mix heatmaps for current exposure and risk, and (2) installed-base churn/retention by account-product-period: prior active-base ARR, current active-base ARR, retained ARR, churn/downsell, expansion, cross-sell, and product churn.

**Graph evidence**
- Current semantic model has product grain on `f_asset_line_item`: product family, area, type, account, region, industry, ARR, and asset end date.
- PBI graph: Renewals already exposes product family in the active-base detail ledger, but not as a product x segment x region heatmap or retention bridge.
- Salesforce gap probe identified OpportunityLineItem as the likely source for new-business product/revenue-stream mix.
- Zebra graph: scenario variance columns map naturally to prior active base versus current active base by product.

**Data/model work**
- Create an effective-dated or snapshot fact for active-base ARR by account-product-period.
- Use asset start/end dates to reconstruct prior/current base only if historical rows are not overwritten; otherwise persist monthly snapshots.
- Define segment explicitly: industry, account type, named segment, or another governed account attribute.
- Stage OpportunityLineItem later for Land + Expand product mix; do not use renewal asset base as new-business product pipeline.

**BI surface work**
- Product heatmap: Product Family/Product Area x Region with active-base ARR, expiring ARR, at-risk ARR, and risk percentage.
- Product heatmap: Product Family/Product Area x Segment once segment is governed.
- Churn view: prior versus current active-base ARR by account-product-period, with retained/churn/downsell/expansion/cross-sell classification.
- Add account-product churn ledger: prior product ARR, current product ARR, delta, churn classification, renewal date.
- Keep this as active-base ARR retention, not Renewal ACV and not Land + Expand ARR.

**Acceptance**
- Product heatmap and churn view both exist; neither is substituted for the other.
- Gross retention and net retention by account-product are computed from prior/current active-base ARR.
- Product churn/downsell/expansion/cross-sell classifications are deterministic and tested.
- All visuals label basis as active-base ARR; Renewal ACV remains separate.
- Heatmap/matrix output passes visual QA and metric-basis gates.

### 5. Stage Hygiene / What Changed / Forecast — `movement_date_roles` (P1)

- Owner lane: semantic model
- Zebra pattern: `role_playing_dates`
- Target state: Movement pages can slice stage and forecast changes by transition date without confusing that with close-period cohorts.

**Graph evidence**
- PBI graph: report-level cleanup has medium findings for stage and forecast transition-date roles.
- Zebra schema graph: role-playing date dimensions are a mined architecture pattern.
- Current pages use Close FQ as cohort context, but movement analytics need transition-period context.

**Data/model work**
- Add direct calendar roles for `f_stage_transition.transition_at` and `f_forecast_transition.transition_at`.
- Keep Close FQ slicers on executive pages; add movement-period controls only where page contract allows.
- Document date-role basis in visible labels and contracts.

**BI surface work**
- Add controlled movement-period views after model roles exist.
- Use transition-date roles for Stage Hygiene and What Changed movement ledgers.

**Acceptance**
- Semantic-filter audit has zero medium transition-date findings.
- No page uses a movement-period slicer before the model role exists.

### 6. VP Ops Scorecard — `scorecard_driver_tree` (P1)

- Owner lane: BI surface
- Zebra pattern: `kpi_tile + variance_table + bridge`
- Target state: The scorecard becomes a driver tree: headline outcome, gap-to-plan, exception lane, stage lane, renewal lane, and 7-day movement lane. Cards summarize; tables/bridge explain.

**Graph evidence**
- PBI graph: VP Ops Scorecard has 8 cards, 12 shapes, and no cleanup findings.
- Enterprise graph: VP Ops Scorecard is 91% Zebra-native, lower than the other executive pages.
- Zebra graph: KPI cards are a spine; variance tables and bridges carry the explanation.

**Data/model work**
- Depends on Forecast plan/coverage and movement-date work for the strongest scorecard version.

**BI surface work**
- Reduce pure scorecard feel by making one primary variance/driver table the central artifact.
- Use neutral Zebra card treatment and explicit Land + Expand / Renewal ACV labels.
- Add navigation/drill targets from each lane to its detail tab.

**Acceptance**
- VP Ops Scorecard reaches 100% Zebra-native decision-visual coverage.
- The page has a visible driver path from headline to detail, not only metric tiles.

### 7. RW KPI Explorer — `explorer_contract_and_slice_dice` (P2)

- Owner lane: governance + BI surface
- Zebra pattern: `kpi_dictionary + scenario_axis`
- Target state: Explorer becomes a governed analysis page with explicit safe slicers, KPI metadata, and separate ARR/Renewal ACV lanes.

**Graph evidence**
- PBI graph: RW KPI Explorer uses 17 measures but has no KPI contract.
- KPI graph: 31 canonical KPIs exist; 29 are placed on executive pages.
- Zebra graph: KPI metadata tables are a mined schema pattern across templates.

**Data/model work**
- Consider future `d_kpi` metadata table only after page contracts stabilize.
- Do not use a universal Motion slicer that contradicts DAX motion guardrails.

**BI surface work**
- Add an explorer contract documenting allowed slicers and non-executive status.
- Group explorer visuals into Land + Expand ARR, Renewal ACV, Stage, and Growth lanes.

**Acceptance**
- Explorer contract exists and is tested.
- Explorer remains free of `Total Open Pipeline Value` unless explicitly labeled cross-motion.

### 8. Zebra transfer framework — `expand_zebra_exemplar_library` (P2)

- Owner lane: transfer engineering
- Zebra pattern: `multi_template_pattern_mining`
- Target state: The transfer layer learns page archetypes from sales, SaaS, daily flash, PVM, and cost/benefit templates before broader rewrites.

**Graph evidence**
- Current transfer framework is grounded primarily in `sales-funnel-power-bi-template`.
- Zebra corpus has 20 templates and 360 mined Zebra visuals.
- RW Growth Mix and Renewals need patterns beyond the sales-funnel exemplar.

**Data/model work**
- No production model change required.

**BI surface work**
- Mine and compare `saas-sales-power-bi-dashboard-template`, `daily-sales-flash-power-bi-dashboard`, `price-volume-mix-analysis-power-bi-template`, and `cost-benefit-analysis-power-bi-template`.
- Extract reusable native patterns for variance tables, bridge charts, comments/annotations, and executive page furniture.

**Acceptance**
- A second and third Zebra exemplar produce DNA + native rebuild gates with zero custom leftovers.
- RW page helpers reference specific learned patterns, not generic Zebra lineage.

## Execution Sequence

1. Close P0 source/model blockers: quota/target, forecast snapshots, Synergy flag.
2. Add movement date roles so Stage/Forecast movement pages can support period analysis without abusing Close FQ.
3. Rebuild Forecast and Growth Mix with scenario variance tables and bridge/decomposition visuals.
4. Add product x segment x region active-base retention/churn heatmaps from asset snapshots or effective-dated asset rows.
5. Upgrade Renewals to an active-base bridge once indexation/uplift fields are staged.
6. Recompose VP Ops Scorecard as a driver tree after Forecast/Growth Mix have real measures.
7. Add an explicit explorer contract and mine additional Zebra templates for broader pattern transfer.

## Non-Targets

- Do not spend the next pass on color/card styling alone; visual QA is already clean.
- Do not force Zebra custom visuals through SimCorp restrictions; native transfer remains the path.
- Do not count proxy KPIs as finished executive metrics.
- Do not blend ARR and Renewal ACV. ARR is Land + Expand only; Renewal ACV is Renewal only. `Total Open Pipeline Value` remains the only labeled cross-motion value.
