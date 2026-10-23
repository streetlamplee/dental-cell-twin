"""Surface teaching: origin + the five faces of the URDF block on the C platter."""

import math
from pathlib import Path

import pytest

from core.teach import AXES, FACES, Teacher, TeachPoint, TeachProgram
from core.urdf_model import load_urdf

URDF = Path(__file__).resolve().parents[1] / "reference" / "teeth_mill.urdf"


@pytest.fixture(scope="module")
def teacher():
    return Teacher.from_urdf(load_urdf(str(URDF)))


def test_face_program_reaches_origin_and_five_faces_at_20mm(teacher):
    prog = teacher.face_program(0.020)
    assert [p.name for p in prog] == ["origin"] + list(FACES)
    assert prog[0].q == {a: 0.0 for a in AXES}
    for p in prog[1:]:
        c = teacher.verify(p.q, p.face)
        assert c.angle_deg < 1e-6 and c.offset_mm < 1e-6 and c.standoff_mm == pytest.approx(20.0)
        assert c.within_limits


def test_sides_need_b90_and_one_c_quarter_turn_each(teacher):
    prog = {p.name: p.q for p in teacher.face_program(0.020)}
    assert prog["top"]["b_joint"] == 0.0
    sides = [prog[f] for f in FACES if f != "top"]
    assert all(abs(math.degrees(q["b_joint"])) == pytest.approx(90.0) for q in sides)
    assert sorted(round(math.degrees(q["c_joint"])) for q in sides) == [0, 90, 180, 270]


def test_close_standoff_puts_the_sides_out_of_z_travel(teacher):
    with pytest.raises(ValueError, match="side_"):
        teacher.face_program(0.005)
    q, _ = teacher.solve_face("top", 0.005)  # the top face is still reachable
    assert q is not None


def test_verify_finds_the_face_a_jogged_pose_looks_at(teacher):
    q = dict(next(p.q for p in teacher.face_program(0.020) if p.name == "side_+x"))
    q["x_joint"] += 0.002  # jog 2 mm
    c = teacher.verify(q)
    assert c.face == "side_+x" and c.angle_deg < 1e-6 and c.offset_mm == pytest.approx(2.0, abs=1e-6)


def test_program_json_round_trip_and_playback(teacher):
    prog = TeachProgram(teacher.face_program(0.020) + [TeachPoint("P7", {a: 0.01 for a in AXES}, None, "manual")],
                        move_s=1.0, hold_s=0.5)
    back = TeachProgram.from_json(prog.to_json(machine="teeth_mill"))
    assert [p.name for p in back.points] == [p.name for p in prog.points] and back.points[-1].source == "manual"
    for i, p in enumerate(back.points):
        q, k = back.pose_at(back.hold_time(i))
        assert k == i and all(q[a] == pytest.approx(p.q[a]) for a in AXES)
    assert back.duration == pytest.approx(7 * 1.5)
