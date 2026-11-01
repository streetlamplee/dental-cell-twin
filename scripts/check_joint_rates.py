"""Audit current arm transfers and inspection machine against source URDF rate limits.

Usage: python scripts/check_joint_rates.py [--out new-directory]
Requires numpy only, no Kit/USD/GPU. Writes JSON/Markdown; exit 2 when known
limits are exceeded or position resets are discontinuous, 3 when limits are missing,
0 only when fully verified, 1 on error.
The command never retimes the running app or changes asset/configuration files.
"""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FACTORY = ROOT / "source/extensions/visiontwin.factory/visiontwin/factory"
sys.path.insert(0, str(FACTORY))

from core import layout as L
from core.arm_transfer import ArmModel, ArmTransfer, TransferSpec, yaw_base
from core.cell_cycle import CellCycle, CellTiming, views_from_spec
from core.motion_limits import audit_boundary, audit_smoothstep, urdf_rate_limits
from core.urdf_model import load_urdf, model_from_kinematics


def assert_same_kinematics(model, source):
    """Do not compare limits from a different joint definition with generated trajectories."""
    if set(model.joints) != set(source.joints):
        raise ValueError("URDF/kinematics joint names differ")
    for name, joint in model.joints.items():
        other = source.joints[name]
        if ((joint.type, joint.parent, joint.child, joint.lower, joint.upper) !=
                (other.type, other.parent, other.child, other.lower, other.upper)
                or not np.allclose(joint.origin, other.origin, atol=2e-9, rtol=0)
                or not np.allclose(joint.axis, other.axis, atol=2e-9, rtol=0)):
            raise ValueError(f"URDF/kinematics mismatch: {name}")
        if joint.velocity is not None and joint.velocity != other.velocity:
            raise ValueError(f"URDF/kinematics velocity mismatch: {name}")


