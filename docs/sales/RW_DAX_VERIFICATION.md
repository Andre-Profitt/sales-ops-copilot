# RW DAX measure verification — recipes

DAX query API (`POST /datasets/{id}/executeQueries`) is **tenant-disabled** in
SimCorp's PBI tenant (error: `PowerBIFeatureDisabled`). Re-confirmed
2026-05-08 against `sm_sales_kpis_rw`.

That means there is no clean Mac-desktop way to programmatically evaluate a
DAX measure and assert its value. This doc lists the verification options
ranked by how clean the loop is.

---

## Recipe 1 — Fabric notebook with sempy (clean, async)

**When:** you want a programmatic, scriptable DAX eval and don't mind running
the loop inside Fabric.

**Why this works:** Fabric notebooks ship sempy + the .NET runtime + the
correct `Microsoft.Fabric.SemanticLink.XmlaTools` assembly pre-loaded. The
desktop sempy install on macOS arm64 fails because the bundled assembly is
Linux x86_64 only.

**Notebook cell:**

```python
import sempy.fabric as fabric

WORKSPACE = "Salesforce Analytics - Sales Manager"
DATASET = "sm_sales_kpis_rw"

# Single-row eval
df = fabric.evaluate_dax(
    dataset=DATASET,
    workspace=WORKSPACE,
    dax_string="""
    EVALUATE ROW(
      "Won ARR",      [Total Closed Won ARR],
      "Open ARR",     [Total Open Pipeline ARR],
      "Backward S3",  [Stage 3 Backward Pct]
    )
    """
)
display(df)

# Sliced eval
df = fabric.evaluate_dax(
    dataset=DATASET,
    workspace=WORKSPACE,
    dax_string="""
    EVALUATE
    SUMMARIZECOLUMNS(
      f_opportunity[motion_type],
      "Won ARR", [Total Closed Won ARR]
    )
    """
)
display(df)
```

**Setup:** create a notebook in workspace `Salesforce Analytics - Sales Manager`,
attach to a Spark pool (any), paste the above. No pip installs needed.

**Limitations:** notebook UI is async, not CLI. Each session warm-up takes
~15s. Not suitable for fast iterate-and-eval loops.

---

## Recipe 2 — Probe-card spot-check (Mac-desktop, manual eyeball)

**When:** you want a fast desktop loop, accept eyeballing as the verification
step.

**CLI:** `scripts/sales/rw_probe_measures.py`

```bash
# Probe 1+ measures by name; auto-grids 4 cards/row on the 'What Changed' tab
python3 -m scripts.sales.rw_probe_measures \
    --measures "Stage 3 Backward Pct,At Risk Opps Count,Healthy Moves Count"

# Open the printed URL, look at the values
# When done:
python3 -m scripts.sales.rw_probe_measures --clear
```

**What it does:**

- Pulls inventory of deployed measures (`fetch_measures_by_table`)
- Resolves each name → table; errors fast if any name unknown or ambiguous
- Clears the `What Changed` redesign tab (always — assumes you're not
  composing real visuals there yet)
- Builds a `build_card_visual` per measure on a 4-col grid
- Pushes the report; prints the URL

**Why this beats inventing a card by hand:** caught typos pre-push (via
`rw_validate.py`-style measure resolution); auto-grid; one CLI call instead
of editing `rw_add_visual.py` for a one-off card row.

**Limitations:** still requires opening a browser to read values. No
programmatic assertion possible.

---

## Recipe 3 — XMLA endpoint via Tabular Editor / DAX Studio (Windows)

**When:** you have a Windows machine or a Windows VM and want a polished
DAX dev experience.

The PBI workspace exposes an XMLA endpoint at:

```
powerbi://api.powerbi.com/v1.0/myorg/Salesforce%20Analytics%20-%20Sales%20Manager
```

DAX Studio + Tabular Editor 2 (free) connect to this endpoint with az / SSO
auth and give you a real DAX REPL + measure-by-measure debugger. This is
the canonical Microsoft workflow.

**Limitations:** Windows-only (Tabular Editor 2 is .NET Framework). DAX
Studio on Mac runs but lacks the XMLA connection feature.

---

## Recommended workflow

| Phase                                               | Tool                                              | Why                              |
| --------------------------------------------------- | ------------------------------------------------- | -------------------------------- |
| Author measure (DAX in `rw_push_semantic_model.py`) | Mac CLI                                           | Where the source lives           |
| Push model                                          | `python3 -m scripts.sales.rw_push_semantic_model` | LRO accepts ⇒ syntactic-correct  |
| Quick spot-check 1-8 measures                       | `rw_probe_measures.py`                            | Fast, no notebook context-switch |
| Cross-check against expected values, slice-and-dice | Fabric notebook (Recipe 1)                        | Programmatic, scriptable         |
| Deep debug (e.g., performance, dependencies)        | DAX Studio (Recipe 3)                             | Best UX if Windows available     |

---

## Why this is in the repo

The whole-stack truth is: **the cleanest Microsoft-canonical path
(`/executeQueries`) is blocked by tenant policy**, sempy desktop is broken
on macOS arm64, and our compromise is `rw_probe_measures.py`. Future you
will forget all three of these facts; this doc is the receipt.
