import base64
from typing import Optional

from ops import OpGroup, Ops
from session import Session
from client import Client
from models import Sync, Update

group = OpGroup("sync")


@group.register(Ops.SYNC_STATE)
def handle_sync_state(msg: Sync, client: Client, session: Optional[Session]):
    bdata = base64.b64decode(msg.state, validate=True)
    client.set_checkpoint(bdata)

    if session:
        update = session.doc.get_update(bdata)
        if update:
            update_encoded = base64.b64encode(update).decode('utf-8')
            client.send(Update(update=update_encoded))


@group.register(Ops.SYNC_UPDATE)
def handle_sync_update(msg: Update, client: Client, session: Optional[Session]):
    if session:
        session.apply_update(client.id, msg.update)
        session.broadcast(msg, exclude=client)
