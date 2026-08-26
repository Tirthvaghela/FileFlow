from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from api.auth import COOKIE_NAME, decode_token
from api.websocket_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.cookies.get(COOKIE_NAME)
    user_id = decode_token(token) if token else None
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            # Dashboard doesn't need to send anything; just keep the
            # connection open and drain any client pings.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception:
        # A dead connection doesn't always surface as WebSocketDisconnect
        # (a lower-level transport error can too) -- clean it up here as
        # well instead of leaving a stale entry in
        # manager.active_connections that would otherwise only ever get
        # pruned by a future broadcast to this same user (see
        # ConnectionManager.broadcast's own stale-connection handling).
        manager.disconnect(websocket, user_id)
