# Agent 6 — LLM-Assisted Decompilation Pipeline for tcaddin.dll

**Mission:** design an executable LLM-assisted decompilation pipeline that emits a searchable, semantically-labeled function map of `tcaddin.dll` (Windows COM DLL, ARM64 + x86_64, 5–20 MB, C++ with RTTI), runnable on macOS M4 Max for the LLM stage, with cost-per-run under $100.

**Date:** 2026-05-01
**Author:** research-swarm agent-6
**Status:** decision-ready, not yet executed

---

## 1. SOTA tool survey (April 2026)

### 1.1 Decompiler-quality matrix

| Tool                                   | Cost (1 yr)                                                              | OSS       | x86_64 PE                         | ARM64 PE                                                              | C++ class recovery                                                                                                         | LLM hooks                                                                                                                    | Notes                                                                                                                                                                                                            |
| -------------------------------------- | ------------------------------------------------------------------------ | --------- | --------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Ghidra 11.x**                        | $0                                                                       | yes (NSA) | excellent                         | very good (sometimes beats Hex-Rays per Hex-Rays' own ARM comparison) | built-in `RecoverClassesFromRTTIScript` for MSVC RTTI; community `Ghidra-Cpp-Class-Analyzer` for richer GCC/Itanium models | headless + GhidraMCP / pyghidra-mcp / OGhidra / DAILA                                                                        | the workhorse choice; only viable free path for ARM64 PE                                                                                                                                                         |
| **IDA Pro 9.2 + Hex-Rays decompilers** | ~$3k–20k+ (named license, decompilers extra; Vendr median ~$20k/yr)      | no        | gold standard                     | gold standard                                                         | best type inference + COM type libs in industry                                                                            | IDAssist (free plugin, BYO key), aiDAPal (free, fine-tuned mistral-7b), RevEng.AI plugin, IDA Pro MCP, IDA Chat (Claude SDK) | only worth it if budget exists; the Hex-Rays gooMBA plugin is unique for MBA deobfuscation if think-cell ships obfuscated math                                                                                   |
| **Binary Ninja + Sidekick 5.0**        | $300/yr Binja + $290/yr Sidekick non-commercial (~$590); commercial ~2×) | no        | very good                         | good                                                                  | reasonable                                                                                                                 | tightly integrated, BNQL query language, "active collaboration" mode auto-queues analyses, Notebook knowledge store          | best UX for "just give me an AI-assisted RE workstation"; weaker than IDA on COM/MSVC type recovery                                                                                                              |
| **RevEng.AI (cloud)**                  | enterprise quote (not public; $4.15M seed 2025)                          | no        | yes                               | partial                                                               | function similarity, AI decompile of selected functions                                                                    | IDA + Ghidra plugins                                                                                                         | strong for _binary similarity_ across a corpus (e.g., "find this function in another DLL") — useful if you ever need to diff tcaddin across versions; not the primary decompile engine                           |
| **DecompAI** (LangGraph + Gradio)      | $0                                                                       | yes       | x86 Linux only today              | no                                                                    | none                                                                                                                       | conversational ReAct agent driving Ghidra/gdb/objdump                                                                        | nice teaching tool, wrong fit for ARM64 PE COM DLL                                                                                                                                                               |
| **LLM4Decompile (9B-v2 / -Ref)**       | $0 (model weights free, GPU compute on M4 Max)                           | yes       | trained on Linux x86_64 GCC O0–O3 | no first-party support                                                | n/a                                                                                                                        | feeds Ghidra output back into a 9B fine-tune for refinement (+16.2% vs end-to-end)                                           | use as an **optional refinement pass** on Ghidra output for function bodies where the C looks rough; recompile rate still only ~17% per DecLLM ISSTA 2025                                                        |
| **DeGPT** (NDSS 2024)                  | $0 (paper + code)                                                        | yes       | n/a                               | n/a                                                                   | n/a                                                                                                                        | three-role (referee/advisor/operator) framework on top of any LLM                                                            | more a _prompting recipe_ than a tool; readability +24%, semantics drift in ~93% of LLM4Decompile-generated functions per DecLLM benchmark — keep DeGPT as a labeling-prompt pattern, not a code-generation step |
| **OOAnalyzer (Pharos / CERT)**         | $0                                                                       | yes       | yes (MSVC 32-bit only)            | **no**                                                                | best-in-class for 32-bit MSVC C++                                                                                          | exports JSON, imports into Ghidra/IDA                                                                                        | 32-bit x86 only — does not apply to a 64-bit ARM64+x64 tcaddin                                                                                                                                                   |
| **DAILA**                              | $0                                                                       | yes       | n/a                               | n/a                                                                   | n/a                                                                                                                        | decompiler-agnostic plugin (Ghidra/IDA/Binja) for GPT-4/Claude/local LLMs                                                    | useful as the _interactive_ layer once the corpus exists                                                                                                                                                         |
| **ghidrecomp** (clearbluejar)          | $0                                                                       | yes       | yes                               | yes                                                                   | inherits Ghidra                                                                                                            | CLI wrapper over pyghidra; emits per-function `.c` files + call graphs                                                       | this is the recommended bulk-decompile driver                                                                                                                                                                    |
| **pyghidra-mcp** (clearbluejar)        | $0                                                                       | yes       | yes                               | yes                                                                   | inherits Ghidra                                                                                                            | headless MCP server exposing the project to any MCP-aware LLM (Claude Code, Codex, etc.)                                     | wire this in _after_ the bulk pass for human-in-the-loop drilldown                                                                                                                                               |

