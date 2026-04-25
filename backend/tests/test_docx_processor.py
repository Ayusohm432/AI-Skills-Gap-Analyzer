"""
tests/test_docx_processor.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the DOCX text extraction pipeline.

All tests use ``unittest.mock`` to avoid requiring real .docx files or the
python-docx binary to be installed in CI.  The fake document objects mimic the
python-docx public API surface that ``docx_processor.py`` relies on.

Run with:
    pytest backend/tests/test_docx_processor.py -v
"""

from __future__ import annotations

import io
import sys
import time
import types
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest


# ── Fake python-docx object builders ─────────────────────────────────────────

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_PARA_TAG = f"{{{_W_NS}}}p"
_TABLE_TAG = f"{{{_W_NS}}}tbl"


def _make_para_element(text: str) -> MagicMock:
    """Create a fake lxml-like element representing <w:p>."""
    el = MagicMock()
    el.tag = _PARA_TAG
    el.text = text
    return el


def _make_table_element() -> MagicMock:
    """Create a fake lxml-like element representing <w:tbl>."""
    el = MagicMock()
    el.tag = _TABLE_TAG
    return el


def _make_paragraph(text: str) -> MagicMock:
    """Return a mock python-docx Paragraph whose .text == text."""
    para = MagicMock()
    para.text = text
    para._element = _make_para_element(text)
    return para


def _make_cell(paragraphs: list[str], nested_tables: list[MagicMock] | None = None) -> MagicMock:
    """Return a mock python-docx TableCell."""
    cell = MagicMock()
    cell.paragraphs = [_make_paragraph(t) for t in paragraphs]
    cell.tables = nested_tables or []
    return cell


def _make_row(cells_text: list[list[str]]) -> MagicMock:
    """Return a mock python-docx TableRow whose cells contain given texts."""
    row = MagicMock()
    row.cells = [_make_cell(cell_paras) for cell_paras in cells_text]
    return row


def _make_table(rows_data: list[list[list[str]]]) -> MagicMock:
    """Return a mock python-docx Table.

    ``rows_data`` is a list of rows; each row is a list of cells; each cell is
    a list of paragraph texts.

    Example::
        _make_table([
            [["Name"], ["Alice"]],   # row 0: 2 cells
            [["Role"], ["Engineer"]], # row 1
        ])
    """
    table = MagicMock()
    table.rows = [_make_row(cells) for cells in rows_data]
    table._element = _make_table_element()
    return table


def _make_document(
    paragraphs: list[str],
    tables: list[MagicMock] | None = None,
    body_order: list[str] | None = None,
) -> MagicMock:
    """Build a mock python-docx Document.

    Args:
        paragraphs: Texts for standalone paragraphs in the document.
        tables:     Pre-built table mocks.
        body_order: Ordered list of ``"para"`` and ``"table"`` strings
                    controlling how ``document.element.body`` is iterated.
                    Defaults to all paragraphs first, then all tables.
    """
    tables = tables or []
    para_mocks = [_make_paragraph(t) for t in paragraphs]
    para_elements = [p._element for p in para_mocks]
    table_elements = [t._element for t in tables]

    if body_order is None:
        body_order = ["para"] * len(paragraphs) + ["table"] * len(tables)

    # Build the iterable for document.element.body
    para_iter = iter(para_elements)
    table_iter = iter(table_elements)
    body_children: list[MagicMock] = []
    for token in body_order:
        if token == "para":
            body_children.append(next(para_iter))
        else:
            body_children.append(next(table_iter))

    # Map element id → wrapper object (mirrors _walk_document_body internals)
    para_map = {id(el): p for el, p in zip(para_elements, para_mocks)}
    table_map = {id(el): t for el, t in zip(table_elements, tables)}

    body_el = MagicMock()
    body_el.__iter__ = lambda self: iter(body_children)

    document = MagicMock()
    document.paragraphs = para_mocks
    document.tables = tables
    document.element.body = body_el

    # Patch the lookup so _walk_document_body can find wrappers by element id
    # We monkeypatch id() calls indirectly by making `.paragraphs` and
    # `.tables` yield objects whose ``._element`` has a consistent id().

    return document


