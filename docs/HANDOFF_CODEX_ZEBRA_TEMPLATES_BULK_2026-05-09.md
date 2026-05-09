# Handoff to Codex — Convert ALL 20 Zebra templates to renderable native PBI reports

**Andre's frame:** "Are we able to convert ALLLL the templates to PBI files?" The translator works (PR9 just landed). One template proven end-to-end. Now bulk-publish all 20 so Andre can flip through them in Fabric and see what the Zebra corpus looks like rendered native.

**Owner you're working for:** Andre (apro@simcorp.com).

**Worktree:** `~/code/apps/sales-ops-copilot-rw/`. Current branch: `feat/track-rw-tooling` (already pushed at `8a38367`).

---

## TL;DR

The translator (`scripts/sales/rw_zebra_kg_translator.py`) deterministically maps any Zebra `visualContainer` to a native PBIR equivalent — proven on the 360-VC infrastructure corpus + one live Fabric round-trip (`cost-management-power-bi-template` → 31/31 native VCs).

To get **all 20 templates rendered side-by-side in Fabric**, two pieces are needed:

1. A native **report.json per template** (translator does this — already proven).
2. A native **semantic model per template** so the translated visuals' measure refs actually resolve. The schemas/measures/relationships are already extracted at `data/zebra_kg/schemas/<slug>/`. What's missing is a TMDL emitter + a Fabric `items` POST that publishes a SemanticModel.

Without (2), the report visualizations show "field not found" placeholders for every measure — you saw this on Andre's last test push.

**Your job:** ship both pieces as a `rw_zebra_kg_publish_all_templates.py` CLI, run it, give Andre 20 working URLs.

---

## State of play (live, verified 2026-05-09 evening)

**Translator (done):**

