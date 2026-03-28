"""
Noise-filtering utilities for the Zotero RAG Assistant.

Removes chunks that contain reference lists, author affiliations, funding
acknowledgments, and journal headers/footers before embedding.  Filtering is
done on the *chunk* level (post-chunking, pre-embedding) using signal-density
heuristics rather than section-name detection, so it generalises across paper
structures and publishers without requiring IMRaD formatting.

Figure captions and in-text plot references are intentionally kept — they
frequently contain key quantitative findings.
"""

from __future__ import annotations

import re

from src.utils.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# Year in parentheses, optionally followed by a letter — e.g. (2019) or (2020a)
_RE_YEAR_PAREN = re.compile(r"\(\d{4}[a-z]?\)")

# DOI patterns — also matches after normalising PDF-extracted spaces in URLs
_RE_DOI = re.compile(r"\b10\.\d{4,}/\S+|doi\.org/\S+", re.IGNORECASE)

# Volume(issue), pages — e.g. "36(6), 584" or "36(6):584"
_RE_VOL_ISSUE_PAGES = re.compile(r"\d+\s*\(\s*\d+\s*\)\s*[,:]?\s*\d+")

# Trailing page ranges — e.g. ", 584–596." or "pp. 584–596"
_RE_PAGE_RANGE = re.compile(r",\s*\d+[-\u2013]\d+\.?\s*$|\bpp?\.\s*\d+[-\u2013]\d+")

# Email addresses
_RE_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")

# Institution keywords used as affiliation signals
_RE_INSTITUTION = re.compile(
    r"\b(university|department|institute|laboratory|college|faculty|"
    r"school of|hospital|centre|center|research group|research institute)\b",
    re.IGNORECASE,
)

# Funding and acknowledgment keywords
_RE_FUNDING = re.compile(
    r"\b(acknowledg|funded by|supported by|grant|fellowship|foundation|"
    r"NSF|NIH|ESRC|ARC|ERC|DFG|NSERC|ANR|BBSRC|AHRC|SSHRC|"
    r"Wellcome Trust|European Research Council|"
    r"National Institutes of Health|National Science Foundation)\b",
    re.IGNORECASE,
)

