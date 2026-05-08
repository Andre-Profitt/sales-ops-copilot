# Agent 3 — think-cell talks, engineering blog & LinkedIn corpus

**Date:** 2026-05-01
**Scope:** Conference talks, dev blog, public LinkedIn signals, WG21 standards papers
**Method:** WebSearch + WebFetch only. All cited URLs verified live during this run.

---

## 1. Talk catalog (verified think-cell engineer talks)

| #   | Title                                                                         | Speaker                           | Year                                                                | Conference / Venue                                                                                      | URL                                                                                                                             | Architectural disclosure (1-line)                                                                                                                                                                                         |
| --- | ----------------------------------------------------------------------------- | --------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Industrial Strength Software Hacking                                          | Simon McPartlin                   | 2014                                                                | Meeting C++ 2014, Berlin (workshop day)                                                                 | think-cell.com/en/career/events/2014-12-04, PDF: think-cell_talk_softwarehacking.pdf                                            | Case study: PowerPoint COM. Five slides on a "function detouring framework"; six slides on signature-based "finding the target function." This is the closest think-cell has come to publishing its hooking architecture. |
| 2   | Developing a Simple PowerPoint Add-in, How Hard Can It Be?                    | Valentin Ziegler                  | 2019                                                                | C++ Russia 2019, Moscow                                                                                 | think-cell.com/en/career/events/2019-04-19                                                                                      | Frames the entire PowerPoint integration problem; pairs with the "1M LoC C++" claim. Followed up by a full-length range talk same conference.                                                                             |
| 3   | Windows, macOS and the Web: Lessons from Cross-Platform Development           | Sebastian Theophil                | 2021 / 2022                                                         | CppNow 2021, ACCU 2021, C++ on Sea 2022, Core C++ 2022                                                  | youtube.com/watch?v=Cmud1jO\_\_VA, youtube.com/watch?v=lXNr276_fJA, youtube.com/watch?v=G9P9LbJuxU0, accu.org PDF               | "Add-in, dynamically loaded — not in control of the main application (nor the computer itself)." Names render targets: NSView, CALayer, HWND, DirectX texture. Both DirectX and OpenGL/Metal supported.                   |
| 4   | Typescripten — Generating Type-Safe JavaScript Bindings for Emscripten        | Sebastian Theophil                | 2021                                                                | CppCon 2021 (online)                                                                                    | think-cell.com/en/career/events/2021-10-27                                                                                      | Confirms a WebAssembly port path exists; >7000 JS libraries wrapped via TypeScript-to-C++ binding generator.                                                                                                              |
| 5   | The C++ Rvalue Lifetime Disaster                                              | Arno Schödl                       | ~2018-2023 (multiple venues, incl. C++ Russia, using std::cpp 2023) | think-cell.com/en/career/talks/rvalue, youtube.com/watch?v=Tz5drzXREW0, youtube.com/watch?v=zzkpTbJiFPM | "Hard-to-find memory corruption in our code because of these problems." Real-world bug evidence inside the production codebase. |
| 6   | Better C++ Ranges / Why Iterators Got It All Wrong / From Iterators to Ranges | Arno Schödl                       | multi-year                                                          | think-cell talks page                                                                                   | think-cell.com/en/career/talks/overview                                                                                         | Reveals the proprietary `tc::` range library — the architectural backbone of "1M LoC C++" — predates std::ranges by ~15 years and uses internal iteration.                                                                |
| 7   | Range-Based Text Formatting                                                   | Valentin Ziegler / Arno Schödl    | 2019                                                                | C++ Russia 2019                                                                                         | think-cell.com/en/career/events/2019-04-19                                                                                      | Internal-iteration ranges for text layout; relevant because chart label rendering is downstream of the same library.                                                                                                      |
| 8   | Nobody Can Program Correctly: 20 Years of Debugging C++                       | Sebastian Theophil                | 2023                                                                | C++ on Sea 2023 + others                                                                                | think-cell_talk_debugging.pdf                                                                                                   | War stories from production debugging; mentions client bug reports flowing back to the team. Implies binary symbol/stacktrace pipeline.                                                                                   |
| 9   | Reusable Code, Reusable Data Structures                                       | Sebastian Theophil                | 2024                                                                | CppCon 2024, C++ on Sea 2024                                                                            | think-cell.com/en/career/events/2024-09-15                                                                                      | Templates / variants / inheritance / type erasure — survey of patterns across the 1M LoC codebase.                                                                                                                        |
| 10  | Passive ARM Assembly Skills for Debugging, Optimization (and Hacking)         | Sebastian Theophil                | 2024-11-21                                                          | C++ Meetup Stockholm (SwedenCpp)                                                                        | think-cell.com/en/career/events/2024-11-21, youtube.com/watch?v=uyIEg0HkWrQ, PDF: think-cell_talk_arm.pdf                       | "(and Hacking)" subtitle is a tell — same engineer, same hooking lineage as McPartlin 2014, now updated for ARM (Apple Silicon Office).                                                                                   |
| 11  | To Err is Human: Robust Error Handling in C++26                               | Sebastian Theophil                | 2025-09-17                                                          | CppCon 2025, Berlin C++ Meetup 2025-09-30                                                               | think-cell.com/en/career/events/2025-09-30                                                                                      | std::expected / std::stacktrace / contracts. Stacktrace adoption hints at production crash-reporting pipeline.                                                                                                            |
| 12  | Cache-Friendly C++                                                            | Jonathan Müller                   | 2025-09-16                                                          | CppCon 2025                                                                                             | think-cell.com/en/career/events/2024-09-15 (also 2025)                                                                          | Data-oriented design; relevant to chart-data containers but not Office-specific.                                                                                                                                          |
| 13  | Functional Programming in C++                                                 | Jonathan Müller                   | 2025-11-05                                                          | Berlin C++ Meetup                                                                                       | think-cell career talks                                                                                                         | Library-design content; not Office-specific.                                                                                                                                                                              |
| 14  | A Deep Dive Into Dispatching Techniques                                       | Jonathan Müller                   | various                                                             | think-cell talks page                                                                                   | think-cell career talks                                                                                                         | Switch / jump table / vtable codegen analysis — relevant to add-in command dispatch but generic.                                                                                                                          |
| 15  | Express Your Expectations: A Fast, Compliant JSON Pull Parser                 | Jonathan Müller                   | various                                                             | think-cell talks page                                                                                   | think-cell career talks                                                                                                         | Confirms internal JSON parser exists; possible hint about how chart data round-trips to/from the customer portal (also written in C++).                                                                                   |
| 16  | C++ Memory Model                                                              | Valentin Ziegler & Fabio Fracassi | various                                                             | think-cell talks page                                                                                   | think-cell career talks                                                                                                         | Threading model; multi-process Office hosts mean shared-memory and message-passing matter.                                                                                                                                |
| 17  | CppCast Interview                                                             | Arno Schödl                       | 2018-01-24                                                          | CppCast podcast                                                                                         | cppcast.com/arno-schodl/                                                                                                        | Founder narrative of think-cell's C++ posture and ISO involvement.                                                                                                                                                        |
| 18  | CyberDay at RWTH Aachen                                                       | Valentin Ziegler & Volker Schöch  | 2016-06-27                                                          | RWTH Aachen                                                                                             | think-cell.com/en/career/events/2016-06-27                                                                                      | University recruiting talk; "in-depth insights into daily business and programming challenges" — generic.                                                                                                                 |
| 19  | C++ vs. Java                                                                  | Valentin Ziegler & Fabio Fracassi | various                                                             | think-cell talks page                                                                                   | think-cell career talks                                                                                                         | Generic comparison; not Office-specific.                                                                                                                                                                                  |
| 20  | Classes C++23 Style                                                           | Sebastian Theophil                | various                                                             | think-cell talks page                                                                                   | think-cell career talks                                                                                                         | C++23 feature survey; generic.                                                                                                                                                                                            |
| 21  | Recruiting Q&A video                                                          | Arno Schödl + Volker Schöch       | various                                                             | think-cell career page                                                                                  | think-cell.com/en/career/dev                                                                                                    | Volker Schöch ("Senior Software Developer") confirmed on tape; primary public-facing role is hiring outreach.                                                                                                             |

