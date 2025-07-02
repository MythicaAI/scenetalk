import json
from typing import Optional
from uuid import uuid4

import wsproto
from fastapi import Cookie, Depends, FastAPI, WebSocket, APIRouter, Query, HTTPException
import logging

from pydantic import BaseModel
from starlette.status import WS_1011_INTERNAL_ERROR
from starlette.websockets import WebSocketState

from .ops import Ops, OpGroup
from .session_manager import SessionManager
from .client import Client

log = logging.getLogger(__name__)

router = APIRouter()
app = FastAPI()
app.include_router(router)

# Create the session manager
session_manager = SessionManager()

CacheKey = str
CacheKeyList = list[CacheKey]

# FastAPI dependency for session handling
async def get_session_id(
        session_id: Optional[str] = Cookie(None),
        session_query: Optional[str] = Query(None, alias="session")
) -> Optional[str]:
    # Priority: query param > cookie > None (creates new)
    return session_query or session_id

@router.websocket("/cache/geo")
async def get_cache_geo(
        session_id: Optional[str] = Depends(get_session_id)) -> CacheKeyList:
    pass

@router.websocket("/cache/tex")
async def get_cache_tex(
        session_id: Optional[str] = Depends(get_session_id)) -> CacheKeyList:
    return CacheKeyList()

@router.websocket("/cache/mat")
async def get_cache_mat(
        session_id: Optional[str] = Depends(get_session_id)) -> CacheKeyList:
    return CacheKeyList()

@router.websocket("/ws")
async def websocket_endpoint(
        websocket: WebSocket,
        session_id: Optional[str] = Depends(get_session_id)):

    websocket.ping_interval = 30
    await websocket.accept()

    async def send_to_client(op: Ops, msg: BaseModel) -> None:
        close = None
        try:
            msg = { "op": str(op), "data": msg.model_dump(mode='json')}
            text = json.dumps(msg)
            await websocket.send_text(text)
        except Exception as e:
            log.exception("failed to send to client", exc_info=e)
            close = (WS_1011_INTERNAL_ERROR, "failed to send to client")

        if close:
            await websocket.close(*close)

    # wrap the client send routine and identity
    client = Client(websocket, str(uuid4()), send_to_client)
    session = None
    if session_id:
        session = session_manager.register_client(client, session_id)
        await client.send(Ops.SESSION_INFO, session.build_info(client.id))

    # Log connection
    log.info(f"Client connected with temporary identity %s", client.id)
    try:
        while True:
            data = await websocket.receive_text()
            log.info(data)

            try:
                msg = json.loads(data)
                op = msg.get("op")
                if not op:
                    log.error("message missing 'op' field")
                    continue
                parts = op.split('/')
                if parts == 2:
                    group, op_name = parts
                else:
                    group = 'core'
                    op_name = parts[0]

                # look up operator
                op_group = OpGroup.find(group)
                if not op_group:
                    raise HTTPException(400, f"unknown op group: {group}")

                op = op_group.ops.get(op_name)
                if not op:
                    log.warning("unknown op: %s, in group: %s",
                                op, group)
                    raise HTTPException(400, f"unknown op: {op} in group: {group}")
            except json.JSONDecodeError as e:
                print(f"JSON error {e}")
    except Exception as e:
        log.exception("Client error", exc_info=e)
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
    finally:
        session_manager.unregister_client(client)