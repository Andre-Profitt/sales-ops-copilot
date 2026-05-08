# Handoff — Personal `tc_toolkit` capability unlock

**Date:** 2026-05-02
**Audience:** A fresh Claude session picking up this work cold.
**Repo:** `~/code/apps/sales-ops-copilot/`
**Andre's framing:** Personal use, not SimCorp. Standard EULA caveats apply
(see "Caveats" below) but this is "use the install I already paid for from a
different process," not "ferry SimCorp client data through it."

## Read first (in this order)

1. `docs/thinkcell-corpus/MASTER_STATE.md` — canonical tracker for the broader investigation. Phase 0/0b/1-10 status, headline findings, open queue.
2. `docs/thinkcell-corpus/tier3-results-2026-05-02.md` — the 22-subdomain cloud topology + COM closure confirmation.
3. This file — the personal capability-unlock plan.

Run these one-liners first to confirm corpus state matches the assumptions below:

```bash
cd ~/code/apps/sales-ops-copilot

# Graph state — should be ~874 nodes / 4287 edges / 712 docs
jq '{nodes: .node_count, edges: .edge_count, docs: .document_count}' \
  state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json

# COM dispatch surface — 25 methods total, 7 FHIDDEN on tcPpAddIn
jq -r 'select(.kind=="COMMethod") | .label' \
  state/thinkcell_bridge/knowledge_graph/thinkcell_kg_nodes.jsonl | wc -l

# Verified strings in tcaddin.dll
jq '.verified_ascii, .verified_utf16' \
  state/thinkcell_bridge/auth_oauth_string_mining/verified_findings.json
```

If any of those don't return expected shape, **stop and read MASTER_STATE.md**
— state has drifted and this handoff may be stale.

## Goal

Build a personal Python package, `tc_toolkit`, that calls four think-cell
endpoint families using the install's own auth, providing:

1. **Stock image search** across Pexels / Unsplash / Freepik / Flaticon (the
   `*.appcom.think-cell.com` proxy farm). Pexels and Unsplash are free APIs
   anyway; **Freepik and Flaticon are normally paid**, accessed via the
   proxy under think-cell's server-held credentials.
2. **Chat-completions API** at `app.prod.ai.think-cell.com/core/`. OpenAI
   Chat Completions schema (`messages` / `content` / `role` JSON keys
   verified in tcaddin.dll). GPT-4-class model behind it (probably; not
   100% verified). Bounded by token's `quota` field.
3. **think-cellXML schema validator** at `schemas.think-cell.com/api`
   (POST allowed per OPTIONS — uncharacterized payload, almost certainly a
   validation endpoint).
4. **Local `.ppttc` rendering as a service** via the bundled `tcserver.exe`
   at `C:\Program Files (x86)\think-cell\tcserver.exe`. Currently NOT
   running; lazy-spawned. 5 routes: `/api`, `/api/v1/search`, `/auth`,
   `/schemas`, `/v0`.

End state: `tc image search "data center" --provider unsplash`,
`tc ai suggest-chart --data sales.csv`, `tc render deck.ppttc out.pptx`,
`tc validate-xml chart.xml` all work from a Mac/Linux terminal.

## What's already verified (don't re-probe)

### COM dispatch surface (closed)

- 25 methods total: 19 IPpMacroInterface + 3 IXlMacroInterface + 3 IUpdateBatch
- IIDs:
  - `IPpMacroInterface` `{24f3e526-2a15-4b8b-bc6a-558500f451c1}`
  - `IXlMacroInterface` `{085347c3-2d5b-4885-869a-b9cc362b924c}`
  - `IUpdateBatch` `{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}`
- 7 FHIDDEN methods (Step3 + Step2 family) — backward-compat, no new capability
- Strongly-typed C# interop generated at
  `state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`
- No alternate COM interfaces (no IConnectionPointContainer, IPersist*,
  IProvideClassInfo*) — proven via QueryInterface against 25 well-known IIDs

### Cloud topology

