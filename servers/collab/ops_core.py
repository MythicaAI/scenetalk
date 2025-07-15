import logging
from typing import Any, Optional

from pydantic import BaseModel

from ops import OpGroup, Ops
from client import Client
from session import Session
from models import Cook, Geometry

log = logging.getLogger(__name__)
group = OpGroup("core")


@group.register(Ops.GEOMETRY)
def geometry(msg: Geometry, client: Client, session: Optional[Session]):
    log.info("geometry uploaded %s", msg)
    if session:
        session.cache_mesh(msg)
        session.broadcast(msg, exclude=client)

@group.register(Ops.COOK)
def cook(msg: Cook, client: Client, session: Optional[Session]):
    log.info("cooking %s, for %s, %s", msg, client, session)