**Bottom line for tcaddin.dll:** Ghidra (decompile + RTTI) → ghidrecomp (bulk export) → Claude Opus 4.7 batch (label) → SQLite + sqlite-vec (search) is the OSS-first recommended stack. IDA Pro is the upgrade lever if you have the budget and you're going to do this for >1 binary or want COM type-library quality.

### 1.2 Why not Hex-Rays for the bulk pass

Three reasons even though Hex-Rays' decompiler is strictly better:

1. Hex-Rays' own docs note **Ghidra sometimes outperforms on ARM**; the gap is smallest exactly in the architecture you most care about for ARM64 Office.
2. Cost-per-run < $100 is incompatible with a $20k/yr seat unless that seat already exists.
3. The pipeline's value is in the LLM-labeling layer, not the last 10% of decompile fidelity. A "good" pseudo-C from Ghidra labels almost as well as a "great" pseudo-C from Hex-Rays under Claude Opus.

If Andre already has Hex-Rays available, swap step 2 (decompile) for IDA + `ida_hexrays.decompile()` via idapython — the rest of the pipeline is identical.

---

## 2. Recommended pipeline

```
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 0  Acquire binary + symbol material              │
            │  - tcaddin.dll (x64 + ARM64), .pdb if obtainable        │
            │  - sha256 + version stamp for provenance                │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 1  Headless analysis (Windows VM or macOS)       │
            │  Tool: Ghidra 11.x analyzeHeadless                      │
            │  Pre-script: load PDB if present                        │
            │  Auto-analysis: full + Decompiler Parameter ID +        │
            │                 RTTI + DWARF/PDB                        │
            │  Post-script: RecoverClassesFromRTTIScript              │
            │               + Ghidra-Cpp-Class-Analyzer plugin        │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 2  Bulk decompile + metadata export              │
            │  Tool: ghidrecomp (pyghidra) OR custom export.py        │
            │  Output: per-function JSONL with                        │
            │   {addr, name, signature, c_code, callers, callees,     │
            │    section, size, has_rtti, vtable_addr, parent_class}  │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 3  Filter & shard                                │
            │  - drop CRT/MFC/ATL/STL boilerplate (allow-list by      │
            │    name pattern + size + flags)                         │
            │  - shard into batches sized to fit Claude Opus 4.7      │
            │    1M-context input with prompt caching                 │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 4  LLM labeling (macOS M4 Max)                   │
            │  Primary: Claude Opus 4.7 via Anthropic Batch API       │
            │           (50% off, 1M context, prompt caching 90% off) │
            │  Secondary: Claude Haiku 4.5 for triage (25× cheaper)   │
            │  Fallback: GPT-5.x via Azure OpenAI                     │
            │  Local QA: qwen2.5:72b on Ollama for spot-check         │
            │  Output per fn: {summary, keywords[], class_guess,      │
            │                  confidence, suspected_subsystem}       │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 5  Embed + index                                 │
            │  Embeddings: text-embedding-3-large (Azure) or          │
            │              local nomic-embed-text via Ollama          │
            │  Storage: SQLite + sqlite-vec + FTS5 (hybrid search)    │
            │  Optional: LanceDB if multi-DLL corpus                  │
            └─────────────────────────────────────────────────────────┘
                                    │
                                    ▼
            ┌─────────────────────────────────────────────────────────┐
            │  STAGE 6  Query surface                                 │
            │  - CLI: `tcaddin-q "where is chart construction?"`      │
            │  - MCP: pyghidra-mcp for live drilldown in Claude Code  │
            └─────────────────────────────────────────────────────────┘
```

