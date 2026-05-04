# Surfaces & Tooling Strategy — 2026-05-04

**Author:** Claude (sales-ops-copilot, deck factory lane)
**Trigger:** Andre, 2026-05-04: "we keep hitting walls. lets plan stratagize and tool before tackeling this again"
**Status:** PARTIALLY EXECUTED — Mac-side gates 1+3 + PPT linter shipped 2026-05-04. VM-side gate 2 written but unrun. See §9 for live progress.

---

## 1. Why we keep hitting walls

We act on these formats by **guessing**, not by reading the spec. Each format has its own validator inside Excel/PowerPoint/think-cell, with its own "I'll silently repair this and not tell you what was wrong" behavior. We only discover problems **visually after rendering** — by which point we've already shipped corrupt artifacts, lost half a session debugging visual drift, or burned a director-pack render trying to figure out why Excel does open-repair-close.

The pattern, restated bluntly:

| Wall we hit                                                   | Root cause                                                                               |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| Excel open-repair-close after named-range migration           | Wrote XML that's _technically_ schema-valid but violates an undocumented Excel invariant |
| `polish_pass.py` shipped black text boxes + Lorem ipsum       | No post-pass visual validation; didn't dry-run before commit                             |
| `master_transplant.py` dragged Sarah's Lorem ipsum            | No before/after visual diff; didn't lint masters                                         |
| `Presentations.Open(.ppttc)` hangs Session 0                  | Pivoted to `ppttc.exe` only after a full hour lost — no documented entry-point map       |
| `LoadStyle` had no effect                                     | Template has no real think-cell anchors; we didn't probe before driving COM              |
| F-01/F-02 (1000× scale errors) caught by Andre eyeballing S18 | No numeric sanity validators; we trusted the math                                        |
| `tcauth` re-signer attempt                                    | Misjudged the legal surface; no policy gate on what tools we even attempt                |

**Common factor:** we shipped without a pre-write validator, without a post-write round-trip canary, and without a known-good reference corpus to diff against.

---

## 2. Surface inventory (every format/protocol/API we touch)

These are everything the deck factory writes, reads, or invokes. Each one has a spec we should read **before** writing more code that touches it.

### A. OOXML SpreadsheetML (xlsx innards)

