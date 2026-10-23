"""Teach pendant window for surface teaching (Day 13). Holds the jog state and the point list;
geometry and checks come from core.teach, the machine is posed through a callback.

Jog: X / Y / Z in mm, B / C in degrees, inside the URDF limits. The readout shows which block
face the tool looks at, with the angle to its normal, the tool tip's offset from its centre
and the standoff. Points: generate origin + 5 faces, save the current pose, go to a point,
play the program, export it as JSON with a verification report.
"""

import math
import os
import time
from typing import Callable, Dict

import carb.eventdispatcher
import omni.kit.app
import omni.ui as ui

from .core.teach import AXES, Teacher, TeachPoint, TeachProgram

UNIT = {"x_joint": ("X", "mm", 1000.0), "y_joint": ("Y", "mm", 1000.0), "z_joint": ("Z", "mm", 1000.0),
        "b_joint": ("B", "deg", 180.0 / math.pi), "c_joint": ("C", "deg", 180.0 / math.pi)}
ROT_RANGE = {"b_joint": (-180.0, 180.0), "c_joint": (-180.0, 360.0)}


class TeachPendant:
    def __init__(self, teacher: Teacher, apply_q: Callable[[Dict[str, float]], None], export_dir: str,
                 on_close: Callable[[], None]) -> None:
        self.teacher, self.apply_q, self.export_dir, self._on_close = teacher, apply_q, export_dir, on_close
        self.q = {a: 0.0 for a in AXES}
        self.points = []
        self._sliders = {}
        self._syncing = False
        self._play_sub = None
        self._window = ui.Window("VisionTwin Teach Pendant", width=420, height=640)
        self._window.set_visibility_changed_fn(lambda visible: None if visible else self.destroy())
        with self._window.frame:
            with ui.VStack(spacing=5, height=0):
                ui.Label("Surface teaching: tool looks straight at each face of the block on C", height=18)
                with ui.HStack(height=24):
                    ui.Label("Standoff (mm)", width=110)
                    self._standoff = ui.FloatField()
                    self._standoff.model.set_value(20.0)
                    ui.Button("Origin + 5 faces", clicked_fn=self._generate, width=140)
                for axis in AXES:
                    name, unit, k = UNIT[axis]
                    lo, hi = ROT_RANGE.get(axis) or (teacher.limits[axis][0] * k, teacher.limits[axis][1] * k)
                    with ui.HStack(height=22):
                        ui.Label(f"{name} ({unit})", width=70)
                        s = ui.FloatSlider(min=lo, max=hi, step=0.1)
                        s.model.add_value_changed_fn(lambda m, a=axis: self._jog(a, m.get_value_as_float()))
                        self._sliders[axis] = s
                self._readout = ui.Label("", height=40, word_wrap=True)
                with ui.HStack(spacing=4, height=28):
                    ui.Button("Save point", clicked_fn=self._save_point)
                    ui.Button("Play", clicked_fn=self._play)
                    ui.Button("Stop", clicked_fn=self._stop)
                    ui.Button("Export", clicked_fn=self.export)
                self._status = ui.Label("", height=18)
                ui.Label("Points", height=18)
                self._list = ui.Frame(height=0)
                self._list.set_build_fn(self._build_list)
        self.set_pose(self.q)

    # -- pose ---------------------------------------------------------------

    def set_pose(self, q: Dict[str, float]) -> None:
        self.q = {a: float(q[a]) for a in AXES}
        self._syncing = True
        for axis, s in self._sliders.items():
            s.model.set_value(self.q[axis] * UNIT[axis][2])
        self._syncing = False
        self.apply_q(self.q)
        c = self.teacher.verify(self.q)
        self._readout.text = (f"looking at {c.face}: angle {c.angle_deg:.2f} deg, offset {c.offset_mm:.2f} mm, "
                              f"standoff {c.standoff_mm:.1f} mm, limits {'OK' if c.within_limits else 'EXCEEDED'}")

    def _jog(self, axis: str, value: float) -> None:
        if self._syncing:
            return
        q = dict(self.q)
        q[axis] = value / UNIT[axis][2]
        self.set_pose(q)

    # -- points -------------------------------------------------------------

    def _generate(self) -> None:
        try:
            self.points = self.teacher.face_program(self._standoff.model.get_value_as_float() / 1000.0)
            self._status.text = f"{len(self.points)} points generated"
        except ValueError as exc:
            self._status.text = str(exc)
        self._list.rebuild()

    def _save_point(self) -> None:
        c = self.teacher.verify(self.q)
        self.points.append(TeachPoint(f"P{len(self.points) + 1}", dict(self.q), c.face if c.angle_deg < 1.0 else None,
                                      "manual"))
        self._status.text = f"saved {self.points[-1].name} ({c.face}, {c.angle_deg:.2f} deg)"
        self._list.rebuild()

    def _build_list(self) -> None:
        with ui.VStack(spacing=2, height=0):
            for i, p in enumerate(self.points):
                with ui.HStack(height=22):
                    ui.Label(f"{i + 1}. {p.name} [{p.source}]", width=210)
                    ui.Button("Go", width=50, clicked_fn=lambda q=p.q: self.set_pose(q))
                    ui.Button("Delete", width=60, clicked_fn=lambda k=i: self._delete(k))

    def _delete(self, i: int) -> None:
        del self.points[i]
        self._list.rebuild()

    # -- playback and export ------------------------------------------------

    def _play(self) -> None:
        if not self.points:
            self._status.text = "no points"
            return
        self._stop()
        program, start, t = TeachProgram(self.points), dict(self.q), [0.0]

        def tick(_event):
            t[0] += 1.0 / 60.0
            q, i = program.pose_at(t[0], start)
            self.set_pose(q)
            self._status.text = f"playing: {program.points[i].name}"
            if t[0] >= program.duration:
                self._stop()
                self._status.text = "program finished"

        self._play_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
            event_name=omni.kit.app.GLOBAL_EVENT_UPDATE, on_event=tick, observer_name="visiontwin.teach.play")

    def _stop(self) -> None:
        if self._play_sub is not None:
            self._play_sub.reset()
            self._play_sub = None

    def export(self) -> str:
        """Write the program and a verification report; returns the JSON path."""
        os.makedirs(self.export_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        program = TeachProgram(self.points)
        path = os.path.join(self.export_dir, f"teach_program_{stamp}.json")
        checks = [self.teacher.verify(p.q, p.face) for p in self.points]
        with open(path, "w", encoding="utf-8") as f:
            f.write(program.to_json(machine="teeth_mill", tool="tool_tip",
                                    checks=[c.__dict__ for c in checks]))
        self._status.text = f"exported {os.path.basename(path)}"
        return path

    def destroy(self) -> None:
        self._stop()
        if self._window is not None:
            w, self._window = self._window, None
            w.destroy()
            self._on_close()
