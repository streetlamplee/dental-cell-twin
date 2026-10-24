"""Kit startup script (run with kit --exec): record one short clip per part of the line, then quit.
Used by scripts/record_clips.ps1 (which encodes each clip with ffmpeg).

The line runs as in scripts/record_demo.py (crown, vision on, seed 42) and the clips follow one
product (`focus`, default #3 = chip defect) through the line, so they never overlap in time:
  01_line      wide shot, crown ringed: the product rides belt section 1 to the cell entry
  02_load      cell close-up: reBot Arm picks it from the belt and seats it on the platter
  03_inspect   spindle camera: B tilt + C turn, 5 views; inset = the frame the inspector saved
  04_unload    cell close-up: machine parks the camera, robot places it on the outfeed belt
  05_reject    wide shot, crown ringed: the pusher sweeps it into the bin (product-ID based sorting)
  06_teach     teach pendant plays origin + 5 faces (opening the pendant stops the line)
Frames between clips are not captured. One update is 1/60 s of simulation, so every 2nd update
encoded at 30 fps plays at real time.

Settings: --/visiontwin/rec/frames=<dir>  --/visiontwin/rec/focus=3  --/visiontwin/rec/seed=42
"""

import asyncio
import collections
import csv
import os
import traceback

import carb
import carb.settings
import cv2
import omni.kit.app
import omni.usd
from omni.kit.viewport.utility import capture_viewport_to_buffer, get_active_viewport, next_viewport_frame_async
from pxr import Gf, Usd, UsdGeom

TAG = "[clips]"
W, H, STRIDE = 1280, 720, 2
CELL, SPINDLE = 1, 2  # ext.set_view indices (cell close-up, inspection camera)
LINE_CAM = "/World/Factory/RecordLineCamera"  # belt section 1 from the spawn point to the cell
REJECT_CAM = "/World/Factory/RecordRejectCamera"  # outfeed belt, reject line, pusher, bin
SWITCH_SETTLE = 4  # updates skipped after a camera switch (the first frame can still be the old view)
SPINDLE_LEAD_S = 0.15  # spindle camera from this long before the first to after the last view hold
RENDER_LAG = 3  # the captured image shows the stage this many updates before the capture request
                # (moving crown 2.6-2.9 cm behind the ring, centred while it stands still)
REJECT_LEAD_M = 0.6  # reject clip starts when the product is this far before the reject line
REJECT_TAIL_S = 1.2  # and ends this long after it left the belt


async def _wait_for(get, app, frames=3000):
    for _ in range(frames):
        v = get()
        if v:
            return v
        await app.next_update_async()
    raise TimeoutError("startup")


def _look_at(eye, target):
    return Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()


class WideCamera:
    """Fixed wide shot that shows the context (belt, cell, pusher, bin). A real-size crown is ~1 cm,
    a few pixels here, so the recording rings it: its USD position projected with this camera.
    (A camera riding along showed only a plain belt and flew through the pusher; panning from a
    fixed eye still had no context.)"""

    def __init__(self, stage, path, eye, target, focal_mm, h_aperture_mm=20.955):
        self.path = path
        self.cam_to_world = _look_at(eye, target)
        self.world_to_cam = self.cam_to_world.GetInverse()
        self.focal_px = focal_mm / h_aperture_mm * W  # Kit fits the horizontal aperture to the width
        cam = UsdGeom.Camera.Define(stage, path)
        cam.AddTransformOp().Set(self.cam_to_world)
        cam.CreateFocalLengthAttr(focal_mm)
        cam.CreateHorizontalApertureAttr(h_aperture_mm)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100.0))

    def project(self, world):
        p = self.world_to_cam.Transform(Gf.Vec3d(*world))
        if p[2] >= -1e-6:  # behind the camera (it looks down -Z)
            return None
        return (int(W / 2 + self.focal_px * p[0] / -p[2]), int(H / 2 - self.focal_px * p[1] / -p[2]))


def _crown_position(stage, prim_path):
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return None
    return list(UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation())