**Scientific publications (think-cell-authored, peer-reviewed):**

| Title                                                  | Authors                          | Year | Venue               |
| ------------------------------------------------------ | -------------------------------- | ---- | ------------------- |
| An Efficient Algorithm for Scatter Chart Labeling      | Sebastian Theophil & Arno Schödl | 2006 | AAAI 2006           |
| A Smart Algorithm for Column Chart Labeling            | Sebastian Müller & Arno Schödl   | 2005 | Smart Graphics 2005 |
| Graphcut Textures (pre-think-cell)                     | Schödl et al.                    | 2003 | SIGGRAPH 2003       |
| Controlled Animation of Video Sprites (pre-think-cell) | Schödl & Essa                    | 2002 | SCA 2002            |
| Video Textures (pre-think-cell)                        | Schödl et al.                    | 2000 | SIGGRAPH 2000       |

The two chart-labeling papers are the only published artifacts that describe **algorithms that ship inside tcaddin.dll** as production code.

---

## 2. Top 5 most-revealing talks — quoted passages and architectural impact

### #1. Simon McPartlin — "Industrial Strength Software Hacking" (Meeting C++ 2014)

This is the single most important think-cell talk for understanding tcaddin.dll's hidden API surface. The PDF outline (the binary-stream extraction recovered the slide titles even though the body text is zlib-compressed) reveals the structure verbatim:

