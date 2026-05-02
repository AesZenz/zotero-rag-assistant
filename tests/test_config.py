import pytest
from pydantic import ValidationError


def test_settings_loads_with_env_vars(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "256")
    monkeypatch.setenv("CHUNK_OVERLAP", "25")
    from src.config import Settings

    s = Settings()
    assert s.chunk_size == 256
    assert s.chunk_overlap == 25


def test_chunk_size_is_int(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "512")
    from src.config import Settings

    s = Settings()
    assert isinstance(s.chunk_size, int)


def test_top_k_chunks_is_int(monkeypatch):
    from src.config import Settings

    s = Settings()
    assert isinstance(s.top_k_chunks, int)


def test_max_cost_per_query_is_float(monkeypatch):
    from src.config import Settings

    s = Settings()
    assert isinstance(s.max_cost_per_query_usd, float)


def test_invalid_int_field_raises_validation_error(monkeypatch):
    monkeypatch.setenv("CHUNK_SIZE", "not_a_number")
    from src.config import Settings

    with pytest.raises(ValidationError):
        Settings()


def test_default_generation_backend(monkeypatch):
    from src.config import Settings

    s = Settings()
    assert s.generation_backend == "claude"


def test_query_decomposition_is_bool(monkeypatch):
    from src.config import Settings

    s = Settings()
    assert isinstance(s.query_decomposition, bool)
