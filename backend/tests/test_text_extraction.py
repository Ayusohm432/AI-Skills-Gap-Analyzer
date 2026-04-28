"""
tests/test_text_extraction.py
==============================
Unit tests for the unified text-extraction pipeline.

Covers:
  1. TXT processor  (extract_text_from_txt)
  2. Unified dispatcher  (extract_text / _resolve_extension)

All tests use stubs/mocks; no real PDF/DOCX/Tesseract dependencies required.

Run with:
    pytest backend/tests/test_text_extraction.py -v
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# 1. TXT Processor
# =============================================================================

class TestTxtProcessor:
    """Tests for nlp/txt_processor.py — extract_text_from_txt()."""

    def _call(self, data: bytes) -> str:
        import nlp.txt_processor as mod
        importlib.reload(mod)
        return mod.extract_text_from_txt(data)

    # ── Encoding ──────────────────────────────────────────────────────────────

    def test_utf8_text_decoded_correctly(self):
        text = "Python developer with 5 years of experience."
        result = self._call(text.encode("utf-8"))
        assert "Python" in result
        assert "experience" in result

    def test_latin1_fallback_decodes_non_utf8_bytes(self):
        # 0xe9 = 'é' in latin-1 but is invalid UTF-8 as a standalone byte
        raw = b"D\xe9veloppeur Python avec exp\xe9rience"
        result = self._call(raw)
        # Should not raise; content should be non-empty
        assert len(result) > 0

    def test_empty_bytes_returns_empty_string(self):
        result = self._call(b"")
        assert result == ""

    def test_whitespace_only_returns_empty_string(self):
        result = self._call(b"   \n\t\n   ")
        assert result.strip() == ""

    # ── Cleaning ──────────────────────────────────────────────────────────────

    def test_multiple_spaces_collapsed(self):
        result = self._call(b"Python    developer   with   extra   spaces")
        assert "  " not in result

    def test_tabs_replaced(self):
        result = self._call(b"Skill\tLevel\tYears")
        assert "\t" not in result

    def test_page_number_lines_stripped(self):
        data = b"Page 1 of 3\nPython backend developer with expertise in FastAPI and Docker."
        result = self._call(data)
        assert "Page 1 of 3" not in result
        assert "Python" in result

    def test_leading_trailing_whitespace_stripped(self):
        result = self._call(b"   Senior Engineer   ")
        assert result == result.strip()

    def test_unicode_content_preserved(self):
        text = "Développeur Python — Île-de-France"
        result = self._call(text.encode("utf-8"))
        assert "Développeur" in result

    def test_multiline_text_preserved(self):
        data = b"Name: Alice\nSkills: Python, Docker\nExperience: 4 years"
        result = self._call(data)
        assert "Alice" in result
        assert "Docker" in result
        assert "Experience" in result


# =============================================================================
# 2. Unified Dispatcher — _resolve_extension
# =============================================================================

class TestResolveExtension:
    """Tests for the private _resolve_extension() helper."""

    def _fn(self):
        import nlp.engine as mod
        importlib.reload(mod)
        return mod._resolve_extension

    def test_pdf_mime_returns_pdf(self):
        assert self._fn()("application/pdf", "") == "pdf"

    def test_docx_mime_returns_docx(self):
        assert self._fn()(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ""
        ) == "docx"

    def test_doc_mime_returns_docx(self):
        assert self._fn()("application/msword", "") == "docx"

    def test_txt_mime_returns_txt(self):
        assert self._fn()("text/plain", "") == "txt"

    def test_mime_takes_priority_over_filename(self):
        # MIME says PDF but filename says .txt — MIME wins
        assert self._fn()("application/pdf", "resume.txt") == "pdf"

    def test_unknown_mime_falls_back_to_pdf_filename(self):
        assert self._fn()("", "resume.pdf") == "pdf"

    def test_unknown_mime_falls_back_to_docx_filename(self):
        assert self._fn()("", "resume.docx") == "docx"

    def test_doc_extension_normalised_to_docx(self):
        assert self._fn()("", "resume.doc") == "docx"

    def test_unknown_mime_falls_back_to_txt_filename(self):
        assert self._fn()("", "notes.txt") == "txt"

    def test_no_mime_no_filename_returns_empty(self):
        assert self._fn()("", "") == ""

    def test_unsupported_mime_no_filename_returns_empty(self):
        assert self._fn()("image/png", "") == ""

    def test_mime_matching_is_case_insensitive(self):
        assert self._fn()("Application/PDF", "") == "pdf"


# =============================================================================
# 3. Unified Dispatcher — extract_text() routing
# =============================================================================

class TestExtractTextDispatcher:
    """Tests for extract_text() — verifies it calls the right processor."""

    def _run(self, content_type: str, filename: str = "", data: bytes = b"x") -> str:
        """Patch all three processors and call extract_text()."""
        import nlp.engine as mod
        importlib.reload(mod)

        with (
            patch.object(mod, "extract_text_from_pdf",  return_value="pdf_result")  as pdf_mock,
            patch.object(mod, "extract_text_from_docx", return_value="docx_result") as docx_mock,
            patch.object(mod, "extract_text_from_txt",  return_value="txt_result")  as txt_mock,
        ):
            result = mod.extract_text(data, content_type=content_type, filename=filename)
            return result, pdf_mock, docx_mock, txt_mock

    def test_pdf_mime_calls_pdf_processor(self):
        result, pdf, docx, txt = self._run("application/pdf")
        pdf.assert_called_once()
        docx.assert_not_called()
        txt.assert_not_called()
        assert result == "pdf_result"

    def test_docx_mime_calls_docx_processor(self):
        result, pdf, docx, txt = self._run(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        docx.assert_called_once()
        pdf.assert_not_called()
        txt.assert_not_called()
        assert result == "docx_result"

    def test_msword_mime_calls_docx_processor(self):
        result, pdf, docx, txt = self._run("application/msword")
        docx.assert_called_once()
        assert result == "docx_result"

    def test_txt_mime_calls_txt_processor(self):
        result, pdf, docx, txt = self._run("text/plain")
        txt.assert_called_once()
        pdf.assert_not_called()
        docx.assert_not_called()
        assert result == "txt_result"

    def test_unknown_mime_with_pdf_filename_calls_pdf(self):
        result, pdf, docx, txt = self._run("", filename="resume.pdf")
        pdf.assert_called_once()
        assert result == "pdf_result"

    def test_unknown_mime_with_docx_filename_calls_docx(self):
        result, pdf, docx, txt = self._run("", filename="resume.docx")
        docx.assert_called_once()
        assert result == "docx_result"

    def test_unknown_mime_with_txt_filename_calls_txt(self):
        result, pdf, docx, txt = self._run("", filename="notes.txt")
        txt.assert_called_once()
        assert result == "txt_result"

    def test_unsupported_format_returns_empty_string(self):
        result, pdf, docx, txt = self._run("image/png", filename="photo.png")
        pdf.assert_not_called()
        docx.assert_not_called()
        txt.assert_not_called()
        assert result == ""

    def test_no_mime_no_filename_returns_empty_string(self):
        result, pdf, docx, txt = self._run("", filename="")
        assert result == ""

    def test_raw_bytes_passed_through_to_processor(self):
        import nlp.engine as mod
        importlib.reload(mod)
        captured = {}
        with patch.object(mod, "extract_text_from_pdf", side_effect=lambda b: captured.update({"b": b}) or "ok"):
            mod.extract_text(b"hello world", content_type="application/pdf")
        assert captured["b"] == b"hello world"


# =============================================================================
# 4. Performance — dispatcher overhead is negligible (<0.1 s)
# =============================================================================

class TestDispatcherPerformance:
    """The dispatcher itself adds no measurable overhead."""

    def test_dispatch_overhead_under_100ms(self):
        import time
        import nlp.engine as mod
        importlib.reload(mod)

        with patch.object(mod, "extract_text_from_txt", return_value="ok"):
            data = b"Python developer " * 1000
            start = time.perf_counter()
            mod.extract_text(data, content_type="text/plain")
            elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"Dispatcher took {elapsed:.4f}s, expected <0.1s"