- Slides 1–2: title + workshop outline
- Slide 3: **"Case study: Interacting with PowerPoint"**
- Slide 5: **"Case study: Interacting with PowerPoint"** (continued)
- Slides 9–12, repeated through 13–15: **"Finding the target function"** (six slide-cuts on this single problem)
- Slides 14–18, repeated through 17–21: **"Function detouring framework"** (five slide-cuts)
- Slide 19: workshop outline (recap)
- Slide 20: `hr@think-cell.com`

The think-cell career page restates the same content prose-form: "patching software where the source code is unavailable… the design and implementation of robust patches… tools and techniques that can be used to find suitable patching locations." Combined with the public career page's claim ("we have probably the best function-hooking engine out there… each time our software starts, we patch the Microsoft Office executables in memory… rather than hard-coding patch addresses, we search for small chunks of assembly code"), the 2014 talk is the **public reference implementation description** of how tcaddin.dll modifies the running Office process.

### #2. Sebastian Theophil — "Windows, macOS and the Web: Lessons from Cross-Platform Development" (CppNow 2021 / C++ on Sea 2022 / Core C++ 2022)

The talk's slide deck on think-cell.com states:

> "**Add-in, dynamically loaded — we are not in control of the main application (nor the computer itself!)**"

> "Lightweight abstractions for OS objects… render into application-supplied objects: **NSView, CALayer, HWND, DirectX texture**. Support both DirectX and OpenGL / Metal. Share the main message loop. Support platform-specific features like the host application."

> "12 years of Windows-only development… ~700,000 lines of C++ (later ~1,000,000 LoC)… many unintentional platform dependencies."

This is the only public source that names the rendering surfaces tcaddin.dll plugs into on each platform. It also names "share the main message loop" — meaning chart interaction runs on PowerPoint's UI thread, not a separate one — which constrains anything an automation surface can do without re-entering Office.

### #3. Sebastian Theophil — "Passive ARM Assembly Skills for Debugging, Optimization (and Hacking)" (SwedenCpp 2024-11-21)

The "(and Hacking)" subtitle is editorial; it carries on the McPartlin-2014 lineage. The Stockholm event page describes it as "a practical introduction to ARM assembly, focusing on essential skills for debugging and optimizing applications on ARM machines, especially for those with x86 assembly experience." Critical context: Microsoft Office on Apple Silicon and Office on Windows-on-ARM are AArch64. think-cell's signature-scanning hook engine has to recognize ARM64 instruction sequences, not just x86. This talk is the public-facing signal that the hooking engine has been **ported to AArch64**, not just the rendering layer. Engineers porting an x86 detour engine to ARM is not a generic "passive" exercise.

### #4. Arno Schödl — "The C++ Rvalue Lifetime Disaster" (multiple venues)

Direct quote from the slide-deck abstract on think-cell.com:

> "These problems are not merely theoretical — **think-cell has had hard-to-find memory corruption in their code because of these problems**."

