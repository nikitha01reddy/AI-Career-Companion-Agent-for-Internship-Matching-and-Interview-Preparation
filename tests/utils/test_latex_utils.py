"""Unit tests for LaTeX escaping helpers."""

from app.utils.latex_utils import escape_latex, sanitize_url


class TestLatexUtils:
    """Escaping and URL sanitization."""

    def test_escape_special_characters(self) -> None:
        assert escape_latex("C++ & Python_3") == r"C++ \& Python\_3"

    def test_sanitize_https_url(self) -> None:
        assert sanitize_url("https://github.com/example") == "https://github.com/example"

    def test_rejects_unsafe_url(self) -> None:
        assert sanitize_url("javascript:alert(1)") == ""