### 2.1 Why Ghidra headless on a Windows VM (Parallels) is fine

`analyzeHeadless` runs on macOS natively too, but the Windows VM gives access to a real `mscoree.dll` / `oleaut32.dll` / Office type libraries on disk for symbol resolution and PDB matching. Either works; pick the VM if you can mount think-cell's installed Office and let Ghidra reference the local Office type libs via `loadAndImport`.

### 2.2 Cost estimate per run (single tcaddin.dll, both arches)

Assumptions: ~12,000 functions per arch after CRT/MFC filtering (binary is 5–20MB; benchmark binaries of similar size yield 8k–15k Ghidra-recognized functions); average decompiled function ≈ 600 input tokens; output summary ≈ 250 tokens.

| Stage                                           | Tokens/run                                | Model                  | List rate               | Effective rate (cache + batch)                                                                                            | $           |
| ----------------------------------------------- | ----------------------------------------- | ---------------------- | ----------------------- | ------------------------------------------------------------------------------------------------------------------------- | ----------- |
| Stage 4 main label, 24k funcs                   | 24k × 600 = 14.4M in; 24k × 250 = 6M out  | Claude Opus 4.7        | $15 in / $75 out per 1M | Batch 50% + cache hit on shared system prompt = ~$7.50 in (with 90% cache after first batch ≈ ~$2 effective) / $37.50 out | ~$28–55     |
| Stage 4 triage (Haiku first pass for filtering) | 24k × 600 = 14.4M in; 24k × 80 = 1.9M out | Claude Haiku 4.5       | $1 / $5                 | batch+cache → ~$0.50 / $2.50                                                                                              | ~$5         |
| Stage 5 embeddings                              | 24k × 250 = 6M tokens                     | text-embedding-3-large | $0.13/1M                | n/a                                                                                                                       | ~$0.80      |
| **Total**                                       |                                           |                        |                         |                                                                                                                           | **~$35–60** |

Comfortably under $100 even without the Haiku triage step. If you skip Haiku and go Opus-only, it's still ≈$55. Re-runs are cheaper because the system prompt + few-shot examples cache hits at 90% off after the first batch.

---

## 3. Concrete commands & code

### 3.1 Ghidra headless decompile + JSON export

`tools/ghidra/decompile_export.py` (Ghidra Python 2 / Jython script — works in `analyzeHeadless`):

