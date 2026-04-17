"""
pdf_extractor.py
================
Core document text-extraction pipeline.

Strategy
--------
1. Try PyMuPDF (fitz) to extract embedded text – fast and accurate for native PDFs.
2. If the extracted character count is too low (likely a scanned/image-based PDF),
   fall back to pytesseract OCR on each page rendered as an image.
3. Clean the resulting text (normalise whitespace, strip common header/footer noise).

Thresholds
----------
SCANNED_CHAR_THRESHOLD : int
    If total extracted characters < this value the PDF is treated as scanned
    and OCR is triggered.  Empirically ~100 chars covers blank / near-blank
    extractions from image-only PDFs.
"""

from __future__ import annotations

import io
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Threshold below which a PDF page is assumed to be image-only ──────────────
SCANNED_CHAR_THRESHOLD: int = 100


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean_text(raw: str) -> str:
    """
    Normalise whitespace and strip common resume header/footer artefacts.

    Steps
    -----
    * Collapse multiple blank lines → single blank line.
    * Collapse multiple spaces/tabs → single space.
    * Strip leading/trailing whitespace from every line.
    * Remove lines that look like page numbers (e.g. "Page 1 of 3", "1 | 2").
    * Remove lines that are pure punctuation / noise (e.g. "- - - - -").
    """
    if not raw:
        return ""

    # Normalise Windows line endings
    text = raw.replace("\r\n", "\n").replace("\r", "\n")

    # Strip per-line leading/trailing whitespace
    lines = [line.strip() for line in text.split("\n")]

    cleaned_lines: list[str] = []
    for line in lines:
        # Skip page-number-like lines:  "Page 1 of 3",  "1 / 3",  "- 1 -"
        if re.fullmatch(r"page\s+\d+\s+of\s+\d+", line, re.IGNORECASE):
            continue
        if re.fullmatch(r"\d+\s*/\s*\d+", line):
            continue
        if re.fullmatch(r"[-–—|]{1,3}\s*\d+\s*[-–—|]{1,3}", line):
            continue
        # Skip lines that are purely repeated punctuation / decorators
        if line and re.fullmatch(r"[^\w\s]{3,}", line):
            continue
        cleaned_lines.append(line)

    # Re-join; collapse 3+ consecutive blank lines → 1
    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Collapse multiple spaces / tabs to a single space
    text = re.sub(r"[ \t]{2,}", " ", text)

    return text.strip()


def _is_scanned(text: str) -> bool:
    """Return True when *text* is short enough to indicate a scanned PDF."""
    return len(text.strip()) < SCANNED_CHAR_THRESHOLD


# ─────────────────────────────────────────────────────────────────────────────
# Primary extractor – PyMuPDF
# ─────────────────────────────────────────────────────────────────────────────

def _extract_with_fitz(file_bytes: bytes) -> str:
    """
    Extract text from a PDF using PyMuPDF (fitz).

    Parameters
    ----------
    file_bytes : bytes
        Raw PDF file content.

    Returns
    -------
    str
        Concatenated text from all pages.

    Raises
    ------
    RuntimeError
        If PyMuPDF is not installed or the bytes cannot be parsed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF (fitz) is required: pip install PyMuPDF"
        ) from exc

    text_parts: list[str] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))

    return "\n".join(text_parts)


# ─────────────────────────────────────────────────────────────────────────────
# OCR fallback – pytesseract
# ─────────────────────────────────────────────────────────────────────────────

def _extract_with_ocr(file_bytes: bytes, dpi: int = 200) -> str:
    """
    Render each PDF page as a raster image and run Tesseract OCR on it.

    Parameters
    ----------
    file_bytes : bytes
        Raw PDF file content.
    dpi : int
        Rendering resolution.  200 DPI is a good balance between speed and OCR
        accuracy for standard A4/letter resume pages.

    Returns
    -------
    str
        OCR-extracted text from all pages.

    Raises
    ------
    RuntimeError
        If PyMuPDF or pytesseract is not available.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF (fitz) is required for OCR rendering: pip install PyMuPDF"
        ) from exc

    try:
        import pytesseract
        from PIL import Image  # Pillow ships with pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "pytesseract and Pillow are required for OCR: "
            "pip install pytesseract Pillow"
        ) from exc

    text_parts: list[str] = []
    zoom = dpi / 72  # fitz default is 72 DPI
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page_num, page in enumerate(doc):
            logger.debug("OCR: processing page %d", page_num + 1)
            pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            page_text = pytesseract.image_to_string(img, lang="eng")
            text_parts.append(page_text)

    return "\n".join(text_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def extract_text(
    file_bytes: bytes,
    *,
    ocr_dpi: int = 200,
    scanned_threshold: Optional[int] = None,
) -> dict:
    """
    Extract text from PDF bytes using the best available method.

    Algorithm
    ---------
    1. Run PyMuPDF to get embedded text (fast, accurate for digital PDFs).
    2. If the result is shorter than *scanned_threshold* characters, assume the
       PDF is scanned and re-extract using pytesseract OCR.
    3. Clean the final text.

    Parameters
    ----------
    file_bytes : bytes
        Raw PDF content read from the uploaded file.
    ocr_dpi : int
        DPI used when rendering pages for OCR (default 200).
    scanned_threshold : int, optional
        Override the default ``SCANNED_CHAR_THRESHOLD``.

    Returns
    -------
    dict with keys:
        ``text``        – cleaned extracted text (str)
        ``method``      – ``"native"`` or ``"ocr"``
        ``page_count``  – number of pages in the document
        ``char_count``  – character count of the cleaned text
        ``elapsed_s``   – wall-clock time in seconds

    Raises
    ------
    ValueError
        If *file_bytes* is empty.
    RuntimeError
        If neither PyMuPDF nor OCR path succeeds.
    """
    if not file_bytes:
        raise ValueError("file_bytes must not be empty")

    threshold = scanned_threshold if scanned_threshold is not None else SCANNED_CHAR_THRESHOLD

    # Count pages (needed for the return dict)
    try:
        import fitz
        with fitz.open(stream=file_bytes, filetype="pdf") as doc:
            page_count = doc.page_count
    except Exception:
        page_count = 0

    t0 = time.perf_counter()

    # ── Step 1: native extraction ─────────────────────────────────────────────
    try:
        raw_text = _extract_with_fitz(file_bytes)
        method = "native"
        logger.debug(
            "Native extraction yielded %d characters", len(raw_text.strip())
        )
    except RuntimeError as exc:
        logger.warning("PyMuPDF unavailable, falling straight to OCR: %s", exc)
        raw_text = ""
        method = "ocr"

    # ── Step 2: OCR fallback if the PDF appears to be scanned ─────────────────
    if len(raw_text.strip()) < threshold or method == "ocr":
        logger.info(
            "PDF appears scanned (chars=%d < threshold=%d). Running OCR …",
            len(raw_text.strip()),
            threshold,
        )
        raw_text = _extract_with_ocr(file_bytes, dpi=ocr_dpi)
        method = "ocr"

    # ── Step 3: clean ─────────────────────────────────────────────────────────
    cleaned = _clean_text(raw_text)

    elapsed = time.perf_counter() - t0
    logger.info(
        "Extraction complete | method=%s pages=%d chars=%d elapsed=%.2fs",
        method,
        page_count,
        len(cleaned),
        elapsed,
    )

    return {
        "text": cleaned,
        "method": method,
        "page_count": page_count,
        "char_count": len(cleaned),
        "elapsed_s": round(elapsed, 3),
    }
