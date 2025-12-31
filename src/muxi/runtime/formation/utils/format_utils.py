"""
Format conversion utilities for the Overlord.
"""


def convert_logging_format(schema_format: str) -> str:
    """
    Convert SCHEMA_GUIDE.md logging format to LoggingConfig format.

    Args:
        schema_format: Format from SCHEMA_GUIDE.md ('jsonl' or 'text')

    Returns:
        Format string for LoggingConfig
    """
    if schema_format == "jsonl":
        return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    elif schema_format == "text":
        return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    else:
        # Default format
        return "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
