"""Kit startup script (run with kit --exec): click through the dashboard and the teach pendant the
way a person would (omni.kit.ui_test mouse clicks on the real widgets), screenshot the whole app
window after each step, write a report, then quit. Used by scripts/gui_check.ps1.

Steps (app defaults: crown line, vision off):
  01 app start: dashboard defaults
  02 Products = 3, Build Scene
  03 Start, View combo -> Cell close-up / Inspection camera / Overview while it runs
  04 run finished with vision off: every crown passes, run record says vision false
  05 tick Vision, Reset, Start: the inspection camera is created at Start (bug fixed 2026-10-24)
  05b change the product, Reset, Start: refused with "press Build Scene"
  06 Build Scene, Start with vision on: inspection camera window, verdicts, rejects
  07 Teach pendant: Origin + 5 faces, jog X, Save point, Play, Export, close

Settings: --/visiontwin/gui/out=<dir>
"""

import asyncio
import glob
import json
import os
import traceback

import carb
import carb.settings
import omni.appwindow
import omni.kit.app
import omni.kit.renderer_capture
import omni.ui as ui

TAG = "[gui]"
DASH = "VisionTwin Factory"
PENDANT = "VisionTwin Teach Pendant"


class Check:
    def __init__(self, out):
        self.out, self.rows, self.shot = out, [], 0
        self.capture = omni.kit.renderer_capture.acquire_renderer_capture_interface()
        self.app = omni.kit.app.get_app()

    def record(self, step, ok, what):
        self.rows.append((step, "PASS" if ok is True else "FAIL" if ok is False else "NOTE", what))
        print(f"{TAG} {step} {'PASS' if ok is True else 'FAIL' if ok is False else 'NOTE'}: {what}")

    async def wait(self, n):
        for _ in range(n):
            await self.app.next_update_async()

    async def screenshot(self, name):
        self.shot += 1
        path = os.path.join(self.out, f"{self.shot:02d}_{name}.png")
        window = omni.appwindow.get_default_app_window()
        self.capture.capture_next_frame_swapchain(path, window)
        await self.wait(3)
        self.capture.wait_async_capture(window)
        return path

    def write(self):
        lines = ["# GUI check", "", "| step | result | observation |", "|---|---|---|"]
        lines += [f"| {s} | {r} | {w} |" for s, r, w in self.rows]
        lines += ["", "Screenshots: " + ", ".join(sorted(os.path.basename(p) for p in glob.glob(f"{self.out}/*.png")))]
        with open(os.path.join(self.out, "report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


async def _until(app, cond, updates):
    for _ in range(updates):
        if cond():
            return True
        await app.next_update_async()
    return cond()


def _label_text(window, prefix):
    for ref in ui_test.find_all(f"{window}//Frame/**/Label[*]"):
        text = ref.widget.text
        if text.startswith(prefix):
            return text
    return ""


async def _click(window, kind, text=None):
    query = f"{window}//Frame/**/{kind}[*]" + (f".text=='{text}'" if text else "")
    ref = ui_test.find(query)
    if ref is None:
        raise LookupError(query)
    await ref.click()
    return ref


async def _main():
    app = omni.kit.app.get_app()
    s = carb.settings.get_settings()
    code = 1
    check = None
    try:
        app.get_extension_manager().set_extension_enabled_immediate("omni.kit.ui_test", True)
        global ui_test
        import omni.kit.ui_test as ui_test
        import visiontwin.factory.extension as vt

        out = s.get("/visiontwin/gui/out")
        os.makedirs(out, exist_ok=True)
        check = Check(out)
        ext = await _until(app, vt.get_instance, 3000) and vt.get_instance()
        await _until(app, lambda: ui_test.find(f"{DASH}//Frame/**/Button[*].text=='Build Scene'") is not None, 600)
        await check.wait(120)

        # 01 defaults
        combo = ui_test.find_all(f"{DASH}//Frame/**/ComboBox[*]")[0].widget.model
        part_index = combo.get_item_value_model().get_value_as_int()
        vision_box = ui_test.find(f"{DASH}//Frame/**/CheckBox[*]")
        check.record("01 defaults", part_index == 2 and not vision_box.widget.model.get_value_as_bool(),
                     f"product combo index {part_index} (2 = crown), Vision checkbox "
                     f"{'on' if vision_box.widget.model.get_value_as_bool() else 'off'}")
        await check.screenshot("start_defaults")

        # 02 Products = 3, Build Scene
        products = ui_test.find_all(f"{DASH}//Frame/**/IntField[*]")[1]
        await products.input("3", clear_before_input=True)
        check.record("02 products field", s.get("/exts/visiontwin.factory/maxProducts") == 3,
                     f"typed 3 -> setting maxProducts = {s.get('/exts/visiontwin.factory/maxProducts')}")
        await _click(DASH, "Button", "Build Scene")
        ok = await _until(app, lambda: ext._scene_ready and _label_text(DASH, "Status").endswith("scene ready"), 3000)
        check.record("02 build scene", ok, f"status '{_label_text(DASH, 'Status')}', cell "
                     f"{'present' if ext._cell is not None else 'missing'}, robot "
                     f"{'present' if ext._arm is not None else 'missing'}")
        await check.wait(60)
        await check.screenshot("built")

        # 03 Start + View combo
        await _click(DASH, "Button", "Start")
        view_combo = ui_test.find_all(f"{DASH}//Frame/**/ComboBox[*]")[1].widget.model
        main = ext.main_viewport
        await _until(app, lambda: ext._sim.station_product is not None, 3000)
        for index, name in ((1, "view_cell_closeup"), (2, "view_inspection_camera"), (0, "view_overview")):
            view_combo.get_item_value_model().set_value(index)
            await check.wait(30)
            check.record(f"03 view {index}", True, f"camera {main.camera_path if main else '?'}")
            await check.screenshot(name)
        ok = await _until(app, lambda: ext.run_complete, 60 * 90)
        summ = ext.summary or {}
        status = _label_text(DASH, "Status")
        passed = summ.get("rejected") == 0 and summ.get("sorted") == 3 and summ.get("vision") is False \
            and status.endswith("3 passed (vision off)")
        check.record("04 run vision off", ok and passed,
                     f"summary vision={summ.get('vision')} sorted={summ.get('sorted')} rejected={summ.get('rejected')}; "
                     f"status '{status}'; counters: "
                     + _label_text(DASH, "t=").replace("\n", " / ")[:160])
        await check.screenshot("done_vision_off")

        # 05 Vision on, Reset, Start (no Build Scene)
        await vision_box.click()
        check.record("05 vision checkbox", s.get("/exts/visiontwin.factory/vision") is True,
                     f"setting vision = {s.get('/exts/visiontwin.factory/vision')}")
        s.set("/exts/visiontwin.factory/maxProducts", 2)
        await _click(DASH, "Button", "Reset")
        await check.wait(10)
        await _click(DASH, "Button", "Start")
        ok = await _until(app, lambda: ext.run_complete, 60 * 60)
        summ = ext.summary or {}
        check.record("05 vision on after Reset only", ok and summ.get("vision") is True and bool(ext._inspectors),
                     f"run_complete={ext.run_complete}, summary vision={summ.get('vision')}, inspectors={len(ext._inspectors)}, "
                     f"rejected={summ.get('rejected')}, run_dir={'set' if ext.run_dir else 'none'}, "
                     f"status '{_label_text(DASH, 'Status')}'")
        await check.screenshot("vision_on_after_reset")
        await _click(DASH, "Button", "Stop")

        # 05b product changed + Reset + Start: must ask for Build Scene, not run a mismatched scene
        combo.get_item_value_model().set_value(0)
        await _click(DASH, "Button", "Reset")
        await _click(DASH, "Button", "Start")
        await check.wait(10)
        status = _label_text(DASH, "Status")
        check.record("05b product changed, Reset only", "press Build Scene" in status and not ext._sim.running,
                     f"status '{status}'")
        await check.screenshot("product_changed_reset")
        combo.get_item_value_model().set_value(2)

        # 06 Build Scene, Start with vision on
        await _click(DASH, "Button", "Build Scene")
        await _until(app, lambda: ext._scene_ready and _label_text(DASH, "Status").endswith("scene ready"), 3000)
        await _click(DASH, "Button", "Start")
        await _until(app, lambda: ext._sim.station_product is not None and ext._cell.phase(ext._station_time()).startswith("VIEW"),
                     60 * 30)
        await check.screenshot("vision_on_inspecting")
        ok = await _until(app, lambda: ext.run_complete, 60 * 60)
        summ = ext.summary or {}
        windows = [w.title for w in ui.Workspace.get_windows() if w.visible and "nspection" in w.title]
        check.record("06 vision on after Build Scene", ok and summ.get("vision") is True and summ.get("sorted") == 2,
                     f"summary vision={summ.get('vision')} sorted={summ.get('sorted')} correct={summ.get('sort_correct')} "
                     f"rejected={summ.get('rejected')}; visible inspection windows {windows}")
        await check.screenshot("vision_on_done")

        # 07 teach pendant
        await _click(DASH, "Button", "Teach pendant (crown cell)")
        ok = await _until(app, lambda: ui_test.find(f"{PENDANT}//Frame/**/Button[*].text=='Play'") is not None, 300)
        check.record("07 pendant opens", ok, f"dashboard status '{_label_text(DASH, 'Status')}'")
        await check.wait(30)
        await check.screenshot("pendant_open")
        await _click(PENDANT, "Button", "Origin + 5 faces")
        await check.wait(10)
        pendant = ext._pendant
        check.record("07 origin + 5 faces", pendant is not None and len(pendant.points) == 6,
                     f"{len(pendant.points) if pendant else 0} points, status '{pendant._status.text if pendant else ''}'")
        x_slider = ui_test.find_all(f"{PENDANT}//Frame/**/FloatSlider[*]")[0].widget.model
        before = dict(pendant.q)
        x_slider.set_value(x_slider.get_value_as_float() - 20.0)
        await check.wait(10)
        moved = {k: round((pendant.q[k] - before[k]) * 1000, 2) for k in before if abs(pendant.q[k] - before[k]) > 1e-9}
        check.record("07 jog X", bool(moved), f"joint change (mm or mrad x1000): {moved}")
        await _click(PENDANT, "Button", "Save point")
        await check.wait(10)
        check.record("07 save point", len(pendant.points) == 7, f"{len(pendant.points)} points, '{pendant._status.text}'")
        await _click(PENDANT, "Button", "Play")
        await check.wait(45)
        await check.screenshot("pendant_playing")
        ok = await _until(app, lambda: not pendant.playing, 60 * 30)
        check.record("07 play", ok, f"status '{pendant._status.text}'")
        await _click(PENDANT, "Button", "Export")
        await check.wait(10)
        files = sorted(glob.glob(os.path.join(pendant.export_dir, "*.json")), key=os.path.getmtime)
        exported = files[-1] if files else None
        n = len(json.load(open(exported, encoding="utf-8")).get("points", [])) if exported else 0
        check.record("07 export", exported is not None and n == 7, f"{exported} ({n} points), '{pendant._status.text}'")
        await check.screenshot("pendant_exported")
        ui.Workspace.get_window(PENDANT).visible = False
        ok = await _until(app, lambda: ext._pendant is None, 120)
        check.record("07 close pendant", ok and _label_text(DASH, "Status").endswith("teach pendant closed"),
                     f"status '{_label_text(DASH, 'Status')}'")
        await check.wait(30)
        await check.screenshot("pendant_closed")
        code = 0 if all(r[1] != "FAIL" for r in check.rows) else 2
    except Exception:
        carb.log_error(f"{TAG} failed:\n{traceback.format_exc()}")
        if check:
            check.record("script", False, traceback.format_exc().strip().splitlines()[-1])
    finally:
        if check:
            check.write()
            print(f"{TAG} report: {os.path.join(check.out, 'report.md')}")
        app.post_quit(code)


ui_test = None
asyncio.ensure_future(_main())
