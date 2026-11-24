"""
Thread-safe per-experiment WebSocket & JSONL event broadcaster.
Supports historical replay on client reconnect without re-starting experiments.
"""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from optimization_agent.key_manager import GroqKeyManager, get_default_key_manager


class EventService:
    """Publishes sanitized runtime events to history logs and active WebSocket clients."""

    def __init__(self, key_mgr: Optional[GroqKeyManager] = None):
        self.key_mgr = key_mgr or get_default_key_manager()
        self._lock = threading.Lock()
        self._history: Dict[str, List[Dict[str, Any]]] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._tailed_offsets: Dict[str, int] = {}

    def bind_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event: Dict[str, Any], *, override_experiment_id: Optional[str] = None) -> Dict[str, Any]:
        exp_id = str(override_experiment_id or event.get("experiment_id") or "")
        normalized = {
            "event_id": str(event.get("event_id") or uuid.uuid4().hex[:12]),
            "experiment_id": exp_id,
            "timestamp": str(event.get("timestamp") or datetime.now(timezone.utc).isoformat()),
            "event_type": str(event.get("event_type") or "info"),
            "agent_id": event.get("agent_id"),
            "payload": event.get("payload") or {},
        }
        sanitized = json.loads(self.key_mgr.sanitize_text(json.dumps(normalized, default=str)))

        with self._lock:
            buf = self._history.setdefault(exp_id, [])
            buf.append(sanitized)
            if len(buf) > 2000:
                del buf[: len(buf) - 2000]
            queues = list(self._subscribers.get(exp_id) or ())

        if queues and self._loop is not None and not self._loop.is_closed():
            for q in queues:
                try:
                    self._loop.call_soon_threadsafe(q.put_nowait, sanitized)
                except Exception:
                    pass
        return sanitized

    def get_history(self, experiment_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._history.get(experiment_id) or [])

    def subscribe(self, experiment_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(experiment_id, set()).add(q)
        return q

    def unsubscribe(self, experiment_id: str, q: asyncio.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(experiment_id)
            if subs and q in subs:
                subs.remove(q)

    def poll_jsonl_into_stream(self, parent_experiment_id: str, root_dir: Path) -> None:
        """Read any new lines from subprocess `*_events.jsonl` logs and broadcast them cleanly."""
        if not root_dir.exists():
            return
        for ev_file in sorted(root_dir.rglob("*_events.jsonl")):
            key = str(ev_file.resolve())
            offset = self._tailed_offsets.get(key, 0)
            try:
                content = ev_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if len(content) <= offset:
                continue
            chunk = content[offset:]
            self._tailed_offsets[key] = len(content)
            for line in chunk.splitlines():
                line_s = line.strip()
                if not line_s:
                    continue
                try:
                    ev = json.loads(line_s)
                    if isinstance(ev, dict):
                        self.publish(ev, override_experiment_id=parent_experiment_id)
                except Exception:
                    pass
