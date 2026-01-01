"""
Network-related utilities for the Overlord.
"""


def detect_stream_protocol(destination: str) -> str:
    """
    Detect stream protocol from destination URL.

    Args:
        destination: Stream destination URL

    Returns:
        Detected protocol string
    """
    if destination.startswith(("https://", "http://")):
        return "webhook"
    elif destination.startswith(("tcp://", "tcps://", "ipc://", "ipcs://")):
        return "zmq"
    elif destination.startswith(("ws://", "wss://")):
        return "websocket"
    else:
        return "zmq"  # Default fallback
