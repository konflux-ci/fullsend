"""Tests for the Unicode normalizer."""

import pytest
from scanners.unicode_normalizer import UnicodeNormalizer


@pytest.fixture
def normalizer():
    return UnicodeNormalizer()


class TestZeroWidthRemoval:
    def test_zero_width_space(self, normalizer):
        result = normalizer.normalize("r\u200bm")
        assert result.normalized == "rm"
        assert result.changed

    def test_zero_width_non_joiner(self, normalizer):
        result = normalizer.normalize("r\u200cm")
        assert result.normalized == "rm"

    def test_zero_width_joiner(self, normalizer):
        result = normalizer.normalize("r\u200dm")
        assert result.normalized == "rm"

    def test_bom(self, normalizer):
        result = normalizer.normalize("\ufefftext")
        assert result.normalized == "text"

    def test_multiple_zero_width(self, normalizer):
        result = normalizer.normalize("r\u200bm\u200c -r\u200df\u200b /")
        assert result.normalized == "rm -rf /"


class TestBidiOverrides:
    def test_rlo_removed(self, normalizer):
        result = normalizer.normalize("file\u202eexe.txt")
        assert result.normalized == "fileexe.txt"
        assert result.changed
        assert any(f.category == "bidi_override" for f in result.findings)

    def test_all_bidi_chars(self, normalizer):
        bidi_chars = "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
        result = normalizer.normalize(f"text{bidi_chars}more")
        assert result.normalized == "textmore"


class TestTagCharacters:
    def test_tag_chars_removed(self, normalizer):
        result = normalizer.normalize(
            "Clean\U000e0001\U000e0069\U000e0067\U000e006e\U000e006f\U000e0072\U000e0065"
        )
        assert result.normalized == "Clean"
        assert result.changed

    def test_tag_chars_decoded(self, normalizer):
        result = normalizer.normalize("text\U000e0068\U000e0065\U000e006c\U000e006c\U000e006f")
        tag_finding = next(f for f in result.findings if f.category == "tag_char")
        assert "hello" in tag_finding.description


class TestAnsiEscapes:
    def test_ansi_color_removed(self, normalizer):
        result = normalizer.normalize("normal \x1b[31mred\x1b[0m text")
        assert result.normalized == "normal red text"
        assert result.changed

    def test_ansi_disabled(self):
        n = UnicodeNormalizer(strip_ansi=False)
        result = n.normalize("normal \x1b[31mred\x1b[0m text")
        assert "\x1b[31m" in result.normalized


class TestNullBytes:
    def test_null_bytes_removed(self, normalizer):
        result = normalizer.normalize("rm\x00 -rf\x00 /")
        assert result.normalized == "rm -rf /"
        assert result.changed


class TestNFKC:
    def test_fullwidth_normalized(self, normalizer):
        # Fullwidth "rm" -> ASCII "rm"
        result = normalizer.normalize("\uff52\uff4d")
        assert result.normalized == "rm"
        assert result.changed

    def test_nfkc_disabled(self):
        n = UnicodeNormalizer(nfkc=False)
        result = n.normalize("\uff52\uff4d")
        assert result.normalized == "\uff52\uff4d"


class TestVariationSelectors:
    def test_variation_selectors_removed(self, normalizer):
        result = normalizer.normalize("a\ufe01b\ufe0fc")
        assert result.normalized == "abc"
        assert result.changed


class TestCleanText:
    def test_no_changes(self, normalizer):
        result = normalizer.normalize("This is perfectly normal text.")
        assert not result.changed
        assert result.normalized == "This is perfectly normal text."
        assert len(result.findings) == 0


class TestCombinedAttack:
    def test_multiple_techniques(self, normalizer):
        tag_chars = "\U000e0061\U000e0070\U000e0070\U000e0072\U000e006f\U000e0076\U000e0065"
        text = f"r\u200bm\u202e -rf /\x00{tag_chars}"
        result = normalizer.normalize(text)
        assert result.changed
        assert len(result.findings) >= 3  # zero_width + bidi + null + tag_char
        # All invisible chars should be gone
        assert "\u200b" not in result.normalized
        assert "\u202e" not in result.normalized
        assert "\x00" not in result.normalized
        assert "\U000e0061" not in result.normalized
