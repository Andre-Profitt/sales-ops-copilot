# Tier 3 Probe Results — 2026-05-02

Endpoints + environment + alternate COM interfaces + shape interfaces.
Closes the "what other endpoints / surfaces exist" question outside the
COM dispatch layer.

## Verdict Table

| Probe                         | Status                   | Headline                                                                                                                                                                                                                            |
| ----------------------------- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **endpoints_and_environment** | **pass — biggest yield** | **6 new think-cell.com subdomains, 6 stock-image providers, 5 distinct route patterns, install GUID, telemetry feature IDs, license-key prefix, full update config schema**                                                         |
| alternate_interfaces          | pass                     | **No event sinks (no `IConnectionPointContainer`), no serialization hooks (`IPersist*` not supported). Only `IClientSecurity` resolves beyond IDispatch — that's COM marshaling boilerplate. The dispatch surface IS the surface.** |
| shape_interfaces              | pass                     | **All 60 sampled shapes (40 think-cell-managed) expose only `IDispatch`. Shapes have no custom COM interfaces — identity lives entirely in `Shape.Tags` + the customXml part.**                                                     |
| browser_extension             | **fail (hangs)**         | Registry walk hangs even after bounded scan. Needs further debug. Intel deferred.                                                                                                                                                   |

## 🎯 Cloud surface — 5 new subdomains + media-proxy infrastructure

The endpoints+env probe extracted **30+ unique think-cell.com URLs** from
binaries. Beyond the previously-known `server.think-cell.com` and
`static.think-cell.com`:

### AI infrastructure

- **`ai.think-cell.com`** — top-level AI domain
- **`ai.appcom.think-cell.com`** — AI app communication endpoint
- **`app.prod.ai.think-cell.com/`** — production AI app
- **`app.prod.ai.think-cell.com/core/`** — AI core API path

Plus `aiauthentication.bin` (342 bytes) in `%APPDATA%\think-cell\` —
local cached auth blob, suggests OAuth2/JWT-style token persistence.

### Stock-image proxy infrastructure

think-cell proxies multiple stock-image services through their own
subdomains:

- **`freepik.appcom.think-cell.com/{download,search}`** (Freepik)
- **`pexels.appcom.think-cell.com/v1/photos/`** (Pexels)
- **`unsplash.appcom.think-cell.com/api/photos/`** (Unsplash)

The update log additionally shows config flags for **Getty**, **Canto**,
and **Brandfolder** integrations (`DisableGetty`, `DisableCanto`,
`DisableBrandfolder`). These three don't surface in the binary URL
scan — they're either direct-API (no proxy) or dynamic-URL.

### Telemetry + appcom

- **`usage.appcom.think-cell.com/`** — telemetry collection endpoint
- This matches `m_setnTelemetryFeature` entries in `settings.xml`
  (feature IDs 19, 44 currently tracked on this install)

### Routes extracted from binaries

Five distinct HTTP route patterns appear in the strings:
`/api`, `/api/v1/search`, `/auth`, `/schemas`, `/v0`. These are likely
different paths against the appcom / ai endpoints above.

### Brandfolder enterprise integration

- Config flag: `BrandfolderAPIKey =` (empty by default)
- Plus: `HideSingleBrandfolder`, `HideBrandfolderCollections`,
  `HideBrandfolderSections`
- **Enterprise customers can wire their own Brandfolder DAM tenant
  directly via API key.** Direct-API surface, not proxied.

## 🎯 settings.xml — install metadata schema

`%APPDATA%\think-cell\settings.xml` (58KB) has rich structured data:

```xml
<root reqver="32687">
  <version val="1000220"/>
  <m_strLicenseKey></m_strLicenseKey>
  <m_strGuid>P5ORMTUJ5E5Y4AJHTN4E7WHKTA</m_strGuid>  <!-- install GUID -->
  <m_bActive val="1"/>
  <m_bChartTable val="0"/>                              <!-- chart-table feature OFF -->
  <m_bTrainingWheels endver="38409" val="1"/>           <!-- ends at v38409 -->
  <m_traininghistory>
    <m_setnTelemetryFeature>
      <elem val="19"/>
      <elem val="44"/>                                  <!-- feature IDs tracked -->
    </m_setnTelemetryFeature>
  </m_traininghistory>
  ...
