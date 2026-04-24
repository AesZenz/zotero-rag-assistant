"""
Centralised configuration for the Zotero RAG Assistant.

All environment variables are declared here with types and defaults that match
.env.example. Import the ``settings`` singleton from this module; do not call
``os.getenv`` directly in other modules.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Generation backend
    generation_backend: str = "claude"
    ollama_model: str = "phi4-mini"

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"
    max_tokens_per_response: int = 500
    max_cost_per_query_usd: float = 0.05

    # Paths
    pdf_library_path: str | None = None
    data_dir: str = "./data"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-mpnet-base-v2"
    use_local_embeddings: bool = True

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Retrieval
    top_k_chunks: int = 5
    use_reranking: bool = False

    # Query decomposition
    query_decomposition: bool = False
    query_decomposition_model: str = "claude-haiku-4-5-20251001"

    # Vector store
    vector_store_type: str = "faiss"

    # Logging
    log_level: str = "INFO"
    log_file: str | None = None

    # Evaluation
    num_generated_questions: int = 20
    test_gen_temperature: float = 0.7
    eval_questions_path: str | None = None

    # Test data
    test_pdf_path: str = "data/path/to/your/test.pdf"


settings = Settings()
