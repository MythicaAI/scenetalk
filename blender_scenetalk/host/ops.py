# Dictionary to store registered operator functions
from enum import Enum
from typing import Awaitable, Callable, Dict, Optional, Self, Type

from pydantic import BaseModel

class Ops(Enum):
    COOK = "cook"
    GEOMETRY = "geometry"
    SYNC_UPDATE = "sync/update"
    SYNC_STATE = "sync/state"
    SESSION_INFO = "session/info"
    SESSION_JOIN = "session/join"


# Pydantic model for message validation
class OperatorMessage(BaseModel):
    operation: str
    data: Optional[dict]

op_groups = {}


OpCall = Callable[[Ops, BaseModel], Awaitable[None]]

class OpGroup:
    def __init__(self, name: str):
        """Initialize an OpGroup with a name and operator registry."""
        self.name = name
        self.ops: Dict[str, OpCall] = {}
        op_groups[name] = self

    @staticmethod
    def find(name: str) -> Type["OpGroup"] | None:
        return op_groups.get(name)

    def execute(self, json_document: dict, client, session):
        """
        Executes an operator function based on a JSON document.

        Args:
            json_document (dict): The JSON document containing 'op' and 'data'.
            client: The client instance (if required by the operator function).
            session: The session instance (if required by the operator function).

        Returns:
            The result of the operator function execution.

        Raises:
            ValueError: If the operator is not found or if the JSON structure is invalid.
        """
        # Validate the JSON document structure using Pydantic
        msg = OperatorMessage(**json_document)

        # Extract the operation name and find the corresponding function
        operator_func = self.ops.get(msg.operation)
        if not operator_func:
            raise ValueError(f"Operator '{msg.operation}' not found in group '{self.name}'.")

        # Ensure the callable is correctly invoked with required arguments
        return operator_func(msg=msg, client=client, session=session)

    def register(self, name: Ops):
        """
        Method to register an operator function.

        Args:
            name (str, optional): The name of the operator. Defaults to the function name if not provided.
        """

        def decorator(func):
            inferred_name = name or func.__name__
            annotations = func.__annotations__

            msg_type = type(annotations.get('msg'))

            client_required = 'client' in annotations and \
                                       annotations[
                                           'client'].__name__ == 'Client'
            session_required = 'session' in annotations and \
                                        annotations[
                                            'session'].__name__ == 'Session'

            async def wrapper(*args, **kwargs):
                # Validate message using the Pydantic structure
                data: msg_type = msg_type(**kwargs.get('data'))
                if not data:
                    raise ValueError("Invalid message data.")

                # Ensure client and session requirements are met
                client = kwargs.get('client')
                session = kwargs.get('session')

                if client_required and client is None:
                    raise ValueError("Client is required but not provided.")
                if session_required and session is None:
                    raise ValueError("Session is required but not provided.")

                return await func(*args, **kwargs)

            # Add the operator to the registry
            self.ops[inferred_name] = wrapper
            return wrapper

        return decorator