- `scripts/sales/rw_zebra_kg_translator.py` — `translate_visual(src_vc, target_catalog, rw_map) -> list[dict]`. Dispatches by family (Tables / Cards / Charts / Waterfall / passthrough). Proven on 360 source VCs + 1 live Fabric round-trip.
- `scripts/sales/rw_zebra_kg_ibcs_synth.py` — IBCS column synthesis, dataBars CF, composite KPI tile.
- `scripts/sales/rw_zebra_kg_test_dashboard.py` — single-template harness (the cheap path you'll extend).
- `scripts/sales/rw_zebra_kg_graphrag.py` — atlas retriever (not in scope here, FYI).

**Test report already pushed** (cost-management, no semantic model — broken refs):

- Workspace: `b66233d5-9d4a-44ba-89a8-b70206d98ae7`
- Report id: `fb0d5b21-5164-4d5e-9e3a-6de6fcf4d1a8`, displayName `test`. Currently bound to `sm_sales_kpis_rw` so most cells show field-not-found. Either reuse it as the demo umbrella or delete and start fresh.

**Per-template schemas already extracted:**

```
data/zebra_kg/schemas/<slug>/
  metadata.json
  model.json            # full structured model: tables, columns, measures, relationships
  measures.csv          # name, table, format_string, expression (DAX) — 439 measures across 20 templates
  relationships.json    # 133 relationships + topology summary
  tables/<table>.json   # per-table column + measure list
```

20 slugs available. List with:

```bash
.venv/bin/python -m scripts.sales.rw_zebra_kg_test_dashboard --list
```

(Top by VC density: cost-management 31, saas-sales 28, social-media 27, dynamic-comments 23, hr-analytics 23, consolidated-financials 22.)

**Source corpus:** `data/zebra_kg/infrastructure/raw_configs.jsonl` — 360 rows, one per Zebra visualContainer across all 20 templates.

**Atlases (reference docs):**

- `docs/sales/RW_ZEBRA_BI_INFRASTRUCTURE_ATLAS.md` — source-side cellular RE
- `docs/sales/RW_POWER_BI_NATIVE_INFRASTRUCTURE_ATLAS.md` — target-side; §6 has the translation matrix; §3-§5 cover TMDL / theme / PBIR shape

---

## Two paths, pick one

### Path A — Light: 20 reports bound to RW dataset (broken refs)

Cheap and fast. Each translated report points at the existing `sm_sales_kpis_rw` semantic model. Visuals render structurally; cells show "Missing_References". **Demonstrates the translator's reach but doesn't actually render data.**

Effort: ~1 hour. Just generalize what `rw_zebra_kg_test_dashboard.py` already does, loop it 20 times, push each as a separate Fabric Report item. Optional polish: bundle all 20 into a single 20-page report.

### Path B — Full: 20 reports + 20 matching semantic models (RECOMMENDED)

For each template, also publish a fresh SemanticModel built from `data/zebra_kg/schemas/<slug>/`. The translated report binds to its own model. Measures resolve. Cells render real values (or BLANK if no data — see "Data fidelity" below).

Effort: ~3-5 hours. The TMDL emitter is the meat of this.

**Andre wants Path B.** Path A is the fallback if Path B blocks.

---

## Path B — Detailed task list

### B1. TMDL emitter — `scripts/sales/rw_zebra_kg_tmdl_emit.py`

Reads `data/zebra_kg/schemas/<slug>/` and emits the TMDL parts a Fabric SemanticModel `items` POST expects:

```
definition.pbism                       # version: 4.0, defaultMode: import (or directQuery=null)
definition/database.tmdl               # `database <name>` + compatibility level 1567
definition/model.tmdl                  # `model Model` + cultures + annotations
definition/cultures/en-US.tmdl         # culture 'en-US' + linguisticMetadata
definition/tables/<table>.tmdl         # one per table — see below
definition/relationships.tmdl          # one entry per relationship, fromColumn / toColumn / cardinality
.platform                              # type: SemanticModel + displayName
```

Per-table TMDL shape:

```tmdl
table 'TableName'

	column 'ColumnName'
		dataType: string  ; or int64, double, dateTime, decimal
		summarizeBy: none
		sourceColumn: 'ColumnName'
		annotation SummarizationSetBy = Automatic

	measure 'MeasureName' = <DAX expression from measures.csv>
		formatString: <format_string from measures.csv, if non-empty>

	partition 'TableName-partition' = m
		mode: import
		source =
			let Source = #table({"ColumnName"}, {}) in Source
```

Notes:

- Use empty M `#table({...}, {})` partitions per table. No source data — measures will evaluate to BLANK but the model is structurally complete and the visuals render without ref errors.
- `model.json` in each schema has full `tables: [{name, columns: [{name, dataType, sourceColumn}], measures: [{name, expression, formatString}]}]` and `relationships: [{name, fromTable, fromColumn, toTable, toColumn, fromCardinality, toCardinality, crossFilteringBehavior}]`. Use it directly.
- Measure DAX may reference tables/columns by single quotes already; do not re-quote.
- DAX expressions in measures.csv may have embedded newlines; preserve them — TMDL multi-line measures use `=` followed by indented body.

Reference TMDL grammar: <https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview>. Keep compatibility level at 1567 (modern) and disable AutoExists if `model.json` says so.

### B2. SemanticModel publisher — extend the same CLI

POST `/v1/workspaces/{ws}/items` with `type: "SemanticModel"`, multipart definition base64-encoded. Same auth flow as the Reports API:

```python
from azure.identity import AzureCliCredential
tok = AzureCliCredential().get_token("https://api.fabric.microsoft.com/.default").token
```

Body shape (the LRO pattern is already in `scripts/sales/rw_inventory_measures.py:_wait_lro` — reuse):

```python
body = {
    "displayName": f"sm_zbr_{slug}",
    "type": "SemanticModel",
    "definition": {"parts": [{"path": p, "payload": b64, "payloadType": "InlineBase64"} for ...]},
}
resp = requests.post(f"{FABRIC}/v1/workspaces/{WORKSPACE_ID}/items", headers=..., json=body)
new_model = wait_lro(resp, tok)  # returns the created item with id
```

Capture the new model's `id`. The next step's `definition.pbir` needs it.

### B3. Per-template Report publisher — bind to the new model

The report's `definition.pbir` has a `byConnection.connectionString` like:

```
Data Source="powerbi://api.powerbi.com/v1.0/myorg/<workspace_name>";initial catalog=sm_zbr_<slug>;integrated security=ClaimsToken;semanticmodelid=<new_id>
```

Fetch the workspace's display name once via `GET /v1/workspaces/{id}` (the slug after `myorg/` is the workspace's `displayName`). Then build connectionString per template.

Then translate the template's raw*configs (you already know how — `rw_zebra_kg_test_dashboard.py` does it for one), wrap as `report.json`, build `.platform` with `displayName: f"zbr*{slug}"`, push as type=Report.

### B4. Bulk runner

```python
for slug in TEMPLATES:
    sm_id = publish_semantic_model(slug)
    rpt_id = publish_report(slug, sm_id)
    print(f"{slug:50s} sm={sm_id} rpt=https://app.fabric.microsoft.com/groups/{ws}/reports/{rpt_id}")
```

Idempotency: check whether a SemanticModel/Report with the target displayName already exists in the workspace (`GET /v1/workspaces/{ws}/items?type=SemanticModel`); if yes, call `updateDefinition` instead of `items` POST.

Output a summary file at `data/zebra_kg/published/all_templates.json` mapping `slug -> {semantic_model_id, report_id, url, vc_count, measure_count}`.

### B5. Test pushes — start with 1, then 3, then 20

