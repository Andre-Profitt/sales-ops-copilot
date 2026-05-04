# Legacy / do not use in factory

Forensic references only. Do **not** point the production factory at anything in this folder.

The next-gen LAND review template lives at:

- `assets/templates/land_review_full_28/LAND_review_full_28.tcseed.pptx` (to be wired)
- `config/thinkcell/land_review_full_28.binding_registry.yml`
- `assets/templates/land_review_full_28/land_review_full_28.template_slot_map.v1.yml`

## What ends up here (when migration runs)

These artifacts are slated for quarantine once the new `tcseed` is certified and `scripts/factory.py` defaults are flipped:

- `assets/LAND_thinkcell_seed.pptx` — debris-laden current seed (visible dev instructions on slides 2/7/8/9/11/12/23/24/26/27)
- `assets/LAND_thinkcell_seed.pre-stripdev.pptx` — backup before strip attempt
- `assets/LAND_thinkcell_seed_polished.pptx`, `_polished_v2.pptx`, `_charts.pptx` — earlier polish/master-transplant attempts
- `~/Downloads/Patrick-Gaughan-LAND-2026-Q2-{CLEAN,CONSULTING,FINAL,shipping}.pptx` — failed one-off Patrick variants

**Not yet moved** to avoid breaking the currently-functional May-2026 packaging lane. Migration happens in PR 1 of the plan once the clean `tcseed` is built and certified.

See `docs/handoffs/2026-05-04-thinkcell-template-fix-plan.md` for the surgical PR sequence.
