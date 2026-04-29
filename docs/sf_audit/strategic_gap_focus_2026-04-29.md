# Strategic gap focus — 2026-04-29

Focused remediation on six live dashboards:

- `CRO Cockpit` `01ZTb00000FxYZhMAN`
- `Forecast Accuracy & Pacing` `01ZTb00000FxYcvMAF`
- `Renewals Dashboard` `01ZTb00000FxYTFMA3`
- `Deal Desk Operations` `01ZTb00000FxYY5MAN`
- `Sales Rep Scorecard` `01ZTb00000FyJSAMA3`
- `Sales Directors Monthly Pipeline and Insights` `01ZTb00000FSP7hMAH`

## Landed

### CRO Cockpit

- Added `Forecast Volatility` using `FA · Slippage by Push Count` (`00OTb000008ngRJMAY`)
- Added `Stage Stickiness` using `Cockpit · Stage Stickiness · L+E` (`00OTb000008nUrZMAU`)
- Removed lower-signal historical region / win-loss trend tiles

### Forecast Accuracy & Pacing

- Added `Won ARR 8Q` (`00OTb000008njKLMAY`)
- Added `Won ARR YTD` (`00OTb000008njLxMAI`)
- Added `Won ARR LY SP` (`00OTb000008njNZMAY`)
- Added `Renewal ACV YTD` (`00OTb000008nhlbMAA`)
- Added `Renewal ACV LY SP` (`00OTb000008njPBMAY`)
- Renamed the headline metric to `Forecast Accuracy Proxy 8Q` to reflect the caveat in `docs/FORECAST_ACCURACY_CAVEAT.md`

### Renewals Dashboard

- Added `Expansion Pipeline by Account` (`00OTb000008njVdMAI`)
- Added `Adoption Score Distribution` (`00OTb000008njXFMAY`)
- Added `Stuck Renewals >30d` (`00OTb000008njYrMAI`)
- Removed `Lost This Quarter`, `Renewal ACV by Industry`, and duplicate `At-Risk Renewals`

### Deal Desk Operations

- Added `Discount Depth Pending` (`00OTb000008njSPMAY`)
- Replaced the historical `Approved YTD` tile with the live queue discount view

### Sales Rep Scorecard

- Added `Quota Attainment YTD` using `CRO · Quota Attainment YTD` (`00OTb000008nehFMAQ`)
- Preserved the dashboard’s custom 2-filter surface (`Region`, `Product Family`)
- Removed `Task Volume by Owner × Type · last 30d`

### Sales Directors Monthly

- Added `Top Deals at Risk (≥1M)` using `CRO · High-Value Deals at Risk (≥1M)` (`00OTb000008muo6MAA`)
- Added `Commercial Approval Queue` using `Commercial Approval Candidates` (`00OTb000008ekp7MAA`)
- Removed `Forecast Category Split` and `Top Accounts by Open ARR`

## QA

- `scripts/audit_dashboard_quality.py` reran successfully after a null-aggregate guard fix in `scripts/audit_dashboard_quality.py`
- All six target dashboards have the expected new widgets live
- All six target dashboards retained their intended filter surfaces
- New live report readout:
  - `FA · Won ARR 8Q` → `205` rows
  - `REN · Expansion Pipeline by Account` → `273` rows
  - `REN · Stuck Renewals >30d` → `124` rows
  - `DD · Discount Depth Pending` → `1` grouped bucket / `2` live source records behind it

## Residuals

- `CRO Cockpit` still lacks true `NRR` and true field-history-based forecast accuracy
- `Forecast Accuracy & Pacing` still lacks true cohort retention and a single unified bookings waterfall because ARR and Renewal ACV cannot be validly blended
- `Renewals Dashboard` still lacks true `NRR` and uplift-mix / downsell mix
- `Deal Desk Operations` discount depth is live but low-signal today because only `2` pending approvals have populated `ZIMIT_Discount__c`
- `Sales Directors Monthly` is materially more drill-list-forward, but it is still a `19`-component dashboard rather than the leaner end-state design
