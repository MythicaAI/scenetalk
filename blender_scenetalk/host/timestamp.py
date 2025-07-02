from datetime import datetime, timezone


def timestamp() -> datetime:
    """

    :rtype: object
    """
    return datetime.now(timezone.utc)

