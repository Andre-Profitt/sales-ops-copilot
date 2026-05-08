# May 2026 Visual Gate Findings

Date: 2026-05-01

Source: `state/2026-Q2/__regional__/publish_gate/regional_publish_gate.json`

## Current Status

All 9 regional decks still pass the publish gate after adding visual eligibility checks.

The new checks are not cosmetic. They test whether the proposed visual has enough data shape to make sense:

- Waterfall: closed-lost must be negative.
- Scatter/Bubble: both axes need at least two distinct nonzero-ish values.
- Timeline/Gantt: dates need real spread.
- Action register: generic repeated due dates must not become a Gantt.

## Findings

| Visual gate | Finding | Template implication |
|---|---|---|
| Waterfall sign | Passed for every region. Closed-lost is now negative in the bridge source. | Keep Waterfall available for movement/QTD views. |
| Action cadence | Every region has action due dates collapsed to the same generic date in the current action source. | Do not use a Gantt for generic action slides. Use a May decision register table until true milestone dates exist. |
| Renewal timeline | Most regions have enough renewal close-date spread; Adam Steinhouse has only `2026-12-31`. | Renewal timeline can be conditional by region. Adam should stay table-only. |
| Scatter/Bubble risk | Most regions have enough probability and ARR spread. Patrick Gaughan has only one distinct ARR value in the Q2 readiness source, making a risk scatter weak. | Scatter should be conditional. Use risk table for Patrick unless a better y-axis is introduced, such as age, push count, or risk score. |
| Dense tables | Current publish gate still verifies table-image slides, object size, native-table removal, forbidden text, and internal/test row filters. | Keep table-image lane as the production table path until a stable named think-cell table donor is proven. |

## Implemented Controls

- `config/connected_thinkcell_factory.jesper_apac.json` now carries `primary_visual`, `fallback_visual`, and `visual_gate` metadata for the key visual-risk objects.
- `scripts/validate_connected_factory_spec.py` validates visual-gate structure and hard workbook failures.
- `scripts/run_regional_deck_publish_gate.py` evaluates visual gates during regional publish checks and records per-director metrics.
- Regenerated connected factory specs/workbooks for all 9 regions.
- Re-ran the regional publish gate; all 9 passed.

## Next Template Improvements

1. Add a director-facing title map so slide titles are operating decisions, not worksheet/object descriptions.
2. Split the template into two assets:
   - engineering/wiring scaffold
   - director-facing presentation shell
3. Add conditional visual selection in the build layer:
   - table-only when timeline dates collapse
   - table-only when scatter axes collapse
   - bar/table fallback when Mekko matrix is sparse
4. Move action slides to a decision-register default across regions.

