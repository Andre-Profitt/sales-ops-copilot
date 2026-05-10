# RW Dashboard Visual QA

Generated: 2026-05-10T09:25:49Z

## Summary

- Pages audited: 7
- Visuals audited: 107
- Findings: 1
- Severity counts: info=0, low=0, medium=1, high=0, critical=0

## Finding mix

- `wall_of_cards`: 1

## Findings

### 1. [medium] wall_of_cards — What Changed / page

Page has an excessive KPI-card density and risks reading as a wall of cards.

- Visual type: `n/a`
- Label: ``
- BBox: x=None y=None w=None h=None
- Evidence: `{"card_area_pct": 0.248, "card_count": 11}`
- Recommendation: Reduce card count, group micro-KPIs, and replace lists of cards with a table/matrix or chart.

## Guardrails encoded

- ARR = Land + Expand only.
- Renewal ACV = Renewal only.
- Do not blend ARR and Renewal ACV except the explicitly labeled `Total Open Pipeline Value`.
- Native cards should carry RAG/accent formatting; tables/matrices should use shared RW/Zebra/IBCS object styles.
