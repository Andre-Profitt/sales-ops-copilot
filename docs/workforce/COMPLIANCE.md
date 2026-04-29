# Workforce Track — Compliance Notes

How Phase 1 respects the SimCorp AI Code of Conduct and Group Compliance whitelist for Claude. Source-of-truth for the constraints: `~/.claude/skills/simcorp-org-wrap/governance.md` and `~/.claude/intel/simcorp-ai-whitelist-2026-04-28.md`.

## Hard rules applied to Phase 1

### 1. People-related decision-making — PROHIBITED via AI

Per Code of Conduct rule 8: "People-related decision-making is PROHIBITED — no AI for evaluating/comparing/profiling/deciding about identifiable individuals."

**Phase 1 design respects this by:**

- The `wf.py` CLI is **descriptive**, not prescriptive. It shows numbers — it doesn't recommend actions like "fire X" or "promote Y."
- **Zero LLM calls** in any Phase 1 code path. SQL aggregations only. The CLI never sends per-person data through Claude, Azure OpenAI, or any other LLM.
- The brief.py / agent.py code paths (which DO use LLM synthesis) deliberately don't import any workforce data. Workforce data stays inside `scripts/workforce/` and never leaks to the brief.
- `wf.py` outputs are **plain-text tables** for the human (Andre) to read and act on. The human is the decider; the tool is descriptive.

### 2. Content-level audit visibility — NONE for Claude

Per the whitelist row for Claude: "SimCorp does not have content-level visibility, which limits full auditability and evidencing of information handling."

**Phase 1 design respects this by:**

- All workforce data lives **on Andre's local Mac only**. The DuckDB at `workforce/state/wf.duckdb` is gitignored. The raw exports at `workforce/raw/` are gitignored. Nothing is uploaded.
- No upload to cloud LLM, no cloud DB, no shared filesystem.
- No data ingress through Cowork (Cowork has the additional restriction that activity is NOT in audit logs — `simcorp-claude-cowork-policy-2026-04-28.md` rule list). Phase 1 uses Claude Code CLI / Codex CLI for development; CLI activity IS auditable.

### 3. Strictly confidential / IP / third-party data — LIMITED

The whitelist marks "strictly confidential" and "IP" as LIMITED for Claude. Workforce performance data falls under "personal data" (which is YES allowed as input) but the ratings of identifiable individuals tip into "people-related decision-making" if AI infers them. Phase 1 stays on the YES side by not using AI inference at all.

### 4. Cowork restrictions — additional gates

Per `simcorp-claude-cowork-policy-2026-04-28.md`:

> Cowork **should not be used for** client services / sensitive client data / regulated work / **compliance-critical / audit-sensitive activities**.

Workforce performance data is "confidential" in spirit (it shows individual-rep performance metrics). **Don't use Cowork for workforce track work** — use Claude Code CLI / Codex CLI instead. Both leave terminal-level audit trails.

## What's prohibited

- ❌ Feeding `wf.py` output (or `weekly_person_kpis` rows) to Claude or any LLM for "synthesize this rep's performance"
- ❌ Sharing the DuckDB file via email, Slack, SharePoint, or any other surface
- ❌ Building "AI-powered coaching recommendations" on top of this data — that's the people-related-decision-making line
- ❌ Using workforce data in the daily brief synthesis (separation of concerns: brief = pipeline, wf = workforce — never mix)
- ❌ Running Phase 1 from Claude Cowork (use CLI instead)

## What's allowed

- ✅ Reading the data via `wf.py` for descriptive analysis
- ✅ Using the data to **inform** human decisions (the human is the decider, not Claude)
- ✅ Discussing the aggregate patterns (anomalies, coverage concentration, capacity vs. commit) with Group Compliance, Sales leadership, or HR — those are humans
- ✅ Building Phase 2 (live SF refresh) provided the same compliance posture is maintained
- ✅ Phase 3 dashboard or TUI provided no LLM inference is added on per-person data

## When to escalate

- Group Compliance (`compliance@simcorp.com` — Konrad Torun, Emilie Terney Bech) — before adding any AI inference layer to this data, or before Phase 3 ships if the consumer surface is anything other than internal/personal use by Andre.
- Data Privacy (`dataprotection@simcorp.com`) — if the local DuckDB is ever copied off the device, or if any workforce data is suspected to have been shared with non-whitelisted AI.

## Test enforcement

The Phase 1 codebase has **no `import openai`, no `from anthropic`, no `azure-openai` import** in any file under `scripts/workforce/`. Verify:

```bash
grep -r -E '(import openai|from openai|import anthropic|from anthropic|AzureOpenAI|OpenAIChat)' scripts/workforce/
# expected: no matches
```

If a future agent adds an LLM dependency to this track, that should trigger a compliance review per this doc.

## Future phases

- **Phase 2 (live SF refresh):** same compliance posture. Read-only against SF; no writes; no LLM inference.
- **Phase 3 (consumer surface):** decide between (a) Fabric dashboard for shared visibility, (b) Local TUI for Andre-only, (c) accepting the existing 112-slide PPTX. Option (a) shifts the data into Fabric workspaces — that's a Group IT-approved path, but the data goes from Andre's Mac to a tenant resource, which might trigger additional review. Option (b) keeps the data local. **Default: review with Konrad Torun before Phase 3.**
