"""Inspection cell: camera on the 5-axis machine (reference/teeth_mill.urdf kinematics)."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from core.cell_cycle import CellCycle, CellTiming, View, views_from_spec
from core.urdf_model import model_from_kinematics

ROOT = Path(__file__).resolve().parents[1]
KIN = ROOT / "assets" / "cad" / "teeth_mill.kinematics.json"
CATALOG = ROOT / "assets" / "parts" / "catalog.json"


@pytest.fixture(scope="module")
def model():
    if not KIN.exists():
        pytest.skip("run scripts/urdf_to_step.ps1 first")
    return model_from_kinematics(json.loads(KIN.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def cell(model):
    spec = json.loads(CATALOG.read_text(encoding="utf-8"))["crown"]["cell"]
    return CellCycle(model, views_from_spec(spec["views"]), CellTiming(**spec["timing"]), spec["standoff_m"])


def target(cell, q):
    return (cell.product_seat(q) @ np.array([0, 0, cell.target_dz, 1.0]))[:3]


def test_camera_is_straight_above_the_product_at_every_view(cell):
    for view, q in zip(cell.views, cell.view_poses):
        cam = cell.camera(q)
        d = cam[:3, 3] - target(cell, q)
        assert np.allclose(d, (0, 0, cell.standoff), atol=1e-9), view.name
        assert np.allclose(cam[:3, :3], np.eye(3)), "spindle camera must keep looking down -Z"


def test_views_tilt_and_turn_the_product(cell):
    for view, q in zip(cell.views, cell.view_poses):
        up = cell.product_seat(q)[:3, 2]  # product's own +Z in the base frame
        assert math.degrees(math.acos(np.clip(up[2], -1, 1))) == pytest.approx(view.b_deg, abs=1e-6)
        assert q["c_joint"] == pytest.approx(math.radians(view.c_deg))


def test_all_poses_are_within_joint_limits(cell):
    for q in [cell.load_pose, cell.unload_pose] + cell.view_poses:
        for joint, (lo, hi) in cell.limits.items():
            assert lo - 1e-9 <= q[joint] <= hi + 1e-9


def test_unreachable_standoff_is_rejected(model):
    with pytest.raises(ValueError, match="outside"):
        CellCycle(model, [View("top", 0, 0)], standoff=0.5)


def test_timeline_holds_still_around_each_capture(cell):
    t = cell.timing
    assert cell.cycle_s == pytest.approx(t.load_s + len(cell.views) * (t.move_s + t.hold_s) + t.move_s + t.unload_s)
    for i, vt in enumerate(cell.view_times):
        for dt in (-t.hold_s / 2 + 1e-3, 0.0, t.hold_s / 2 - 1e-3):
            q = cell.pose_at(vt + dt)
            assert all(q[j] == pytest.approx(cell.view_poses[i][j]) for j in q)
        assert cell.view_at(vt) == i
    assert cell.pose_at(None) == cell.load_pose and cell.pose_at(cell.cycle_s + 1) == cell.load_pose


def test_camera_is_parked_aside_during_load_and_unload(cell):
    seat_x = cell.product_seat(cell.load_pose)[0, 3]
    assert cell.camera(cell.load_pose)[0, 3] - seat_x > 0.1  # +X side while loading from -X
    assert cell.camera(cell.unload_pose)[0, 3] - seat_x < -0.1  # -X side while unloading to +X


def test_root_puts_the_load_seat_on_the_belt_line(cell):
    root = cell.root(-1.0, 0.798)
    seat = root @ cell.product_seat(cell.load_pose)
    assert np.allclose(seat[:3, 3], (-1.0, 0.0, 0.798))