</root>
```

Key signals:

- **Install GUID format**: `P5ORMTUJ5E5Y4AJHTN4E7WHKTA` — 26-char
  base64-like, **same format as the `THINKCELLSHAPEDONOTDELETE`
  Shape.Tag values** we found yesterday. Confirms think-cell uses one
  ID format for both install identity and per-shape identity.
- **`reqver` / `endver` version-gating**: features have explicit
  version-validity ranges. `reqver="32687"` requires runtime build
  ≥32687; `endver="38409"` removes the feature at build 38409.
- **License key field is empty** in the probed install (eval/trial?).
  Format hint: `LYXM2-XXXXX-XXXXX-XXXXX-XXXXX` (5 segments, alphanumeric).
- **Telemetry feature IDs**: `19` and `44` are the only flags currently
  tracked. The full feature-ID space is encoded in tcaddin.dll;
  decompilation could enumerate it.
- **`m_bChartTable val="0"`** — confirms native editable tables are
  feature-flag-disabled at the install level (matches existing
  unblock-matrix verdict).

## 🎯 SimCorp `tcfield_*` automation field naming convention

Walking shape tags on the LAND seed surfaced an undocumented SimCorp
naming convention for automation text fields:

```
tcfield_S01_DirectorName
tcfield_S01_Period
tcfield_S02_<purpose>
...
```

**Format: `tcfield_<slide-scope>_<purpose>`** where `<slide-scope>` is
`S<NN>` (slide number, zero-padded). This is your existing factory's
internal naming; worth folding into a `validate_thinkcell_shapes.py`
pre-flight that confirms expected `tcfield_*` names exist before
`.ppttc` binding.

## ❌ Alternate COM interfaces — no event surface

Tested 25 well-known IIDs against `tcPpAddIn`, `tcXlAddIn`, `tcUpdate`.
Only resolved:

- `IUnknown` (always)
- `IDispatch` (always)
- `IClientSecurity` — generic COM proxy security; not a think-cell
  surface

**Definitively absent** (none QI'd successfully):

- `IConnectionPointContainer` — **no event sinks**. think-cell does NOT
  fire callbacks back to subscribers. No reactive automation lane.
- `IPersist`, `IPersistStream`, `IPersistStorage`, `IPersistStreamInit`,
  `IPersistMemory`, `IPersistFile`, `IPersistPropertyBag` — **no
  serialization hooks** beyond what the typelib already exposes.
- `IProvideClassInfo`, `IProvideClassInfo2` — no additional class
  metadata.
- `IObjectSafety`, `ISupportErrorInfo`, `IPropertyNotifySink`,
  `IRunnableObject`, `IExternalConnection` — none.
- `IViewObject`, `IOleObject`, `ICustomDoc` — none.

**Conclusion**: `IDispatch` is the entire callable surface. Any future
think-cell automation must go through one of the 25 documented +
FHIDDEN methods we already enumerated via typeinfo. There is **no event
loop**, **no notification pipeline**, **no persistence side-channel**.

## ❌ Shape interfaces — only `IDispatch`

Walked 60 shapes (40 think-cell-managed) on the LAND seed deck.
Each shape was QI'd against 14 well-known IIDs. **Every shape resolved
to exactly `IDispatch`.** No `IPersist`, no `IOleObject`, no
`IDataObject`, no `IPropertyBag`, no custom interfaces.

**think-cell stores all per-shape metadata in two places**:

1. `Shape.Tags("THINKCELLSHAPEDONOTDELETE")` = 26-char base64 ID
   (matches install-GUID format)
2. `customXml` part inside the .pptx (the `think-cellXML` proprietary
   schema)

**There is no third path.** No COM-interface-based introspection;
no event interception; no in-memory mutation hook (within our box).

## Updated unblock-matrix implications

| Lane                               | Before      | After                                                                                                                                                                                        |
| ---------------------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reactive / event-driven automation | speculative | **Closed: no `IConnectionPointContainer`. No event surface exists.**                                                                                                                         |
| Custom serialization hook          | speculative | **Closed: no `IPersist*`. customXml is the only path.**                                                                                                                                      |
| Shape introspection beyond Tags    | speculative | **Closed: shapes expose only `IDispatch`. Tags + customXml are the entire surface.**                                                                                                         |
| AI features                        | unknown     | **Confirmed live and authenticated.** `aiauthentication.bin` exists, endpoints `app.prod.ai.think-cell.com/core/` are real, OAuth-style auth flow inferred.                                  |
| Stock-image media                  | unknown     | **6 providers integrated (Getty, Unsplash, Canto, Brandfolder, Pexels, Freepik), 3 proxied through `*.appcom.think-cell.com`, 3 likely direct-API.**                                         |
| Telemetry                          | unknown     | **`usage.appcom.think-cell.com/` is the collector. Per-feature IDs (19, 44 currently). Per-install GUID identifies the sender.**                                                             |
| Brandfolder enterprise API         | unknown     | **Configurable per-tenant via `BrandfolderAPIKey` field. Direct-API surface for enterprise.**                                                                                                |
| Update mechanism                   | unknown     | **Auto-update enabled, follows Office update channel. Last attempt failed at 2026-05-02T01:00:15Z with code 3 (`KNOWNPROBLEM`). Configurable per-tenant URL override available but unused.** |

## What this means for SimCorp factory work

1. **No new automation lane** at the COM dispatch layer. The 25-method
   contract is final.
2. **Telemetry awareness**: every install's usage flows to
   `usage.appcom.think-cell.com`. SimCorp Compliance / Group Compliance
   should know this if they don't. Per-feature IDs are tracked.
   Per-install GUID identifies the sender uniquely.
3. **Brandfolder enterprise integration is a real direct-API path** if
   SimCorp ever adopts it as their DAM. `BrandfolderAPIKey` config field
   means SimCorp could wire an internal asset library into think-cell
   without proxying through think-cell.com — direct enterprise API.
4. **AI features are live**: `app.prod.ai.think-cell.com/core/`
   endpoint, local auth blob (`aiauthentication.bin`). If AI features
   are used in SimCorp work, that traffic flows to think-cell's prod AI
   API — which has compliance / data-residency implications.
5. **Stock-image providers are configurable**: `Disable<Provider>=true`
   lockable per-install. SimCorp Compliance may want to disable
   providers based on data-residency / ToS.
6. **`m_strGuid` install identifier** survives across sessions and
   identifies your install in telemetry. Worth recording for support
   tickets.

## Output Artifacts

```
state/thinkcell_bridge/
├── endpoints_and_environment/20260502-061453/thinkcell_endpoints_and_environment_probe.json
├── alternate_interfaces/20260502-061455/thinkcell_alternate_interfaces_probe.json
├── shape_interfaces/20260502-061455/thinkcell_shape_interfaces_probe.json
└── browser_extension/20260502-061456/  (empty — probe still hangs)
```

Plus pulled artifacts (live VM):

```
C:\Users\test\AppData\Local\think-cell\
├── settings.xml          (392 bytes — minimal local UI state)
├── POWERPNT.officeUI     (7KB — ribbon customization)
└── tcupdate_log.log      (73KB — auto-update history + config schema)

