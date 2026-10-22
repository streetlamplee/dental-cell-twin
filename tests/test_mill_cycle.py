import json
import math
from pathlib import Path

import numpy as np
import pytest

from core.mill_cycle import MillCycle
from core.urdf_model import load_urdf, model_from_kinematics

ROOT = Path(__file__).resolve().parents[1]
URDF = ROOT / "reference" / "teeth_mill.urdf"
KIN = ROOT / "assets" / "cad" / "teeth_mill.kinematics.json"


@pytest.fixture(scope="module")
def mill():
    return load_urdf(str(URDF))


def limits(model):
    return {n: (j.lower, j.upper) for n, j in model.joints.items() if j.type == "prismatic"}


def test_kinematics_json_reproduces_urdf_transforms(mill):
    if not KIN.exists():
        pytest.skip("run scripts/urdf_to_step.ps1 first")
    rebuilt = model_from_kinematics(json.loads(KIN.read_text(encoding="utf-8")))
    q = {"x_joint": -0.1, "y_joint": 0.05, "z_joint": -0.02, "b_joint": 0.4, "c_joint": 1.3}
    a, b = mill.link_transforms(q), rebuilt.link_transforms(q)
    for link in ("x_carriage", "z_slide", "y_table", "b_cradle", "c_platter", "tool_tip"):
        assert np.allclose(a[link], b[link], atol=1e-9), link


def test_cycle_stays_within_limits_and_returns_home(mill):
    lim = limits(mill)
    cyc = MillCycle(lim, duration=3.0)
    home = cyc.joint_values(0.0)
    assert cyc.trigger(10.0)
    last = None
    for i in range(0, 300):
        q = cyc.joint_values(10.0 + i * 0.01)
        for name, (lo, hi) in lim.items():
            assert lo - 1e-12 <= q[name] <= hi + 1e-12, (name, q[name])
        last = q
    assert last["c_joint"] == pytest.approx(2 * math.pi, abs=1e-3)  # one full platter turn
    end = cyc.joint_values(20.0)  # cycle over -> idle home pose
    assert not cyc.busy
    for name in lim:
        assert end[name] == pytest.approx(home[name])
    assert math.cos(end["c_joint"]) == pytest.approx(math.cos(last["c_joint"]), abs=1e-6)


def test_trigger_ignored_while_busy(mill):
    cyc = MillCycle(limits(mill), duration=3.0)
    assert cyc.trigger(0.0)
    assert not cyc.trigger(1.0)
    cyc.joint_values(3.5)
    assert cyc.trigger(4.0)
    assert cyc.cycles == 2