# Publisher / journal header-footer keywords
_RE_PUBLISHER = re.compile(
    r"\b(elsevier|springer|wiley|taylor|francis|sage|oxford university press|"
    r"cambridge university press|ISSN|eISSN|©|copyright|all rights reserved|"
    r"published by|journal homepage|available online|Contents lists available|"
    r"received:|accepted:|article history|keywords:)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_doi_spaces(text: str) -> str:
    """Collapse spaces that PDF extraction inserts within DOI URLs.

    PyMuPDF occasionally extracts "http://dx. doi.org/" with a spurious space.
    Normalising before applying DOI regexes ensures those links are counted.
    """
    text = re.sub(r"(dx)\s*\.\s*(doi)", r"\1.\2", text, flags=re.IGNORECASE)
    text = re.sub(r"(doi)\s*\.\s*(org)", r"\1.\2", text, flags=re.IGNORECASE)
    return text


# ---------------------------------------------------------------------------
# Internal signal detectors
# ---------------------------------------------------------------------------

def _is_reference_chunk(text: str) -> tuple[bool, str]:
    """Return (True, reason) if the chunk looks like a bibliography / reference list.

    Uses chunk-level signal counts rather than per-line co-occurrence.
    Per-line logic fails because PDF text extraction frequently splits a single
    citation entry across two or three lines, so the year, DOI, and page-range
    signals for one reference never appear on the same line.

    Decision rules (any one is sufficient):
    - ≥ 3 DOIs  →  reference list (DOIs are essentially absent from body text)
    - ≥ 5 vol(issue)pages patterns  →  reference list
    - ≥ 8 year-in-parens AND (≥ 1 DOI OR ≥ 2 vol/pages)  →  reference list
      (many in-text citations alone don't produce DOIs or vol/pages patterns)
    """
    text = _normalize_doi_spaces(text)

    doi_count = len(_RE_DOI.findall(text))
    vol_issue_count = len(_RE_VOL_ISSUE_PAGES.findall(text))
    year_count = len(_RE_YEAR_PAREN.findall(text))

    if doi_count >= 3:
        return True, f"reference list ({doi_count} DOIs)"

    if vol_issue_count >= 5:
        return True, f"reference list ({vol_issue_count} vol/issue patterns)"

    if year_count >= 8 and (doi_count >= 1 or vol_issue_count >= 2):
        return (
            True,
            f"reference list ({year_count} years, {doi_count} DOIs, "
            f"{vol_issue_count} vol/pages)",
        )

    return False, ""


def _is_affiliation_chunk(text: str) -> bool:
    """Return True if the chunk looks like an author affiliation block.

    Requires an email address AND at least one institution keyword, or a high
    density of institution keywords in a short chunk.  Email alone is not
    sufficient because methods sections sometimes list a contact address.
    """
    has_email = bool(_RE_EMAIL.search(text))
    institution_count = len(_RE_INSTITUTION.findall(text))
    word_count = len(text.split())

    if has_email and institution_count >= 1:
        return True

    # Dense institution keywords in a short passage (standalone affiliation block)
    if institution_count >= 3 and word_count < 200:
        return True

    return False


def _is_funding_chunk(text: str) -> bool:
    """Return True if the chunk is primarily a funding / acknowledgment block.

    Uses keyword density (matches per 50 words) to avoid filtering body text
    that happens to mention a grant or agency name once.
    """
    matches = _RE_FUNDING.findall(text)
    word_count = len(text.split())
    density = len(matches) / max(word_count / 50, 1)
    return density >= 2.0


def _is_header_footer_chunk(text: str, token_count: int) -> bool:
    """Return True if the chunk looks like a journal header or footer.

    Two detection paths:
    - Short chunks (≤ 120 tokens) with any publisher keyword.
    - Any length chunk whose first 300 characters contain ≥ 2 publisher
      keyword matches — catches long first-page chunks that open with journal
      boilerplate (e.g. ScienceDirect landing-page text) before the abstract.
    """
    if token_count <= 120 and _RE_PUBLISHER.search(text):
        return True

    start_hits = len(_RE_PUBLISHER.findall(text[:300]))
    if start_hits >= 2:
        return True

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_noise_chunk(chunk: dict) -> tuple[bool, str]:
    """Classify a single chunk as noise or content.

    Args:
        chunk: A chunk dict as produced by :func:`src.ingestion.chunker.chunk_document`.
            Must contain ``"text"`` and optionally ``"token_count"``.

    Returns:
        A ``(is_noise, reason)`` tuple.  *reason* is an empty string when
        *is_noise* is ``False``.
    """
    text = chunk["text"]
    token_count = chunk.get("token_count", len(text.split()))

    is_ref, reason = _is_reference_chunk(text)
    if is_ref:
        return True, reason

    if _is_affiliation_chunk(text):
        return True, "author affiliations"

    if _is_funding_chunk(text):
        return True, "funding/acknowledgments"

    if _is_header_footer_chunk(text, token_count):
        return True, "journal header/footer"

    return False, ""


def filter_chunks(chunks: list[dict]) -> list[dict]:
    """Remove noise chunks from a list of document chunks.

    Filters reference lists, author affiliations, funding acknowledgments, and
    journal headers/footers.  Figure captions and in-text citations are
    intentionally kept.

    Args:
        chunks: Output of :func:`src.ingestion.chunker.chunk_document`.

    Returns:
        Filtered list with noise chunks removed.  The original list is not
        modified.
    """
    if not chunks:
        return chunks

    kept: list[dict] = []
    dropped: list[tuple[int, str]] = []

    for chunk in chunks:
        noise, reason = is_noise_chunk(chunk)
        if noise:
            dropped.append((chunk["chunk_id"], reason))
        else:
            kept.append(chunk)

    if dropped:
        preview = "; ".join(
            f"chunk {cid} ({r})" for cid, r in dropped[:5]
        ) + ("…" if len(dropped) > 5 else "")
        logger.info(
            "Noise filter: dropped %d/%d chunks — %s",
            len(dropped),
            len(chunks),
            preview,
        )
    else:
        logger.info("Noise filter: no noise detected in %d chunks", len(chunks))

    return kept
