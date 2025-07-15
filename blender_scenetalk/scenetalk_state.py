from typing import Callable
from pycrdt import Doc, Map, TransactionEvent

doc = Doc()
scene = Map()
origin = None
doc["scene"] = scene


def observe_changes(handle_doc_changes: Callable[[TransactionEvent], None]):
    doc.observe(handle_doc_changes)


def apply_remote_update(origin: str, update: bytes):
    doc.apply_update(update, origin=origin)


def set_remote_state(state: bytes):
    if len(state) == 0:
        return
    doc.get_update(state)
