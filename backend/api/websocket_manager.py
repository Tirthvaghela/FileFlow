import logging

from fastapi import WebSocket

logger = logging.getLogger("fileflow.ws")


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        await websocket.accept()
        self.active_connections.setdefault(user_id, []).append(websocket)

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        connections = self.active_connections.get(user_id)
        if connections and websocket in connections:
            connections.remove(websocket)
            if not connections:
                del self.active_connections[user_id]

    async def broadcast(self, payload: dict, user_id: int) -> None:
        """Deliver only to that user's own connected sockets -- one
        account's live activity never reaches another account's browser."""
        stale: list[WebSocket] = []
        for connection in self.active_connections.get(user_id, []):
            try:
                await connection.send_json(payload)
            except Exception:  # noqa: BLE001
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection, user_id)


manager = ConnectionManager()
