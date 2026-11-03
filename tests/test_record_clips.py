"""Exercise recording decisions without importing the Kit startup script."""

import ast
from pathlib import Path
from types import SimpleNamespace


def _selector(prediction="good", state="INSPECTED", route=None):
    path = Path(__file__).resolve().parents[1] / "scripts" / "record_clips.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    constants = {"CELL", "SPINDLE", "LINE_CAM", "REJECT_CAM", "SPINDLE_LEAD_S", "REJECT_LEAD_M", "REJECT_TAIL_S"}
    nodes = [node for node in tree.body if (
        isinstance(node, ast.ClassDef) and node.name == "Clips") or (
        isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in constants for t in node.targets))]
    namespace = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    product = SimpleNamespace(prediction=prediction, state=SimpleNamespace(value=state),
                              defect_kind=None, defect_reason=None, x=1.4)
    tracker = SimpleNamespace(all=lambda: [product], get=lambda _pid: product)
    sim = SimpleNamespace(tracker=tracker, station_product=None, time=23.0)
    decisions = {} if route is None else {1: SimpleNamespace(route=route)}
    ext = SimpleNamespace(_sim=sim, _sorter=SimpleNamespace(decisions=decisions))
    layout = SimpleNamespace(CELL_X=-1.0, REJECT_X=1.5)
    return namespace["Clips"](ext, 1, layout), product, sim


def test_good_verdict_selects_pass_clip_before_gate():
    clips, _, _ = _selector()
    clip, _, caption = clips.current()
    assert clip == "05_pass"
    assert "vision verdict good" in caption


def test_sorted_good_product_is_filmed_continuing_past_gate():
    clips, product, sim = _selector(state="SORTED", route="pass")
    product.x = 1.6
    assert clips.current()[0] == "05_pass"
    sim.time += 1.0
    assert "continues on outfeed belt" in clips.current()[2]
    sim.time += 0.3
    assert clips.current() == "done"


def test_actual_reject_decision_overrides_prior_good_prediction():
    clips, _, _ = _selector(state="REJECTED", route="reject")
    clip, _, caption = clips.current()
    assert clip == "05_reject"
    assert "pushed into the reject bin" in caption


def test_defect_verdict_selects_reject_clip_before_gate():
    clips, _, _ = _selector(prediction="defect")
    assert clips.current()[0] == "05_reject"