def _make_docx_module(document: MagicMock) -> types.ModuleType:
    """Return a fake ``docx`` module whose ``Document()`` returns *document*."""
    docx_mod = types.ModuleType("docx")
    docx_mod.Document = MagicMock(return_value=document)
    return docx_mod


# ── Helper to reload and call the extractor ───────────────────────────────────


def _run_extractor(document: MagicMock) -> str:
    """Patch sys.modules, reload docx_processor, call extract_text_from_docx."""
    docx_mod = _make_docx_module(document)

    with patch.dict(sys.modules, {"docx": docx_mod}):
        from nlp import docx_processor
        import importlib
        importlib.reload(docx_processor)
        result = docx_processor.extract_text_from_docx(b"dummy-docx-bytes")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 1. Paragraph extraction tests
# ─────────────────────────────────────────────────────────────────────────────


class TestParagraphExtraction:
    """Paragraphs-only documents (no tables)."""

    def test_single_paragraph_returned(self):
        doc = _make_document(
            ["Python developer with 5 years of experience in machine learning."]
        )
        result = _run_extractor(doc)
        assert "Python" in result
        assert "machine learning" in result

    def test_multiple_paragraphs_concatenated(self):
        doc = _make_document([
            "Name: Alice Johnson",
            "Skills: Python, FastAPI, PostgreSQL, Docker, Kubernetes",
            "Experience: 4 years at TechCorp building distributed systems.",
        ])
        result = _run_extractor(doc)
        assert "Alice" in result
        assert "FastAPI" in result
        assert "TechCorp" in result

    def test_empty_paragraphs_skipped(self):
        """Blank paragraphs should not produce extra blank lines in output."""
        doc = _make_document(["Senior", "", "   ", "Engineer"])
        result = _run_extractor(doc)
        # Blank lines should be collapsed, not turn into \n\n\n
        assert "\n\n\n" not in result
        assert "Senior" in result
        assert "Engineer" in result

    def test_whitespace_within_paragraph_normalised(self):
        doc = _make_document(["Python    developer\t\twith  extra   spaces"])
        result = _run_extractor(doc)
        assert "  " not in result

    def test_leading_trailing_whitespace_stripped(self):
        doc = _make_document(["   Senior Backend Engineer   "])
        result = _run_extractor(doc)
        assert result == result.strip()

    def test_page_number_lines_removed(self):
        """Header/footer lines like 'Page 1 of 3' should be stripped."""
        doc = _make_document([
            "Page 1 of 3",
            "Java Spring developer with expertise in microservices and REST APIs.",
        ])
        result = _run_extractor(doc)
        assert "Page 1 of 3" not in result
        assert "Java" in result

    def test_repeated_header_lines_removed(self):
        """Lines repeated ≥3 times (e.g. a running header) are stripped."""
        repeated = "ALICE JOHNSON — RESUME"
        doc = _make_document([
            repeated,
            "Education: B.Sc. Computer Science",
            repeated,
            "Skills: Python, Go, Rust",
            repeated,
        ])
        result = _run_extractor(doc)
        assert result.count(repeated) == 0
        assert "Education" in result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Table extraction tests
# ─────────────────────────────────────────────────────────────────────────────


