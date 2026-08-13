Usage
=====

All commands are run via ``pixi run <task>``. Tasks in the ``docs`` environment
require ``pixi run -e docs <task>``.

----

HTTP API Server
---------------

``api``
^^^^^^^

.. code-block:: bash

   pixi run api

Starts a FastAPI + Uvicorn server at ``http://localhost:8000``. All heavy
resources (vector store, embedder, generator) are loaded once at startup via
FastAPI's lifespan mechanism.

**Endpoints:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Endpoint
     - Description
   * - ``GET /health``
     - Liveness check; returns ``{"status": "ok"}``.
   * - ``POST /ingest``
     - Launches ``scripts/ingest_papers.py --resume`` as a background
       subprocess and returns immediately — the embedding run can take minutes
       on CPU and the caller does not need to wait. When the run finishes and
       new papers were added, the script POSTs to ``/reload`` itself so the
       fresh index becomes queryable without a restart.
   * - ``POST /reload``
     - Re-reads the FAISS index from disk into memory and returns
       ``{"status": "reloaded", "vectors": N}``. Called automatically at the end
       of an ingest; also safe to call by hand to pick up an index rebuilt out
       of band.
   * - ``POST /sync``
     - Runs ``scripts/sync_zotero.py`` as a background subprocess (copies new
       PDFs from Zotero, then triggers ``/ingest``). Used by the n8n automation
       workflow.
   * - ``POST /query``
     - Accepts JSON body ``{"query": "...", "top_k": 5}``. Embeds the query,
       searches the FAISS index, generates an answer via the configured
       backend, and returns ``{"answer": "...", "cost_usd": 0.0, "model": "..."}``.

**Prerequisites:** A populated FAISS index in ``DATA_DIR`` (run
``pixi run ingest`` first).

``sync-zotero``
^^^^^^^^^^^^^^^

.. code-block:: bash

   pixi run sync-zotero

Reads Zotero's local SQLite database at ``~/Zotero/zotero.sqlite`` (in
read-only mode), queries the ``Psy/Neuroscience/AI`` collection for PDF
attachments, copies any files not already present in ``PDF_LIBRARY_PATH``,
and then POSTs to ``http://localhost:8000/ingest`` if new PDFs were copied.

**Relevant environment variables:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``PDF_LIBRARY_PATH``
     - Destination directory where synced PDFs are written.

**Prerequisites:** ``PDF_LIBRARY_PATH`` set in ``.env``. For automatic
re-ingestion, the API server (``pixi run api``) must be running before this
task is invoked — if not reachable, the sync still copies files but prints a
warning instead of failing.

----

Ingestion
---------

``ingest`` / ``ingest-library``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pixi run ingest
   # or equivalently:
   pixi run ingest-library

Reads every PDF from the directory specified by ``PDF_LIBRARY_PATH``, extracts
text, chunks it into token-sized windows, filters noise (references,
affiliations, headers/footers), embeds the chunks with the local
sentence-transformers model, and writes the resulting FAISS index to
``DATA_DIR``.

**Relevant environment variables** (set in ``.env``):

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``PDF_LIBRARY_PATH``
     - Path to the folder containing your Zotero PDFs.
   * - ``DATA_DIR``
     - Output directory for the FAISS index and metadata (default: ``./data``).
   * - ``EMBEDDING_MODEL``
     - HuggingFace model used for embeddings (default: ``sentence-transformers/all-mpnet-base-v2``).
   * - ``CHUNK_SIZE``
     - Tokens per chunk (default: ``512``).
   * - ``CHUNK_OVERLAP``
     - Token overlap between consecutive chunks (default: ``50``).

----

Querying
--------

``query``
^^^^^^^^^

.. code-block:: bash

   pixi run query

Launches the interactive query assistant using the **Claude API** as the
generation backend. Embeds the query locally, retrieves the top-K most
relevant chunks from the FAISS index, and streams Claude's answer to the
terminal.

**Relevant environment variables:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``ANTHROPIC_API_KEY``
     - Required. Your Anthropic API key.
   * - ``CLAUDE_MODEL``
     - Claude model to use (default: ``claude-sonnet-4-6``).
   * - ``MAX_TOKENS_PER_RESPONSE``
     - Maximum tokens in Claude's response (default: ``500``).
   * - ``MAX_COST_PER_QUERY_USD``
     - Soft cost cap per query in USD (default: ``0.05``).
   * - ``TOP_K_CHUNKS``
     - Number of chunks to retrieve per query (default: ``5``).

**Prerequisites:** A populated FAISS index in ``DATA_DIR`` (run ``pixi run ingest`` first).

``query-ollama``
^^^^^^^^^^^^^^^^

.. code-block:: bash

   pixi run query-ollama

Identical to ``query`` but forces ``GENERATION_BACKEND=ollama``, routing
generation through a locally running Ollama server instead of the Claude API.
Useful for fully offline, cost-free querying.

.. important::

   Ollama must be running as a background process **before** invoking this
   task. Start it in a separate terminal and leave that terminal open for the
   duration of your session:

   .. code-block:: bash

      # In a separate terminal — keep it open
      ollama serve

   If Ollama is not reachable the task will fail immediately with a descriptive
   error message.

**Relevant environment variables:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``OLLAMA_MODEL``
     - Ollama model tag to use (default: ``phi4-mini``). The model must have
       been pulled first: ``ollama pull phi4-mini``.
   * - ``TOP_K_CHUNKS``
     - Number of chunks to retrieve per query (default: ``5``).

