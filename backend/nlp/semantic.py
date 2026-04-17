"""
Semantic skill extraction using sentence-transformers.

Uses all-MiniLM-L6-v2 to encode resume text chunks and compare them
against a pre-embedded skill taxonomy via cosine similarity.

This module is designed for:
  - Lazy model loading (no import-time downloads)
  - One-time taxonomy embedding cache
  - <100ms inference per resume after warm-up
"""

import json
import re
import logging
from pathlib import Path
from typing import Any

import numpy as np

from nlp.config import NLPConfig

logger = logging.getLogger(__name__)

# ── Module-level singletons (lazy-loaded) ────────────────────────────
_model = None
_taxonomy_cache: dict[str, Any] | None = None


# ── Generic / noisy entries to exclude from the taxonomy ─────────────
_GENERIC_NAMES = {
    "introduction", "learn the basics", "pick a language",
    "basic syntax", "variables", "data types", "functions",
    "conditionals", "loops", "arrays", "sets", "lists",
    "type casting", "variables and data types", "installation and configuration",
    "what is hosting", "what is http", "what is domain name",
    "how does the internet work", "internet", "search engines",
    "configuration", "skills and responsibilities", "responsibilities",
    "developer journey", "learn a programming language",
    "programming fundamentals", "learn the basics of c#",
    "the fundamentals", "basic math skills", "introduction to language",
    "learn the fundamentals", "manage your testing",
    "understand the basics", "understand he basics",
    "what is", "why use", "how to", "guide to",
    "step by step", "become a", "for beginners", "for development",
    "key skills", "key concepts and terminologies",
    "usecases and benefits", "overview of kubernetes",
    "checkpoint - collaborative work",
}


