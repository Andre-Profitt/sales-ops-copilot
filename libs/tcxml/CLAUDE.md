# tcxml

Reader for think-cell's embedded chart XML inside `.pptx` decks.

## Purpose

`.pptx` files store think-cell charts as Compound File Binary (CFB) blobs at
`ppt/embeddings/oleObject*.bin`. Each blob has a stream named `think-cellXML`
holding the chart XML. This library extracts those streams and parses them
against the empirically-derived schema in
`state/thinkcell_bridge/thinkcellxml_corpus/<ts>/schema_inventory.json`
(305 elements, 40 chart classes, 21 attributes, 11 build versions seen).

Reader-only. Writer is a follow-up.

## Install (editable, inside parent venv)

```bash
cd ~/code/apps/sales-ops-copilot
.venv/bin/pip install -e libs/tcxml
```

## Usage

```python
from pathlib import Path
from tcxml import load_schema, extract_thinkcell_streams, parse_thinkcell_xml

schema = load_schema(Path("state/thinkcell_bridge/thinkcellxml_corpus/20260502-071725/schema_inventory.json"))

for blob_name, xml_bytes in extract_thinkcell_streams(Path("deck.pptx")):
    chart = parse_thinkcell_xml(xml_bytes, schema)
    print(blob_name, chart.reqver, len(chart.elements))
```

## Tests

```bash
cd ~/code/apps/sales-ops-copilot
.venv/bin/python -m pytest libs/tcxml/tests/ -x -q
```

`TCXML_SCHEMA` env var overrides the default schema path; `TCXML_FIXTURE_DIR`
overrides the corpus fixture directory.
