# Connected Factory - Jesper APAC 2026-Q2

Built artifact:

- `state/2026-Q2/Jesper-Tyrer/factory/connected/jesper_apac_connected_factory.xlsx`

Builder and gate:

```bash
.venv/bin/python scripts/build_connected_factory_workbook.py
.venv/bin/python scripts/validate_connected_factory_spec.py \
  --workbook state/2026-Q2/Jesper-Tyrer/factory/connected/jesper_apac_connected_factory.xlsx
.venv/bin/python scripts/audit_jesper_apac_intel_coverage.py \
  state/2026-Q2/Jesper-Tyrer/Jesper-Tyrer-LAND-2026-Q2.pptx \
  --json-output state/2026-Q2/Jesper-Tyrer/factory/jesper_apac_intel_coverage.json \
  --markdown-output state/2026-Q2/Jesper-Tyrer/factory/jesper_apac_intel_coverage.md
```

Smoke gate:

```bash
soffice --headless --convert-to xlsx \
  --outdir /tmp/connected_factory_smoke \
  state/2026-Q2/Jesper-Tyrer/factory/connected/jesper_apac_connected_factory.xlsx
```

What is connected now:

- Original APAC ETL workbook copied into `Raw_*` sheets.
- Current Q2 workbook/model extracts copied into `Raw_Current_*` sheets.
- Original APAC deck intelligence preserved in `Raw_Original_Intel`.
- Formula/model layer created for Q1 accountability, Q2 readiness, loss drivers, forecast category, renewals, owner coaching, pushed deals, pipeline creation, and action contract.
- 13 deck-facing output sheets created as `Out_*`.
- 13 Excel defined names created from the factory spec, one per deck-facing output range.
- `ThinkCell_Link_Map` maps every deck-facing output range to its Excel defined name, PowerPoint / think-cell object name, source tabs, model tabs, metric basis, and current publish path.
- `Audit_Checks` validates the preserved original sidecar facts and the waterfall closed-lost sign.

Important linkage status:

- The PowerPoint tables are currently generated native PPT tables from the workbook outputs during each factory rebuild.
- They are therefore rebuild-linked and auditable back to Excel, but they are not live Office-linked table objects inside the PPTX.
- The Excel side is now explicit enough for repeatable `Excel -> named range -> think-cell/PPT object` orchestration: use `ThinkCell_Link_Map` as the manifest and `rng_*` defined names as the range contract.
- Live think-cell/Excel table linking remains blocked until a real named data-backed think-cell table donor is proven without triggering PowerPoint repair.

Critical signs/gates:

- `Out_S05_PipelineMovement!E2` is negative closed-lost ARR.
- `Out_S13_Renewals` labels renewal value as ACV.
- Deck-facing output headers spell out `Unweighted ARR (EUR)` where ARR is unweighted; weighted ARR appears only where explicitly labeled.
- ARR and renewal ACV remain separate.
- `audit_jesper_apac_intel_coverage.py` passes the grouped original-APAC coverage rules: Q1 accountability, Q1 loss hygiene, original forecast mix, Q2 zero-activity baseline, Q2-Q3 risk triage, concentration spine, push discipline, approval scope, renewal reconciliation, and close-date guardrails.
- The factory spec still honestly marks think-cell table objects as blocked until a real named data-backed think-cell table donor is proven.

Next think-cell lane:

1. Use `ThinkCell_Link_Map` as the canonical manifest for object orchestration.
2. Wire chart/text objects from the named ranges in the connected workbook.
3. Keep native PPT tables for table slides until the named think-cell table donor exists.
4. Prove a donor table with sentinel Excel values, inspect the package, then update the seed builder to copy that intact table object graph.
5. Only after that, flip the table objects in `config/connected_thinkcell_factory.jesper_apac.json` from `blocked_no_named_table_donor` to supported.

Long-running polish runner:

```bash
.venv/bin/python scripts/run_director_deck_polish_loop.py \
  --director "Jesper Tyrer" \
  --period 2026-Q2 \
  --iterations 0 \
  --max-minutes 480 \
  --refresh-source-every 3 \
  --until-pass
```

Detached `tmux` launch:

```bash
tmux new-session -d -s jesper_apac_polish \
  'cd /Users/test/code/apps/sales-ops-copilot && \
   .venv/bin/python scripts/run_director_deck_polish_loop.py \
     --director "Jesper Tyrer" \
     --period 2026-Q2 \
     --iterations 0 \
     --max-minutes 480 \
     --refresh-source-every 3 \
     --until-pass \
     --sleep-seconds 300 \
     2>&1 | tee state/2026-Q2/Jesper-Tyrer/factory/longhaul/run.log'
```

Useful fast smoke:

```bash
.venv/bin/python scripts/run_director_deck_polish_loop.py \
  --iterations 1 \
  --skip-source \
  --skip-powerpoint-open \
  --sleep-seconds 0
```

Stop an overnight run by creating:

```bash
touch state/2026-Q2/Jesper-Tyrer/factory/longhaul/STOP
```

Longhaul reports land in:

- `state/2026-Q2/Jesper-Tyrer/factory/longhaul/latest_report.md`
- `state/2026-Q2/Jesper-Tyrer/factory/longhaul/summary.md`
- `state/2026-Q2/Jesper-Tyrer/factory/longhaul/iter-*/manifest.json`