1. Smoke one template end-to-end (recommend `consolidated-financials-power-bi-template` — already E2E-validated).
2. Verify in Fabric: open URL, confirm no "field not found" errors on the measure refs (cells will be BLANK if no data — that's expected and correct).
3. Run on 3 more, spot-check.
4. Run all 20.

---

## Data fidelity caveat

Empty M partitions = measures evaluate to BLANK. Visuals render structurally with all the IBCS column synthesis, dataBars, composite cards, waterfallChart, etc. — but with no numeric data.

**This is what Andre is asking for.** He wants to see the translator's output rendered without ref errors. The data layer is not in scope. If he wants real data, that's a Phase 2 conversation about importing each Zebra PBIX's data tables into the matching semantic model.

If you can cheaply do better — e.g., the source PBIX files (`~/Downloads/rw-zebra-bi-template-research-20260509/files/`) contain the Zebra-published sample data — extracting one table as M-literal `#table({col1, col2}, {{1, 2}, ...})` is doable but multiplies the work. Default: BLANK is fine.

---

## Workspace + auth

- Workspace: `b66233d5-9d4a-44ba-89a8-b70206d98ae7` (F64, `Salesforce Analytics - Sales Manager`)
- Auth: `az login` already done; `AzureCliCredential` works inside `.venv`. See `scripts/sales/rw_inventory_measures.py:_token`.
- Existing test report: `fb0d5b21-5164-4d5e-9e3a-6de6fcf4d1a8` (`displayName: "test"`). You can either reuse this as the cost-management slot or delete it via `DELETE /v1/workspaces/{ws}/items/{id}` and let your CLI create a fresh `zbr_cost-management` report.
- Existing RW report (DO NOT TOUCH): `d7362a11-f3dd-4bd1-a69a-68c941c2598b` (`rpt_vp_ops_scorecard`). It powers the live VP Ops scorecard.
- Existing RW semantic model (DO NOT TOUCH): `sm_sales_kpis_rw` / `3c58b5dd-b321-4aaa-a5cd-fb73e474edbb`.

---

## Testing

Before pushing 20: write a TMDL emitter test that round-trips one schema (`data/zebra_kg/schemas/cost-management-power-bi-template/model.json`) → TMDL parts → parses back via grep on column/measure declarations. Don't try to validate TMDL semantics in Python — let Fabric reject if it's wrong.

Existing 151 track:rw tests must stay green:

```bash
.venv/bin/pytest tests/sales/ --ignore=tests/sales/test_rw_zebra_kg_translator_e2e.py
```

---

## Acceptance criteria

1. ✅ `scripts/sales/rw_zebra_kg_publish_all_templates.py` exists.
2. ✅ Running it produces 20 SemanticModels + 20 Reports in workspace `b66233d5-…`, named `sm_zbr_<slug>` / `zbr_<slug>`.
3. ✅ At least 18 of 20 reports open in Fabric without "field not found" errors. (Allow up to 2 to fail gracefully — translator already handles that; just log + continue.)
4. ✅ `data/zebra_kg/published/all_templates.json` summary written.
5. ✅ A short followup commit on `feat/track-rw-tooling` adds the CLI + a one-line `make publish-all-zebra` target if the repo has a Makefile.
6. ✅ Existing tests stay green; one new test confirms TMDL emitter round-trips one schema.

When done, append a "✅ all 20 published" line to this handoff doc with the date + list of 20 URLs.

---

## Quick start

```bash
cd ~/code/apps/sales-ops-copilot-rw
git checkout feat/track-rw-tooling && git pull
.venv/bin/pytest tests/sales/ --ignore=tests/sales/test_rw_zebra_kg_translator_e2e.py  # baseline 151 green

# Read the translator + ibcs_synth to ground yourself (~600 lines total)
$EDITOR scripts/sales/rw_zebra_kg_translator.py scripts/sales/rw_zebra_kg_ibcs_synth.py

# Read the per-template schema for one slug
ls data/zebra_kg/schemas/cost-management-power-bi-template/
cat data/zebra_kg/schemas/cost-management-power-bi-template/model.json | jq '.tables[0]'

# Read the existing single-template harness
$EDITOR scripts/sales/rw_zebra_kg_test_dashboard.py

# Probe an existing SemanticModel's TMDL shape for reference
.venv/bin/python -c "
import base64, requests, time, json
from scripts.sales.rw_inventory_measures import _token, FABRIC, WORKSPACE_ID, SEMANTIC_MODEL_ID
tok = _token()
r = requests.post(f'{FABRIC}/v1/workspaces/{WORKSPACE_ID}/semanticModels/{SEMANTIC_MODEL_ID}/getDefinition',
                  headers={'Authorization': f'Bearer {tok}'})
op = r.headers['x-ms-operation-id']
while True:
    time.sleep(2)
    if requests.get(f'{FABRIC}/v1/operations/{op}', headers={'Authorization': f'Bearer {tok}'}).json().get('status')=='Succeeded': break
res = requests.get(f'{FABRIC}/v1/operations/{op}/result', headers={'Authorization': f'Bearer {tok}'}).json()
for p in res['definition']['parts']:
    if p['path'].endswith('.tmdl'):
        print('===', p['path'], '===')
        print(base64.b64decode(p['payload']).decode()[:1000])
        print()
" | head -100
```

Ship it.
