from datetime import datetime
from typing import Any, Dict

from session import Session
from client import Client
from ops import OpGroup, Ops
from pydantic import BaseModel

from ws_app import session_manager



group = OpGroup("session")

@group.register(Ops.SESSION_INFO)
async def handle_session_info(msg: SessionInfo, client: Client, session: Session):
    pass

@group.register(Ops.SESSION_JOIN)
async def handle_session_join(msg: SessionCreate, client: Client, session: Session):
    # Register client with session
    session = session_manager.register_client(client, msg.session_id)

    # Send session info
    session_data = session.build_info(msg.client_id)
    await client.send(Ops.SESSION_INFO, session_data)
