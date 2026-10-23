"""Kit startup script (run with kit --exec): render a robot USD (from urdf_mesh_to_usd) at a
joint pose, driven by forward kinematics from its kinematics.json, then quit.
Used by scripts/render_robot_pose.ps1.

Settings: --/visiontwin/robot/usd=<usd>  --/visiontwin/robot/pose="joint1=0.5,joint2=-1.2"
          --/visiontwin/robot/out=<png>
"""

import asyncio
import json
import os
import sys
import traceback

import carb
import carb.settings
import numpy as np
import omni.kit.actions.core
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_file, get_active_viewport, next_viewport_frame_async
from pxr import Gf, Usd, UsdGeom, UsdLux

TAG = "[render_robot]"
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "source/extensions/visiontwin.factory/visiontwin/factory"))

from core.urdf_model import model_from_kinematics  # noqa: E402


def gf(m):
    return Gf.Matrix4d(np.asarray(m, dtype=float).T.tolist())


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    usd, out = s.get("/visiontwin/robot/usd"), s.get("/visiontwin/robot/out")
    pose = dict((k.strip(), float(v)) for k, v in (p.split("=") for p in (s.get("/visiontwin/robot/pose") or "").split(",") if p))
    code = 1
    try:
        ctx = omni.usd.get_context()
        await ctx.new_stage_async()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        kin = json.load(open(os.path.splitext(usd)[0] + ".kinematics.json", encoding="utf-8"))
        model = model_from_kinematics(kin)
        robot = UsdGeom.Xform.Define(stage, "/World/Robot")
        robot.GetPrim().GetReferences().AddReference(usd)
        tf = model.link_transforms(pose)
        for link, m in tf.items():
            prim = stage.GetPrimAtPath(f"/World/Robot/{link}")
            if prim:
                x = UsdGeom.Xformable(prim)
                x.ClearXformOpOrder()
                x.AddTransformOp(opSuffix="joint").Set(gf(m))
        UsdGeom.Cube.Define(stage, "/World/Floor").GetSizeAttr().Set(1.0)
        UsdGeom.XformCommonAPI(stage.GetPrimAtPath("/World/Floor")).SetScale(Gf.Vec3f(2, 2, 0.01))
        UsdGeom.XformCommonAPI(stage.GetPrimAtPath("/World/Floor")).SetTranslate(Gf.Vec3d(0, 0, -0.006))
        UsdLux.DistantLight.Define(stage, "/World/Key").CreateIntensityAttr(2500)
        UsdLux.DomeLight.Define(stage, "/World/Dome").CreateIntensityAttr(600)
        cam = UsdGeom.Camera.Define(stage, "/World/Cam")
        eye, target = Gf.Vec3d(0.55, -0.75, 0.5), Gf.Vec3d(0.12, 0.0, 0.18)
        cam.AddTransformOp().Set(Gf.Matrix4d().SetLookAt(eye, target, Gf.Vec3d(0, 0, 1)).GetInverse())
        cam.CreateFocalLengthAttr(24.0)
        try:  # stage lights only (the viewport's auto rig would add its own lights)
            omni.kit.actions.core.execute_action("omni.kit.viewport.menubar.lighting", "set_lighting_mode_stage")
        except Exception:
            pass
        vp = None
        for _ in range(600):
            vp = get_active_viewport()
            if vp:
                break
            await app.next_update_async()
        vp.camera_path = "/World/Cam"
        await next_viewport_frame_async(vp, 90)
        result = await capture_viewport_to_file(vp, out).wait_for_result(completion_frames=60)
        ee = tf.get("end_link")
        print(f"{TAG} pose={pose} end_link at {np.round(ee[:3, 3], 4).tolist() if ee is not None else '?'} "
              f"capture={result} -> {out}")
        code = 0 if result else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
