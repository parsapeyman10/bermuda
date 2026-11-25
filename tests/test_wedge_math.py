"""Unit tests for wedge.py — half-plane clipping, area, intersections, wedge interiors."""
import math
import numpy as np
import pytest
from wedge import clip_halfplane, area, line_inter, Wedge, region


# ---------------------------------------------------------------- clip_halfplane
def test_clip_halfplane_square_by_diagonal():
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]
    # keep a*x + b*y + c >= 0  with  y >= x  -> a=-1, b=1, c=0
    out = clip_halfplane(square, -1, 1, 0)
    assert area(out) == pytest.approx(8.0, abs=1e-9)
    for x, y in out:
        assert y >= x - 1e-9


def test_clip_halfplane_no_intersection_returns_empty():
    square = [(0, 0), (4, 0), (4, 4), (0, 4)]
    out = clip_halfplane(square, 0, 1, -10)   # keep y >= 10 — nothing survives
    assert out == []


def test_clip_halfplane_keeps_everything_when_inside():
    square = [(1, 1), (3, 1), (3, 3), (1, 3)]
    out = clip_halfplane(square, 1, 0, -0.5)  # keep x >= 0.5 — entire square
    assert area(out) == pytest.approx(4.0, abs=1e-9)


# ----------------------------------------------------------------------- area
def test_area_shoelace_known_shapes():
    assert area([(0, 0), (2, 0), (2, 2), (0, 2)]) == pytest.approx(4.0)
    assert area([(0, 0), (4, 0), (0, 3)]) == pytest.approx(6.0)
    assert area([(1, 1), (1, 1)]) == 0.0 or area([(1, 1)]) == 0.0


# ----------------------------------------------------------------- line_inter
def test_line_inter_perpendicular():
    # y = x  and  y = -x + 2  -> (1, 1)
    p = line_inter((0, 0), 1.0, (0, 2), -1.0)
    assert p[0] == pytest.approx(1.0)
    assert p[1] == pytest.approx(1.0)


def test_line_inter_parallel_returns_none():
    assert line_inter((0, 0), 1.0, (5, 0), 1.0) is None


# --------------------------------------------------------------------- Wedge
def _wedge(apex, mL, mR):
    w = Wedge(apex, mL, mR)
    return w


def test_wedge_interior_point_satisfies_both_halfplanes():
    # apex at origin, legs symmetric slopes ±2, opening UPWARD (V shape): interior y > 2|x|
    w = _wedge((0, 0), -2.0, 2.0)
    hp = w.halfplanes()
    assert len(hp) == 2
    inside = (0.0, 5.0)
    for a, b, c in hp:
        assert a * inside[0] + b * inside[1] + c >= -1e-9
    outside = (0.0, -5.0)
    assert any(a * outside[0] + b * outside[1] + c < 0 for a, b, c in hp)


def test_wedge_down_opening_interior():
    # apex at origin, opening DOWNWARD (inverted V): interior y < -2|x|
    w = _wedge((0, 10), 2.0, -2.0)
    hp = w.halfplanes()
    inside = (0.0, 5.0)
    for a, b, c in hp:
        assert a * inside[0] + b * inside[1] + c >= -1e-9


def test_wedge_ray_directions_match_legs():
    w = _wedge((3, 7), -1.5, 0.75)
    np.testing.assert_allclose(w.uL, np.array([-1.0, 1.5]) / np.linalg.norm([-1.0, 1.5]), atol=1e-12)
    np.testing.assert_allclose(w.uR, np.array([1.0, 0.75]) / np.linalg.norm([1.0, 0.75]), atol=1e-12)


# -------------------------------------------------------------------- region
def test_region_intersection_of_two_cones():
    # two up-cones whose common area exists near their crossing
    w1 = _wedge((0, 0), -2.0, 2.0)
    w2 = _wedge((10, 0), -2.0, 2.0)
    poly = region([w1, w2], box=(-5, 15, -1, 100))
    assert len(poly) >= 3
    # every vertex must satisfy both wedges
    for w in (w1, w2):
        for a, b, c in w.halfplanes():
            for p in poly:
                assert a * p[0] + b * p[1] + c >= -1e-9


def test_region_disjoint_wedges_yield_empty():
    # left wedge opens up from far-left apex, right wedge opens down — disjoint here
    w1 = _wedge((0, 100), -2.0, 2.0)   # up-cone high
    w2 = _wedge((0, 100), 2.0, -2.0)   # down-cone from same apex: intersection is just the apex region
    poly = region([w1, w2], box=(-50, 50, 0, 100))
    # intersection is a degenerate sliver/point -> fewer than 3 vertices or ~zero area
    assert len(poly) < 3 or area(poly) < 1e-6


def test_region_clips_to_box():
    w = _wedge((5, 0), -1.0, 1.0)
    poly = region([w], box=(0, 10, 0, 4))
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert min(xs) >= 0 - 1e-9 and max(xs) <= 10 + 1e-9
    assert min(ys) >= 0 - 1e-9 and max(ys) <= 4 + 1e-9
