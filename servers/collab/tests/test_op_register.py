from pydantic import BaseModel
from ops import OpGroup
from sessions import Client, Session


class FooMessage(BaseModel):
    pass

class BarMessage(BaseModel):
    pass

def validate_execution(msg: BaseModel, client: Client, session: Session | None):
    return {
        'valid_msg_type': type(msg) == BaseModel,
        'valid_client': type(client) == Client and client is not None,
        'valid_session': type(session) == Session and session is not None,
    }

module_ops = OpGroup("test-module")

@module_ops.register()
def module_foo(msg: FooMessage, client: Client, session: Session):
    validate_execution(msg, client, session)

def test_register_module():
    assert len(module_ops.ops) == 1

def test_register_with_no_session():
    ops = OpGroup("test")
    @ops.register()
    def foo(msg: FooMessage, client: Client):
        validate_execution(msg, client, None)

def test_register_with_session():
    ops = OpGroup("test")
    @ops.register()
    def foo(msg: FooMessage, client: Client, session: Session):
        validate_execution(msg, client, session)

def test_register_two():
    ops = OpGroup("test")
    @ops.register()
    def foo(msg: FooMessage, client: Client, session: Session):
        validate_execution(msg, client, session)
    @ops.register()
    def bar(msg: BarMessage, client: Client, session: Session):
        validate_execution(msg, client, session)
    assert len(ops.ops) == 2