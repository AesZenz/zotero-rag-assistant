import os

# Must be set before any torch/sentence-transformers import to avoid OpenMP bug on Intel Mac
os.environ.setdefault("OMP_NUM_THREADS", "1")

from pathlib import Path

import faiss
import fitz
import numpy as np
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PDF_PATH = FIXTURE_DIR / "sample.pdf"

PAGE1_TEXT = "This is page one of the test document. It contains sample scientific text about neural networks and deep learning."
PAGE2_TEXT = "This is page two of the test document. It discusses transformer architectures and attention mechanisms."


def _create_sample_pdf(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 100), PAGE1_TEXT)
    page2 = doc.new_page()
    page2.insert_text((72, 100), PAGE2_TEXT)
    doc.save(str(path))
    doc.close()


if not SAMPLE_PDF_PATH.exists():
    _create_sample_pdf(SAMPLE_PDF_PATH)


@pytest.fixture(scope="session")
def sample_pdf_path() -> Path:
    return SAMPLE_PDF_PATH


@pytest.fixture
def sample_chunks():
    return [
        {
            "chunk_id": 0,
            "text": "Neural networks learn representations from data through gradient descent optimization.",
            "start_char": 0,
            "end_char": 83,
            "token_count": 12,
            "source": "sample.pdf",
            "pdf_title": "Test Paper",
            "author": "Test Author",
            "page_count": 2,
            "creation_date": None,
        },
        {
            "chunk_id": 1,
            "text": "Transformer architectures use self-attention to model long-range dependencies.",
            "start_char": 84,
            "end_char": 160,
            "token_count": 11,
            "source": "sample.pdf",
            "pdf_title": "Test Paper",
            "author": "Test Author",
            "page_count": 2,
            "creation_date": None,
        },
        {
            "chunk_id": 2,
            "text": "Convolutional neural networks excel at image recognition tasks using local filters.",
            "start_char": 161,
            "end_char": 244,
            "token_count": 13,
            "source": "sample.pdf",
            "pdf_title": "Test Paper",
            "author": "Test Author",
            "page_count": 2,
            "creation_date": None,
        },
        {
            "chunk_id": 3,
            "text": "Recurrent networks process sequential data but suffer from vanishing gradients.",
            "start_char": 245,
            "end_char": 324,
            "token_count": 12,
            "source": "sample.pdf",
            "pdf_title": "Test Paper",
            "author": "Test Author",
            "page_count": 2,
            "creation_date": None,
        },
    ]


@pytest.fixture
def sample_vectors():
    rng = np.random.default_rng(seed=42)
    vecs = rng.random((4, 768)).astype(np.float32)
    faiss.normalize_L2(vecs)
    return vecs


@pytest.fixture
def tmp_index_dir(tmp_path):
    return tmp_path / "index"
