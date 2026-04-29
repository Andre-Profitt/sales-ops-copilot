# Marketing & Lead Funnel — All 5 Widgets Empty (Manual Fix Required)

_Found 2026-04-28 by `dashboard_quality_audit`. Documented here because
the fix can't be done via the SF Analytics REST API._

## What's wrong

The 5 reports under `Marketing & Lead Funnel` (dashboard `01ZTb00000FxYbJMAV`)
shipped with `scope: user`. The running user `apro@simcorp.com` owns **0** of
the org's **53,148** Leads, so every widget renders empty.

| Report ID | Name | Scope | Owner result |
|---|---|---|---|
| `00OTb000008mw9xMAA` | Conversions by Source | `user` | 0 rows |
| `00OTb000008mw6jMAA` | Leads by Source | `user` | 0 rows |
| `00OTb000008mwBZMAY` | Stale Leads >2y | `user` | 0 rows |
| `00OTb000008mw8LMAQ` | Leads by Status | `user` | 0 rows |
| `00OTb000008mwDBMAY` | Lead Volume Trend | `user` | 0 rows |

## Why API won't fix it

The Salesforce Reports REST API for `LeadList` reports rejects every
broader scope value with HTTP 400 `is not a valid scope`:

- `organization` → rejected
- `everything` → rejected
- `all` → rejected
- ListView developer names (`All_Leads`, etc.) → rejected
- `userOrHierarchyFilter` overrides → JSON_PARSER_ERROR

Only `user` and `team` are accepted; `team` returns ~2 leads (apro's direct
reports), still useless.

## How to fix (Lightning UI)

1. Open each report:
   - https://simcorp.my.salesforce.com/00OTb000008mw9xMAA
   - https://simcorp.my.salesforce.com/00OTb000008mw6jMAA
   - https://simcorp.my.salesforce.com/00OTb000008mwBZMAY
   - https://simcorp.my.salesforce.com/00OTb000008mw8LMAQ
   - https://simcorp.my.salesforce.com/00OTb000008mwDBMAY
2. Click `Edit`.
3. In the Filters panel: `Show Me` ▸ `All Leads`.
4. `Save`.

Repeat for all 5 reports. Then refresh the Marketing dashboard
(`01ZTb00000FxYbJMAV`) — widgets should populate immediately.

## Alternative (if you want it scriptable later)

Rebuild the 5 reports against a custom Lead Report Type that has no
implicit owner-scoping. That requires a Setup→`Report Types` config
change (admin role) and is overkill for this.
