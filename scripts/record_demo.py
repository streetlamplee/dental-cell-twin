"""Kit startup script (run with kit --exec): record the demo as video frames, then quit.
Used by scripts/record_demo.ps1 (which encodes the frames with ffmpeg).

Same flow as scripts/run_demo.py (crown line with vision on, automatic views, teaching
playback), but every `stride`-th update the main viewport is captured at a fixed 1280x720 and
written as JPEG with an English caption and live counters. One update is 1/60 s of simulation
(fixed step, synchronous rendering), so stride 2 encoded at 30 fps plays at real time.
At the end, result stills are appended.

Settings: --/visiontwin/rec/frames=<dir>  --/visiontwin/rec/products=4  --/visiontwin/rec/seed=42
          --/visiontwin/rec/stride=2  --/visiontwin/rec/stills=<png;png>
"""

import asyncio
import os
import traceback

import carb
import carb.settings
import cv2
import numpy as np
import omni.kit.app
from omni.kit.viewport.utility import capture_viewport_to_buffer, get_active_viewport, next_viewport_frame_async

TAG = "[record]"
W, H, FPS = 1280, 720, 30
OVERVIEW, CELL, SPINDLE = 0, 1, 2
SWITCH_SETTLE = 4  # updates skipped after a camera switch (a 1-update wait still showed a stale frame)
SPINDLE_LEAD_S = 0.15  # spindle camera shown this long before the first / after the last view hold


async def _wait_for(get, app, frames=3000):
    for _ in range(frames):
        v = get()
        if v:
            return v
        await app.next_update_async()
    raise TimeoutError("startup")


def _state(ext):
    """(view, caption) for the current simulation state."""
    t = ext._station_time()
    if ext._cell is None or t is None:
        return OVERVIEW, "Line: conveyor -> inspection cell (5-axis machine) -> reject pusher"
    phase = ext._cell.phase(t)
    if phase == "LOADING":
        return CELL, "Seeed reBot Arm loads the crown: 6-DoF IK, top-down grasp"
    if phase == "UNLOADING":
        return CELL, "Seeed reBot Arm unloads onto the outfeed belt"
    if phase.startswith("VIEW"):
        return SPINDLE, f"Camera on the spindle: {phase.lower()} (B tilt + C turn)"
    # the spindle camera only sees the machine body while it comes in from / goes back to park
    cycle = ext._cell.cycle
    edge = cycle.timing.hold_s / 2.0 + SPINDLE_LEAD_S
    if t < cycle.view_times[0] - edge:
        return CELL, "Machine brings the camera over the crown"
    if t > cycle.view_times[-1] + edge:
        return CELL, "Machine parks the camera for unloading"
    return SPINDLE, "Machine moves the camera to the next view"


def _counters(ext) -> str:
    d = ext._sorter.decisions.values()
    ok = sum(1 for x in d if ext._sorter.route_correct(ext._sim.tracker.get(x.product_id).ground_truth, x.route))
    rej = sum(1 for x in d if x.route == "reject")
    return (f"sim {ext._sim.time:5.1f}s | spawned {len(ext._sim.tracker.all())} | sorted {ok}/{len(d)} correct | "
            f"rejected {rej} | cell: {ext._cell_status()}")


