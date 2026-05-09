"""
pdf_processor.py
~~~~~~~~~~~~~~~~
Core document text extraction pipeline.

Primary extractor : PyMuPDF (fitz)
OCR fallback      : pytesseract (for scanned / image-based PDFs)

Detection heuristic:
  If the total number of characters across all pages is below
  OCR_CHAR_THRESHOLD, the PDF is considered scanned and OCR is triggered.
"""

from __future__ import annotations

import io
import logging
import re

logger = logging.getLogger(__name__)

# ── Configurable thresholds ──────────────────────────────────────────────────
# Characters per page below which we consider the page "image-only"
OCR_CHAR_THRESHOLD: int = 100
# DPI used when rasterising pages for OCR (higher → better quality, slower)
OCR_DPI: int = 200
# ─────────────────────────────────────────────────────────────────────────────


def _is_scanned(doc: "fitz.Document") -> bool:
    """Return True if the document appears to be a scanned (image-only) PDF.

    Heuristic: sum all characters extracted from every page; if the total is
    below OCR_CHAR_THRESHOLD we assume the document carries no searchable text.
    """
    total_chars = sum(len(page.get_text("text")) for page in doc)
    logger.debug("Total native characters detected: %d", total_chars)
    return total_chars < OCR_CHAR_THRESHOLD


def _ocr_extract(doc: "fitz.Document") -> str:
    """Rasterise each PDF page and run Tesseract OCR on it.

    Returns the concatenated OCR text for the whole document.
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
    except ImportError as exc:
        logger.error(
            "OCR dependencies missing (%s). "
            "Install pytesseract and Pillow, and ensure Tesseract is in PATH.",
            exc,
        )
        return ""

    ocr_text_parts: list[str] = []
    matrix = __import__("fitz").Matrix(OCR_DPI / 72, OCR_DPI / 72)  # scale to target DPI

    for page_num, page in enumerate(doc):
        try:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text: str = pytesseract.image_to_string(img, lang="eng")
            ocr_text_parts.append(page_text)
            logger.debug("OCR page %d: %d chars", page_num, len(page_text))
        except Exception as e:
            logger.warning("OCR failed on page %d: %s", page_num, e)

    return "\n".join(ocr_text_parts)


def _clean_text(text: str) -> str:
    """Clean and normalise extracted text.

    Steps:
    1. Collapse all whitespace sequences (\\t, multiple spaces) to a single space.
    2. Strip leading/trailing whitespace from each line.
    3. Remove blank lines that are purely repeated header/footer artefacts
       (e.g. "Page 1 of 5", "John Doe – Curriculum Vitæ").
    4. Collapse more than two consecutive newlines to two.
    5. Strip leading/trailing whitespace from the whole document.
    """
    # 1. Normalise horizontal whitespace inside each line
    text = re.sub(r"[ \t]+", " ", text)

    # 2. Strip each line
    lines = [line.strip() for line in text.splitlines()]

    # 3. Remove common header/footer patterns
    _HEADER_FOOTER_RE = re.compile(
        r"^("
        r"page\s+\d+\s*(of\s*\d+)?|"  # Page N / Page N of M
        r"\d+\s*/\s*\d+|"              # N/M
        r"confidential|"
        r"curriculum vitae|"
        r"resume"
        r")$",
        re.IGNORECASE,
    )

    # Track repetitive lines (seen in >1 page position) – typical of headers/footers
    from collections import Counter
    line_counts: Counter[str] = Counter(l for l in lines if l)
    # A line repeated ≥3 times across the whole doc likely is a header or footer
    repeated = {line for line, count in line_counts.items() if count >= 3}

    cleaned_lines: list[str] = []
    for line in lines:
        if _HEADER_FOOTER_RE.match(line):
            continue
        if line in repeated:
            continue
        cleaned_lines.append(line)

    # 4. Collapse multiple blank lines
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 5. Final strip
    return text.strip()


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF given its raw bytes.

    Algorithm:
    1. Open via PyMuPDF (fitz).
    2. Detect if the document is scanned (low raw character count).
    3. If native → concatenate page text directly.
       If scanned → rasterise pages and run pytesseract OCR.
    4. Clean and return the extracted text.

    Args:
        file_bytes: Raw bytes of the PDF file.

    Returns:
        Cleaned plain-text string extracted from the document.
    """
    try:
        import fitz  # type: ignore  # PyMuPDF
    except ImportError:
        logger.error(
            "PyMuPDF (fitz) is not installed. "
            "Add 'pymupdf' to requirements.txt and reinstall."
        )
        return _fallback_pdfplumber(file_bytes)

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.error("Failed to open PDF with PyMuPDF: %s", exc)
        return _fallback_pdfplumber(file_bytes)

    if _is_scanned(doc):
        logger.info("Scanned PDF detected – activating OCR fallback.")
        raw_text = _ocr_extract(doc)
    else:
        logger.info("Native PDF detected – extracting text directly.")
        raw_text = "\n".join(page.get_text("text") for page in doc)

    doc.close()
    return _clean_text(raw_text)


# ── Fallback: pdfplumber (legacy) ────────────────────────────────────────────

def _fallback_pdfplumber(file_bytes: bytes) -> str:
    """Attempt extraction with pdfplumber when PyMuPDF is unavailable."""
    try:
        import pdfplumber  # type: ignore

        text_parts: list[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text_parts.append(extracted)
        raw = "\n".join(text_parts)
        return _clean_text(raw)
    except Exception as exc:
        logger.error("pdfplumber fallback also failed: %s", exc)
        return ""