**Prerequisites:** Ollama installed, ``ollama serve`` running in a separate
terminal, and the target model pulled (``ollama pull <model>``).

----

Evaluation
----------

``generate-eval-questions``
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pixi run generate-eval-questions
   # with options:
   pixi run generate-eval-questions --n 50
   pixi run generate-eval-questions --n 50 --index-path data/paper_index.faiss

Samples ``n`` chunks from the FAISS index and uses Claude to generate one
self-contained research question per chunk. Results are written to
``data/eval/eval_questions.jsonl`` for use by the ``evaluate`` task.

**Options:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Flag
     - Description
   * - ``--n``
     - Number of questions to generate (default: ``20``).
   * - ``--index-path``
     - Path to the FAISS index file (default: ``data/paper_index.faiss``).
   * - ``--model``
     - Claude model to use for question generation (default: ``claude-haiku-4-5-20251001``).

**Prerequisites:** A populated FAISS index and ``ANTHROPIC_API_KEY`` set.

``evaluate``
^^^^^^^^^^^^

.. code-block:: bash

   pixi run evaluate

Runs the full RAG evaluation pipeline:

1. **Retrieval metrics** — for each eval question, embeds it, searches the
   index, and checks whether the source chunk appears in the top-K results.
   Computes Precision\@K, Recall\@K, and MRR.
2. **Answer quality** — generates an answer for each question and scores it
   with Claude-as-judge (faithfulness + answer relevancy).

Results are printed to the terminal and saved to ``data/eval/``.

**Relevant environment variables:**

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Variable
     - Description
   * - ``GENERATION_BACKEND``
     - Backend for answer generation during evaluation: ``claude`` (default)
       or ``ollama``.
   * - ``ANTHROPIC_API_KEY``
     - Required when using the Claude backend or Claude-as-judge scoring.
   * - ``TOP_K_CHUNKS``
     - Number of chunks to retrieve per question (default: ``5``).

**Prerequisites:** ``data/eval/eval_questions.jsonl`` produced by
``generate-eval-questions``, and a populated FAISS index.

----

Development
-----------

``test``
^^^^^^^^

.. code-block:: bash

   pixi run test

Runs the unit test suite (excludes the ``@pytest.mark.integration`` test) with
verbose pytest output. No model downloads or API calls — all external
dependencies are mocked.

``test-all``
^^^^^^^^^^^^

.. code-block:: bash

   pixi run test-all

Runs all tests including the full-pipeline integration test
(``tests/test_integration.py``). The integration test uses a deterministic mock
embedder so no real model is loaded, but it does require the ``tests/fixtures/``
sample PDF to be present.

``test-cov``
^^^^^^^^^^^^

.. code-block:: bash

   pixi run test-cov

Runs the unit tests (same scope as ``test``) with a coverage report printed to
the terminal (``--cov=src --cov-report=term-missing``).

``test-parser`` / ``test-chunker`` / ``test-embedder`` / ``test-vector-store``
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: bash

   pixi run test-parser
   pixi run test-chunker
   pixi run test-embedder
   pixi run test-vector-store

Standalone smoke-test scripts for individual pipeline components. Useful for
quickly verifying a single component after making changes.

``format``
^^^^^^^^^^

.. code-block:: bash

   pixi run format

Runs ``black`` over ``src/``, ``scripts/``, and ``tests/`` to auto-format code.

``lint``
^^^^^^^^

.. code-block:: bash

   pixi run lint

Runs ``ruff`` over ``src/``, ``scripts/``, and ``tests/`` to check for style
and correctness issues without modifying files.

``check``
^^^^^^^^^

.. code-block:: bash

   pixi run check

Convenience task that runs ``format``, ``lint``, and ``test`` in sequence.
Use this before committing to ensure the codebase is clean.

``notebook``
^^^^^^^^^^^^

.. code-block:: bash

   pixi run notebook

Opens JupyterLab in the ``notebooks/`` directory.

``docs``
^^^^^^^^

.. code-block:: bash

   pixi run -e docs docs

Builds this documentation with Sphinx and writes the HTML output to
``docs/_build/html/``. Open ``docs/_build/html/index.html`` in a browser to
view the result.

.. note::

   The ``docs`` task is only available in the ``docs`` environment and must be
   invoked with ``pixi run -e docs docs``.

Continuous integration
^^^^^^^^^^^^^^^^^^^^^^

``.github/workflows/tests.yml`` runs the same two pixi tasks on GitHub Actions:
``unit`` (``pixi run test``) and ``integration`` (``pixi run test-all``), as
parallel ``ubuntu-latest`` jobs that install the environment with
``prefix-dev/setup-pixi`` and its build cache. The workflow triggers on every
pull request and on pushes to ``main``, filtered to changes under ``src/`` or
``tests/`` and to the pixi manifests.

No repository secrets are configured. ``sentence_transformers`` and
``anthropic.Anthropic`` are patched in the tests, and every field on
``Settings`` has a default (including ``anthropic_api_key``), so the suite
imports and runs on a clean runner with no ``.env`` file and no API key. Adding
a test that performs real network or API calls would break this and require
``ANTHROPIC_API_KEY`` to be wired in as a secret.

.. note::

   ``linux-64`` is present in ``pixi.toml``'s ``platforms`` solely for these
   runners. Removing it — or leaving ``pixi.lock`` unresolved for it — breaks
   every CI run.
