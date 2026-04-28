# eval/

Evaluation harness for the daily Sales Ops AI brief produced by `scripts/agent.py`
(Microsoft Agent Framework wrapper) or `scripts/brief.py` (CLI).

## What's implemented (Phase 1 — local)

- **`evaluators/numeric_recall.py`** — `NumericFactRecallEvaluator`. Pure
  rule-based regex extraction of dollar figures, counts, names, and labels
  from the brief markdown. Currency facts pass within `tolerance_pct`
  (default ±5%); counts and labels are exact-match.
- **`evaluators/groundedness_judge.py`** — `GroundednessLLMJudgeEvaluator`.
  LLM-as-judge against `gpt53chat` on `apro-openai` (same auth pattern as
  `brief.py` / `agent.py` — `AzureCliCredential` → `Cognitive Services
OpenAI User`). Asks the model to flag any claim in the brief that
  contradicts or isn't supported by the verified facts. Enforces ARR/ACV
  separation in the system prompt.
- **`run_eval.py`** — runner. Loads the latest dataset + the latest
  `agent-YYYY-MM-DD.md`, runs both evaluators, prints a summary, writes a
  per-run JSON to `eval/runs/<timestamp>.json`. Exit 0 if both scores ≥ 0.9.

## What's deferred (Phase 3)

- AI Foundry SDK integration via `azure-ai-evaluation`. The local evaluator
  interface (`run(facts, brief_md) → score + detail`) maps cleanly onto
  Foundry's evaluator contract; wiring is mechanical when the Foundry
  project is provisioned.
- Trend dashboards (per-fact regression timelines).
- Adversarial / red-team eval datasets.
- Hooking into a Foundry-hosted agent's eval pipeline so results land in
  the Foundry portal rather than `eval/runs/`.

`azure-ai-evaluation` is intentionally NOT in `requirements.txt` yet — it's
the Foundry SDK and Phase 3 will add it.

## Adding a new dataset

1. Run today's brief: `python3 scripts/agent.py`.
2. Hand-verify the headline numbers against Salesforce.
3. Copy `eval/datasets/2026-04-28.json`, rename to today's date, update
   `facts` with the verified values.
4. Re-run `python3 eval/run_eval.py` against the new dataset.

## Extending an evaluator

- Rule-based: add a new fact to `dataset.facts`, then add an extractor in
  `evaluators/numeric_recall.py` (regex against the markdown). If the value
  is currency, add it to `CURRENCY_FACTS` so it gets tolerance treatment.
- LLM judge: edit `JUDGE_SYSTEM` in `evaluators/groundedness_judge.py` to
  emphasise new rules.

## Known limitation

Ground truth is a snapshot. Pipeline numbers drift daily, so this harness
catches **regressions** in the agent's extraction/synthesis, not absolute
correctness over time. To detect drift in the underlying SF data, use
`scripts/snapshot_diff.py` instead — that's a different signal.

## Auth precondition

`az login --tenant aa81b43f-3969-4fd4-80c9-84c411508d82` (same as
`scripts/preflight.py`). Without this the LLM judge will fail; the
rule-based evaluator runs offline.
