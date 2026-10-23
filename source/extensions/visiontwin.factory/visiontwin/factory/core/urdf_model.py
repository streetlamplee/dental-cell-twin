"""Minimal URDF reader (pure Python + numpy): links, box/cylinder visuals, joints.

Covers what reference/teeth_mill.urdf (box/cylinder) and the Seeed reBot Arm URDF (mesh
visuals, file path relative to the URDF) use. Inertia and collisions are not read. Transforms are 4x4 numpy arrays (meters, URDF frames).

URDF conventions: origin rpy is fixed-axis roll-pitch-yaw, R = Rz(yaw) Ry(pitch) Rx(roll);
a cylinder's axis is its local Z.
"""

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

MOVABLE = ("prismatic", "revolute", "continuous")


def rpy_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    cr, sr, cp, sp, cy, sy = (math.cos(roll), math.sin(roll), math.cos(pitch),
                              math.sin(pitch), math.cos(yaw), math.sin(yaw))
    return np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp, cp * sr, cp * cr],
    ])


def transform(xyz=(0.0, 0.0, 0.0), rpy=(0.0, 0.0, 0.0)) -> np.ndarray:
    t = np.eye(4)
    t[:3, :3] = rpy_matrix(*rpy)
    t[:3, 3] = xyz
    return t


def _floats(text: Optional[str], n: int, default=0.0) -> Tuple[float, ...]:
    if not text:
        return (default,) * n
    vals = tuple(float(v) for v in text.split())
    if len(vals) != n:
        raise ValueError(f"expected {n} numbers, got {text!r}")
    return vals


def _origin(elem) -> np.ndarray:
    o = elem.find("origin") if elem is not None else None
    if o is None:
        return np.eye(4)
    return transform(_floats(o.get("xyz"), 3), _floats(o.get("rpy"), 3))


@dataclass
class Visual:
    name: str
    shape: str  # "box", "cylinder" or "mesh"
    size: Tuple[float, ...]  # box: (x, y, z); cylinder: (radius, length); mesh: scale (x, y, z)
    origin: np.ndarray  # link frame -> visual frame
    rgba: Tuple[float, float, float, float]
    material: str
    mesh: Optional[str] = None  # mesh file name as written in the URDF


@dataclass
class Link:
    name: str
    visuals: List[Visual] = field(default_factory=list)


@dataclass
class Joint:
    name: str
    type: str
    parent: str
    child: str
    origin: np.ndarray  # parent link frame -> joint/child frame at joint value 0
    axis: Tuple[float, float, float]
    lower: Optional[float]
    upper: Optional[float]

    @property
    def movable(self) -> bool:
        return self.type in MOVABLE


@dataclass
class UrdfModel:
    name: str
    links: Dict[str, Link]
    joints: Dict[str, Joint]

    @property
    def root(self) -> str:
        children = {j.child for j in self.joints.values()}
        roots = [n for n in self.links if n not in children]
        if len(roots) != 1:
            raise ValueError(f"expected one root link, got {roots}")
        return roots[0]

    def parent_joint(self, link: str) -> Optional[Joint]:
        return next((j for j in self.joints.values() if j.child == link), None)

    def link_transforms(self, q: Optional[Dict[str, float]] = None) -> Dict[str, np.ndarray]:
        """World (root) transform of every link for joint values q (default: home = 0)."""
        q = q or {}
        out = {self.root: np.eye(4)}
        pending = [j for j in self.joints.values()]
        while pending:
            progressed = False
            for j in list(pending):
                if j.parent not in out:
                    continue
                motion = np.eye(4)
                v = q.get(j.name, 0.0)
                axis = np.array(j.axis, dtype=float)
                if j.type == "prismatic":
                    motion[:3, 3] = axis * v
                elif j.type in ("revolute", "continuous") and v:
                    motion[:3, :3] = _axis_angle(axis, v)
                out[j.child] = out[j.parent] @ j.origin @ motion
                pending.remove(j)
                progressed = True
            if not progressed:
                raise ValueError(f"disconnected joints: {[j.name for j in pending]}")
        return out

    def visuals(self):
        """(link_name, Visual) pairs in document order."""
        for link in self.links.values():
            for v in link.visuals:
                yield link.name, v

    def kinematics(self) -> dict:
        """JSON-serialisable joint description (the source of truth for joints after STEP)."""
        return {
            "robot": self.name,
            "units": {"length": "m", "angle": "rad"},
            "root": self.root,
            "joints": [{
                "name": j.name, "type": j.type, "parent": j.parent, "child": j.child,
                "origin_xyz": [round(float(x), 9) for x in j.origin[:3, 3]],
                "origin_rotation": [[round(float(x), 9) for x in row] for row in j.origin[:3, :3]],
                "axis": list(j.axis), "lower": j.lower, "upper": j.upper,
            } for j in self.joints.values()],
        }


