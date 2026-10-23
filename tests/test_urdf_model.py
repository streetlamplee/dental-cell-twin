import math
from pathlib import Path

import numpy as np
import pytest

from core.urdf_model import load_urdf, rpy_matrix

URDF = Path(__file__).resolve().parents[1] / "reference" / "teeth_mill.urdf"


@pytest.fixture(scope="module")
def mill():
    return load_urdf(str(URDF))


def test_counts_match_the_reference_model(mill):
    assert mill.name == "teeth_mill"
    assert mill.root == "world"
    with_geometry = [l for l in mill.links.values() if l.visuals]
    assert len(with_geometry) == 6
    assert sum(len(l.visuals) for l in mill.links.values()) == 16
    movable = sorted(j.name for j in mill.joints.values() if j.movable)
    assert movable == ["b_joint", "c_joint", "x_joint", "y_joint", "z_joint"]


def test_joint_details(mill):
    x = mill.joints["x_joint"]
    assert (x.type, x.parent, x.child, x.axis) == ("prismatic", "base_link", "x_carriage", (1.0, 0.0, 0.0))
    assert x.lower == pytest.approx(-0.26535) and x.upper == pytest.approx(0.02545)
    b = mill.joints["b_joint"]
    assert b.type == "continuous" and b.axis == (-1.0, 0.0, 0.0) and b.lower is None


def test_visual_shapes_and_colors(mill):
    v = {name: vis for _, vis in mill.visuals() for name in [vis.name]}
    assert v["base_plate"].shape == "box" and v["base_plate"].size == pytest.approx((0.4908, 0.568375, 0.04))
    assert v["spindle"].shape == "cylinder" and v["spindle"].size == pytest.approx((0.028, 0.1))
    assert v["marker"].rgba == pytest.approx((0.85, 0.15, 0.10, 1.0))


def test_home_pose_link_transforms(mill):
    t = mill.link_transforms()
    assert np.allclose(t["x_carriage"][:3, 3], [0.11995, 0.125, 0.41595])
    # tool_tip = x origin + z origin + tool_tip origin (all translations at home)
    assert np.allclose(t["tool_tip"][:3, 3], [0.11995, 0.125 - 0.085 - 0.04, 0.41595 + 0.01565 - 0.19])


def test_joint_motion(mill):
    t = mill.link_transforms({"x_joint": -0.1, "z_joint": 0.01})
    assert np.allclose(t["z_slide"][:3, 3], [0.11995 - 0.1, 0.125 - 0.085, 0.41595 + 0.01565 + 0.01])
    tb = mill.link_transforms({"b_joint": math.pi / 2})["c_platter"]
    # b axis is -x: +90 deg maps local z (0,0,1) to world +y
    assert np.allclose(tb[:3, :3] @ [0, 0, 1], [0, 1, 0], atol=1e-9)


def test_rpy_pitch_rotates_cylinder_axis_to_x():
    # b_hub uses rpy="0 pi/2 0": the cylinder's local z axis becomes world x
    assert np.allclose(rpy_matrix(0, math.pi / 2, 0) @ [0, 0, 1], [1, 0, 0], atol=1e-12)


def test_kinematics_json_round_trip(mill):
    k = mill.kinematics()
    assert k["root"] == "world" and k["units"] == {"length": "m", "angle": "rad"}
    names = [j["name"] for j in k["joints"]]
    assert "x_joint" in names and "tool_tip_joint" in names
    y = next(j for j in k["joints"] if j["name"] == "y_joint")
    assert y["origin_xyz"] == pytest.approx([0, -0.050975, 0.04])


def test_mesh_visuals_are_read(tmp_path):
    (tmp_path / "arm.urdf").write_text("""<robot name="arm">
      <material name="yellow"><color rgba="0.7 0.8 0.1 1"/></material>
      <link name="base"><visual name="shell"><origin xyz="0 0 0.1"/>
        <geometry><mesh filename="../meshes/base.stl" scale="0.001 0.001 0.001"/></geometry>
        <material name="yellow"/></visual></link>
      <link name="link1"/>
      <joint name="j1" type="revolute"><parent link="base"/><child link="link1"/>
        <axis xyz="0 0 1"/><limit lower="-1" upper="1"/></joint>
    </robot>""", encoding="utf-8")
    m = load_urdf(str(tmp_path / "arm.urdf"))
    v = m.links["base"].visuals[0]
    assert v.shape == "mesh" and v.mesh == "../meshes/base.stl" and v.size == (0.001, 0.001, 0.001)
    assert v.rgba == (0.7, 0.8, 0.1, 1.0) and v.origin[2, 3] == 0.1