class TestTableExtraction:
    """Documents containing tables."""

    def test_simple_two_column_table(self):
        """A two-column table should be rendered as 'col1 | col2' rows."""
        table = _make_table([
            [["Skill"], ["Proficiency"]],
            [["Python"], ["Expert"]],
            [["Docker"], ["Intermediate"]],
        ])
        doc = _make_document([], tables=[table])
        result = _run_extractor(doc)
        assert "Python" in result
        assert "Docker" in result
        assert "Expert" in result

    def test_table_row_formatted_with_pipe(self):
        """Each row should have cells separated by ' | '."""
        table = _make_table([
            [["Company"], ["Role"], ["Duration"]],
            [["Acme Corp"], ["Backend Engineer"], ["2020-2023"]],
        ])
        doc = _make_document([], tables=[table])
        result = _run_extractor(doc)
        assert "Acme Corp" in result
        assert "Backend Engineer" in result

    def test_empty_table_cells_skipped(self):
        """Cells that contribute no text should not leave trailing pipes."""
        table = _make_table([
            [["Name"], [""]],
            [[""], ["Value"]],
        ])
        doc = _make_document([], tables=[table])
        result = _run_extractor(doc)
        # Should not start or end a row with ' | '
        for line in result.splitlines():
            assert not line.startswith(" | "), f"Leading pipe in: {line!r}"
            assert not line.endswith(" | "), f"Trailing pipe in: {line!r}"

    def test_table_without_rows_produces_no_output(self):
        table = _make_table([])
        doc = _make_document([], tables=[table])
        result = _run_extractor(doc)
        assert result.strip() == ""

    def test_nested_table_expanded(self):
        """Text inside a nested table should appear in the output."""
        inner_table = _make_table([
            [["Python 3.11"], ["NumPy"], ["Pandas"]],
        ])
        inner_table._element = _make_table_element()

        # Outer cell contains both the nested table and its own paragraph
        outer_cell = _make_cell(
            paragraphs=["Technologies:"],
            nested_tables=[inner_table],
        )
        outer_row = MagicMock()
        outer_row.cells = [outer_cell]
        outer_table = MagicMock()
        outer_table.rows = [outer_row]
        outer_table._element = _make_table_element()

        doc = _make_document([], tables=[outer_table])
        result = _run_extractor(doc)
        assert "Python 3.11" in result
        assert "Pandas" in result

    def test_multi_paragraph_cell(self):
        """Cells may contain multiple paragraphs; all should be included."""
        table = _make_table([
            [["Bachelor's Degree\nComputer Science\n2019-2023"]],
        ])
        # Override cell paragraphs to have multiple entries
        cell = _make_cell(
            paragraphs=["Bachelor's Degree", "Computer Science", "2019-2023"]
        )
        table.rows[0].cells = [cell]
        doc = _make_document([], tables=[table])
        result = _run_extractor(doc)
        assert "Bachelor" in result
        assert "Computer Science" in result


# ─────────────────────────────────────────────────────────────────────────────
# 3. Document body ordering (paragraphs and tables interleaved)
# ─────────────────────────────────────────────────────────────────────────────


class TestDocumentBodyOrder:
    """Verify content is emitted in XML document order."""

    def test_table_between_paragraphs(self):
        """Content from a table sandwiched between paragraphs must all appear."""
        table = _make_table([
            [["Python"], ["Expert"]],
        ])
        doc = _make_document(
            paragraphs=["Header Section", "Footer note"],
            tables=[table],
            body_order=["para", "table", "para"],
        )
        result = _run_extractor(doc)
        assert "Header Section" in result
        assert "Python" in result
        assert "Footer note" in result

    def test_paragraphs_after_table_included(self):
        table = _make_table([[["Skill"], ["Level"]]])
        doc = _make_document(
            paragraphs=["Introduction", "Conclusion paragraph here."],
            tables=[table],
            body_order=["para", "table", "para"],
        )
        result = _run_extractor(doc)
        assert "Introduction" in result
        assert "Conclusion" in result