def _axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    a = axis / np.linalg.norm(axis)
    k = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(angle) * k + (1 - math.cos(angle)) * (k @ k)


def model_from_kinematics(kin: dict) -> UrdfModel:
    """Rebuild a joints-only model from kinematics.json (written by urdf_to_step.py), so
    joint motion can be computed without the URDF once the geometry came through STEP."""
    joints: Dict[str, Joint] = {}
    links: Dict[str, Link] = {kin["root"]: Link(kin["root"])}
    for j in kin["joints"]:
        origin = np.eye(4)
        origin[:3, :3] = np.array(j["origin_rotation"], dtype=float)
        origin[:3, 3] = j["origin_xyz"]
        joints[j["name"]] = Joint(j["name"], j["type"], j["parent"], j["child"], origin,
                                  tuple(j["axis"]), j["lower"], j["upper"])
        links.setdefault(j["parent"], Link(j["parent"]))
        links.setdefault(j["child"], Link(j["child"]))
    return UrdfModel(kin["robot"], links, joints)


def load_urdf(path: str) -> UrdfModel:
    root = ET.parse(path).getroot()
    colors = {}
    for m in root.findall("material"):
        c = m.find("color")
        if c is not None:
            colors[m.get("name")] = _floats(c.get("rgba"), 4, 1.0)

    links: Dict[str, Link] = {}
    for le in root.findall("link"):
        link = Link(le.get("name"))
        for i, ve in enumerate(le.findall("visual")):
            geo = ve.find("geometry")
            box, cyl, mesh = geo.find("box"), geo.find("cylinder"), geo.find("mesh")
            mesh_file = None
            if box is not None:
                shape, size = "box", _floats(box.get("size"), 3)
            elif cyl is not None:
                shape, size = "cylinder", (float(cyl.get("radius")), float(cyl.get("length")))
            elif mesh is not None:
                shape, size, mesh_file = "mesh", _floats(mesh.get("scale"), 3, 1.0), mesh.get("filename")
            else:
                raise ValueError(f"link {link.name}: only box/cylinder/mesh visuals are supported")
            mat = ve.find("material")
            mat_name = mat.get("name") if mat is not None else ""
            rgba = colors.get(mat_name, (0.7, 0.7, 0.7, 1.0))
            link.visuals.append(Visual(ve.get("name") or f"{link.name}_visual{i}", shape, size,
                                       _origin(ve), rgba, mat_name, mesh_file))
        links[link.name] = link

    joints: Dict[str, Joint] = {}
    for je in root.findall("joint"):
        lim = je.find("limit")
        ax = je.find("axis")
        joints[je.get("name")] = Joint(
            name=je.get("name"), type=je.get("type"),
            parent=je.find("parent").get("link"), child=je.find("child").get("link"),
            origin=_origin(je), axis=_floats(ax.get("xyz") if ax is not None else "1 0 0", 3),
            lower=float(lim.get("lower")) if lim is not None and lim.get("lower") else None,
            upper=float(lim.get("upper")) if lim is not None and lim.get("upper") else None,
        )
    return UrdfModel(root.get("name"), links, joints)