```python
# decompile_export.py — Ghidra postScript
import json, os
from ghidra.app.decompiler import DecompInterface, DecompileOptions
from ghidra.util.task import ConsoleTaskMonitor

OUT = os.environ.get("DECOMPILE_OUT", "/tmp/tcaddin.jsonl")
TIMEOUT = 120  # seconds per function

prog = currentProgram
fm = prog.getFunctionManager()
sm = prog.getSymbolTable()
decomp = DecompInterface()
opts = DecompileOptions()
opts.grabFromProgram(prog)
decomp.setOptions(opts)
decomp.openProgram(prog)
monitor = ConsoleTaskMonitor()

with open(OUT, "w") as f:
    for func in fm.getFunctions(True):
        if func.isThunk() or func.isExternal():
            continue
        addr = func.getEntryPoint().toString()
        name = func.getName()
        sig  = func.getPrototypeString(False, False)
        size = int(func.getBody().getNumAddresses())
        callers = [c.getEntryPoint().toString() for c in func.getCallingFunctions(monitor)]
        callees = [c.getEntryPoint().toString() for c in func.getCalledFunctions(monitor)]
        ns   = func.getParentNamespace().getName(True)  # picks up RTTI class
        res  = decomp.decompileFunction(func, TIMEOUT, monitor)
        c_code = res.getDecompiledFunction().getC() if res and res.decompileCompleted() else None
        rec = {
            "addr": addr, "name": name, "signature": sig, "size": size,
            "namespace": ns, "callers": callers, "callees": callees,
            "section": prog.getMemory().getBlock(func.getEntryPoint()).getName(),
            "c_code": c_code,
        }
        f.write(json.dumps(rec) + "\n")
```

Run it (Windows or macOS):

```bash
# Set GHIDRA_INSTALL_DIR first
export GHIDRA_INSTALL_DIR="/Applications/ghidra_11.3_PUBLIC"
PROJ=/tmp/tcaddin_proj
BIN=/path/to/tcaddin.dll
mkdir -p "$PROJ"

DECOMPILE_OUT=/tmp/tcaddin.jsonl \
"$GHIDRA_INSTALL_DIR/support/analyzeHeadless" \
  "$PROJ" tcaddin_x64 \
  -import "$BIN" \
  -postScript RecoverClassesFromRTTIScript.java \
  -postScript decompile_export.py \
  -scriptPath /path/to/tools/ghidra \
  -deleteProject
```

For ARM64, repeat with the ARM64 build of tcaddin.dll. Ghidra autodetects PE+ARM64.

If you prefer Python 3 + pyghidra (cleaner on macOS):

```bash
pip install pyghidra ghidrecomp
ghidrecomp tcaddin.dll --output ./decomp_out --skip-cache=False --max-workers=8
```

`ghidrecomp` writes one `.c` per function plus call graphs; convert to JSONL with a 30-line glue script.

### 3.2 Python orchestrator — Claude Opus batch labeling

`tools/llm/label_functions.py`:

````python
# label_functions.py
# uv run python label_functions.py decomp.jsonl labels.jsonl
import json, sys, hashlib
from pathlib import Path
import anthropic

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY env

SYSTEM = """You are a senior reverse engineer labeling decompiled C functions
from a Windows COM DLL (think-cell add-in for PowerPoint/Excel).
For each function, return a single-line JSON with these fields:
  summary       (<=160 chars, plain English, what it does)
  keywords      (3-8 lowercase tokens, snake_case, e.g. chart_layout, com_idispatch)
  subsystem     (one of: chart_construction, layout_engine, data_binding,
                 com_plumbing, ui_ribbon, persistence, drawing, hooking,
                 string_utils, math, crt, unknown)
  class_guess   (best-guess C++ class or "")
  confidence    (low|medium|high)
Return ONLY the JSON object, no prose."""

FEW_SHOT = [
    {"role":"user","content":"<example function 1>"},
    {"role":"assistant","content":'{"summary":"...","keywords":["..."],"subsystem":"...","class_guess":"","confidence":"medium"}'},
]

def label_batch(records, model="claude-opus-4-7"):
    requests = []
    for r in records:
        if not r.get("c_code"):
            continue
        prompt = f"Function name: {r['name']}\nNamespace: {r['namespace']}\n" \
                 f"Signature: {r['signature']}\nCallers: {len(r['callers'])} " \
                 f"Callees: {len(r['callees'])}\n\n```c\n{r['c_code'][:8000]}\n```"
        requests.append({
            "custom_id": r["addr"],
            "params": {
                "model": model,
                "max_tokens": 400,
                "system": [{"type":"text","text":SYSTEM,"cache_control":{"type":"ephemeral"}}],
                "messages": FEW_SHOT + [{"role":"user","content":prompt}],
            }
        })
    batch = client.messages.batches.create(requests=requests)
    return batch.id

