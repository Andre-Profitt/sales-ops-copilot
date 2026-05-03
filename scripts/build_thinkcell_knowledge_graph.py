#!/usr/bin/env python3
"""Build a lightweight knowledge graph and Graph-RAG index for think-cell work."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PERIOD = "2026-Q2"
DEFAULT_OUTPUT_DIR = ROOT / "state" / "thinkcell_bridge" / "knowledge_graph"


@dataclass
class Node:
    id: str
    kind: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    relation: str
    target: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass
class RagDocument:
    id: str
    kind: str
    title: str
    text: str
    node_ids: list[str]
    terms: list[str]


CORPUS_DOCS = [
    {
        "key": "automation_api_surface",
        "title": "think-cell automation/API surface (manual-attributed)",
        "path": "docs/thinkcell-corpus/automation-api-surface.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
            "https://www.think-cell.com/en/resources/manual/exceldataautomation",
            "https://www.think-cell.com/en/resources/manual/jsondataautomation",
            "https://www.think-cell.com/en/resources/manual/style-files",
            "https://www.think-cell.com/en/resources/manual/import-mekko-graphics",
        ],
        "summary": (
            "Stable readable hub for the think-cell COM API: Excel data "
            "automation (CreateUpdate, AddRangeData, AddRangeImage, Send), "
            "PowerPoint API (PresentationFromTemplateStep3, UpdateBatchStep3, "
            "style/Mekko/UI methods), JSON automation (.ppttc + tcserver), "
            "Developer Setup (VBA/C#/VSTO/late binding/HRESULT), official "
            "examples, and the proven/observed_uninvoked/blocked/not_found "
            "capability verdict + Adoption Matrix."
        ),
    },
    {
        "key": "automation_api_source_map",
        "title": "think-cell automation API source map (link graph + factory status)",
        "path": "docs/thinkcell-corpus/automation-api-source-map.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
            "https://www.think-cell.com/en/resources/manual/introductionautomation",
            "https://www.think-cell.com/en/resources/manual/exceldataautomation",
            "https://www.think-cell.com/en/resources/manual/exceldatalinks",
            "https://www.think-cell.com/en/resources/manual/jsondataautomation",
            "https://www.think-cell.com/en/resources/manual/style-files",
            "https://www.think-cell.com/en/resources/manual/import-mekko-graphics",
        ],
        "summary": (
            "Structured link graph from each official think-cell manual page "
            "and Microsoft Learn reference to its factory implication and "
            "status (production / proof_candidate / reference_only / blocked "
            "/ not_applicable). Includes an Adoption Matrix per lane and "
            "explicit probe coverage for proof candidates."
        ),
    },
    {
        "key": "json_automation_hub",
        "title": "think-cell JSON Data Automation Knowledge Hub (.ppttc)",
        "path": "docs/thinkcell-corpus/json-data-automation-hub.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/jsondataautomation",
        ],
        "summary": (
            "Durable hub for .ppttc JSON automation as used in the SimCorp "
            "Sales Director deck factory. Anchors official .ppttc shape, data "
            "types, and template/data/name/table contract to the latest VM "
            "probe and proven QTR04/QTR05 binding evidence."
        ),
    },
    {
        "key": "unblock_matrix",
        "title": "think-cell unblock matrix",
        "path": "docs/thinkcell-corpus/unblock-matrix.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
            "https://www.think-cell.com/en/resources/manual/exceldataautomation",
            "https://www.think-cell.com/en/resources/manual/jsondataautomation",
            "https://www.think-cell.com/en/resources/manual/import-mekko-graphics",
        ],
        "summary": (
            "Decision registry for contested automation lanes: native Mekko, "
            "Mekko Graphics import, native editable tables, Office Web "
            "Add-ins, direct chart creation, tcserver.exe, and style API. "
            "Separates direct API support from factory-unblocked donor lanes "
            "and hard platform blocks."
        ),
    },
    {
        "key": "hidden_surface_probe",
        "title": "think-cell hidden surface probe",
        "path": "docs/thinkcell-corpus/hidden-surface-probe.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
        ],
        "summary": (
            "Bounded reverse-engineering probe for hidden think-cell "
            "constructor/ribbon surfaces. Uses IDispatch.GetIDsOfNames over "
            "candidate names mined from tcaddin.dll and confirms no callable "
            "headless chart constructor was found."
        ),
    },
    {
        "key": "com_registry_probe",
        "title": "think-cell COM registry probe",
        "path": "docs/thinkcell-corpus/com-registry-probe.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
        ],
        "summary": (
            "Registry, OleViewDotNet, live COMAddIns, and Procmon evidence "
            "for the VM. Confirms think-cell registers a single late-bound "
            "add-in CLSID backed by tcaddin.dll, with no registered TypeLib, "
            "no LocalServer32, and no separate chart-factory CLSID."
        ),
    },
    {
        "key": "interactive_ui_path_probe",
        "title": "think-cell interactive UI path probe",
        "path": "docs/thinkcell-corpus/interactive-ui-path-probe.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/api",
        ],
        "summary": (
            "Desktop-console follow-up for UI-only think-cell methods. "
            "Proves StartTableInsertion plus a scripted slide click creates "
            "a native CSmartGrid table object, but the payload has no "
            "m_strName and is not yet a production ppttc/Excel-bound lane. "
            "ShowChartGallery did not create a chart."
        ),
    },
    {
        "key": "github_surface_scan",
        "title": "think-cell GitHub surface scan",
        "path": "docs/thinkcell-corpus/github-surface-scan.md",
        "manual_urls": [
            "https://github.com/think-cell",
            "https://github.com/think-cell/think-cell-library",
            "https://github.com/Philistino/ThinkcellBuilder",
            "https://github.com/duarteocarmo/think-cell",
            "https://github.com/ZoeDekraker/think-cell-chart-update",
        ],
        "summary": (
            "GitHub scan for official and third-party think-cell automation "
            "surfaces. Confirms the official org exposes C++ libraries/forks, "
            "not an Office automation SDK, while public Python repos are "
            "ppttc writers that require named template objects. Captures "
            "adoption ideas for a stricter internal writer/linter."
        ),
    },
    {
        "key": "ppttc_validator",
        "title": "think-cell .ppttc validator / lint gate",
        "path": "docs/thinkcell-corpus/ppttc-validator.md",
        "manual_urls": [
            "https://www.think-cell.com/en/resources/manual/jsondataautomation",
        ],
        "summary": (
            "Reusable structural and manifest-drift gate for the .ppttc files "
            "the LAND deck factory emits. Pure Python (no Office, no VM, no "
            "think-cell). Catches malformed JSON, bad array/template/data/"
            "name/table shape, duplicate names, and (with an expected-name "
            "manifest) drift between emitted names and the wired template — "
            "the most common cause of think-cell loading the deck and applying "
            "no data."
        ),
    },
    {
        "key": "tier1_novel_probes",
        "title": "think-cell tier-1 novel probes (plan)",
        "path": "docs/thinkcell-corpus/tier1-novel-probes.md",
        "manual_urls": [],
        "summary": (
            "Plan for five tier-1 novel probes targeting code paths the static "
            "GetIDsOfNames scan did not cover: ITypeInfo enumeration, PE "
            "resource extraction, clipboard-format dump after a chart copy, "
            "rerun of the 3,200-name candidate scan against tcXlAddIn/tcUpdate, "
            "and architecture-sibling DLL diffing."
        ),
    },
    {
        "key": "tier1_results_2026_05_01",
        "title": "think-cell tier-1 probe results (2026-05-01)",
        "path": "docs/thinkcell-corpus/tier1-results-2026-05-01.md",
        "manual_urls": [],
        "summary": (
            "Tier-1 probe outcomes. Headline: ITypeInfo enumeration succeeds — "
            "all three IDispatch implementations expose ITypeInfo with internal "
            "interface names + IIDs + complete func tables (IPpMacroInterface "
            "{24f3e526-2a15-4b8b-bc6a-558500f451c1}, IXlMacroInterface "
            "{085347c3-2d5b-4885-869a-b9cc362b924c}, IUpdateBatch "
            "{be9bb0c3-e5fb-4de5-b499-aae20fff6fad}). PE resources expose 57KB "
            "tc15 baseline style XML using new https://schemas.think-cell.com/"
            "next/tcstyle namespace. tcaddin.dll is ARM64-only; no x86/x64 "
            "siblings. tcasr.exe sidecar binary confirmed but lazy-spawned."
        ),
    },
    {
        "key": "tier2_results_2026_05_01",
        "title": "think-cell tier-2 probe results (2026-05-01)",
        "path": "docs/thinkcell-corpus/tier2-results-2026-05-01.md",
        "manual_urls": [],
        "summary": (
            "Tier-2 probe outcomes. LoadStyleForRegion proven production-ready. "
            "ShowChartGallery succeeds in non-interactive SSH for all three "
            "HWND variants in 758–834ms — surprising headless lane. Shape.Tag "
            "introspection: single tag THINKCELLSHAPEDONOTDELETE on 307/499 "
            "shapes (61.5%) in LAND seed deck; values are 22-char base64-like "
            "opaque IDs matching install-GUID format. Strongly-typed C# interop "
            "generated for IPpMacroInterface/IXlMacroInterface/IUpdateBatch "
            "with all 25 methods and 7 FHIDDEN markers. Confirms next/tcstyle "
            "schema is strict superset of installed 36264/tcstyle (+60 elements, "
            "+10 attributes — tc15 schema preview)."
        ),
    },
    {
        "key": "tier3_results_2026_05_02",
        "title": "think-cell tier-3 probe results (2026-05-02)",
        "path": "docs/thinkcell-corpus/tier3-results-2026-05-02.md",
        "manual_urls": [],
        "summary": (
            "Tier-3 probe outcomes across five endpoint families. COM dispatch "
            "definitively closed: only IClientSecurity resolves beyond "
            "IUnknown/IDispatch (proxy boilerplate, not surface). No "
            "IConnectionPointContainer, IPersist*, IProvideClassInfo*. Custom "
            "shape interfaces also closed: 60 sampled shapes, 40 think-cell-"
            "managed, all expose only IDispatch — no third metadata path "
            "beyond Shape.Tags + customXml. Cloud topology mapped to 22 "
            "subdomains across AI / auth / update / telemetry / stock-proxy / "
            "license / static / schemas / training / analytics / marketing "
            "buckets. tcserver enumerates 5 routes: /api, /api/v1/search, "
            "/auth, /schemas, /v0. aiauthentication.bin confirmed DPAPI-"
            "encrypted (current-user bound). Update mechanism failed at "
            "2026-05-02T01:00:15Z (code 3 KNOWNPROBLEM). 6+ stock providers: "
            "Freepik/Pexels/Unsplash/Flaticon (proxied) + Getty/Canto/"
            "Brandfolder (direct API). tcfield_S<NN>_<purpose> field naming "
            "convention surfaced from settings.xml."
        ),
    },
    {
        "key": "phases_master_runbook",
        "title": "think-cell phases master runbook",
        "path": "docs/thinkcell-corpus/phases-master-runbook.md",
        "manual_urls": [],
        "summary": (
            "Single canonical reference for the six think-cell investigation "
            "phases (Phase 0 public/local intel, Phase 1 Frida+mitmproxy "
            "capture, Phase 2 Ghidra LLM-assisted decompile, Phase 3 "
            "think-cellXML grammar inference, Phase 4 targeted exercises, "
            "Phase 5 background research) plus stop rules. Read first when "
            "extending the investigation; do not start a phase without "
            "checking the runbook's stop conditions."
        ),
    },
    {
        "key": "runbook_phase1_frida_mitm",
        "title": "Phase 1 Frida + mitmproxy capture runbook",
        "path": "docs/thinkcell-corpus/runbook_phase1_frida_mitm_capture.md",
        "manual_urls": [],
        "summary": (
            "Manual workflow for capturing IDispatch::Invoke traffic via Frida "
            "16.7+ Process.attachModuleObserver paired with mitmproxy on the "
            "VM. Targets all 22 think-cell.com subdomains. Critical: Microsoft "
            "Defender ASR (KB0233) ships a YARA rule that deletes tcaddin.dll/"
            "tcasr.exe on hook-pattern detection — disable ASR or use Stalker "
            "(BBL-level instrumentation, no .text modification) to avoid trip."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_synthesis",
        "title": "Research swarm synthesis (2026-05-01)",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/SYNTHESIS.md",
        "manual_urls": [],
        "summary": (
            "Cross-cutting synthesis of 8 parallel research agents. New "
            "surfaces flagged: tcasr.exe sidecar (named-mutex + Win32 message "
            "+ shared-memory IPC), browser-extension native messaging, "
            "server.think-cell.com/portal SSO. Confirms public surface is "
            "category-standard (most PowerPoint chart add-ins ship zero "
            "developer API). Step* family is COM interface evolution; Step1/"
            "Step2 predecessors are likely callable but FHIDDEN. Patents are "
            "algorithmic (label placement, image extraction), not architectural."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent1_patents",
        "title": "Research swarm agent 1 — patent miner",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-1-patents.md",
        "manual_urls": [],
        "summary": (
            "~10 US patents/applications by Think-Cell Software GmbH. All "
            "algorithmic (layout constraint solving, label placement, "
            "image-based chart-data extraction, pattern-driven canvas "
            "filling). No coverage of OOXML custom XML parts, COM dispatch, "
            "ribbon callbacks, or wire formats. Closest hint: US 10,789,414 "
            "(pattern-based canvas filling, possible conceptual ancestor of "
            ".ppttc) and US 10,776,448 (cell-based reactive computing, sole-"
            "Schoedl filing, possible conceptual ancestor of JSON automation)."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent2_wayback",
        "title": "Research swarm agent 2 — wayback + community recon",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-2-wayback-community.md",
        "manual_urls": [],
        "summary": (
            "Wayback Machine snapshots of think-cell manual pages 2014–2026 "
            "and community-discovered tricks. Confirms API has been purely "
            "additive over 6 years — no methods retracted. Community wrappers "
            "(duarteocarmo/think-cell, Philistino, dbdoan) all assume named-"
            "template lane; none probe hidden surface."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent3_talks",
        "title": "Research swarm agent 3 — talks + LinkedIn intel",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-3-talks-linkedin.md",
        "manual_urls": [],
        "summary": (
            "21 verified think-cell engineer talks. Headline: Simon McPartlin's "
            "'Industrial Strength Software Hacking' (Meeting C++ 2014) is the "
            "public reference description of how tcaddin.dll modifies Office — "
            "function detouring framework + signature-based target finding "
            "via CFindCodePattern. Sebastian Theophil's 2024 ARM talk continues "
            "the lineage on Apple Silicon / Windows-on-ARM. Stack signals: "
            "Boost.Spirit (.ppttc parser), COIN-OR CLP (layout LP), OpenCV+"
            "Leptonica (image-extraction patents)."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent4_adjacent",
        "title": "Research swarm agent 4 — adjacent product API survey",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-4-adjacent-products.md",
        "manual_urls": [],
        "summary": (
            "10 PowerPoint chart/automation competitors surveyed. Most "
            "(Macabacus, Efficient Elements, Aploris, Power-user, BrightSlide, "
            "empower) ship zero public API/SDK. Mekko Graphics is the closest "
            "peer on COM surface size (small IAddInUtilities) and exposes "
            "GetChartData/IsMekkoChart that think-cell deliberately omits — "
            "a category-norm chart-introspection lane think-cell could add. "
            "think-cell's tcserver is more than most competitors expose."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent5_cloud",
        "title": "Research swarm agent 5 — cloud probe",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-5-cloud-probe.md",
        "manual_urls": [],
        "summary": (
            "Initial cloud probe verdict was 'no SaaS' — but this missed the "
            "*.appcom.think-cell.com proxy convention and app.prod.ai.think-"
            "cell.com naming. Tier-3 probe later mapped 22 subdomains. "
            "Confirmed correct findings: no PowerPoint Web / Office Mobile / "
            "Word / OneNote / Visio integration. Browser extension uses native "
            "messaging to local desktop add-in (undocumented protocol)."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent6_decompile",
        "title": "Research swarm agent 6 — LLM decompile pipeline spec",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-6-llm-decompile-pipeline.md",
        "manual_urls": [],
        "summary": (
            "Decision-ready RE pipeline for tcaddin.dll on M4 Max: Ghidra 11.x "
            "headless + RecoverClassesFromRTTIScript + ghidrecomp bulk export "
            "+ Claude Opus 4.7 batch labeling + SQLite + sqlite-vec. $35-60/run "
            "on Anthropic Batch API; 4-8h wall-clock; OSS-only path. IDA Pro "
            "is the upgrade lever if budget exists; Hex-Rays sometimes "
            "outperforms Ghidra on x86 but Ghidra wins on ARM64."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent7_versions",
        "title": "Research swarm agent 7 — differential build analysis",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-7-version-evolution.md",
        "manual_urls": [],
        "summary": (
            "API has been purely additive for 6 years. .ppttc JSON introduced "
            "in tc9 (April 2018, IANA-registered application/vnd.think-cell."
            "ppttc+json by Arno Schoedl). tcserver.exe shipped tc10 (2019) "
            "alongside macOS support. GetStyleName officially 'new' in tc14 "
            "(Nov 2025) but GetStyleNameStep2 was already resolvable — proves "
            "method resolution lags documentation. Installed 15.0.100.220 is "
            "a pre-GA tc15 pilot. Step1/Step2 predecessors of *Step3 methods "
            "likely exist as callable FHIDDEN methods (now confirmed by tier 1)."
        ),
    },
    {
        "key": "research_swarm_2026_05_01_agent8_academic",
        "title": "Research swarm agent 8 — academic RE literature",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-01/agent-8-academic-literature.md",
        "manual_urls": [],
        "summary": (
            "Survey of academic + industry RE literature for techniques the "
            "user's static probes do not cover. Top recommendations: dynamic "
            "binary instrumentation (Frida/TinyInst/DynamoRIO) on POWERPNT.EXE "
            "(Check Point did this for MSGraph.Chart.8 — same Office family); "
            "coverage-guided harness fuzzing (WINNIE on WinAFL/Jackalope+"
            "TinyInst); BinDiff/ghidriff between two tcaddin versions; "
            "OOAnalyzer/DeClassifier C++ class-hierarchy + RTTI recovery."
        ),
    },
    {
        "key": "master_state",
        "title": "think-cell research MASTER STATE",
        "path": "docs/thinkcell-corpus/MASTER_STATE.md",
        "manual_urls": [],
        "summary": (
            "Single canonical tracker for think-cell investigation phases (0/0b/1-10), "
            "headline findings (COM dispatch closed, 22 cloud subdomains, think-cellXML "
            "cracked via olefile CFB extraction, DPAPI license-token format known, "
            "TCLayout.ActiveDocument.1 is virtual COM resolved by tcaddin.dll's hook "
            "engine), and open queue. Read first when returning to the work."
        ),
    },
    {
        "key": "research_swarm_2026_05_02_deep_techniques",
        "title": "Research swarm 2026-05-02 — deep techniques (Pass 2)",
        "path": "docs/thinkcell-corpus/research-swarm-2026-05-02/agent-deep-techniques.md",
        "manual_urls": [],
        "summary": (
            "Post-2025 frontier RE techniques for tcaddin.dll. Top-5: D-LiFT + "
            "Idioms + LLM4Decompile-Ref-22B-V2 (RL-tuned, compiler-correctness "
            "gating, eliminates 93% LLM-decompile error rate, recovers "
            "DISPPARAMS/VARIANT/SAFEARRAY); ChatPRE replaces BinPRE for "
            "grammar inference (F1 0.89 vs 0.42-0.55); ChatAFL for IDispatch "
            "fuzzing; Frida 16.7+ Process.attachModuleObserver + Stalker BBL "
            "instrumentation (catches tcaddin.dll before its own pattern scan, "
            "no .text modification, defeats anti-tamper); KB0233 + Theophil "
            "ACCU 2023+2024 talks — Microsoft Defender ASR ships YARA "
            "signature deleting tcaddin.dll/tcasr.exe; reverse-engineer the "
            "YARA rule for free hook-engine opcode signature recon."
        ),
    },
    {
        "key": "phase12_progressive_decoding_2026_05_02",
        "title": "Phase 12 progressive decoding — 2026-05-02",
        "path": "docs/thinkcell-corpus/phase12_progressive_decoding-2026-05-02.md",
        "manual_urls": [],
        "summary": (
            "Auth-token issuance fully decoded: GET aiauthentication.appcom."
            "think-cell.com/?build=&systemid=&licensekey=, no Authorization "
            "header, no HMAC on request, returns 121B URL-encoded payload "
            "(expires/licensekeyid/userhalfmonths/quota/hash). tc_toolkit."
            "tcauth.mint_token() works live from Mac. /core/ HMAC scheme "
            "still gated — requires AI ribbon-button click which is "
            "non-trivial to programmatically trigger. Failed click strategies "
            "(empirical): ExecuteMso (custom tc: namespace blocked), UIA "
            "ControlViewWalker, UIA all-types managed client, Alt+Q Tell-Me "
            "search, UIA RawViewWalker (Stage 1 — 2026-05-02-163300, 16 "
            "invokables all PowerPoint chrome, zero think-cell). UIA fully "
            "ruled out at every filter level. Next: Stage 2 MSAA via oleacc "
            "AccessibleObjectFromWindow (Microsoft sample "
            "CSOfficeRibbonAccessibility ports cleanly), Stage 3 QAT pinning "
            "via PowerPoint.officeUI XML, Stage 4 Frida custom handlers "
            "(BCryptCreateHash/HashData/FinishHash) wired into capture "
            "script for HMAC byte capture."
        ),
    },
]


BUILD_LEVELS = [
    {
        "level": "L0",
        "label": "Runtime Surface",
        "purpose": "Prove the Windows/PowerPoint/Excel/think-cell automation surface exists before any build work.",
        "node_kinds": ["Runtime", "AutomationLane"],
        "build_action": "Run the VM capability probe and keep ppttc, PowerPoint addin, and Excel addin methods visible.",
        "success_gate": "Programmatic lab status is pass and probe reports ppttc plus AddRangeData/AddRangeImage.",
    },
    {
        "level": "L1",
        "label": "Salesforce Fit Gate",
        "purpose": "Decide which directors and chart families are eligible from real quarter data.",
        "node_kinds": ["SalesforceFit", "SalesDirector", "QuarterSeedContract"],
        "build_action": "Use the quarter seed-bank fit counts and director fallback lists before selecting visuals.",
        "success_gate": "Every contract has explicit eligible and fallback directors with ARR/ACV guardrails intact.",
    },
    {
        "level": "L2",
        "label": "Template Family",
        "purpose": "Map each SimCorp visual contract to the closest think-cell stock family.",
        "node_kinds": ["TemplateFamily", "Template", "QuarterSeedContract"],
        "build_action": "Select stock family references such as Bar, Column; Scatter, Bubble; Timeline, Gantt; Waterfall; Mekko; Tables.",
        "success_gate": "At least one matching family/template is attached to each production candidate contract.",
    },
    {
        "level": "L3",
        "label": "Slide Donor",
        "purpose": "Pick specific stock slides that can serve as visual or native-chart donor references.",
        "node_kinds": ["Slide", "Signal", "ThinkCellClass", "UseClass"],
        "build_action": "Use high-score unnamed donor candidates for chart seeds and table-reference slides for table-image/native-table probes.",
        "success_gate": "Candidate slides expose readable think-cellXML and have a relevant use class or signal.",
    },
    {
        "level": "L4",
        "label": "Named Seed Contract",
        "purpose": "Convert a visual donor into a named think-cell seed surface that automation can update.",
        "node_kinds": ["QuarterSeedContract", "AutomationLane"],
        "build_action": "Author or verify named elements in PowerPoint with think-cell installed; do not treat stock POTX as already ppttc-ready.",
        "success_gate": "Seed PPTX contains the expected AddRangeData/AddRangeImage names before binding.",
    },
    {
        "level": "L5",
        "label": "Binding Proof",
        "purpose": "Run the actual data binding and prove the output deck changed with expected values.",
        "node_kinds": ["Runtime", "QuarterSeedContract", "SalesforceFit"],
        "build_action": "Run ppttc or Excel UpdateBatch, render the output, and assert bound values in the package.",
        "success_gate": "Bound deck renders nonblank output and contains expected data/text, not merely ppttc exit code 0.",
    },
]


# Cloud topology — 22 think-cell.com subdomains catalogued from binary string
# extraction (endpoints_and_environment probe) + SSL cert SAN extraction +
# tier-3 manual role assignment. Update this list when new subdomains land.
CLOUD_ENDPOINTS = [
    # AI infrastructure
    {
        "host": "app.prod.ai.think-cell.com",
        "category": "ai",
        "role": "production AI endpoint exposing /core/ path; auth-required",
        "auth": "required",
    },
    {
        "host": "ai.think-cell.com",
        "category": "ai",
        "role": "AI infrastructure parent host",
        "auth": "unknown",
    },
    {
        "host": "prod.ai.think-cell.com",
        "category": "ai",
        "role": "AI prod (wildcard *.prod.ai cert)",
        "auth": "unknown",
    },
    {
        "host": "ai.appcom.think-cell.com",
        "category": "ai",
        "role": "AI app-communication subdomain; 403-everywhere on unauthenticated probe",
        "auth": "required",
    },
    # Auth subsystems
    {
        "host": "aiauthentication.appcom.think-cell.com",
        "category": "auth",
        "role": "dedicated AI auth endpoint; corresponds to local DPAPI-encrypted aiauthentication.bin",
        "auth": "issues_token",
    },
    {
        "host": "cdnauthentication.appcom.think-cell.com",
        "category": "auth",
        "role": "likely signs CDN URLs for static.think-cell.com access",
        "auth": "issues_token",
    },
    # Update / telemetry / ops
    {
        "host": "update.appcom.think-cell.com",
        "category": "update",
        "role": "auto-update server; matches tcupdate_log.log references",
        "auth": "unknown",
    },
    {
        "host": "usage.appcom.think-cell.com",
        "category": "telemetry",
        "role": "telemetry collector; receives install GUID + per-feature IDs (POST-only)",
        "auth": "install_id",
    },
    {
        "host": "bug.appcom.think-cell.com",
        "category": "ops",
        "role": "bug-reporting endpoint",
        "auth": "unknown",
    },
    {
        "host": "unsupported.appcom.think-cell.com",
        "category": "ops",
        "role": "deprecated / legacy fallback",
        "auth": "unknown",
    },
    # Stock-image proxies
    {
        "host": "freepik.appcom.think-cell.com",
        "category": "stock_proxy",
        "role": "Freepik image search proxy (nginx-fronted)",
        "auth": "proxy_injected",
    },
    {
        "host": "pexels.appcom.think-cell.com",
        "category": "stock_proxy",
        "role": "Pexels transparent proxy (returns Pexels homepage on /api); k8s-style /healthz returns 200",
        "auth": "proxy_injected",
    },
    {
        "host": "unsplash.appcom.think-cell.com",
        "category": "stock_proxy",
        "role": "Unsplash OAuth-injected proxy; OAuth bearer injected at proxy",
        "auth": "proxy_injected",
    },
    {
        "host": "flaticon.appcom.think-cell.com",
        "category": "stock_proxy",
        "role": "Flaticon icon search proxy (7th provider, not in [stockimages] settings list)",
        "auth": "proxy_injected",
    },
    # License / portal
    {
        "host": "server.think-cell.com",
        "category": "license",
        "role": "license/admin portal; /portal SSO-gated; TRACE method enabled (mild misconfig)",
        "auth": "sso",
    },
    {
        "host": "www.server.think-cell.com",
        "category": "license",
        "role": "license portal www variant",
        "auth": "sso",
    },
    # Schemas / static / training / analytics / marketing
    {
        "host": "schemas.think-cell.com",
        "category": "schemas",
        "role": "XSD distribution; /api allows GET+POST+OPTIONS+HEAD — likely schema validation endpoint",
        "auth": "unknown",
    },
    {
        "host": "static.think-cell.com",
        "category": "static",
        "role": "CDN; serves 4 public ppttc templates at /ppttc/template2-5.pptx (78KB-967KB)",
        "auth": "none",
    },
    {
        "host": "academy.think-cell.com",
        "category": "training",
        "role": "training/courses subdomain (referenced from www JS)",
        "auth": "unknown",
    },
    {
        "host": "matomo.think-cell.com",
        "category": "analytics",
        "role": "Matomo analytics (3rd-party tracker; in www JS)",
        "auth": "n/a",
    },
    {
        "host": "www.think-cell.com",
        "category": "marketing",
        "role": "marketing site",
        "auth": "none",
    },
    {"host": "think-cell.com", "category": "marketing", "role": "apex domain", "auth": "none"},
    # Network-recon adds (2026-05-02): brute-force enumeration + cert-SAN
    # extraction surfaced three more think-cell.com subdomains. Only demo. is
    # web-reachable; mail. is SMTP and vpn. is a VPN gateway.
    {
        "host": "demo.think-cell.com",
        "category": "marketing",
        "role": "Cloudflare-fronted marketing demo; SNI-restricted (handshake fails without specific config)",
        "auth": "none",
    },
    {
        "host": "mail.think-cell.com",
        "category": "ops",
        "role": "SMTP server (NOT web); cert-SAN evidence only",
        "auth": "n/a",
    },
    {
        "host": "vpn.think-cell.com",
        "category": "ops",
        "role": "VPN gateway (NOT web); cert mismatch on HTTP",
        "auth": "n/a",
    },
]


# Hosting topology by hostname — IP cluster, cloud provider, TLS issuer. Source:
# 2026-05-02 cross-host correlation pass (DNS + cert + traceroute). Only includes
# hostnames where the topology is verified.
HOSTING_TOPOLOGY = {
    # Berlin think-cell-owned IP block 213.61.194.0/24 — single shared GoDaddy 9-SAN cert
    "server.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "www.server.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "aiauthentication.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "cdnauthentication.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "bug.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "flaticon.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "unsupported.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "update.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "usage.appcom.think-cell.com": {
        "ip": "213.61.194.234",
        "provider": "think-cell Berlin",
        "tls_issuer": "GoDaddy G2 (9-SAN shared cert)",
    },
    "mail.think-cell.com": {
        "ip": "213.61.194.235",
        "provider": "think-cell Berlin",
        "tls_issuer": None,
    },
    "vpn.think-cell.com": {
        "ip": "213.61.194.236",
        "provider": "think-cell Berlin",
        "tls_issuer": None,
    },
    # Hetzner DE — stock-image proxy farm (3 vhosts on one box)
    "pexels.appcom.think-cell.com": {
        "ip": "49.12.247.56",
        "provider": "Hetzner DE",
        "tls_issuer": "Thawte TLS RSA CA G1",
    },
    "unsplash.appcom.think-cell.com": {
        "ip": "49.12.247.56",
        "provider": "Hetzner DE",
        "tls_issuer": "Thawte TLS RSA CA G1",
    },
    "freepik.appcom.think-cell.com": {
        "ip": "49.12.247.56",
        "provider": "Hetzner DE",
        "tls_issuer": "Thawte TLS RSA CA G1",
    },
    # Hetzner DE — marketing + schemas farm
    "matomo.think-cell.com": {"ip": "162.55.44.8", "provider": "Hetzner DE", "tls_issuer": None},
    "schemas.think-cell.com": {"ip": "162.55.44.8", "provider": "Hetzner DE", "tls_issuer": None},
    "www.think-cell.com": {"ip": "162.55.44.8", "provider": "Hetzner DE", "tls_issuer": None},
    "think-cell.com": {"ip": "162.55.44.8", "provider": "Hetzner DE", "tls_issuer": None},
    # Hetzner DE — isolated AI proxy
    "ai.appcom.think-cell.com": {
        "ip": "157.180.21.252",
        "provider": "Hetzner DE",
        "tls_issuer": None,
    },
    # Google Cloud — AI workloads (presumably for GPU)
    "app.prod.ai.think-cell.com": {
        "ip": "34.159.52.56",
        "provider": "Google Cloud (GCP)",
        "tls_issuer": "Let's Encrypt R12",
    },
    "prod.ai.think-cell.com": {
        "ip": "34.159.52.56",
        "provider": "Google Cloud (GCP)",
        "tls_issuer": "Let's Encrypt R12",
    },
    # AWS CloudFront — training site
    "academy.think-cell.com": {
        "ip": "99.84.234.x",
        "provider": "AWS CloudFront",
        "tls_issuer": "AWS Issuer",
    },
    # Cloudflare — marketing demo
    "demo.think-cell.com": {
        "ip": "104.18.34.21",
        "provider": "Cloudflare",
        "tls_issuer": "Cloudflare-issued",
    },
    # static CDN — issuer not yet captured
    "static.think-cell.com": {"ip": None, "provider": "think-cell CDN", "tls_issuer": None},
}


# 2026-05-02 finding: replaying the DPAPI-decrypted token across 60 endpoints
# in 5 styles (Bearer, Basic, X-License-Key, X-Thinkcell-Token, Cookie) produced
# zero diffs vs unauthenticated. Auth scheme is bespoke; assume HMAC-signed-
# request, /auth-issued-session, or mTLS. Phase 1 (Frida + mitmproxy capture) is
# the only path to observe the actual handshake.
AUTH_SCHEME_NOTE = (
    "DPAPI token replay (Bearer/Basic/X-License-Key/X-Thinkcell-Token/Cookie) "
    "produced zero diffs vs unauthenticated across 60 endpoints. Auth scheme "
    "is bespoke; assume HMAC-signed-request, /auth-issued-session, or mTLS."
)


# Stock-image / DAM providers integrated by the think-cell desktop add-in.
# 4 are proxied via *.appcom.think-cell.com; 3 are direct API / customer-tenant.
STOCK_PROVIDERS = [
    {"name": "Freepik", "kind": "proxy", "host": "freepik.appcom.think-cell.com"},
    {"name": "Pexels", "kind": "proxy", "host": "pexels.appcom.think-cell.com"},
    {"name": "Unsplash", "kind": "proxy", "host": "unsplash.appcom.think-cell.com"},
    {"name": "Flaticon", "kind": "proxy", "host": "flaticon.appcom.think-cell.com"},
    {"name": "Getty", "kind": "direct_api", "host": None, "config_field": None},
    {"name": "Canto", "kind": "direct_api", "host": None, "config_field": None},
    {
        "name": "Brandfolder",
        "kind": "direct_api",
        "host": None,
        "config_field": "BrandfolderAPIKey",
    },
]


# ---------------------------------------------------------------------------
# 2026-05-02 additions: Python libraries shipped this session that wrap the
# think-cell COM surface (tc_com_driver) or read/write the embedded chart XML
# format (tcxml). Recorded here as Library nodes so builders can ask which
# library wraps which COM method/interface or which library reads the format.
# ---------------------------------------------------------------------------
LIBRARIES = [
    {
        "name": "tcxml",
        "path": "libs/tcxml",
        "lang": "Python",
        "deps": ["lxml>=5.0", "olefile>=0.47"],
        "public_api": [
            "extract_thinkcell_streams",
            "parse_thinkcell_xml",
            "serialize_thinkcell_xml",
            "pack_thinkcell_stream",
            "load_schema",
            "Schema",
            "Element",
            "Attribute",
            "ChartClass",
            "ParsedChart",
            "ParsedElement",
        ],
        "status": "ready",
        "tests_passing": 7,
        "writer_status": "stubbed",  # pack_thinkcell_stream raises NotImplementedError
        "purpose": (
            "Reader/writer for think-cell's embedded chart XML inside .pptx CFB-wrapped "
            "oleObject*.bin streams. Reads + parses + serializes think-cellXML; CFB "
            "writer is a NotImplementedError stub for follow-up."
        ),
        "platform": "any",
        "reads_format": "think-cellXML",
        "writes_format": "think-cellXML",
        "wraps_com": False,
    },
    {
        "name": "tc_com_driver",
        "path": "libs/tc_com_driver",
        "lang": "Python",
        "deps": ["pywin32>=308 ; sys_platform == 'win32'"],
        "public_api": [
            "ThinkCellClient",
            "PpAddIn",
            "XlAddIn",
            "UpdateBatch",
            "ThinkCellError",
            "ThinkCellNotFoundError",
            "ThinkCellNotActiveError",
            "PowerPointNotRunningError",
            "WrongPlatformError",
            "PP_MACRO_IID",
            "XL_MACRO_IID",
            "UPDATE_BATCH_IID",
        ],
        "status": "ready",
        "tests_passing": 11,
        "writer_status": "n/a",
        "purpose": (
            "pywin32-backed wrapper around think-cell's documented IDispatch surface "
            "(IPpMacroInterface / IXlMacroInterface / IUpdateBatch). Vendor-sanctioned "
            "automation, no reverse engineering. 25 user-visible COM methods exposed."
        ),
        "platform": "Windows",
        "reads_format": None,
        "writes_format": None,
        "wraps_com": True,
        "wraps_interfaces": [
            ("IPpMacroInterface", "24f3e526-2a15-4b8b-bc6a-558500f451c1"),
            ("IXlMacroInterface", "085347c3-2d5b-4885-869a-b9cc362b924c"),
            ("IUpdateBatch", "be9bb0c3-e5fb-4de5-b499-aae20fff6fad"),
        ],
    },
]


# Chart-family taxonomy for the 89-class corpus. Each ChartClass is bucketed
# into one ChartFamily based on a substring rule against the class name.
# Order matters: longer/more-specific patterns first so e.g. "Pentagon" matches
# CPentagonGridlineAnchor rather than falling through to "PPT" or "Sequence".
CHART_FAMILY_PATTERNS: list[tuple[str, str]] = [
    # think-cellXML element-tag families. Substring-match against ChartClass name.
    ("Gantt", "Gantt"),
    ("Scatter", "Scatter"),
    ("Bubble", "Bubble"),
    ("Pie", "Pie"),
    ("Waterfall", "Waterfall"),
    ("Pentagon", "Pentagon"),
    ("Sequence", "SequenceChart"),  # CSequenceChart*, CSequenceMSGraphState
    ("DataAxis", "Axis"),  # CDataAxisGridline / Tickmark / Label / Break
    ("Gridline", "Gridline"),  # CGridline, CGridlinePair, *GridlineAnchor (catch-all)
    ("PPT", "PPTPrimitive"),  # CPPTLine, CPPTRectangle, etc. (rendering primitives)
    ("Container", "Container"),
    ("Rect", "Rect"),
    ("ShapeTable", "Table"),
    ("SmartGrid", "SmartGrid"),
    ("AdviseSink", "ComPlumbing"),
    ("VariableSource", "DataBinding"),
    ("TextVariable", "DataBinding"),
    ("TranslatedStrings", "DataBinding"),
    ("SLTBSizeCalculator", "Layout"),
]


def _classify_chart_family(class_name: str) -> str:
    for pattern, family in CHART_FAMILY_PATTERNS:
        if pattern in class_name:
            return family
    return "Other"


# COM dispatch boilerplate to filter out when ingesting typeinfo funcs — these
# are inherited from IUnknown / IDispatch and are not think-cell surface.
COM_BOILERPLATE_METHODS = {
    "QueryInterface",
    "AddRef",
    "Release",
    "GetTypeInfoCount",
    "GetTypeInfo",
    "GetIDsOfNames",
    "Invoke",
}

FUNCFLAG_FHIDDEN = 0x40


# Mechanism / virtual-ProgID layer: tcaddin.dll registers no CLSID for
# TCLayout.ActiveDocument.1, yet that ProgID appears in every think-cell
# chart's <mc:AlternateContent> block. Slide-XML probe confirms 80+ hits
# across 5 bound decks, registry probe confirms HKCR has no entry, and
# `New-Object TCLayout.ActiveDocument.1` fails. think-cell resolves the ProgID
# in-process by hooking Office's CLSIDFromProgID/CoCreateInstance — the same
# function-detouring mechanism Simon McPartlin presented at Meeting C++ 2014
# ("Industrial Strength Software Hacking") and Sebastian Theophil updated for
# ARM64 in 2024. Without tcaddin.dll loaded, every chart falls back to the
# pre-rendered <mc:Fallback> PNG.
HOOK_ENGINE_DESCRIPTION = (
    "tcaddin.dll's in-memory function-detouring engine. Intercepts Office's "
    "CLSIDFromProgID and CoCreateInstance to resolve unregistered ProgIDs "
    "(notably TCLayout.ActiveDocument.1) to internal C++ chart-rendering "
    "code. Pattern-scans Office binaries via CFindCodePattern. Targeted by "
    "Microsoft Defender ASR signature KB0233."
)

VIRTUAL_PROGIDS = [
    {
        "progid": "TCLayout.ActiveDocument.1",
        "role": "embedded chart object ProgID used in <mc:AlternateContent>",
        "registered": False,
        "evidence": (
            "82+ slide-XML hits across 5 bound decks; HKCR lookup returns "
            "nothing; New-Object fails. Resolved at runtime by tcaddin.dll's "
            "hook engine; falls back to <mc:Fallback> PNG when not loaded."
        ),
    },
]


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"missing input: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_programmatic_lab_json() -> Path:
    root = ROOT / "state" / "thinkcell_bridge" / "programmatic_lab"
    candidates = sorted(
        root.glob("*/thinkcell_programmatic_lab.json"), key=lambda item: item.stat().st_mtime
    )
    if not candidates:
        raise SystemExit(f"no programmatic lab JSON found under {root}")
    return candidates[-1]


def _latest_probe_json(subdir: str, glob_pattern: str) -> Path | None:
    """Return the newest matching probe JSON under state/thinkcell_bridge/<subdir>/, or None."""
    root = ROOT / "state" / "thinkcell_bridge" / subdir
    if not root.exists():
        return None
    candidates = sorted(root.glob(glob_pattern), key=lambda item: item.stat().st_mtime)
    return candidates[-1] if candidates else None


def _latest_probe_json_in_any(subdirs: list[str], glob_pattern: str) -> Path | None:
    """Return the newest matching probe JSON under any of state/thinkcell_bridge/<subdir>/."""
    candidates: list[Path] = []
    for subdir in subdirs:
        root = ROOT / "state" / "thinkcell_bridge" / subdir
        if not root.exists():
            continue
        candidates.extend(root.glob(glob_pattern))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item.stat().st_mtime)
    return candidates[-1]


def _load_json_lenient(path: Path) -> Any:
    """Load JSON, tolerating UTF-8 BOM (PowerShell often emits BOM-prefixed JSON)."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _node_id(kind: str, label: str) -> str:
    digest = hashlib.sha1(f"{kind}:{label}".encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:72]
    return f"{kind}:{slug}:{digest}"


