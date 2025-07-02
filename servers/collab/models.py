from datetime import datetime

from pydantic import BaseModel
from typing import Any, Dict

class Vector2(BaseModel):
    xy: tuple[float, float]


class Vector3(BaseModel):
    xyz: tuple[float, float, float]


class Geometry(BaseModel):
    vertices: list[Vector3]
    indices: list[int]
    uvs: list[Vector2]
    color: list[Vector3]

class Cook(BaseModel):
    params: dict[str, Any]


class SessionInfo(BaseModel):
    session_id: str
    client_id: str
    created_at: datetime
    last_active: datetime
    props: Dict[str, Any] = {}
    state: str


class SessionCreate(BaseModel):
    session_id: str


class SessionJoin(BaseModel):
    session_id: str
    client_id: str


class Sync(BaseModel):
    state: str  # TODO: base64

class Update(BaseModel):
    update: str  # TODO base64
