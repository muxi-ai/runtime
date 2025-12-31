"""
Unit tests for text_cleaner utility functions.
"""

import pytest
from muxi.runtime.utils.text_cleaner import remove_invisible_characters, clean_response_text


class TestRemoveInvisibleCharacters:
    """Test cases for remove_invisible_characters function."""

    def test_empty_string(self):
        """Test that empty strings are handled correctly."""
        assert remove_invisible_characters("") == ""
        assert remove_invisible_characters(None) is None

    def test_normal_text(self):
        """Test that normal text is preserved."""
        text = "Hello, World! This is a test."
        assert remove_invisible_characters(text) == text

    def test_emojis_preserved(self):
        """Test that emojis are preserved."""
        text = "Hello 🌾😄 World! 🎉"
        assert remove_invisible_characters(text) == text

        # Test the dad joke example
        dad_joke = "Because **he was outstanding in his field!** 🌾😄"
        assert remove_invisible_characters(dad_joke) == dad_joke

    def test_zero_width_spaces(self):
        """Test removal of zero-width spaces."""
        # Zero-width space
        text = "Hello\u200bWorld"
        assert remove_invisible_characters(text) == "HelloWorld"

        # Zero-width non-joiner
        text = "Hello\u200cWorld"
        assert remove_invisible_characters(text) == "HelloWorld"

        # Zero-width joiner
        text = "Hello\u200dWorld"
        assert remove_invisible_characters(text) == "HelloWorld"

    def test_invisible_spaces(self):
        """Test removal of various invisible space characters."""
        # Non-breaking space
        text = "Hello\u00a0World"
        assert remove_invisible_characters(text) == "HelloWorld"

        # En space
        text = "Hello\u2002World"
        assert remove_invisible_characters(text) == "HelloWorld"

        # Em space
        text = "Hello\u2003World"
        assert remove_invisible_characters(text) == "HelloWorld"

        # Hair space
        text = "Hello\u200aWorld"
        assert remove_invisible_characters(text) == "HelloWorld"

    def test_mixed_invisible_characters(self):
        """Test removal of multiple types of invisible characters."""
        text = "Hello\u200b\u200c World\u00a0!\u2003Test\u200d"
        assert remove_invisible_characters(text) == "Hello World!Test"

    def test_preserves_normal_whitespace(self):
        """Test that normal whitespace is preserved."""
        text = "Hello World\n\tNew Line\rCarriage Return"
        assert remove_invisible_characters(text) == text

    def test_preserves_markdown(self):
        """Test that markdown formatting is preserved."""
        text = "# Header\n\n**Bold** and *italic*\n\n- List item"
        assert remove_invisible_characters(text) == text

    def test_complex_text_with_emojis_and_invisible(self):
        """Test complex text with both emojis and invisible characters."""
        text = "Hello\u200b 🌾 World\u200c! 😄\u00a0More\u2003text 🎉"
        expected = "Hello 🌾 World! 😄Moretext 🎉"
        assert remove_invisible_characters(text) == expected

    def test_line_and_paragraph_separators(self):
        """Test removal of line and paragraph separators."""
        # Line separator
        text = "Line1\u2028Line2"
        assert remove_invisible_characters(text) == "Line1Line2"

        # Paragraph separator
        text = "Para1\u2029Para2"
        assert remove_invisible_characters(text) == "Para1Para2"

    def test_word_joiner(self):
        """Test removal of word joiner character."""
        text = "No\u2060Break"
        assert remove_invisible_characters(text) == "NoBreak"

    def test_zero_width_no_break_space(self):
        """Test removal of zero-width no-break space (BOM)."""
        text = "\ufeffStart of text"
        assert remove_invisible_characters(text) == "Start of text"

    def test_real_world_llm_response(self):
        """Test cleaning a real-world LLM response."""
        text = "# Dad Joke Time!\u200b\n\nHey there!\u200c I'm glad you're in the mood\u00a0for humor.\n\n## Why did the scarecrow win?\n\nBecause **he was outstanding\u2003in his field!** 🌾😄"  # noqa: E501
        expected = "# Dad Joke Time!\n\nHey there! I'm glad you're in the moodfor humor.\n\n## Why did the scarecrow win?\n\nBecause **he was outstandingin his field!** 🌾😄"  # noqa: E501
        assert remove_invisible_characters(text) == expected

    def test_unicode_control_characters(self):
        """Test removal of Unicode control characters."""
        # Various control characters (except tab, newline, CR)
        text = "Text\x00with\x01various\x02control\x03chars"
        assert remove_invisible_characters(text) == "Textwithvariouscontrolchars"

        # But preserves tab, newline, CR
        text = "Text\twith\ntab\rand newlines"
        assert remove_invisible_characters(text) == text


class TestCleanResponseText:
    """Test cases for clean_response_text function."""

    def test_basic_cleaning(self):
        """Test basic response text cleaning."""
        text = "Hello\u200bWorld!"
        assert clean_response_text(text) == "HelloWorld!"

    def test_complex_response(self):
        """Test cleaning complex response with multiple issues."""
        text = "# Header\u200b\n\nContent\u00a0with\u2003spaces 🎉"
        expected = "# Header\n\nContentwithspaces 🎉"
        assert clean_response_text(text) == expected

    def test_preserves_important_content(self):
        """Test that important content is preserved."""
        text = "**Bold** *italic* 🌾😄 [link](url)"
        assert clean_response_text(text) == text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
