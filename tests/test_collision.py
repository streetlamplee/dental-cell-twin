"""Collision math and sampled trajectory regressions (no Kit/USD required)."""

import math

import numpy as np
import pytest

from core.collision import Box, CollisionBlocked, candidate_pairs, overlaps, require_clear, sample_times
from core.urdf_model import rpy_matrix


def box(center=(0, 0, 0), half=(0.5, 0.5, 0.5), angle=0, name="box"):
    c, s = math.cos(angle), math.sin(angle)
    return Box(name, center, half, [[c, -s, 0], [s, c, 0], [0, 0, 1]])


def test_touching_containment_and_separation():
    a = box()
    assert overlaps(a, box((1, 0, 0)))
    assert overlaps(a, box(half=(0.1, 0.1, 0.1)))
    assert not overlaps(a, box((1.001, 0, 0)))
    assert overlaps(a, box((1.001, 0, 0)), margin=0.002)


def test_sat_rejects_rotated_boxes_with_overlapping_aabbs():
    a = box(half=(1, 0.05, 0.1), angle=math.pi / 4)
    b = box((-0.15, 0.15, 0), half=(1, 0.05, 0.1), angle=math.pi / 4)
    lo_a, hi_a = a.aabb()
    lo_b, hi_b = b.aabb()
    assert np.all(hi_a >= lo_b) and np.all(hi_b >= lo_a)
    assert not overlaps(a, b)
    assert candidate_pairs([a], [b]) == []


def test_rigid_transform_preserves_overlap_and_broadphase():
    pose = np.eye(4)
    pose[:3, :3] = box(angle=0.7).axes
    pose[:3, 3] = (5, -7, 0.8)
    a, b = box(name="robot"), box((0.8, 0, 0), name="wall")
    assert overlaps(a.moved(pose), b.moved(pose))
    assert len(candidate_pairs([a.moved(pose)], [b.moved(pose)])) == 1


def test_cross_product_axis_separates_skew_boxes_when_all_face_axes_overlap():
    a = box(half=(1, 0.15, 0.15))
    b = Box("skew", (1.122545859, -0.295310011, 0.904124146), (1, 0.15, 0.15),
            rpy_matrix(1.037416933, -0.904813541, 0.134103842))
    delta = b.center - a.center
    for axis in [*a.axes.T, *b.axes.T]:
        radius = np.abs(a.axes.T @ axis) @ a.half + np.abs(b.axes.T @ axis) @ b.half
        assert abs(delta @ axis) <= radius
    assert not overlaps(a, b)  # six face axes alone would falsely report interference


def test_sampling_detects_midsegment_collision_that_endpoints_miss():
    keys = [(0.0, {"x": -1.0}), (1.0, {"x": 1.0})]
    wall = box(half=(0.05, 0.5, 0.5))
    assert not overlaps(box((-1, 0, 0), half=(0.02, 0.02, 0.02)), wall)
    assert not overlaps(box((1, 0, 0), half=(0.02, 0.02, 0.02)), wall)
    times = sample_times(keys, max_dt=0.1, max_translation=0.02, linear_joints=("x",))
    assert any(overlaps(box((-1 + 2 * t * t * (3 - 2 * t), 0, 0), half=(0.02, 0.02, 0.02)), wall)
               for t in times)


def test_sampling_includes_keyframes_and_limits_smoothstep_joint_increments():
    keys = [(0.0, {"j": 0, "finger": 0}), (0.01, {"j": 2, "finger": 0.012}),
            (0.2, {"j": 2, "finger": 0.012})]
    times = sample_times(keys, max_dt=0.02, max_angle=0.01, max_translation=0.001, linear_joints=("finger",))
    assert times[0] == 0 and times[-1] == 0.2 and 0.01 in times
    assert np.max(np.diff(times)) <= 0.02 + 1e-12
    before = np.array([t / 0.01 for t in times if t <= 0.01])
    assert np.max(np.diff(2 * before ** 2 * (3 - 2 * before))) <= 0.01 + 1e-12


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_sampling_limits_fail(value):
    with pytest.raises(ValueError):
        sample_times([(0, {"j": 0}), (1, {"j": 1})], max_dt=value)


def test_invalid_geometry_and_margin_fail():
    with pytest.raises(ValueError):
        box(half=(-1, 1, 1))
    with pytest.raises(ValueError):
        Box("shear", (0, 0, 0), (1, 1, 1), [[1, 1, 0], [0, 1, 0], [0, 0, 1]])
    with pytest.raises(ValueError):
        overlaps(box(), box(), margin=float("nan"))


def test_blocking_policy_contains_first_contact_and_allows_clear_report():
    require_clear({"status": "clear_at_samples", "contacts": []})
    with pytest.raises(CollisionBlocked, match="load at 0.5000s, link3 vs table"):
        require_clear({"status": "blocked_potential_collision", "contacts": [
            dict(phase="load", time_s=0.5, robot="link3", obstacle="table")]})
