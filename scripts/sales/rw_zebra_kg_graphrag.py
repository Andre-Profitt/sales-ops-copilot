"""Semantic retriever over the Zebra + native PBI infrastructure atlases.

Chunks the two markdown files at heading boundaries, embeds with
sentence-transformers all-MiniLM-L6-v2, persists to data/zebra_kg/graphrag/.

Spec: docs/superpowers/specs/2026-05-09-rw-zebra-kg-translator-design.md §4.1
"""

from __future__ import annotations
