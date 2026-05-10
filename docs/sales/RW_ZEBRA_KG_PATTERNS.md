# RW Zebra KG — Patterns & Topology Findings

Source-of-truth synthesis of what the **439 DAX expressions** + **133 relationships** across **20 Zebra templates** taught us, and how those patterns inform RW measure authoring (PR2 onward).

Produced 2026-05-09 from:

- `data/zebra_kg/dax_patterns.json` (`rw_zebra_kg_dax_atlas.py`, commit `e553c5f`)
- `data/zebra_kg/topology_patterns.json` (`rw_zebra_kg_topology_atlas.py`, commit `bb824df`)
- Suggester smoke output (`rw_zebra_kg_suggest_dax.py`, commit `e0884cf`)

## Methodology

Per measure, we extract a feature signature from the DAX expression via 23 regex tags covering time-intelligence functions, aggregations, filter primitives, conditionals, variables, and lookups. Measures cluster by feature-set; clusters of ≤2 measures collapse into `pattern_misc`. Per-template topology classifies fact/dim tables, calendar/scenario dim presence, bidirectional and inactive relationships, and role-playing dimensions. The suggester scores patterns against an authoring intent string via keyword→tag mapping plus canonical-name and canonical-DAX text matches.

## Top 10 DAX patterns

| #   | Pattern                                                                | Measures | Templates | Canonical example                 |
| --- | ---------------------------------------------------------------------- | -------: | --------: | --------------------------------- |
| 1   | `pattern_no_features` (pure measure refs / arithmetic)                 |      128 |        20 | `Net New MRR`                     |
| 2   | `filter:calculate` (CALCULATE without other recognized features)       |       46 |        12 | `Downsell MRR`                    |
| 3   | `filter:calculate + time:date_add` (rolling-offset comparisons)        |       44 |        14 | `Customer Satisfaction PY`        |
| 4   | `cond:if + var` (conditional with variables)                           |       36 |         7 | `Comments measure all levels`     |
| 5   | `cond:if` (bare conditional logic)                                     |       26 |        10 | `Selected BU or Product Category` |
| 6   | `pattern_misc` (long-tail singletons)                                  |       23 |        15 | —                                 |
| 7   | `agg:sum + filter:calculate`                                           |       21 |         5 | `Pessimistic_Plans`               |
| 8   | `agg:sum` (bare SUM)                                                   |       20 |         8 | `Total Good Biscuits`             |
| 9   | `safe_ratio` (DIVIDE only)                                             |       18 |         5 | `Availability Loss Gross %`       |
| 10  | `agg:divide + filter:all + filter:calculate` (denominator-clear ratio) |       10 |         6 | `PnL OM AC`                       |

## Topology findings (20 templates)

| Signal                            |           Count | Implication for RW                                                                                                                                                                         |
| --------------------------------- | --------------: | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Templates with calendar dim       | **11/20 (55%)** | Zebra's mainline pattern is an explicit `Calendar` / `DateTableTemplate` join. RW currently has no explicit date dim. Adding one unlocks proper time intelligence + role-playing dates.    |
| Templates with scenario dim       |            1/20 | Scenario-as-dim is rare in Zebra; the flat measure-per-scenario approach (`Sales AC`, `Sales PY`) dominates. RW already follows this pattern.                                              |
| Templates with bidirectional rels |  **3/20 (15%)** | Zebra is conservative with bidirectional cross-filters — best-practice. RW should follow.                                                                                                  |
| Templates with role-playing dims  |      4/20 (20%) | Multi-date columns join the same dim via different FK columns (e.g., `OrderDate` and `ShipDate` both → `Calendar`). Inactive relationships + `USERELATIONSHIP()` is the validated pattern. |
| Total relationships               |             133 | —                                                                                                                                                                                          |
| Inactive relationships            |               7 | Confirms role-playing dim usage is real, not error noise.                                                                                                                                  |

## Adaptation guide for RW

### Time intelligence — prefer `DATEADD`, not `DATESINPERIOD`

The dominant time-intel pattern in Zebra (44 measures, 14 templates) is `CALCULATE + DATEADD` — rolling-offset comparisons (e.g., last quarter, prior year, month-over-month). Only 5 measures use `DATESINPERIOD`. PR2's new `*_7d` measures should follow the dominant idiom. Canonical shape:

```dax
-- Adapt the consolidated-financials canonical:
CALCULATE(
    [Closed Won ARR],
    DATEADD(d_calendar[Date], -7, DAY)
)
```

### Variance / YoY — use `SAMEPERIODLASTYEAR` for clean periods, `DATEADD` for arbitrary offsets

The `time:sameperiodlastyear + filter:calculate` cluster (separate from `date_add`) is the clean-PY-comparison pattern. For `Variance vs PY`, the suggester's top pick (`agg:divide + filter:allexcept + filter:calculate`) lifts a market-share denominator-clear shape from FMCG portfolio that's structurally what RW needs for any `*  YoY Pct` measure.

### Filter-with-predicate — the gate-violation idiom

For `Stage 3+ deals without Commercial Approval` and similar gate-violation measures, the `filter_calculate_predicate` cluster (`CALCULATE + FILTER + boolean AND` predicate, 4 measures, suggester top pick at score 15) is the structural template. Adapt:

