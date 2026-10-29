"""Run-local timing and task ownership; independent of Kit and its renderer."""

import asyncio
import csv
import json
import os
import time
from collections import Counter

from .metrics import percentile


class TaskOwner:
    """Keep strong references and invalidate work before releasing its resources."""

    def __init__(self, on_error=None):
        self.tasks = set()
        self.errors = []
        self.on_error = on_error

    def create(self, coroutine):
        task = asyncio.ensure_future(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task):
        self.tasks.discard(task)
        if not task.cancelled():
            exc = task.exception()
            if exc is not None:
                self.errors.append(repr(exc))
                if self.on_error:
                    self.on_error(repr(exc))

    def cancel(self, exclude=None):
        for task in tuple(self.tasks):
            if task is not exclude:
                task.cancel()

    async def drain(self):
        tasks = tuple(self.tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.difference_update(tasks)


class RunTrace:
    FIELDS = ("run_id", "generation", "request_id", "product_id", "view", "event",
              "wall_s", "sim_s", "update", "target_frame", "captured_frame", "digest", "detail")

    def __init__(self, directory, run_id, generation, enabled=False, clock=time.perf_counter):
        self.run_id, self.generation = run_id, generation
        self.clock, self.t0 = clock, clock()
        self.counts = Counter()
        self.requests = {}
        self.latencies = {"capture": [], "inspection": [], "verdict": []}
        self.closed = False
        self.ended = None
        self.max_pending = 0
        self.sequence = 0
        self._file = None
        if enabled:
            self._file = open(os.path.join(directory, "trace.csv"), "w", newline="", encoding="utf-8")
            self._writer = csv.DictWriter(self._file, self.FIELDS)
            self._writer.writeheader()

    def request(self, product_id, view, sim_s, update):
        self.sequence += 1
        ticket = dict(request_id=self.sequence, product_id=product_id, view=view,
                      target_frame=update)
        self.requests[self.sequence] = dict(start=self.clock(), received=None, terminal=False)
        self.event("CAPTURE_REQUESTED", ticket, sim_s, update)
        pending = sum(not r["terminal"] for r in self.requests.values())
        self.max_pending = max(self.max_pending, pending)
        return ticket

    def event(self, event, ticket=None, sim_s=None, update=None, **extra):
        if self.closed:
            return
        now = self.clock()
        self.counts[event] += 1
        ticket = ticket or {}
        request = self.requests.get(ticket.get("request_id"))
        if request:
            elapsed = (now - request["start"]) * 1000
            if event == "CAPTURE_RECEIVED":
                request["received"] = now
                request["terminal"] = True
                self.latencies["capture"].append(elapsed)
            elif event in ("TIMEOUT", "CANCELLED", "CAPTURE_ERROR", "DISCARDED"):
                request["terminal"] = True
            elif event == "INSPECTION_DONE" and request["received"] is not None:
                self.latencies["inspection"].append((now - request["received"]) * 1000)
            elif event == "VERDICT_APPLIED":
                self.latencies["verdict"].append(elapsed)
        if self._file:
            row = dict(run_id=self.run_id, generation=self.generation, event=event,
                       wall_s=round(now - self.t0, 6), sim_s=sim_s, update=update, **ticket)
            row.update(extra)
            self._writer.writerow(row)

    def summary(self, sim_s):
        elapsed = (self.ended if self.ended is not None else self.clock()) - self.t0
        return dict(wall_s=round(elapsed, 6), real_time_factor=sim_s / elapsed if elapsed else None,
                    clock="perf_counter", window="start to final capture drain; excludes stage/setup warmup",
                    events=dict(self.counts), max_pending=self.max_pending,
                    latency_ms={name: dict(n=len(xs), p50=percentile(xs, 50),
                                           p95=percentile(xs, 95), max=max(xs) if xs else None)
                                for name, xs in self.latencies.items()})

    def close(self, sim_s, status="complete"):
        if self.closed:
            return
        self.event("RUN_END", sim_s=sim_s, detail=status)
        self.ended = self.clock()
        self.closed = True
        if self._file:
            directory = os.path.dirname(self._file.name)
            self._file.close()
            with open(os.path.join(directory, "timing.json"), "w", encoding="utf-8") as f:
                json.dump(dict(status=status, **self.summary(sim_s)), f, indent=2)
