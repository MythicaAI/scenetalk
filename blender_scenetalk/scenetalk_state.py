from typing import Callable
from pycrdt import Doc, Map, TransactionEvent

doc = Doc()
scene = Map()
doc["scene"] = scene


def observe_changes(handle_doc_changes: Callable[[TransactionEvent], None]):
    doc.observe(handle_doc_changes)


def apply_remote_update(update: bytes):
    doc.apply_update(update)