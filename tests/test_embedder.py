from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.ingestion.embedder import SentenceTransformerEmbedder, embed_chunks

DIM = 768


def _make_mock_model(n_texts=1):
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = DIM

    def mock_encode(texts, **kwargs):
        if isinstance(texts, str):
            return np.zeros(DIM, dtype=np.float32)
        return np.zeros((len(texts), DIM), dtype=np.float32)

    mock_model.encode.side_effect = mock_encode
    return mock_model


@pytest.fixture
def patched_embedder():
    with patch("sentence_transformers.SentenceTransformer") as mock_cls:
        mock_cls.return_value = _make_mock_model()
        embedder = SentenceTransformerEmbedder()
        embedder._load_model()  # trigger lazy load while patch is active
        yield embedder


def test_embed_text_output_shape(patched_embedder):
    result = patched_embedder.embed_text("hello world")
    assert isinstance(result, list)
    assert len(result) == DIM


def test_embed_text_output_dtype(patched_embedder):
    result = patched_embedder.embed_text("hello world")
    assert all(isinstance(v, float) for v in result)


def test_embed_batch_output_shape(patched_embedder):
    texts = ["first sentence", "second sentence", "third sentence"]
    result = patched_embedder.embed_batch(texts)
    assert len(result) == 3
    assert all(len(v) == DIM for v in result)


def test_embed_batch_output_dtype(patched_embedder):
    result = patched_embedder.embed_batch(["text one", "text two"])
    for vec in result:
        assert all(isinstance(v, float) for v in vec)


def test_embed_text_empty_raises():
    embedder = SentenceTransformerEmbedder()
    with pytest.raises(ValueError):
        embedder.embed_text("")


def test_embed_batch_empty_raises():
    embedder = SentenceTransformerEmbedder()
    with pytest.raises(ValueError):
        embedder.embed_batch([])


def test_embed_chunks_empty_returns_empty():
    result = embed_chunks([])
    assert result == []


def test_embed_chunks_adds_embedding_key():
    chunks = [
        {"chunk_id": 0, "text": "neural networks", "token_count": 2},
        {"chunk_id": 1, "text": "deep learning", "token_count": 2},
    ]
    with patch("sentence_transformers.SentenceTransformer") as mock_cls:
        mock_cls.return_value = _make_mock_model()
        embedder = SentenceTransformerEmbedder()
        result = embed_chunks(chunks, embedder)

    for chunk in result:
        assert "embedding" in chunk
        assert len(chunk["embedding"]) == DIM