class Clips:
    """Decides which clip (if any) the current update belongs to."""

    def __init__(self, ext, focus, L):
        self.ext, self.focus, self.L = ext, focus, L
        self.left_belt_t = None  # sim time the focus product left the belt (rejected or sorted)

    def current(self):
        """(clip, camera, caption) or None between clips; 'done' after the reject clip."""
        ext, f = self.ext, self.focus
        if len(ext._sim.tracker.all()) < f:
            return None
        p = ext._sim.tracker.get(f)
        tag = f"Crown #{f} ({p.defect_kind or 'good'})"
        if ext._sim.station_product == f:
            t, cycle = ext._station_time(), ext._cell.cycle
            edge = cycle.timing.hold_s / 2.0 + SPINDLE_LEAD_S
            if t < cycle.timing.load_s:
                return "02_load", CELL, f"{tag}: reBot Arm picks it from the belt (6-DoF IK, top-down grasp)"
            if t < cycle.view_times[0] - edge:
                return "02_load", CELL, f"{tag}: seated on the platter, the machine brings the camera in"
            if t <= cycle.view_times[-1] + edge:
                phase = ext._cell.phase(t)
                what = phase.lower() if phase.startswith("VIEW") else "moving to the next view"
                return "03_inspect", SPINDLE, f"{tag}: spindle camera, {what} (B tilt + C turn)"
            if t < cycle.unload_start:
                return "04_unload", CELL, f"{tag}: the machine parks the camera"
            return "04_unload", CELL, f"{tag}: reBot Arm places it on the outfeed belt"
        if p.x < self.L.CELL_X:
            return "01_line", LINE_CAM, f"{tag} rides the infeed belt (0.5 m/s) to the cell entry"
        if p.state.value in ("SPAWNED", "MOVING", "PROCESSING", "INSPECTED"):
            if p.x < self.L.REJECT_X - REJECT_LEAD_M:
                return None
            verdict = f"{p.prediction} ({p.defect_reason})" if p.defect_reason else str(p.prediction)
            return "05_reject", REJECT_CAM, f"{tag}: vision verdict {verdict} -> sorted by product ID"
        if self.left_belt_t is None:
            self.left_belt_t = ext._sim.time
        if ext._sim.time <= self.left_belt_t + REJECT_TAIL_S:
            route = "pushed into the reject bin" if p.state.value in ("REJECTED", "EXITED") and \
                ext._sorter.decisions.get(f) and ext._sorter.decisions[f].route == "reject" else "passed"
            return "05_reject", REJECT_CAM, f"{tag}: {route}"
        return "done"


def _inspect_inset(ext, focus):
    """Latest frame the inspector saved for the focus product, with its view name and verdict."""
    if ext._log is None:
        return None
    views = ext._cell.cycle.views
    for k in reversed(range(len(views))):
        path = os.path.join(ext._log.frames_dir, f"P_{focus:04d}_v{k}.png")
        if os.path.exists(path):
            img = cv2.imread(path)
            if img is None:
                return None
            h, w = img.shape[:2]  # the crown sits in the middle of the 640x480 frame
            img = img[int(h * 0.32):int(h * 0.68), int(w * 0.32):int(w * 0.68)]
            label = f"saved view {k + 1}/{len(views)} {views[k].name}"
            verdict = _view_verdict(ext, focus, k)
            return img, label + (f": {verdict}" if verdict else "")
    return None


def _view_verdict(ext, focus, k):
    path = os.path.join(ext._log.run_dir, "inspections.csv")
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row["product_id"] == str(focus) and row["view"] == str(k):
                return row["predicted_label"]
    return None


