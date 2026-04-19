"""
tests/test_pdf_processor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the PDF text extraction pipeline.

Tests use unittest.mock to avoid requiring real PDF files or Tesseract/PyMuPDF
binaries to be installed in the CI environment.

Run with:
    pytest backend/tests/test_pdf_processor.py -v
"""

from __future__ import annotations

import time
import types
import sys
import io
from collections import Counter
from unittest import mock
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


# ── Helpers to build lightweight fitz-document fakes ─────────────────────────

def _make_fitz_page(text: str) -> MagicMock:
    """Return a mock fitz.Page whose get_text() returns `text`."""
    page = MagicMock()
    page.get_text.return_value = text
    return page


def _make_fitz_doc(pages_text: list[str]) -> MagicMock:
    """Return a mock fitz.Document that iterates over fake pages."""
    pages = [_make_fitz_page(t) for t in pages_text]
    doc = MagicMock()
    doc.__iter__ = lambda self: iter(pages)
    # len() is also used occasionally
    doc.__len__ = lambda self: len(pages)
    doc.close = MagicMock()
    return doc


# ── Build a minimal fake fitz module ─────────────────────────────────────────

def _make_fitz_module(doc: MagicMock) -> types.ModuleType:
    fitz_mod = types.ModuleType("fitz")
    fitz_mod.open = MagicMock(return_value=doc)
    fitz_mod.Matrix = MagicMock(return_value=MagicMock())
    return fitz_mod


# ─────────────────────────────────────────────────────────────────────────────
# 1. Native PDF extraction tests
# ─────────────────────────────────────────────────────────────────────────────


class TestNativePDFExtraction:
    """PDF with searchable text — PyMuPDF path, no OCR."""

    def _run(self, pages_text: list[str]) -> str:
        doc = _make_fitz_doc(pages_text)
        fitz_mod = _make_fitz_module(doc)

        with patch.dict(sys.modules, {"fitz": fitz_mod}):
            from nlp import pdf_processor
            # Force reload so the patched module is used
            import importlib
            importlib.reload(pdf_processor)
            result = pdf_processor.extract_text_from_pdf(b"dummy-pdf-bytes")
        return result

    def test_single_page_returns_text(self):
        # String must be > OCR_CHAR_THRESHOLD (100 chars) to avoid triggering OCR fallback
        page_text = (
            "Python developer with 5 years of experience in machine learning, "
            "deep learning, and data engineering. Proficient in TensorFlow, PyTorch."
        )
        result = self._run([page_text])
        assert "Python" in result
        assert "machine learning" in result

    def test_multi_page_concatenated(self):
        # Each page string combined must exceed OCR_CHAR_THRESHOLD (100 chars)
        result = self._run([
            "Skills: Python, Docker, Kubernetes, FastAPI, PostgreSQL, Redis, AWS",
            "Experience: 3 years at Acme Corp working on scalable backend systems",
        ])
        assert "Python" in result
        assert "Docker" in result
        assert "Acme" in result

    def test_whitespace_normalised(self):
        """Multiple spaces / tabs should be collapsed."""
        noisy = "Python    developer\t\twith  lots  of   whitespace"
        result = self._run([noisy])
        # There should be no runs of 2+ spaces after cleaning
        assert "  " not in result

    def test_page_numbers_stripped(self):
        """Lines matching 'Page N of M' should be removed."""
        # Total chars must exceed OCR_CHAR_THRESHOLD (100) to avoid triggering OCR fallback
        result = self._run([
            "Page 1 of 3",
            "Java Spring Boot developer with expertise in microservices, REST APIs, "
            "and cloud infrastructure on AWS and GCP.",
        ])
        assert "Page 1 of 3" not in result
        assert "Java" in result

    def test_close_called_on_document(self):
        doc = _make_fitz_doc(["Some native text with enough characters to pass threshold."])
        fitz_mod = _make_fitz_module(doc)

        with patch.dict(sys.modules, {"fitz": fitz_mod}):
            from nlp import pdf_processor
            import importlib
            importlib.reload(pdf_processor)
            pdf_processor.extract_text_from_pdf(b"dummy")

        doc.close.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 2. OCR fallback tests (scanned PDF)
# ─────────────────────────────────────────────────────────────────────────────


