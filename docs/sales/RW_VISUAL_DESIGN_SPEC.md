# RW Dashboard — Consulting-grade visual design spec

> **Source of truth:** the brainstorm mockups at `.superpowers/brainstorm/95130-1778258028/content/*.html`. Open them in a browser to see the target look. This doc distills the tokens.

The mockups and the redesign spec (`docs/superpowers/specs/2026-05-08-rw-dashboard-redesign-design.md` § Layout standards) define the target. Everything below is extracted verbatim from those mockups, indexed for reuse in PBI theme JSON + objects shapes.

---

## Color palette

### RAG (threshold-crossable)

| Token         | Hex    | Use                              |
| ------------- | ------ | -------------------------------- |
| `--rag-green` | `#393` | Healthy, on-target, forward, won |
| `--rag-amber` | `#d80` | Watch, near-threshold            |
| `--rag-red`   | `#c33` | At-risk, breach, lost, slipped   |

### Background tints (RAG-band cards)

| Token             | Hex       | Use                     |
| ----------------- | --------- | ----------------------- |
| `--bg-red-tint`   | `#fee`    | At Risk card background |
| `--bg-amber-tint` | `#fff8e6` | Watch card background   |
| `--bg-green-tint` | `#eef9ee` | Healthy card background |

### Neutrals (chrome)

| Token               | Hex       | Use                                             |
| ------------------- | --------- | ----------------------------------------------- |
| `--bg-card`         | `#f5f7fa` | Hero / neutral card background                  |
| `--bg-table-header` | `#f0f0f0` | Table header row                                |
| `--bg-table-alt`    | `#fafafa` | Alternating-row, total-row                      |
| `--text-body`       | `#252423` | Body text (PBI default `firstLevelElements`)    |
| `--text-muted`      | `#666`    | Secondary card lines, axis labels               |
| `--text-very-muted` | `#888`    | Tertiary, footnotes, "X more rows" placeholders |
| `--border-light`    | `#ddd`    | Card outlines                                   |
| `--border-rule`     | `#eee`    | Table cell rules                                |

### SimCorp brand (palette accent)

| Token              | Hex       | Source                              |
| ------------------ | --------- | ----------------------------------- |
| `--simcorp-navy`   | `#1A1D31` | `scripts/build_kpi_strip_mockup.py` |
| `--simcorp-blue`   | `#083EA7` | Same                                |
| `--simcorp-purple` | `#4B17B6` | Same                                |

---

## Typography hierarchy

| Class            | Size    | Weight            | Color                  | Use                                     |
| ---------------- | ------- | ----------------- | ---------------------- | --------------------------------------- |
| Hero number      | 28-32px | 600               | `--text-body`          | Card primary metric                     |
| In-card emphasis | 18px    | 600               | `--text-body` (or RAG) | "$4.8M" inside risk-band card           |
| Body             | 11-12px | 400               | `--text-body`          | Secondary card line, table cell         |
| Section label    | 10px    | 500-600 uppercase | `--text-muted`         | "RISK BAND — only what needs attention" |
| Tertiary         | 10-11px | 400               | `--text-very-muted`    | Footnote, sub-population caveats        |
| Bold span        | inline  | 600               | inherit                | `<strong>` in card body                 |

---

## Layout

### Grid

CSS-grid mockups use:

- 3-card hero: `grid-template-columns: repeat(3, 1fr); gap: 8px`
- 4-card change buckets: `repeat(4, 1fr); gap: 8px`
- Two side-by-side tables: `1fr 1fr; gap: 12px`
- Hero with leading featured card: `2fr 1fr 1fr; gap: 12px`

### Spacing

- Card padding: `10px` standard, `14px` hero
- Section gap (margin-bottom between blocks): `18px`
- Card gap (within a row): `8-12px`

---

## Card patterns

### Risk-band card (RAG-tinted)

```html
<div
  style="background:#fee;border-left:3px solid #c33;padding:10px;text-align:left"
>
  <strong style="color:#c33">⚠ At risk · 5 deals</strong><br />
  <span style="font-size:18px;font-weight:600">$4.8M</span> ARR exposure<br />
  <span style="color:#666;font-size:10px"
    >Stage 5+ slipped or moved backward</span
  >
</div>
```

Three slots: bold colored heading with icon, prominent number with secondary unit, muted definition.

### Hero card (neutral)

