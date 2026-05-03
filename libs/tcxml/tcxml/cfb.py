"""Pull `think-cellXML` streams out of CFB blobs embedded in .pptx files.

Writing CFB blobs back is intentionally NOT implemented here yet — see
`pack_thinkcell_stream` for the rationale.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterator
from pathlib import Path

import olefile

_THINKCELL_STREAM = "think-cellXML"
_THINKCELL_PACKAGE_STORAGE = "think-cellChild0"
_THINKCELL_PACKAGE_STREAM = "Package"
_EMBED_PREFIX = "ppt/embeddings/oleObject"
_EMBED_SUFFIX = ".bin"


def extract_thinkcell_streams(pptx_path: Path) -> Iterator[tuple[str, bytes]]:
    """Yield (oleObject member name, raw think-cellXML bytes) for each chart blob."""
    with zipfile.ZipFile(pptx_path) as zf:
        members = sorted(
            n for n in zf.namelist() if n.startswith(_EMBED_PREFIX) and n.endswith(_EMBED_SUFFIX)
        )
        for name in members:
            blob = zf.read(name)
            if not olefile.isOleFile(io.BytesIO(blob)):
                continue
            ole = olefile.OleFileIO(io.BytesIO(blob))
            try:
                if not ole.exists(_THINKCELL_STREAM):
                    continue
                with ole.openstream(_THINKCELL_STREAM) as stream:
                    yield name, stream.read()
            finally:
                ole.close()


def pack_thinkcell_stream(
    xml_bytes: bytes,
    package_zip_bytes: bytes | None = None,
) -> bytes:
    """Pack `xml_bytes` (and optional Package ZIP) into a CFB OLE blob.

    Intended layout (matching what real think-cell embeds):

        Root Entry/
          think-cellXML            (UTF-8 XML stream)
          think-cellChild0/        (storage, optional)
            Package                (ZIP bytes)

    Status: NOT IMPLEMENTED.

    Why not implemented yet:

    * `olefile==0.47` is read-mostly; its `write_stream` only replaces an
      existing stream of the same size — it cannot create a CFB container
      from scratch.
    * No other dependency in this repo can write CFB.
    * A correct minimal CFB writer must cover sector size selection,
      FAT/MiniFAT/DIFAT chains, MiniStream cutoff (4096 bytes), the directory
      red-black tree, header magic + sector shift, and stream allocation.
      The MS-CFB spec is ~70 pages; doing this in-repo is several hours of
      careful work with real correctness risk if a deck embeds it.
    * Until we genuinely need round-trip pptx writing, the safer path is to
      raise loudly and let the caller decide (e.g. shell out to a known-good
      CFB writer such as Apache POI / `python-docx`'s OPC pipeline plus a
      separate CFB tool, or use a pre-existing OLE container as a template
      and only swap the `think-cellXML` stream via `olefile.write_stream`
      when the new payload is the same size).

    TODO(tcxml-writer-cfb): implement a minimal MS-CFB writer here once we
    need full deck round-trip. Tracking ticket should reference MS-CFB
    [MS-CFB] sections 2.1 (header), 2.2 (sectors), 2.3 (FAT/DIFAT/MiniFAT),
    2.6 (directory). Suggested first cut: 512-byte sectors, single DIFAT
    sector, no MiniStream allocation when both streams exceed 4096 bytes
    (the typical case for think-cellXML).
    """
    raise NotImplementedError(
        "pack_thinkcell_stream: writing CFB containers from scratch is not "
        "implemented. olefile==0.47 cannot create new CFB blobs and a "
        "minimal MS-CFB writer is deliberately out of scope until full "
        "pptx round-trip is needed. See TODO(tcxml-writer-cfb) in cfb.py."
    )
