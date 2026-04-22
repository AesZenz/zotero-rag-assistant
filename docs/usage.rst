Usage
=====

All commands are run via ``pixi run <task>``. Tasks in the ``docs`` environment
require ``pixi run -e docs <task>``.

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
   with RAGAS (if installed) or Claude-as-judge faithfulness scoring.

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

Runs the full test suite with pytest, verbose output, and coverage reporting.
An HTML coverage report is written to ``htmlcov/``.

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
