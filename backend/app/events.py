"""
WebSocket Connection Manager for SWARMFORGE live event streaming.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Union

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages active WebSocket connections and broadcasts JSON events.
    Silently drops dead sockets upon send failures.
    """

    def __init__(self) -> None:
        self.active_connections: List[WebSocket] = []
        self._lock: asyncio.Lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
        logger.info("WebSocket client connected. Active sockets: %d", len(self.active_connections))

    def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a WebSocket connection."""
        try:
            self.active_connections.remove(websocket)
            logger.info(
                "WebSocket client disconnected. Active sockets: %d",
                len(self.active_connections),
            )
        except ValueError:
            pass

    async def broadcast(self, message: Union[Dict[str, Any], str, List[Any]]) -> None:
        """
        Broadcast a JSON message to all active WebSocket clients.
        Silently drops dead sockets upon send failures.
        """
        async with self._lock:
            sockets_to_send = list(self.active_connections)

        if not sockets_to_send:
            return

        dead_sockets: List[WebSocket] = []
        for ws in sockets_to_send:
            try:
                if isinstance(message, (dict, list)):
                    await ws.send_json(message)
                else:
                    await ws.send_text(str(message))
            except Exception as ex:
                logger.debug("Silently dropping dead socket %s: %s", ws, ex)
                dead_sockets.append(ws)

        if dead_sockets:
            async with self._lock:
                for dead_ws in dead_sockets:
                    try:
                        self.active_connections.remove(dead_ws)
                    except ValueError:
                        pass
            logger.info(
                "Dropped %d dead sockets. Remaining active: %d",
                len(dead_sockets),
                len(self.active_connections),
            )
