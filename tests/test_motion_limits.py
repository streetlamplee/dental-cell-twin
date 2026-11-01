"""Analytical extrema and declared-limit audit, independent of Kit/USD/hardware."""

import math

import pytest

from core.motion_limits import audit_boundary, audit_smoothstep, retime_duration, urdf_rate_limits


def definition(kind="revolute", velocity=1, acceleration=2):
    return dict(type=kind, velocity=velocity, acceleration=acceleration)


def test_exact_peak_rates_direction_and_required_duration():
    report = audit_smoothstep([(0, {"j": 1}), (2, {"j": -3})], {"j": definition()})
    segment = report["segments"][0]
    row = segment["joints"]["j"]
    assert row["peak_velocity"] == pytest.approx(3)
    assert row["peak_acceleration"] == pytest.approx(6)
    assert row["velocity_peak_time_s"] == 1
    assert row["acceleration_peak_endpoint_times_s"] == [0, 2]
    assert row["velocity_ratio"] == 3 and row["acceleration_ratio"] == 3
    assert segment["min_duration_known_limits_s"] == pytest.approx(max(6, math.sqrt(12)))
    assert report["status"] == "exceeded"


def test_duration_scaling_and_exact_equality_are_allowed():
    fast = audit_smoothstep([(0, {"j": 0}), (1, {"j": 1})], {"j": definition(velocity=1.5, acceleration=6)})
    slow = audit_smoothstep([(0, {"j": 0}), (2, {"j": 1})], {"j": definition(velocity=1.5, acceleration=6)})
    assert fast["status"] == slow["status"] == "within"
    assert slow["joints"]["j"]["peak_velocity"] == fast["joints"]["j"]["peak_velocity"] / 2
    assert slow["joints"]["j"]["peak_acceleration"] == fast["joints"]["j"]["peak_acceleration"] / 4


def test_retiming_extends_only_when_required_and_honors_known_acceleration():
    assert retime_duration({"j": 0}, {"j": 0.2}, 0.45, {"j": 0.1}) == pytest.approx(3)
    assert retime_duration({"j": 0}, {"j": 0}, 0.45, {"j": 0.1}) == 0.45
    assert retime_duration({"j": 0}, {"j": 0.01}, 0.45, {}) == 0.45
    assert retime_duration({"j": 0}, {"j": 1}, 0.45, {"j": 100}, {"j": 1.5}) == 2


@pytest.mark.parametrize("limit", [0, -1, float("inf"), float("nan")])
def test_retiming_does_not_ignore_invalid_declared_limits(limit):
    with pytest.raises(ValueError):
        retime_duration({"j": 0}, {"j": 1}, 0.45, {"j": limit})


def test_missing_limits_are_unverified_even_for_stationary_joint():
    report = audit_smoothstep([(0, {"j": 0}), (1, {"j": 0})], {"j": definition(velocity=None, acceleration=None)})
    assert report["status"] == "incomplete"
    row = report["joints"]["j"]
    assert row["peak_velocity"] == row["peak_acceleration"] == 0
    assert row["velocity_status"] == row["acceleration_status"] == "unverified"


def test_interior_segment_peak_is_not_hidden_by_endpoints_or_holds():
    report = audit_smoothstep([(0, {"j": 0}), (2, {"j": 0}), (2.1, {"j": 1}), (5, {"j": 1})],
                             {"j": definition(velocity=10, acceleration=None)})
    assert report["joints"]["j"]["velocity_peak_segment"] == 1
    assert report["joints"]["j"]["peak_velocity"] == pytest.approx(15)
    assert report["status"] == "exceeded"


def test_continuous_joint_uses_raw_runtime_displacement_not_shortest_angle():
    report = audit_smoothstep([(0, {"c": 0}), (1, {"c": 2 * math.pi})],
                             {"c": definition("continuous", 20, 100)})
    assert report["joints"]["c"]["peak_velocity"] == pytest.approx(3 * math.pi)


def test_prismatic_units_and_gripper_signs():
    report = audit_smoothstep([(0, {"left": 0.012, "right": -0.012}),
                              (0.15, {"left": 0.0045, "right": -0.0045})],
                             {j: definition("prismatic", 0.08, None) for j in ("left", "right")})
    for row in report["joints"].values():
        assert row["units"] == "m/s, m/s^2"
        assert row["peak_velocity"] == pytest.approx(0.075)
        assert row["peak_acceleration"] == pytest.approx(2)
        assert row["velocity_status"] == "within"


def test_real_position_jump_is_not_hidden_by_continuous_joint_wrap():
    limits = {"x": definition("prismatic"), "c": definition("continuous")}
    report = audit_boundary({"x": -0.2, "c": 2 * math.pi}, {"x": 0.09, "c": 0}, limits)
    assert report["status"] == "discontinuous"
    assert report["joints"]["x"]["physical_delta"] == pytest.approx(0.29)
    assert report["joints"]["x"]["status"] == "position_jump"
    assert report["joints"]["c"]["status"] == "continuous_angle_wrap"


def test_continuous_half_turn_reset_is_still_a_real_jump():
    report = audit_boundary({"j": math.pi}, {"j": 0}, {"j": definition("continuous")})
    assert report["status"] == "discontinuous"


@pytest.mark.parametrize("keys", [[], [(0, {"j": 0})], [(1, {"j": 0}), (1, {"j": 1})],
    [(1, {"j": 0}), (0, {"j": 1})], [(0, {"j": 0}), (1, {"other": 1})],
    [(0, {"j": 0}), (float("nan"), {"j": 1})], [(0, {"j": 0}), (1, {"j": float("inf")})]])
def test_invalid_trajectories_fail(keys):
    with pytest.raises(ValueError):
        audit_smoothstep(keys, {"j": definition()})


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_limits_fail(value):
    with pytest.raises(ValueError):
        audit_smoothstep([(0, {"j": 0}), (1, {"j": 1})], {"j": definition(velocity=value)})


def test_urdf_parser_keeps_missing_limits_and_does_not_use_effort(tmp_path):
    path = tmp_path / "robot.urdf"
    path.write_text('<robot name="r"><joint name="j" type="revolute"><limit effort="999" velocity="0.5"/></joint>'
                    '<joint name="c" type="continuous"/><joint name="fixed" type="fixed"/></robot>')
    limits = urdf_rate_limits(path)
    assert limits["j"] == definition(velocity=0.5, acceleration=None)
    assert limits["c"] == definition("continuous", None, None)
    assert "fixed" not in limits
