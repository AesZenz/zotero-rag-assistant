import fitz
import pytest

from src.ingestion.pdf_parser import (
    PDFParseError,
    extract_metadata,
    extract_text_from_pdf,
)

# Known text inserted into sample.pdf by conftest
PAGE1_SNIPPET = "page one"
PAGE2_SNIPPET = "page two"
KNOWN_PAGE_COUNT = 2


def test_extract_text_returns_nonempty_string(sample_pdf_path):
    text = extract_text_from_pdf(str(sample_pdf_path))
    assert isinstance(text, str)
    assert len(text) > 0


def test_extract_text_contains_known_content(sample_pdf_path):
    text = extract_text_from_pdf(str(sample_pdf_path))
    assert PAGE1_SNIPPET in text
    assert PAGE2_SNIPPET in text


def test_extract_metadata_returns_expected_keys(sample_pdf_path):
    meta = extract_metadata(str(sample_pdf_path))
    assert set(meta.keys()) == {"pdf_title", "author", "creation_date", "page_count"}


def test_extract_metadata_page_count(sample_pdf_path):
    meta = extract_metadata(str(sample_pdf_path))
    assert meta["page_count"] == KNOWN_PAGE_COUNT


def test_combined_result_has_all_required_keys(sample_pdf_path):
    text = extract_text_from_pdf(str(sample_pdf_path))
    meta = extract_metadata(str(sample_pdf_path))
    result = {"text": text, **meta}
    assert {"text", "pdf_title", "author", "page_count", "creation_date"}.issubset(result.keys())


def test_missing_file_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_text_from_pdf("/tmp/nonexistent_zotero_test_file.pdf")


def test_missing_file_metadata_raises_file_not_found():
    with pytest.raises(FileNotFoundError):
        extract_metadata("/tmp/nonexistent_zotero_test_file.pdf")


def test_encrypted_pdf_raises_pdf_parse_error(tmp_path):
    encrypted_path = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(
        str(encrypted_path),
        encryption=fitz.PDF_ENCRYPT_AES_256,
        user_pw="secret",
        owner_pw="owner",
    )
    doc.close()

    with pytest.raises(PDFParseError):
        extract_text_from_pdf(str(encrypted_path))
