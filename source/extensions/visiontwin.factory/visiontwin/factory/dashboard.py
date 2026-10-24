"""omni.ui control panel. Holds no simulation state; it calls back into the extension.

Line setup values (product, seed, product count, defect rate) are written to the
extension settings and take effect on Build Scene / Reset, so a run's configuration is
always the one recorded in its run.json.
"""

from collections import deque
from typing import Callable, Dict, Sequence

import omni.ui as ui

PRODUCTS = ("box", "kfl08", "crown")
PRODUCT_LABELS = ("Box (colour)", "KFL08 flange bearing", "Dental crown (inspection cell)")
VIEWS = ("Overview", "Cell close-up", "Inspection camera")


class Dashboard:
    def __init__(self, on_build: Callable[[], None], on_start: Callable[[], None],
                 on_stop: Callable[[], None], on_reset: Callable[[], None],
                 on_speed: Callable[[float], None], initial_speed: float,
                 on_setting: Callable[[str, object], None] = None, initial: Dict[str, object] = None,
                 on_view: Callable[[int], None] = None, on_teach: Callable[[], None] = None) -> None:
        on_setting = on_setting or (lambda _k, _v: None)
        initial = initial or {}
        self._events = deque(maxlen=5)
        self._window = ui.Window("VisionTwin Factory", width=380, height=560)
        with self._window.frame:
            with ui.VStack(spacing=6, height=0):
                ui.Label("Line setup (applied on Build Scene / Reset)", height=18)
                with ui.HStack(height=24):
                    ui.Label("Product", width=100)
                    part = str(initial.get("part", "box"))
                    combo = ui.ComboBox(PRODUCTS.index(part) if part in PRODUCTS else 0, *PRODUCT_LABELS)
                    combo.model.add_item_changed_fn(
                        lambda m, _i: on_setting("part", PRODUCTS[m.get_item_value_model().get_value_as_int()]))
                self._int_field("Seed", initial.get("seed", 42), lambda v: on_setting("seed", v))
                self._int_field("Products", initial.get("maxProducts", 30), lambda v: on_setting("maxProducts", v))
                with ui.HStack(height=24):
                    ui.Label("Vision", width=100)
                    vision = ui.CheckBox(width=20)
                    vision.model.set_value(bool(initial.get("vision", False)))
                    vision.model.add_value_changed_fn(lambda m: on_setting("vision", m.get_value_as_bool()))
                    ui.Label("  inspection camera + verdicts", width=0)
                with ui.HStack(height=24):
                    ui.Label("Defect rate", width=100)
                    rate = ui.FloatSlider(min=0.0, max=1.0, step=0.05)
                    rate.model.set_value(float(initial.get("defectRate", 0.3)))
                    rate.model.add_value_changed_fn(lambda m: on_setting("defectRate", round(m.get_value_as_float(), 3)))
                ui.Spacer(height=4)
                ui.Button("Build Scene", clicked_fn=on_build, height=30)
                if on_teach:
                    ui.Button("Teach pendant (crown cell)", clicked_fn=on_teach, height=24)
                with ui.HStack(spacing=4, height=30):
                    ui.Button("Start", clicked_fn=on_start)
                    ui.Button("Stop", clicked_fn=on_stop)
                    ui.Button("Reset", clicked_fn=on_reset)
                with ui.HStack(height=24):
                    ui.Label("Speed (m/s)", width=100)
                    speed = ui.FloatDrag(min=0.0, max=2.0, step=0.05)
                    speed.model.set_value(initial_speed)
                    speed.model.add_value_changed_fn(lambda m: on_speed(m.get_value_as_float()))
                with ui.HStack(height=24):
                    ui.Label("View", width=100)
                    view = ui.ComboBox(0, *VIEWS)
                    if on_view:
                        view.model.add_item_changed_fn(
                            lambda m, _i: on_view(m.get_item_value_model().get_value_as_int()))
                ui.Spacer(height=4)
                self._status = ui.Label("Status: idle", height=20)
                self._counters = ui.Label("", height=90, word_wrap=True)
                ui.Label("Recent events", height=18)
                self._last_event = ui.Label("", height=90, word_wrap=True)

    @staticmethod
    def _int_field(label: str, value, on_change: Callable[[int], None]) -> None:
        with ui.HStack(height=24):
            ui.Label(label, width=100)
            field = ui.IntField()
            field.model.set_value(int(value))
            field.model.add_value_changed_fn(lambda m: on_change(m.get_value_as_int()))

    def set_status(self, text: str) -> None:
        self._status.text = f"Status: {text}"

    def set_counters(self, text: str) -> None:
        self._counters.text = text

    def set_last_event(self, text: str) -> None:
        if not text:
            self._events.clear()
        else:
            self._events.append(text)
        self._last_event.text = "\n".join(reversed(self._events))

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None
