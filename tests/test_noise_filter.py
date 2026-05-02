from src.ingestion.noise_filter import is_noise_chunk, filter_chunks

# --- helpers ---

def _chunk(text: str, token_count: int = 200) -> dict:
    return {"chunk_id": 0, "text": text, "token_count": token_count}


# --- reference list detection ---

REFERENCE_TEXT = """
Smith J, Jones B. A study of things. Journal of Things. 2019;36(4):120-135.
doi:10.1234/things.2019.001
Brown K, Davis L. More things. Sci Rep. 2020;12(2):45-67.
doi:10.1234/scirep.2020.002
White M, Green P. Yet more things. Nature. 2021;540(3):88–99.
doi:10.1038/nature.2021.003
Taylor R. Final things. Cell. 2018;178(1):55–70. doi:10.1016/cell.2018.004
"""

BODY_TEXT = (
    "In this study we demonstrate that transformer architectures achieve "
    "state-of-the-art performance on natural language understanding benchmarks. "
    "Our proposed method relies on multi-head attention to capture long-range "
    "dependencies between tokens. We evaluated the model on GLUE and SuperGLUE "
    "and report improvements over baseline approaches across all tasks."
)

FUNDING_TEXT = (
    "Acknowledgments. This work was supported by a grant from the NSF (award 1234567) "
    "and funded by the NIH under grant number R01-AB123456. We also acknowledge "
    "support from the Wellcome Trust fellowship program and the National Science "
    "Foundation Graduate Research Fellowship."
)

AFFILIATION_TEXT = (
    "1 Department of Computer Science, University of Oxford, Oxford, UK. "
    "2 Institute of Neural Computation, University College London, London, UK. "
    "Correspondence: j.smith@cs.ox.ac.uk"
)


def test_reference_chunk_is_classified_as_noise():
    is_noise, reason = is_noise_chunk(_chunk(REFERENCE_TEXT))
    assert is_noise is True
    assert "reference" in reason.lower()


def test_body_text_is_not_noise():
    is_noise, reason = is_noise_chunk(_chunk(BODY_TEXT))
    assert is_noise is False
    assert reason == ""


def test_funding_acknowledgment_is_noise():
    is_noise, reason = is_noise_chunk(_chunk(FUNDING_TEXT, token_count=60))
    assert is_noise is True
    assert "funding" in reason.lower() or "acknowledg" in reason.lower()


def test_author_affiliation_is_noise():
    is_noise, reason = is_noise_chunk(_chunk(AFFILIATION_TEXT))
    assert is_noise is True
    assert "affiliation" in reason.lower()


def test_filter_chunks_removes_noise():
    chunks = [
        {"chunk_id": 0, "text": BODY_TEXT, "token_count": 80},
        {"chunk_id": 1, "text": REFERENCE_TEXT, "token_count": 200},
    ]
    kept = filter_chunks(chunks)
    assert len(kept) == 1
    assert kept[0]["chunk_id"] == 0


def test_filter_chunks_empty_list():
    assert filter_chunks([]) == []


def test_filter_chunks_does_not_mutate_input():
    chunks = [{"chunk_id": 0, "text": BODY_TEXT, "token_count": 80}]
    original_len = len(chunks)
    filter_chunks(chunks)
    assert len(chunks) == original_len
