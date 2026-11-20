"""In-process event hub: tool events and UI events pushed to /ws/events/{session_id}."""
import asyncio
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Set


class EventHub:
    def __init__(self) -> None:
        self._subs: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._recent: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=200))
        self.history: Deque[dict] = deque(maxlen=500)

    def publish(self, session_id: str, event: Dict[str, Any]) -> dict:
        event = {"ts": time.time(), "session_id": session_id, **event}
        self._recent[session_id].append(event)
        self.history.append(event)
        for key in (session_id, "*"):
            for q in list(self._subs.get(key, ())):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        return event

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subs[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        self._subs[session_id].discard(q)

    def recent(self, session_id: str):
        return list(self._recent.get(session_id, ()))


hub = EventHub()
