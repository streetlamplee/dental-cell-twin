"""USD adapter and actual-asset preflight; also runnable via CAD Python + unittest.

    .venv-cad/Scripts/python.exe -m unittest discover -s tests -p test_collision_usd.py -v

System-Python core CI skips this file when usd-core is unavailable.
"""

import importlib.util
from pathlib import Path
import sys
import unittest

import numpy as np

HAS_USD = importlib.util.find_spec("pxr") is not None
ROOT = Path(__file__).resolve().parents[1]
if HAS_USD:
    from pxr import Gf, Usd, UsdGeom

    spec = importlib.util.spec_from_file_location("collision_runner", ROOT / "scripts/check_collisions.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    from _collision_factory.core.collision import CollisionBlocked, require_clear


@unittest.skipUnless(HAS_USD, "requires usd-core in CAD Python")
class GeometryBoundsTests(unittest.TestCase):
    def test_composed_millimetre_scale_rotation_and_relative_frame(self):
        stage = Usd.Stage.CreateInMemory()
        parent = UsdGeom.Xform.Define(stage, "/Asset")
        xf = UsdGeom.XformCommonAPI(parent)
        xf.SetTranslate(Gf.Vec3d(1, 2, 3))
        xf.SetRotate(Gf.Vec3f(0, 0, 90))
        xf.SetScale(Gf.Vec3f(0.001, 0.001, 0.001))
        cube = UsdGeom.Cube.Define(stage, "/Asset/Link/Cube")
        cube.CreateSizeAttr(20)
        UsdGeom.XformCommonAPI(cube).SetTranslate(Gf.Vec3d(100, 0, 0))
        frame = np.eye(4)
        frame[:3, 3] = (1, 2, 3)
        boxes = runner.collision.geometry_boxes(stage, "/Asset/Link", frame)
        self.assertEqual(len(boxes), 1)
        box = boxes[0]
        np.testing.assert_allclose(box.center, (0, 0.1, 0), atol=1e-7)
        np.testing.assert_allclose(box.half, (0.01, 0.01, 0.01), atol=1e-7)
        world = box.moved(frame)
        actual = UsdGeom.BBoxCache(0, [UsdGeom.Tokens.default_]).ComputeWorldBound(cube.GetPrim()).ComputeAlignedRange()
        low, high = world.aabb()
        np.testing.assert_allclose(low, actual.GetMin(), atol=1e-7)
        np.testing.assert_allclose(high, actual.GetMax(), atol=1e-7)

    def test_hidden_and_inactive_geometry_is_excluded(self):
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/Root")
        UsdGeom.Cube.Define(stage, "/Root/Visible")
        UsdGeom.Cube.Define(stage, "/Root/Hidden").MakeInvisible()
        UsdGeom.Cube.Define(stage, "/Root/Inactive").GetPrim().SetActive(False)
        boxes = runner.collision.geometry_boxes(stage, "/Root")
        self.assertEqual([b.name for b in boxes], ["/Root/Visible"])

    def test_instance_proxy_mesh_is_not_lost(self):
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/Asset")
        UsdGeom.Cube.Define(stage, "/Asset/Cube")
        instance = UsdGeom.Xform.Define(stage, "/Instance").GetPrim()
        instance.GetReferences().AddInternalReference("/Asset")
        instance.SetInstanceable(True)
        boxes = runner.collision.geometry_boxes(stage, "/Instance")
        self.assertEqual([b.name for b in boxes], ["/Instance/Cube"])

    def test_empty_geometry_cannot_pass_as_clear(self):
        stage = Usd.Stage.CreateInMemory()
        UsdGeom.Xform.Define(stage, "/Empty")
        with self.assertRaisesRegex(ValueError, "no visible collision geometry"):
            runner.collision.geometry_boxes(stage, "/Empty")


@unittest.skipUnless(HAS_USD and (ROOT / "assets/robots/usd/rebot_b601_dm.usd").exists(),
                     "requires CAD Python and fetched robot USD")
class ActualCellTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stage, cls.arm, cls.cell = runner.build_scene()

    def test_actual_cell_and_inserted_obstacle(self):
        # One test keeps the baseline and injected obstacle on exactly the same composed stage.
        before = self.stage.GetRootLayer().ExportToString()
        report = runner.collision.check_cell(self.stage, self.arm, self.cell)
        self.assertEqual(report["status"], "clear_at_samples")
        self.assertGreater(report["robot_boxes"], 10)
        self.assertGreater(report["environment_boxes"], 10)
        self.assertEqual(before, self.stage.GetRootLayer().ExportToString(), "preflight must not move the scene")
        require_clear(report)

        q, _, _ = self.arm.transfer.state("load", 0.5)
        tool = self.arm.transfer.arm.tool(q)
        obstacle = "/World/Factory/InjectedObstacle"
        runner.scene._box(self.stage, obstacle, tuple(tool[:3, 3]), (0.06, 0.06, 0.06), (1, 0, 0))
        try:
            blocked = runner.collision.check_cell(self.stage, self.arm, self.cell)
            self.assertEqual(blocked["status"], "blocked_potential_collision")
            self.assertTrue(any(c["obstacle"] == obstacle and c["phase"] == "load" for c in blocked["contacts"]))
            with self.assertRaises(CollisionBlocked):
                require_clear(blocked)
        finally:
            self.stage.RemovePrim(obstacle)


if __name__ == "__main__":
    unittest.main()
