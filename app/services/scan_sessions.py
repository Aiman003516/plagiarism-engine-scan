"""Re-attachable SSE scan sessions (buffer + fan-out of scan events)."""

import time
import uuid
import hmac
import json
import asyncio
from typing import List, Dict, Any, Optional, Tuple
import threading


# ---------------------------------------------------------------------------
# Re-attachable SSE scan sessions
# ---------------------------------------------------------------------------
# The scan streams below are produced *inside* a POST request. When the browser
# navigates away (or reloads), the response reader is dropped and — without help
# — every later log line is lost, even though the worker thread keeps running to
# completion. The client is then stuck showing a half-finished scan.
#
# A `ScanStreamSession` buffers every event it publishes and keeps a list of live
# subscribers, so a client that comes back can (1) replay the events it missed and
# (2) keep following the still-running scan over
# `GET /api/plagiarism/scan-stream/{project_id}`.
#
# `EventSource` can neither POST nor send an `Authorization` header, so each
# session mints an unguessable `stream_token` (delivered as the first frame of the
# originating stream) that acts as a capability for re-attaching. The long-lived
# JWT therefore never has to appear in a URL.
_SCAN_SESSION_TTL_SECONDS = 3600
_SCAN_SESSION_MAX = 32
_SCAN_TERMINAL_EVENTS = ("complete", "error")


class ScanStreamSession:
    """Buffers and fans out the SSE events of a single running scan."""

    def __init__(self, project_id: str, loop: asyncio.AbstractEventLoop):
        self.project_id = project_id
        self.stream_token = uuid.uuid4().hex
        self.created_at = time.time()
        self.last_event_at = self.created_at
        self.done = False
        self._loop = loop
        self._lock = threading.Lock()
        self._events: List[Dict[str, Any]] = []
        self._subscribers: List[asyncio.Queue] = []

    # -- publishing (called from executor worker threads) --------------------
    def publish(self, event: Dict[str, Any]) -> None:
        with self._lock:
            self._events.append(event)
            self.last_event_at = time.time()
            if event.get("type") in _SCAN_TERMINAL_EVENTS:
                self.done = True
            # Fan out under the same lock that `subscribe()` snapshots the backlog
            # with, so a client registering concurrently can neither miss this
            # event nor receive it twice.
            for queue in list(self._subscribers):
                self._loop.call_soon_threadsafe(queue.put_nowait, event)

    def publish_log(self, message: str) -> None:
        self.publish({"type": "log", "text": message})

    # -- subscribing ---------------------------------------------------------
    def subscribe(self) -> Tuple[asyncio.Queue, List[Dict[str, Any]]]:
        """Return `(queue, backlog)`; together they cover every event exactly once."""
        queue: asyncio.Queue = asyncio.Queue()
        with self._lock:
            backlog = list(self._events)
            # A finished session has nothing left to stream — replay only.
            if not self.done:
                self._subscribers.append(queue)
        return queue, backlog

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def header_event(self) -> Dict[str, Any]:
        """First frame of the originating stream: lets the client persist the token."""
        return {
            "type": "session",
            "project_id": self.project_id,
            "stream_token": self.stream_token,
            "reconnect_url": (
                f"/api/plagiarism/scan-stream/{self.project_id}"
                f"?token={self.stream_token}"
            ),
        }


_scan_sessions: Dict[str, ScanStreamSession] = {}
_scan_sessions_lock = threading.Lock()


def _prune_scan_sessions_locked() -> None:
    """Drop expired/finished sessions. Caller must hold `_scan_sessions_lock`."""
    now = time.time()
    for project_id in [
        pid for pid, session in _scan_sessions.items()
        if now - session.last_event_at > _SCAN_SESSION_TTL_SECONDS
    ]:
        del _scan_sessions[project_id]

    overflow = len(_scan_sessions) - _SCAN_SESSION_MAX
    if overflow > 0:
        # Evict finished sessions oldest-first; a running scan is never evicted.
        finished = sorted(
            (session for session in _scan_sessions.values() if session.done),
            key=lambda session: session.last_event_at,
        )
        for session in finished[:overflow]:
            _scan_sessions.pop(session.project_id, None)


def _start_scan_session(project_id: str) -> ScanStreamSession:
    """Register (replacing any previous one) and return the session for a project."""
    session = ScanStreamSession(project_id, asyncio.get_event_loop())
    with _scan_sessions_lock:
        _prune_scan_sessions_locked()
        _scan_sessions[project_id] = session
    return session


def _get_scan_session(project_id: str, token: Optional[str]) -> Optional[ScanStreamSession]:
    """Look a session up, validating the reconnect capability token."""
    with _scan_sessions_lock:
        session = _scan_sessions.get(project_id)
    if session is None or not token:
        return None
    # Constant-time compare: the token is the only credential this endpoint has.
    if not hmac.compare_digest(session.stream_token, token):
        return None
    return session


async def _stream_scan_events(session: ScanStreamSession, skip_logs: int = 0):
    """Yield SSE frames: replay the missed backlog, then follow the live queue.

    `skip_logs` is the re-attaching client's resume cursor: how many log lines it
    already holds. The replay then tops the client up instead of repeating the
    whole terminal every time the user navigates back to the page.
    """
    queue, backlog = session.subscribe()
    try:
        remaining = max(0, skip_logs)
        for event in backlog:
            if event.get("type") == "log" and remaining > 0:
                remaining -= 1
                continue
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("type") in _SCAN_TERMINAL_EVENTS:
                return
        if session.done:
            return
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event.get("type") in _SCAN_TERMINAL_EVENTS:
                break
    finally:
        session.unsubscribe(queue)
