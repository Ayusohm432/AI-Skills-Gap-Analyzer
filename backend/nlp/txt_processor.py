"""
txt_processor.py
~~~~~~~~~~~~~~~~
Plain-text (.txt) resume extraction.

Strategy
--------
1. Decode raw bytes as UTF-8.  If that fails, fall back to latin-1 which can
   represent any single byte without raising, so this path never throws.
2. Pass the result through the shared ``_clean_text`` function (imported from
   nlp.pdf_processor) to normalise whitespace and strip headers/footers
   consistently with the PDF and DOCX pipelines.

No third-party dependencies beyond the stdlib are required.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def extract_text_from_txt(file_bytes: bytes) -> str:
    """Extract and clean text from a plain-text file.

    Args:
        file_bytes: Raw bytes of the .txt file.

    Returns:
        Cleaned plain-text string, or an empty string if decoding fails
        unexpectedly. Errors are logged; no exception is raised.
    """
    # ── 1. Decode ─────────────────────────────────────────────────────────
    text = _decode(file_bytes)
    if text is None:
        return ""

    logger.info("TXT: decoded %d characters", len(text))

    # ── 2. Clean (reuse shared pipeline) ──────────────────────────────────
    from nlp.pdf_processor import _clean_text  # noqa: PLC0415

    return _clean_text(text)


def _decode(file_bytes: bytes) -> str | None:
    """Try UTF-8 then latin-1 decoding.

    Returns the decoded string, or None if both attempts somehow fail
    (practically impossible with latin-1, but we guard defensively).
    """
    for encoding in ("utf-8", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except (UnicodeDecodeError, AttributeError):
            logger.debug("TXT: %s decoding failed, trying next encoding", encoding)

    logger.error("TXT: all decoding strategies exhausted – returning empty string")
    return None
