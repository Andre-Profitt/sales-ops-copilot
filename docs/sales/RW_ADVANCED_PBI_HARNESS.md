# RW Advanced Power BI Harness

The current report looks basic because the repo can generate valid PBIR, but it
does not yet have a serious Desktop-to-code loop for advanced visual finish.
This harness adds that missing loop.

## What The Harness Does

`scripts/sales/rw_dashboard_harness.py` gives us five practical commands:

```bash
python3 -m scripts.sales.rw_dashboard_harness snapshot --source live --label before_rag
python3 -m scripts.sales.rw_dashboard_harness inventory --source desktop --page "What Changed"
python3 -m scripts.sales.rw_dashboard_harness audit --source desktop
python3 -m scripts.sales.rw_dashboard_harness diff --before output/rw_dashboard_harness/snapshots/before_rag.report.json --after-desktop --emit-candidates
python3 -m scripts.sales.rw_dashboard_harness extract --source desktop --page "What Changed" --name e337 --objects-only
```

Outputs go to `output/rw_dashboard_harness/`, which is treated as generated
working output.

## Workflow

1. Regenerate/open the Desktop PBIP:

```bash
python3 -m scripts.sales.rw_pbi_desktop_lab
python3 -m scripts.sales.rw_pbi_desktop_lab --launch
```

2. Snapshot the live report before changing a visual:

```bash
python3 -m scripts.sales.rw_dashboard_harness snapshot --source live --label before_rag_card
```

3. In Power BI Desktop, edit one representative visual. For the first pass, use
   a `What Changed` At Risk card and make it match the HTML mockup:

- tint `#fee`
- accent/border `#c33`
- larger primary value
- smaller gray label/secondary line

4. Save the PBIP in Desktop.

5. Diff the saved Desktop report against the pre-edit snapshot:

```bash
python3 -m scripts.sales.rw_dashboard_harness diff \
  --before output/rw_dashboard_harness/snapshots/before_rag_card.report.json \
  --after-desktop \
  --emit-candidates
```

6. The harness writes candidate files under
   `output/rw_dashboard_harness/candidates/<timestamp>/`:

- full edited visualContainer JSON
- isolated `singleVisual.objects` JSON
- a README summarizing visual type, title, fields, and changed keys

7. Promote the captured object shape into:

- `scripts/sales/_pbir_shapes.py`
- `scripts/sales/_pbir_helpers.py`
- the relevant page composer

8. Rebuild and validate:

```bash
python3 -m scripts.sales.rw_compose_what_changed
python3 -m scripts.sales.rw_validate --live
```

## Why This Is Better

The old loop was: guess PBIR JSON, push, eyeball, repeat.

The new loop is: Desktop authors the exact renderer-valid shape, the harness
diffs the saved PBIP, then code generalizes the proven shape across the report.

That is how we get from basic cards to advanced Power BI finish without
hand-rolling undocumented `singleVisual.objects` blocks.

## First Capture Targets

- RAG card tint/accent/title/value/secondary-line shape.
- Combined count plus ARR card shape, if Desktop can represent it cleanly.
- Table conditional formatting for threshold-crossable cells.
- Matrix header/row formatting for the Forecast Stage x Motion grid.

## Visible RAG Fallback

Power BI may accept card `background` / `border` objects in `report.json` but
still render a stale or visually unchanged card in Desktop/Service. For status
bands that must visibly change, use a `basicShape` rectangle behind the card
pair as the panel treatment, then keep card-internal objects for typography.

The first implementation is on `What Changed`:

- three tinted `basicShape` panels behind At Risk / Watch / Healthy
- six count/ARR cards with RAG object blocks
- live page now has 18 visuals instead of 15

## Guardrail

ARR and ACV still never blend. ARR is Land + Expand only. ACV is Renewal only.
`Total Open Pipeline Value` remains the only explicitly labeled cross-motion
measure.