This is a rare admission that production tcaddin.dll has experienced memory corruption tied to rvalue/lvalue confusion. Combined with #6 below, it tells you the codebase relies heavily on a custom range library where temporaries flow through pipelines — i.e., chart-data transformations are written as range adaptor stacks, not imperative loops. This is the architectural shape against which any external automation surface (PPTTC, COM, RPC) sits.

### #5. Valentin Ziegler — "Developing a Simple PowerPoint Add-in, How Hard Can It Be?" (C++ Russia 2019)

The think-cell event page describes this as a "short presentation… followed by Q&A at the booth," paired with a full-length text-formatting / range talk by the same speaker the same day. The title is rhetorical — "how hard can it be?" punchlines at the 1M-LoC C++ codebase. This talk's existence confirms think-cell publicly sells the difficulty of PowerPoint integration as part of its recruiting brand: the talk's purpose is to convince C++ engineers that the integration challenges are interesting, not to ship a how-to. The video itself is linked on the think-cell talks page and is the canonical answer to the question of "what is the hard part of building tcaddin.dll." Pair with the "Industrial Strength Software Hacking" slide deck for the full picture.

---

## 3. Engineering team tech-stack inventory (public-only sources)

Sourced from the think-cell career pages (think-cell.com/en/career/jobs/development, /en/career/dev), the talks index, the dev blog, and **public** LinkedIn job postings. No private LinkedIn profile content scraped beyond what the user already named (Theophil, Schödl, Ziegler, Müller, McPartlin, Schöch).

### Named engineers with public conference activity

| Name               | Public role                                                                 | Public output                                                                                                                                                                 |
| ------------------ | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Arno Schödl        | Co-Founder & CTO / Technical Director (later "Founder & Technical Advisor") | rvalue lifetime, ranges, error handling, AAAI 2006, SIGGRAPH track from prior career, CppCast 2018, X handle @aschoedl                                                        |
| Sebastian Theophil | Senior SE / Team Lead AI; founding employee (2002–)                         | Cross-platform talk, ARM assembly talk, error handling C++26, Typescripten, debugging talk, AAAI 2006 co-author. Sole engineer with public macOS-port and ARM-hooking signal. |
| Valentin Ziegler   | Senior SE                                                                   | PowerPoint add-in talk (C++ Russia 2019), text formatting, RWTH recruiting, memory model talk, C++ vs Java                                                                    |
| Volker Schöch      | Senior Software Developer                                                   | Recruiting Q&A video, RWTH 2016 talk; no solo conference talks. LinkedIn handle: volker-c-schöch (publicly-listed Berlin / think-cell).                                       |
| Jonathan Müller    | Library developer ("foonathan")                                             | Cache-friendly, dispatching, JSON, lifetimes, max overengineering, functional programming. ISO C++ committee member. Open-source library author at foonathan.net.             |
| Simon McPartlin    | Senior software engineer (per 2014 event page)                              | Industrial Strength Software Hacking (Meeting C++ 2014). Single public talk; the most architecturally revealing one.                                                          |
| Fabio Fracassi     | C++ engineer                                                                | Memory model talk + C++ vs Java (co-presenter with Ziegler)                                                                                                                   |
| Matthias Hofmann   | (no public think-cell talk found in this run; user-named but not surfaced)  | —                                                                                                                                                                             |

### Tech stack disclosed in public job postings

Direct quotes from think-cell.com/en/career/jobs/development:

- "Everything we do is C++. Even our customer portal is written in C++."
- "There's some Assembler glue code where necessary, and our build scripts are written in Python."
- "We use Boost throughout our codebase — for example, **Boost.Spirit for parsing**."
- They maintain "a proprietary range library going beyond Boost.Range and range-v3, including unifying internal and external iteration."
- Cross-platform library: "supports macOS and Windows from a single codebase."
- "Proprietary **reference-counting and persistence libraries to save and restore whole object trees**."
- "Assertions and error checks stay in the release code" → **server-side bug reporting pipeline**.
- Solver: **CLP** (COIN-OR) for simplex / linear optimization (chart layout).
- Vision: **OpenCV** + **Leptonica** for chart recognition (read-back from images).
- "A dedicated team that focuses on reverse engineering with **the IDA from Hex-Rays**."
- "Each time our software starts, **we patch the Microsoft Office executables in memory**."
- "Rather than hard-coding patch addresses, **we search for small chunks of assembly code**."
- "We have probably **the best function-hooking engine out there**."