def build_trajectories():
    machine_urdf = ROOT / "reference/teeth_mill.urdf"
    machine_kin = ROOT / "assets/cad/teeth_mill.kinematics.json"
    manifest = ROOT / "assets/robots/sources.json"
    robot_source = json.loads(manifest.read_text(encoding="utf-8"))["rebot_b601_dm"]
    robot_urdf = ROOT / "assets/robots/rebot_b601_dm" / robot_source["urdf"]
    expected = robot_source["sha256"][robot_source["urdf"]]
    if hashlib.sha256(robot_urdf.read_bytes()).hexdigest() != expected:
        raise ValueError("robot URDF does not match pinned source hash")
    robot_kin = ROOT / "assets/robots/usd/rebot_b601_dm.kinematics.json"
    catalog = ROOT / "assets/parts/catalog.json"
    cell_spec = json.loads(catalog.read_text(encoding="utf-8"))["crown"]["cell"]
    machine = model_from_kinematics(json.loads(machine_kin.read_text(encoding="utf-8")))
    robot = model_from_kinematics(json.loads(robot_kin.read_text(encoding="utf-8")))
    assert_same_kinematics(machine, load_urdf(str(machine_urdf)))
    assert_same_kinematics(robot, load_urdf(str(robot_urdf)))
    cycle = CellCycle(machine, views_from_spec(cell_spec["views"]), CellTiming(**cell_spec["timing"]), cell_spec["standoff_m"])
    if cycle.timing.load_s != cycle.timing.unload_s:
        raise ValueError("arm requires equal load/unload durations")
    arm = ArmModel(robot, yaw_base(*L.ARM_BASE, L.ARM_YAW_DEG))

    def belt(x):
        pose = np.eye(4)
        pose[:3, 3] = (x, 0, L.CONVEYOR_TOP_Z)
        return pose

    # Same crown poses as the runtime (PART_REST_DZ is checked from source below).
    import ast
    scene_tree = ast.parse((FACTORY / "scene_manager.py").read_text(encoding="utf-8"))
    rest = [ast.literal_eval(n.value) for n in scene_tree.body if isinstance(n, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PART_REST_DZ" for target in n.targets)]
    if rest != [0.0]:
        raise ValueError("PART_REST_DZ changed; audit belt pose must be updated")
    seat = cycle.root(L.CELL_X, L.CONVEYOR_TOP_Z) @ cycle.product_seat(cycle.load_pose)
    transfer = ArmTransfer(arm, L.ARM_WAIT, belt(L.CELL_ENTRY_X), seat, belt(L.CELL_EXIT_X), TransferSpec(cycle.timing.load_s))
    arm_limits = urdf_rate_limits(robot_urdf)
    trajectories = {}
    for phase, data in transfer.phases.items():
        keys = [(t, dict(q, finger_left=g, finger_right=-g)) for t, q, g in data["timeline"]]
        trajectories[f"arm_{phase}"] = (keys, arm_limits, lambda t, phase=phase: transfer.state(phase, t)[0])
    trajectories["inspection_machine"] = (cycle._keys, urdf_rate_limits(machine_urdf), cycle.pose_at)
    sources = [machine_urdf, machine_kin, robot_urdf, robot_kin, catalog, manifest,
               FACTORY / "core/arm_transfer.py", FACTORY / "core/cell_cycle.py", FACTORY / "core/layout.py",
               FACTORY / "core/motion_limits.py", FACTORY / "scene_manager.py", Path(__file__)]
    return trajectories, sources


def crosscheck_runtime(keys, evaluate):
    """Finite differences of actual runtime position evaluators, inside every segment."""
    errors = {"position": 0.0, "velocity": 0.0, "acceleration": 0.0}
    for (t0, q0), (t1, q1) in zip(keys, keys[1:]):
        duration = t1 - t0
        h = duration * 1e-3
        for u in (0.25, 0.5, 0.75):
            t = t0 + duration * u
            before, current, after = evaluate(t - h), evaluate(t), evaluate(t + h)
            for joint in q0:
                delta = q1[joint] - q0[joint]
                expected = dict(position=q0[joint] + delta * u * u * (3 - 2 * u),
                                velocity=delta * 6 * u * (1 - u) / duration,
                                acceleration=delta * (6 - 12 * u) / duration ** 2)
                measured = dict(position=current[joint], velocity=(after[joint] - before[joint]) / (2 * h),
                                acceleration=(after[joint] - 2 * current[joint] + before[joint]) / h ** 2)
                for metric in errors:
                    error = abs(measured[metric] - expected[metric]) / max(1, abs(expected[metric]))
                    errors[metric] = max(errors[metric], error)
    if max(errors.values()) > 1e-5:
        raise AssertionError(f"runtime interpolation differs from audit formula: {errors}")
    return dict(passed=True, normalized_max_errors=errors, tolerance=1e-5,
                method="central differences at u=.25/.5/.75, h=T*.001; endpoints use analytical one-sided limits")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/joint_rates" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    args = parser.parse_args()
    trajectories, sources = build_trajectories()
    reports = {}
    for name, (keys, limits, evaluator) in trajectories.items():
        report = audit_smoothstep(keys, limits)
        report["runtime_crosscheck"] = crosscheck_runtime(keys, evaluator)
        report["endpoint_reset"] = audit_boundary(keys[-1][1], evaluator(keys[-1][0]), limits)
        if report["endpoint_reset"]["status"] == "discontinuous":
            report["status"] = "discontinuous"
        reports[name] = report
    status = "discontinuous" if any(r["status"] == "discontinuous" for r in reports.values()) else "exceeded" if any(r["status"] == "exceeded" for r in reports.values()) else "incomplete" if any(
        r["status"] == "incomplete" for r in reports.values()) else "within"
    result = dict(status=status, trajectories=reports,
                  continuous_boundary_note="Continuous joints may finish at an equivalent angle +/-2pi; raw cycle reset is not a physical motion command. No wrap within segments is assumed.",
                  source_sha256={str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "report.json").write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Joint velocity and acceleration audit", "", f"Status: {status}", "",
             "Analytical cubic smoothstep peaks, checked against declared source URDF limits.",
             "Missing limits remain unverified. No runtime timing or configuration was modified.", ""]
    for name, report in reports.items():
        lines += [f"## {name}", "", f"Duration: {report['duration_s']:.6f} s; status: {report['status']}", "",
                  "| Joint | Units | Segment peak velocity | Velocity limit | Result | Segment peak acceleration | Accel limit | Result |",
                  "|---|---|---:|---:|---|---:|---:|---|"]
        for joint, row in report["joints"].items():
            vl = "missing" if row["velocity_limit"] is None else f"{row['velocity_limit']:.6f}"
            al = "missing" if row["acceleration_limit"] is None else f"{row['acceleration_limit']:.6f}"
            lines.append(f"| {joint} | {row['units']} | {row['peak_velocity']:.6f} | {vl} | {row['velocity_status']} | {row['peak_acceleration']:.6f} | {al} | {row['acceleration_status']} |")
        exceeded = [(s, j, r) for s in report["segments"] for j, r in s["joints"].items() if r["velocity_status"] == "exceeded" or r["acceleration_status"] == "exceeded"]
        lines += ["", "### Exceeded segments", "", "| Segment | Time (s) | Joint | Velocity ratio | Acceleration ratio |", "|---|---|---|---:|---:|"]
        for segment, joint, row in exceeded:
            lines.append(f"| {segment['index']} | {segment['start_s']:.6f}–{segment['end_s']:.6f} | {joint} | {row['velocity_ratio']} | {row['acceleration_ratio']} |")
        lines += ["", "### Runtime endpoint reset", "", "| Joint | Raw delta | Physical delta | Status |", "|---|---:|---:|---|"]
        for joint, row in report["endpoint_reset"]["joints"].items():
            if row["status"] != "continuous":
                lines.append(f"| {joint} | {row['delta']:.9f} | {row['physical_delta']:.9f} | {row['status']} |")
        lines += ["", "A real position jump has no finite continuous-time velocity/acceleration bound; segment peaks exclude that jump."]
        lines += ["", f"Runtime interpolation crosscheck: {report['runtime_crosscheck']['passed']}", ""]
    lines += ["## Limits of interpretation", "", *[f"- {item}" for item in next(iter(reports.values()))["limitations"]],
              "- Continuous joint cycle boundaries require angle unwrapping before use with a real controller."]
    (args.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{status}: report -> {args.out / 'report.md'}")
    return {"within": 0, "exceeded": 2, "discontinuous": 2, "incomplete": 3}[status]


if __name__ == "__main__":
    sys.exit(main())
