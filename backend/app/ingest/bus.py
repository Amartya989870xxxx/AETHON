"""Event transport abstraction.

Cameras produce events continuously and in bursts; the engines consume them at
their own pace. A queue between the two is what stops an ingestion spike from
becoming dropped observations.

For the demo everything runs in one process, so `InProcessBus` is an asyncio
queue. The production topology puts MQTT (camera -> edge) and Kafka (edge ->
core) here instead. Because every consumer only depends on this interface, that
swap does not touch a line of engine code.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Protocol


class EventBus(Protocol):
    async def publish(self, topic: str, payload: dict[str, Any]) -> None: ...
    def subscribe(self, topic: str, handler: Callable[[dict], Awaitable[None]]) -> None: ...


class InProcessBus:
    """Single-process pub/sub with bounded queues and backpressure."""

    def __init__(self, maxsize: int = 10_000):
        self._queues: dict[str, asyncio.Queue] = {}
        self._handlers: dict[str, list[Callable[[dict], Awaitable[None]]]] = {}
        self._tasks: list[asyncio.Task] = []
        self._maxsize = maxsize
        self.published = 0
        self.dropped = 0

    def _queue(self, topic: str) -> asyncio.Queue:
        if topic not in self._queues:
            self._queues[topic] = asyncio.Queue(maxsize=self._maxsize)
        return self._queues[topic]

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        q = self._queue(topic)
        try:
            q.put_nowait(payload)
            self.published += 1
        except asyncio.QueueFull:
            # Shedding load is a decision, not an accident: we count it and
            # expose it on /health so a saturated pipeline is visible rather
            # than silently lossy.
            self.dropped += 1

    def subscribe(self, topic: str, handler: Callable[[dict], Awaitable[None]]) -> None:
        self._handlers.setdefault(topic, []).append(handler)

    async def _consume(self, topic: str) -> None:
        q = self._queue(topic)
        while True:
            payload = await q.get()
            for handler in self._handlers.get(topic, []):
                try:
                    await handler(payload)
                except Exception as exc:  # one bad event must not kill the stream
                    print(f"[bus] handler error on {topic}: {exc!r}")
            q.task_done()

    def start(self) -> None:
        for topic in self._handlers:
            self._tasks.append(asyncio.create_task(self._consume(topic)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

    def stats(self) -> dict:
        return {
            "published": self.published,
            "dropped": self.dropped,
            "queue_depth": {t: q.qsize() for t, q in self._queues.items()},
        }


TOPIC_OBSERVATIONS = "observations"
TOPIC_ALERTS = "alerts"

bus = InProcessBus()
