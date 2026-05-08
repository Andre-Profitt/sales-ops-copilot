"""Tests for the visual-schema KG. Pure data — no network."""

import pytest

from scripts.sales._pbir_shapes import (
    PENDING,
    SHAPES,
    get_shape,
    list_shapes,
    shape_or_raise,
)


def test_foundation_shapes_captured_at_minimum():
    """The shipped REST-safe shapes must be in the KG."""
    for name in ("card", "slicer", "tableEx", "pivotTable", "textbox"):
        assert name in SHAPES, f"{name} should be captured"


def test_each_shape_points_at_a_real_builder():
    """builder field should match an existing function in _pbir_helpers."""
    import scripts.sales._pbir_helpers as helpers

    for name, shape in SHAPES.items():
        assert hasattr(helpers, shape.builder), (
            f"{name}: builder {shape.builder!r} not found in _pbir_helpers"
        )


def test_get_shape_returns_known():
    s = get_shape("card")
    assert s is not None
    assert s.visual_type == "card"


def test_get_shape_returns_none_for_unknown():
    assert get_shape("not-a-real-visual-type") is None


def test_shape_or_raise_known():
    s = shape_or_raise("tableEx")
    assert s.builder == "build_table_visual"


def test_shape_or_raise_pending_gives_helpful_message():
    with pytest.raises(NotImplementedError, match="PENDING"):
        shape_or_raise("waterfallChart")


def test_shape_or_raise_unknown_gives_helpful_message():
    with pytest.raises(KeyError, match="not in the schema KG"):
        shape_or_raise("not-a-real-visual-type")


def test_pending_and_shapes_disjoint():
    """A shape can't be both captured and pending."""
    assert set(SHAPES).isdisjoint(set(PENDING))


def test_list_shapes_is_sorted():
    assert list_shapes() == sorted(list_shapes())
