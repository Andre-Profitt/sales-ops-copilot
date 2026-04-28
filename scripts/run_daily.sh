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
#
# As of 2026-04-28 agent.py is the default — Microsoft Agent Framework wrapper
# around the same data-pull functions, output-equivalent to brief.py.
# brief.py remains the fallback (drop-in: swap `agent.py` → `brief.py`).
python3 scripts/agent.py --html --open --onedrive-publish
RC=$?

if [[ $RC -eq 0 ]]; then
  echo "[$(date)] agent.py succeeded"
else
  echo "[$(date)] agent.py failed with rc=$RC"
fi

# Memo-grade PDF for forwarding to directors. Lives in reports/ alongside the
# .md/.html (NOT published to OneDrive — Power Automate Flow watches .html).
TODAY="$(date +%Y-%m-%d)"
AGENT_MD="reports/agent-${TODAY}.md"
PDF_OUT="reports/${TODAY}.pdf"
if [[ -f "$AGENT_MD" ]]; then
  python3 scripts/brief_pdf.py "$AGENT_MD" "$PDF_OUT" --pdf \
    && echo "[$(date)] PDF: $PDF_OUT" \
    || echo "[$(date)] PDF render failed (non-fatal)"
fi

# Board-pack PowerPoint deck. Nice-to-have only — never fails the daemon.
# Runs only when the brief succeeded; OneDrive publish lets Power Automate
# pick up the .pptx for distribution.
if [[ $RC -eq 0 ]]; then
  python3 scripts/deck.py --onedrive-publish \
    && echo "[$(date)] deck: reports/deck-${TODAY}.pptx" \
    || echo "[$(date)] deck render failed (non-fatal)"
fi

exit $RC
