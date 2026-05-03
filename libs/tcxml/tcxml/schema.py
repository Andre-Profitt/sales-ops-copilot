"""Dataclass mirror of the empirically-extracted think-cellXML schema."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Element:
    name: str
    occurrences: int


@dataclass(frozen=True, slots=True)
class Attribute:
    name: str
    occurrences: int


@dataclass(frozen=True, slots=True)
class ChartClass:
    name: str
    occurrences: int


@dataclass(slots=True)
class Schema:
    elements: dict[str, Element]
    attributes: dict[str, Attribute]
    chart_classes: dict[str, ChartClass]
    build_versions: tuple[int, ...] = field(default_factory=tuple)
    namespaces: tuple[str, ...] = field(default_factory=tuple)

    def has_element(self, name: str) -> bool:
        return name in self.elements or name in self.chart_classes

    def has_attribute(self, name: str) -> bool:
        return name in self.attributes


def load_schema(path: Path) -> Schema:
    """Load schema_inventory.json. Raises FileNotFoundError if absent."""
    raw = json.loads(path.read_text(encoding="utf-8"))

    elements = {name: Element(name=name, occurrences=0) for name in raw["all_elements_sorted"]}
    for name, count in raw["element_top_30"]:
        elements[name] = Element(name=name, occurrences=int(count))

    attributes = {
        name: Attribute(name=name, occurrences=int(count)) for name, count in raw["attributes"]
    }

    chart_classes = {
        name: ChartClass(name=name, occurrences=int(count))
        for name, count in raw["chart_classes_top_30"]
    }

    build_versions = tuple(int(b) for b in raw.get("version_gate_distinct_builds", []))
    namespaces = tuple(raw.get("namespaces", []) or ())

    return Schema(
        elements=elements,
        attributes=attributes,
        chart_classes=chart_classes,
        build_versions=build_versions,
        namespaces=namespaces,
    )
