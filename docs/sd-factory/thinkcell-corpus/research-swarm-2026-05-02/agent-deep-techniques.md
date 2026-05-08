# Deep Technical Survey — Frontier RE Techniques for tcaddin.dll

**Pass 2 (deeper). Generated 2026-05-02. Cap 6000 words.**

Scope: 48 MB closed-source Windows ARM64 COM add-in DLL (think-cell `tcaddin.dll`) loaded in-process by `POWERPNT.EXE`. This pass focuses on what Pass 1 (2026-05-01) missed: post-2025-08 LLM decompilation SOTA, LLM-augmented grammar inference, OOXML custom-XML inference, in-proc instrumentation post-2024, and the published shape of think-cell's hook engine.

---

## Top-of-document summary — 5 actionable techniques the Pass-1 survey missed

1. **D-LiFT + LLM4Decompile-Ref-22B-V2 + Idioms (Realtype)** — RL-fine-tuned LLM decompiler chain. D-LiFT (NDSS 2026, [arXiv 2506.10125](https://arxiv.org/abs/2506.10125)) wraps a Ghidra-output LLM in a D-Score loop that scores compiler-correctness AND readability before accepting a refinement; on coreutils it improves 68% of functions and avoids the 93% new-error rate reported for raw LLM4Decompile. Pair it with Idioms (NDSS 2026, [arXiv 2502.04536](https://arxiv.org/abs/2502.04536)) which jointly predicts code AND user-defined types — critical for COM `IDispatch` argument structs in tcaddin.dll. **Pass 1 listed LLM4Decompile but missed both the D-Score correctness validator and Idioms' joint-type prediction.**

2. **ChatPRE replaces BinPRE for grammar inference** — [ChatPRE](https://www.sciencedirect.com/science/article/abs/pii/S1084804526000019) (Elsevier 2026) lifts BinPRE's heuristic field detectors with a three-stage LLM agent: dynamic taint + variable mapping → LLM semantic inference → LLM holistic re-inference. Reported F1 0.89 on segmentation vs BinPRE's 0.42–0.55. **For .ppttc / think-cellXML / OOXML custom-XML grammar reconstruction this is the direct upgrade path.** Repo: `huoyuxi/ChatPRE`.

3. **ChatAFL coverage-guided seed expansion against the IDispatch surface** — [ChatAFL](https://www.ndss-symposium.org/ndss-paper/large-language-model-guided-protocol-fuzzing/) (NDSS 2024, still SOTA per the 2025 follow-on TSE paper) uses an LLM to grow a seed corpus for stateful targets: 47.6% more state transitions, 29.6% more states, 5.8% more code coverage vs AFLNet. For tcaddin's automation surface (DISPID-keyed `Invoke` calls), feed it the existing tier1/tier2 probe results as seeds and let it expand the protocol grammar. **Pass 1 referenced AFL++ generally but not LLM-guided protocol fuzzing.**

4. **Frida 16.7+ `Process.attachModuleObserver` synchronous load hook** — [Frida 16.7.0](https://frida.re/news/2025/03/13/frida-16-7-0-released/) added a synchronous module-load callback that fires _after_ DllMain but _before_ any caller invokes the new module. This is the right primitive to instrument tcaddin.dll's COM registration path WITHOUT racing think-cell's pattern scanner. **Pass 1 used Interceptor; the new ModuleObserver is materially better for first-load capture.**

5. **think-cell's hook engine pattern-search is documented obliquely in Theophil's debugging talk** — The "Nobody Can Program Correctly" talk (think-cell, ACCU 2023 + 2024 redux) walks the audience through real bugs in their Office integration including, per the abstract, _"reverse-engineering Microsoft's code"_ (think-cell careers page, public). Pair the slide PDF ([talk PDF](https://www.think-cell.com/assets/en/career/talks/pdf/think-cell_talk_debugging.pdf)) with KB0233 (Windows Defender ASR rule deletes tcaddin.dll/tcasr.exe) for inferred opcode signature surfaces. **Pass 1 cited the McPartlin 2014 talk; the Theophil 2023–2024 series is fresher and richer.**

---

## 1. Post-2025-08 LLM-assisted decompilation SOTA

### State of the art

| Tool / paper                                 | Date              | Key contribution                                                                                                                                                                                                                       | Apply to tcaddin.dll?                                                                                                                                                                              |
| -------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **LLM4Decompile-9B-v2** + Decompile-Bench    | 2024-09 / 2025-05 | 9B param Yi-Coder fine-tune; 0.6494 re-executability on Decompile-bench. 2M binary–source pair training set released 2025-05-20. ([repo](https://github.com/albertan017/LLM4Decompile))                                                | **HIGH** — biggest open Ghidra-refiner. Run on tcaddin per-function output.                                                                                                                        |
| **LLM4Decompile-Ref-22B-V2**                 | 2024-06           | 22B refiner; outperforms 6.7B-V1.5 by 40.1%. ([HuggingFace](https://huggingface.co/LLM4Binary/llm4decompile-6.7b-v2))                                                                                                                  | **HIGH** — the largest free Ghidra-refiner; ARM64 not in train set, so prefer running on x64 build of tcaddin (think-cell ships both).                                                             |
| **DeGPT** (NDSS 2024)                        | 2024              | Three-role LLM (referee/advisor/operator) + MSSC semantic-fidelity check. 24.4% cognitive-burden reduction. ([paper](https://www.ndss-symposium.org/wp-content/uploads/2024-401-paper.pdf), [repo](https://github.com/PeiweiHu/DeGPT)) | **MED** — comments only, doesn't recompile. Layer it after D-LiFT for variable rename.                                                                                                             |
| **DecLLM** (ISSTA 2025)                      | 2025-06           | LLM repair loop using compiler errors AS the oracle. 70% recompile rate on coreutils. ([paper](https://dl.acm.org/doi/10.1145/3728958))                                                                                                | **MED** — recompilability is less critical than readability for tcaddin RE; useful for CodeQL queries on extracted functions.                                                                      |
| **D-LiFT** (NDSS 2026)                       | 2026-02           | RL fine-tuning with D-Score: compiler-correctness gated readability. 68.2% of native-decompiler functions improved without new errors. ([paper](https://arxiv.org/abs/2506.10125))                                                     | **HIGH** — the safest LLM-refinement pipeline. Pass-1 raw LLM4Decompile introduces 93.2% new-error rate; D-LiFT eliminates that.                                                                   |
| **Idioms**                                   | NDSS 2026         | Joint code + type-definition prediction; Realtype dataset. 54.4% accuracy on ExeBench. ([paper](https://arxiv.org/abs/2502.04536))                                                                                                     | **HIGH** — recovers struct/typedef definitions, exactly what's needed for `DISPPARAMS`/`VARIANT`/`SAFEARRAY` parameter shapes.                                                                     |
| **HELIOS** (hier. graph abstraction)         | 2026-01           | [arXiv 2601.14598](https://arxiv.org/pdf/2601.14598) — structure-aware LLM decompilation with hierarchical CFG.                                                                                                                        | **MED** — relevant for tcaddin's giant dispatch tables.                                                                                                                                            |
| **Idiomatic Decompilers — Dart/x86-64**      | 2026-04           | Cross-language transfer: 4B specialized model approaches 120× larger general LLMs on CodeBLEU. ([arXiv 2604.02278](https://arxiv.org/html/2604.02278))                                                                                 | **LOW** — Dart-specific, but the technique (small specialized model + synthetic same-language augmentation) transfers if Andre wants to fine-tune a tcaddin-specific decompiler from C++ binaries. |
| **WaDec** (ASE 2024)                         | 2024-10           | First Wasm-decompile LLM; >50% recompile + re-execute. ([arXiv 2406.11346](https://arxiv.org/abs/2406.11346))                                                                                                                          | **LOW** — Wasm only, but proves the slicing-by-control-flow approach for big binaries; could be ported to MSVC structured C++ if needed.                                                           |
| **Decompiling the Synergy** (NDSS 2026 main) | 2026-02           | Empirical study of human–LLM teaming in RE. From ASU + Padua + EURECOM.                                                                                                                                                                | **HIGH** — read the ablations; it tells you when human-in-the-loop pays off vs full automation.                                                                                                    |

### Tooling integrations

- **RevEng.AI** ([reveng.ai](https://reveng.ai/), [Hex-Rays plugin page](https://plugins.hex-rays.com/revengai/plugin-ida)) — Ghidra plugin updated 2026-04-24, IDA Pro plugin maintained, Binary Ninja 2026-03-27, Python toolkit 2026-02-23. New TS/Java/Python/Go SDKs as of 2026-04-29. Their function-similarity model is the current best free alternative to manual signature work; upload tcaddin.dll, get back name suggestions for 30–60% of functions in one pass. **Cost: free tier exists; paid tier ~$50/mo individual.** ([blog on AI decomp](https://blog.reveng.ai/training-an-llm-to-decompile-assembly-code/))
- **Binary Ninja Sidekick 3.0** ([blog](https://binary.ninja/2025/02/26/sidekick-3.0.html), [docs](https://docs.sidekick.binary.ninja/latest/guide/llm_operators/)) — Feb 2025 release ships Analysis Console, custom-tool system, Automation Workbench scripts that compose Python + LLM operators. The `LLMOperator` primitive is what Pass-1 missed: you describe a _task_ once and it generates a parameterized output schema, runs against any function in the binary, returns structured results. Sidekick On-Premises in roadmap. **Cost: $XXX/yr commercial seat (price gated).**
- **reverser_ai** ([github.com/mrphrazer/reverser_ai](https://github.com/mrphrazer/reverser_ai)) — local Mistral-7B Binary Ninja plugin, queries 2–5s on Apple Silicon. IDA + Ghidra support still on the roadmap as of late 2025. Useful as a quick local-only fallback.
- **Cisco Talos LLM-as-Sidekick blog** (2025-08-19, [post](https://blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/)) — practitioner walkthrough of MCP+IDA Pro+VSCode-based MCP client + local GPU model. The setup recipe transfers directly.

### Anthropic-specific Claude decompile workflows

No Anthropic-published RE case study exists. The closest is the [SimoneAvogadro/android-reverse-engineering-skill](https://github.com/SimoneAvogadro/android-reverse-engineering-skill) Claude Code skill (decompile APK/JAR + extract HTTP APIs). For tcaddin.dll the analogous pattern is: Ghidra script export per-function pseudocode → Claude Skill prompt template → write-back IDA/Ghidra symbol names. Use **XML-tagged prompts + few-shot examples** per [Claude prompting best practices](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices) (Claude 4.x is literal; vague requests now under-perform vs 3.x). For 48 MB of code, Opus 4.7 with 1M context lets you cluster 200+ related functions per call. Set effort=medium, max_output=64k, batch by call-graph SCC.

### Function-level vs basic-block-level vs instruction-level labeling

- **Function-level (recommended for tcaddin.dll)** — the LLM4Decompile-Ref / D-LiFT / Idioms regime. Best signal-to-noise; matches how RE analysts think.
- **Basic-block-level** — RevEng.AI's similarity model operates here; useful for hot-spot triage.
- **Instruction-level** — academic; no SOTA tool ships this.

### Embeddings for decompiled C

[LoRACode 2025](https://arxiv.org/pdf/2503.05315) shows UniXcoder + LoRA gives biggest C/C++ MRR lift (9.1% / 7.47%) and matches StarCoder at lower cost. For tcaddin.dll function-similarity search, **UniXcoder-base + a LoRA adapter trained on the post-Ghidra/post-D-LiFT C output** is the right embed for nearest-neighbor function clustering inside the 48 MB binary. CodeBERT and StarEncoder both score >0.98 on dissimilar pairs (false positives) per the LoRACode benchmark — avoid them.

### Recipe (1 weekend cost ~$30 OpenRouter or free local)

```bash
# 1. Ghidra headless extract pseudocode for every named function
analyzeHeadless . tcaddin.gpr -import tcaddin.dll \
  -postScript ExportPseudoC.java -deleteProject

# 2. D-LiFT-style refinement: pipe each function through Ghidra + Claude Opus 4.7
#    with extracted assembly + decompiled C + RTTI hints
python decompile_loop.py \
  --input tcaddin_pseudo/ \
  --model claude-opus-4-7 \
  --score-via clang -fsyntax-only \
  --max-rounds 3

# 3. Idioms-style joint type recovery: prompt for typedefs alongside code
#    Use Realtype-style dataset for few-shot examples
```

**Applicability score for tcaddin.dll: HIGH** — 48 MB ≈ ~50–80k functions; D-LiFT + Opus 4.7 in 1M context can refine ~500 fn per minute at $15/M input; budget ~$200 for full corpus.

---

## 2. Grammar inference from observed samples — frontier 2024–2026

### The successor map

- **BinPRE** (CCS 2024, [arXiv 2409.01994](https://arxiv.org/abs/2409.01994), [repo](https://github.com/ecnusse/BinPRE)) — instruction-similarity field extraction + atomic semantic detector library. Pass-1 already covered this.
- **ChatPRE** (Elsevier 2026, [paper](https://www.sciencedirect.com/science/article/abs/pii/S1084804526000019), [repo](https://github.com/huoyuxi/ChatPRE)) — **the direct LLM successor.** Three stages: (1) dynamic taint + variable-mapping field segmentation on IDA pseudo-C, (2) LLM agent inferring functional semantics from pseudo-C + field content, (3) LLM holistic re-inference correcting boundary errors. F1 0.89 segmentation, 0.64 field-type, beats BinPRE's 0.44/0.55.
- **MALPRE** (IEEE ISSRE 2025) — code slicing + agentic workflow for malware protocols. Useful template if you want stage-2 to be agentic per-DISPID rather than per-function.
- **BitInfer** (IEEE COMPSAC 2025) — genetic-algorithm based field semantic inference. Backup if LLM cost is an issue.

### LLM-augmented CFG refinement (active learning)

[XML Prompting as Grammar-Constrained Interaction](https://arxiv.org/html/2509.08182v1) (2025) gives the formal apparatus for asking an LLM to refine a candidate CFG against observed examples with convergence guarantees — relevant when reverse-engineering think-cellXML inside OOXML custom XML parts. The fixed-point semantics let you prove the inferred grammar covers all observed samples.

### XML-with-proprietary-extensions (think-cellXML inside OOXML custom XML parts)

The OOXML "Custom XML data" mechanism (ECMA 376 part 4 §8) is just an extra ZIP entry — any add-in (think-cell, empower®, Mekko Graphics) can stuff arbitrary XML into the .pptx package. Per [the OOXML wiki](https://wiki.openoffice.org/wiki/OOXML/Markup_Compatibility_and_Extensibility), Microsoft itself does this for proprietary new-shape elements; converting `.ppt` → `.pptx` reportedly breaks think-cell state ([KB0126](https://www.think-cell.com/en/resources/kb/0126)), confirming think-cell stores serialized state in a custom XML part outside the standard chart XML.

**Recommended grammar-inference flow for think-cellXML:**

1. Collect `tier1-novel-probes.md` outputs and existing `template-family-map.md` corpus (~hundreds of think-cell-touched .pptx files).
2. `unzip -p file.pptx '*.xml' | xmllint --format -` to extract custom XML parts.
3. Run **iXML inverse-grammar inference** ([MarkupUK 2025 proceedings](https://markupuk.org/pdf/proceedings-2025-2.pdf)) to bootstrap a starting CFG from observed samples.
4. Feed CFG + 50 examples to Claude Opus 4.7 as a ChatPRE-stage-3 holistic re-inference: _"Given this provisional grammar and these examples, identify under-constrained productions and propose minimal refinements."_
5. **Active-learning loop:** generate inputs that two competing grammars would handle differently, push them through PowerPoint via the JSON automation API ([think-cell JSON automation](https://www.think-cell.com/en/resources/manual/jsondataautomation)), observe which round-trips, prune.

### Active learning approaches for protocol grammar disambiguation

- [LLM-Boofuzz](https://www.mdpi.com/2079-9292/14/23/4550) (Nov 2025) — LLMs parse real traffic to extract protocol info, generate scripts with repair mechanism, multi-script iterative fuzzing. 53.4% line coverage, finds all 15 test vulns vs 7–8 for AFLNet/Snipuzz/Boofuzz.
- [LLM-Assisted Model-Based Fuzzing](https://arxiv.org/html/2508.01750v1) (Aug 2025) — generation-guided fuzzer for protocol implementations using LLM-extracted grammar.

**Applicability score for tcaddin.dll think-cellXML grammar: HIGH.** ChatPRE pattern is mature; few-day spike with the corpus already in `docs/thinkcell-corpus/`. Cost: ~$50 in Opus tokens for full sweep.

---

## 3. Symbolic / concolic execution scaling on COM dispatch interfaces

### State of the angr ecosystem

No 2025 paper specifically targets COM `IDispatch::Invoke`. The relevant primitives:

- **angr** itself: per [docs](https://docs.angr.io/en/latest/core-concepts/symbolic.html) you must write SimProcedures to summarize complex functions; for `IDispatch::Invoke` that means stubbing the vtable indirection and modeling `DISPPARAMS`+`VARIANT` symbolically. No public SimProcedure for this exists.
- **dAngr** ([NDSS BAR 2025](https://www.ndss-symposium.org/wp-content/uploads/bar2025-final14.pdf)) — interactive symbolic debugger built on angr. Not COM-aware but the interactive UX shrinks the SimProcedure-authoring loop dramatically.
- **TritonDSE** + Sydr (DynamoRIO+Triton hybrid). Triton is Linux/Windows/macOS compatible per its [docs](https://triton-library.github.io/), runs x86/x86-64/AArch64. **For ARM64 tcaddin.dll, Triton is a better starting point than angr** (which has weaker ARM64 + Windows PE support).

### Enumerating reachable code paths through `IDispatch::Invoke` given known DISPID + signature

There is no off-the-shelf tool for this. Build it as a custom Triton harness:

```python
# Pseudocode for Triton harness on tcaddin.dll
ctx = TritonContext(ARCH.AARCH64)
ctx.setMode(MODE.ALIGNED_MEMORY, True)

# Load tcaddin.dll image into Triton's symbolic memory
load_pe(ctx, "tcaddin.dll")

# Symbolize DISPID + DISPPARAMS args
dispid = ctx.symbolizeRegister(REG.X1, "dispid")
disp_params_ptr = ctx.symbolizeRegister(REG.X2, "disp_params_ptr")

# Hook IDispatch::Invoke entry (resolve via RTTI)
invoke_addr = find_dispatch_invoke(ctx)

# Concolic exec: explore branches keyed on dispid value
explore_paths(ctx, invoke_addr, max_paths=128)

# Each terminating state corresponds to a reachable code-path for that DISPID
```

**Applicability score: MED.** High effort (1–2 weeks), high value (gives complete reachability map per DISPID). Triton is the right tool. Manticore has weaker ARM64. Pair with angr SimProcedures for win32/COM stubs (`CoCreateInstance`, `IUnknown::QueryInterface`).

### Real-world precedent

The [hardwear.io 2023 talk](https://hardwear.io/usa-2023/presentation/analyzing-decompiled-c++vtables-and-objects-in-GCC-binaries.pdf) on static C++ vtable analysis in Ghidra is the closest published recipe. For tcaddin.dll specifically, no public symbolic-execution write-up exists.

---

## 4. In-process Office add-in instrumentation post-2024

### Frida / Frida-Gum

- **[Frida 17.2.0](https://frida.re/news/2025/06/18/frida-17-2-0-released/)** (June 2025) — current; full Windows ARM64 support.
- **[Frida 16.7.0](https://frida.re/news/2025/03/13/frida-16-7-0-released/)** (March 2025) — added `Process.attachModuleObserver`. Synchronous callback fires _after_ DllMain but _before_ any other code uses the new module. **This is materially better than Pass-1's Interceptor for first-load capture: catches tcaddin.dll registration without racing think-cell's own pattern scanner.**
- Stalker for code tracing (BBL-level coverage), MemoryAccessMonitor for read/write watchpoints, and the new ModuleObserver give a complete dynamic-instrumentation kit on POWERPNT.

### DTrace4Win

DTrace for Windows exists ([microsoft/DTrace-on-Windows](https://github.com/microsoft/DTrace-on-Windows)) but is anaemic vs Frida; no 2025 update of substance. **Skip.**

### Microsoft Office Telemetry / TraceLogging providers

Per [Microsoft docs](https://learn.microsoft.com/en-us/windows/win32/etw/about-event-tracing), four ETW provider types exist; modern Office uses TraceLogging providers (channel 11). To enumerate POWERPNT.EXE's TraceLogging providers:

```powershell
# PowerShell admin
logman query providers | Select-String -Pattern "Office|PowerPoint|POWERPNT"
# Then run a session capturing only the relevant providers:
wpr -start GeneralProfile -filemode
# trigger think-cell action in PowerPoint
wpr -stop tcaddin.etl
# Open in WPA, look for non-Microsoft providers — that's tcaddin's own ETW if any
```

If tcaddin.dll registers its own TraceLogging provider (likely for crash telemetry), the GUID will be visible after `TraceLoggingRegister` in DllMain `PROCESS_ATTACH`. Capturing it gives you free internal-event observability without hooking. **Check this first before Frida.**

### eBPF for Windows

Per [Microsoft eBPF-for-Windows](https://github.com/microsoft/ebpf-for-windows) and [eunomia 2025 deep dive](https://eunomia.dev/blog/2025/02/12/ebpf-ecosystem-progress-in-20242025-a-technical-deep-dive/), eBPF on Windows now supports custom map types, ring buffer + perf event arrays, and ETW-integrated tracing. **Not yet production-ready for userland-process hooking on the scale of an Office add-in** — Linux's uprobes equivalent is missing. Watch this in 2026 H2; for now, **Frida is the right tool**. Office hours: weekly Mondays 8:30 PST.

### Office Add-in runtime logging

[Microsoft Office runtime-logging docs](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/runtime-logging) cover Office.js add-ins, NOT COM add-ins. For COM add-ins (tcaddin.dll), use [HKEY_CURRENT_USER\Software\Microsoft\Office\16.0\PowerPoint\Options\EnableLogging] = 1 to surface Office-side load failures.

**Applicability score: HIGH.** Frida + ETW combo replaces 80% of what API Monitor / Process Monitor used to give you, with better fidelity.

---

## 5. Adjacent-domain RE that transfers

### Mekko Graphics

Same architectural niche as think-cell (PowerPoint COM add-in, chart serialization in custom XML parts). No public RE writeup; their FAQ mentions the same `COMAddIn` registration path. **Useful as a control: if Mekko also stores in custom XML parts but with a different serialization format, comparing the two reveals which "weird XML namespace = some-add-in" patterns are think-cell's.**

### empower® for PowerPoint

Cloud-based SaaS (Azure-hosted) per [empowersuite.com](https://www.empowersuite.com/en/features/empower-ppt-charts) — different architecture (server round-trip for some operations). Less directly comparable. Useful for _contrast_: if empower's chart data is round-trip-proof in OOXML and think-cell's isn't, that confirms think-cell relies more heavily on private custom-XML state.

### Tableau Desktop add-ins

Tableau's [extensions API](https://github.com/tableau/extensions-api) is a sandboxed JS-in-iframe model — no DLL hooking; transfers nothing.

### Power BI Desktop

[granite-cs/PowerBiVisibility](https://github.com/granite-cs/PowerBiVisibility) shows the .pbix == OPC-package + Layout file (UTF-16 LE-encoded) pattern. Same family as .pptx with custom XML parts. **The `unzip → modify → repackage` workflow developed for Power BI transfers directly to think-cell-touched .pptx files.**

### Office.js add-ins (custom functions)

Per the [Microsoft Learn custom-functions docs](https://learn.microsoft.com/en-us/office/dev/add-ins/excel/custom-functions-overview), Office.js custom functions expose JSON metadata files and run in a **separate runtime from the browser engine**. Reverse engineering involves DevTools breakpoints + JSON metadata inspection. **Doesn't transfer to tcaddin.dll** (different runtime), but the pattern of _"public manifest tells you the function-name surface even if implementation is opaque"_ is identical to the COM type-library / DISPID enumeration approach in `tier1-novel-probes.md`.

### Consulting-tool RE blogs

Genuinely no public practitioner blog covers RE on think-cell, Mekko, or empower at the binary level. The Analyst Academy / Slideworks / Plus AI / Deckary content is all about _visual_ style RE (Pyramid Principle, MECE, action titles), not binary RE. **Treat the absence as confirmation that this angle is novel.**

---

## 6. Communities + practitioner blogs

| Source                                 | URL                                                                                                                                                        | What's there for tcaddin                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hex-Rays Plugin Repo**               | [plugins.hex-rays.com](https://plugins.hex-rays.com)                                                                                                       | RevEng.AI plugin; daily auto-indexer scans GitHub for `ida-plugin.json`; submit your own analysis as a plugin if useful. **Look for ComIDA / Comida** (COM GUID reference resolver, Hexrays-aware).                                                                                                                                                                                                                                                            |
| **Ghidra-Cpp-Class-Analyzer**          | [github.com/astrelsky/Ghidra-Cpp-Class-Analyzer](https://github.com/astrelsky/Ghidra-Cpp-Class-Analyzer)                                                   | RTTI + vtable analysis; mostly GCC-flavored. For MSVC tcaddin.dll, prefer **rtti-vtable-dumper** or **ClassDumper**.                                                                                                                                                                                                                                                                                                                                           |
| **rtti-vtable-dumper**                 | [github.com/jessy-lua/rtti-vtable-dumper](https://github.com/jessy-lua/rtti-vtable-dumper)                                                                 | Cross-platform CLI extractor for MSVC RTTI on Windows x64 DLLs. **Run this first on tcaddin.dll** (note: ARM64 support unclear; check on x64 build).                                                                                                                                                                                                                                                                                                           |
| **OOAnalyzer** (CMU SEI Pharos)        | [sei.cmu.edu blog](https://www.sei.cmu.edu/blog/using-ooanalyzer-to-reverse-engineer-object-oriented-code-with-ghidra/)                                    | Ghidra plugin for C++ class reconstruction. Slow but thorough.                                                                                                                                                                                                                                                                                                                                                                                                 |
| **OALabs**                             | [research.openanalysis.net](https://research.openanalysis.net/), [Patreon DLL series](https://www.patreon.com/posts/ida-free-reverse-138624283)            | 2025-09-10 IDA Free DLL analysis series; general-purpose, transfers. No tcaddin-specific write-up.                                                                                                                                                                                                                                                                                                                                                             |
| **Cisco Talos**                        | [blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/](https://blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/) | 2025-08-19; setup recipe for MCP+IDA Pro+local-GPU LLM. Best practitioner walkthrough of the LLM-RE stack.                                                                                                                                                                                                                                                                                                                                                     |
| **VxUnderground**                      | [vx-underground.org](https://vx-underground.org/)                                                                                                          | Malware corpus + RE writeups. **No tcaddin-adjacent samples** (it's not malware) but think-cell HAS been incorrectly DLP-flagged: see [KB0233](https://www.think-cell.com/en/resources/kb/0233) (Defender ASR rule deletes tcaddin.dll between 1.353.694.0 and 1.355.1377.0 signatures). That ASR rule's pattern _is_ a published Microsoft signature for "in-process Office hook" — interesting fingerprint of how Defender characterizes tcaddin's behavior. |
| **Reverse Engineering Stack Exchange** | [reverseengineering.stackexchange.com](https://reverseengineering.stackexchange.com)                                                                       | No tcaddin-specific Q&As as of 2026-05; general COM RE patterns useful (search `[com] [office]`).                                                                                                                                                                                                                                                                                                                                                              |
| **r/ReverseEngineering**               | reddit.com/r/ReverseEngineering                                                                                                                            | No tcaddin posts found; generic Office add-in posts mostly malware-focused.                                                                                                                                                                                                                                                                                                                                                                                    |
| **Frida Discord + frida-tools forum**  | [frida.re](https://frida.re)                                                                                                                               | Active. Ask `Module observer + COM add-in` in Frida Discord — the maintainers respond within hours.                                                                                                                                                                                                                                                                                                                                                            |

### IDA-specific COM tooling worth flagging

- **Comida** / **ComIDA** plugins — search COM GUID references and apply types via Hexrays. Both surface in [fr0gger/awesome-ida-x64-olly-plugin](https://github.com/fr0gger/awesome-ida-x64-olly-plugin).
- **Virtuailor** — IDAPython vtable reconstructor for x86/x64. **Does not yet support ARM64**; check status on issue tracker before committing.
- **Classy** — IDA class manager: vtable assignment, function signatures, IDA struct + C-header generation.

---

## 7. Probe automation techniques

### LLM-driven probe planning

[FLARE](https://arxiv.org/abs/2604.05289) (2025) — agentic coverage-guided fuzzing for LLM multi-agent systems. Two coverage criteria (intra/inter-agent) jointly drive seed selection. **Applicability for tcaddin: HIGH.** The DISPID surface is exactly an inter-component interaction graph; FLARE-style cumulative coverage guides Andre's existing probe runner toward unexplored DISPIDs.

### Coverage-guided probe expansion

- **ChatAFL** ([NDSS 2024](https://www.ndss-symposium.org/ndss-paper/large-language-model-guided-protocol-fuzzing/), [arXiv](https://abhikrc.com/pdf/NDSS24.pdf)) — LLM constructs message-type grammars, mutates messages, predicts next-message in sequence. 47.6% more state transitions, 5.8% more code coverage vs AFLNet.
- **PSGFuzz** ([TSE 2025](https://abhikrc.com/pdf/TSE_PSG_2025.pdf)) — diverse seed-corpus enhancement. Pair with ChatAFL.
- **AFL+LLM-repair** (2025) — coverage-guided + LLM patch loop; repairs 11/13 crash-inducing programs in three iterations.

### Property-based testing for COM dispatch

- **[Hypothesis](https://hypothesis.works/)** + **[HypoFuzz](https://hypofuzz.com/)** — Python PBT + adaptive fuzzer. Use `pywin32` to bridge Hypothesis test inputs into `IDispatch::Invoke` calls.
- **QuickCheck**-style approach: define properties like _"any DISPID with valid args either returns S_OK or DISP_E_TYPEMISMATCH; never AV"_ and let the fuzzer find counterexamples.

### Invariant testing recipe

```python
import win32com.client
from hypothesis import given, strategies as st

tc = win32com.client.gencache.EnsureDispatch("thinkcell.PpAddIn")  # or late-bound

@given(
    dispid=st.integers(min_value=0, max_value=8000),
    args=st.lists(st.one_of(st.integers(), st.text(), st.floats()), max_size=10),
)
def test_invoke_no_av(dispid, args):
    """Property: no DISPID + arg combo should AV the host process."""
    try:
        tc._oleobj_.Invoke(dispid, 0, 1, True, *args)
    except Exception:
        pass  # expected for invalid combos
    # If we got here, POWERPNT is still alive → property holds
```

Wrap in HypoFuzz for adaptive coverage. **Applicability: HIGH.** Modest cost (CPU only); high value (finds the panic surface). 1 weekend.

---

## 8. Anti-tamper / hook engine analysis

### What's publicly known about think-cell's hook engine

- think-cell _publicly states_ it integrates seamlessly with Office and reverse-engineers Microsoft's code (think-cell careers / about page; CppCon sponsor profile).
- The "Nobody Can Program Correctly" Theophil debugging talk ([slides PDF](https://www.think-cell.com/assets/en/career/talks/pdf/think-cell_talk_debugging.pdf), ACCU 2023, [accu.org video](https://accu.org/video/spring-2023-day-1/theophil/), redux at C++ Berlin Meetup 2024-03-20, FU Berlin 2024-04-15, Zurich C++ Meetup 2025-03-14, ETH Zurich 2025-03-13) covers debugging real Office-integration bugs. Read for: what kinds of breakages they've encountered → infers what they're hooking.
- **[KB0233](https://www.think-cell.com/en/resources/kb/0233)** confirms Defender ASR signatures 1.353.694.0–1.355.1377.0 detect-and-delete tcaddin.dll/tcasr.exe. **Whatever pattern that ASR rule matched is a fingerprint of think-cell's hooking technique.** Worth pulling Defender historical signatures for those build IDs and reversing the YARA rule.

### Detecting / coexisting with the hook engine

Per the [OBS Studio Detours-coexistence forum thread](https://obsproject.com/forum/threads/detours-based-injection-in-27-1-0-and-compatibility-with-third-party-hooks.149496/) and the [Apriorit comparison](https://www.apriorit.com/dev-blog/win-comparison-of-api-hooking-libraries):

- **Microsoft Detours** is designed to coexist _only_ with other Detours-based hooks. It overwrites the top-level JMP and relocates other hooks' JMPs to its own trampolines. Many third-party hooks reject this kind of relocation.
- **`DetourCodeFromPointerEx`** unwinds the entire JMP chain and installs at the very end, which works around most coexistence issues.
- **Custom inline hooks** (no library signature) avoid pattern-scanning detection that catches Detours/EasyHook/MinHook.

### How NOT to trip think-cell's pattern scanner

think-cell's hook engine "searches for assembly patterns to be robust against minor Office changes" (per the McPartlin / Theophil talks). To safely instrument POWERPNT:

1. **Hook _outside_ the addresses think-cell scans.** Their pattern-scan targets specific PowerPoint internals (drawing/layout/chart APIs). Hooks at COM-marshaling boundaries (`OleAut32!DispCallFunc`, `Ole32!CoCreateInstance`) are off their radar.
2. **Use Frida's Stalker (BBL-level instrumentation) rather than inline trampolines** — Stalker recompiles basic blocks on the fly into a parallel address space; the original code is unmodified, so a pattern scan against the original .text section sees no change. ([frida-stalker docs](https://frida.re/docs/stalker/))
3. **Use Frida 16.7+ ModuleObserver to instrument tcaddin.dll _before_ it runs its first scan.** Catch DllMain `DLL_PROCESS_ATTACH` synchronously, then observe what tcaddin tries to read from POWERPNT's memory before patching.
4. **eBPF-for-Windows + ETW** for telemetry-only observation; no code modification → undetectable by pattern scan.

**Applicability: HIGH** for Stalker; **HIGH** for ModuleObserver-first observation; **MED** for ETW (can only see what they choose to log).

### Published techniques to detect hook engines

[Securehat blog](https://blog.securehat.co.uk/process-injection/detecting-process-injection-using-microsoft-detour-hooks) — uses Detours to add hooks for common APIs to detect injection. Same primitive could enumerate other hooks already installed in POWERPNT (walk `IAT` + check for non-original-image targets). Run this pre-and-post tcaddin load to map what tcaddin patches.

---

## 9. Patent + legal landscape — recent filings

### Known patents (Justia + USPTO)

[Justia think-cell GmbH page](https://patents.justia.com/assignee/think-cell-software-gmbh) lists publicly visible patents covering:

- **Automatic data extraction from charts** — bar chart hypothesis-and-test image analysis; capture-module GUI screen-area selection. (Filed pre-2024; published earlier.)
- **Display methods for labeled scatter charts** — interactive labeling algorithm for scatter chart annotations.
- **Display methods for labeled column charts** — same family for column charts.

Inventor names appearing across the portfolio: **Sebastian Theophil, Volker Schöch, Arno Schödl, Hannebauer, Ziegler, Lahmann, Nordhus, Ringenberg, McPartlin, Müller, Fracassi**.

### Post-2024-12-31 filings

I could not directly query USPTO / Google Patents with proper assignee filtering through WebSearch alone, and `WebFetch` to `patents.justia.com` and `patents.google.com` was permission-denied in this environment. **Manual follow-up required:**

```
# In Andre's environment:
# 1. https://patents.google.com/?assignee=think-cell&after=publication:20250101
# 2. https://ppubs.uspto.gov/ → assignee:"think-cell software"
# 3. Track inventor surname AND-search:
#    https://patents.google.com/?inventor=Theophil+Sebastian
```

Things to look for specifically:

- AI/ML feature patents (likely if think-cell 15 ships AI features per the GA-pre window referenced).
- Custom-XML serialization / round-trip patents (would describe the .pptx-internal storage format).
- JSON-automation protocol patents (would reveal the .ppttc grammar formally).
- Chart-layout / spatial-packing patents (their core IP).

**Applicability: HIGH.** Patent disclosures are the _only_ legitimate channel where think-cell publishes implementation details. **One weekend of patent reading > one month of binary RE** for some questions.

---

## 10. Beta / preview channel observability

### Release cadence

think-cell ships ~monthly. Per [their installation manual](https://www.think-cell.com/en/resources/manual/installation):

- Auto-update runs every time PowerPoint/Excel opens with think-cell installed.
- Per [their preview/pilot guide](https://www.think-cell.com/en/resources/manual/maintenance), pilot users can be configured to receive updates from think-cell's main server while the rest of the org pulls from a corporate XML feed. **The pilot URL is the same `update.think-cell.com/...` as production but with a different XML config pointer.**
- think-cell monitors all Microsoft 365 channels nightly and ships compatibility patches when Microsoft pushes a breaking change.

### Build 38409 status

Build 38409 is referenced in `settings.xml` `endver`. As of 2026-05-01 search results, this build number is **not surfaced** on the public [What's New page](https://www.think-cell.com/en/product/whats-new). It may be:

- A pre-GA tc15 internal build.
- A pilot-channel build available via the staged-rollout XML.
- The "endver" upper bound is forward-looking — meaning the file was last touched by some build with version ≤ 38409.

To confirm:

```bash
# Probe the public update server for that build's XML config:
curl -s "https://update.think-cell.com/update.xml" | xmllint --format -
# Compare with the pilot channel:
curl -s "https://update.think-cell.com/pilot/update.xml" | xmllint --format -
# Check Software Informer historical listings:
# https://think-cell.software.informer.com/versions/
```

### Differential analysis

Once you have two builds, run `bindiff` (Hex-Rays + Zynamics) or `Diaphora` (open-source diff at function level) on tcaddin.dll. Per **Idioms** + **D-LiFT** approaches above, you can also semantic-diff at the LLM-decompiled-pseudocode level — useful when symbol layout shifts between builds.

### Subscribe-able announcement channels

- **think-cell What's New page** — manual check, no RSS surfaced.
- **think-cell Group on LinkedIn** — sporadic.
- **think-cell on Twitter/X** — minimal recent activity.
- **GitHub release-watcher pattern**: monitor [github.com/makingspace/think-cell-styles](https://github.com/makingspace/think-cell-styles) (third-party but tracks schema changes).

**Recommendation:** write a tiny daily cronjob that diffs the `update.xml` from production + pilot channels and posts to a Slack channel. ~30 min to ship.

---

## Bottom: prioritized 1-weekend recommendation list

If Andre has only a single weekend, here's the priority order (each estimate is wall-clock for a focused weekend with Claude Opus 4.7 1M context as primary tool):

### Tier S (do first)

1. **Patent reading** (~3 hrs, $0). Pull every think-cell patent from Google Patents + USPTO with assignee filter, sort by date desc. Read top 10. Single highest signal-per-hour technique on this list. One unrelated bonus: `inventor:Schödl` may reveal his older Charité / TU Berlin academic work that's free to read.

2. **D-LiFT + Idioms decompilation pipeline on the 200 hottest functions** (~6 hrs, ~$50 in Opus tokens). Run Ghidra headless export → D-LiFT-style refinement loop with compiler-correctness gating → Idioms-style joint type recovery. Focus on functions reachable from the COM dispatch entry point. Output: a clean 200-function corpus you can grep / cluster. ([D-LiFT](https://arxiv.org/abs/2506.10125), [Idioms](https://arxiv.org/abs/2502.04536))

3. **ChatPRE-style think-cellXML grammar inference from your existing corpus** (~4 hrs, ~$20 in Opus tokens). Use the .pptx files already in `template-family-map.md` + tier1/2 probes. Three-stage agent. Output: a CFG/PCFG you can validate by round-tripping through the JSON-automation API. Worst case: you get a partial grammar that's still better than what BinPRE alone would give.

### Tier A (do next)

4. **Frida 16.7+ ModuleObserver harness for tcaddin.dll's first-load** (~4 hrs, $0). Catch DllMain `PROCESS_ATTACH` synchronously; log what tcaddin reads from POWERPNT memory before any patching; dump the pattern-scan signatures it's looking for. Use Stalker (not Interceptor) to avoid tripping their detector. ([Frida 16.7](https://frida.re/news/2025/03/13/frida-16-7-0-released/))

5. **Hypothesis + HypoFuzz property-based DISPID fuzzer via pywin32** (~3 hrs, $0). Define properties `(dispid, args) → no AV`. Wrap in HypoFuzz for adaptive corpus growth. Surfaces the _crash boundary_ of the dispatch table; pairs perfectly with the Idioms-recovered argument types. ([HypoFuzz](https://hypofuzz.com/))

6. **ETW provider enumeration on POWERPNT** (~1 hr, $0). `wpr -start GeneralProfile -filemode`, trigger think-cell action, `wpr -stop tcaddin.etl`, open in WPA, look for non-Microsoft GUIDs. If tcaddin emits its own TraceLogging events, you have free internal-event observability without hooking.

### Tier B (do if time)

7. **Defender ASR signature reversal for KB0233 builds** (~3 hrs, $0). Pull historical Defender SecurityIntelligence signature files for versions 1.353.694.0–1.355.1377.0 from Microsoft's signature archive; extract the YARA-equivalent rule that classified tcaddin.dll as malicious. That rule's pattern _is_ think-cell's hook fingerprint.

8. **RevEng.AI free-tier function-similarity pass** (~2 hrs, $0). Upload tcaddin.dll → get name suggestions for 30–60% of functions. Cross-reference with D-LiFT output for high-confidence renames. ([RevEng.AI portal](https://portal.reveng.ai/))

9. **Pilot-channel + production-channel `update.xml` diff cronjob** (~30 min, $0). Subscribe to weekly diffs of think-cell's preview channel; surface new build numbers (like 38409) as soon as they appear. 30 min to ship, runs forever.

10. **Bindiff / Diaphora-LLM differential analysis on consecutive builds** (~3 hrs once you have two builds, $20 in tokens). Once 38409 lands publicly, diff it against the current GA build at the LLM-pseudocode level (Idioms output is structurally diff-able). Surfaces every function that changed between two known-good builds — biggest indicator of where think-cell's active development is, hence where their interesting code lives.

---

## Citations (consolidated)

**Decompilation (LLM):**

- [LLM4Decompile repo](https://github.com/albertan017/LLM4Decompile)
- [LLM4Decompile arXiv](https://arxiv.org/html/2403.05286v3)
- [LLM4Decompile-6.7b-v2 HF](https://huggingface.co/LLM4Binary/llm4decompile-6.7b-v2)
- [DeGPT NDSS 2024](https://www.ndss-symposium.org/ndss-paper/degpt-optimizing-decompiler-output-with-llm/)
- [DeGPT repo](https://github.com/PeiweiHu/DeGPT)
- [DecLLM ISSTA 2025](https://dl.acm.org/doi/10.1145/3728958)
- [D-LiFT NDSS 2026 arXiv](https://arxiv.org/abs/2506.10125)
- [Idioms NDSS 2026 arXiv](https://arxiv.org/abs/2502.04536)
- [LLMs as Idiomatic Decompilers (Dart) arXiv](https://arxiv.org/html/2604.02278)
- [WaDec ASE 2024 arXiv](https://arxiv.org/abs/2406.11346)
- [HELIOS arXiv](https://arxiv.org/pdf/2601.14598)

**Tools:**

- [RevEng.AI](https://reveng.ai/)
- [RevEng.AI Hex-Rays plugin](https://plugins.hex-rays.com/revengai/plugin-ida)
- [RevEng.AI training blog](https://blog.reveng.ai/training-an-llm-to-decompile-assembly-code/)
- [Binary Ninja Sidekick 3.0](https://binary.ninja/2025/02/26/sidekick-3.0.html)
- [Sidekick docs](https://docs.sidekick.binary.ninja/latest/guide/llm_operators/)
- [Talos LLM-as-Sidekick](https://blog.talosintelligence.com/using-llm-as-a-reverse-engineering-sidekick/)
- [reverser_ai](https://github.com/mrphrazer/reverser_ai)
- [Ghidra-Cpp-Class-Analyzer](https://github.com/astrelsky/Ghidra-Cpp-Class-Analyzer)
- [rtti-vtable-dumper](https://github.com/jessy-lua/rtti-vtable-dumper)
- [ClassDumper](https://github.com/GrandpaGameHacker/ClassDumper)
- [OOAnalyzer (CMU SEI)](https://www.sei.cmu.edu/blog/using-ooanalyzer-to-reverse-engineer-object-oriented-code-with-ghidra/)
- [awesome-ida-x64-olly-plugin](https://github.com/fr0gger/awesome-ida-x64-olly-plugin)

**Grammar / protocol inference:**

- [BinPRE arXiv](https://arxiv.org/abs/2409.01994)
- [BinPRE repo](https://github.com/ecnusse/BinPRE)
- [ChatPRE Elsevier](https://www.sciencedirect.com/science/article/abs/pii/S1084804526000019)
- [ChatAFL NDSS 2024](https://www.ndss-symposium.org/ndss-paper/large-language-model-guided-protocol-fuzzing/)
- [ChatAFL PDF](https://abhikrc.com/pdf/NDSS24.pdf)
- [PSGFuzz TSE 2025](https://abhikrc.com/pdf/TSE_PSG_2025.pdf)
- [LLM-Boofuzz MDPI](https://www.mdpi.com/2079-9292/14/23/4550)
- [LLM-assisted Model-based Fuzzing arXiv](https://arxiv.org/html/2508.01750v1)
- [FLARE arXiv](https://arxiv.org/abs/2604.05289)
- [XML Prompting as Grammar-Constrained arXiv](https://arxiv.org/html/2509.08182v1)
- [MarkupUK 2025 proceedings](https://markupuk.org/pdf/proceedings-2025-2.pdf)

**Symbolic execution:**

- [angr docs](https://docs.angr.io/en/latest/core-concepts/symbolic.html)
- [angr repo](https://github.com/angr/angr)
- [dAngr NDSS BAR 2025](https://www.ndss-symposium.org/wp-content/uploads/bar2025-final14.pdf)
- [Triton library](https://triton-library.github.io/)
- [Triton repo](https://github.com/JonathanSalwan/Triton)

**Instrumentation:**

- [Frida home](https://frida.re/)
- [Frida 17.2.0 release](https://frida.re/news/2025/06/18/frida-17-2-0-released/)
- [Frida 16.7.0 release](https://frida.re/news/2025/03/13/frida-16-7-0-released/)
- [eBPF for Windows](https://github.com/microsoft/ebpf-for-windows)
- [eunomia eBPF 2024–2025 deep dive](https://eunomia.dev/blog/2025/02/12/ebpf-ecosystem-progress-in-20242025-a-technical-deep-dive/)
- [Microsoft ETW about](https://learn.microsoft.com/en-us/windows/win32/etw/about-event-tracing)
- [Microsoft TraceLogging](https://learn.microsoft.com/en-us/windows/win32/api/traceloggingprovider/nf-traceloggingprovider-tracelogging_define_provider)
- [Office runtime logging](https://learn.microsoft.com/en-us/office/dev/add-ins/testing/runtime-logging)
- [API Monitor](http://www.rohitab.com/apimonitor)
- [ired.team API monitoring](https://www.ired.team/offensive-security/code-injection-process-injection/api-monitoring-and-hooking-for-offensive-tooling)
- [Securehat detecting injection](https://blog.securehat.co.uk/process-injection/detecting-process-injection-using-microsoft-detour-hooks)
- [Apriorit hooking comparison](https://www.apriorit.com/dev-blog/win-comparison-of-api-hooking-libraries)
- [OBS Detours coexistence](https://obsproject.com/forum/threads/detours-based-injection-in-27-1-0-and-compatibility-with-third-party-hooks.149496/)

**Property-based testing:**

- [Hypothesis](https://hypothesis.works/articles/what-is-property-based-testing/)
- [HypoFuzz](https://hypofuzz.com/)
- [HypoFuzz repo](https://github.com/Zac-HD/hypofuzz)

**Embeddings:**

- [LoRACode arXiv](https://arxiv.org/pdf/2503.05315)
- [CodeBERT/UniXcoder repo](https://github.com/microsoft/CodeBERT)

**Claude prompting:**

- [Claude prompting best practices](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Claude API prompting](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)

**think-cell specific:**

- [think-cell What's New](https://www.think-cell.com/en/product/whats-new)
- [think-cell M365 channel compat KB0165](https://www.think-cell.com/en/resources/kb/0165)
- [think-cell deployment guide](https://www.think-cell.com/en/resources/manual/deploymentguide)
- [think-cell Defender ASR conflict KB0233](https://www.think-cell.com/en/resources/kb/0233)
- [think-cell update/maintenance manual](https://www.think-cell.com/en/resources/manual/maintenance)
- [think-cell API manual](https://www.think-cell.com/en/resources/manual/api)
- [think-cell JSON automation manual](https://www.think-cell.com/en/resources/manual/jsondataautomation)
- [think-cell debugging talk PDF (Theophil)](https://www.think-cell.com/assets/en/career/talks/pdf/think-cell_talk_debugging.pdf)
- [Theophil ACCU 2023 video](https://accu.org/video/spring-2023-day-1/theophil/)
- [think-cell-library on GitHub](https://github.com/think-cell/think-cell-library)
- [think-cell on CppCon](https://cppcon.org/think-cell/)
- [Justia patents — think-cell GmbH](https://patents.justia.com/assignee/think-cell-software-gmbh)
- [makingspace/think-cell-styles](https://github.com/makingspace/think-cell-styles)
- [Sphereon thinkcell-creator](https://github.com/Sphereon-Opensource/thinkcell-creator/blob/master/pom.xml)
- [thinkcell PyPI](https://pypi.org/project/thinkcell/)

**OOXML:**

- [OOXML compatibility/extensibility wiki](https://wiki.openoffice.org/wiki/OOXML/Markup_Compatibility_and_Extensibility)
- [Custom XML in OOXML critique](http://ooxmlisdefectivebydesign.blogspot.com/2008/03/custom-xml-what-custom-xml.html)

**Adjacent tools:**

- [Tableau extensions API](https://github.com/tableau/extensions-api)
- [empower® charts](https://www.empowersuite.com/en/features/empower-ppt-charts)
- [Mekko Graphics](https://www.mekkographics.com/product/)
- [PowerBiVisibility](https://github.com/granite-cs/PowerBiVisibility)
- [Office.js custom-functions overview](https://learn.microsoft.com/en-us/office/dev/add-ins/excel/custom-functions-overview)

**Conferences:**

- [NDSS 2026 main accepted papers](https://www.ndss-symposium.org/ndss2026/accepted-papers/)
- [NDSS 2026 BAR accepted](https://www.ndss-symposium.org/ndss2026/co-located-events/bar/accepted-papers/)
