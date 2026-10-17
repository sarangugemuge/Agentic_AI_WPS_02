"""
SkillSync Event Broadcaster — In-Memory Async Event Bus for Server-Sent Events (SSE).
Allows decoupled backend services (webhooks, background sync worker) to broadcast
real-time assessment updates directly to connected frontend clients.
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, Set

logger = logging.getLogger("skillsync.services.broadcaster")


class EventBroadcaster:
    """
    Manages active SSE client queues and broadcasts JSON-encoded events.
    """

    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> AsyncGenerator[str, None]:
        """
        Yields Server-Sent Events formatted strings to an active HTTP connection.
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers.add(queue)
            logger.info(f"[SSE] Client connected. Active subscribers: {len(self._subscribers)}")

        # Send initial connection handshake event
        initial_payload = {
            "event": "connected",
            "message": "SkillSync Real-Time Event Stream connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield f"event: connected\ndata: {json.dumps(initial_payload)}\n\n"

        try:
            while True:
                try:
                    # Wait for next event with a periodic heartbeat keep-alive
                    event_data = await asyncio.wait_for(queue.get(), timeout=20.0)
                    event_name = event_data.get("event", "message")
                    yield f"event: {event_name}\ndata: {json.dumps(event_data)}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic keep-alive ping comment so proxies don't close idle HTTP connection
                    yield ": ping keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            async with self._lock:
                self._subscribers.discard(queue)
                logger.info(f"[SSE] Client disconnected. Active subscribers: {len(self._subscribers)}")

    async def broadcast(self, event_name: str, payload: Dict[str, Any]) -> None:
        """
        Dispatches an event payload to all currently connected subscriber queues.
        """
        message = {
            "event": event_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }

        async with self._lock:
            subscribers_snapshot = list(self._subscribers)

        if not subscribers_snapshot:
            logger.debug(f"[SSE Broadcast] No active subscribers for event '{event_name}'")
            return

        logger.info(f"[SSE Broadcast] Sending '{event_name}' to {len(subscribers_snapshot)} subscriber(s)")

        for queue in subscribers_snapshot:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("[SSE Broadcast] Subscriber queue full, dropping event.")


# Global singleton broadcaster instance
broadcaster = EventBroadcaster()


def get_broadcaster() -> EventBroadcaster:
    """Dependency injection getter for EventBroadcaster."""
    return broadcaster
