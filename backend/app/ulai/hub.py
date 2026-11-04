"""In-process fan-out of live call updates to the browser (served as Server-Sent Events)."""

import asyncio
from collections import defaultdict
from typing import Any

ALL = "*"


class Hub:
    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, topic: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._subs[topic].add(q)
        return q

    def unsubscribe(self, topic: str, q: asyncio.Queue) -> None:
        self._subs[topic].discard(q)
        if not self._subs[topic]:
            self._subs.pop(topic, None)

    def publish(self, call_id: str, message: dict[str, Any]) -> None:
        for topic in (call_id, ALL):
            for q in list(self._subs.get(topic, ())):
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    # A stalled browser tab mustn't hold up the call; it re-syncs on reconnect.
                    pass