| Part                       | Spec                     | What we do                                                        | Risk                   |
| -------------------------- | ------------------------ | ----------------------------------------------------------------- | ---------------------- |
| `xl/workbook.xml`          | ECMA-376 §18.2           | openpyxl writes it; we mutate `defined_names`                     | **High** (today's bug) |
| `xl/workbook.xml.rels`     | OPC §11                  | openpyxl manages                                                  | Low                    |
| `xl/worksheets/sheet*.xml` | ECMA-376 §18.3           | openpyxl writes data                                              | Medium                 |
| `xl/styles.xml`            | ECMA-376 §18.8           | openpyxl writes formats                                           | Medium                 |
| `xl/sharedStrings.xml`     | ECMA-376 §18.4           | openpyxl writes strings                                           | Low                    |
| `xl/theme/theme1.xml`      | ECMA-376 §20 / DrawingML | We don't touch — but think-cell does                              | Medium                 |
| `xl/charts/chart*.xml`     | ECMA-376 §21             | We **don't** write these — would unlock native think-cell anchors | Untapped               |

Key sub-element today: `<definedNames>` per §18.2.6.

### B. OOXML PresentationML (pptx innards)

| Part                            | Spec             | What we do                                     | Risk                       |
| ------------------------------- | ---------------- | ---------------------------------------------- | -------------------------- |
| `ppt/presentation.xml`          | ECMA-376 §19.2   | python-pptx writes / we do not normally mutate | Low                        |
| `ppt/slideMasters/*.xml`        | ECMA-376 §19.3   | `master_transplant.py` lifted Sarah's          | **High** (Lorem ipsum bug) |
| `ppt/slides/slide*.xml`         | ECMA-376 §19.3.1 | `polish_pass.py` mutated                       | **High** (black bar bug)   |
| `ppt/theme/*.xml`               | DrawingML §20    | indirect via masters                           | Medium                     |
| `ppt/charts/chart*.xml`         | ECMA-376 §21     | think-cell-generated                           | Read-only                  |
| `ppt/embeddings/oleObject*.bin` | MS-CFB           | think-cell uses these as binding anchors       | Don't touch                |
| `ppt/_rels/*.rels`              | OPC §11          | python-pptx manages                            | Medium                     |

### C. think-cell `.ppttc` JSON

| Layer                                                                | Spec                        | What we do                                     | Risk                                                                  |
| -------------------------------------------------------------------- | --------------------------- | ---------------------------------------------- | --------------------------------------------------------------------- |
| Top-level array                                                      | think-cell docs (KB-1234\*) | `build_ppttc.py` writes                        | Medium — already gated by `validate_ppttc.py` + `test_build_ppttc.py` |
| Cell types: `string`, `number`, `percentage`, `date`, `fill`, `null` | think-cell docs             | We use 5 of 6                                  | Low                                                                   |
| Per-binding scale unit (k, M, %)                                     | think-cell docs             | F-01/F-02 demonstrated we got this wrong twice | Medium                                                                |

### D. think-cell oleObject CFB

| Layer                                     | Spec               | What we do                           | Risk         |
| ----------------------------------------- | ------------------ | ------------------------------------ | ------------ |
| Compound File Binary                      | MS-CFB             | We don't touch; think-cell maintains | Out of scope |
| Embedded Excel snapshot                   | MS-XLS / MS-XLSX   | think-cell embeds                    | Out of scope |
| Auth token bytes (`aiauthentication.bin`) | Vendor proprietary | **Off-limits** per usage policy      | Closed       |

### E. Wire & runtime surfaces

| Surface                                                      | What we do                            | Risk                           |
| ------------------------------------------------------------ | ------------------------------------- | ------------------------------ |
| `ppttc.exe` headless render                                  | Mac → SSH → VM → ppttc.exe → scp back | Medium — opaque error messages |
| Excel COM (`Workbook.Names.Add`, `UpdateBatch.AddRangeData`) | Driven via `wc.Dispatch`              | Medium — Session 0 quirks      |
| PowerPoint COM (`Presentations.Open`, `LoadStyle`)           | Same                                  | Medium — same quirks           |
| SSH `-File` invocation vs `-EncodedCommand`                  | PS5.1 quirks                          | Closed — `-File` works         |
| Mac → VM SCP / robocopy ferry                                | File copy                             | Low                            |

---

## 3. The harness — three layers per surface

For every artifact we write, we need three gates:

### Gate 1: Pre-write validator (Mac-side, fast)

- Runs in <1s.
- Checks our **own writer's output** against a strict ruleset before we hand it to Excel/PowerPoint/ppttc.
- Returns: `clean | warn(reasons) | fail(reasons)`.

### Gate 2: Post-write round-trip canary (VM-side, slower)

- Opens the artifact via vendor app COM.
- Logs the `XlCorruptLoad` mode for xlsx (0=normal, 1=repair, 2=extract). For pptx, monitors any "PowerPoint found a problem with content in <file>" dialog via UIAutomation.
- Saves + closes. If a repair pass ran, the saved bytes will differ from input.
- Diffs `diff_oxml.py` to log exactly what Excel/PPT silently rewrote.
- If repair mode triggered → fail upstream.

### Gate 3: Reference corpus (golden samples)

- 12 known-good xlsx/pptx samples produced by:
  - Excel-Win 2024 (clean save, save with one definedName, save with localSheetId, save with hidden=1)
  - Excel-Mac 2024 (same)
  - openpyxl 3.1.x (same)
  - python-pptx 1.0.x (clean save, save after slide insert, save after master change)
  - LibreOffice round-trip
  - think-cell render output (waterfall, mekko, stacked100, line, table, fill chart)
- Stored in `state/oxml_reference/` (gitignored, regenerated via `scripts/regen_oxml_corpus.py`).
- We `diff_oxml.py` our writes against these and fail if our output omits/reorders attrs vs the corpus.

---

## 4. What we already have vs what's missing

| Capability                        | Tool                                                | Status                                          |
| --------------------------------- | --------------------------------------------------- | ----------------------------------------------- |
| ppttc validator                   | `scripts/validate_ppttc.py`                         | EXISTS — used by `test_build_ppttc.py`          |
| Workbook contract validator       | `scripts/validate_workbook_contract.py`             | EXISTS — covers data shape, not OOXML structure |
| Render-lane contract              | `scripts/validate_render_lane_contract.py`          | EXISTS                                          |
| Connected-factory spec            | `scripts/validate_connected_factory_spec.py`        | EXISTS                                          |
| Excel **strict** OOXML linter     | —                                                   | **MISSING**                                     |
| PPT **strict** OOXML linter       | —                                                   | **MISSING**                                     |
| Excel round-trip canary (VM-side) | —                                                   | **MISSING**                                     |
| PPT round-trip canary (VM-side)   | —                                                   | **MISSING**                                     |
| OOXML structural diff             | `scripts/diff_thinkcell_schemas.py` (partial)       | Partial — covers ppttc only                     |
| Reference corpus                  | —                                                   | **MISSING**                                     |
| Visual SSIM diff                  | `scripts/assess_deck_against_annotated_original.py` | EXISTS — verify if SSIM-grade                   |
| Numeric sanity (F-01/F-02 class)  | F-01/F-02 fixes inline                              | **PARTIAL** — no systematic check               |

---

## 5. Build order (concrete next steps)

Each step has a clear pass/fail and a time budget. We do NOT touch the migration until the harness can tell us _why_ Excel rejected it.

### Step 1 — Strict xlsx linter (Mac-side, ~45 min)

- `scripts/validate_xlsx_strict.py`
- Inputs: path to .xlsx
- Checks:
  - ZipFile opens cleanly
  - All required parts present per OPC
  - `xl/workbook.xml` parses with lxml
  - `<sheets>` precedes `<definedNames>` precedes `<calcPr>` (workbook child order)
  - Each `<definedName>` has `name` + non-empty text content
  - `localSheetId` (if present) is 0-based and < len(sheets)
  - `name` matches `[A-Za-z_][A-Za-z0-9_.]*`, not in cell-reference range
  - `refersTo` text content has matched `'` quoting on sheet names with non-alphanumerics
  - `refersTo` text content has no `#REF!`
  - No duplicate `(name, localSheetId)` pairs
  - `<definedNames>` block sorted alphabetically by name (Excel's serializer always does this)
- Output: JSON report + exit code 0/1.
- **Acceptance:** runs on all 9 director current xlsx → all pass; runs on a hand-crafted broken xlsx → fails with the specific rule.

### Step 2 — Round-trip canary (VM-side, ~30 min)

- `scripts/vm/roundtrip_excel.ps1`
- Inputs: .xlsx path on VM
- Opens via `Excel.Workbooks.Open(path, CorruptLoad := xlNormalLoad)`
- Reads `Workbook.RecoveryLog` if present (Excel 2016+)
- Saves to `<file>.roundtrip.xlsx` and closes
- Returns: JSON `{ corrupt_load: int, repair_log: str | null, bytes_in: int, bytes_out: int }`
- **Acceptance:** roundtrip clean Jesper xlsx → corrupt_load=0; roundtrip the broken 79-name version → corrupt_load=1, repair_log present. We finally see what Excel objected to.

### Step 3 — OOXML diff tool (Mac-side, ~30 min)

- `scripts/diff_oxml.py`
- Inputs: two .xlsx (or .pptx) paths
- Output: markdown diff of:
  - Files added/removed
  - Per-file: tags added/removed, attrs added/removed/modified, text content diff
- **Acceptance:** diff `Jesper.pre.xlsx` vs `Jesper.roundtrip.xlsx` → emits exactly what Excel silently rewrote during repair

### Step 4 — Reference corpus minimal (~30 min)

- `state/oxml_reference/excel_minimal_definedname.xlsx` — handcrafted via Excel COM on VM
- `state/oxml_reference/excel_localsheet_definedname.xlsx`
- `state/oxml_reference/excel_hidden_definedname.xlsx`
- `state/oxml_reference/openpyxl_minimal_definedname.xlsx`
- `state/oxml_reference/openpyxl_localsheet_definedname.xlsx`
- Diff openpyxl-produced vs Excel-produced → identifies the openpyxl serialization deltas in one shot.

### Step 5 — Re-attempt the named-range migration with the harness on (~30 min)

- Run `add_chart_binding_named_ranges.py` → emit broken xlsx
- Run `validate_xlsx_strict.py` → expect specific failure
- Run `roundtrip_excel.ps1` → confirm repair-load + read repair log
- Patch the writer to emit per the exact rule that failed.
- Loop until all 9 directors pass strict + roundtrip.

### Step 6 — PPT strict + roundtrip + visual SSIM (parallel-able to Step 5, ~1h)

- `scripts/validate_pptx_strict.py` — checks: oleObjects present per binding, masters consistent, no orphan placeholders, no out-of-canvas shapes
- `scripts/vm/roundtrip_powerpoint.ps1`
- Visual SSIM extension to `assess_deck_against_annotated_original.py`

**Total time to functional harness: ~3.5 hours of focused build, then we can attack the migration with a feedback loop instead of a guess loop.**

---

## 6. Knowledge research (parallel — research subagents)

Things to read **before** the next code edit on these surfaces:

| Topic                                                        | Source                              | Owner                                          |
| ------------------------------------------------------------ | ----------------------------------- | ---------------------------------------------- |
| ECMA-376 §18.2.6 `definedName` exact attribute schema        | learn.microsoft.com / ECMA-376 PDF  | Already pulled — see search results 2026-05-04 |
| openpyxl `defined_names` known issues + serialization quirks | github.com/openpyxl/openpyxl issues | TODO                                           |
| python-pptx slide-master preservation guarantees             | github.com/scanny/python-pptx       | TODO                                           |
| think-cell ppttc.exe full CLI flags + exit codes             | docs.think-cell.com / vendor SDK    | TODO                                           |
| ECMA-376 §19.3 PresentationML order rules                    | learn.microsoft.com                 | TODO                                           |
| Excel `XlCorruptLoad` enum + `RecoveryLog` API               | learn.microsoft.com                 | DONE — see XlCorruptLoad search hit            |

Each topic gets a 200-LOC max research note in `docs/thinkcell-corpus/research-notes/<topic>.md`.

---

## 7. What we will NOT do

- **No more polish_pass-style output XML hacking** — every mutation goes through the harness.
- **No more master_transplant** — masters lifted from another deck must pass `validate_pptx_strict.py` first.
- **No more guessing at COM** — every COM call we write goes into `tc_com_driver.py` with a docstring citing the MS API doc URL.
- **No tcauth-class artifacts** — usage policy gate.
- **No undocumented entry points** — if it's not in vendor docs, we don't drive it.

---

## 8. Sequencing for Andre's Monday EOD

```
Today (Sat): build harness (Steps 1-4, ~2h focused)
Tonight:     re-attempt SNN_ migration with harness (Step 5, ~1h)
Sunday AM:   PPT side harness + template polish fixes (Step 6, ~1h)
Sunday PM:   ship 9-director deck pack
Monday AM:   buffer + Andre review
Monday EOD:  ship
```

Andre redirects with a single word and we re-sequence.

---

## 9. Progress log (live)

### 2026-05-04 evening — Mac-side harness shipped

| Gate               | File                                                     | Status         | Notes                                                                                                                                                                                                                                                                                 |
| ------------------ | -------------------------------------------------------- | -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 (xlsx strict)    | `scripts/validate_xlsx_strict.py`                        | **DONE**       | All 9 directors clean (exit 0). Forged 3 broken samples to confirm rule-specific fails: `definedName.localSheetId.range`, `definedName.name.cellref-conflict`, `definedName.refersTo.broken`.                                                                                         |
| 1 (pptx strict)    | `scripts/validate_pptx_strict.py`                        | **DONE**       | Seed `LAND_thinkcell_seed.pptx`: 0 fail, 8 warn (real off-canvas brand bars at y=7.87in on 7.50in slide). Polished variants both flag 12 Lorem ipsum leaks across slides 4,5,6,13,15,16,17,18,19,21,22,25 — **confirms the master_transplant bug** that produced `_polished_v2.pptx`. |
| 2 (xlsx roundtrip) | `scripts/vm/roundtrip_excel.ps1`                         | WRITTEN, UNRUN | VM-side. Needs ferry+invoke from `scripts/run_xlsx_canary.py` against the SNN\_-migrated xlsx to identify Excel's repair-pass trigger.                                                                                                                                                |
| 3 (oxml diff)      | `scripts/diff_oxml.py`                                   | **DONE**       | Tested on corpus pairs: detects added attrs (`localSheetId='0'`, `hidden='1'`), modified attr values, structural element add/remove.                                                                                                                                                  |
| Corpus             | `scripts/regen_oxml_corpus.py` + `state/oxml_reference/` | PARTIAL        | 5 openpyxl variants emitted. VM-side `regen_oxml_corpus.ps1` is a stub.                                                                                                                                                                                                               |
| Orchestrator       | `scripts/run_xlsx_canary.py`                             | **DONE**       | One-stop harness. `--skip-vm` works Mac-only. Full Mac→VM→Mac flow ready to fire when Andre is at the VM.                                                                                                                                                                             |

### Findings the harness already surfaced

1. **Defined-name alphabetical ordering is NOT the Excel repair trigger.** All 9 baseline xlsx files have 30 names in insertion order (not alphabetical), and Excel opens them clean. Our prior hypothesis was wrong — saved a wasted migration attempt.
2. **8 slides in the seed template have a brand-bar shape positioned 0.37in past the bottom slide edge** (y=7.87in on a 7.50in slide). Likely from a prior polish_pass run that misjudged the bottom anchor. Not the headline issue Andre flagged but worth a fix.
3. **`master_transplant.py` produced 12 Lorem ipsum leaks** across `_polished_v2.pptx` slides — exactly what Andre saw visually. The harness now catches this pre-commit.

### What the harness does NOT yet catch (TODO — when time permits)

- **Theme-color-bound text** on title slide (black-text bug). Current dark-on-dark detector only resolves `srgbClr@val`; PowerPoint title slides typically reference `schemeClr@val` against `theme1.xml`. Next refinement: resolve theme colors before contrast-checking.
- **VM-side regen_oxml_corpus.ps1** is a stub. Wire after gate-2 confirmed end-to-end.
- **Visual SSIM** post-render canary (Sunday lane).
- **Numeric sanity** for chart payload (F-01/F-02 class). Belongs in `validate_ppttc.py` extension, not here.

### Immediate unblock for the SNN\_ migration

When Andre is back at the VM:

```bash
# 1. Regenerate the broken 79-name xlsx (does not touch baselines)
python3 scripts/add_chart_binding_named_ranges.py --target Jesper-Tyrer --out /tmp/jesper_79.xlsx

# 2. Run the full canary
python3 scripts/run_xlsx_canary.py --host Windows-VM /tmp/jesper_79.xlsx \
    --report state/canary/jesper_79.md

# 3. Read state/canary/jesper_79.md — Excel will tell us the exact repair trigger
#    via gate-2 corrupt_load + repair_log + gate-3 structural diff
```
