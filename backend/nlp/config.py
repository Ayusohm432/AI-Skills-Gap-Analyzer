"""
Centralized NLP configuration for the AI Skills Gap Analyzer.

All settings are overridable via environment variables with the NLP_ prefix.
Example: NLP_SEMANTIC_THRESHOLD=0.8
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings


# Resolve project root relative to this file: backend/nlp/config.py -> project root
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _BACKEND_DIR.parent


class NLPConfig(BaseSettings):
    """Configuration for the NLP / semantic skill extraction pipeline."""

    # ── Semantic extraction ──────────────────────────────────────────
    SEMANTIC_MODEL_NAME: str = "all-MiniLM-L6-v2"
    SEMANTIC_THRESHOLD: float = 0.75
    SEMANTIC_MAX_SKILLS: int = 50           # Cap output to top-N results
    SEMANTIC_BATCH_SIZE: int = 64           # Batch size for encoding

    # ── Taxonomy path (resolved relative to project root) ────────────
    SKILL_TAXONOMY_PATH: str = str(
        _BACKEND_DIR / "models" / "data" / "skill_categories.json"
    )

    # ── Taxonomy filtering ───────────────────────────────────────────
    TAXONOMY_MIN_FREQUENCY: int = 5         # Exclude skills with freq < this
    TAXONOMY_MIN_NAME_LENGTH: int = 2       # Exclude single-char names
    TAXONOMY_EXCLUDE_GENERIC: bool = True   # Filter out noisy / non-technical entries

    # ── Feature flags ────────────────────────────────────────────────
    USE_SEMANTIC_EXTRACTION: bool = True     # Toggle semantic on/off
    MERGE_STRATEGY: str = "union"            # "union" | "semantic_only" | "keyword_only"

    class Config:
        env_prefix = "NLP_"