# ─────────────────────────────────────────────────────────────────────────────
# 4. Edge case / error handling tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Graceful degradation for malformed or unusual inputs."""

    def test_empty_document_returns_empty_string(self):
        doc = _make_document([])
        result = _run_extractor(doc)
        assert result == ""

    def test_all_empty_paragraphs_returns_empty_string(self):
        doc = _make_document(["", "   ", "\t"])
        result = _run_extractor(doc)
        assert result.strip() == ""

    def test_missing_python_docx_returns_empty_string(self):
        """If python-docx is not installed, the function returns '' and logs."""
        # Remove docx from sys.modules to simulate ImportError
        with patch.dict(sys.modules, {"docx": None}):
            from nlp import docx_processor
            import importlib
            importlib.reload(docx_processor)
            result = docx_processor.extract_text_from_docx(b"dummy")
        assert result == ""

    def test_corrupt_bytes_returns_empty_string(self):
        """python-docx raises when given corrupt bytes; we return ''."""
        docx_mod = types.ModuleType("docx")
        docx_mod.Document = MagicMock(side_effect=Exception("bad zip"))

        with patch.dict(sys.modules, {"docx": docx_mod}):
            from nlp import docx_processor
            import importlib
            importlib.reload(docx_processor)
            result = docx_processor.extract_text_from_docx(b"\x00\x01\x02")
        assert result == ""

    def test_unicode_characters_preserved(self):
        """Non-ASCII resume content should pass through unchanged."""
        doc = _make_document([
            "Développeur Python — Île-de-France",
            "Compétences: programmation orientée objet, machine learning",
        ])
        result = _run_extractor(doc)
        assert "Développeur" in result
        assert "Compétences" in result

    def test_tabs_in_paragraph_normalised(self):
        doc = _make_document(["Skill\tLevel\tYears"])
        result = _run_extractor(doc)
        assert "\t" not in result


# ─────────────────────────────────────────────────────────────────────────────
# 5. Private helper unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHelpers:
    """Direct unit tests for internal helper functions."""

    def setup_method(self):
        from nlp import docx_processor
        import importlib
        importlib.reload(docx_processor)
        self.mod = docx_processor

    def test_paragraph_text_strips_whitespace(self):
        para = _make_paragraph("  hello world  ")
        result = self.mod._paragraph_text(para)
        assert result == "hello world"

    def test_paragraph_text_collapses_spaces(self):
        para = _make_paragraph("hello    world")
        result = self.mod._paragraph_text(para)
        assert "  " not in result

    def test_extract_table_text_single_row(self):
        table = _make_table([
            [["Alice"], ["Engineer"], ["5 years"]],
        ])
        result = self.mod._extract_table_text(table)
        assert "Alice" in result
        assert "Engineer" in result
        assert "5 years" in result

    def test_extract_table_text_multiple_rows(self):
        table = _make_table([
            [["Company"], ["Role"]],
            [["Google"], ["SWE"]],
            [["Meta"], ["Backend"]],
        ])
        result = self.mod._extract_table_text(table)
        lines = result.splitlines()
        assert len(lines) == 3
        assert "Google" in result
        assert "Meta" in result

    def test_extract_table_text_empty_cells_filtered(self):
        table = _make_table([
            [[""], [""], [""]],
        ])
        result = self.mod._extract_table_text(table)
        assert result.strip() == ""


# ─────────────────────────────────────────────────────────────────────────────
# 6. Performance test (< 5 s for a large document)
# ─────────────────────────────────────────────────────────────────────────────


class TestPerformance:
    """Extraction must complete within 5 seconds for a large resume."""

    def test_extraction_time_under_5_seconds(self):
        # Simulate a 3-page resume: 60 paragraphs and a 20-row table
        paragraphs = [
            f"Python backend developer with expertise in FastAPI and Docker. Line {i}"
            for i in range(60)
        ]
        table = _make_table([
            [["Company Corp"], ["Senior Engineer"], ["2018–2023"]]
            for _ in range(20)
        ])
        doc = _make_document(paragraphs, tables=[table])

        docx_mod = _make_docx_module(doc)
        with patch.dict(sys.modules, {"docx": docx_mod}):
            from nlp import docx_processor
            import importlib
            importlib.reload(docx_processor)

            start = time.perf_counter()
            docx_processor.extract_text_from_docx(b"dummy")
            elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"Extraction took {elapsed:.2f}s, expected < 5s"
