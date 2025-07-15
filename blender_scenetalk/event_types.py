import enum


class EventType(enum.Enum):
    """Event types are used internally to get work onto the main blender thread."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    STATUS = "status"
    GEOMETRY = "geometry"
    SESSION_INFO = "session_info"
    QUIT = "quit"
