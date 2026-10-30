"""Offline collision preflight using composed USD assets, without Kit or a GPU.

Run with .venv-cad/Scripts/python.exe. Exit 0: no overlap at samples;
2: potential collision (report written); 1: missing assets/invalid geometry/error.
Does not modify the source assets. Reports are written into --out.
"""

import argparse
from datetime import datetime
import hashlib
import importlib
import json
from pathlib import Path
import sys
import types

import numpy as np
from pxr import Usd

ROOT = Path(__file__).resolve().parents[1]
# Load the USD-only adapters without executing the Kit extension's __init__.
package = types.ModuleType("_collision_factory")
package.__path__ = [str(ROOT / "source/extensions/visiontwin.factory/visiontwin/factory")]
sys.modules[package.__name__] = package
scene = importlib.import_module("_collision_factory.scene_manager")
cell_module = importlib.import_module("_collision_factory.inspection_cell")
robot_module = importlib.import_module("_collision_factory.robot_arm")
collision = importlib.import_module("_collision_factory.collision_check")
catalog_module = importlib.import_module("_collision_factory.core.product_catalog")
L = importlib.import_module("_collision_factory.core.layout")


def build_scene():
    spec = catalog_module.ProductCatalog("crown", str(ROOT / "assets/parts")).cell
    robot_asset = ROOT / f"assets/robots/usd/{spec.transfer}.usd"
    kin = robot_asset.with_suffix(".kinematics.json")
    machine_asset = ROOT / "assets/cad/teeth_mill.usd"
    machine_kin = machine_asset.with_suffix(".kinematics.json")
    for path in (robot_asset, kin, machine_asset, machine_kin):
        if not path.is_file():
            raise FileNotFoundError(f"collision asset missing: {path}")
    stage = Usd.Stage.CreateInMemory()
    scene.build_factory_scene(stage, layout=scene.CELL)
    cycle = cell_module.build_cycle(str(machine_kin), spec)
    cell = cell_module.InspectionCell(stage, str(machine_asset), str(machine_kin), spec, cycle)

    def belt_pose(x):
        pose = np.eye(4)
        pose[:3, 3] = (x, 0, L.CONVEYOR_TOP_Z + scene.PART_REST_DZ)
        return pose

    transfer = robot_module.build_transfer(str(kin), belt_pose(L.CELL_ENTRY_X), cell.seat_pose(),
                                          belt_pose(L.CELL_EXIT_X), cycle.timing.load_s, cycle.timing.unload_s)
    arm = robot_module.RobotArm(stage, str(robot_asset), transfer)
    return stage, arm, cell


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "results/collision" / datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--max-dt", type=float, default=1 / 120)
    parser.add_argument("--max-angle-deg", type=float, default=1.0)
    parser.add_argument("--margin-mm", type=float, default=0.0)
    args = parser.parse_args()
    stage, arm, cell = build_scene()
    report = collision.check_cell(stage, arm, cell, args.max_dt, args.max_angle_deg, args.margin_mm / 1000)
    report["usd_version"] = list(Usd.GetVersion())
    sources = [ROOT / "assets/cad/teeth_mill.usd", ROOT / "assets/cad/teeth_mill.kinematics.json",
               ROOT / "assets/robots/usd/rebot_b601_dm.usd", ROOT / "assets/robots/usd/rebot_b601_dm.kinematics.json",
               ROOT / "assets/parts/catalog.json"]
    factory = Path(package.__path__[0])
    sources += [factory / name for name in ("collision_check.py", "core/collision.py", "core/arm_transfer.py",
                                             "core/cell_cycle.py", "core/layout.py")]
    report["source_sha256"] = {str(path.relative_to(ROOT)).replace("\\", "/"):
                               hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Robot collision preflight", "", f"Status: {report['status']}",
             "", "Conservative geometry boxes; discrete sampling, not continuous/mesh collision proof.",
             "", f"Robot boxes: {report['robot_boxes']}; environment boxes: {report['environment_boxes']}",
             f"Max time step: {args.max_dt}s; max angular step: {args.max_angle_deg} deg; box padding: {args.margin_mm} mm.",
             "", "| Phase | Samples |", "|---|---|"]
    lines += [f"| {phase} | {data['samples']} |" for phase, data in report["phases"].items()]
    lines += ["", "## First overlap per pair and phase", "", "| Phase | Time (s) | Robot | Obstacle |", "|---|---|---|---|"]
    lines += [f"| {c['phase']} | {c['time_s']:.6f} | {c['robot']} | {c['obstacle']} |" for c in report["contacts"]]
    lines += ["", "Excluded: " + "; ".join(report["excluded"]), "", *report["limits"]]
    (args.out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{report['status']}: {len(report['contacts'])} potential pairs; report: {args.out / 'report.json'}")
    return 2 if report["contacts"] else 0


if __name__ == "__main__":
    sys.exit(main())
