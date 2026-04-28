#!/bin/bash
# Daily wrapper for sales-ops-copilot — invoked by launchd at 07:00 local time.
# Activates venv, runs brief.py, exits.
# Logs go to ~/Library/Logs/sales-ops-brief.log via launchd plist redirection.

set -uo pipefail

PROJECT_DIR="$HOME/code/apps/sales-ops-copilot"
cd "$PROJECT_DIR" || { echo "[$(date)] cd failed: $PROJECT_DIR"; exit 1; }

# Activate venv
# shellcheck disable=SC1091
source .venv/bin/activate || { echo "[$(date)] venv activation failed"; exit 1; }

echo "==================== $(date) ===================="
echo "Running sales-ops-copilot daily brief..."

# Run the brief; captures both stdout and stderr to the launchd log
python3 scripts/brief.py
RC=$?

if [[ $RC -eq 0 ]]; then
  echo "[$(date)] brief.py succeeded"
else
  echo "[$(date)] brief.py failed with rc=$RC"
fi

exit $RC
