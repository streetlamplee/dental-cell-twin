"""omni.ui control panel. Holds no simulation state; it calls back into the extension."""

from typing import Callable

import omni.ui as ui


class Dashboard:
    def __init__(self, on_build: Callable[[], None], on_start: Callable[[], None],
                 on_stop: Callable[[], None], on_reset: Callable[[], None],
                 on_speed: Callable[[float], None], initial_speed: float) -> None:
        self._window = ui.Window("VisionTwin Factory", width=360, height=320)
        with self._window.frame:
            with ui.VStack(spacing=6, height=0):
                ui.Button("Build Scene", clicked_fn=on_build, height=30)
                with ui.HStack(spacing=4, height=30):
                    ui.Button("Start", clicked_fn=on_start)
                    ui.Button("Stop", clicked_fn=on_stop)
                    ui.Button("Reset", clicked_fn=on_reset)
                with ui.HStack(height=24):
                    ui.Label("Speed (m/s)", width=100)
                    speed = ui.FloatDrag(min=0.0, max=2.0, step=0.05)
                    speed.model.set_value(initial_speed)
                    speed.model.add_value_changed_fn(lambda m: on_speed(m.get_value_as_float()))
                ui.Spacer(height=4)
                self._status = ui.Label("Status: idle", height=20)
                self._counters = ui.Label("", height=40, word_wrap=True)
                self._last_event = ui.Label("", height=20, word_wrap=True)

    def set_status(self, text: str) -> None:
        self._status.text = f"Status: {text}"

    def set_counters(self, text: str) -> None:
        self._counters.text = text

    def set_last_event(self, text: str) -> None:
        self._last_event.text = text

    def destroy(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None
