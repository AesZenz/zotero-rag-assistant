import tiktoken
import pytest

from src.ingestion.chunker import chunk_text, chunk_document

_ENC = tiktoken.get_encoding("cl100k_base")

METADATA = {
    "pdf_title": "Test Paper",
    "author": "Test Author",
    "page_count": 3,
    "creation_date": None,
}


def test_chunk_count_increases_with_long_text():
    short_chunks = chunk_text("hello world", chunk_size=512, overlap=50)
    long_text = " ".join(["word"] * 600)
    long_chunks = chunk_text(long_text, chunk_size=100, overlap=10)
    assert len(long_chunks) > len(short_chunks)
    assert len(long_chunks) >= 5


def test_overlap_tokens_shared_between_adjacent_chunks():
    text = " ".join(["science"] * 300)
    overlap = 30
    chunks = chunk_text(text, chunk_size=100, overlap=overlap)
    assert len(chunks) >= 2

    tokens0 = _ENC.encode(chunks[0]["text"])
    tokens1 = _ENC.encode(chunks[1]["text"])
    assert tokens0[-overlap:] == tokens1[:overlap]


def test_chunk_document_metadata_fields_present():
    text = " ".join(["research"] * 200)
    chunks = chunk_document(text, METADATA, chunk_size=100, overlap=10)
    assert len(chunks) > 0
    for chunk in chunks:
        assert "pdf_title" in chunk
        assert "author" in chunk
        assert "page_count" in chunk
        assert "creation_date" in chunk
        assert "chunk_id" in chunk
        assert "text" in chunk
        assert chunk["pdf_title"] == METADATA["pdf_title"]
        assert chunk["author"] == METADATA["author"]


def test_empty_string_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_document_empty_string_returns_empty_list():
    assert chunk_document("", METADATA) == []


def test_chunk_ids_are_sequential():
    text = " ".join(["token"] * 300)
    chunks = chunk_text(text, chunk_size=50, overlap=5)
    ids = [c["chunk_id"] for c in chunks]
    assert ids == list(range(len(chunks)))


def test_invalid_chunk_size_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=0)


def test_overlap_ge_chunk_size_raises():
    with pytest.raises(ValueError):
        chunk_text("some text", chunk_size=50, overlap=50)