def _overlay(rgb, caption, counters):
    img = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if img.shape[1] != W or img.shape[0] != H:
        img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA)
    cv2.rectangle(img, (0, 0), (W, 44), (24, 24, 26), -1)
    cv2.putText(img, caption, (16, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (245, 245, 245), 2, cv2.LINE_AA)
    if counters:
        cv2.rectangle(img, (0, H - 36), (W, H), (24, 24, 26), -1)
        cv2.putText(img, counters, (16, H - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (210, 210, 210), 1, cv2.LINE_AA)
    return img


def _still(path, caption):
    src = cv2.imread(path)
    canvas = np.full((H, W, 3), 251, np.uint8)
    if src is not None:
        k = min(W / src.shape[1], (H - 60) / src.shape[0])
        src = cv2.resize(src, (int(src.shape[1] * k), int(src.shape[0] * k)), interpolation=cv2.INTER_AREA)
        y, x = 50 + (H - 50 - src.shape[0]) // 2, (W - src.shape[1]) // 2
        canvas[y:y + src.shape[0], x:x + src.shape[1]] = src
    cv2.putText(canvas, caption, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (30, 30, 30), 2, cv2.LINE_AA)
    return canvas


class Recorder:
    def __init__(self, viewport, out_dir):
        self.vp, self.out = viewport, out_dir
        self.index, self.pending = 0, 0
        os.makedirs(out_dir, exist_ok=True)

    def grab(self, caption, counters):
        i = self.index
        self.index += 1
        self.pending += 1

        def done(buffer, buffer_size, width, height, fmt):
            try:
                from visiontwin.factory.frame_provider import capsule_to_rgb

                rgb = capsule_to_rgb(buffer, buffer_size, width, height, fmt)
                cv2.imwrite(os.path.join(self.out, f"{i:05d}.jpg"), _overlay(rgb, caption, counters),
                            [cv2.IMWRITE_JPEG_QUALITY, 92])
            except Exception as exc:
                carb.log_error(f"{TAG} frame {i}: {exc}")
            finally:
                self.pending -= 1

        capture_viewport_to_buffer(self.vp, done)

    def add_frames(self, img, count):
        for _ in range(count):
            cv2.imwrite(os.path.join(self.out, f"{self.index:05d}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 92])
            self.index += 1


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    code = 1
    try:
        import visiontwin.factory.extension as vt

        out = s.get("/visiontwin/rec/frames")
        stride = int(s.get("/visiontwin/rec/stride") or 2)
        ext = await _wait_for(vt.get_instance, app)
        vp = await _wait_for(get_active_viewport, app)
        for key, value in (("part", "crown"), ("vision", True), ("defectRate", 0.3),
                           ("seed", int(s.get("/visiontwin/rec/seed") or 42)),
                           ("maxProducts", int(s.get("/visiontwin/rec/products") or 4))):
            s.set(f"/exts/visiontwin.factory/{key}", value)
        await ext.build_scene_async()
        vp.resolution_scale = 1.0
        vp.resolution = (W, H)
        ext.set_view(OVERVIEW)
        await next_viewport_frame_async(vp, 60)
        rec = Recorder(vp, out)
        intro = "Dental machining cell digital twin - Omniverse Kit, URDF/STEP -> USD"
        for k in range(120):  # 2 s of overview before the line starts
            if k % stride == 0:
                rec.grab(intro, "")
            await app.next_update_async()
        ext.start()
        current, k, settle = OVERVIEW, 0, 0
        while not ext.run_complete:
            view, caption = _state(ext)
            if view != current:
                ext.set_view(view)
                current, settle = view, SWITCH_SETTLE
            if settle > 0:  # the first frames after a camera switch are not the new view yet
                settle -= 1
            elif k % stride == 0:
                rec.grab(caption, _counters(ext))
            k += 1
            await app.next_update_async()
        ext.set_view(OVERVIEW)
        final = f"Line finished: {ext.summary['sort_correct']}/{ext.summary['sorted']} sorted correctly"
        for k in range(90):
            if k % stride == 0:
                rec.grab(final, _counters(ext))
            await app.next_update_async()
        pendant = ext.open_teach_pendant()
        if pendant is not None:
            pendant.generate()
            pendant.play()
            k = 0
            while pendant.playing:
                if k % stride == 0:
                    rec.grab("Surface teaching (from a real dental mill exercise): "
                             + pendant._status.text.replace("playing: ", "") + ", tool normal to the face, 20 mm", "")
                k += 1
                await app.next_update_async()
        for _ in range(600):
            if rec.pending == 0:
                break
            await app.next_update_async()
        for path in (p for p in (s.get("/visiontwin/rec/stills") or "").split(";") if p):
            name = os.path.basename(path)
            caption = ("Chip is invisible from the top view, seen only from a side view" if "views" in name else
                       "Dark lighting: rule-based 29 false rejects -> learned model 0" if "model" in name else name)
            rec.add_frames(_still(path, caption), FPS * 4)
        print(f"{TAG} {rec.index} frames -> {out}")
        code = 0
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
    finally:
        app.post_quit(code)


asyncio.ensure_future(_main())
