"""USD geometry adapter and sampled robot/environment preflight (no renderer needed)."""

import math

import numpy as np
from pxr import Usd, UsdGeom

from .core import layout as L
from .core.collision import Box, candidate_pairs, sample_times


def geometry_boxes(stage, root_path, frame=None):
    """One enclosing box per visible boundable, in the supplied rigid world frame.

    Uses composed USD transforms, including mesh offsets, references and mm/m scales.
    AABB in each geometry's own frame preserves its orientation. Shear is rejected.
    """
    root = stage.GetPrimAtPath(root_path)
    if not root:
        raise ValueError(f"collision geometry missing: {root_path}")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
                             useExtentsHint=False)
    xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
    inverse = np.linalg.inv(frame) if frame is not None else np.eye(4)
    boxes = []
    for prim in Usd.PrimRange(root, Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Boundable):
            continue
        image = UsdGeom.Imageable(prim)
        if image.ComputeVisibility() == UsdGeom.Tokens.invisible:
            continue
        bound = cache.ComputeUntransformedBound(prim).ComputeAlignedRange()
        if bound.IsEmpty():
            raise ValueError(f"empty collision bounds: {prim.GetPath()}")
        low, high = np.array(bound.GetMin()), np.array(bound.GetMax())
        pose = inverse @ np.array(xforms.GetLocalToWorldTransform(prim)).T
        scale = np.linalg.norm(pose[:3, :3], axis=0)
        if np.any(scale <= 0):
            raise ValueError(f"degenerate collision transform: {prim.GetPath()}")
        # Degenerate faces are thickened only to numerical tolerance, never discarded.
        half = np.maximum((high - low) * scale / 2, 1e-9)
        boxes.append(Box(str(prim.GetPath()), pose[:3, :3] @ ((low + high) / 2) + pose[:3, 3],
                         half, pose[:3, :3] / scale))
    if not boxes:
        raise ValueError(f"no visible collision geometry: {root_path}")
    return boxes


def check_cell(stage, arm, cell, max_dt=1 / 120, max_angle_deg=1.0, margin_m=0.0):
    """Robot vs machine, camera, fixture, conveyors, floor, stands and factory obstacles.

    Includes load/unload interpolation and the entire machine cycle with the arm waiting.
    Excludes self-collision, carried products, inter-machine contacts and teaching/manual
    motion. Base-link vs mounting pedestal is the sole intentional mounting exclusion.
    Report includes every unique (phase, robot geometry, obstacle geometry) pair's first hit.
    """
    if not math.isfinite(margin_m) or margin_m < 0:
        raise ValueError("margin must be finite and nonnegative")
    transfer, cycle = arm.transfer, cell.cycle
    robot_tf = transfer.arm.model.link_transforms(transfer.wait_pose())
    robot = {link: geometry_boxes(stage, f"{L.ARM_PATH}/{link}", transfer.arm.base @ tf)
             for link, tf in robot_tf.items()}
    machine_tf = cell.model.link_transforms(cycle.load_pose)
    machine = {link: geometry_boxes(stage, f"{L.CELL_PATH}/Machine/{cell.model.name}/{link}", cell.root @ tf)
               for link, tf in machine_tf.items()
               if stage.GetPrimAtPath(f"{L.CELL_PATH}/Machine/{cell.model.name}/{link}")}
    if not machine:
        raise ValueError("no machine collision geometry")
    camera = geometry_boxes(stage, f"{L.CELL_PATH}/CameraRig", cell.root @ cycle.camera(cycle.load_pose))
    fixture = geometry_boxes(stage, f"{L.CELL_PATH}/Fixture", cell.root @ cycle.product_seat(cycle.load_pose))
    excluded = [f"{L.CELL_PATH}/Machine", f"{L.CELL_PATH}/CameraRig", f"{L.CELL_PATH}/Fixture", L.ARM_PATH]
    static = [b for b in geometry_boxes(stage, L.FACTORY_PATH)
              if not any(b.name == p or b.name.startswith(p + "/") for p in excluded)]
    if not static:
        raise ValueError("no static collision geometry")
    report = dict(status="clear_at_samples", method="per-geometry OBB SAT, discrete smoothstep samples",
                  units="m, rad, s", max_dt_s=max_dt, max_joint_step_deg=max_angle_deg,
                  max_linear_joint_step_m=0.002, box_padding_m=margin_m,
                  robot_boxes=sum(map(len, robot.values())),
                  environment_boxes=sum(map(len, machine.values())) + len(camera) + len(fixture) + len(static),
                  excluded=["robot self-collision", "carried products", "machine vs environment",
                            "manual/teach motion", "base_link vs mounting pedestal"],
                  limits=["OBB overlap may be a false positive for non-box geometry",
                          "discrete samples do not prove continuous collision freedom",
                          "report is a snapshot; stage edits require a new preflight"],
                  phases={}, contacts=[])
    seen = set()

    def inspect(phase, t, q, machine_q):
        tf = transfer.arm.model.link_transforms(q)
        moving = [(link, b.moved(transfer.arm.base @ tf[link])) for link, boxes in robot.items() for b in boxes]
        mtf = cell.model.link_transforms(machine_q)
        obstacles = static + [b.moved(cell.root @ mtf[link]) for link, boxes in machine.items() for b in boxes]
        obstacles += [b.moved(cell.root @ cycle.camera(machine_q)) for b in camera]
        obstacles += [b.moved(cell.root @ cycle.product_seat(machine_q)) for b in fixture]
        links = {b.name: link for link, b in moving}
        for a, b in candidate_pairs([b for _, b in moving], obstacles, margin_m):
            if links[a.name] == transfer.arm.model.root and b.name == f"{L.ARM_PATH}_Pedestal":
                continue
            key = (phase, a.name, b.name)
            if key not in seen:
                seen.add(key)
                report["contacts"].append(dict(phase=phase, time_s=float(t), robot=a.name,
                                               obstacle=b.name, joints={k: float(v) for k, v in q.items()},
                                               machine_joints={k: float(v) for k, v in machine_q.items()},
                                               robot_center_m=a.center.tolist(), obstacle_center_m=b.center.tolist()))

    angle = math.radians(max_angle_deg)
    for phase in ("load", "unload"):
        timeline = transfer.phases[phase]["timeline"]
        keys = [(t, dict(q, finger_left=g, finger_right=-g)) for t, q, g in timeline]
        times = sample_times(keys, max_dt, angle, linear_joints=("finger_left", "finger_right"))
        machine_q = cycle.load_pose if phase == "load" else cycle.unload_pose
        for t in times:
            inspect(phase, t, transfer.state(phase, t)[0], machine_q)
        report["phases"][phase] = dict(samples=len(times), duration_s=times[-1])
    times = sample_times(cycle._keys, max_dt, angle, linear_joints=("x_joint", "y_joint", "z_joint"))
    for t in times:
        inspect("inspection_wait", t, transfer.wait_pose(), cycle.pose_at(t))
    report["phases"]["inspection_wait"] = dict(samples=len(times), duration_s=times[-1])
    report["contacts"].sort(key=lambda c: (c["phase"], c["time_s"], c["robot"], c["obstacle"]))
    if report["contacts"]:
        report["status"] = "blocked_potential_collision"
    return report
