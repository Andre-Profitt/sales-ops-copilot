# think-cell GitHub Surface Scan

Date: 2026-05-01

## Question

Does GitHub expose a better think-cell automation path than the current
SimCorp factory model: named PowerPoint donors, `.ppttc` JSON payloads,
PowerPoint/Excel COM update runtime, and table-image fallbacks?

## Source Set

- Official think-cell GitHub org: https://github.com/think-cell
- Official `think-cell-library`: https://github.com/think-cell/think-cell-library
- Third-party `ThinkcellBuilder`: https://github.com/Philistino/ThinkcellBuilder
- Third-party `think-cell`: https://github.com/duarteocarmo/think-cell
- Third-party `think-cell-chart-update`: https://github.com/ZoeDekraker/think-cell-chart-update

## Official Org Verdict

The official `think-cell` GitHub org exists, but it is not an Office automation
SDK surface. The public org scan found 17 repos. The active/relevant official
repos are engineering libraries and forks:

| Repo | Signal | Factory implication |
|---|---:|---|
| `think-cell/think-cell-library` | C++ core library, 457 stars, updated 2026-04-17 | Useful for understanding think-cell engineering style only; no PowerPoint automation layer. |
| `think-cell/typescripten` | TypeScript-to-C++ headers compiler | Not relevant to deck factory automation. |
| `think-cell/wg21` | C++ standards papers | Not relevant. |
| Boost/LLVM/OpenCV/minidump forks | dependency/fork material | Not relevant. |

Bounded GitHub code search against the official org did not find public
automation examples for these terms before the API rate limit stopped broader
search expansion:

- `ppttc`
- `PresentationFromTemplate`
- `COMAddIns`
- `thinkcell.addin`
- `AddRangeData`
- `StartTableInsertion`
- `ShowChartGallery`
- `m_strName`

Conclusion: the official GitHub org does not change the API verdict. The
official manual plus VM probe remain the source of truth for the supported
automation surface.

## Third-Party Repos

### Philistino/ThinkcellBuilder

This is the most useful public implementation pattern. It is an unofficial
Python `.ppttc` builder with a presentation/template abstraction, chart/text/table
helpers, and DataFrame support. It outputs `.ppttc` files that think-cell can
turn into PowerPoint when a valid think-cell install/license is present.

Useful ideas to absorb:

- A typed writer API around template objects instead of raw JSON assembly.
- DataFrame-to-think-cell table helpers.
- Explicit support boundaries: named charts, text fields, and tables, but not
  Gantt charts.
- Documentation of a real limitation we have already observed: names/types
  cannot be derived programmatically from a template and mistyped names can be
  silently ignored during build.

Factory verdict: useful as a reference pattern, not as a dependency. The
SimCorp factory already needs stricter row filtering, ARR/ACV basis labels,
donor validation, named-element inventory checks, and VM-bound proof artifacts
than this package provides.

### duarteocarmo/think-cell

This is an earlier/minimal unofficial Python `.ppttc` writer. It shows the
same model: start from an already-authored think-cell template with known object
names, then emit JSON for charts/text fields.

Useful ideas to absorb:

- Small object model for `template`, `name`, `table`, and text-field entries.
- Duplicate template handling tests.
- Simple example fixtures for expected `.ppttc` output.

Factory verdict: confirms that the public Python ecosystem is centered on
`.ppttc` generation, not chart creation or template introspection.

### ZoeDekraker/think-cell-chart-update

This repo is a small demonstration that reads CSV, emits a `.ppttc` payload,
and invokes `C:\Program Files (x86)\think-cell\ppttc.exe`. It is useful as a
minimal end-to-end example, not as reusable infrastructure.

Factory verdict: confirms our `ppttc.exe` runtime lane. It does not solve
donor creation, naming, or validation.

## Factory Decision

Do not pivot to a GitHub dependency. Use the public repos as design references
for a stricter internal writer/linter.

Immediate upgrades worth implementing in the SimCorp factory:

1. Add a typed `.ppttc` builder facade over our existing payload generation.
2. Add a preflight that validates every emitted `name` against the template's
   known named-element inventory before `ppttc.exe` runs.
3. Add a no-silent-ignore gate: if an expected bound chart/table/text field is
   absent in the rendered PPTX, fail the build.
4. Add a dataframe/range helper for chart tables so Excel-derived tables and
   `.ppttc` chart payloads share one row/column basis.
5. Add unit fixtures that compare emitted JSON against canonical `.ppttc`
   payloads per chart family.

## Non-Goals

- Do not use GitHub repos to bypass think-cell licensing.
- Do not treat Python `.ppttc` writers as a chart factory; they require named
  think-cell objects in a template.
- Do not assume the official GitHub org contains hidden Office automation code.
- Do not resume broad GitHub code search until the API rate limit resets; the
  official-org search already answered the high-value question.