22 subdomains across 4 hosting clusters. See
`scripts/build_thinkcell_knowledge_graph.py` constant `HOSTING_TOPOLOGY` for
the full IP-cluster map. Key facts:

- `app.prod.ai.think-cell.com` lives on GCP (`34.159.52.56`), Let's Encrypt
- 4 stock-image proxies on Hetzner DE (`49.12.247.56` — pexels/unsplash/freepik
  share one box; flaticon is on the Berlin cluster)
- Berlin `213.61.194.234` hosts auth + telemetry + bug + update + license

### Auth scheme (partial)

**Verified:**

- BCrypt-CNG used: `BCryptOpenAlgorithmProvider`, `BCryptCreateHash`,
  `BCryptHashData` confirmed in tcaddin.dll ASCII strings with full
  source-level `_ASSERTE` context
- Both MD5 and SHA256 supported; `BCRYPT_ALG_HANDLE_HMAC_FLAG` set
  conditionally on whether a key is supplied
- `aiauthentication.bin` (342 bytes, `%APPDATA%\think-cell\`) is DPAPI-
  encrypted (magic `01 00 00 00 D0 8C 9D DF`), current-user bound. Decryptable
  via `[ProtectedData]::Unprotect` on the same Windows install user
- `messages` / `content` / `role` JSON literals are in tcaddin.dll →
  Chat-Completions-shaped body

**NOT verified (assume false until proven):**

- ~~JWT-shaped tokens~~ — earlier inference was substring noise. Only
  `iss`/`sub`/`aud` etc. as substrings in 49MB of binary; no `"iss":` /
  `"sub":` JSON literals confirmed.
- ~~Canonical-request signing AWS-style~~ — inferred from the
  `m_setnRequestedPathHashes` member name only. Speculation, not evidence.
- DPAPI plaintext format `expires=...&licensekeyid=...&hash=...` — claimed
  by the prior agent without persisted artifact. **Run the decrypt and
  verify before assuming this format.**

**Unknown:**

- The exact wire layout — what gets HMAC'd, where the signature goes
  (header? query string? body envelope?). **This is what Phase 1 of this
  plan captures definitively.**

### CFB chart serialization (cracked)

Every think-cell chart is an OLE Compound File at
`ppt/embeddings/oleObject*.bin` with three streams:

- `think-cellXML` (~100KB) — full chart serialization, MFC C++ class names
  as element tags
- `think-cellChild0/Package` (~16KB) — embedded xlsx datasheet
- `think-cellChild0/think-cellXML` (~700B) — child layout

Schema inventory: 305 distinct elements, 21 attributes, 40 chart classes,
85 member-prefix patterns. Captured at
`state/thinkcell_bridge/thinkcellxml_corpus/20260502-071725/schema_inventory.json`.

### TCLayout virtual COM

- ProgID `TCLayout.ActiveDocument.1` appears in every chart's
  `<mc:AlternateContent>` block (82+ hits across 5 bound decks)
- HKCR has no entry for it; `New-Object` fails
- Resolved at runtime by tcaddin.dll's hook engine (CLSIDFromProgID
  interception) — this is McPartlin's "Industrial Strength Software Hacking"
  pattern from Meeting C++ 2014
- Without tcaddin.dll loaded, charts fall back to the `<mc:Fallback>` PNG

## The plan — 4 phases

### Phase 1 — Auth capture (half-day, VM-side)

**Goal:** observe the wire format definitively. No more inference.

**Tools:** Frida 16.7+ (use `Process.attachModuleObserver` API — fires after
DllMain but before tcaddin's own pattern scanner). Standard `Interceptor.attach`
on imports, NOT Stalker (Stalker modifies `.text` and may trip tcaddin's
own hook detection).

**Critical pre-flight — Defender ASR:**
Microsoft Defender ASR signature KB0233 deletes tcaddin.dll/tcasr.exe on
hook-pattern detection. Disable ASR on the VM before running Frida hooks,
or the binary disappears mid-capture. PowerShell:

```powershell
Get-MpPreference | Select-Object AttackSurfaceReductionRules_Ids
# Add an exclusion or disable the relevant rule for the test
```

**The probe** (write as `scripts/probe_thinkcell_auth_capture.ps1` +
`scripts/run_thinkcell_auth_capture.py` mirroring the existing harness
conventions in those folders):

```javascript
// frida_auth_capture.js — attach to POWERPNT.EXE
const captures = [];

// 1. Hook BCrypt to capture HMAC inputs/outputs
[
  "BCryptOpenAlgorithmProvider",
  "BCryptCreateHash",
  "BCryptHashData",
  "BCryptFinishHash",
].forEach((name) => {
  const addr = Module.getExportByName("bcrypt.dll", name);
  Interceptor.attach(addr, {
    onEnter(args) {
      this.args = args;
      this.name = name;
    },
    onLeave(ret) {
      captures.push({
        fn: this.name,
        ts: Date.now(),
        // Capture relevant args based on fn signature
        // BCryptHashData: (handle, pbInput, cbInput, dwFlags)
        input_hex:
          this.name === "BCryptHashData"
            ? this.args[1].readByteArray(this.args[2].toInt32()).hexEncode()
            : null,
      });
    },
  });
});

// 2. Hook WinHttp to capture pre-TLS HTTP requests
["WinHttpAddRequestHeaders", "WinHttpSendRequest"].forEach((name) => {
  const addr = Module.getExportByName("winhttp.dll", name);
  Interceptor.attach(addr, {
    onEnter(args) {
      captures.push({
        fn: name,
        ts: Date.now(),
        // For AddRequestHeaders: args[1] is headers wide-string
        headers:
          name === "WinHttpAddRequestHeaders"
            ? args[1].readUtf16String()
            : null,
      });
    },
  });
});

// 3. Hook ProtectedData::Unprotect (or CryptUnprotectData) to see DPAPI plaintext
const unprotect = Module.getExportByName("crypt32.dll", "CryptUnprotectData");
Interceptor.attach(unprotect, {
  onLeave(ret) {
    // Output blob is at args[3] (DATA_BLOB *pDataOut)
    // Capture pbData + cbData from the output blob
  },
});
```

**Trigger sequence on the VM:**

1. Launch PowerPoint with think-cell loaded, deck blank
2. Wait for cold-start auth to complete (capture token validation traffic)
3. Invoke an AI feature once (forces fresh `/core/` call)
4. Trigger stock-image search once (captures proxy auth)
5. Wait for any background telemetry flush
6. Collect Frida log → JSON

**Persist outputs to:**
`state/thinkcell_bridge/auth_capture/<TS>/auth_capture.json`

**Success criterion:** the Authorization header value (or whatever signature
header name shows up) should appear byte-for-byte as the output of one of
the BCryptHashData calls. That correlation proves the auth scheme.

### Phase 2 — Decode + `tcauth` library (half-day, Mac-side)

Once Phase 1 captures land, decode:

1. **DPAPI plaintext format** — what's actually inside the 342-byte blob.
   The prior agent claimed
   `expires=<unix>&licensekeyid=<guid>&userhalfmonths=N&quota=N&hash=<HMAC>`
   without persisting an artifact. **Re-run the unprotect, dump the bytes,
   verify the format.**
2. **Canonical-string layout** — what string was passed to BCryptHashData?
   It will look like one of:
   - AWS-style: `METHOD\n/path\nquery\nheaders\nbody-hash`
   - Simple: `METHOD path body-hash timestamp`
   - JWT-style: base64url(header).base64url(payload) (signed, not HMAC'd)
   - think-cell-bespoke
3. **Header placement** — `Authorization: Bearer <sig>`, `X-TC-Sig: <sig>`,
   query string? The `WinHttpAddRequestHeaders` capture shows this.
4. **Token-refresh flow** — does `aiauthentication.appcom` issue session
   tokens, or is the DPAPI blob the long-lived credential? Answered by
   sequencing the captures: which endpoint is hit first?

**Build `tc_toolkit/tcauth.py`:**

```python
class TcAuth:
    """Replicates think-cell's request-signing scheme using the install's DPAPI token."""

    def __init__(self, dpapi_blob_path: Path):
        # Decrypt via Python ctypes calling CryptUnprotectData,
        # OR call out to a tiny PowerShell helper if running on Windows,
        # OR read a pre-decrypted plaintext file (Mac-side dev workflow)
        self.token = self._load_token(dpapi_blob_path)

    def sign(self, method: str, url: str, body: bytes = b'') -> dict[str, str]:
        """Return headers to attach to an httpx request."""
        ...
```

Lives at `~/code/labs/tc_toolkit/` (per `~/code/CLAUDE.md` taxonomy: this
is exploratory, so `labs/`).

### Phase 3 — Capability clients (1 day, Mac-side)

Wrap each endpoint family as a Python module:

```
tc_toolkit/
├── pyproject.toml
├── tc_toolkit/
│   ├── __init__.py
│   ├── tcauth.py        # The Phase 2 library
│   ├── images.py        # Pexels/Unsplash/Freepik/Flaticon search via *.appcom proxies
│   ├── ai.py            # Chat completions against app.prod.ai/core/
│   ├── schema.py        # think-cellXML validation against schemas.think-cell.com/api
│   ├── render.py        # ppttc → pptx via local tcserver.exe
│   └── cli.py           # Click-based CLI
└── tests/
    ├── test_images.py
    ├── test_ai.py
    └── test_schema.py
```

**`images.py` API sketch:**

```python
@dataclass
class ImageResult:
    provider: str
    title: str
    url: str
    license: str
    thumbnail: bytes | None

async def search(query: str, *, provider: str = 'unsplash',
                 limit: int = 10) -> list[ImageResult]: ...

async def download(result: ImageResult, dest: Path) -> Path: ...
```

**`ai.py` API sketch:**

```python
@dataclass
class ChatMessage:
    role: str  # 'system' | 'user' | 'assistant'
    content: str

async def complete(messages: list[ChatMessage], *,
                   stream: bool = False) -> str: ...

async def suggest_chart(data: pd.DataFrame, *,
                        purpose: str | None = None) -> str: ...
```

**`schema.py` API sketch:**

```python
@dataclass
class ValidationError:
    line: int
    message: str
    severity: str

def validate(thinkcell_xml: bytes) -> list[ValidationError]: ...
```

**`render.py` API sketch (requires tcserver.exe running on the VM):**

```python
def render(ppttc: dict | bytes, *, out_pptx: Path,
           tcserver_url: str = 'http://localhost:8080/v0') -> Path: ...
```

For this one, the auth model is the same as the AI endpoint (per the
`/auth` route enumeration). Confirm during Phase 1 capture whether
tcserver.exe accepts the same DPAPI-derived signature.

### Phase 4 — Personal CLI + smoke (half-day)

```bash
tc image search "data center" --provider unsplash --limit 5
tc image download <result-id> --out ~/Downloads/
tc ai chat "Explain my Q2 sales decline"
tc ai suggest-chart --data sales.csv --purpose "show year-over-year trend"
tc validate-xml chart.xml
tc render deck.ppttc out.pptx --tcserver http://vm-ip:8080
```

Smoke test: each of the 4 capabilities returns success on a known-good
input. Persist test fixtures under `tests/fixtures/`.

## Caveats — read before you start

1. **EULA gray area.** This is "use the install I paid for from a different
   process." Materially less problematic than enterprise data going through
   it, but think-cell's EULA hasn't been read with this in mind. Do this
   for personal hobbyist use; don't deploy as a service for others.

2. **Quota.** The DPAPI token has a `quota` field. AI endpoint usage will
   be bounded by whatever that number is. Read the value from the decrypted
   plaintext early — if it's "1000 calls/half-month" you've got room; if it's
   "10/day" you've got a constrained resource.

3. **Defender ASR (KB0233)** can delete tcaddin.dll/tcasr.exe on hook-pattern
   detection. Disable on the test VM. Don't disable on production machines.

4. **Anti-tamper.** think-cell ships function-detouring infrastructure
   (CFindCodePattern + the McPartlin hook engine) intended for hooking
   Office, not for being hooked itself. They probably don't actively
   detect Frida — but if the AI endpoint starts returning 401s after
   Frida runs, it may be User-Agent-fingerprinted or origin-checked.

5. **Token rotation.** The DPAPI blob's `expires` field bounds its
   lifetime (~3 hours observed). The auth flow likely refreshes
   automatically when think-cell talks to its endpoints. If you're calling
   from outside the desktop, you'll need to either:
   - Re-trigger refresh by launching PowerPoint periodically, or
   - Implement the refresh handshake yourself (capture the refresh flow in
     Phase 1 — it's one of the trigger conditions in
     `runbook_phase1_auth_flow_capture.md`)

6. **`messages`/`content`/`role`** matches OpenAI Chat Completions schema,
   but the model behind `/core/` is not necessarily GPT-4. It might be
   Claude, Gemini, an Anthropic-hosted Sonnet, or think-cell's own fine-tune.
   You won't know until you call it.

7. **Verify the prior agent's claims before depending on them.** Especially:
   the DPAPI plaintext format, the JWT-shape claim (revoked), the
   "PpAICoreURL constant" (UTF-16LE only — verified). When in doubt:

```bash
# Re-grep tcaddin.dll for any specific symbol claim
strings -n 6 -el state/thinkcell_bridge/tcaddin_dll/tcaddin.dll | \
    grep -i "<symbol-you-want-to-verify>"
```

## Stop rules

Abort if:

1. Phase 1 capture shows the auth uses **client-certificate (mTLS)** instead
   of an HMAC header. Replicating mTLS without exfiltrating the install
   client cert is much harder; treat this as a different problem.
2. The DPAPI token has `quota: 0` or `expires` already past — your install
   is metered out or your license is dormant. Force a refresh by triggering
   PowerPoint + AI feature first.
3. think-cell pushes a tc15 update mid-capture and the binary version
   changes — capture is invalid against the new build, restart from a
   clean state.
4. Defender deletes tcaddin.dll on Frida attach. Disable ASR or use Stalker
   instead of Interceptor (acceptable trade-off if scoped right).
5. Calling the AI endpoint with replayed signature returns a stable 401 —
   the auth scheme has a host/origin fingerprint we haven't characterized;
   stop, return to Phase 1 to capture more context.

## Resources

| Resource                       | Path                                                                               |
| ------------------------------ | ---------------------------------------------------------------------------------- |
| MASTER_STATE                   | `docs/thinkcell-corpus/MASTER_STATE.md`                                            |
| Phase 1 auth-flow runbook      | `docs/thinkcell-corpus/runbook_phase1_auth_flow_capture.md`                        |
| Knowledge graph (queryable)    | `state/thinkcell_bridge/knowledge_graph/`                                          |
| Graph query CLI                | `.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "<question>"`         |
| think-cellXML schema inventory | `state/thinkcell_bridge/thinkcellxml_corpus/20260502-071725/schema_inventory.json` |
| C# strongly-typed interop      | `state/thinkcell_bridge/csharp_interop/20260501-215903/Thinkcell.Interop.cs`       |
| Verified strings               | `state/thinkcell_bridge/auth_oauth_string_mining/verified_findings.json`           |
| Local DPAPI auth blob (VM)     | `%APPDATA%\think-cell\aiauthentication.bin` (342 bytes)                            |
| ppttc.exe (VM)                 | `C:\Program Files (x86)\think-cell\ppttc.exe`                                      |
| tcserver.exe (VM, not running) | `C:\Program Files (x86)\think-cell\tcserver.exe`                                   |
| tcaddin.dll on disk (Mac copy) | `state/thinkcell_bridge/tcaddin_dll/tcaddin.dll` (49MB)                            |

### Hostnames in scope

Stock proxies: `freepik.appcom.think-cell.com`, `pexels.appcom.think-cell.com`,
`unsplash.appcom.think-cell.com`, `flaticon.appcom.think-cell.com`

AI: `app.prod.ai.think-cell.com/core/`, gated by `aiauthentication.appcom.think-cell.com`

Schemas: `schemas.think-cell.com/api`

Local rendering: `tcserver.exe` on `localhost` (port TBD; check binary or settings.xml)

### Compile-time IIDs (for any C# interop work)

```
IPpMacroInterface  {24f3e526-2a15-4b8b-bc6a-558500f451c1}
IXlMacroInterface  {085347c3-2d5b-4885-869a-b9cc362b924c}
IUpdateBatch       {be9bb0c3-e5fb-4de5-b499-aae20fff6fad}
```

### Definitively closed (don't re-probe)

- COM dispatch surface beyond the 25 methods. Empirically closed via 5
  orthogonal techniques (GetIDsOfNames, ITypeInfo, IDispatchEx,
  QueryInterface against 25 well-known IIDs, InvokeMember). All converge.
- Web add-in path. Hard-blocked by Microsoft.
- Native editable think-cell tables. PowerPoint repair-prompts on raw
  m_strName injection. Use Excel COM `AddRangeImage` table-image lane.
- Mekko Graphics import. Blocked — no donor PPTX in VM.

## What success looks like

End of this plan:

```bash
$ tc ai chat "Suggest a chart type for showing FY26 ARR by stage"
Recommended: Mekko (categorical-by-quantitative). For pipeline mix
across an ordinal stage progression, the Mekko gives you both relative
share within stage and absolute width by stage — better than a stacked
bar at the same screen size.

$ tc image search "data center" --provider freepik --limit 3
[1] Modern data center server room - Premium - https://...
[2] Cloud computing data center - Standard - https://...
[3] Network infrastructure - Standard - https://...

$ tc render examples/qtr01.ppttc out.pptx
Rendered to out.pptx (37 KB) in 2.1s

$ tc validate-xml my-handrolled-mekko.xml
Line 12: m_setColors requires at least 1 child of type CRGB
Line 47: CSequenceChartDataScalar.m_dValue out of range [0, 1e9]
2 validation errors found
```

That's "free Pexels+Unsplash+Freepik+Flaticon image search, free
GPT-4-class chat completions, free think-cellXML linter, and a local
JSON-to-PPTX rendering service" — all from a Mac terminal, all using the
identity of the install you already paid for.

Total time investment: ~2.5 days of focused work, dependent on Phase 1
capture going clean.

## Final note for the new agent

The prior session's discovery work was thorough but had two overclaim
incidents:

1. PpAICoreURL / BCryptCreateHash / Getty/Canto URLs were claimed as
   "found in mining JSON" but were actually only in an unpersisted
   stdout-only Python probe. After verification: they ARE in tcaddin.dll
   (most are UTF-16LE-encoded), but the JSON the prior agent referenced
   didn't contain them.
2. JWT-shaped tokens claim was substring noise (3-letter hits like "iss"
   in 49MB of binary) — revoked.

So: **verify before relying on prior claims.** The verification script at
`state/thinkcell_bridge/auth_oauth_string_mining/verified_findings.json`
captures what's been confirmed; check it before treating any string-mining
claim as ground truth. When in doubt, run `strings -n 6 -el` (UTF-16LE
aware) on the binary yourself. The `verify-handoff-claims` discipline in
Andre's memory applies here.

Andre's preferences (from his global CLAUDE.md):

- Default to action, not questions
- No A/B/C/D option menus; pick one and report
- Short status updates; no preambles
- Lead with the answer or action
- One sentence beats one paragraph beats a heading-rich essay
- Investigate the environment before asking; only ask for things
  unrecoverable programmatically
- Never commit `.env` or anything with secrets
- Don't `--no-verify` or `--force` push without per-incident approval

When this work is done, send a tight summary to MASTER_STATE.md and
optionally (Andre's call) create a `tc_toolkit` entry under
`~/.claude/projects/-Users-test/memory/` for cross-session persistence.
