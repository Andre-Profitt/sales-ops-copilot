# Power Automate Flow Runbook — Sales Ops Brief → Teams Self-Chat

Wire a Power Automate cloud flow that posts a Teams self-chat notification every time a new HTML file lands in `OneDrive/Sales Ops Briefs/`.

## Why this exists

SimCorp Conditional Access blocks personal-app `Chat.ReadWrite` token issuance (verified 2026-04-28: `AADSTS53003` even with the standard MS Graph CLI public client). Andre has no IT permission to register a tenant app. Workaround: a Power Automate flow Andre creates in his own tenant context — runs delegated as him, full audit trail, IT-clean. Standard connectors only — no Premium needed.

## Prerequisites

- M365 E5 license (`SPE_E5`) — already true. Includes Power Automate Standard tier.
- `FLOW_FREE` SKU — already provisioned.
- OneDrive for Business sync working — confirmed at `~/Library/CloudStorage/OneDrive-SimCorp/`.
- Folder `Sales Ops Briefs/` exists at the OneDrive root (created by `scripts/test_flow.py` if missing).
- Brief CLI drops files at `~/Library/CloudStorage/OneDrive-SimCorp/Sales Ops Briefs/YYYY-MM-DD.html` (parallel agent owns this).

## Click-path (5 minutes)

1. Open `https://make.powerautomate.com` in a browser. Sign in as `apro@simcorp.com`. Confirm the environment selector (top-right) shows the SimCorp tenant.
2. Left nav: **Create** → **Automated cloud flow**.
3. **Flow name:** `Sales Ops Brief → Teams Self-Chat`. Skip the trigger picker (click **Skip** at the bottom — gives the full new-designer experience).
4. Click the **+** in the designer → **Add a trigger**. Search `OneDrive for Business`. Select connector **OneDrive for Business** (icon: blue cloud, "By: Microsoft"). Pick trigger **When a file is created**.
5. Sign in to the OneDrive for Business connection when prompted (uses `apro@simcorp.com` — same account, no extra creds).
6. Configure trigger:
   - **Folder:** click the folder icon, navigate to `/Sales Ops Briefs` (root-level folder). If it does not appear, run `python3 scripts/test_flow.py` once to create it, then refresh the picker.
   - **Include subfolders:** `No`
   - Leave **Infer Content Type** and **Number of files to return** at defaults.
7. Click **+ New step** below the trigger → **Add an action**. Search `Teams`. Select connector **Microsoft Teams**. Pick action **Post message in a chat or channel**.
8. Sign in to the Teams connection if prompted.
9. Configure action:
   - **Post as:** `User`
   - **Post in:** `Chat with Flow bot`
   - **Recipient:** `apro@simcorp.com` (this is the "chat with self" target — the Flow bot DMs you in your own self-chat thread)
   - **Message:** paste the block below (use the dynamic-content lightning-bolt to insert `File name with extension` and `Web url` from the trigger's outputs):

   ```
   📊 Sales Ops Brief — @{triggerOutputs()?['body/Name']}

   File: @{triggerOutputs()?['body/Name']}
   Open: @{triggerOutputs()?['body/{Link}']}
   ```

   In the new designer, you do NOT type the `@{...}` expressions by hand — click the lightning-bolt next to the **Message** field and pick:
   - `File name with extension` (renders as `File name`) — for both the headline and the File: line
   - `Link to file` (the `{Link}` property — renders as a clickable web URL) — for the Open: line

10. Top-right: **Save**. Confirm the flow card now shows **On**.
11. Rename if needed: top breadcrumb → click flow name → confirm `Sales Ops Brief → Teams Self-Chat`.

That's it. Trigger polls OneDrive every ~60s; Teams post lands in the chat-with-self thread (top of the chat list, your own name).

## Test

```bash
cd ~/code/apps/sales-ops-copilot
python3 scripts/test_flow.py
```

Wait up to 60s. Check Teams → chat with self. You should see the Flow bot post with filename + clickable link. Then clean up:

```bash
python3 scripts/test_flow.py --cleanup
```

## Disable / delete

- **Disable** (keeps the flow definition): `make.powerautomate.com` → **My flows** → row → **Turn off**.
- **Delete**: same row → **...** → **Delete**.
- **Pause notifications without deleting** (e.g. on PTO): **Turn off** for the duration.

## Troubleshooting

**Flow doesn't fire**

- Standard polling interval is ~1 min for E5; can stretch to 15 min on Free tier. If you're on `FLOW_FREE` only (no Premium), the trigger may take up to 15 min — don't panic at 90s.
- `make.powerautomate.com` → **My flows** → click flow → **Run history**. If empty, trigger isn't seeing the file. Verify the folder path in the trigger config matches `/Sales Ops Briefs` (no `~` , no leading `/Library/...`).
- File must be **fully written** before the connector polls. Brief CLI writes `.tmp` then `os.replace` (atomic) — that's correct. Don't write the final filename until the bytes are flushed.
- Trigger condition customizations: settings tab on the trigger card → **Trigger conditions** must be empty (or correctly filter `endsWith(...,'.html')` — if you add a filter and it's wrong, nothing fires). See [Troubleshoot Power Automate trigger issues](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot#trigger-not-firing).

**Teams post is empty / shows "null"**

- Dynamic-content tokens were typed manually instead of inserted via the lightning-bolt. Delete the message body, re-add tokens via the picker. Save. Re-test.
- `body/{Link}` token doesn't appear in the picker for some tenants — alternative tokens that work: `Web url`, or `File link`. Pick whichever your designer surfaces.

**Link is broken / opens 404**

- OneDrive `Web url` requires the user to be signed into the same OneDrive — works for self-chat, breaks if forwarded. Acceptable for this use case.
- If you want a "always-works" link, swap to **Get file metadata using path** (OneDrive for Business action, Standard) and use its `Web url` output instead of the trigger's.

## Compliance note

Flow runs delegated as `apro@simcorp.com`, in the SimCorp tenant, with full Power Automate run-history audit trail. No app registration, no service account, no Graph token. IT-clean per Group Compliance whitelist (2026-04-28).

## References (Microsoft Learn)

- Send a message in Teams using Power Automate — [https://learn.microsoft.com/power-automate/teams/send-a-message-in-teams](https://learn.microsoft.com/power-automate/teams/send-a-message-in-teams)
- OneDrive for Business connector reference (Standard tier confirmed) — [https://learn.microsoft.com/connectors/onedriveforbusiness/](https://learn.microsoft.com/connectors/onedriveforbusiness/)
- Standard connectors list — [https://learn.microsoft.com/connectors/connector-reference/connector-reference-standard-connectors](https://learn.microsoft.com/connectors/connector-reference/connector-reference-standard-connectors)
- Troubleshoot trigger issues — [https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot](https://learn.microsoft.com/troubleshoot/power-platform/power-automate/flow-run-issues/triggers-troubleshoot)
- Power Automate licensing (Standard vs Premium entitlements) — [https://learn.microsoft.com/power-platform/admin/power-automate-licensing/types](https://learn.microsoft.com/power-platform/admin/power-automate-licensing/types)