def _overlay(rgb, caption, footer, inset=None, marker=None):
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if img.shape[1] != W or img.shape[0] != H:
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    if inset is not None:
        src, label = inset
        iw = 400
        ih = int(src.shape[0] * iw / src.shape[1])
        x0, y0 = W - iw - 16, H - 36 - ih - 40
        img[y0 - 30:y0 + ih + 4, x0 - 4:x0 + iw + 4] = (24, 24, 26)
        img[y0:y0 + ih, x0:x0 + iw] = cv2.resize(src, (iw, ih), interpolation=cv2.INTER_AREA)
        color = (90, 90, 235) if label.endswith("defect") else (235, 235, 235)
        cv2.putText(img, label, (x0 + 4, y0 - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)
    if marker is not None:
        (mx, my), label = marker
        cv2.circle(img, (mx, my), 22, (40, 210, 255), 2, cv2.LINE_AA)
        cv2.putText(img, label, (mx + 26, my - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (40, 210, 255), 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, 0), (W, 44), (24, 24, 26), -1)
    cv2.putText(img, caption, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.78, (245, 245, 245), 2, cv2.LINE_AA)
    cv2.rectangle(img, (0, H - 36), (W, H), (24, 24, 26), -1)
    cv2.putText(img, footer, (16, H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 210, 210), 1, cv2.LINE_AA)
    return img


class Recorder:
    def __init__(self, viewport, out_dir):
        self.vp, self.out = viewport, out_dir
        self.counts, self.pending = {}, 0

    def grab(self, clip, caption, footer, inset=None, marker=None):
        from visiontwin.factory.frame_provider import capsule_to_rgb

        d = os.path.join(self.out, clip)
        os.makedirs(d, exist_ok=True)
        i = self.counts.get(clip, 0)
        self.counts[clip] = i + 1
        self.pending += 1

        def done(buffer, buffer_size, width, height, fmt):
            try:
                rgb = capsule_to_rgb(buffer, buffer_size, width, height, fmt)
                cv2.imwrite(os.path.join(d, f"{i:05d}.jpg"), _overlay(rgb, caption, footer, inset, marker),
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
            except Exception as exc:
                carb.log_error(f"{TAG} {clip} frame {i}: {exc}")
            finally:
                self.pending -= 1

        capture_viewport_to_buffer(self.vp, done)


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    code = 1
    try:
        import visiontwin.factory.extension as vt
        from visiontwin.factory.core import layout as L

        out = s.get("/visiontwin/rec/frames")
        focus = int(s.get("/visiontwin/rec/focus") or 3)
        ext = await _wait_for(vt.get_instance, app)
        vp = await _wait_for(get_active_viewport, app)
        for key, value in (("part", "crown"), ("vision", True), ("defectRate", 0.3),
                           ("seed", int(s.get("/visiontwin/rec/seed") or 42)), ("maxProducts", focus + 1)):
            s.set(f"/exts/visiontwin.factory/{key}", value)
        await ext.build_scene_async()
        stage = omni.usd.get_context().get_stage()
        crown_path = f"{L.PRODUCTS_PATH}/P_{focus:04d}"
        wide = {LINE_CAM: WideCamera(stage, LINE_CAM, (-2.15, -1.9, 1.6), (-2.0, 0.0, 0.8), 20.0),
                REJECT_CAM: WideCamera(stage, REJECT_CAM, (L.REJECT_X - 0.65, -2.2, 2.0),
                                       (L.REJECT_X - 0.05, -0.35, 0.62), 24.0)}  # down to the bin
        history = collections.deque(maxlen=RENDER_LAG + 1)  # crown positions, oldest first
        vp.resolution_scale = 1.0
        vp.resolution = (W, H)
        await next_viewport_frame_async(vp, 30)
        rec, clips = Recorder(vp, out), Clips(ext, focus, L)
        vp.camera_path = LINE_CAM  # first clip's camera; nothing is captured until the crown spawns
        ext.start()
        current_cam, settle, k = LINE_CAM, 0, 0
        while True:
            history.append(_crown_position(stage, crown_path))
            state = clips.current()
            if state == "done" or ext.run_complete:
                break
            if state is not None:
                clip, cam, caption = state
                if cam != current_cam:
                    if isinstance(cam, str):
                        vp.camera_path = cam
                    else:
                        ext.set_view(cam)
                    current_cam, settle = cam, SWITCH_SETTLE
                if settle > 0:
                    settle -= 1
                elif k % STRIDE == 0:
                    footer = f"sim {ext._sim.time:5.1f}s | cell: {ext._cell_status()}"
                    pos = history[0] if cam in wide else None
                    xy = wide[cam].project(pos) if pos is not None else None
                    rec.grab(clip, caption, footer, _inspect_inset(ext, focus) if clip == "03_inspect" else None,
                             (xy, f"#{focus}") if xy is not None else None)
            k += 1
            await app.next_update_async()
        print(f"{TAG} line clips done at sim {ext._sim.time:.1f}s")
        pendant = ext.open_teach_pendant()
        if pendant is None:
            raise RuntimeError("teach pendant did not open")
        pendant.generate()
        await next_viewport_frame_async(vp, 10)  # 4 updates still showed the previous camera
        pendant.play()
        k = 0
        while pendant.playing:
            if k % STRIDE == 0:
                point = pendant._status.text.replace("playing: ", "")
                rec.grab("06_teach", f"Surface teaching: {point}, tool normal to the face at 20 mm",
                         "origin + top + 4 sides of the block on the C platter (B -90 for the sides)")
            k += 1
            await app.next_update_async()
        for _ in range(600):
            if rec.pending == 0:
                break
            await app.next_update_async()
        print(f"{TAG} " + ", ".join(f"{c}={n}" for c, n in sorted(rec.counts.items())) + f" -> {out}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
