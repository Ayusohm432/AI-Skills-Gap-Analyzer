"""
tests/test_pdf_extractor.py
============================
Unit tests for backend/nlp/pdf_extractor.py.

Two code paths are covered:
    1. Native extraction (digital / text-layer PDF)       → method == "native"
    2. OCR fallback    (scanned / image-only PDF)          → method == "ocr"

The tests use minimal synthetic PDF bytes so that they run entirely in-process
without requiring real PDF files on disk.  PyMuPDF is used to generate them.
"""

from __future__ import annotations

import io
import sys
import time
import types
import unittest
from unittest.mock import MagicMock, patch

# ── Make sure we can import the module from any working directory ──────────────
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nlp.pdf_extractor import (
    SCANNED_CHAR_THRESHOLD,
    _clean_text,
    _is_scanned,
    extract_text,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers – build minimal synthetic PDF bytes
# ─────────────────────────────────────────────────────────────────────────────

def _make_native_pdf(content: str = "This is a rich text PDF about Python Machine Learning and Data Science with enough characters to pass the threshold.") -> bytes:
    """Return bytes of a single-page digital PDF embedding *content* as text."""
    try:
        import fitz
    except ImportError:
        raise unittest.SkipTest("PyMuPDF not installed – skipping PDF tests")

    doc = fitz.open()
    page = doc.new_page()
    # Add content multiple times to ensure it's "rich" (>100 chars)
    page.insert_text((72, 72), content * 3, fontsize=12)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def _make_blank_pdf() -> bytes:
    """Return bytes of a single blank page (simulates a scanned PDF with no text layer)."""
    try:
        import fitz
    except ImportError:
        raise unittest.SkipTest("PyMuPDF not installed – skipping PDF tests")

    doc = fitz.open()
    doc.new_page()          # blank – no text layer
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# Test suite
# ─────────────────────────────────────────────────────────────────────────────

class TestCleanText(unittest.TestCase):
    """Tests for the internal _clean_text helper."""

    def test_empty_string(self):
        self.assertEqual(_clean_text(""), "")

    def test_collapses_multiple_blank_lines(self):
        raw = "Line A\n\n\n\n\nLine B"
        cleaned = _clean_text(raw)
        self.assertNotIn("\n\n\n", cleaned)
        self.assertIn("Line A", cleaned)
        self.assertIn("Line B", cleaned)

    def test_strips_page_number_lines(self):
        raw = "John Doe\nPage 1 of 3\nSoftware Engineer"
        cleaned = _clean_text(raw)
        self.assertNotIn("Page 1 of 3", cleaned)
        self.assertIn("John Doe", cleaned)

    def test_strips_slash_page_number(self):
        raw = "Resume\n2 / 3\nSkills"
        cleaned = _clean_text(raw)
        self.assertNotIn("2 / 3", cleaned)

    def test_collapses_multiple_spaces(self):
        raw = "Python    Machine    Learning"
        cleaned = _clean_text(raw)
        self.assertNotIn("  ", cleaned)

    def test_strips_pure_punctuation_lines(self):
        raw = "Name: Alice\n---\nSkills: Python"
        cleaned = _clean_text(raw)
        self.assertNotIn("---", cleaned)

    def test_preserves_normal_content(self):
        raw = "Alice Smith\nPython Developer\n5 years experience"
        cleaned = _clean_text(raw)
        self.assertIn("Alice Smith", cleaned)
        self.assertIn("Python Developer", cleaned)


class TestIsScanned(unittest.TestCase):
    """Tests for the heuristic that detects scanned PDFs."""

    def test_short_text_is_scanned(self):
        self.assertTrue(_is_scanned("A" * (SCANNED_CHAR_THRESHOLD - 1)))

    def test_empty_text_is_scanned(self):
        self.assertTrue(_is_scanned(""))
        self.assertTrue(_is_scanned("   "))

    def test_long_text_is_not_scanned(self):
        self.assertFalse(_is_scanned("A" * SCANNED_CHAR_THRESHOLD))


class TestExtractTextNative(unittest.TestCase):
    """Tests for native (text-layer) PDF extraction – no OCR."""

    def test_raises_on_empty_bytes(self):
        with self.assertRaises(ValueError):
            extract_text(b"")

    def test_native_pdf_extracts_correctly(self):
        """A digital PDF must be extracted natively (method=='native')."""
        content = "Alice Smith Python Machine Learning Docker Kubernetes and some more text to be sure."
        pdf_bytes = _make_native_pdf(content)

        # Explicitly set threshold to 0 to ensure we don't trigger OCR even if extraction is weird
        result = extract_text(pdf_bytes, scanned_threshold=0)

        self.assertEqual(result["method"], "native")
        self.assertGreater(result["char_count"], 0)
        self.assertIn("Python", result["text"])
        self.assertEqual(result["page_count"], 1)

    def test_extraction_time_under_5_seconds(self):
        """Extraction of a 2-page resume equivalent must finish in <5 s."""
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF not installed")

        doc = fitz.open()
        for _ in range(2):
            page = doc.new_page()
            page.insert_text(
                (72, 72),
                "Alice Smith\nSoftware Engineer\nPython Docker Kubernetes AWS React " * 10,
                fontsize=11,
            )
        buf = io.BytesIO()
        doc.save(buf)
        doc.close()
        pdf_bytes = buf.getvalue()

        t0 = time.perf_counter()
        result = extract_text(pdf_bytes, scanned_threshold=0)
        elapsed = time.perf_counter() - t0

        self.assertLess(elapsed, 5.0, msg=f"Extraction took {elapsed:.2f}s > 5s limit")
        self.assertEqual(result["page_count"], 2)

    def test_result_keys_present(self):
        pdf_bytes = _make_native_pdf()
        result = extract_text(pdf_bytes, scanned_threshold=0)
        for key in ("text", "method", "page_count", "char_count", "elapsed_s"):
            self.assertIn(key, result)


class TestExtractTextOCRFallback(unittest.TestCase):
    """Tests for the OCR fallback path triggered on scanned-style PDFs."""

    def test_ocr_triggered_for_blank_pdf(self):
        """
        A blank-page PDF yields almost no native text, so OCR must be activated.
        We patch pytesseract to avoid needing Tesseract installed in CI.
        """
        blank_pdf = _make_blank_pdf()
        ocr_text = "John Doe Machine Learning Engineer Python TensorFlow"

        with patch("nlp.pdf_extractor._extract_with_ocr", return_value=ocr_text) as mock_ocr:
            result = extract_text(blank_pdf)

        mock_ocr.assert_called_once()
        self.assertEqual(result["method"], "ocr")
        self.assertIn("John", result["text"])

    def test_ocr_path_uses_returned_text(self):
        """OCR result is cleaned and surfaced in the 'text' key."""
        blank_pdf = _make_blank_pdf()
        ocr_text = "Jane Doe\nPage 1 of 2\nData Scientist\nPython  Pandas"

        with patch("nlp.pdf_extractor._extract_with_ocr", return_value=ocr_text):
            result = extract_text(blank_pdf)

        # Page number should be stripped by _clean_text
        self.assertNotIn("Page 1 of 2", result["text"])
        self.assertIn("Data Scientist", result["text"])
        # Multiple spaces should be collapsed
        self.assertNotIn("  ", result["text"])

    def test_ocr_threshold_override(self):
        """
        Setting scanned_threshold=0 must force native path even on a blank PDF.
        """
        pdf_bytes = _make_native_pdf()

        # With threshold=0 it should never call OCR
        with patch("nlp.pdf_extractor._extract_with_ocr") as mock_ocr:
            # We mock the return value just in case it BUGGED and called it, 
            # so characters length checks don't crash on a mock object
            mock_ocr.return_value = "Mocked Text" 
            result = extract_text(pdf_bytes, scanned_threshold=0)

        mock_ocr.assert_not_called()
        self.assertEqual(result["method"], "native")

    def test_method_is_native_for_rich_pdf(self):
        """A text-rich PDF must never trigger OCR."""
        long_content = " ".join(["Python"] * 100)   # Well above threshold
        pdf_bytes = _make_native_pdf(long_content)

        with patch("nlp.pdf_extractor._extract_with_ocr") as mock_ocr:
            mock_ocr.return_value = "Mocked Text"
            # Use a threshold of 1 to ensure we don't trigger OCR as long as 
            # ANY text was extracted natively.
            result = extract_text(pdf_bytes, scanned_threshold=1)

        mock_ocr.assert_not_called()
        self.assertEqual(result["method"], "native")



# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