### Salary signal (LinkedIn job postings, multiple regions)

EUR 130,000 / yr after one year of employment. Published verbatim on at least four country-localized LinkedIn job postings (DE, FI, BY, AU). The salary is a tech-stack signal in that it tells you think-cell is paying for senior-level reverse-engineering and C++ talent, not entry-level Office-add-in plumbing.

### WG21 (C++ standards) papers — github.com/think-cell/wg21

12 papers visible: P2881 Generator-for, P2895 Noncopyable, P3001 No std::hive, P3014 expected customize exception, P3429 Reflection header dependencies, P3431 Deprecate const views, P3555 Infinite range, P3649 Principled safety profiles, P3801 Task concerns, P3843 Function wrapper, P3845 Naming execution monad, P3929 Safety hazard: function_ref. **None** touch COM, OOXML, Office, RPC, or automation. think-cell's standards work is library-quality / language-safety only — they don't disclose Office-integration techniques to ISO.

### Dev blog signal — think-cell.com/en/career/devblog/overview

31 posts visible. Two of architectural relevance:

- **"By Default Different"** — discusses uniqueness of "named mutexes, Win32 user-defined messages, file names for shared memory backing." This is the closest the blog comes to disclosing **inter-process signaling** between tcaddin.dll instances and any sidecar process (e.g., `tcasr.exe`).
- **"Event or no Event?"** — cross-platform UI widget event firing on programmatic state changes; relevant because automation surfaces have to choose whether programmatic edits fire change events that PowerPoint reacts to.

The other 29 posts are language-design / C++ standardization content; no Office disclosures.

### Public file-system / process signal (third-party, not think-cell)

From System Explorer's `tcaddin.dll` profile + automation-analysis sandboxes:

