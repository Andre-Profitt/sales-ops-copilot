# think-cell research — Phases master runbook

Date: 2026-05-02
Authoritative state across all phases of the think-cell research session.

## Phase status

| Phase | Description                                                             | Status                                                       |
| ----- | ----------------------------------------------------------------------- | ------------------------------------------------------------ |
| **0** | Cheap public discovery + local artifact deep read                       | **DONE** today                                               |
| **1** | Frida + mitmproxy + Procmon live capture                                | **scaffolded**, requires interactive desktop session on VM   |
| **2** | Ghidra-headless + local-Claude LLM decompile of tcaddin.dll             | **scaffolded**, ~1-2h Ghidra + ~1-2h labeling, ~$5-15 cost   |
| **3** | think-cellXML grammar via differential customXml capture                | **scaffolded** (PowerShell harness ready)                    |
| **4** | Targeted exercises (C# interop, AI auth decode, tcasr Procmon, fuzzing) | partial — C# interop generated, others scaffolded as runbook |
| **5** | External research feedback (deep technique survey)                      | **agent dispatched in background**                           |

## Phase 0 — completed today

- `phase0_public_http`: HEAD/OPTIONS sweep across 13 subdomains + cert transparency
- `phase0_template_schema`: enumerated `static.think-cell.com/ppttc/template[1-50].pptx` + `schemas.think-cell.com/<build>/tcstyle.xsd`
- `phase0_local_artifacts`: pulled + magic-byte-sniffed all local think-cell files

Outputs in `state/thinkcell_bridge/phase0_*/`.

Headlines:

- **`aiauthentication.bin` IS Windows DPAPI-encrypted** (magic `01 00 00 00 D0 8C 9D DF`). Stores AI token, can only be decrypted by current user on same machine.
- **4 public templates** at `static.think-cell.com/ppttc/`: template2.pptx, template3.pptx, template4.pptx, template5.pptx (sizes 78KB-967KB).
- **Only one schema XSD served**: `36264/tcstyle.xsd` (46KB). The "next/tcstyle" namespace is binary-embedded only, not URL-served.
- **`pexels.appcom.think-cell.com` is a transparent proxy to pexels.com** (responses are literally pexels.com HTML). think-cell middlemen for: auth, observation, caching, rate-limiting.
- **`schemas.think-cell.com` allows POST** per OPTIONS — interesting; not characterized further.
- **`ai.appcom.think-cell.com` is 403-everywhere** — auth-required for everything.

## Phase 1 — to run (interactive desktop session)

```powershell
# On VM interactive desktop session (not SSH non-interactive)
.\setup_phase1_capture_env.ps1                    # one-time
# Follow runbook_phase1_frida_mitm_capture.md
```

Three terminals: mitmproxy (terminal 1), Procmon (terminal 2), frida-trace (terminal 3).
Manual workflow: open template → insert chart → use AI feature → save → close.
Then ferry capture artifacts to Mac and run analyzer:

```bash
.venv/bin/python scripts/analyze_phase1_capture.py --capture state/thinkcell_bridge/phase1_capture/<ts>
```

Yield: complete call graph + wire format + IPC contract for one full workflow.

## Phase 2 — to run (overnight)

```bash
./scripts/decompile_tcaddin_with_ghidra.sh --setup        # one-time, downloads Ghidra 11.4
./scripts/decompile_tcaddin_with_ghidra.sh --pull-dll     # scp tcaddin.dll from Windows-VM
./scripts/decompile_tcaddin_with_ghidra.sh --decompile    # ~1-2h: produces functions.jsonl

# Then label the most-interesting functions with Claude
.venv/bin/python scripts/label_thinkcell_functions_with_claude.py \
    --jsonl state/thinkcell_bridge/ghidra_decompile/<ts>/functions.jsonl \
    --model claude-haiku-4-5-20251001 \
    --top-n 500
```

Cost: ~$5-15 with Haiku 4.5 on top 500 functions. Set `ANTHROPIC_API_KEY=` in `.env` first.

For higher-quality labeling on the most-interesting subset, use `--model claude-opus-4-7 --top-n 50`.

Output: `state/thinkcell_bridge/ghidra_decompile/<ts>/functions.db` — SQLite with FTS5 index. Query via standard SQL or build a `query_thinkcell_function_db.py` helper.

## Phase 3 — to run (multi-day if pursued)

```bash
# Initial capture: 6 mutations on the first chart shape
.venv/bin/python scripts/run_thinkcell_phase3_xml_capture.py    # to be written
```

Or directly:

```powershell
# On VM
& "\\Mac\Home\code\apps\sales-ops-copilot\scripts\capture_thinkcellxml_diff.ps1" -OutputPath \\Mac\Home\code\apps\sales-ops-copilot\state\thinkcell_bridge\phase3_xml_grammar\<ts>\diff.json
```

Each run produces 6 baseline/modified.pptx pairs + extracted customXml. Iterate with more mutations to build a grammar corpus.

Then apply grammar inference (BinPRE / Skyfire / GLADE) on the corpus to derive a CFG. Multi-day if you go deep.

## Phase 4 — targeted exercises

- **C# interop smoke test**: compile `Thinkcell.Interop.cs` (already generated) + 50-line console app calling `LoadStyle` + `LoadStyleStep2`. Validates IIDs end-to-end. ~2h.
- **`aiauthentication.bin` decode**: it's DPAPI. Decrypt with current Windows user via `[System.Security.Cryptography.ProtectedData]::Unprotect()`. Reveals the AI token (likely OAuth refresh). ~30min.
- **tcasr.exe Procmon trigger trace**: launch Procmon filtered to tcasr.exe, then trigger a `.ppttc` write that engages the sidecar. Captures the spawn moment + IPC names. Folded into Phase 1 capture if Procmon runs throughout.
- **`.ppttc` parser fuzz**: AFL++/libFuzzer harness around `ppttc.exe`. Half-day setup, days of running. Lower priority.
- **Browser-extension native-messaging probe debug**: the existing probe hangs in registry walk. Bound the scan more aggressively. ~1h.

## Phase 5 — external research (agent dispatched in background)

Agent is researching:

- Post-2025-08 LLM decompile SOTA
- Grammar inference frontier 2024-2026
- Symbolic execution scaling on COM dispatch
- In-process Office add-in instrumentation
- Adjacent-domain RE (Tableau, Power BI, Mekko)
- Communities + practitioner blogs
- Probe automation techniques
- Anti-tamper / hook engine analysis
- Patent + legal landscape (recent filings)
- Beta / preview channel observability

Output will land at `docs/thinkcell-corpus/research-swarm-2026-05-02/agent-deep-techniques.md`.

## Files written this session (Phase 0 + scaffolds)

```
scripts/
├── probe_thinkcell_phase0_public_http.py            (Mac-side, ran)
├── probe_thinkcell_phase0_template_and_schema_enum.py (Mac-side, ran)
├── probe_thinkcell_phase0_local_artifacts.ps1       (VM, ran via runner)
├── run_thinkcell_phase0_local_artifacts.py          (Mac wrapper, ran)
├── setup_phase1_capture_env.ps1                     (Phase 1 env setup)
├── decompile_tcaddin_with_ghidra.sh                 (Phase 2 Ghidra)
├── label_thinkcell_functions_with_claude.py         (Phase 2 LLM labeler)
├── analyze_phase1_capture.py                        (Phase 1 unified analyzer)
└── capture_thinkcellxml_diff.ps1                    (Phase 3 grammar capture)

docs/thinkcell-corpus/
├── runbook_phase1_frida_mitm_capture.md             (Phase 1 manual workflow)
└── phases-master-runbook.md                         (this file)
```

## Stop rules

- **Personal license only.** Do not republish findings, do not share captures.
- **No SimCorp data in capture sessions.** This VM is personal think-cell only.
- **mitmproxy CA only on personal VM.** Never on a SimCorp-issued machine.
- **Reset proxy after capture.** `netsh winhttp reset proxy`.
- **Phase 2 cost cap.** Default `--top-n 500` keeps labeling under $20 with Haiku 4.5. Don't run on the full 10K+ function list.
