# RW Unit Policy

- Currency unit: `EUR M`
- Semantic format: `"EUR" #,0,,.0"M";("EUR" #,0,,.0"M");"-"`
- Visual/theme display-unit scaling: forbidden except explicit `None` display units
- Count format: `#,0`
- Percent format: `0.0%`
- Day/duration format: `0.0` where decimal precision is useful, otherwise `0`.

## Findings

| Severity | Finding | Next action |
| --- | --- | --- |
| `info` | No unit policy findings. | Keep the unit audit in the publish gate. |
