import json
from typing import Optional
from uuid import uuid4

from fastapi import Cookie, Depends, WebSocket, APIRouter, Query
import logging

from starlette.websockets import WebSocketState

from sessions import SessionManager

log = logging.getLogger(__name__)

router = APIRouter()

# Create the session manager
session_manager = SessionManager()


# FastAPI dependency for session handling
async def get_session_id(
        session_id: Optional[str] = Cookie(None),
        session_query: Optional[str] = Query(None, alias="session")
) -> Optional[str]:
    # Priority: query param > cookie > None (creates new)
    return session_query or session_id

@router.websocket("/ws")
async def websocket_endpoint(
        websocket: WebSocket,
        session_id: Optional[str] = Depends(get_session_id)):

    websocket.ping_interval = 30
    await websocket.accept()

    # Generate client ID
    client_id = str(uuid4())

    # Create or join session
    if not session_id or session_id not in session_manager.sessions:
        session_id = session_manager.create_session(session_id)
        is_new_session = True
    else:
        is_new_session = False

    async def send_to_client(msg: object) -> None:
        await websocket.send_text(json.dumps(msg))

    # Register client with session
    session_manager.register_client(client_id, session_id, send_to_client)

    # Send session info to client

    # Log connection
    log.info(f"Client connected", extra={"session_id": session_id,})
    try:
        # Send session info
        await websocket.send_json({
            "op": "session_info",
            "session_id": session_id,
            "client_id": client_id,
            "is_new_session": is_new_session
        })

        while True:
            data = await websocket.receive_text()
            log.info(data)

            try:
                msg = json.loads(data)
                op = msg.get("op")
                if op and op == "update":
                    await session_manager.broadcast_to_session(
                        session_id,
                        msg,
                        exclude_client=client_id)
            except json.JSONDecodeError as e:
                print(f"JSON error {e}")
    except Exception as e:
        print(f"Error: {e}")
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
    finally:
        session_manager.unregister_client(client_id)