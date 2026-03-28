"""
PDF parsing utilities for the Zotero RAG Assistant.

Provides two public functions:
- extract_text_from_pdf  – full text extraction with cleaning
- extract_metadata       – title, author, creation date from PDF metadata
"""

import re
from datetime import datetime
from pathlib import Path

import fitz  # pymupdf

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class PDFParseError(Exception):
    """Raised when a PDF cannot be parsed for any reason."""


class PDFNoTextError(PDFParseError):
    """Raised when a PDF contains no extractable text (e.g. scanned image)."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean_text(raw: str) -> str:
    """Normalise whitespace and line breaks in extracted PDF text.

    - Collapses runs of spaces / tabs to a single space.
    - Replaces three or more consecutive newlines with two (paragraph break).
    - Strips leading / trailing whitespace from the whole document.

    Args:
        raw: Raw text as returned by PyMuPDF.

    Returns:
        Cleaned text string.
    """
    # Collapse horizontal whitespace (spaces, tabs) within lines
    text = re.sub(r"[ \t]+", " ", raw)
    # Normalise line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove trailing spaces on each line
    text = re.sub(r" +\n", "\n", text)
    # Collapse more-than-two consecutive blank lines into two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _open_pdf(pdf_path: str) -> fitz.Document:
    """Open a PDF file, raising descriptive errors on failure.

    Args:
        pdf_path: Absolute or relative path to the PDF file.

    Returns:
        An open :class:`fitz.Document`.

    Raises:
        FileNotFoundError: If the path does not exist.
        PDFParseError: If PyMuPDF cannot open the file (corrupted / not a PDF).
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        doc = fitz.open(str(path))
    except Exception as exc:
        raise PDFParseError(f"Cannot open PDF '{pdf_path}': {exc}") from exc

    if doc.is_encrypted:
        raise PDFParseError(f"PDF is encrypted and cannot be read: {pdf_path}")

    return doc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract and clean all text from a PDF file.

    Iterates over every page using PyMuPDF, concatenates the page texts,
    then applies whitespace normalisation.

    Args:
        pdf_path: Path to the PDF file to parse.

    Returns:
        A single cleaned string containing the full document text.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        PDFParseError: If the file is corrupted, encrypted, or otherwise
            unreadable by PyMuPDF.
        PDFNoTextError: If the document yields no extractable text at all
            (e.g. a scanned-image PDF with no OCR layer).
    """
    logger.debug("Extracting text from '%s'", pdf_path)

    doc = _open_pdf(pdf_path)

    page_texts: list[str] = []
    try:
        for page_num, page in enumerate(doc, start=1):
            try:
                text = page.get_text("text")
                if text:
                    page_texts.append(text)
            except Exception as exc:
                logger.warning(
                    "Could not read page %d of '%s': %s", page_num, pdf_path, exc
                )
    finally:
        doc.close()

    if not page_texts:
        raise PDFNoTextError(
            f"No extractable text found in '{pdf_path}'. "
            "The file may be a scanned image without an OCR layer."
        )

    raw = "\n".join(page_texts)
    cleaned = _clean_text(raw)

    logger.debug(
        "Extracted %d characters from %d pages in '%s'",
        len(cleaned),
        len(page_texts),
        pdf_path,
    )
    return cleaned


def extract_metadata(pdf_path: str) -> dict:
    """Extract bibliographic metadata from a PDF file.

    Reads the PDF's internal metadata dictionary and returns a normalised
    subset: title, author, and creation date.  Missing fields are returned
    as ``None`` rather than raising an error, since metadata is often
    incomplete in practice.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        A dictionary with the following keys:

        - ``"pdf_title"`` (``str | None``) – document title
        - ``"author"`` (``str | None``) – author(s) as a single string
        - ``"creation_date"`` (``datetime | None``) – parsed creation date
        - ``"page_count"`` (``int``) – total number of pages

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        PDFParseError: If the file cannot be opened by PyMuPDF.
    """
    logger.debug("Extracting metadata from '%s'", pdf_path)

    doc = _open_pdf(pdf_path)

    try:
        raw_meta: dict = doc.metadata or {}
        page_count: int = doc.page_count
    finally:
        doc.close()

    title: str | None = raw_meta.get("title") or None
    author: str | None = raw_meta.get("author") or None
    creation_date: datetime | None = _parse_pdf_date(raw_meta.get("creationDate"))

    metadata = {
        "pdf_title": title,
        "author": author,
        "creation_date": creation_date,
        "page_count": page_count,
    }

    logger.debug("Metadata for '%s': %s", pdf_path, metadata)
    return metadata


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def _parse_pdf_date(date_str: str | None) -> datetime | None:
    """Parse a PDF date string into a :class:`datetime` object.

    PDF dates follow the format ``D:YYYYMMDDHHmmSSOHH'mm'``.
    Only the date/time portion is parsed; timezone offset is discarded.

    Args:
        date_str: Raw date string from PDF metadata, or ``None``.

    Returns:
        A :class:`datetime` instance, or ``None`` if parsing fails.
    """
    if not date_str:
        return None

    # Strip leading "D:" prefix if present
    date_str = date_str.lstrip("D:").strip()

    # Try progressively shorter formats (some PDFs omit time fields)
    for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d"):
        try:
            # Truncate to the length of the format before parsing
            return datetime.strptime(date_str[: len(fmt)], fmt)
        except ValueError:
            continue

    logger.warning("Could not parse PDF date string: '%s'", date_str)
    return None
