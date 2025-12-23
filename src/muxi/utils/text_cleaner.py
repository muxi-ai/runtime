"""
Utility functions for cleaning text by removing invisible characters.
"""

import unicodedata


def remove_invisible_characters(text: str) -> str:
    """
    Remove invisible Unicode characters from text while preserving emojis and visible content.

    Removes:
    - Zero-width characters (ZWSP, ZWJ, ZWNJ)
    - Various invisible spaces and separators
    - Control characters
    - Format characters
    - Other invisible Unicode characters

    Preserves:
    - Regular text
    - Emojis
    - Normal whitespace (space, tab, newline)

    Args:
        text: Input text to clean

    Returns:
        Cleaned text with invisible characters removed
    """
    if not text:
        return text

    # Define invisible characters to remove
    # Based on https://invisible-characters.com/
    invisible_chars = [
        '\u200b',  # Zero-width space
        '\u200c',  # Zero-width non-joiner
        '\u200d',  # Zero-width joiner
        '\u2060',  # Word joiner
        '\ufeff',  # Zero-width no-break space
        '\u180e',  # Mongolian vowel separator
        '\u2000',  # En quad
        '\u2001',  # Em quad
        '\u2002',  # En space
        '\u2003',  # Em space
        '\u2004',  # Three-per-em space
        '\u2005',  # Four-per-em space
        '\u2006',  # Six-per-em space
        '\u2007',  # Figure space
        '\u2008',  # Punctuation space
        '\u2009',  # Thin space
        '\u200a',  # Hair space
        '\u205f',  # Medium mathematical space
        '\u3000',  # Ideographic space
        '\u00a0',  # Non-breaking space
        '\u2028',  # Line separator
        '\u2029',  # Paragraph separator
        '\u202f',  # Narrow no-break space
    ]

    # Create a translation table
    translator = str.maketrans({char: None for char in invisible_chars})

    # Remove invisible characters
    cleaned = text.translate(translator)

    # Also remove any other control characters except common ones (tab, newline, carriage return)
    # This uses Unicode categories to identify control characters
    result = []
    for char in cleaned:
        category = unicodedata.category(char)
        # Cc = Control characters, Cf = Format characters, Co = Private use, Cn = Unassigned
        if category in ('Cc', 'Cf', 'Co', 'Cn'):
            # Keep common whitespace characters
            if char in ('\t', '\n', '\r'):
                result.append(char)
            # Skip other control/format characters
        else:
            result.append(char)

    return ''.join(result)


def clean_response_text(text: str) -> str:
    """
    Clean response text for final output.

    This is a convenience wrapper that applies all necessary text cleaning
    for response outputs, including removing invisible characters.

    Args:
        text: Response text to clean

    Returns:
        Cleaned response text
    """
    # Remove invisible characters
    text = remove_invisible_characters(text)

    # Remove decorative separator lines (box drawing characters)
    # These sometimes appear when LLM adds visual separators
    import re
    text = re.sub(r'^[─━═┄┅┈┉\-_]{3,}\s*$', '', text, flags=re.MULTILINE)
    
    # Strip leading/trailing whitespace and normalize multiple newlines
    text = text.strip()
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text