if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    records = [json.loads(l) for l in src.open()]
    # chunk to <=100k requests / <=256MB
    CHUNK = 5000
    for i in range(0, len(records), CHUNK):
        bid = label_batch(records[i:i+CHUNK])
        print(f"submitted batch {bid} ({i}..{i+CHUNK})")
````

Poll + retrieve later:

```python
batch = client.messages.batches.retrieve(bid)
if batch.processing_status == "ended":
    for line in client.messages.batches.results(bid):
        addr = line.custom_id
        try:
            payload = json.loads(line.result.message.content[0].text)
            payload["addr"] = addr
            dst.write(json.dumps(payload) + "\n")
        except Exception as e:
            errors.append((addr, str(e)))
```

### 3.3 SQLite + sqlite-vec + FTS5 schema

```sql
-- schema.sql — apply with: sqlite3 tcaddin.db < schema.sql
CREATE TABLE function (
    addr            TEXT PRIMARY KEY,         -- e.g. "180001a40"
    arch            TEXT NOT NULL,            -- 'x64' or 'arm64'
    binary_sha256   TEXT NOT NULL,
    name            TEXT,
    signature       TEXT,
    namespace       TEXT,
    section         TEXT,
    size_bytes      INTEGER,
    callers_json    TEXT,                     -- JSON array of addrs
    callees_json    TEXT,
    c_code          TEXT,
    summary         TEXT,
    subsystem       TEXT,
    class_guess     TEXT,
    confidence      TEXT,
    keywords_json   TEXT,
    label_model     TEXT,
    labeled_at      TEXT
);

-- Full-text search over the human-readable fields.
CREATE VIRTUAL TABLE function_fts USING fts5(
    name, signature, namespace, summary, keywords, c_code,
    content='function', content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Vector search (load sqlite-vec extension first).
-- 1024-dim because text-embedding-3-large default; use 768 for nomic-embed-text.
CREATE VIRTUAL TABLE function_vec USING vec0(
    addr TEXT PRIMARY KEY,
    embedding FLOAT[1024]
);

-- Triggers to keep FTS in sync.
CREATE TRIGGER function_ai AFTER INSERT ON function BEGIN
    INSERT INTO function_fts(rowid, name, signature, namespace, summary, keywords, c_code)
    VALUES (new.rowid, new.name, new.signature, new.namespace, new.summary,
            new.keywords_json, new.c_code);
END;
```

Hybrid query (the workhorse):

```sql
WITH kw AS (
    SELECT rowid, bm25(function_fts) AS score
    FROM function_fts WHERE function_fts MATCH ?
),
vec AS (
    SELECT addr, distance FROM function_vec
    WHERE embedding MATCH ? AND k = 50
)
SELECT f.addr, f.name, f.summary, f.subsystem,
       COALESCE(kw.score, 999) AS bm25,
       COALESCE(vec.distance, 1.0) AS vdist
FROM function f
LEFT JOIN kw  ON kw.rowid = f.rowid
LEFT JOIN vec ON vec.addr = f.addr
WHERE kw.rowid IS NOT NULL OR vec.addr IS NOT NULL
ORDER BY (0.4 * vdist) + (0.6 * (bm25 / 50.0)) ASC
LIMIT 20;
```

The first parameter is the FTS5 query (e.g., `chart NEAR/5 construct`); the second is the embedding of the natural-language question.

---

## 4. tcaddin.dll-specific recommendations

### 4.1 C++ class recovery — best tool