def _tokens(text: str) -> list[str]:
    return sorted(set(re.findall(r"[a-z0-9][a-z0-9_+-]{1,}", text.lower())))


def _add_node(nodes: dict[str, Node], kind: str, label: str, **properties: Any) -> str:
    node_id = _node_id(kind, label)
    existing = nodes.get(node_id)
    if existing:
        existing.properties.update(
            {key: value for key, value in properties.items() if value is not None}
        )
    else:
        nodes[node_id] = Node(
            node_id,
            kind,
            label,
            {key: value for key, value in properties.items() if value is not None},
        )
    return node_id


def _add_edge(
    edges: list[Edge], source: str, relation: str, target: str, **properties: Any
) -> None:
    edges.append(
        Edge(
            source=source,
            relation=relation,
            target=target,
            properties={key: value for key, value in properties.items() if value is not None},
        )
    )


def _slide_doc(slide: dict[str, Any], node_id: str) -> RagDocument:
    ole_classes = sorted(
        {klass for ole in slide.get("ole_parts", []) for klass in ole.get("thinkcell_classes", [])}
    )
    text = "\n".join(
        [
            f"Template: {slide['template']}",
            f"Slide: {slide['slide_number']}",
            f"Title: {slide['title_guess']}",
            f"Family: {slide['family']}",
            f"Use class: {slide['use_class']}",
            f"SimCorp fit: {slide['simcorp_fit']}",
            f"Signals: {', '.join(slide.get('signals', []))}",
            f"Ole classes: {', '.join(ole_classes[:25])}",
            f"Text: {'; '.join(slide.get('text', [])[:12])}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="slide",
        title=f"{slide['template']} slide {slide['slide_number']}: {slide['title_guess']}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _contract_doc(contract: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Contract: {contract['name']}",
            f"Family: {contract['family']}",
            f"Template family: {contract['thinkcell_template_family']}",
            f"Priority: {contract['build_priority']}",
            f"Lane: {contract['supported_lane']}",
            f"Source: {contract['data_source']}",
            f"Guardrail: {contract['metric_guardrail']}",
            f"Fallback: {contract['fallback']}",
            f"Eligible directors: {', '.join(contract.get('eligible_directors', []))}",
            f"Fallback directors: {', '.join(contract.get('fallback_directors', []))}",
            f"Notes: {contract['notes']}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="quarter_contract",
        title=f"{contract['name']} - {contract['family']}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _proof_doc(proof: dict[str, Any], node_id: str) -> RagDocument:
    checks = ", ".join(
        f"{check.get('name')}={check.get('status')}" for check in proof.get("checks", [])
    )
    targets = ", ".join(
        f"{target.get('name')} slide {target.get('slide')}" for target in proof.get("targets", [])
    )
    text = "\n".join(
        [
            f"Proof: {proof['contract']}",
            f"Status: {proof['status']}",
            f"Period: {proof['period']}",
            f"Director: {proof['director_slug']}",
            f"Deck: {proof['deck']}",
            f"Workbook: {proof['workbook']}",
            f"Render dir: {proof['render_dir']}",
            f"Targets: {targets}",
            f"Checks: {checks}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="build_proof",
        title=f"{proof['contract']} L5 proof - {proof['status']}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _template_doc(summary: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Template: {summary['template']}",
            f"Family: {summary['family']}",
            f"Slides: {summary['slide_count']}",
            f"OLE parts: {summary['ole_parts']}",
            f"Readable think-cellXML parts: {summary['readable_thinkcellxml_parts']}",
            f"Native tables: {summary['native_tables']}",
            f"Chart refs: {summary['chart_refs']}",
            f"Use classes: {summary['use_classes']}",
            f"Top slide numbers: {summary['top_slide_numbers']}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="template",
        title=summary["template"],
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _build_level_doc(level: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Build level: {level['level']} {level['label']}",
            f"Purpose: {level['purpose']}",
            f"Graph node kinds: {', '.join(level['node_kinds'])}",
            f"Build action: {level['build_action']}",
            f"Success gate: {level['success_gate']}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="build_level",
        title=f"{level['level']} - {level['label']}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _read_corpus_doc_text(path: Path, max_chars: int = 8000) -> str:
    if not path.exists():
        return ""
    body = path.read_text(encoding="utf-8")
    if len(body) <= max_chars:
        return body
    return body[:max_chars]


def _corpus_doc_doc(spec: dict[str, Any], node_id: str, body: str) -> RagDocument:
    summary = spec.get("summary") or ""
    manual = ", ".join(spec.get("manual_urls", []) or [])
    text = "\n".join(
        [
            f"Corpus doc: {spec['title']}",
            f"Path: {spec['path']}",
            f"Manual sources: {manual}" if manual else "",
            f"Summary: {summary}",
            "",
            body,
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="corpus_doc",
        title=spec["title"],
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _endpoint_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    topo = HOSTING_TOPOLOGY.get(spec["host"], {})
    needs_replay_note = spec["category"] in {"ai", "auth"} and spec.get("auth") not in (
        None,
        "n/a",
        "none",
    )
    parts = [
        f"Cloud endpoint: {spec['host']}",
        f"Category: {spec['category']}",
        f"Role: {spec['role']}",
        f"Auth: {spec.get('auth', 'unknown')}",
    ]
    if topo.get("provider"):
        parts.append(
            f"Hosting: {topo['provider']} ({topo.get('ip') or 'ip unknown'}); TLS: {topo.get('tls_issuer') or 'unknown'}"
        )
    if needs_replay_note:
        parts.append(f"Auth replay note: {AUTH_SCHEME_NOTE}")
    text = "\n".join(parts)
    return RagDocument(
        id=f"doc:{node_id}",
        kind="cloud_endpoint",
        title=f"{spec['host']} ({spec['category']})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _provider_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Stock provider: {spec['name']}",
            f"Integration kind: {spec['kind']}",
            f"Proxy host: {spec.get('host') or '(direct API; no proxy)'}",
            f"Config field: {spec.get('config_field') or '(none)'}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="stock_provider",
        title=f"{spec['name']} ({spec['kind']})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _artifact_doc(record: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Local artifact: {record.get('path')}",
            f"Size bytes: {record.get('size')}",
            f"SHA256: {record.get('sha256')}",
            f"Magic byte format: {record.get('magic_byte_format')}",
            f"Last write UTC: {record.get('last_write_utc')}",
            f"Is text: {record.get('is_text')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="local_artifact",
        title=f"{(record.get('path') or '').replace('/', chr(92)).rsplit(chr(92), 1)[-1]} ({record.get('magic_byte_format', 'unknown')})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _interface_doc(target: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"COM interface: {target.get('type_name')}",
            f"Live object label: {target.get('label')}",
            f"IID: {target.get('type_guid')}",
            f"Func count: {target.get('func_count')}",
            f"Object type: {target.get('object_type')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="com_interface",
        title=f"{target.get('type_name')} ({target.get('label')})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _method_doc(method: dict[str, Any], interface_label: str, node_id: str) -> RagDocument:
    flags = int(method.get("flags") or 0)
    visibility = "FHIDDEN" if (flags & FUNCFLAG_FHIDDEN) else "normal"
    params = ", ".join(method.get("param_names") or [])
    text = "\n".join(
        [
            f"COM method: {interface_label}.{method.get('name')}",
            f"DispId: {method.get('memid')}",
            f"Flags hex: 0x{flags:x}",
            f"Visibility: {visibility}",
            f"Param count: {method.get('params')}",
            f"Param names: {params}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="com_method",
        title=f"{interface_label}.{method.get('name')} (DispId {method.get('memid')})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _hook_engine_doc(node_id: str) -> RagDocument:
    text = "\n".join(
        [
            "Mechanism: tcaddin.dll hook engine",
            f"Description: {HOOK_ENGINE_DESCRIPTION}",
            "Public reference: McPartlin 2014 Meeting C++ 'Industrial Strength Software Hacking' "
            "+ Theophil 2024 'Passive ARM Assembly Skills (and Hacking)'.",
            "Architectural implication: tcaddin.dll is not optional for chart rendering — "
            "it is how the COM object exists at all. Defender ASR signature KB0233 deletes it.",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="mechanism",
        title="tcaddin.dll hook engine (CLSIDFromProgID interception)",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _virtual_progid_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Virtual ProgID: {spec['progid']}",
            f"Role: {spec['role']}",
            f"Registered in HKCR: {spec['registered']}",
            f"Evidence: {spec['evidence']}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="virtual_progid",
        title=f"{spec['progid']} (virtual / hook-resolved)",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _chart_class_doc(name: str, frequency: int, node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"think-cell C++ chart class: {name}",
            f"Element-tag occurrences across corpus: {frequency}",
            "Source: think-cellXML element-tag scan of bound-deck oleObject CFB streams. "
            "Element tags map 1:1 to MFC C++ class names (Hungarian-prefixed members "
            "appear as XML attributes).",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="chart_class",
        title=f"{name} (×{frequency})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _library_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Python library: {spec['name']}",
            f"Repo path: {spec['path']}",
            f"Language: {spec['lang']}",
            f"Platform: {spec.get('platform', 'any')}",
            f"Status: {spec['status']}",
            f"Writer status: {spec.get('writer_status', 'n/a')}",
            f"Tests passing: {spec.get('tests_passing', 0)}",
            f"Dependencies: {', '.join(spec.get('deps', []))}",
            f"Public API: {', '.join(spec.get('public_api', []))}",
            f"Reads format: {spec.get('reads_format') or '(none)'}",
            f"Writes format: {spec.get('writes_format') or '(none)'}",
            f"Wraps COM: {spec.get('wraps_com', False)}",
            f"Purpose: {spec.get('purpose', '')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="library",
        title=f"{spec['name']} ({spec.get('platform', 'any')}, {spec['status']})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _etw_provider_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    flags = []
    if spec.get("is_thinkcell_specific"):
        flags.append("think-cell-specific")
    if spec.get("is_auth_relevant"):
        flags.append("auth-relevant")
    if spec.get("is_office_powerpoint"):
        flags.append("office/ppt")
    if spec.get("recommended_for_phase12"):
        flags.append("recommended-for-phase1/2-capture")
    text = "\n".join(
        [
            f"ETW provider: {spec['name']}",
            f"GUID: {spec['guid']}",
            f"Source DLL hint: {spec.get('source_dll') or '(unknown)'}",
            f"Flags: {', '.join(flags) if flags else '(none)'}",
            f"Capture rationale: {spec.get('rationale', '(no rationale recorded)')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="etw_provider",
        title=f"{spec['name']} ({spec['guid']})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _chart_family_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    members = spec.get("member_chart_classes") or []
    text = "\n".join(
        [
            f"Chart family: {spec['name']}",
            f"Member chart-class count: {len(members)}",
            f"Total tag hits across corpus: {spec.get('total_hits', 0)}",
            f"Member chart classes: {', '.join(members[:60])}",
            f"Description: {spec.get('description', '')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="chart_family",
        title=f"ChartFamily {spec['name']} ({len(members)} classes)",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


# --- v2 helpers (2026-05-02): role-mapping for binaries; vhost role overlay ---

# Role mapping for the 11 helper binaries observed under
# state/thinkcell_bridge/factory_api_candidates/binaries_v2/. Roles are
# attributed from binary names + observed top_routes/tc_urls/http_libs.
BINARY_ROLE_BY_NAME: dict[str, str] = {
    "ppttc.exe": "ppttc CLI runner (.ppttc → bound deck)",
    "ppttchdl.exe": "ppttc handler companion",
    "tcasr.exe": "tcasr sidecar (named-mutex IPC partner of tcaddin.dll)",
    "tcgmail.exe": "Gmail-integration helper",
    "tcindex.exe": "indexing helper (multi-version /v0..v3 routes)",
    "tcmail.exe": "mail-integration helper",
    "tcnatmsg.exe": "browser-extension native-messaging host",
    "tcperf.exe": "telemetry/performance helper",
    "tcserver.exe": "tcserver REST broker (boost::beast HTTP, /v0..v2 routes)",
    "tctabimp.exe": "table-import helper (Mozilla addons URL touched)",
    "tcupdate.exe": "auto-update client (WinHTTP, update.appcom.think-cell.com)",
}


def _binary_artifact_doc(record: dict[str, Any], role: str, node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Binary artifact: {record.get('name')}",
            f"Role: {role}",
            f"Size bytes: {record.get('size')}",
            f"Route count: {record.get('route_count')}",
            f"Top routes: {', '.join((record.get('top_routes') or [])[:8])}",
            f"think-cell URLs: {', '.join((record.get('tc_urls') or [])[:6])}",
            f"HTTP libs: {', '.join(record.get('http_libs') or [])}",
            f"HTTP signatures: {', '.join((record.get('http_sigs') or [])[:6])}",
            f"Native-messaging marker: {record.get('has_native_messaging')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="binary_artifact",
        title=f"{record.get('name')} ({role})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _embedded_resource_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Embedded resource: {spec.get('label')}",
            f"Parent binary: {spec.get('parent')}",
            f"Resource kind: {spec.get('kind')}",
            f"Detail: {spec.get('detail')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="embedded_resource",
        title=f"{spec.get('label')} (embedded in {spec.get('parent')})",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _ip_cluster_doc(ip: str, hosts: list[str], provider: str, node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"IP cluster: {ip}",
            f"Cloud provider: {provider}",
            f"vhosts on this IP: {', '.join(hosts)}",
            f"Cluster size: {len(hosts)} subdomain(s)",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="ip_cluster",
        title=f"IP cluster {ip} ({provider}, {len(hosts)} vhosts)",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _auth_evidence_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Auth evidence: {spec.get('marker_type')}",
            f"Value: {spec.get('value')}",
            f"Encoding: {spec.get('encoding')}",
            f"Verdict: {spec.get('verdict')}",
            f"Found in: {spec.get('found_in')}",
            f"Source probe: {spec.get('source')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="auth_evidence",
        title=f"AuthEvidence {spec.get('marker_type')} = {spec.get('verdict')}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _schema_layer_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    text = "\n".join(
        [
            f"Schema layer: {spec.get('label')}",
            f"Source: {spec.get('source')}",
            f"Build number: {spec.get('build_number')}",
            f"Element count: {spec.get('element_count')}",
            f"Attribute count: {spec.get('attribute_count')}",
            f"Note: {spec.get('note')}",
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="schema",
        title=f"Schema {spec.get('label')}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


def _documentation_doc(spec: dict[str, Any], node_id: str) -> RagDocument:
    """Build a RAG document for an official-vendor-doc Documentation node."""
    facts_text = "\n".join(
        f"- [{f.get('topic')}] {f.get('fact')} (quote: {f.get('source_quote', '')[:200]})"
        for f in spec.get("key_facts", [])[:20]
    )
    text = "\n".join(
        [
            f"Documentation: {spec.get('filename')}",
            f"Title: {spec.get('title')}",
            "Source type: official-vendor-doc",
            f"Section count: {spec.get('section_count')}",
            f"Word count: {spec.get('word_count')}",
            f"Topic tags: {', '.join(spec.get('topic_tags', []))}",
            f"Open questions resolved: {', '.join(spec.get('open_questions_resolved', []))}",
            "Key facts:",
            facts_text,
        ]
    )
    return RagDocument(
        id=f"doc:{node_id}",
        kind="documentation",
        title=f"think-cell official doc: {spec.get('title')}",
        text=text,
        node_ids=[node_id],
        terms=_tokens(text),
    )


# Per-doc routing → which COMMethod / Mechanism / CloudEndpoint nodes each
# official documentation file describes. Drives DESCRIBES / SCHEMA_FOR /
# DOCUMENTS_ENDPOINT edge creation in build_graph.
DOCUMENTATION_TARGETS = {
    "official-en-jsondataautomation.html": {
        "topic_tags": ["ppttc", "json", "automation", "tcserver", "ppttc.exe"],
        "describes_methods": [],
        "schema_for_mechanism": ["think-cellXML embedded chart format"],
        "describes_endpoints": ["server.think-cell.com", "static.think-cell.com"],
    },
    "official-en-introductionautomation.html": {
        "topic_tags": ["AddRangeData", "AddRangeImage", "naming", "templates"],
        "describes_methods": [],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-exceldataautomation.html": {
        "topic_tags": [
            "PresentationFromTemplate",
            "UpdateBatch",
            "UpdateChart",
            "AddRangeData",
            "AddRangeImage",
        ],
        "describes_methods": [
            "IXlMacroInterface.PresentationFromTemplate",
            "IUpdateBatch.AddRangeData",
            "IUpdateBatch.AddRangeImage",
            "IUpdateBatch.Send",
            "IXlMacroInterface.UpdateChart",
            "IXlMacroInterface.UpdateChartStep3",
            "IXlMacroInterface.UpdateBatchStep3",
            "IXlMacroInterface.PresentationFromTemplateStep3",
        ],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-api.html": {
        "topic_tags": ["API", "VBA", "C#", "tcXlAddIn", "tcUpdate"],
        "describes_methods": [
            "IXlMacroInterface.PresentationFromTemplate",
            "IUpdateBatch.AddRangeData",
            "IXlMacroInterface.UpdateChart",
        ],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-exceldatalinks.html": {
        "topic_tags": ["Excel", "data links", "linked ranges"],
        "describes_methods": [],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-element-datasheets.html": {
        "topic_tags": ["datasheet", "transpose", "optional rows", "100%="],
        "describes_methods": [],
        "schema_for_mechanism": ["think-cellXML embedded chart format"],
        "describes_endpoints": [],
    },
    "official-en-tables-with-datasheets.html": {
        "topic_tags": ["tables", "datasheet", "data-driven"],
        "describes_methods": [],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-table.html": {
        "topic_tags": ["tables"],
        "describes_methods": [],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
    "official-en-import-mekko-graphics.html": {
        "topic_tags": ["Mekko Graphics", "ImportMekkoGraphicsCharts", "GetMekkoGraphicsXML"],
        "describes_methods": [
            "IPpMacroInterface.ImportMekkoGraphicsCharts",
            "IPpMacroInterface.GetMekkoGraphicsXML",
        ],
        "schema_for_mechanism": [],
        "describes_endpoints": [],
    },
}


def _build_official_documentation(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    corpus_node: str,
    lab_node: str,
    com_method_node_by_label: dict[str, str],
    endpoint_node_by_host: dict[str, str],
) -> dict[str, Any]:
    """Build Documentation nodes from the latest official_docs_corpus extraction.

    Returns counter dict so caller can report node + edge deltas.
    """
    counters: dict[str, Any] = {
        "documentation_nodes_added": 0,
        "describes_method_edges": 0,
        "schema_for_mechanism_edges": 0,
        "describes_endpoint_edges": 0,
        "documents_runtime_edges": 0,
        "documents_corpus_edges": 0,
        "extraction_path": None,
    }

    extraction_path = _latest_probe_json("official_docs_corpus", "*/extraction.json")
    if extraction_path is None:
        return counters
    counters["extraction_path"] = str(extraction_path.relative_to(ROOT))

    extraction = _load_json(extraction_path)
    if not extraction or not isinstance(extraction, dict):
        return counters

    # Find a Mechanism node by exact label (we'll use the think-cellXML one).
    mechanism_id_by_label: dict[str, str] = {}
    for nid, node in nodes.items():
        if node.kind == "Mechanism":
            mechanism_id_by_label[node.label] = nid

    for doc_record in extraction.get("docs", []):
        filename = doc_record.get("filename")
        if not filename:
            continue
        target_spec = DOCUMENTATION_TARGETS.get(filename, {})

        spec = {
            "filename": filename,
            "title": doc_record.get("title", filename),
            "section_count": doc_record.get("section_count"),
            "word_count": doc_record.get("word_count"),
            "key_facts": doc_record.get("key_facts", []),
            "topic_tags": target_spec.get("topic_tags", []),
            "open_questions_resolved": doc_record.get("open_questions_resolved", []),
        }

        node_id = _add_node(
            nodes,
            "Documentation",
            filename,
            title=spec["title"],
            source_type="official-vendor-doc",
            source_path=str(extraction_path.relative_to(ROOT)),
            section_count=spec["section_count"],
            word_count=spec["word_count"],
            topic_tags=spec["topic_tags"],
            open_questions_resolved=spec["open_questions_resolved"],
            key_fact_count=len(spec["key_facts"]),
        )
        counters["documentation_nodes_added"] += 1

        # Anchor to the corpus + runtime
        _add_edge(
            edges, corpus_node, "HAS_DOCUMENTATION", node_id, source_type="official-vendor-doc"
        )
        counters["documents_corpus_edges"] += 1
        _add_edge(edges, node_id, "DOCUMENTS_RUNTIME", lab_node)
        counters["documents_runtime_edges"] += 1

        # DESCRIBES → COMMethod
        for method_label in target_spec.get("describes_methods", []):
            method_id = com_method_node_by_label.get(method_label)
            if method_id:
                _add_edge(edges, node_id, "DESCRIBES", method_id, target_kind="COMMethod")
                counters["describes_method_edges"] += 1

        # SCHEMA_FOR → Mechanism
        for mech_label in target_spec.get("schema_for_mechanism", []):
            mech_id = mechanism_id_by_label.get(mech_label)
            if mech_id:
                _add_edge(edges, node_id, "SCHEMA_FOR", mech_id, target_kind="Mechanism")
                counters["schema_for_mechanism_edges"] += 1

        # DESCRIBES → CloudEndpoint
        for host in target_spec.get("describes_endpoints", []):
            endpoint_id = endpoint_node_by_host.get(host)
            if endpoint_id:
                _add_edge(edges, node_id, "DESCRIBES", endpoint_id, target_kind="CloudEndpoint")
                counters["describes_endpoint_edges"] += 1

        docs.append(_documentation_doc(spec, node_id))

    return counters


def _build_binaries_v2(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    lab_node: str,
    endpoint_node_by_host: dict[str, str],
) -> None:
    bin_root = ROOT / "state" / "thinkcell_bridge" / "factory_api_candidates" / "binaries_v2"
    scan_path = bin_root / "binary_strings_scan.json"
    if not scan_path.exists():
        return
    try:
        scan = json.loads(scan_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    if not isinstance(scan, list):
        return
    for record in scan:
        name = record.get("name")
        if not name:
            continue
        role = BINARY_ROLE_BY_NAME.get(name, "helper binary")
        binary_id = _add_node(
            nodes,
            "BinaryArtifact",
            name,
            role=role,
            size=record.get("size"),
            route_count=record.get("route_count"),
            top_routes=record.get("top_routes") or [],
            tc_urls=record.get("tc_urls") or [],
            http_libs=record.get("http_libs") or [],
            http_sigs=(record.get("http_sigs") or [])[:8],
            has_native_messaging=record.get("has_native_messaging", False),
            source_path=str(scan_path.relative_to(ROOT)),
        )
        _add_edge(edges, lab_node, "EXPOSES_INTERFACE", binary_id, role=role)

        # Embed observed think-cell URLs as endpoints when they map to a known
        # CloudEndpoint host. Otherwise just record them as text on the binary.
        for url in record.get("tc_urls") or []:
            try:
                host = url.split("//", 1)[1].split("/", 1)[0]
            except IndexError:
                continue
            target = endpoint_node_by_host.get(host)
            if target is not None:
                _add_edge(edges, binary_id, "USES_ENDPOINT", target, url=url)

        # Embedded resources: top_routes (each is an embedded HTTP route),
        # http_libs (boost::beast / WinHTTP signatures = embedded TLS stack),
        # tc_urls (string-table URL constants), http_sigs (Content-Type values).
        for route in (record.get("top_routes") or [])[:8]:
            label = f"{name}::route::{route}"
            res_id = _add_node(
                nodes,
                "EmbeddedResource",
                label,
                parent_binary=name,
                resource_kind="http_route",
                content_hint=route,
                is_likely_text=True,
            )
            spec = {
                "label": label,
                "parent": name,
                "kind": "http_route",
                "detail": route,
            }
            _add_edge(edges, binary_id, "EMBEDS_RESOURCE", res_id, resource_kind="http_route")
            docs.append(_embedded_resource_doc(spec, res_id))
        for lib in record.get("http_libs") or []:
            label = f"{name}::http_lib::{lib}"
            res_id = _add_node(
                nodes,
                "EmbeddedResource",
                label,
                parent_binary=name,
                resource_kind="http_lib",
                content_hint=lib,
                is_likely_text=True,
            )
            spec = {"label": label, "parent": name, "kind": "http_lib", "detail": lib}
            _add_edge(edges, binary_id, "EMBEDS_RESOURCE", res_id, resource_kind="http_lib")
            docs.append(_embedded_resource_doc(spec, res_id))
        docs.append(_binary_artifact_doc(record, role, binary_id))


def _build_ip_clusters(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    endpoint_node_by_host: dict[str, str],
) -> None:
    """Group CloudEndpoints by shared IP into IPCluster nodes."""
    ip_to_hosts: dict[str, list[str]] = {}
    ip_to_provider: dict[str, str] = {}
    for host, topo in HOSTING_TOPOLOGY.items():
        ip = topo.get("ip")
        if not ip or ip == "99.84.234.x":  # masked CDN address
            continue
        ip_to_hosts.setdefault(ip, []).append(host)
        ip_to_provider[ip] = topo.get("provider") or "unknown"
    for ip, hosts in ip_to_hosts.items():
        provider = ip_to_provider[ip]
        cluster_id = _add_node(
            nodes,
            "IPCluster",
            ip,
            ip=ip,
            provider=provider,
            hosts=sorted(hosts),
            host_count=len(hosts),
        )
        for host in hosts:
            endpoint_id = endpoint_node_by_host.get(host)
            if endpoint_id is None:
                continue
            _add_edge(edges, cluster_id, "HOSTS_ENDPOINT", cluster_id, host=host) if False else None
            _add_edge(edges, cluster_id, "HOSTS_ENDPOINT", endpoint_id, host=host)
            _add_edge(edges, endpoint_id, "RESOLVES_TO", cluster_id, ip=ip)
        docs.append(_ip_cluster_doc(ip, sorted(hosts), provider, cluster_id))


def _build_auth_evidence(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    lab_node: str,
    endpoint_node_by_host: dict[str, str],
) -> None:
    """Emit AuthEvidence nodes from auth_oauth_string_mining and vm_native_auth_verify."""
    # Source 1 — auth_oauth_string_mining/verified_findings.json (per-marker truth bool)
    findings_path = (
        ROOT / "state" / "thinkcell_bridge" / "auth_oauth_string_mining" / "verified_findings.json"
    )
    if findings_path.exists():
        try:
            findings = json.loads(findings_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            findings = {}
        for marker, present in (findings.get("verified_ascii") or {}).items():
            verdict = "verified" if present else "denied"
            spec = {
                "marker_type": marker,
                "value": marker,
                "encoding": "ASCII",
                "verdict": verdict,
                "found_in": "tcaddin.dll string table",
                "source": str(findings_path.relative_to(ROOT)),
            }
            label = f"{marker} ({verdict}, ASCII)"
            ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
            _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict=verdict)
            docs.append(_auth_evidence_doc(spec, ev_id))
        for marker, present in (findings.get("verified_utf16") or {}).items():
            verdict = "verified" if present else "denied"
            spec = {
                "marker_type": marker,
                "value": marker,
                "encoding": "UTF-16LE",
                "verdict": verdict,
                "found_in": "tcaddin.dll string table",
                "source": str(findings_path.relative_to(ROOT)),
            }
            label = f"{marker} ({verdict}, UTF-16LE)"
            ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
            _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict=verdict)
            docs.append(_auth_evidence_doc(spec, ev_id))
            # Bind UTF-16 verified hosts to their CloudEndpoint
            if verdict == "verified" and "thinkcell" in marker:
                target_host = "app.prod.ai.think-cell.com"
                target = endpoint_node_by_host.get(target_host)
                if target is not None:
                    _add_edge(edges, target, "EVIDENCED_BY", ev_id)

    # Source 2 — vm_native_auth_verify/.../vm_native_auth_verify.json (verdict block)
    vm_path = _latest_probe_json("vm_native_auth_verify", "*/vm_native_auth_verify.json")
    if vm_path is not None:
        try:
            vm = json.loads(vm_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            vm = {}
        verdict_block = vm.get("verdict") or {}
        # confirmed_strings → verified, denied_strings → denied
        confirmed = verdict_block.get("confirmed_strings") or []
        denied = verdict_block.get("denied_strings") or []
        utf16_strings = vm.get("utf16_strings_grep") or {}
        for marker in confirmed:
            grep_entry = utf16_strings.get(marker, {})
            in_ascii = grep_entry.get("in_ascii", False)
            in_utf16 = grep_entry.get("in_utf16", False)
            encoding = (
                "UTF-16LE" if in_utf16 and not in_ascii else "ASCII" if in_ascii else "unknown"
            )
            spec = {
                "marker_type": marker,
                "value": grep_entry.get("needle", marker),
                "encoding": encoding,
                "verdict": "verified",
                "found_in": "tcaddin.dll (VM dumpbin + grep)",
                "source": str(vm_path.relative_to(ROOT)),
            }
            label = f"{marker} (verified VM, {encoding})"
            ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
            _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict="verified")
            docs.append(_auth_evidence_doc(spec, ev_id))
        for marker in denied:
            grep_entry = utf16_strings.get(marker, {})
            spec = {
                "marker_type": marker,
                "value": grep_entry.get("needle", marker),
                "encoding": "absent",
                "verdict": "denied",
                "found_in": "tcaddin.dll (not present in ASCII or UTF-16 strings)",
                "source": str(vm_path.relative_to(ROOT)),
            }
            label = f"{marker} (denied VM)"
            ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
            _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict="denied")
            docs.append(_auth_evidence_doc(spec, ev_id))
        # Verdict-level booleans → top-level summary AuthEvidence nodes
        verdict_summaries = [
            ("jwt_likely", "JWT auth scheme"),
            ("canonical_request_likely", "AWS-canonical-request auth scheme"),
            ("bcrypt_definitively_used", "BCrypt API used"),
            ("bcrypt_sha256_likely", "BCrypt SHA256 HMAC"),
            ("bcrypt_hmac_flag", "BCrypt HMAC flag set"),
        ]
        for key, label_text in verdict_summaries:
            if key not in verdict_block:
                continue
            value = bool(verdict_block.get(key))
            verdict = "verified" if value else "denied"
            spec = {
                "marker_type": label_text,
                "value": str(value),
                "encoding": "boolean_verdict",
                "verdict": verdict,
                "found_in": "vm_native_auth_verify verdict block",
                "source": str(vm_path.relative_to(ROOT)),
            }
            label = f"{label_text} = {verdict}"
            ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
            _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict=verdict)
            docs.append(_auth_evidence_doc(spec, ev_id))


def _build_chartxmlclass_bindings(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    chart_class_node_by_name: dict[str, str],
) -> None:
    """Emit OCCURS_IN_CHART edges from chart classes to BuildProof / corpus nodes
    when the chart class appears in any extracted think-cellXML deck.

    2026-05-02: scans BOTH the original `thinkcellxml_corpus` and the extended
    `thinkcellxml_corpus_extended` so the LAND_thinkcell_seed decks (only
    present in the original) and the new chart-template decks (only present
    in the extended) both get ExtractedDeck nodes, which downstream Package.zip
    bundling depends on.
    """
    seen_deck_paths: set[str] = set()
    for subdir in ("thinkcellxml_corpus", "thinkcellxml_corpus_extended"):
        extraction_path = _latest_probe_json(subdir, "*/extraction_index.json")
        if extraction_path is None:
            continue
        try:
            ext = json.loads(extraction_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            continue
        for deck in ext.get("decks", []) or []:
            deck_path_raw = deck.get("deck") or ""
            deck_label = Path(deck_path_raw).name or deck_path_raw
            if not deck_label or deck_path_raw in seen_deck_paths:
                continue
            seen_deck_paths.add(deck_path_raw)
            deck_id = _add_node(
                nodes,
                "ExtractedDeck",
                deck_label,
                full_path=deck_path_raw,
                sha256=deck.get("sha256"),
                tc_tag_count=deck.get("tc_tag_count"),
                thinkcellxml_count=deck.get("thinkcellxml_count"),
                ole_object_count=len(deck.get("ole_objects") or []),
                source_corpus=subdir,
            )
            # Connect every cataloged chart class to this deck (corpus-level
            # bind). Per-chart frequency-in-deck isn't in the index, so we
            # just record the chart_class_count occurrence as bound.
            for class_name, class_id in chart_class_node_by_name.items():
                _add_edge(
                    edges,
                    class_id,
                    "OCCURS_IN_CHART",
                    deck_id,
                    deck=deck_label,
                )


def _build_schema_layers(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    lab_node: str,
) -> None:
    """Emit Schema nodes for embedded vs installed think-cellXML schema layers.
    Source: schema_inventory.json (547 elements in the extended corpus) + per-build
    version-gate distinct_builds list (23 build numbers as of 2026-05-02)."""
    schema_path = _latest_probe_json_in_any(
        ["thinkcellxml_corpus_extended", "thinkcellxml_corpus"],
        "*/schema_inventory.json",
    )
    if schema_path is None:
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    element_count = schema.get("element_count") or 0
    attr_count = schema.get("attribute_count") or 0
    # Single embedded layer summarising the bound-deck corpus.
    embedded_label = "embedded think-cellXML (bound-deck corpus)"
    spec_embedded = {
        "label": embedded_label,
        "source": "embedded",
        "build_number": "corpus-merged",
        "element_count": element_count,
        "attribute_count": attr_count,
        "note": "Aggregate element-tag scan across all bound-deck CFB streams.",
    }
    sid_embedded = _add_node(
        nodes,
        "Schema",
        embedded_label,
        namespace="think-cellXML",
        source="embedded",
        build_number="corpus-merged",
        element_count=element_count,
        attribute_count=attr_count,
    )
    _add_edge(edges, lab_node, "CONTAINS_SCHEMA", sid_embedded, schema_source="embedded")
    docs.append(_schema_layer_doc(spec_embedded, sid_embedded))

    for build in schema.get("version_gate_distinct_builds") or []:
        layer_label = f"version-gated think-cellXML build {build}"
        spec_layer = {
            "label": layer_label,
            "source": "installed",
            "build_number": str(build),
            "element_count": None,
            "attribute_count": None,
            "note": "Build-id seen in version_gate attribute on bound-deck XML.",
        }
        sid_layer = _add_node(
            nodes,
            "Schema",
            layer_label,
            namespace="think-cellXML",
            source="installed",
            build_number=str(build),
        )
        _add_edge(edges, lab_node, "CONTAINS_SCHEMA", sid_layer, schema_source="installed")
        docs.append(_schema_layer_doc(spec_layer, sid_layer))


# ---------------------------------------------------------------------------
# 2026-05-02 builders for new node kinds: Library, ETWProvider, ChartFamily,
# plus augmentation of existing AuthEvidence / CloudEndpoint / BinaryArtifact.
# ---------------------------------------------------------------------------


def _build_libraries(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    com_method_node_by_label: dict[str, str],
    com_interface_node_by_iid: dict[str, str],
    lab_node: str,
) -> dict[str, str]:
    """Emit Library nodes (tcxml + tc_com_driver) and wire WRAPS / READS_FORMAT
    / WRITES_FORMAT edges. Returns map of library-name -> node_id so callers
    can wire additional edges if needed."""
    library_node_by_name: dict[str, str] = {}

    # 1) Ensure a "think-cellXML format" Mechanism node exists so the tcxml
    #    Library can READS_FORMAT/WRITES_FORMAT into the format itself.
    format_mech_id = _add_node(
        nodes,
        "Mechanism",
        "think-cellXML embedded chart format",
        description=(
            "MFC-derived XML grammar serialized into a CFB stream named 'think-cellXML' "
            "inside each ppt/embeddings/oleObject*.bin. Element tags map 1:1 to MFC C++ "
            "class names (CSequenceChart*, CGanttBar, CScatter*, CPieChart*, etc.). "
            "tcxml is the local Python parser; tc_com_driver does NOT touch this format "
            "directly (think-cell COM round-trips it server-side)."
        ),
        public_reference="schema_inventory.json (547 elements / 89 chart classes)",
        defender_signature=None,
    )
    docs.append(
        RagDocument(
            id=f"doc:{format_mech_id}",
            kind="mechanism",
            title="think-cellXML embedded chart format",
            text=(
                "Mechanism: think-cellXML embedded chart format.\n"
                "CFB-wrapped chart XML at ppt/embeddings/oleObject*.bin::think-cellXML. "
                "Reader+writer is libs/tcxml; COM round-trip is libs/tc_com_driver."
            ),
            node_ids=[format_mech_id],
            terms=_tokens("think-cellXML embedded chart format CFB oleObject ppt embeddings tcxml"),
        )
    )
    _add_edge(edges, lab_node, "HOSTS_MECHANISM", format_mech_id)

    for spec in LIBRARIES:
        lib_id = _add_node(
            nodes,
            "Library",
            spec["name"],
            path=spec["path"],
            lang=spec["lang"],
            deps=spec.get("deps") or [],
            public_api=spec.get("public_api") or [],
            status=spec["status"],
            writer_status=spec.get("writer_status"),
            tests_passing=spec.get("tests_passing"),
            platform=spec.get("platform", "any"),
            purpose=spec.get("purpose"),
            wraps_com=bool(spec.get("wraps_com")),
            reads_format=spec.get("reads_format"),
            writes_format=spec.get("writes_format"),
        )
        library_node_by_name[spec["name"]] = lib_id
        # Edge: Runtime --HAS_LIBRARY--> Library (so the lab/runtime is the
        # natural anchor for "what local libraries exist").
        _add_edge(edges, lab_node, "HAS_LIBRARY", lib_id, status=spec["status"])
        docs.append(_library_doc(spec, lib_id))

        # tcxml reads + writes the think-cellXML format Mechanism.
        if spec.get("reads_format") == "think-cellXML":
            _add_edge(edges, lib_id, "READS_FORMAT", format_mech_id, format="think-cellXML")
        if spec.get("writes_format") == "think-cellXML":
            _add_edge(
                edges,
                lib_id,
                "WRITES_FORMAT",
                format_mech_id,
                format="think-cellXML",
                writer_status=spec.get("writer_status"),
            )

        # tc_com_driver wraps the 3 COM interfaces + each of the 25 visible
        # COM methods. Edges keyed off IIDs / "{interface}.{method}" labels
        # already populated by the typeinfo loader earlier in build_graph.
        if spec.get("wraps_com"):
            for iface_name, iid in spec.get("wraps_interfaces") or []:
                target = com_interface_node_by_iid.get(iid.lower())
                if target is not None:
                    _add_edge(
                        edges,
                        lib_id,
                        "WRAPS_INTERFACE",
                        target,
                        iid=iid,
                        interface=iface_name,
                    )
            # WRAPS_METHOD edges: every COMMethod whose interface is one of
            # the wrapped interfaces. Include FHIDDEN _step* variants too —
            # tc_com_driver exposes them as private accessors (per CLAUDE.md).
            wrapped_iface_names = {n for n, _ in spec.get("wraps_interfaces") or []}
            for label, method_id in com_method_node_by_label.items():
                interface = label.split(".", 1)[0]
                if interface in wrapped_iface_names:
                    _add_edge(
                        edges,
                        lib_id,
                        "WRAPS_METHOD",
                        method_id,
                        method_label=label,
                    )

    return library_node_by_name


# ETW provider GUIDs that are most useful to enable for Phase 1/2 capture
# sessions: think-cell-specific traces + the auth/TLS providers most likely
# to fire during the AI-auth handshake. Source DLL hints come from public
# Microsoft docs on each provider name.
ETW_RECOMMENDED_FOR_PHASE12 = {
    "{158204D2-DEAE-4373-9949-2ED01E5C5B27}",  # think-cell indexer
    "{53A5768F-94C6-40CE-911A-DF1B4D4118CB}",  # think-cell server
    "{C7E089AC-BA2A-11E0-9AF7-68384824019B}",  # Microsoft-Windows-Crypto-BCrypt
    "{E8ED09DC-100C-45E2-9FC8-B53399EC1F70}",  # Microsoft-Windows-Crypto-NCrypt
    "{91CC1150-71AA-47E2-AE18-C96E61736B6F}",  # Microsoft-Windows-Schannel-Events
    "{1F678132-5938-4686-9FDC-C8FF68F15C85}",  # Schannel
    "{37D2C3CD-C5D4-4587-8531-4696C44244C8}",  # Security: SChannel
    "{7D44233D-3055-4B9C-BA64-0D47CA40A232}",  # Microsoft-Windows-WinHttp
    "{64DE121B-5F08-5853-AB48-7758F2EA2DD3}",  # Microsoft-Windows-WinHttp-Diagnostics
    "{D071CE03-0D7B-5B27-E817-B9C12961934E}",  # Microsoft-Windows-WinHttp-Pca
    "{DD5EF90A-6398-47A4-AD34-4DCECDEF795F}",  # Microsoft-Windows-HttpService
    "{C42A2738-2333-40A5-A32F-6ACC36449DCC}",  # Microsoft-Windows-HttpLog
    "{7B6BC78C-898B-4170-BBF8-1A469EA43FC5}",  # Microsoft-Windows-HttpEvent
    "{F5344219-87A4-4399-B14A-E59CD118ABB8}",  # Microsoft-Windows-Http-SQM-Provider
    "{41877CB4-11FC-4188-B590-712C143C881D}",  # Microsoft-Windows-Runtime-Web-Http
    "{CC85922F-DB41-11D2-9244-006008269001}",  # Local Security Authority (LSA)
    "{199FE037-2B82-40A9-82AC-E1D46C792B99}",  # LsaSrv
    "{9CC0413E-5717-4AF5-82EB-6103D8707B45}",  # EAP RasTls (TLS-cred enrollment paths)
    "{D710D46C-235D-4798-AC20-9F83E1DCD557}",  # EAP Ttls
}


# ETW provider name -> source DLL / module hint (best-effort, not always
# verifiable from netsh dump alone).
ETW_PROVIDER_DLL_HINTS = {
    "Microsoft-Windows-Crypto-BCrypt": "bcrypt.dll",
    "Microsoft-Windows-Crypto-NCrypt": "ncrypt.dll",
    "Microsoft-Windows-Schannel-Events": "schannel.dll",
    "Schannel": "schannel.dll",
    "Security: SChannel": "schannel.dll",
    "Microsoft-Windows-WinHttp": "winhttp.dll",
    "Microsoft-Windows-WinHttp-Diagnostics": "winhttp.dll",
    "Microsoft-Windows-WinHttp-Pca": "winhttp.dll",
    "Microsoft-Windows-HttpService": "http.sys",
    "Microsoft-Windows-HttpLog": "http.sys",
    "Microsoft-Windows-HttpEvent": "http.sys",
    "Microsoft-Windows-Http-SQM-Provider": "http.sys",
    "Microsoft-Windows-Runtime-Web-Http": "winrt http",
    "Local Security Authority (LSA)": "lsasrv.dll",
    "LsaSrv": "lsasrv.dll",
    "Microsoft-Windows-EapMethods-RasTls": "eapprasts.dll",
    "Microsoft-Windows-EapMethods-Ttls": "eapttls.dll",
    "Microsoft-Office-Events": "Office shared",
    "Microsoft-Office-Word": "Office Word",
    "Microsoft-Office-Word2": "Office Word",
    "Microsoft-Office-Word3": "Office Word",
    "OfficeAirSpace": "Office shared",
    "OfficeLoggingLiblet": "Office shared",
    "RefsWppTrace": "ReFS",
    "think-cell indexer": "tcaddin.dll / tcindex.exe",
    "think-cell server": "tcserver.exe",
}


def _build_etw_providers(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    lab_node: str,
    auth_evidence_node_ids: list[str],
) -> None:
    """Emit ETWProvider nodes from the etw_wmi_inventory probe. Wire RELEVANT_FOR
    edges: think-cell-specific providers --> the runtime; auth-relevant providers
    --> existing AuthEvidence top-level summary nodes."""
    etw_path = _latest_probe_json("etw_wmi_inventory", "*/etw_wmi.json")
    if etw_path is None:
        return
    try:
        etw = json.loads(etw_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    providers_block = etw.get("etw_providers") or {}

    def _emit(provider_dict: dict[str, str], category: str) -> str | None:
        name = provider_dict.get("name")
        guid = provider_dict.get("guid")
        if not name or not guid:
            return None
        is_tc = guid in {
            "{158204D2-DEAE-4373-9949-2ED01E5C5B27}",
            "{53A5768F-94C6-40CE-911A-DF1B4D4118CB}",
        }
        is_auth = category == "auth"
        is_office = category == "office_powerpoint"
        recommended = guid in ETW_RECOMMENDED_FOR_PHASE12
        rationale_bits = []
        if is_tc:
            rationale_bits.append("think-cell-owned ETW channel")
        if is_auth:
            rationale_bits.append(
                "fires on TLS handshake / auth crypto operations during AI-auth flow"
            )
        if is_office:
            rationale_bits.append("Office runtime trace; correlates COM-add-in lifecycle")
        rationale = "; ".join(rationale_bits) or "registered Windows ETW provider"
        spec = {
            "name": name,
            "guid": guid,
            "source_dll": ETW_PROVIDER_DLL_HINTS.get(name),
            "is_thinkcell_specific": is_tc,
            "is_auth_relevant": is_auth,
            "is_office_powerpoint": is_office,
            "recommended_for_phase12": recommended,
            "rationale": rationale,
        }
        provider_id = _add_node(
            nodes,
            "ETWProvider",
            f"{name} {guid}",
            **spec,
        )
        _add_edge(
            edges,
            lab_node,
            "HAS_ETW_PROVIDER",
            provider_id,
            category=category,
            recommended=recommended,
        )
        if is_tc:
            _add_edge(edges, provider_id, "EMITTED_BY_RUNTIME", lab_node)
        if recommended:
            for ev_id in auth_evidence_node_ids:
                _add_edge(
                    edges,
                    provider_id,
                    "RELEVANT_FOR",
                    ev_id,
                    reason="Phase 1/2 capture: surface this provider during auth runtime",
                )
        docs.append(_etw_provider_doc(spec, provider_id))
        return provider_id

    for entry in providers_block.get("auth_relevant", []) or []:
        _emit(entry, "auth")
    for entry in providers_block.get("office_powerpoint", []) or []:
        _emit(entry, "office_powerpoint")
    for entry in providers_block.get("think_cell", []) or []:
        _emit(entry, "think_cell")


def _build_chart_families(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    chart_class_node_by_name: dict[str, str],
    chart_class_frequencies: dict[str, int],
    corpus_node: str,
) -> None:
    """Bucket every ChartClass into a ChartFamily and wire IN_FAMILY edges.
    ChartFamily nodes carry member_chart_classes + total_hits aggregated
    across the bucket."""
    family_members: dict[str, list[str]] = {}
    family_total_hits: dict[str, int] = {}
    for class_name, class_node_id in chart_class_node_by_name.items():
        family = _classify_chart_family(class_name)
        family_members.setdefault(family, []).append(class_name)
        family_total_hits[family] = family_total_hits.get(family, 0) + chart_class_frequencies.get(
            class_name, 0
        )
    family_descriptions = {
        "SequenceChart": (
            "Dominant family. CSequenceChart* covers timeline / column / line / "
            "stacked-bar charts and most multi-series temporal data. Includes "
            "value indicator lines, CAGR, intervals, and series ranges."
        ),
        "Gantt": (
            "Project-timeline charts (CGanttBar, CGanttMilestone, CGanttProcess, "
            "CGanttTable, CGanttRange*, etc.). Used for renewal-timeline visuals."
        ),
        "Pie": ("Pie / donut charts (CPieChartSE / CPieChartData* / CPieChartScalarOutsideLabel)."),
        "Scatter": (
            "Scatter charts (CScatterChartSE / CScatterChartData* / CScatterChartLegend*)."
        ),
        "Bubble": "Bubble-size legends and bubble labels (CBubbleSize*).",
        "Waterfall": "Waterfall connectors (CWaterfallConnector); thin family.",
        "Pentagon": "Pentagon-shape SE + gridline anchors (CPentagonSE, CPentagonGridlineAnchor).",
        "Axis": (
            "Data-axis primitives (CDataAxisGridline / Tickmark / Label / Break) "
            "shared across all chart families."
        ),
        "Gridline": "Gridline primitives (CGridline, CGridlinePair, *GridlineAnchor).",
        "PPTPrimitive": (
            "PowerPoint rendering primitives (CPPTLine, CPPTRectangle, "
            "CPPTPolyline, CPPTGenericLine, CPPTAutoShapeLine, CPPTBreakShape, "
            "CPPTStyledPolyline, CPPTRectangleBase, CPPTGanttScaleBox, "
            "CPPTSequenceChart). The render-side support classes."
        ),
        "Container": "Generic shape containers (CContainerSE, CContainerSEGridlineAnchor).",
        "Rect": "Rect-primitive variants (CRectSE, CRectSEGridlineAnchor, CRectUserSEGridlineAnchor).",
        "Table": "Native think-cell tables (CShapeTable).",
        "SmartGrid": "SmartGrid layout (CSmartGrid; backs the StartTableInsertion lane).",
        "ComPlumbing": "COM IAdviseSink boilerplate (CAdviseSink).",
        "DataBinding": (
            "Variable-source / text-variable binding (CVariableSource, CTextVariable, "
            "CTranslatedStringsSource). The wire format for AddRangeData / .ppttc."
        ),
        "Layout": "Layout helpers (CSLTBSizeCalculator).",
        "Other": "Unclassified ChartClass nodes that don't match any known family pattern.",
    }
    for family, members in sorted(family_members.items()):
        spec = {
            "name": family,
            "member_chart_classes": sorted(members),
            "total_hits": family_total_hits.get(family, 0),
            "description": family_descriptions.get(family, ""),
        }
        family_id = _add_node(
            nodes,
            "ChartFamily",
            family,
            member_chart_classes=sorted(members),
            member_count=len(members),
            total_hits=family_total_hits.get(family, 0),
            description=family_descriptions.get(family, ""),
        )
        _add_edge(edges, corpus_node, "HAS_CHART_FAMILY", family_id, member_count=len(members))
        for member in members:
            class_id = chart_class_node_by_name.get(member)
            if class_id is not None:
                _add_edge(edges, class_id, "IN_FAMILY", family_id, family=family)
        docs.append(_chart_family_doc(spec, family_id))


def _build_dpapi_baseline_evidence(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    lab_node: str,
    endpoint_node_by_host: dict[str, str],
) -> str | None:
    """Emit a single AuthEvidence node summarising the DPAPI-decoded
    aiauthentication.bin token structure (current as of 2026-05-02)."""
    parsed_path = _latest_probe_json("dpapi_baseline", "*/aiauthentication.parsed.json")
    if parsed_path is None:
        return None
    try:
        parsed = json.loads(parsed_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return None
    field_names = parsed.get("field_names") or []
    expires = parsed.get("expires_summary") or {}
    hash_shape = parsed.get("hash_shape") or {}
    valid_hours = expires.get("valid_for_hours")
    hash_len = hash_shape.get("length")
    structure = parsed.get("blob_structure") or "uint32_le_length_prefix + url_encoded_payload"
    spec = {
        "marker_type": "DPAPI token baseline",
        "value": (
            f"structure={structure}; fields={','.join(field_names)}; "
            f"hash_length={hash_len} (16 bytes — MD5 OR truncated SHA256, ambiguous); "
            f"rotation~={valid_hours}h"
        ),
        "encoding": "DPAPI (current-user) -> uint32_le length + url-encoded form payload",
        "verdict": "verified",
        "found_in": "C:\\Users\\<user>\\AppData\\Roaming\\think-cell\\aiauthentication.bin",
        "source": str(parsed_path.relative_to(ROOT)),
    }
    label = f"DPAPI token baseline ({len(field_names)} fields, ~{valid_hours}h rotation)"
    ev_id = _add_node(nodes, "AuthEvidence", label, **spec)
    _add_edge(edges, lab_node, "HAS_AUTH_EVIDENCE", ev_id, verdict="verified")
    target = endpoint_node_by_host.get("aiauthentication.appcom.think-cell.com")
    if target is not None:
        _add_edge(edges, target, "EVIDENCED_BY", ev_id)
    docs.append(_auth_evidence_doc(spec, ev_id))
    return ev_id


def _augment_canto_endpoint(
    nodes: dict[str, Node],
    edges: list[Edge],
    endpoint_node_by_host: dict[str, str],
) -> None:
    """Annotate the Canto stock-image-related findings on whichever endpoint
    we can locate. Findings: oauth.canto.com requires `app_id` (not
    `client_id`), think-cell's app_id value not in binary strings, server-
    proxied flow likely. We attach as properties on the closest existing
    CloudEndpoint (server.think-cell.com is the SSO portal; think-cell
    itself doesn't expose a Canto endpoint to the public probe)."""
    canto_path = _latest_probe_json("canto_oauth_probe", "*/results.json")
    if canto_path is None:
        return
    try:
        canto = json.loads(canto_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    findings = (
        "Canto oauth.canto.com requires `app_id` parameter (not `client_id`); "
        "think-cell's app_id value not present in tcaddin.dll/tcserver.exe string "
        "tables — server-proxied flow likely (think-cell front-end never sees raw "
        "client_id). Probe captured 12 endpoints, all 4xx; no /.well-known endpoint."
    )
    annotated = False
    # Annotate the SSO portal endpoint if present (Canto is one of the
    # direct-API stock providers; think-cell either proxies the flow via
    # the SSO portal or via an undocumented per-tenant endpoint).
    for host in ("server.think-cell.com", "www.server.think-cell.com"):
        target = endpoint_node_by_host.get(host)
        if target is None:
            continue
        node = nodes.get(target)
        if node is None:
            continue
        node.properties["canto_oauth_probe"] = findings
        node.properties["canto_oauth_probe_source"] = str(canto_path.relative_to(ROOT))
        annotated = True
    # Independent of annotating endpoints, also attach the finding to the
    # Canto StockProvider (if present) as a property; Canto is integrated
    # via direct_api per STOCK_PROVIDERS.
    canto_provider_label = "Canto"
    for nid, node in nodes.items():
        if node.kind == "StockProvider" and node.label == canto_provider_label:
            node.properties["oauth_app_id_note"] = findings
            node.properties["oauth_probe_source"] = str(canto_path.relative_to(ROOT))
            annotated = True
            break
    if annotated and canto.get("summary", {}).get("total_probes"):
        # Wire a single edge from the runtime to the SSO endpoint flagged with
        # the canto-probe rationale; this keeps the finding queryable.
        sso_target = endpoint_node_by_host.get("server.think-cell.com")
        runtime_node = next(
            (
                nid
                for nid, node in nodes.items()
                if node.kind == "Runtime"
                and "Parallels Windows think-cell automation runtime" in node.label
            ),
            None,
        )
        if sso_target is not None and runtime_node is not None:
            _add_edge(
                edges,
                runtime_node,
                "PROBES_OAUTH",
                sso_target,
                provider="Canto",
                probe_count=canto.get("summary", {}).get("total_probes"),
                key_finding="app_id_required_not_client_id",
            )


def _build_package_zip_artifacts(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
) -> None:
    """Emit BinaryArtifact nodes for the 24 Package.zip xlsb workbooks decoded
    from CFB streams + CONTAINS edges from each parent ExtractedDeck (matched
    on basename) to the Package.zip BinaryArtifact node. The child Package.zip
    artifacts are never persisted-as-files outside the corpus, so we record
    only one summary BinaryArtifact node per unique deck rather than 24
    individual nodes (to avoid blowing up node count without semantic gain)."""
    pkg_path = _latest_probe_json("package_datasheet_decode", "*/results.json")
    if pkg_path is None:
        return
    try:
        pkg = json.loads(pkg_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return
    details = pkg.get("details") or []
    if not details:
        return
    # Group by parent deck folder so we emit one BinaryArtifact summary per deck.
    by_parent: dict[str, list[dict[str, Any]]] = {}
    for entry in details:
        path = entry.get("path", "")
        # Path format: state/.../by_deck/<DECK_NAME>/ole_NN_Package.zip
        parts = path.split("/")
        try:
            deck_idx = parts.index("by_deck")
            parent = parts[deck_idx + 1]
        except (ValueError, IndexError):
            parent = "unknown"
        by_parent.setdefault(parent, []).append(entry)

    # Locate ExtractedDeck nodes by their basename (which is what the existing
    # builder uses as the label). The ExtractedDeck label is the .pptx filename;
    # the by_deck folder name strips .pptx, so match permissively.
    extracted_deck_by_basename: dict[str, str] = {}
    for nid, node in nodes.items():
        if node.kind != "ExtractedDeck":
            continue
        # Label is e.g. "LAND_thinkcell_seed.pptx" — strip extension.
        label = node.label
        stem = label.rsplit(".", 1)[0]
        extracted_deck_by_basename[stem] = nid

    for parent, entries in sorted(by_parent.items()):
        zip_count = len(entries)
        total_bytes = sum(int(e.get("size_bytes") or 0) for e in entries)
        # Aggregate observation: every sheet across all entries is "Sheet1" of floats.
        all_sheets_are_sheet1 = all((e.get("sheets") or [None])[0] == "Sheet1" for e in entries)
        all_floats = all(
            "float" in (s.get("value_types") or []) and len(s.get("value_types") or []) == 1
            for e in entries
            for s in (e.get("sheet_summaries") or [])
        )
        artifact_label = f"{parent}::Package.zip aggregate (xlsb workbooks)"
        spec_role = (
            f"24-package-zip xlsb workbook bundle decoded from CFB Package streams in "
            f"{parent}; cells are all floats; labels live in the parent think-cellXML "
            f"stream (NOT in these workbooks)."
        )
        bin_id = _add_node(
            nodes,
            "BinaryArtifact",
            artifact_label,
            role=spec_role,
            size=total_bytes,
            zip_count=zip_count,
            decoded_ok=zip_count,
            sheets_all_sheet1=all_sheets_are_sheet1,
            value_types_all_float=all_floats,
            source_path=str(pkg_path.relative_to(ROOT)),
            kind_hint="xlsb_workbook_bundle",
        )
        # Connect parent ExtractedDeck (CFB-wrapped) --CONTAINS--> the Package
        # ZIP aggregate (the xlsb workbooks live inside the deck's CFB streams).
        deck_id = extracted_deck_by_basename.get(parent)
        if deck_id is not None:
            _add_edge(edges, deck_id, "CONTAINS", bin_id, kind="xlsb_workbook_bundle")
        record = {
            "name": artifact_label,
            "size": total_bytes,
            "route_count": None,
            "top_routes": [],
            "tc_urls": [],
            "http_libs": [],
            "http_sigs": [],
            "has_native_messaging": False,
        }
        docs.append(_binary_artifact_doc(record, spec_role, bin_id))


def build_graph(
    period: str,
) -> tuple[dict[str, Node], list[Edge], list[RagDocument], dict[str, Any]]:
    slide_corpus = _load_json(
        ROOT / "state" / "thinkcell_bridge" / "slide_corpus" / "thinkcell_slide_corpus.json"
    )
    quarter_spec = _load_json(
        ROOT
        / "state"
        / "thinkcell_bridge"
        / "quarter_seed_bank"
        / period
        / "quarter_seed_bank_spec.json"
    )
    programmatic_lab_path = _latest_programmatic_lab_json()
    programmatic_lab = _load_json(programmatic_lab_path)

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    docs: list[RagDocument] = []

    corpus_node = _add_node(
        nodes,
        "Corpus",
        f"think-cell slide corpus {slide_corpus['slide_count']} slides",
        template_count=slide_corpus["template_count"],
        slide_count=slide_corpus["slide_count"],
    )
    lab_node = _add_node(
        nodes,
        "Runtime",
        "Parallels Windows think-cell automation runtime",
        status=programmatic_lab.get("status"),
        host=programmatic_lab.get("host"),
        capabilities=(programmatic_lab.get("probe") or {}).get("capabilities", {}),
    )
    _add_edge(edges, corpus_node, "VALIDATED_BY", lab_node)

    for spec in CORPUS_DOCS:
        path = ROOT / spec["path"]
        body = _read_corpus_doc_text(path)
        if not body:
            continue
        doc_id = _add_node(
            nodes,
            "CorpusDoc",
            spec["title"],
            key=spec["key"],
            path=spec["path"],
            manual_urls=spec.get("manual_urls", []),
            summary=spec.get("summary"),
        )
        _add_edge(edges, corpus_node, "HAS_CORPUS_DOC", doc_id, key=spec["key"])
        _add_edge(edges, doc_id, "DOCUMENTS_RUNTIME", lab_node)
        docs.append(_corpus_doc_doc(spec, doc_id, body))

    build_level_nodes: dict[str, str] = {}
    for level in BUILD_LEVELS:
        level_id = _add_node(
            nodes,
            "BuildLevel",
            f"{level['level']} {level['label']}",
            level=level["level"],
            purpose=level["purpose"],
            node_kinds=level["node_kinds"],
            build_action=level["build_action"],
            success_gate=level["success_gate"],
        )
        build_level_nodes[level["level"]] = level_id
        _add_edge(edges, corpus_node, "HAS_BUILD_LEVEL", level_id)
        docs.append(_build_level_doc(level, level_id))

    template_nodes: dict[str, str] = {}
    family_nodes: dict[str, str] = {}
    for summary in slide_corpus["summaries"]:
        family_id = family_nodes.setdefault(
            summary["family"],
            _add_node(nodes, "TemplateFamily", summary["family"]),
        )
        template_id = _add_node(
            nodes,
            "Template",
            summary["template"],
            family=summary["family"],
            slide_count=summary["slide_count"],
            ole_parts=summary["ole_parts"],
            readable_thinkcellxml_parts=summary["readable_thinkcellxml_parts"],
            native_tables=summary["native_tables"],
            chart_refs=summary["chart_refs"],
            use_classes=summary["use_classes"],
            top_slide_numbers=summary["top_slide_numbers"],
        )
        template_nodes[summary["template"]] = template_id
        _add_edge(edges, corpus_node, "HAS_TEMPLATE", template_id)
        _add_edge(edges, family_id, "HAS_TEMPLATE", template_id)
        docs.append(_template_doc(summary, template_id))

    signal_nodes: dict[str, str] = {}
    use_class_nodes: dict[str, str] = {}
    fit_nodes: dict[str, str] = {}
    ole_class_nodes: dict[str, str] = {}

    for slide in slide_corpus["slides"]:
        slide_label = f"{slide['template']}#slide-{slide['slide_number']:03d}"
        slide_id = _add_node(
            nodes,
            "Slide",
            slide_label,
            template=slide["template"],
            family=slide["family"],
            slide_number=slide["slide_number"],
            title=slide["title_guess"],
            use_class=slide["use_class"],
            donor_score=slide["donor_score"],
            simcorp_fit=slide["simcorp_fit"],
            chart_refs=slide["chart_refs"],
            native_tables=slide["native_tables"],
            readable_thinkcellxml=sum(
                1 for ole in slide.get("ole_parts", []) if ole.get("thinkcellxml_readable")
            ),
        )
        _add_edge(
            edges,
            template_nodes[slide["template"]],
            "CONTAINS_SLIDE",
            slide_id,
            slide_number=slide["slide_number"],
        )
        use_class_id = use_class_nodes.setdefault(
            slide["use_class"], _add_node(nodes, "UseClass", slide["use_class"])
        )
        fit_id = fit_nodes.setdefault(
            slide["simcorp_fit"], _add_node(nodes, "SimCorpFit", slide["simcorp_fit"])
        )
        _add_edge(edges, slide_id, "HAS_USE_CLASS", use_class_id)
        _add_edge(edges, slide_id, "HAS_SIMCORP_FIT", fit_id)
        for signal in slide.get("signals", []):
            signal_id = signal_nodes.setdefault(signal, _add_node(nodes, "Signal", signal))
            _add_edge(edges, slide_id, "HAS_SIGNAL", signal_id)
        for klass in sorted(
            {
                klass
                for ole in slide.get("ole_parts", [])
                for klass in ole.get("thinkcell_classes", [])
            }
        )[:40]:
            klass_id = ole_class_nodes.setdefault(klass, _add_node(nodes, "ThinkCellClass", klass))
            _add_edge(edges, slide_id, "HAS_THINKCELL_CLASS", klass_id)
        if slide["donor_score"] >= 80:
            _add_edge(edges, slide_id, "CANDIDATE_FOR", lab_node, reason="high donor score")
        docs.append(_slide_doc(slide, slide_id))

    director_nodes: dict[str, str] = {}
    contract_nodes: dict[str, str] = {}
    lane_nodes: dict[str, str] = {}
    for contract in quarter_spec["contracts"]:
        contract_id = _add_node(
            nodes,
            "QuarterSeedContract",
            contract["name"],
            family=contract["family"],
            thinkcell_template_family=contract["thinkcell_template_family"],
            build_priority=contract["build_priority"],
            supported_lane=contract["supported_lane"],
            fallback=contract["fallback"],
            metric_guardrail=contract["metric_guardrail"],
        )
        contract_nodes[contract["name"]] = contract_id
        docs.append(_contract_doc(contract, contract_id))
        for level_id in build_level_nodes.values():
            _add_edge(edges, contract_id, "REQUIRES_BUILD_LEVEL", level_id)
        lane_id = lane_nodes.setdefault(
            contract["supported_lane"],
            _add_node(nodes, "AutomationLane", contract["supported_lane"]),
        )
        _add_edge(edges, contract_id, "USES_AUTOMATION_LANE", lane_id)
        _add_edge(edges, contract_id, "VALIDATED_BY", lab_node)
        for family, family_id in family_nodes.items():
            if (
                family.lower() in contract["thinkcell_template_family"].lower()
                or contract["family"].lower() in family.lower()
            ):
                _add_edge(edges, contract_id, "USES_TEMPLATE_FAMILY", family_id)
        for director in contract.get("eligible_directors", []):
            director_id = director_nodes.setdefault(
                director, _add_node(nodes, "SalesDirector", director)
            )
            _add_edge(edges, contract_id, "ELIGIBLE_FOR_DIRECTOR", director_id)
        for director in contract.get("fallback_directors", []):
            director_id = director_nodes.setdefault(
                director, _add_node(nodes, "SalesDirector", director)
            )
            _add_edge(
                edges,
                contract_id,
                "FALLBACK_FOR_DIRECTOR",
                director_id,
                fallback=contract["fallback"],
            )
        proof_path = (
            ROOT
            / "state"
            / "thinkcell_bridge"
            / "build_scaffold"
            / period
            / "work"
            / contract["name"]
            / f"{contract['name']}-proof.json"
        )
        if proof_path.exists():
            try:
                proof = json.loads(proof_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                proof = None
            if proof:
                proof_id = _add_node(
                    nodes,
                    "BuildProof",
                    f"{contract['name']} L5 proof {proof.get('status')}",
                    contract=contract["name"],
                    status=proof.get("status"),
                    period=proof.get("period"),
                    director_slug=proof.get("director_slug"),
                    deck=proof.get("deck"),
                    workbook=proof.get("workbook"),
                    render_dir=proof.get("render_dir"),
                    proof_json=str(proof_path.relative_to(ROOT)),
                )
                _add_edge(edges, contract_id, "HAS_BUILD_PROOF", proof_id)
                _add_edge(edges, proof_id, "VALIDATED_BY", lab_node)
                if proof.get("director_slug"):
                    director_id = director_nodes.setdefault(
                        str(proof["director_slug"]).replace("-", " "),
                        _add_node(
                            nodes, "SalesDirector", str(proof["director_slug"]).replace("-", " ")
                        ),
                    )
                    _add_edge(edges, proof_id, "PROVEN_FOR_DIRECTOR", director_id)
                docs.append(_proof_doc(proof, proof_id))

    for row in programmatic_lab.get("salesforce_intel", {}).get("fit_directors", []):
        director_id = director_nodes.setdefault(
            str(row["director"]), _add_node(nodes, "SalesDirector", str(row["director"]))
        )
        _add_node(
            nodes,
            "SalesforceFit",
            f"{row['director']} {period} visual gates",
            territory=row.get("territory"),
            q2_open_arr_count=row.get("q2_open_arr_count"),
            q2_open_arr_eur=row.get("q2_open_arr_eur"),
            q2_open_renewal_count=row.get("q2_open_renewal_count"),
            fy26_open_renewal_count=row.get("fy26_open_renewal_count"),
            chart_gates=row.get("chart_gates", {}),
        )
        fit_id = _node_id("SalesforceFit", f"{row['director']} {period} visual gates")
        _add_edge(edges, director_id, "HAS_SALESFORCE_FIT", fit_id, period=period)

    # ----- Cloud topology + stock providers (constant-driven) -----
    # Hosting-topology fields (ip / provider / tls_issuer) are merged in from
    # HOSTING_TOPOLOGY where known. AI + auth endpoints carry the bespoke-auth
    # note from the 2026-05-02 token-replay null result.
    bespoke_auth_categories = {"ai", "auth"}
    provider_nodes: dict[str, str] = {}
    endpoint_node_by_host: dict[str, str] = {}
    for spec in CLOUD_ENDPOINTS:
        topo = HOSTING_TOPOLOGY.get(spec["host"], {})
        auth_value = spec.get("auth")
        if spec["category"] in bespoke_auth_categories and auth_value not in (None, "n/a", "none"):
            auth_note = AUTH_SCHEME_NOTE
        else:
            auth_note = None
        endpoint_id = _add_node(
            nodes,
            "CloudEndpoint",
            spec["host"],
            category=spec["category"],
            role=spec["role"],
            auth=auth_value,
            auth_replay_note=auth_note,
            hosting_ip=topo.get("ip"),
            hosting_provider=topo.get("provider"),
            tls_issuer=topo.get("tls_issuer"),
        )
        endpoint_node_by_host[spec["host"]] = endpoint_id
        _add_edge(edges, corpus_node, "HAS_CLOUD_ENDPOINT", endpoint_id, category=spec["category"])
        _add_edge(edges, lab_node, "USES_ENDPOINT", endpoint_id, category=spec["category"])
        docs.append(_endpoint_doc(spec, endpoint_id))
        # HostingProvider grouping — one node per cloud cluster, edge from each endpoint.
        prov_label = topo.get("provider")
        if prov_label:
            prov_id = provider_nodes.get(prov_label)
            if prov_id is None:
                prov_id = _add_node(
                    nodes,
                    "HostingProvider",
                    prov_label,
                    representative_ips=[topo["ip"]] if topo.get("ip") else [],
                )
                provider_nodes[prov_label] = prov_id
            _add_edge(
                edges,
                endpoint_id,
                "HOSTED_ON",
                prov_id,
                ip=topo.get("ip"),
                tls_issuer=topo.get("tls_issuer"),
            )

    for spec in STOCK_PROVIDERS:
        provider_id = _add_node(
            nodes,
            "StockProvider",
            spec["name"],
            integration_kind=spec["kind"],
            host=spec.get("host"),
            config_field=spec.get("config_field"),
        )
        _add_edge(
            edges,
            lab_node,
            "INTEGRATES_PROVIDER",
            provider_id,
            integration_kind=spec["kind"],
        )
        if spec.get("host") and spec["host"] in endpoint_node_by_host:
            _add_edge(
                edges,
                provider_id,
                "PROXIED_VIA",
                endpoint_node_by_host[spec["host"]],
            )
        docs.append(_provider_doc(spec, provider_id))

    # ----- Local artifacts (phase0_local_artifacts probe) -----
    phase0_path = _latest_probe_json("phase0_local_artifacts", "*/phase0_local_artifacts.json")
    if phase0_path is not None:
        phase0 = _load_json_lenient(phase0_path) or {}
        for record in phase0.get("files", []):
            if not record.get("exists"):
                continue
            # Phase0 paths are Windows-style (e.g. C:\Users\...); pathlib.Path
            # on macOS treats those as one segment, so basename via rsplit.
            # Use last 3 components so e.g. AppData\\Roaming\\think-cell\\settings.xml
            # and AppData\\Local\\think-cell\\settings.xml don't collide on label.
            raw_path = (record.get("path") or "").replace("/", "\\")
            parts = raw_path.split("\\")
            file_name = parts[-1] if parts else "unknown"
            label = "\\".join(parts[-3:]) if len(parts) >= 3 else file_name
            artifact_id = _add_node(
                nodes,
                "LocalArtifact",
                label,
                path=record.get("path"),
                size=record.get("size"),
                sha256=record.get("sha256"),
                magic_byte_format=record.get("magic_byte_format"),
                last_write_utc=record.get("last_write_utc"),
                is_text=record.get("is_text"),
            )
            _add_edge(edges, lab_node, "HAS_LOCAL_ARTIFACT", artifact_id)
            # Bind aiauthentication.bin to its likely auth endpoint.
            if file_name.lower() == "aiauthentication.bin":
                target = endpoint_node_by_host.get("aiauthentication.appcom.think-cell.com")
                if target:
                    _add_edge(
                        edges,
                        artifact_id,
                        "STORES_TOKEN_FOR",
                        target,
                        encryption="DPAPI (current-user bound)",
                    )
            docs.append(_artifact_doc(record, artifact_id))

    # ----- COM interfaces + methods (typeinfo probe) -----
    typeinfo_path = _latest_probe_json("typeinfo", "*/thinkcell_typeinfo_probe.json")
    com_method_node_by_label: dict[str, str] = {}
    com_interface_node_by_iid: dict[str, str] = {}
    if typeinfo_path is not None:
        typeinfo = _load_json_lenient(typeinfo_path) or {}
        for target in typeinfo.get("targets", []):
            iface_name = target.get("type_name")
            iid = target.get("type_guid")
            if not iface_name:
                continue
            interface_id = _add_node(
                nodes,
                "COMInterface",
                iface_name,
                live_object=target.get("label"),
                iid=iid,
                func_count=target.get("func_count"),
                object_type=target.get("object_type"),
            )
            if iid:
                com_interface_node_by_iid[iid.lower()] = interface_id
            _add_edge(
                edges, lab_node, "EXPOSES_INTERFACE", interface_id, live_object=target.get("label")
            )
            docs.append(_interface_doc(target, interface_id))
            for func in target.get("funcs", []):
                name = func.get("name")
                if not name or name in COM_BOILERPLATE_METHODS:
                    continue
                memid = func.get("memid")
                flags = int(func.get("flags") or 0)
                visibility = "FHIDDEN" if (flags & FUNCFLAG_FHIDDEN) else "normal"
                method_label = f"{iface_name}.{name}"
                method_id = _add_node(
                    nodes,
                    "COMMethod",
                    method_label,
                    interface=iface_name,
                    name=name,
                    dispid=memid,
                    flags_hex=f"0x{flags:x}",
                    visibility=visibility,
                    param_count=func.get("params"),
                    param_names=func.get("param_names") or [],
                )
                com_method_node_by_label[method_label] = method_id
                _add_edge(
                    edges,
                    interface_id,
                    "HAS_METHOD",
                    method_id,
                    visibility=visibility,
                    dispid=memid,
                )
                docs.append(_method_doc(func, iface_name, method_id))

    # ----- Hook engine + virtual ProgIDs (architectural mechanism) -----
    hook_id = _add_node(
        nodes,
        "Mechanism",
        "tcaddin.dll hook engine",
        description=HOOK_ENGINE_DESCRIPTION,
        defender_signature="KB0233 ASR rule deletes tcaddin.dll/tcasr.exe on hook-pattern detection",
        public_reference="McPartlin 2014 Meeting C++ + Theophil 2024 ARM",
    )
    _add_edge(edges, lab_node, "HOSTS_MECHANISM", hook_id)
    docs.append(_hook_engine_doc(hook_id))

    for spec in VIRTUAL_PROGIDS:
        progid_id = _add_node(
            nodes,
            "VirtualProgID",
            spec["progid"],
            role=spec["role"],
            registered_in_hkcr=spec["registered"],
            evidence=spec["evidence"],
        )
        _add_edge(edges, progid_id, "RESOLVED_BY", hook_id)
        _add_edge(edges, lab_node, "EMBEDS_VIRTUAL_PROGID", progid_id)
        docs.append(_virtual_progid_doc(spec, progid_id))

    # ----- Chart-anatomy classes (think-cellXML corpus extraction) -----
    # Use top_30 (frequency-ranked) for the high-occurrence classes, then
    # supplement with the long-tail ChartClasses surfaced by all_elements_sorted
    # (frequency unknown; flagged as long_tail). The long-tail is where the
    # specialized features live: CSequenceChartValueIndicatorLine (threshold
    # lines), CXlImageExternalLink (AddRangeImage persistence), CWaterfallConnector,
    # etc. Worth keeping in the graph for queryability.
    # 2026-05-02: prefer the *extended* corpus (89 chart classes, 547 elements,
    # 23 distinct build versions) over the original 40-class corpus when both
    # exist. _latest_probe_json_in_any picks the newest by mtime across both.
    schema_path = _latest_probe_json_in_any(
        ["thinkcellxml_corpus_extended", "thinkcellxml_corpus"],
        "*/schema_inventory.json",
    )
    chart_class_node_by_name: dict[str, str] = {}
    chart_class_frequencies: dict[str, int] = {}
    if schema_path is not None:
        schema = _load_json_lenient(schema_path) or {}
        chart_classes_top = schema.get("chart_classes_top_30") or []
        all_elements = schema.get("all_elements_sorted") or []
        top_names: set[str] = set()
        # Top-30 entries with frequency
        for entry in chart_classes_top:
            if not isinstance(entry, list) or len(entry) < 2:
                continue
            name, freq = entry[0], int(entry[1])
            top_names.add(name)
            class_id = _add_node(
                nodes,
                "ChartClass",
                name,
                frequency=freq,
                rank="top_30",
                source="think-cellXML element-tag extraction across bound-deck CFB streams",
            )
            chart_class_node_by_name[name] = class_id
            chart_class_frequencies[name] = freq
            _add_edge(edges, corpus_node, "HAS_CHART_CLASS", class_id, frequency=freq)
            docs.append(_chart_class_doc(name, freq, class_id))
        # Long-tail: any C-prefixed element name not already in top_30, excluding
        # CDATA which is XML-spec, not a class name.
        for elem in all_elements:
            if not (elem.startswith("C") and not elem.startswith("CDATA")):
                continue
            if elem in top_names:
                continue
            class_id = _add_node(
                nodes,
                "ChartClass",
                elem,
                frequency=None,
                rank="long_tail",
                source="think-cellXML element-tag extraction across bound-deck CFB streams (long-tail; frequency below top_30 threshold)",
            )
            chart_class_node_by_name[elem] = class_id
            chart_class_frequencies[elem] = 0
            _add_edge(edges, corpus_node, "HAS_CHART_CLASS", class_id, rank="long_tail")
            docs.append(_chart_class_doc(elem, 0, class_id))
        # Attach corpus-level inventory stats to the runtime as a single property bag.
        if schema:
            inv_id = _add_node(
                nodes,
                "SchemaInventory",
                f"think-cellXML schema inventory ({schema.get('element_count', 0)} elements)",
                element_count=schema.get("element_count"),
                attribute_count=schema.get("attribute_count"),
                chart_class_count=schema.get("chart_class_count"),
                member_prefix_count=schema.get("member_prefix_count"),
                version_gate_count=schema.get("version_gate_count"),
                version_gate_distinct_builds=schema.get("version_gate_distinct_builds"),
            )
            _add_edge(edges, corpus_node, "HAS_SCHEMA_INVENTORY", inv_id)
            _add_edge(edges, lab_node, "VALIDATED_BY", inv_id)

    # ----- v2 additions (2026-05-02): BinaryArtifact, EmbeddedResource, Schema,
    # IPCluster, AuthEvidence, ChartXMLClass<-->BuildProof, plus their edges.
    # All sourced strictly from JSON probes — never invented.
    _build_binaries_v2(nodes, edges, docs, lab_node, endpoint_node_by_host)
    _build_ip_clusters(nodes, edges, docs, endpoint_node_by_host)
    _build_auth_evidence(nodes, edges, docs, lab_node, endpoint_node_by_host)
    _build_chartxmlclass_bindings(nodes, edges, docs, chart_class_node_by_name)
    _build_schema_layers(nodes, edges, docs, lab_node)

    # ----- v3 additions (2026-05-02 evening): Library, ETWProvider, ChartFamily,
    # plus DPAPI baseline AuthEvidence, Canto-OAuth CloudEndpoint augmentation,
    # and Package.zip xlsb bundle BinaryArtifacts.
    _build_libraries(
        nodes,
        edges,
        docs,
        com_method_node_by_label,
        com_interface_node_by_iid,
        lab_node,
    )
    dpapi_baseline_ev_id = _build_dpapi_baseline_evidence(
        nodes, edges, docs, lab_node, endpoint_node_by_host
    )
    auth_ev_anchor_ids: list[str] = []
    # Anchor ETW providers to the DPAPI baseline (top of the auth chain) plus
    # any AuthEvidence node whose marker hints at a verdict-summary (jwt/bcrypt
    # boolean nodes from _build_auth_evidence).
    if dpapi_baseline_ev_id:
        auth_ev_anchor_ids.append(dpapi_baseline_ev_id)
    for nid, node in nodes.items():
        if node.kind != "AuthEvidence":
            continue
        marker = (node.properties or {}).get("marker_type") or ""
        if any(
            tok in marker
            for tok in (
                "BCrypt",
                "JWT",
                "AWS-canonical-request",
                "DPAPI",
            )
        ):
            if nid not in auth_ev_anchor_ids:
                auth_ev_anchor_ids.append(nid)
    _build_etw_providers(nodes, edges, docs, lab_node, auth_ev_anchor_ids)
    _augment_canto_endpoint(nodes, edges, endpoint_node_by_host)
    _build_package_zip_artifacts(nodes, edges, docs)
    _build_chart_families(
        nodes,
        edges,
        docs,
        chart_class_node_by_name,
        chart_class_frequencies,
        corpus_node,
    )
    documentation_counters = _build_official_documentation(
        nodes,
        edges,
        docs,
        corpus_node,
        lab_node,
        com_method_node_by_label,
        endpoint_node_by_host,
    )

    etw_path = _latest_probe_json("etw_wmi_inventory", "*/etw_wmi.json")
    extended_corpus_schema_path = _latest_probe_json(
        "thinkcellxml_corpus_extended", "*/schema_inventory.json"
    )
    dpapi_path = _latest_probe_json("dpapi_baseline", "*/aiauthentication.parsed.json")
    canto_path = _latest_probe_json("canto_oauth_probe", "*/results.json")
    package_zip_path = _latest_probe_json("package_datasheet_decode", "*/results.json")
    manifest = {
        "schema": "thinkcell-knowledge-graph/v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "period": period,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "document_count": len(docs),
        "inputs": {
            "slide_corpus": "state/thinkcell_bridge/slide_corpus/thinkcell_slide_corpus.json",
            "quarter_seed_spec": f"state/thinkcell_bridge/quarter_seed_bank/{period}/quarter_seed_bank_spec.json",
            "programmatic_lab": str(programmatic_lab_path.relative_to(ROOT)),
            "typeinfo_probe": (
                str(typeinfo_path.relative_to(ROOT)) if typeinfo_path is not None else None
            ),
            "phase0_local_artifacts": (
                str(phase0_path.relative_to(ROOT)) if phase0_path is not None else None
            ),
            "cloud_endpoints_constant": "scripts/build_thinkcell_knowledge_graph.py:CLOUD_ENDPOINTS",
            "stock_providers_constant": "scripts/build_thinkcell_knowledge_graph.py:STOCK_PROVIDERS",
            "libraries_constant": "scripts/build_thinkcell_knowledge_graph.py:LIBRARIES",
            "etw_wmi_inventory": (
                str(etw_path.relative_to(ROOT)) if etw_path is not None else None
            ),
            "thinkcellxml_corpus_extended_schema": (
                str(extended_corpus_schema_path.relative_to(ROOT))
                if extended_corpus_schema_path is not None
                else None
            ),
            "dpapi_baseline": (
                str(dpapi_path.relative_to(ROOT)) if dpapi_path is not None else None
            ),
            "canto_oauth_probe": (
                str(canto_path.relative_to(ROOT)) if canto_path is not None else None
            ),
            "package_datasheet_decode": (
                str(package_zip_path.relative_to(ROOT)) if package_zip_path is not None else None
            ),
        },
        "extension_2026_05_02": {
            "added_node_kinds": ["Library", "ETWProvider", "ChartFamily"],
            "added_edge_relations": [
                "HAS_LIBRARY",
                "WRAPS_INTERFACE",
                "WRAPS_METHOD",
                "READS_FORMAT",
                "WRITES_FORMAT",
                "HAS_ETW_PROVIDER",
                "EMITTED_BY_RUNTIME",
                "RELEVANT_FOR",
                "HAS_CHART_FAMILY",
                "IN_FAMILY",
                "PROBES_OAUTH",
                "CONTAINS",
            ],
            "augmented_node_kinds": ["AuthEvidence", "CloudEndpoint", "BinaryArtifact"],
            "summary": (
                "Added Library nodes for tcxml + tc_com_driver wired to existing "
                "COMInterface/COMMethod nodes via WRAPS_INTERFACE/WRAPS_METHOD "
                "and to a new think-cellXML format Mechanism via READS_FORMAT/"
                "WRITES_FORMAT. Added ETWProvider nodes from etw_wmi_inventory "
                "(2 think-cell-specific + 17 auth-relevant + Office/PowerPoint), "
                "with RELEVANT_FOR edges to AuthEvidence anchors. Added "
                "ChartFamily nodes bucketing the 89-class extended corpus "
                "(SequenceChart, Gantt, Pie, Scatter, Bubble, Waterfall, "
                "Pentagon, Axis, PPTPrimitive, etc.) with IN_FAMILY edges. "
                "Augmented existing AuthEvidence with the DPAPI baseline "
                "(uint32_le length + url-encoded form, 5 fields, 16-byte hash, "
                "~12h rotation), augmented CloudEndpoint with the Canto OAuth "
                "app_id finding, and added BinaryArtifact aggregates for the "
                "24 Package.zip xlsb workbook bundles (CONTAINS edge from "
                "parent ExtractedDeck)."
            ),
        },
        "extension_official_docs_2026_05_02": {
            "added_node_kinds": ["Documentation"],
            "added_edge_relations": [
                "HAS_DOCUMENTATION",
                "DOCUMENTS_RUNTIME",
                "DESCRIBES",
                "SCHEMA_FOR",
            ],
            "counters": documentation_counters,
            "summary": (
                "Ingested 9 official think-cell HTML documentation files "
                "(JSON automation, Excel automation, API reference, element "
                "datasheets, tables, Mekko import, etc.) extracted under "
                "state/thinkcell_bridge/official_docs_corpus/<ts>/extraction.json. "
                "Each HTML file is one Documentation node (source_type="
                "official-vendor-doc) with topic_tags + key-fact count. "
                "Wired Documentation --DESCRIBES--> COMMethod for "
                "PresentationFromTemplate / UpdateBatch / UpdateChart / "
                "AddRangeData / AddRangeImage / Mekko methods, "
                "Documentation --SCHEMA_FOR--> Mechanism (think-cellXML format) "
                "for the JSON + element-datasheets docs, and "
                "Documentation --DESCRIBES--> CloudEndpoint for tcserver-related "
                "endpoints. Answers open questions A (.ppttc schema), "
                "B (named ranges vs AddRangeData Name), C (Presentations.Open "
                "behavior), D (UpdateChart vs UpdateBatch vs PresentationFromTemplate), "
                "E (element naming convention)."
            ),
        },
        "entrypoints": {
            "query_cli": "scripts/query_thinkcell_knowledge_graph.py",
            "nodes_jsonl": "state/thinkcell_bridge/knowledge_graph/thinkcell_kg_nodes.jsonl",
            "edges_jsonl": "state/thinkcell_bridge/knowledge_graph/thinkcell_kg_edges.jsonl",
            "rag_index": "state/thinkcell_bridge/knowledge_graph/thinkcell_graph_rag_index.json",
        },
    }
    return nodes, edges, docs, manifest


def write_outputs(
    nodes: dict[str, Node],
    edges: list[Edge],
    docs: list[RagDocument],
    manifest: dict[str, Any],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    nodes_path = out_dir / "thinkcell_kg_nodes.jsonl"
    edges_path = out_dir / "thinkcell_kg_edges.jsonl"
    rag_path = out_dir / "thinkcell_graph_rag_index.json"
    manifest_path = out_dir / "thinkcell_kg_manifest.json"
    md_path = out_dir / "thinkcell_kg.md"

    with nodes_path.open("w", encoding="utf-8") as handle:
        for node in sorted(nodes.values(), key=lambda item: (item.kind, item.label)):
            handle.write(json.dumps(asdict(node), sort_keys=True) + "\n")
    with edges_path.open("w", encoding="utf-8") as handle:
        for edge in edges:
            handle.write(json.dumps(asdict(edge), sort_keys=True) + "\n")
    rag_path.write_text(
        json.dumps(
            {"schema": "thinkcell-graph-rag-index/v1", "documents": [asdict(doc) for doc in docs]},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_markdown(manifest, nodes, edges, md_path)


def write_markdown(
    manifest: dict[str, Any], nodes: dict[str, Node], edges: list[Edge], path: Path
) -> None:
    counts: dict[str, int] = {}
    for node in nodes.values():
        counts[node.kind] = counts.get(node.kind, 0) + 1
    relation_counts: dict[str, int] = {}
    for edge in edges:
        relation_counts[edge.relation] = relation_counts.get(edge.relation, 0) + 1

    lines = [
        "# think-cell Knowledge Graph",
        "",
        f"- Nodes: `{manifest['node_count']}`",
        f"- Edges: `{manifest['edge_count']}`",
        f"- RAG documents: `{manifest['document_count']}`",
        "",
        "## Node Kinds",
        "",
        "| Kind | Count |",
        "|---|---:|",
    ]
    for kind, count in sorted(counts.items()):
        lines.append(f"| {kind} | {count} |")
    lines.extend(["", "## Edge Relations", "", "| Relation | Count |", "|---|---:|"])
    for relation, count in sorted(relation_counts.items()):
        lines.append(f"| {relation} | {count} |")
    lines.extend(
        [
            "",
            "## Example Queries",
            "",
            "```bash",
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "scatter fallback Patrick"',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "FY26 renewal timeline donor slides"',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "Commercial Approval table image contract"',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "which slides are native bar column donors"',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "L4 named seed contract"',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "forecast mix bar donor" --kind slide',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR01 L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR03 L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR04 scatter L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR05 FY26 renewal Gantt L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR06 Q2 renewal Gantt Sarah L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR07 Mekko stage industry L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR08 L5 proof waterfall" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR09 L5 proof geography" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR10 L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR11 L5 proof" --kind build_proof',
            '.venv/bin/python scripts/query_thinkcell_knowledge_graph.py "QTR12 hybrid L5 proof stale pipeline" --kind build_proof',
            "```",
            "",
            "## Future-Session Contract",
            "",
            "- Start with the query CLI before rereading the full corpus.",
            "- Prefer quarter seed contracts for SimCorp use-case decisions.",
            "- Prefer slide corpus nodes for donor/reference selection.",
            "- Keep Salesforce gates attached to director-specific chart choices.",
            "- Use build levels when moving from retrieval to construction:",
            "  L0 runtime, L1 Salesforce fit, L2 family, L3 donor slide, L4 named seed, L5 binding proof.",
            "- Use build proof nodes to find completed L5 evidence before rerunning expensive VM/render work.",
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", default=DEFAULT_PERIOD)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    nodes, edges, docs, manifest = build_graph(args.period)
    write_outputs(nodes, edges, docs, manifest, args.output_dir)
    print(
        f"nodes={manifest['node_count']} edges={manifest['edge_count']} docs={manifest['document_count']}"
    )
    print(f"manifest={args.output_dir / 'thinkcell_kg_manifest.json'}")
    print(f"query_index={args.output_dir / 'thinkcell_graph_rag_index.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
