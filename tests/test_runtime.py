"""Cancellation, ownership and timing semantics without requiring Kit."""

import asyncio
import csv

from core.runtime import RunTrace, TaskOwner


def test_cancel_drains_tasks_and_runs_finally():
    async def scenario():
        owner, cleaned = TaskOwner(), []
        async def work():
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.append(True)
        owner.create(work())
        await asyncio.sleep(0)
        owner.cancel()
        await owner.drain()
        assert cleaned == [True] and not owner.tasks and not owner.errors
    asyncio.run(scenario())


def test_task_errors_are_observed():
    async def scenario():
        owner = TaskOwner()
        async def work():
            raise RuntimeError("intentional failure")
        owner.create(work())
        await owner.drain()
        assert len(owner.errors) == 1 and "intentional failure" in owner.errors[0]
    asyncio.run(scenario())


def test_trace_uses_wall_clock_and_keeps_requests_distinct(tmp_path):
    now = [100.0]
    trace = RunTrace(str(tmp_path), "r1", 7, True, clock=lambda: now[0])
    a = trace.request(1, 0, 0.1, 10)
    b = trace.request(1, 1, 0.2, 20)
    now[0] += 0.2
    trace.event("CAPTURE_RECEIVED", a, 0.3, 30, captured_frame=10)
    now[0] += 0.01
    trace.event("INSPECTION_DONE", a)
    trace.event("VERDICT_APPLIED", a)
    trace.event("TIMEOUT", b, detail="wall")
    result = trace.summary(1.0)
    assert result["max_pending"] == 2
    assert abs(result["latency_ms"]["capture"]["p50"] - 200) < 1e-8
    assert result["latency_ms"]["capture"]["n"] == 1
    trace.close(1.0)
    frozen = trace.summary(1.0)["wall_s"]
    now[0] += 10
    assert trace.summary(1.0)["wall_s"] == frozen
    trace.event("DISCARDED", a)  # no write to a closed file
    with open(tmp_path / "trace.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert {r["generation"] for r in rows} == {"7"}
    assert rows[-1]["event"] == "RUN_END"