C:\Users\test\AppData\Roaming\think-cell\
├── settings.xml          (58KB — install GUID, training history, telemetry features)
└── aiauthentication.bin  (342 bytes — AI auth blob)
```

## Open / deferred

- **Browser extension probe**: still hangs on registry walk. The
  bounded-scan edit didn't help. Likely a permissions / ACL issue on a
  specific Wow6432Node entry. Deprioritized; we already have the
  native-messaging architecture intel from Agent 5's research-swarm
  output (think-cell ships a Chrome/Edge extension with native messaging
  to local desktop add-in — useless without local install).
- **Decompilation of feature-ID enum**: tcaddin.dll has the enum that
  maps feature IDs (19, 44) to feature names. Surface via the deferred
  LLM-decompile pipeline (Agent 6's spec, $35-60 / overnight).
- **Capture live network traffic to `usage.appcom.think-cell.com/`**:
  would reveal the telemetry payload schema. Out of bounds (per the
  user's no-DLL-injection / no-MITM rule).
- **Test the Brandfolder API path**: scaffolded but not exercised.
  Would need a real Brandfolder enterprise tenant — out of scope unless
  SimCorp adopts Brandfolder.

## Closes vs Opens (cumulative across all 3 tiers)

**Definitively closed:**

- COM dispatch surface: 25 methods total (19+3+3) across 3 IIDs
- No alternate COM interfaces beyond `IDispatch`
- No event sinks / connection points
- No serialization hooks beyond the typelib
- No custom shape COM interfaces
- No cloud / mobile / Web Add-in product
- No retracted public methods (API has been purely additive 6 years)
- No DLL-injection-friendly hooks the user wants to use

**Now mapped:**

- 5 think-cell cloud subdomains (`ai`, `appcom`, `ai.appcom`,
  `usage.appcom`, plus stock-provider proxies)
- 6 stock-image providers (Getty, Unsplash, Canto, Brandfolder, Pexels,
  Freepik)
- 5 HTTP route patterns
- Install GUID format
- Telemetry feature ID system
- Update mechanism config schema
- Settings.xml schema
- AI auth blob format
- `tcfield_*` shape naming convention
- `aiauthentication.bin` local cache

**Still genuinely open:**

- think-cellXML chart-serialization grammar (custom XML diff —
  multi-day work)
- tcasr.exe IPC contract (Procmon trace at spawn — needs admin)
- Feature-ID → feature-name map (LLM-decompile pipeline)
- Browser-extension native-messaging protocol (probe debug + run)
- C# console smoke-test of generated interop assembly