- COM registration: **`thinkcell.addin`** — accessed via `Application.COMAddIns("thinkcell.addin").Object`.
- DLL is invocable directly via `rundll32.exe "tcaddin.dll",#2` (and ordinals #3, #5, #6, #7) — i.e., **exported ordinal entry points** for installer / update tasks **outside** the Office host.
- Companion: `tcasr.exe` — required for internal datasheet open and email features (Send Slides, Request Support).
- Windows Defender ASR conflict: rules `3B576869-A4EC-4529-8536-B80A7769E899` and `c1db55ab-c21a-4637-bb3f-a12568109d35` block tcaddin.dll, confirming the in-memory-patching pattern triggers EDR heuristics — exactly what you'd expect from a binary that detours Office processes at startup.

---

## 4. Bottom-line — what does think-cell's public engineering output reveal about tcaddin.dll's internal API structure?

Triangulating across the 21 talks, 31 blog posts, 12 WG21 papers, and the public job-page disclosures, **the structure of tcaddin.dll's hidden API is consistent and inferable** even though the company never publishes a contract for it. The picture is:

**Layer 1 — the documented surface.** tcaddin.dll registers as a COM add-in under ProgID `thinkcell.addin`, exposes a small set of methods (`UpdateChart`, `ActivateAddIn`, `IsAddInActive`) callable from any Office host's COMAddIns collection. Customer-facing automation (UiPath, VBA macros, the documented PPTTC template-control format) lives here. The job posting and the McPartlin 2014 talk both flag this surface as **"things that _are_ possible via the documented Microsoft Office API"** — the small fraction of behavior think-cell exposes through Office's own extension points.

**Layer 2 — the in-process hooking layer.** This is where the bulk of tcaddin.dll lives. McPartlin's "Function detouring framework" + "Finding the target function" (signature scanning) is the architecture. think-cell's career page is unusually candid: "we patch the Microsoft Office executables in memory… rather than hard-coding patch addresses, we search for small chunks of assembly code." Theophil's 2024 ARM talk extends this engine to AArch64 (Apple Silicon Office, Windows-on-ARM Office). The implication for the user's research question — _is there a deeper API surface than the manual_ — is **yes, but it is not an API**: it is a private function-hooking layer that intercepts Office internals and is intentionally not stable, not contractual, and not callable from outside the host process. Anything an automation client could "call" at this layer would have to be wrapped through layer 1's COM surface or layer 3's RPC.

**Layer 3 — the cross-platform abstraction + sidecar process.** Theophil's cross-platform talk names the rendering surfaces (NSView / CALayer / HWND / DirectX texture) and confirms tcaddin.dll shares Office's main message loop. The "By Default Different" blog post implies named-mutex / Win32-user-message / shared-memory-backed-file inter-process signaling — consistent with `tcasr.exe` being a sidecar that the in-process DLL talks to for tasks Office shouldn't host (datasheet open, mail send, support requests, license / update flows).

**Layer 4 — the data model and persistence.** The job posting names "proprietary reference-counting and persistence libraries to save and restore whole object trees." The chart-labeling papers (AAAI 2006, Smart Graphics 2005) describe algorithms that operate over rich chart-object graphs, not flat OOXML. Combined with the support-page note that converting to OOXML breaks chart-state synchronization ("This element was changed without think-cell"), the picture is: think-cell's chart data is stored as a **proprietary serialized object tree, embedded in the .pptx as one or more custom XML parts**. OOXML is the carrier; the payload is think-cell's own format produced by their persistence library. No public talk describes this format. The "Express Your Expectations: A Fast, Compliant JSON Pull Parser" talk hints that the customer portal's chart-data exchange may be a JSON projection of the same tree.

**Layer 5 — the range-based functional core.** Schödl's range talks + Theophil's reusable-code talk + Müller's library work establish that the 1M-LoC codebase is structured as **internal-iteration range pipelines**, not imperative loops. This matters for automation because a future API surface that accepts "data + recipe" (PPTTC-style) is the natural shape for a system that internally pipelines transformations through ranges. The 2026-04-29 PPTTC research notes in this corpus already match this pattern — PPTTC's declarative shape is the right outside-skin for a range-pipeline internal architecture.

**What this means for the user's research question.** A "deeper API surface" beyond the manual exists at layers 2–4, but **none of it is exposed as a callable contract**:

1. Layer 2 (function-hook engine) is private and platform-binary-specific. Any "deeper" automation that depended on it would be no more stable than think-cell's signature scanner is — i.e., it would break on Office point releases.
2. Layer 3 (sidecar IPC) goes through `tcasr.exe` and is named-mutex / shared-memory-backed; not advertised, not documented, and changing it would break think-cell's own internal datasheet/email features.
3. Layer 4 (chart-object-tree custom XML part) **is** the technically richest hidden surface — it is the actual, durable representation of every chart think-cell has ever drawn. But its schema is unpublished, the company actively warns users that touching it via OOXML conversion breaks state ("manually carry over changes to think-cell"), and there is zero public disclosure of its grammar.

The honest answer to "is there a deeper API than the documented manual" is: **the only stable, contractual deeper surface is PPTTC and the small COM object** (`Application.COMAddIns("thinkcell.addin").Object`). Everything else exists, is technically richer, and is publicly admitted to exist — McPartlin 2014 + Theophil 2024 + the career page literally say so — but is by think-cell's own architectural choice not a callable API. Automation that wants more than the manual exposes has two routes: (a) drive the documented COM object from Office VBA / .NET / UiPath, or (b) author a PPTTC template and drive the documented templating channel. Anything else would mean reverse-engineering tcaddin.dll's own custom XML part schema, which the corpus's other agents (PPTTC validator, hidden-surface probe) are better positioned to do than this corpus is positioned to ask think-cell about.

---

## Sources

- [think-cell talks index](https://www.think-cell.com/en/career/talks)
- [think-cell talks overview](https://www.think-cell.com/en/career/talks/overview)
- [think-cell career — development jobs](https://www.think-cell.com/en/career/jobs/development)
- [think-cell career — dev page](https://www.think-cell.com/en/career/dev)
- [think-cell developer blog](https://www.think-cell.com/en/career/devblog/overview)
- [think-cell on CppCon](https://cppcon.org/think-cell/)
- [think-cell at Meeting C++ 2014 (McPartlin)](https://www.think-cell.com/en/career/events/2014-12-04/)
- [Industrial Strength Software Hacking PDF](https://www.think-cell.com/assets/think-cell_talk_softwarehacking.pdf)
- [Passive ARM Assembly PDF](https://www.think-cell.com/assets/think-cell_talk_arm.pdf)
- [Nobody Can Program Correctly PDF](https://www.think-cell.com/assets/en/career/talks/pdf/think-cell_talk_debugging.pdf)
- [Cross-platform talk slideshow](https://www.think-cell.com/en/career/talks/cross-platform)
- [Cross-platform talk PDF (ACCU)](https://accu.org/conf-docs/PDFs_2021/sebastian_theophil_windows_macos_and_the_web_lessons_from_cross_platform_development_at_think_cell.pdf)
- [Cross-platform talk YouTube — CppNow 2021](https://www.youtube.com/watch?v=Cmud1jO__VA)
- [Cross-platform talk YouTube — C++ on Sea 2022](https://www.youtube.com/watch?v=lXNr276_fJA)
- [Cross-platform talk YouTube — Core C++ 2022](https://www.youtube.com/watch?v=G9P9LbJuxU0)
- [Passive ARM Assembly YouTube](https://www.youtube.com/watch?v=uyIEg0HkWrQ)
- [SwedenCpp 2024 recap](https://a4z.gitlab.io/blog/2024/12/11/SwedenCpp-2024.html)
- [Stockholm Meetup 2024-11-21](https://www.think-cell.com/en/career/events/2024-11-21)
- [C++ Russia 2019 (Ziegler PowerPoint Add-in talk)](https://www.think-cell.com/en/career/events/2019-04-19)
- [C++ Russia rvalue talk YouTube](https://www.youtube.com/watch?v=zzkpTbJiFPM)
- [using std::cpp 2023 rvalue talk YouTube](https://www.youtube.com/watch?v=Tz5drzXREW0)
- [Rvalue talk slideshow](https://www.think-cell.com/en/career/talks/rvalue)
- [CppCon 2024 (Reusable Code)](https://www.think-cell.com/en/career/events/2024-09-15)
- [CppCon 2021 online (Typescripten)](https://www.think-cell.com/en/career/events/2021-10-27)
- [CyberDay RWTH 2016 (Ziegler + Schöch)](https://www.think-cell.com/en/career/events/2016-06-27)
- [Berlin C++ Meetup 2025-09-30](https://www.think-cell.com/en/career/events/2025-09-30)
- [CppCast Schödl interview](https://cppcast.com/arno-schodl/)
- [Schödl — C++ Europe profile](https://cppeurope.com/speakers/arno-schodl-ph-d/)
- [Theophil — C++ Europe profile](https://cppeurope.com/speakers/sebastian-theophil/)
- [Volker Schöch LinkedIn (public profile, Berlin)](https://www.linkedin.com/in/volker-c-sch%C3%B6ch-334b111/)
- [think-cell Wikipedia](https://en.wikipedia.org/wiki/Think-cell)
- [think-cell jobs board on Meeting C++](https://meetingcpp.com/jobs/items/Cpp-developer-at-think-cell.html)
- [think-cell company page on LinkedIn](https://www.linkedin.com/company/think-cell)
- [LinkedIn job posting — Berlin C++ developer (DE)](https://de.linkedin.com/jobs/view/c++-developer-m-f-d-in-berlin-and-remote-130-000-euro-per-year-at-think-cell-software-3703608573)
- [LinkedIn job posting — Berlin C++ developer (FI)](https://fi.linkedin.com/jobs/view/c++-developer-m-f-d-in-berlin-and-remote-up-to-130-000-eur-per-year-at-think-cell-software-3853487170)
- [Codeforces — about think-cell](https://codeforces.com/blog/entry/125618)
- [System Explorer — tcaddin.dll](https://systemexplorer.net/file-database/file/tcaddin-dll)
- [KB0233 — Windows Defender / tcaddin conflict](https://www.think-cell.com/en/resources/kb/0233)
- [KB0126 — OOXML conversion warning](https://www.think-cell.com/en/resources/kb/0126)
- [KB0173 — Word/Excel chart support](https://www.think-cell.com/en/resources/kb/0173)