def _get_model(config: NLPConfig | None = None):
    """Lazy-load the SentenceTransformer model (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        config = config or NLPConfig()
        logger.info("Loading semantic model: %s", config.SEMANTIC_MODEL_NAME)
        _model = SentenceTransformer(config.SEMANTIC_MODEL_NAME)
        logger.info("Semantic model loaded successfully")
    return _model


def _load_taxonomy(config: NLPConfig) -> list[dict]:
    """
    Load and filter the skill taxonomy from skill_categories.json.

    Filtering rules (when TAXONOMY_EXCLUDE_GENERIC is True):
      - Remove skills with frequency < TAXONOMY_MIN_FREQUENCY
      - Remove skills with name length < TAXONOMY_MIN_NAME_LENGTH
      - Remove generic / noisy names from the _GENERIC_NAMES set
      - Deduplicate case-insensitive (keep the first / highest-frequency entry)
    """
    taxonomy_path = Path(config.SKILL_TAXONOMY_PATH)
    if not taxonomy_path.exists():
        logger.warning("Taxonomy file not found at %s", taxonomy_path)
        return []

    with open(taxonomy_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    raw_skills = data.get("skills", [])
    logger.info("Raw taxonomy has %d skills", len(raw_skills))

    if not config.TAXONOMY_EXCLUDE_GENERIC:
        return raw_skills

    # Apply filters
    seen_lower: set[str] = set()
    filtered: list[dict] = []

    for skill in raw_skills:
        name = skill.get("name", "").strip()
        name_lower = name.lower()
        freq = skill.get("frequency", 0)

        # Skip too short
        if len(name) < config.TAXONOMY_MIN_NAME_LENGTH:
            continue

        # Skip low frequency
        if freq < config.TAXONOMY_MIN_FREQUENCY:
            continue

        # Skip generic names
        if name_lower in _GENERIC_NAMES:
            continue

        # Skip entries that look like questions / sentences
        if name_lower.startswith(("what is", "what are", "what does",
                                   "why use", "how does", "how to",
                                   "guide to", "when to")):
            continue

        # Deduplicate case-insensitive
        if name_lower in seen_lower:
            continue
        seen_lower.add(name_lower)

        filtered.append(skill)

    logger.info("Filtered taxonomy: %d skills (removed %d)",
                len(filtered), len(raw_skills) - len(filtered))
    return filtered


def _get_taxonomy_embeddings(config: NLPConfig | None = None):
    """
    Compute and cache skill name embeddings from the taxonomy.

    Returns:
        dict with keys:
          - "names": list[str]  — skill names in taxonomy order
          - "embeddings": np.ndarray of shape (N, dim)
          - "metadata": list[dict] — full skill entries for reference
    """
    global _taxonomy_cache
    if _taxonomy_cache is not None:
        return _taxonomy_cache

    config = config or NLPConfig()
    model = _get_model(config)
    skills = _load_taxonomy(config)

    if not skills:
        _taxonomy_cache = {
            "names": [],
            "embeddings": np.array([]),
            "metadata": [],
        }
        return _taxonomy_cache

    names = [s["name"] for s in skills]

    logger.info("Encoding %d taxonomy skill names...", len(names))
    embeddings = model.encode(
        names,
        batch_size=config.SEMANTIC_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,  # Pre-normalize for fast cosine sim
    )

    _taxonomy_cache = {
        "names": names,
        "embeddings": embeddings,
        "metadata": skills,
    }
    logger.info("Taxonomy embeddings cached: shape %s", embeddings.shape)
    return _taxonomy_cache


def _chunk_text(text: str, chunk_size: int = 3, overlap: int = 1) -> list[str]:
    """
    Split text into overlapping sentence-level chunks.

    Args:
        text: Full resume text
        chunk_size: Number of sentences per chunk
        overlap: Number of overlapping sentences between chunks

    Returns:
        List of text chunks
    """
    # Split on sentence boundaries
    sentences = re.split(r'(?<=[.!?;])\s+|\n+', text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

    if not sentences:
        return [text] if text.strip() else []

    chunks = []
    step = max(1, chunk_size - overlap)

    for i in range(0, len(sentences), step):
        chunk = " ".join(sentences[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)

    # If we have very few sentences, also include the full text as a chunk
    if len(sentences) <= chunk_size:
        chunks.append(text.strip())

    return chunks


def extract_skills_semantic(
    text: str,
    config: NLPConfig | None = None,
) -> list[dict[str, Any]]:
    """
    Extract skills from text using semantic similarity against the taxonomy.

    Args:
        text: Resume or document text to analyze
        config: NLP configuration (uses defaults if None)

    Returns:
        List of dicts with keys:
          - "skill": str  — skill name (proper casing from taxonomy)
          - "confidence": float — cosine similarity score [0, 1]
          - "category": str — skill category from taxonomy
    """
    config = config or NLPConfig()
    model = _get_model(config)
    taxonomy = _get_taxonomy_embeddings(config)

    if not taxonomy["names"]:
        logger.warning("Empty taxonomy — returning no skills")
        return []

    if not text or not text.strip():
        return []

    # 1. Chunk the input text
    chunks = _chunk_text(text)
    if not chunks:
        return []

    # 2. Encode all chunks at once
    chunk_embeddings = model.encode(
        chunks,
        batch_size=config.SEMANTIC_BATCH_SIZE,
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,
    )

    # 3. Compute cosine similarity: (num_chunks, dim) @ (dim, num_skills) -> (num_chunks, num_skills)
    #    Since both are L2-normalized, dot product == cosine similarity
    taxonomy_embeddings = taxonomy["embeddings"]
    similarity_matrix = chunk_embeddings @ taxonomy_embeddings.T  # shape: (C, S)

    # 4. For each skill, take the MAX similarity across all chunks
    max_similarities = similarity_matrix.max(axis=0)  # shape: (S,)

    # 5. Filter by threshold and collect results
    skill_results: dict[str, dict[str, Any]] = {}

    for idx in range(len(taxonomy["names"])):
        score = float(max_similarities[idx])
        if score >= config.SEMANTIC_THRESHOLD:
            skill_name = taxonomy["names"][idx]
            skill_meta = taxonomy["metadata"][idx]

            # Keep the highest score for each skill (already max across chunks)
            if skill_name not in skill_results or score > skill_results[skill_name]["confidence"]:
                skill_results[skill_name] = {
                    "skill": skill_name,
                    "confidence": round(score, 4),
                    "category": skill_meta.get("category", "Other"),
                }

    # 6. Sort by confidence descending and cap at max results
    results = sorted(skill_results.values(), key=lambda x: x["confidence"], reverse=True)
    results = results[:config.SEMANTIC_MAX_SKILLS]

    logger.info("Semantic extraction found %d skills (threshold=%.2f)",
                len(results), config.SEMANTIC_THRESHOLD)
    return results


def warm_up(config: NLPConfig | None = None) -> None:
    """
    Pre-load the model and taxonomy embeddings.
    Call this at server startup to avoid cold-start latency on the first request.
    """
    config = config or NLPConfig()
    _get_model(config)
    _get_taxonomy_embeddings(config)
    logger.info("Semantic extractor warm-up complete")


def reset_cache() -> None:
    """Reset the module-level caches. Useful for testing."""
    global _model, _taxonomy_cache
    _model = None
    _taxonomy_cache = None