| Option                                  | Verdict                                                                                                                                                                                                                                                                               |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ghidra `RecoverClassesFromRTTIScript`   | **Use this first.** MSVC RTTI is present per the problem statement; the script walks RTTI Type Descriptors / Class Hierarchy Descriptors and lays down vftables + class namespaces. Known issue #8853 with negative vftable offsets exists — handle by skipping rather than aborting. |
| `Ghidra-Cpp-Class-Analyzer` (astrelsky) | **Add as second pass.** Better for inheritance trees (virtual + multiple). Gives you the tree-style hierarchy that helps Stage 4's `class_guess`.                                                                                                                                     |
| OOAnalyzer                              | **Skip.** 32-bit MSVC only — wrong arch.                                                                                                                                                                                                                                              |
| IDA Pro                                 | If available, its MSVC class recovery is the most reliable; the type-library mechanism also auto-applies COM interface signatures (`IDispatch::Invoke`, `IUnknown::QueryInterface`) which is exactly what tcaddin needs.                                                              |

### 4.2 Vtable extraction

Ghidra's RTTI script gives you vtables for free in the Symbol Tree under `<class>::vftable`. Extract them in Stage 2 by walking `prog.getSymbolTable().getSymbols("vftable")` and following data references. For each vftable, list the function pointer at every slot — this gives the LLM strong "who is dispatched here" signal for COM virtual calls.

### 4.3 Hex-Rays-quality OSS decompile?

Closest free alternative: **Ghidra + LLM4Decompile-Ref-9B-v2 refinement pass** on the rough functions. Pipeline: Ghidra produces pseudo-C → for any function where readability is weak (heuristic: `goto` count > 5, or `*(undefined8 *)` casts > 3), pipe through LLM4Decompile-Ref locally on the M4 Max GPU. The published paper claims +16.2% over end-to-end LLM4Decompile and Ghidra alone; ISSTA 2025 (DecLLM) tempers this — only ~17% recompile success — but for _human readability_, the lift is real.

Note: LLM4Decompile is trained on x86_64 Linux GCC. **Do not use it for ARM64 PE** — it will hallucinate confidently. For ARM64, stick with raw Ghidra and lean harder on the LLM-labeling step instead of trying to re-write the C.

### 4.4 Should you buy IDA Pro?

**Probably no, for this single task.** Reasons:

- Ghidra's ARM64 output is competitive (Hex-Rays' own docs concede this).
- The labeling layer (Stage 4) is the differentiator, and Claude Opus 4.7 reads Ghidra output fine.
- $20k median annual seat dwarfs the $35–60 per-run pipeline cost by 300×.

**Buy IDA if:**

- You will reverse multiple binaries per quarter and the cumulative time savings clear $20k.
- You need clean COM type library auto-application out-of-the-box (Ghidra requires manual import).
- You hit MBA-obfuscated arithmetic in tcaddin (gooMBA is unique to IDA).

**Compromise:** start with Ghidra; if you're consistently re-doing manual COM type fixup, buy IDA Home ($365/yr) for personal projects, decompiler add-on extra. IDA Pro Cloud Decompiler tier (~$3k) is the cheapest pro entry point.

---

## 5. Output schema (canonical, SQLite)

See section 3.3. Top-level intent:

- `function` is the source of truth — one row per function per arch.
- `function_fts` is the keyword search.
- `function_vec` is the semantic search.
- The hybrid query in 3.3 lets a human or LLM ask _"where is the chart construction code?"_ and get the top-20 candidates ranked by combined BM25 + cosine similarity.

If the corpus grows beyond a single DLL (e.g., diffing tcaddin v13 vs v14, or adding `tcppt.dll`), migrate to **LanceDB** — same schema concept, but its multi-table + Arrow-native columnar storage scales better than SQLite once you cross ~1M rows or want cross-binary similarity queries.

---

## 6. Risk register

