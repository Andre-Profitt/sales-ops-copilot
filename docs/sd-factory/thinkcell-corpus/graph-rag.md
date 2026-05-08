# think-cell Graph RAG

Purpose: give future sessions a fast way to reason over the think-cell template
corpus without rereading every PowerPoint file.

## Artifacts

- Graph manifest: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_manifest.json`
- Nodes: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_nodes.jsonl`
- Edges: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg_edges.jsonl`
- RAG index: `state/thinkcell_bridge/knowledge_graph/thinkcell_graph_rag_index.json`
- Summary: `state/thinkcell_bridge/knowledge_graph/thinkcell_kg.md`
- Build scaffold: `state/thinkcell_bridge/build_scaffold/2026-Q2/thinkcell_build_scaffold.md`
- Slide corpus JSON: `state/thinkcell_bridge/slide_corpus/thinkcell_slide_corpus.json`
- Slide corpus CSV: `state/thinkcell_bridge/slide_corpus/thinkcell_slide_index.csv`

## Build

```bash
.venv/bin/python scripts/extract_thinkcell_slide_corpus.py
.venv/bin/python scripts/build_thinkcell_knowledge_graph.py --period 2026-Q2
.venv/bin/python scripts/build_thinkcell_build_scaffold.py --period 2026-Q2
```

The graph includes retrieval nodes plus build-level nodes. Use the scaffold
output when moving from search results into seed-authoring or binding work.

## Query

```bash
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "scatter fallback Patrick"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "FY26 renewal timeline donor slides"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "Commercial Approval table image contract"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "which slides are native bar column donors"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "L4 named seed contract"
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "forecast mix bar donor" --kind slide
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR01 L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR03 L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR04 scatter L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR05 FY26 renewal Gantt L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR06 Q2 renewal Gantt Sarah L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR07 Mekko stage industry L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR08 L5 proof waterfall" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR09 L5 proof geography" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR10 L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR11 L5 proof" --kind build_proof
.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR12 hybrid L5 proof stale pipeline" --kind build_proof
```

## Node Model

- `BuildLevel`: L0 through L5 build-readiness levels.
- `BuildProof`: completed L5 proof artifacts with deck, workbook, render, checks, and targets.
- `Template`: one installed `.potx` file.
- `Slide`: one slide within a template, including donor score, use class, signals, and readable OLE/think-cell hints.
- `TemplateFamily`: chart or template grouping.
- `QuarterSeedContract`: SimCorp use-case contract from the Salesforce-backed quarter seed-bank spec.
- `SalesDirector`: regional director.
- `SalesforceFit`: director-specific Q2 chart gates from the Salesforce fit test.
- `AutomationLane`: `ppttc`, native think-cell chart update, table-image donor, or fallback lane.
- `Runtime`: the Windows/Parallels think-cell runtime capability probe.
- `COMInterface`: live-IDispatch interface (IID, internal name, func count) from typeinfo probe.
- `COMMethod`: per-interface method (DispId, flags, FHIDDEN visibility, params).
- `BinaryArtifact`: helper binary (e.g. tcserver.exe, ppttc.exe) with role, size, observed routes, HTTP libs.
- `EmbeddedResource`: an HTTP route or HTTP library reference embedded in a binary.
- `Schema`: a layer of the think-cellXML schema (embedded corpus-merged or per-build version-gated).
- `CloudEndpoint`: think-cell.com subdomain with category, role, auth, hosting topology.
- `IPCluster`: shared-IP grouping of CloudEndpoints (e.g. 213.61.194.234 Berlin block, 49.12.247.56 Hetzner stock proxies).
- `AuthEvidence`: verified-or-denied authentication marker (BCrypt API names, JWT markers, AWS V4 markers) with explicit `verdict` and `encoding` fields.
- `LocalArtifact`: on-disk file under `%AppData%\think-cell\` (settings.xml, aiauthentication.bin, log files).
- `ChartClass`: think-cell C++ chart class observed in CFB-extracted think-cellXML.
- `ExtractedDeck`: a single bound-deck whose CFB streams were dumped for chart-class extraction.

## Edge Model

- `HAS_BUILD_LEVEL`: corpus to reusable build-readiness level.
- `REQUIRES_BUILD_LEVEL`: quarter seed contract to L0-L5 gates.
- `HAS_BUILD_PROOF`: quarter seed contract to completed proof artifact.
- `PROVEN_FOR_DIRECTOR`: proof artifact to the director it was run against.
- `CONTAINS_SLIDE`: template to slide.
- `HAS_SIGNAL`: slide to extracted signal.
- `HAS_THINKCELL_CLASS`: slide to readable `think-cellXML` class hints.
- `USES_TEMPLATE_FAMILY`: SimCorp contract to template family.
- `ELIGIBLE_FOR_DIRECTOR` / `FALLBACK_FOR_DIRECTOR`: data-shape gates by director.
- `USES_AUTOMATION_LANE`: contract to supported implementation lane.
- `VALIDATED_BY`: contract/corpus to VM runtime proof.
- `EXPOSES_INTERFACE`: runtime to COMInterface or BinaryArtifact (dispatch surface).
- `HAS_METHOD`: COMInterface to its COMMethod children.
- `EMBEDS_RESOURCE`: BinaryArtifact to EmbeddedResource (HTTP routes, libs).
- `CONTAINS_SCHEMA`: runtime to Schema layer (embedded corpus or per-build).
- `HOSTS_ENDPOINT`: IPCluster to CloudEndpoint that resolves to that IP.
- `RESOLVES_TO`: CloudEndpoint to IPCluster.
- `OCCURS_IN_CHART`: ChartClass to ExtractedDeck.
- `EVIDENCED_BY`: CloudEndpoint to AuthEvidence node.
- `STORES_TOKEN_FOR`: LocalArtifact (DPAPI blob) to its CloudEndpoint.
- `HAS_AUTH_EVIDENCE`: runtime to AuthEvidence node (verified or denied verdict).
- `USES_ENDPOINT`: BinaryArtifact (or runtime) to CloudEndpoint mentioned by URL.
- `HOSTED_ON`: CloudEndpoint to HostingProvider.
- `HAS_CLOUD_ENDPOINT`: corpus to CloudEndpoint.
- `INTEGRATES_PROVIDER` / `PROXIED_VIA`: stock-provider linkage to its proxy CloudEndpoint.
- `HAS_LOCAL_ARTIFACT`: runtime to a `%AppData%\think-cell` file.
- `HAS_CHART_CLASS` / `HAS_SCHEMA_INVENTORY`: corpus-level chart-class catalogue and aggregate schema stats.

## Build Levels

- `L0 Runtime Surface`: VM and addin capability proof.
- `L1 Salesforce Fit Gate`: director eligibility and fallback proof.
- `L2 Template Family`: stock family mapping.
- `L3 Slide Donor`: candidate donor/reference slide selection.
- `L4 Named Seed Contract`: real named think-cell seed surface.
- `L5 Binding Proof`: bound output render and package assertion.

## Current Takeaways

- 497 template slides were indexed.
- 139 slides expose readable `think-cellXML`.
- 51 slides carry empty `m_strName` and are nameable donor candidates.
- 37 slides are high-fit native chart donor candidates.
- 11 slides are table reference/donor probes.
- 25 slides are avoid-by-default for SimCorp operating reviews.
- 12 contract-level `BuildProof` nodes are present for 2026-Q2: QTR01 through
  QTR12.
- Current graph size: 752 nodes, 4,089 edges, and 589 RAG documents.
- Stock donor proofs are represented as `BuildProof` nodes too: QTR04 scatter,
  QTR05 FY26 renewal Gantt, and QTR06 Q2 renewal Gantt.

The graph should be the first stop for future template-selection work. It does
not replace actual VM validation; it narrows which slides and contracts deserve
that validation.
