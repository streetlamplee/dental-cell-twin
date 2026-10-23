"""Transfer robot (Seeed reBot Arm B601-DM): IK and the load/unload pick-and-place."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from core import layout as L
from core.arm_transfer import ARM_JOINTS, ArmModel, ArmTransfer, TransferSpec, _pose, _rot_error, yaw_base
from core.urdf_model import model_from_kinematics

KIN = Path(__file__).resolve().parents[1] / "assets" / "robots" / "usd" / "rebot_b601_dm.kinematics.json"


@pytest.fixture(scope="module")
def model():
    if not KIN.exists():
        pytest.skip("run scripts/fetch_robot.ps1 and scripts/urdf_mesh_to_usd.ps1 first")
    return model_from_kinematics(json.loads(KIN.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def transfer(model):
    arm = ArmModel(model, yaw_base(*L.ARM_BASE, L.ARM_YAW_DEG))
    seat = _pose((L.CELL_X, 0.0, L.CONVEYOR_TOP_Z), np.eye(3))
    entry = _pose((L.CELL_ENTRY_X, 0.0, L.CONVEYOR_TOP_Z), np.eye(3))
    exit_ = _pose((L.CELL_EXIT_X, 0.0, L.CONVEYOR_TOP_Z), np.eye(3))
    return ArmTransfer(arm, L.ARM_WAIT, entry, seat, exit_, TransferSpec(2.0))


def test_rotation_error_is_accurate_for_tiny_angles():
    c, s = math.cos(1e-6), math.sin(1e-6)
    r = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    assert np.allclose(_rot_error(np.eye(3), r), (0, 0, 1e-6), atol=1e-12)  # acos would return 0 here


def test_ik_recovers_reachable_poses(model):
    arm = ArmModel(model, np.eye(4))
    rng = np.random.default_rng(3)
    for _ in range(3):
        target = arm.tool({j: rng.uniform(*arm.limits[j]) * 0.7 for j in ARM_JOINTS})
        q, pe, re = arm.solve(target, [])
        assert pe < 5e-4 and re < math.radians(1.0)
        assert all(arm.limits[j][0] <= q[j] <= arm.limits[j][1] for j in ARM_JOINTS)


def test_unreachable_target_is_rejected(model):
    arm = ArmModel(model, yaw_base(*L.ARM_BASE, L.ARM_YAW_DEG))
    with pytest.raises(ValueError, match="IK failed"):
        ArmTransfer(arm, L.ARM_WAIT, _pose((L.CELL_X, 0.0, 0.8)), _pose((L.CELL_X + 1.5, 0.0, 0.8)),
                    _pose((L.CELL_EXIT_X, 0.0, 0.8)), TransferSpec(2.0))


@pytest.mark.parametrize("phase", ["load", "unload"])
def test_product_is_carried_from_pick_to_place_keeping_its_yaw(transfer, phase):
    ph = transfer.phases[phase]
    states = [transfer.state(phase, t)[2] for t in np.linspace(0, ph["timeline"][-1][0], 200)]
    assert states[0] == "before" and states[-1] == "after" and "carried" in states
    assert states == sorted(states, key=["before", "carried", "after"].index)  # one carry, in order
    _, carried, _ = transfer.state(phase, ph["release_t"] - 1e-6)
    place = ph["place"]
    assert np.linalg.norm(carried[:3, 3] - place[:3, 3]) < 1e-3
    assert np.linalg.norm(_rot_error(carried[:3, :3], place[:3, :3])) < math.radians(1.0)


def test_phases_start_and_end_at_the_wait_pose_with_the_gripper_open(transfer):
    for phase, ph in transfer.phases.items():
        for t in (0.0, ph["timeline"][-1][0]):
            q, _, _ = transfer.state(phase, t)
            assert all(q[j] == pytest.approx(L.ARM_WAIT[j]) for j in ARM_JOINTS), phase
            assert q["finger_left"] == pytest.approx(transfer.spec.finger_open)
        q, _, _ = transfer.state(phase, (ph["grasp_t"] + ph["release_t"]) / 2)
        assert q["finger_left"] == pytest.approx(transfer.spec.finger_closed)
