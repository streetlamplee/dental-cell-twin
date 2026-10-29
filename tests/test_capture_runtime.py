"""Exercise actual capture request ownership with a deterministic fake renderer."""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types

import numpy as np
import pytest


@pytest.fixture
def capture_module(monkeypatch):
    factory = Path(__file__).resolve().parents[1] / "source/extensions/visiontwin.factory/visiontwin/factory"
    package = types.ModuleType("capture_test_factory")
    package.__path__ = [str(factory)]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    app = types.SimpleNamespace(update=100, now=0.0)
    app.get_update_number = lambda: app.update
    async def next_update():
        app.update += 1
        app.now += 0.1
        await asyncio.sleep(0)
    app.next_update_async = next_update
    for name in ("omni", "omni.kit", "omni.kit.app", "omni.kit.widget", "omni.kit.widget.viewport",
                 "omni.kit.widget.viewport.capture", "carb"):
        module = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, module)
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, module)
    sys.modules["omni.kit.app"].get_app = lambda: app
    sys.modules["carb"].log_error = lambda message: None
    captures = []
    class Capture:
        def __init__(self, callback, **kwargs):
            self.callback = callback
            self.frame_info = {"swh_frame_number": kwargs["frame_to_capture"]}
            captures.append(self)
        async def wait_for_result(self):
            if not app.complete:
                await asyncio.Event().wait()
            self.callback(None, 4, 1, 1, None)
    app.complete = True
    sys.modules["omni.kit.widget.viewport.capture"].ByteCapture = Capture
    spec = importlib.util.spec_from_file_location("capture_test_factory.capture_runtime", factory / "capture_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "perf_counter", lambda: app.now)
    return module, app, captures


def pool_for(module, **kwargs):
    viewport = types.SimpleNamespace(schedule_capture=lambda cap: None)
    return module.CapturePool(lambda: viewport, lambda *args: np.zeros((1,1,3), dtype=np.uint8), **kwargs)


def test_cancel_before_task_starts_has_no_pending_or_delivery(capture_module):
    module, app, captures = capture_module
    async def scenario():
        pool, delivered = pool_for(module), []
        pool.request(lambda *args: delivered.append(args))
        pool.close()
        await pool.drain()
        assert pool.pending == 0 and not pool.owner.tasks and delivered == [] and captures == []
    asyncio.run(scenario())


@pytest.mark.parametrize("wall,budget,expected", [(0.15, 100, "wall_timeout"), (30, 2, "update_budget")])
def test_deadlines_are_distinct_and_native_late_callbacks_are_ignored(capture_module, wall, budget, expected):
    module, app, captures = capture_module
    async def scenario():
        app.complete = False
        pool, errors, events, delivered = pool_for(module, wall_timeout_s=wall, update_budget=budget), [], [], []
        pool.request(lambda *args: delivered.append(args), errors.append, lambda event, **kw: events.append(event))
        await pool.drain()
        assert errors == [expected] and events == ["TIMEOUT"] and pool.pending == 0
        captures[0].callback(None,4,1,1,None)
        assert not delivered and pool.timeouts == 1 and not pool.owner.errors
    asyncio.run(scenario())


def test_completion_is_delivered_once_and_cancellation_is_idempotent(capture_module):
    module, app, captures = capture_module
    async def scenario():
        pool, delivered, events = pool_for(module), [], []
        pool.request(lambda *args: delivered.append(args), on_event=lambda event, **kw: events.append(event))
        await pool.drain()
        pool.cancel_pending()
        pool.close()
        assert len(delivered) == 1 and events == ["CAPTURE_RECEIVED"] and delivered[0][3] == 0
        assert pool.pending == 0 and not pool.owner.tasks and not pool.owner.errors
    asyncio.run(scenario())


def test_old_callback_never_reads_cleared_extension_attributes(capture_module, monkeypatch, tmp_path):
    module, app, captures = capture_module
    for name in ("carb.eventdispatcher", "omni.usd"):
        stub = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, stub)
        parent, child = name.rsplit(".", 1)
        monkeypatch.setattr(sys.modules[parent], child, stub, raising=False)
    path = Path(module.__file__).with_name("runtime_session.py")
    spec = importlib.util.spec_from_file_location("capture_test_factory.runtime_session", path)
    runtime_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runtime_module)
    session = runtime_module.RuntimeSession.__new__(runtime_module.RuntimeSession)
    held = []
    ext = types.SimpleNamespace(_sim=types.SimpleNamespace(time=1),
        _frames=types.SimpleNamespace(request_frame=lambda *args, **kw: held.append((args,kw))))
    session.ext, session.alive, session.generation = ext, True, 4
    session.active_ticket, session.discarded = None, 0
    session.trace = runtime_module.RunTrace(str(tmp_path), "r", 4, False)
    delivered = []
    session.capture(1, 0, lambda *args: delivered.append(True), lambda *args: delivered.append(True))
    session.alive = False
    session.trace.close(1, "aborted:shutdown")
    del ext._sim
    held[0][0][1]("late error after unload")
    assert not delivered and session.discarded == 1
