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

# Run the brief; captures both stdout and stderr to the launchd log.
# --open auto-launches the rendered HTML in the default browser at 7am
# (Teams chat-with-self path is CA-blocked — see memory
# feedback_graph_cli_client_also_ca_blocked.md). Drop --open if the daily
# browser tab gets annoying; the .html file is still written either way.
# --onedrive-publish atomic-writes the HTML to OneDrive-SimCorp/Sales Ops
# Briefs/ so a Power Automate Flow can pick it up and post to Teams self-chat.
python3 scripts/brief.py --html --open --onedrive-publish
RC=$?

if [[ $RC -eq 0 ]]; then
  echo "[$(date)] brief.py succeeded"
else
  echo "[$(date)] brief.py failed with rc=$RC"
fi

exit $RC