```html
<div
  style="background:#f5f7fa;border:1px solid #ddd;padding:14px;text-align:left"
>
  <div style="font-size:10px;color:#666;text-transform:uppercase">
    Quota attainment forecast
  </div>
  <div style="font-size:32px;font-weight:600;line-height:1">87%</div>
  <div style="font-size:11px;color:#666;margin-top:4px">
    $26.1M weighted / $30M quota
  </div>
  <!-- optional progress bar / sparkline / gap row -->
</div>
```

### Compact counter card

```html
<div class="placeholder" style="text-align:left;padding:10px">
  <strong>Stage moves</strong> · 12<br />
  ↑ 7 forward · ↓ 5 back<br />
  <span style="color:#888;font-size:10px">$8.2M moved</span>
</div>
```

---

## Table patterns

```html
<table
  style="width:100%;font-size:11px;border-collapse:collapse;text-align:left"
>
  <tr style="background:#f0f0f0">
    <th style="padding:6px">Stage</th>
    <th style="text-align:right">Forward %</th>
    ...
  </tr>
  <tr>
    <td style="padding:4px">S6</td>
    <td style="text-align:right;color:#393">86%</td>
    ...
  </tr>
  <tr style="background:#fafafa">
    <!-- alt row or Total row -->
    <td style="padding:4px;font-weight:600">Total</td>
    ...
  </tr>
</table>
```

Rules:

- Numerics right-aligned, monospace if possible
- RAG colors inline on threshold-crossable columns only (Forward %, Coverage ×, Days late, Days stalled — NOT on count or $ columns)
- Total row: bold, light-grey background
- Footnote row for sub-population caveats: `style="color:#888;font-size:10px"`
- Max 7 columns per table (per spec § Layout standards)
- Empty state: every table renders "No items match current filters" string when filtered to zero rows

---

## Iconography

Mockups use these inline glyphs:

| Glyph | Use                                         |
| ----- | ------------------------------------------- |
| ⚠     | At risk indicator                           |
| ▲     | Watch / trend up                            |
| ✓     | Healthy / won                               |
| ↑     | Forward stage move                          |
| ↓     | Backward stage move                         |
| ✗     | Lost / fail                                 |
| ·     | Mid-dot separator (typographic, not bullet) |

These are Unicode — render natively in Power BI text fields without needing a custom font.

---

## What this maps to in Power BI

| Mockup element                                                        | PBI mechanism                                                          | Status                                                        |
| --------------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------- |
| dataColors palette                                                    | theme JSON `dataColors`                                                | Apply via `themes/rw_simcorp_consulting.json`                 |
| Background / foreground / tableAccent                                 | theme JSON structural colors                                           | Same file                                                     |
| Typography hierarchy (callout / title / label)                        | theme JSON `textClasses`                                               | Same file                                                     |
| RAG inline coloring on table cells                                    | conditional formatting via `objects.values`                            | Per-visual; capture-and-generalize via `rw_capture_visual.py` |
| Card RAG-tinted backgrounds (At Risk red, Watch amber, Healthy green) | per-visual `objects.background.color`                                  | Per-visual; capture                                           |
| Compact $ format (`$2.5M`)                                            | measure `formatString` (e.g., `"$"#,0.0,,"M"` or `"$"#,0,"K"`)         | Update DAX measures                                           |
| Section labels above visuals ("RISK BAND")                            | `textbox` visualType                                                   | Schema not captured yet — `_pbir_shapes.PENDING`              |
| Hero with progress bar                                                | composite of card + `basicShape` rectangles                            | Defer to Phase 2                                              |
| Funnel chart                                                          | custom visualType `HorizontalFunnel...` (in fixture) or stock `funnel` | Capture + add builder                                         |

---

## Application path (in priority order)

1. **Theme JSON** — biggest single visual upgrade. Apply via `config.themeCollection.customTheme` block in `report.json`. One push, every visual inherits.
2. **Compact format strings on key measures** — `Total Closed Won ARR`, `Total Open Pipeline ARR`, `Total Open Pipeline Value`, etc.: switch `"$"#,0` → `"$"#,0.0,,"M"` so values render as `$2.5M` not `$2,547,381`.
3. **Card consolidation** — pair count + ARR into single cards via `objects` shape. Browser-author one example, then apply via `build_card_visual_with_objects` across all tabs.
4. **Section header textboxes** — capture `textbox` shape from a browser-authored example, add to `_pbir_shapes.SHAPES`, build `build_textbox_visual` helper, sprinkle one above each section per the mockups' "RISK BAND" / "CHANGE BUCKETS" / "DETAIL" labels.
5. **RAG conditional formatting on tables** — capture `objects.values` shape, build `build_table_visual_with_cf`.

Steps 3-5 are browser-author + capture cycles using the harness already built (`rw_capture_visual.py`).
