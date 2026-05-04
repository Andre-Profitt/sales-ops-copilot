"""Pre-substitute Jinja-style ``{key}`` placeholders in a .pptx template.

ppttc.exe only fills think-cell named bindings; it never touches plain text in
slide XML. LAND_template.pptx (and similar director-deck templates) ship with
Jinja-style placeholders like ``{director_name}``, ``{period}``,
``{scope_label}`` baked into slide XML as literal text. Without
pre-substitution the rendered .pptx still shows ``{director_name}`` instead of
e.g. ``Jesper Tyrer``.

This module walks a .pptx (a zip of XML parts), substitutes those placeholders
in ``ppt/slides/slide*.xml``, and returns a path to a NEW .pptx (the input is
never mutated). Pure stdlib + lxml; ASCII-only.

Public API
~~~~~~~~~~

* :func:`scan_placeholders` -- discover what ``{key}`` placeholders the
  template contains, and which slide XML files they live in.
* :func:`substitute_placeholders` -- write a copy of the .pptx with every
  occurrence of ``{key}`` replaced by ``bindings[key]`` in the slide XML.
* :func:`binding_name_to_placeholder` -- map a think-cell binding name like
  ``S01_DirectorName`` to the Jinja-style placeholder key ``director_name``.
* :func:`extract_scalar_string_bindings` -- pull every binding from a .ppttc
  whose ``table`` is a single ``[[{string: <val>}]]`` and project it through
  :func:`binding_name_to_placeholder` into a placeholder->string map.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree

# Slide XML parts we care about. We deliberately do NOT touch slide layouts
# or masters: think-cell elements live on slides, and placeholders we are
# asked to substitute always live on a slide as well. Touching layouts would
# also mutate every slide that inherits from them, which is not what callers
# expect.
_SLIDE_GLOB = "ppt/slides/slide*.xml"

# Placeholder regex: ``{key}`` where key is snake_case (lowercase letters,
# digits, underscores; must start with a letter). Matches ``{director_name}``
# but not ``{0}`` or ``{}``. We intentionally keep the grammar narrow so we
# never replace genuine PowerPoint XML attributes that happen to contain
# braces (DrawingML rarely emits literal ``{...}`` inside <a:t>, but we stay
# conservative).
_PLACEHOLDER_RE = re.compile(r"\{([a-z][a-z0-9_]*)\}")

# DrawingML text-run namespace -- used to limit substitution to <a:t> nodes.
_NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}

# Binding-name pattern: ``S01_DirectorName`` -- one ``S<digits>_`` prefix
# followed by a PascalCase identifier. Strip the prefix, then snake_case the
# tail.
_BINDING_PREFIX_RE = re.compile(r"^S\d+_")
_PASCAL_TO_SNAKE_RE = re.compile(r"(?<!^)(?=[A-Z])")


def binding_name_to_placeholder(binding_name: str) -> str:
    """Convert a think-cell binding name to a Jinja-style placeholder key.

    The transform:

    1. Strip a leading ``S\\d+_`` prefix (e.g. ``S01_``, ``S22_``) if present.
    2. Convert PascalCase / camelCase tail to ``snake_case``.

    Examples:
        >>> binding_name_to_placeholder("S01_DirectorName")
        'director_name'
        >>> binding_name_to_placeholder("S01_Period")
        'period'
        >>> binding_name_to_placeholder("S01_ScopeLabel")
        'scope_label'
        >>> binding_name_to_placeholder("S22_StaleActivityFootnote")
        'stale_activity_footnote'
        >>> binding_name_to_placeholder("DirectorName")
        'director_name'
        >>> binding_name_to_placeholder("already_snake")
        'already_snake'

    Args:
        binding_name: think-cell binding name.

    Returns:
        snake_case placeholder key (no surrounding braces).

    Raises:
        ValueError: if ``binding_name`` is empty or all-whitespace.
    """
    if not binding_name or not binding_name.strip():
        raise ValueError("binding_name must be a non-empty string")
    tail = _BINDING_PREFIX_RE.sub("", binding_name)
    if not tail:
        raise ValueError(f"binding_name has no body after stripping prefix: {binding_name!r}")
    snake = _PASCAL_TO_SNAKE_RE.sub("_", tail).lower()
    # Collapse accidental double underscores from awkward inputs.
    while "__" in snake:
        snake = snake.replace("__", "_")
    return snake.strip("_")


def scan_placeholders(template_path: Path) -> dict[str, list[Path]]:
    """Discover ``{key}`` placeholders inside a .pptx's slide XML.

    Walks every ``ppt/slides/slide*.xml`` part, scans <a:t> text-run nodes,
    and groups placeholder keys by the slide-XML zip-internal paths they
    appear in.

    Args:
        template_path: Path to a .pptx file.

    Returns:
        Mapping of placeholder key -> sorted list of slide-XML zip-internal
        paths (as ``pathlib.Path`` instances rooted at ``ppt/slides/``).
        Empty dict if the file has no placeholders.

    Raises:
        FileNotFoundError: if ``template_path`` does not exist.
        zipfile.BadZipFile: if ``template_path`` is not a valid .pptx.
    """
    template_path = template_path.expanduser().resolve()
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")

    found: dict[str, set[Path]] = {}
    with zipfile.ZipFile(template_path, "r") as zf:
        for name in zf.namelist():
            if not _is_slide_xml(name):
                continue
            xml_bytes = zf.read(name)
            for key in _scan_placeholders_in_xml(xml_bytes):
                found.setdefault(key, set()).add(Path(name))

    return {k: sorted(v) for k, v in sorted(found.items())}


def substitute_placeholders(
    template_path: Path,
    bindings: dict[str, str],
    output_path: Path | None = None,
    include_masters: bool = False,
) -> Path:
    """Write a copy of ``template_path`` with placeholders substituted.

    For every ``ppt/slides/slide*.xml`` inside the .pptx, every <a:t> text-run
    is scanned for ``{key}`` patterns. Whenever ``key`` appears in
    ``bindings``, the text run is rewritten with the substituted value.
    Other parts of the .pptx (layouts, theme, media, etc.) are copied
    verbatim. Slide-master XML parts are processed iff
    ``include_masters=True``.

    Notes:
        * The input ``template_path`` is NEVER mutated.
        * Placeholders absent from ``bindings`` are left untouched (they may
          be filled later by ppttc.exe through think-cell named bindings or
          a downstream substitution pass).
        * Substitution is text-only: the values are XML-escaped before being
          written into <a:t>. Newlines in values become literal newlines in
          the run text -- callers that need multi-paragraph runs should
          split the value themselves and pre-render the proper <a:p> shape.

    Args:
        template_path: Path to the source .pptx.
        bindings: Mapping of placeholder key -> replacement string. Keys are
            without surrounding braces (e.g. ``"director_name"``, not
            ``"{director_name}"``).
        output_path: Where to write the substituted .pptx. When ``None``
            (default), the output goes to a tempdir as
            ``<stem>-substituted-<ts>.pptx``.
        include_masters: When True, also rewrite ``ppt/slideMasters/*.xml``.
            Default False so existing template_prep callers see no
            behavior change. The polish path
            (``tcrender.template_polish.add_footer_to_master``) puts
            ``{director_name}`` / ``{period}`` placeholders in the
            master and depends on this flag for per-render fill.

    Returns:
        Path to the new .pptx.

    Raises:
        FileNotFoundError: if ``template_path`` does not exist.
        TypeError: if ``bindings`` contains non-string values.
        zipfile.BadZipFile: if ``template_path`` is not a valid .pptx.
    """
    template_path = template_path.expanduser().resolve()
    if not template_path.exists():
        raise FileNotFoundError(f"template not found: {template_path}")
    for k, v in bindings.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise TypeError(
                f"bindings must map str -> str; got {type(k).__name__} -> {type(v).__name__}"
            )

    if output_path is None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        tmpdir = Path(tempfile.mkdtemp(prefix="tcrender_subst_"))
        output_path = tmpdir / f"{template_path.stem}-substituted-{ts}.pptx"
    else:
        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy first so we preserve the zip ordering / compression of non-slide
    # parts byte-for-byte where possible. Then rewrite the slide parts in a
    # second pass.
    shutil.copyfile(template_path, output_path)

    # Read all slide XMLs and rewrite the ones that contain placeholders.
    # We rewrite by streaming a fresh zip, because zipfile in CPython does
    # not support in-place replacement of named entries.
    with zipfile.ZipFile(template_path, "r") as zin:
        members = zin.infolist()
        slide_overrides: dict[str, bytes] = {}
        for info in members:
            target = False
            if _is_slide_xml(info.filename):
                target = True
            elif include_masters and _is_slide_master_xml(info.filename):
                target = True
            if not target:
                continue
            xml_bytes = zin.read(info.filename)
            new_bytes = _substitute_xml(xml_bytes, bindings)
            if new_bytes != xml_bytes:
                slide_overrides[info.filename] = new_bytes

    if not slide_overrides:
        # Nothing to rewrite -- return the copy as-is.
        return output_path

    tmp_out = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        with (
            zipfile.ZipFile(template_path, "r") as zin,
            zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout,
        ):
            for info in zin.infolist():
                data = slide_overrides.get(info.filename)
                if data is None:
                    data = zin.read(info.filename)
                # Preserve original date_time / external_attr so PowerPoint
                # accepts the result.
                zout.writestr(info, data)
        tmp_out.replace(output_path)
    finally:
        if tmp_out.exists():
            try:
                tmp_out.unlink()
            except OSError:
                pass

    return output_path


def extract_scalar_string_bindings(ppttc_path: Path) -> dict[str, str]:
    """Pull scalar-string bindings from a .ppttc and project them to placeholder keys.

    Walks every entry in the .ppttc array; for every binding whose ``table``
    is a single ``[[{string: <val>}]]`` (one row, one cell, ``string`` only),
    map the binding ``name`` through :func:`binding_name_to_placeholder` and
    record the value.

    Bindings whose ``table`` shape is anything else (multi-row, numbers,
    nulls, mixed) are skipped -- those are tabular bindings consumed by
    ppttc.exe, not Jinja-style scalars.

    Args:
        ppttc_path: Path to the .ppttc JSON file.

    Returns:
        Mapping of placeholder key -> string value.

    Raises:
        FileNotFoundError: if ``ppttc_path`` does not exist.
        ValueError: if the .ppttc top-level shape is wrong (not a non-empty
            JSON array of objects).
    """
    ppttc_path = ppttc_path.expanduser().resolve()
    text = ppttc_path.read_text(encoding="utf-8")
    parsed = json.loads(text)
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f".ppttc must be a non-empty JSON array: {ppttc_path}")

    out: dict[str, str] = {}
    for entry in parsed:
        if not isinstance(entry, dict):
            raise ValueError(".ppttc entries must be JSON objects")
        data = entry.get("data")
        if not isinstance(data, list):
            continue
        for binding in data:
            if not isinstance(binding, dict):
                continue
            name = binding.get("name")
            table = binding.get("table")
            if not isinstance(name, str) or not isinstance(table, list):
                continue
            scalar = _scalar_string_from_table(table)
            if scalar is None:
                continue
            try:
                key = binding_name_to_placeholder(name)
            except ValueError:
                continue
            # Last writer wins on collision; this is documented behavior --
            # callers should not have duplicate placeholder mappings across
            # entries, but multiple entries pointing at the same template is
            # a legitimate ppttc shape.
            out[key] = scalar
    return out


# -- internals -------------------------------------------------------------


def _is_slide_xml(name: str) -> bool:
    """Return True if ``name`` is a ``ppt/slides/slide<n>.xml`` part."""
    if not name.startswith("ppt/slides/"):
        return False
    tail = name[len("ppt/slides/") :]
    if not tail.startswith("slide") or not tail.endswith(".xml"):
        return False
    middle = tail[len("slide") : -len(".xml")]
    return middle.isdigit()


def _is_slide_master_xml(name: str) -> bool:
    """Return True if ``name`` is a ``ppt/slideMasters/slideMaster<n>.xml`` part."""
    prefix = "ppt/slideMasters/"
    if not name.startswith(prefix):
        return False
    tail = name[len(prefix) :]
    if not tail.startswith("slideMaster") or not tail.endswith(".xml"):
        return False
    middle = tail[len("slideMaster") : -len(".xml")]
    return middle.isdigit()


def _scan_placeholders_in_xml(xml_bytes: bytes) -> set[str]:
    """Return the set of placeholder keys found in <a:t> text-runs of ``xml_bytes``."""
    keys: set[str] = set()
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return keys
    for t in root.iter(f"{{{_NS['a']}}}t"):
        text = t.text or ""
        for m in _PLACEHOLDER_RE.finditer(text):
            keys.add(m.group(1))
    return keys


def _substitute_xml(xml_bytes: bytes, bindings: dict[str, str]) -> bytes:
    """Return ``xml_bytes`` with placeholders substituted in <a:t> nodes.

    Preserves the original XML declaration / encoding by serializing through
    lxml with ``xml_declaration=True, encoding=root.docinfo.encoding``.
    """
    root = etree.fromstring(xml_bytes)
    changed = False
    for t in root.iter(f"{{{_NS['a']}}}t"):
        text = t.text
        if not text or "{" not in text:
            continue
        new_text = _replace_in_text(text, bindings)
        if new_text != text:
            t.text = new_text
            changed = True
    if not changed:
        return xml_bytes

    # lxml's tostring drops the XML declaration unless explicitly asked.
    # PowerPoint .pptx slide parts ship with an XML declaration; preserve it.
    encoding = "UTF-8"
    standalone = True
    if hasattr(root, "getroottree"):
        tree = root.getroottree()
        info = tree.docinfo
        if info.encoding:
            encoding = info.encoding
        if info.standalone is not None:
            standalone = bool(info.standalone)
    return etree.tostring(
        root,
        xml_declaration=True,
        encoding=encoding,
        standalone=standalone,
    )


def _replace_in_text(text: str, bindings: dict[str, str]) -> str:
    """Replace ``{key}`` occurrences in ``text`` using ``bindings``.

    Keys absent from ``bindings`` are left as-is.
    """

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        if key in bindings:
            return bindings[key]
        return m.group(0)

    return _PLACEHOLDER_RE.sub(repl, text)


def _scalar_string_from_table(table: list[Any]) -> str | None:
    """Return the scalar string value if ``table`` is ``[[{string: <val>}]]``.

    Returns None for any other shape (multi-row, multi-cell, number cells,
    null cells, mixed, etc.).
    """
    if len(table) != 1:
        return None
    row = table[0]
    if not isinstance(row, list) or len(row) != 1:
        return None
    cell = row[0]
    if not isinstance(cell, dict):
        return None
    if list(cell.keys()) != ["string"]:
        return None
    val = cell["string"]
    if not isinstance(val, str):
        return None
    return val


__all__ = [
    "binding_name_to_placeholder",
    "extract_scalar_string_bindings",
    "scan_placeholders",
    "substitute_placeholders",
]