```dax
-- Lift the HR headcount predicate skeleton to opportunity gate logic:
CALCULATE(
    SUM(f_opportunity[arr_org_ccy]),
    FILTER(
        f_opportunity,
        AND(
            f_opportunity[stage_name] IN { "3 - Engagement", "4 - Shortlisted",
                                            "5 - Preferred", "6 - Contracting" },
            OR(
                ISBLANK(f_opportunity[Stage_20_Approval__c]),
                f_opportunity[Stage_20_Approval__c] <> "Approved"
            )
        )
    )
)
```

### Cardinal-rule check for any new RW measure

Every PR2 measure must enforce `motion_type IN { "Land", "Expand" }` for ARR-side or `motion_type = "Renewal"` for ACV-side. Zebra templates don't enforce this — they're motion-agnostic — so the lift always _adds_ a motion filter on top of the canonical.

## Implications for PR2 — measure-by-measure authoring guidance

| PR2 measure                              | Lift from                                                                                            | Pattern                            | Adaptation notes                                                                                                                             |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `New Opps ARR 7d`                        | consolidated-financials `Comments (periods)` (DATESINPERIOD) **OR** dominant `DATEADD` shape         | `filter:calculate + time:date_add` | Use `DATEADD(d_calendar[Date], -7, DAY)` over `DATESINPERIOD`; filter `[is_new_in_period] = TRUE`; add `motion_type IN { "Land", "Expand" }` |
| `Closed Won ARR 7d`                      | Same shape as above                                                                                  | same                               | Replace `[is_new_in_period]` with `[is_closed] = TRUE && [stage_name] = "8 - Won"`                                                           |
| `Closed Lost ARR 7d`                     | Same                                                                                                 | same                               | Replace stage filter with `[stage_name] = "9 - Lost"` (or whatever RW uses for lost)                                                         |
| `Backward Moves ARR 7d`                  | f_stage_transition table — use the existing `Stage Moves ARR 7d` pattern (already in the live model) | `time:date_add` family             | Filter `[direction] = "backward"` on the existing measure's logic                                                                            |
| `Commercial Approval Gate Exception ARR` | hr-analytics `Headcount` (FILTER predicate)                                                          | `filter_calculate_predicate`       | Stage 3+ Land + ISBLANK or != "Approved" Stage_20_Approval\_\_c. Cite suggester intent 3 result.                                             |

Each of these should be authored with a TMDL comment block citing the pattern name + canonical Zebra source for review traceability:

```tmdl
measure 'New Opps ARR 7d' = ...
    /// Pattern: filter:calculate + time:date_add
    /// Lifted from: consolidated-financials-power-bi-template
    /// Cardinal rule: Land + Expand only (motion_type filter applied)
```

## Limitations

- **128 / 439 measures (29%) cluster as `pattern_no_features`** — pure measure references or simple arithmetic. The atlas can't help author these because they have no extractable structure. They're typically variance-by-subtraction (`[X] - [X PY]`) — straightforward, no skeleton needed.
- **23 measures in `pattern_misc`** are singletons or pairs. The suggester won't surface these reliably.
- **Adaptation rename map is small** — `_RW_RENAME_MAP` only covers the most common Zebra-template tables (Sales / Calendar / BusinessUnits / KPIs / etc.). Domain-specific names (Employees, Portfolio, Comments) pass through unchanged. The output is for review, not paste-into-TMDL.
- **No DAX dependency analysis yet** — the existing KG has `depends_on` edges between measures, but the atlas doesn't traverse them. PR4.1 could add transitive-dependency surfacing (e.g., "to lift `Customer Satisfaction PY`, you also need `Customer Satisfaction AC` which depends on `Customer Satisfaction Score`...").
- **No cross-template idiom strength signal** — a pattern that appears in 14 templates is more idiomatic than one that appears in 5, but the score doesn't yet weight by template breadth. PR4.1 could add this.

## How to use this

1. **Before authoring a new RW measure**, run:
   ```bash
   python3 -m scripts.sales.rw_zebra_kg_suggest_dax \
     --intent "<your intent string>" --top 3
   ```
2. Read the top-1 pattern's canonical DAX and the adapted version.
3. Hand-edit the adapted DAX for RW: cardinal-rule motion filter, RW-specific column names, RW-specific business logic (e.g., stage names).
4. Cite the pattern + source template in the TMDL comment.
5. Push via `rw_push_semantic_model.py` (after snapshotting the existing TMDL).

## Related artifacts

- Spec: `docs/superpowers/specs/2026-05-09-zebra-bi-knowledge-graph-design.md`
- Plan: `docs/superpowers/plans/2026-05-09-zebra-kg-pattern-atlas.md`
- DAX atlas script: `scripts/sales/rw_zebra_kg_dax_atlas.py`
- Topology atlas script: `scripts/sales/rw_zebra_kg_topology_atlas.py`
- Suggester: `scripts/sales/rw_zebra_kg_suggest_dax.py`
- Query CLI: `scripts/sales/rw_zebra_kg_query.py` — `--list-dax-patterns`, `--dax-pattern <name>`, `--topology <slug|summary>`
