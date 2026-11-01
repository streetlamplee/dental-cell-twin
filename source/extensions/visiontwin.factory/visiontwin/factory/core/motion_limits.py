"""Analytical joint rate audit for the runtime's cubic smoothstep segments.

No retiming or motor dynamics: missing limits remain unverified. Acceleration
peaks are one-sided endpoint values; acceleration jumps imply unbounded jerk.
"""

import math
import xml.etree.ElementTree as ET


def retime_duration(before, after, minimum_s, velocity_limits, acceleration_limits=None):
    """Lengthen a smoothstep segment; never shorten it or invent unknown limits."""
    if not math.isfinite(minimum_s) or minimum_s <= 0:
        raise ValueError("minimum duration must be finite and positive")
    if set(before) != set(after) or not all(math.isfinite(v) for v in (*before.values(), *after.values())):
        raise ValueError("segment joint values must be finite and have matching names")
    duration = minimum_s
    for field, limits in (("velocity", velocity_limits), ("acceleration", acceleration_limits or {})):
        for joint, limit in limits.items():
            if joint not in before or not math.isfinite(limit) or limit <= 0:
                raise ValueError(f"invalid {field} constraint: {joint}")
            delta = abs(after[joint] - before[joint])
            required = 1.5 * delta / limit if field == "velocity" else math.sqrt(6 * delta / limit)
            duration = max(duration, required)
    return duration


def urdf_rate_limits(path):
    """Read declared SI velocity/acceleration limits without inventing defaults."""
    limits = {}
    for joint in ET.parse(path).getroot().findall("joint"):
        kind = joint.get("type")
        if kind not in ("revolute", "continuous", "prismatic"):
            continue
        element = joint.find("limit")
        values = {}
        for field in ("velocity", "acceleration"):
            raw = element.get(field) if element is not None else None
            value = float(raw) if raw is not None else None
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"invalid {field} limit: {joint.get('name')}")
            values[field] = value
        limits[joint.get("name")] = dict(type=kind, **values)
    return limits


def audit_boundary(before, after, limits, tolerance=1e-9):
    """Classify an instantaneous state reset separately from smooth segments.

    A whole-turn wrap is equivalent only for continuous joints. A real position
    jump has no finite continuous-time velocity/acceleration bound.
    """
    if set(before) != set(after) or not set(before) <= set(limits):
        raise ValueError("boundary joint definitions differ")
    rows = {}
    for joint in sorted(before):
        delta = after[joint] - before[joint]
        if not math.isfinite(delta):
            raise ValueError("boundary values must be finite")
        physical_delta = math.remainder(delta, 2 * math.pi) if limits[joint]["type"] == "continuous" else delta
        status = "position_jump" if abs(physical_delta) > tolerance else "continuous_angle_wrap" if abs(delta) > tolerance else "continuous"
        rows[joint] = dict(delta=delta, physical_delta=physical_delta, status=status)
    return dict(status="discontinuous" if any(r["status"] == "position_jump" for r in rows.values()) else "continuous",
                joints=rows, note="Position jumps cannot be assigned finite continuous-time rate bounds")


def audit_smoothstep(keys, limits):
    """Compute exact peak rates for each segment and compare declared limits.

    q(u)=q0+dq*(3u^2-2u^3); |v|max=1.5*|dq|/T at u=.5;
    |a|max=6*|dq|/T^2 at u=0+/1-. Angles are not wrapped: runtime
    interpolates raw joint values, including continuous joints.
    """
    if len(keys) < 2:
        raise ValueError("at least two keyframes required")
    joints = set(keys[0][1])
    if not joints or any(set(q) != joints for _, q in keys):
        raise ValueError("all keyframes must contain the same nonempty joint set")
    for t, q in keys:
        if not math.isfinite(t) or not all(math.isfinite(v) for v in q.values()):
            raise ValueError("keyframes must be finite")
    if not joints <= set(limits):
        raise ValueError(f"joint definitions missing: {sorted(joints - set(limits))}")
    for name in joints:
        if limits[name]["type"] not in ("prismatic", "revolute", "continuous"):
            raise ValueError(f"unsupported joint type: {name}")
        for field in ("velocity", "acceleration"):
            value = limits[name].get(field)
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"invalid {field} limit: {name}")
    segments, summaries = [], {}
    for index, ((t0, q0), (t1, q1)) in enumerate(zip(keys, keys[1:])):
        duration = t1 - t0
        if duration <= 0:
            raise ValueError("keyframe times must strictly increase")
        rows = {}
        for joint in sorted(joints):
            delta = q1[joint] - q0[joint]
            velocity, acceleration = 1.5 * abs(delta) / duration, 6 * abs(delta) / duration ** 2
            definition = limits[joint]
            vl, al = definition.get("velocity"), definition.get("acceleration")
            vr, ar = velocity / vl if vl is not None else None, acceleration / al if al is not None else None
            required = max(1.5 * abs(delta) / vl if vl is not None else 0,
                           math.sqrt(6 * abs(delta) / al) if al is not None else 0)
            row = dict(delta=delta, peak_velocity=velocity, peak_acceleration=acceleration,
                       velocity_limit=vl, acceleration_limit=al,
                       velocity_ratio=vr, acceleration_ratio=ar,
                       velocity_status="unverified" if vr is None else "exceeded" if vr > 1 + 1e-9 else "within",
                       acceleration_status="unverified" if ar is None else "exceeded" if ar > 1 + 1e-9 else "within",
                       min_duration_known_limits_s=required,
                       velocity_peak_time_s=(t0 + t1) / 2,
                       acceleration_peak_endpoint_times_s=[t0, t1])
            rows[joint] = row
            summary = summaries.setdefault(joint, dict(type=definition["type"],
                units="m/s, m/s^2" if definition["type"] == "prismatic" else "rad/s, rad/s^2",
                velocity_limit=vl, acceleration_limit=al, peak_velocity=-1, peak_acceleration=-1,
                velocity_status="unverified" if vl is None else "within",
                acceleration_status="unverified" if al is None else "within"))
            for metric in ("velocity", "acceleration"):
                if row[f"peak_{metric}"] > summary[f"peak_{metric}"]:
                    summary[f"peak_{metric}"] = row[f"peak_{metric}"]
                    summary[f"{metric}_peak_segment"] = index
                if row[f"{metric}_status"] == "exceeded":
                    summary[f"{metric}_status"] = "exceeded"
        segments.append(dict(index=index, start_s=t0, end_s=t1, duration_s=duration, joints=rows,
                             min_duration_known_limits_s=max(r["min_duration_known_limits_s"] for r in rows.values())))
    statuses = [s[f"{metric}_status"] for s in summaries.values() for metric in ("velocity", "acceleration")]
    return dict(status="exceeded" if "exceeded" in statuses else "incomplete" if "unverified" in statuses else "within",
                duration_s=keys[-1][0] - keys[0][0], joints=summaries, segments=segments,
                limitations=["Declared URDF limits are not independently verified hardware specifications",
                             "Missing limits are unverified, not passing",
                             "Cubic smoothstep has acceleration jumps and unbounded ideal jerk at joins",
                             "No payload, torque, tracking error or real controller dynamics considered",
                             "Minimum duration uses known limits only and is not an approved retiming"])
