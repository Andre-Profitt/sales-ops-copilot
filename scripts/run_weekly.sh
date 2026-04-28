#!/bin/bash
# Weekly wrapper for sales-ops-copilot — invoked by launchd Sundays at 07:00.
# Activates venv, runs weekly_brief.py with OneDrive publish, exits.
# Pairs with com.simcorp.sales-ops-copilot.weekly.plist.

set -uo pipefail

PROJECT_DIR="$HOME/code/apps/sales-ops-copilot"
cd "$PROJECT_DIR" || { echo "[$(date)] cd failed: $PROJECT_DIR"; exit 1; }

# shellcheck disable=SC1091
source .venv/bin/activate || { echo "[$(date)] venv activation failed"; exit 1; }

echo "==================== $(date) ===================="
echo "Running sales-ops-copilot weekly rollup..."

python3 scripts/weekly_brief.py --onedrive-publish
RC=$?

if [[ $RC -eq 0 ]]; then
  echo "[$(date)] weekly_brief.py succeeded"
else
  echo "[$(date)] weekly_brief.py failed with rc=$RC"
fi

exit $RC