| Risk                                                                                                                                                       | Likelihood | Impact | Mitigation                                                                                                                                                                                                                                                                                                                                                                     |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **LLM hallucinates function purpose**                                                                                                                      | high       | medium | (1) Two-pass: Haiku triage → Opus only on uncertain (`confidence != high`) functions. (2) Ground every label in _callers/callees + namespace + nearby strings_ in the prompt. (3) Surface `confidence` in the schema; never present low-confidence labels as fact. (4) Spot-check 2% with local qwen2.5:72b — if disagreement rate >10%, re-run with a stricter system prompt. |
| **think-cell has shipped obfuscation** (their job posting + `CFindCodePattern` hints suggest active anti-tamper / pattern matching, not heavy obfuscation) | medium     | high   | Run Ghidra deobfuscation passes; if MBA expressions appear, that's the case for IDA + gooMBA. Detect by counting suspicious arithmetic chains in Stage 3.                                                                                                                                                                                                                      |
| **Symbols stripped, RTTI present** (the problem statement)                                                                                                 | certain    | low    | RTTI gives class names + vtables — the hardest 60% is solved. The remaining 40% (free functions, statics) is where LLM labeling earns its keep.                                                                                                                                                                                                                                |
| **ARM64 decompile quality lower than x64**                                                                                                                 | medium     | medium | Cross-reference: label both arches, then _for matching functions_ use the x64 label as a prior on the ARM64 label. Use RevEng.AI binary similarity (free tier) to pair x64↔ARM64 functions across builds.                                                                                                                                                                      |
| **Function explosion (>50k functions)**                                                                                                                    | low        | medium | The 24k estimate is for a 20MB binary post-CRT-filter. If you see 50k+, add a stricter filter (size ≥ 16 bytes, ≥ 1 caller, not in `.rdata` thunks) before Stage 4 — labeling 50k × Opus is ~$110, breaks budget.                                                                                                                                                              |
| **Anthropic batch results expire (24h)**                                                                                                                   | low        | low    | Persist `batch_id` to disk; have the orchestrator poll-and-resume.                                                                                                                                                                                                                                                                                                             |
| **Ghidra `RecoverClassesFromRTTIScript` crashes** (issue #8853)                                                                                            | medium     | low    | Wrap in try/except in postScript; fall back to per-class analysis loop.                                                                                                                                                                                                                                                                                                        |
| **PDB unavailable**                                                                                                                                        | high       | low    | Plan for it — pipeline does not require PDB; symbols stripped is the assumed condition. PDB if available is a bonus.                                                                                                                                                                                                                                                           |
| **Anti-debug / packed loader**                                                                                                                             | low        | high   | Validate by `binwalk` + entropy scan before Stage 1; if entropy > 7.0 across most of the binary, you have packing — handle with manual unpacking before Ghidra. think-cell does not historically pack.                                                                                                                                                                         |
| **Cost overrun (single function decompile pathological)**                                                                                                  | low        | low    | Set per-request `max_tokens=400`; truncate input C at 8KB (covers 99.5% of functions); separately label monsters with chunked prompts.                                                                                                                                                                                                                                         |

---

## 7. Execution checklist

1. Verify Ghidra 11.3+ installed; install `Ghidra-Cpp-Class-Analyzer` extension.
2. `pip install pyghidra ghidrecomp anthropic sqlite-vec` (sqlite-vec via `uv add` or vendored loadable extension).
3. Acquire tcaddin.dll x64 + ARM64 builds; sha256 + record version.
4. Stage 1 + 2: run `analyzeHeadless` per arch with `decompile_export.py`. Expect 30–90 min per arch on M4 Max.
5. Stage 3: filter JSONL to drop CRT/MFC/ATL boilerplate (regex on `name` + `namespace`).
6. Stage 4: submit Anthropic batch; expect 1–4h turnaround. Persist batch IDs.
7. Stage 5: embed labels with `text-embedding-3-large` (or local `nomic-embed-text` for $0); insert into SQLite.
8. Stage 6: ship a 50-line CLI that takes a natural-language query, embeds it, runs the hybrid SQL, returns the top-20 with `addr`, `name`, `summary`, `subsystem`.
9. Hook `pyghidra-mcp` into Claude Code for live drilldown ("show me the disassembly at 180004a30").

Total wall-clock for one full run: **4–8 hours**, of which ~1 hour is human attention (kicking off stages, sanity-checking labels). Total $: **$35–60**.

---

## 8. Sources

- [Ghidra Headless Analyzer README](https://static.grumpycoder.net/pixel/support/analyzeHeadlessREADME.html)
- [galoget/ghidra-headless-scripts](https://github.com/galoget/ghidra-headless-scripts)
- [clearbluejar/ghidrecomp](https://github.com/clearbluejar/ghidrecomp)
- [pyghidra-mcp announcement](https://clearbluejar.github.io/posts/pyghidra-mcp-headless-ghidra-mcp-server-for-project-wide-multi-binary-analysis/)
- [HackOvert/GhidraSnippets](https://github.com/HackOvert/GhidraSnippets)
- [Tenable: Extracting Ghidra Decompiler Output with Python](https://medium.com/tenable-techblog/extracting-ghidra-decompiler-output-with-python-a737e9ed8fce)
- [astrelsky/Ghidra-Cpp-Class-Analyzer](https://github.com/astrelsky/Ghidra-Cpp-Class-Analyzer)
- [Ghidra RTTI Analysis discussion #3213](https://github.com/NationalSecurityAgency/ghidra/discussions/3213)
- [Ghidra issue #8853 — RecoverClassesFromRTTIScript exception](https://github.com/NationalSecurityAgency/ghidra/issues/8853)
- [SEI CMU OOAnalyzer](https://www.sei.cmu.edu/blog/using-ooanalyzer-to-reverse-engineer-object-oriented-code-with-ghidra/)
- [cmu-sei/pharos](https://github.com/cmu-sei/pharos)
- [Hex-Rays IDA Pro](https://hex-rays.com/ida-pro)
- [Hex-Rays pricing](https://hex-rays.com/pricing)
- [Vendr Hex-Rays pricing data](https://www.vendr.com/buyer-guides/hex-rays)
- [Hex-Rays ARM disassembly comparisons](https://docs.hex-rays.com/user-guide/decompiler/introduction-to-decompilation-vs-disassembly/comparisons-of-arm-disassembly-and-decompilation)
- [Binary Ninja Sidekick 5.0](https://binary.ninja/2025/07/28/sidekick-5.0.html)
- [Sidekick pricing](https://sidekick.binary.ninja/)
- [RevEng.AI](https://reveng.ai/)
- [RevEng.AI seed funding](https://www.prweb.com/releases/revengai-secures-4-15m-seed-round-to-tackle-software-supply-chain-security-302491721.html)
- [RevEng.AI IDA plugin](https://plugins.hex-rays.com/revengai/plugin-ida)
- [louisgthier/decompai](https://github.com/louisgthier/decompai)
- [albertan017/LLM4Decompile](https://github.com/albertan017/LLM4Decompile)
- [LLM4Decompile EMNLP 2024 paper](https://aclanthology.org/2024.emnlp-main.203/)
- [DeGPT NDSS 2024 paper](https://www.ndss-symposium.org/wp-content/uploads/2024-401-paper.pdf)
- [DecLLM ACM 2025](https://dl.acm.org/doi/pdf/10.1145/3728958)
- [atredispartners/aidapal](https://github.com/atredispartners/aidapal)
- [mrexodia/ida-pro-mcp](https://github.com/mrexodia/ida-pro-mcp)
- [symgraph/IDAssist](https://github.com/symgraph/IDAssist)
- [mahaloz/DAILA](https://github.com/mahaloz/DAILA)
- [llnl/OGhidra](https://github.com/llnl/OGhidra)
- [Anthropic batch processing docs](https://platform.claude.com/docs/en/build-with-claude/batch-processing)
- [Anthropic prompt caching docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Anthropic API pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [asg017/sqlite-vec](https://github.com/asg017/sqlite-vec)
- [sqlite-vec hybrid search blog](https://alexgarcia.xyz/blog/2024/sqlite-vec-hybrid-search/index.html)
- [SQLite FTS5 docs](https://www.sqlite.org/fts5.html)
- [LanceDB on Tigris](https://www.tigrisdata.com/docs/libraries/lancedb/vector-database/)
- [think-cell Reverse Engineer interview (Glassdoor)](https://www.glassdoor.com/Interview/think-cell-Reverse-Engineer-Interview-Questions-EI_IE710083.0,10_KO11,27.htm)
- [think-cell KB0091](https://www.think-cell.com/en/resources/kb/0091)
- [Cisco Talos: LLMs as RE sidekick](https://blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/)
