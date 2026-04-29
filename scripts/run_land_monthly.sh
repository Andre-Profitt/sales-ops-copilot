#!/usr/bin/env bash
# Monthly LAND deck pipeline — invoked by launchd
# (com.simcorp.sales-ops-copilot.land-monthly, fires Day=1 Hour=6).
#
# Pipeline (in order):
#   1. forecast_backtest.py     — 4-quarter stage-conversion forward rates
#   2. land_brief.py            — per-director trends.json + brief.md + land.xlsx
#   3. regional_memo.py         — per-region rollup memos
#   4. run_land_to_deck.py      — generate per-director PPTX (non-blocking)
#
# Steps 1-3 are critical and chained with &&. Step 4 hits the deck-gen
# Function App; if that endpoint is unreachable the pipeline still produces
# the ETL artifacts (trends + xlsx + memos), and the deck generation is
# logged separately for retry.

set -u
cd /Users/test/code/apps/sales-ops-copilot

PYTHON=/Users/test/code/apps/sales-ops-copilot/.venv/bin/python3
PERIOD="$(date +%Y)-Q$(echo "scale=0; ($(date +%-m)-1)/3+1" | bc)"
ENDPOINT="${LAND_DECK_ENDPOINT:-https://func-simcorp-deckgen-dev.azurewebsites.net}"
LOG_DIR=/Users/test/code/apps/sales-ops-copilot/state
DECK_LOG="$LOG_DIR/land-monthly-deck-gen.log"

echo "============================================================"
echo "Land monthly run @ $(date)  period=$PERIOD"
echo "============================================================"

# Steps 1-3: critical ETL + memo chain. Fail loud if any step fails.
"$PYTHON" scripts/forecast_backtest.py --quarters-back 4 \
  && "$PYTHON" scripts/land_brief.py --all-directors --period "$PERIOD" \
  && "$PYTHON" scripts/regional_memo.py --period "$PERIOD"
ETL_RC=$?

if [ "$ETL_RC" -ne 0 ]; then
  echo "ETL/memo chain failed (rc=$ETL_RC). Skipping deck generation." >&2
  exit "$ETL_RC"
fi

# Step 4: deck generation. Non-blocking — endpoint may be down,
# Foundry quota may be exhausted, etc. Always log to a separate file.
echo "----- Deck generation -----"
{
  echo "$(date) — Starting --all-directors deck generation against $ENDPOINT"
  "$PYTHON" scripts/run_land_to_deck.py \
    --all-directors \
    --period "$PERIOD" \
    --endpoint "$ENDPOINT" \
    --skip-regen
  DECK_RC=$?
  echo "$(date) — Deck generation finished rc=$DECK_RC"
} >> "$DECK_LOG" 2>&1

# Tail the log so the cron stdout shows what happened
tail -10 "$DECK_LOG"

# Exit 0 from the wrapper regardless of deck-gen rc — the ETL artifacts are
# the must-have; deck gen is best-effort. Operator monitors $DECK_LOG.
exit 0