class TestScannedPDFOCRFallback:
    """PDF with no native text — OCR path should activate."""

    def _run_with_ocr(self, ocr_text: str) -> str:
        # Scanned doc: pages return empty / very short text
        doc = _make_fitz_doc([""])  # zero native chars → triggers OCR
        fitz_mod = _make_fitz_module(doc)

        # Fake pixmap
        pix = MagicMock()
        pix.width = 100
        pix.height = 100
        pix.samples = b"\xff" * (100 * 100 * 3)
        doc.__iter__ = lambda self: iter([_make_fitz_page("")])
        # Override get_pixmap on the page
        page = _make_fitz_page("")
        page.get_pixmap = MagicMock(return_value=pix)
        doc.__iter__ = lambda self: iter([page])

        # Patch pytesseract and Pillow
        pytesseract_mod = types.ModuleType("pytesseract")
        pytesseract_mod.image_to_string = MagicMock(return_value=ocr_text)

        pil_mod = types.ModuleType("PIL")
        pil_image_mod = types.ModuleType("PIL.Image")
        fake_image = MagicMock()
        pil_image_mod.frombytes = MagicMock(return_value=fake_image)
        pil_mod.Image = pil_image_mod

        with patch.dict(
            sys.modules,
            {
                "fitz": fitz_mod,
                "pytesseract": pytesseract_mod,
                "PIL": pil_mod,
                "PIL.Image": pil_image_mod,
            },
        ):
            from nlp import pdf_processor
            import importlib
            importlib.reload(pdf_processor)
            result = pdf_processor.extract_text_from_pdf(b"dummy-scanned-pdf")

        return result

    def test_ocr_text_returned(self):
        result = self._run_with_ocr("React developer with TypeScript skills")
        assert "React" in result

    def test_empty_scanned_page_returns_empty_string(self):
        result = self._run_with_ocr("   \n\n  ")
        assert result.strip() == ""

    def test_is_scanned_heuristic_triggers_for_low_char_count(self):
        """Directly test the _is_scanned helper."""
        from nlp import pdf_processor
        import importlib

        # Build a doc with tiny text (below threshold)
        short_doc = _make_fitz_doc(["ab"])  # 2 chars < 100 threshold
        long_doc = _make_fitz_doc(["x" * 500])

        importlib.reload(pdf_processor)
        assert pdf_processor._is_scanned(short_doc) is True
        assert pdf_processor._is_scanned(long_doc) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Text cleaning tests
# ─────────────────────────────────────────────────────────────────────────────


class TestCleanText:
    """Unit tests for the _clean_text helper (no mocking needed)."""

    def setup_method(self):
        from nlp import pdf_processor
        import importlib
        importlib.reload(pdf_processor)
        self.clean = pdf_processor._clean_text

    def test_collapse_spaces(self):
        assert "  " not in self.clean("hello   world")

    def test_strip_page_number(self):
        text = "Skills\nPage 1 of 5\nExperience"
        result = self.clean(text)
        assert "Page 1 of 5" not in result
        assert "Skills" in result

    def test_strip_numeric_page_marker(self):
        text = "Education\n1/3\nProjects"
        result = self.clean(text)
        assert "1/3" not in result

    def test_strip_repeated_header(self):
        # A line repeated ≥3 times should be stripped
        repeated_line = "JOHN DOE RESUME"
        text = "\n".join([repeated_line, "Skills: Python", repeated_line, "Education", repeated_line])
        result = self.clean(text)
        assert result.count(repeated_line) == 0

    def test_collapse_blank_lines(self):
        text = "Line1\n\n\n\n\nLine2"
        result = self.clean(text)
        assert "\n\n\n" not in result

    def test_leading_trailing_whitespace_stripped(self):
        result = self.clean("   hello world   ")
        assert result == result.strip()

    def test_tabs_replaced(self):
        result = self.clean("col1\tcol2\tcol3")
        assert "\t" not in result


# ─────────────────────────────────────────────────────────────────────────────
# 4. Performance test (< 5s for small doc)
# ─────────────────────────────────────────────────────────────────────────────


class TestPerformance:
    """Extraction must complete within 5 seconds for a standard resume."""

    def test_extraction_time_under_5_seconds(self):
        # Simulate a 2-page native PDF
        pages = [
            "Python Developer with 5 years of experience in backend systems. " * 40,
            "Skills: Docker, Kubernetes, PostgreSQL, FastAPI, AWS. " * 40,
        ]
        doc = _make_fitz_doc(pages)
        fitz_mod = _make_fitz_module(doc)

        with patch.dict(sys.modules, {"fitz": fitz_mod}):
            from nlp import pdf_processor
            import importlib
            importlib.reload(pdf_processor)

            start = time.perf_counter()
            pdf_processor.extract_text_from_pdf(b"dummy")
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Extraction took {elapsed:.2f}s, expected < 5s"
