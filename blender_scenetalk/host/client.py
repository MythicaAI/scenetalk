from datetime import datetime
from typing import Awaitable, Callable

from pycrdt import Doc
from pydantic import BaseModel

from .ops import Ops, OpCall
from .timestamp import timestamp


class Client:
    def __init__(self, websocket, id, send_to_client: OpCall):
        self.websocket = websocket
        self.id = id
        self.send_to_client = send_to_client
        self.last_active: datetime = timestamp()
        self.authenticated = False

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        return self.id == other.id

    def set_checkpoint(self, checkpoint: bytes):
        self.checkpoint = checkpoint

    def updates(self, doc: Doc):
        doc.get_update(state=self.checkpoint)

    async def send(self, op: Ops, data: BaseModel):
       await self.send_to_client(op, data)
