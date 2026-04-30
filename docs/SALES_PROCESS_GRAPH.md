# Sales process knowledge graph

`scripts/sales_process_graph.py` is the single source of truth for SimCorp's
sales-process model. Every consumer that needs stage names, governance gates,
deal motions, action-item rules, or metric definitions imports from this graph
instead of hand-coding the data.

## Why a graph

Three of these consumers existed independently before:

- `excel_companion.py` had its own `STAGES_8` / `GOVERNANCE_GATES` / `MOTIONS` tuples
- `land_brief.py` had its own action-item rule definitions
- `brand-deck-agent-py/agent/land_system_prompt.py` had its own handbook section
  embedded in the LLM system prompt

When the handbook intel was refreshed (or the SimCorp-One attach threshold
tweaked, or the Commercial Approval rule clarified) the change had to be made
in every consumer separately, and any one of them silently went stale.

The graph collapses that into one Python module. Update the graph -> all
surfaces (xlsx, deck, daily brief, alerts) see the same canonical facts.

## Schema

Six frozen dataclasses + 1 aggregator:

| Entity           | Count | Purpose                                                                                  |
| ---------------- | ----- | ---------------------------------------------------------------------------------------- |
| `Stage`          | 8     | The 8-stage SimCorp sales process                                                        |
| `GovernanceGate` | 5     | Commercial Approval / Margin Review / Deal Services Design / Deal Review / Due Diligence |
| `Motion`         | 3     | LAND / EXPAND / RENEWAL — which revenue field, which stages                              |
| `Metric`         | 9     | Named metrics (raw / proxy / derived) with caveats                                       |
| `Rule`           | 8     | Action-item rules — threshold semantics + suggested actions                              |
| `Qualifier`      | 25    | Stage-exit qualifiers verbatim from the handbook                                         |
| `ProcessGraph`   | 1     | Aggregator (`GRAPH`)                                                                     |

`SCHEMA_VERSION = 1`. Bump on breaking changes (rename / remove fields). Adding
optional fields with defaults is backward-compatible.

## Source of truth refs

```python
HANDBOOK_SOURCE = "~/.claude/intel/simcorp-sales-process-2026-04.md"
BRAND_PALETTE_SOURCE = "~/projects/brand-deck-agent-py/assets/simcorp-2024.json"
```

The graph copies the handbook prose verbatim. If those source files change,
update the graph and re-test consumers.

## Cross-project usage

### sales-ops-copilot

```python
# scripts/excel_companion.py — Process_Standards sheet
from sales_process_graph import GRAPH
STAGES_8 = [(str(s.number), s.name, s.description) for s in GRAPH.stages]
GOVERNANCE_GATES = [(g.name, g.trigger, _stages_when_string(g.when_stages), g.purpose) for g in GRAPH.gates]
MOTIONS = [(m.name, m.description, m.process_notes, m.revenue_field) for m in GRAPH.motions]
```

### brand-deck-agent-py (intended future swap)

When the LAND deck pipeline swaps to enterprise Claude (per the
`feedback_deck_llm_substrate_2026-04-29` memory), the system prompt's
handbook block becomes a one-line graph call:

```python
# agent/land_system_prompt.py
from sales_process_graph import to_llm_context

SYSTEM_PROMPT = f"""
You are the SimCorp Sales Director monthly LAND review writer.

{to_llm_context()}

[director-specific narrative section follows...]
"""
```

This replaces ~80 lines of hand-curated handbook prose with a 3KB markdown
block generated from the graph. Update the graph -> the deck prompt updates.

### Daily brief (future)

`scripts/brief.py` currently hand-rolls its methodology section. It can move
to `to_llm_context()` for the SimCorp-process portion + its own data section.

### Alert generators / Claude skills (future)

A future `account-drill` or `owner-drill` skill can:

- enumerate `gates_at_stage(N)` to know which approvals matter for an opp
- look up `metric("zombie_arr").how_to_read` to caveat any zombie figure it cites
- import `proxy_metrics()` to know which numbers always need a "PROXY —" prefix

## Query API

```python
from sales_process_graph import (
    GRAPH,
    stage, gate, motion, metric, rule,        # by-name lookups
    gates_at_stage, rules_at_stage,           # stage-keyed
    qualifiers_for_stage_exit,                # exit checklist
    proxy_metrics,                            # caveat-required metrics
    to_json, to_llm_context,                  # serializers
)

# what gates apply when reviewing a Stage 3 opp?
for g in gates_at_stage(3):
    print(g.name)
# -> Commercial Approval, Deal Services Design, Due Diligence

# which rules might fire on a Stage 4 deal?
[r.rule_id for r in rules_at_stage(4)]
# -> ['zombie_arr', 'approval_gap', 'simcorp_one_attach_low',
#     'late_stage_concentration', 'activity_drought', 'renewal_thin', 'slippage']

# all metrics requiring proxy caveat language
[m.name for m in proxy_metrics()]
# -> ['grr_proxy']
```

## Smoke test

```bash
cd ~/code/apps/sales-ops-copilot
python3 scripts/sales_process_graph.py
```

Prints the LLM context block + a few sample queries + the JSON schema version
and size. Use this to verify the graph imports clean before shipping a change.

## Update workflow

1. Edit `scripts/sales_process_graph.py` (graph data only — don't change shapes
   without bumping `SCHEMA_VERSION`).
2. Run the smoke test (above).
3. Re-run any director's LAND xlsx generation — Process_Standards sheet should
   reflect the change.
4. If the change touches a `Rule` whose threshold or `metrics_used` shifts,
   verify `land_brief.py`'s rule runner still aligns (the runner currently
   implements rules independently — the graph documents semantics, the runner
   computes; an obvious next step is to wire the runner directly off the graph).
