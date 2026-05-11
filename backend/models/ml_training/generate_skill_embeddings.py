"""
generate_skill_embeddings.py
============================
[Phase 2][ML] Issue #25 — Pre-compute BERT embeddings for the full skill vocabulary.

What it does
------------
1. Collects every unique skill that appears in ``models/data/skill_gap_pairs.json``
   (from both ``current_skills`` and ``missing_skills`` fields).
2. Sorts the vocabulary alphabetically for deterministic index assignment.
3. Encodes all skills with ``all-MiniLM-L6-v2`` in configurable batches.
4. Saves two artifacts to ``ml_training/data/``:
   - ``skills_embeddings.npy``   — float32 array of shape (N_skills, 384)
   - ``skill_vocabulary.json``   — {"skill_name": row_index, ...}
5. Validates shape and vocabulary size consistency.
6. Updates versioned ``metadata.json`` via the shared ``versioning`` helper.

The script is **idempotent**: if both output files already exist, it exits
immediately without doing any work. Use ``--force`` to regenerate.

Usage
-----
    # Normal first run
    python models/ml_training/generate_skill_embeddings.py

    # Re-run safely (no-op)
    python models/ml_training/generate_skill_embeddings.py

    # Force regeneration (e.g. after skill_gap_pairs.json is updated)
    python models/ml_training/generate_skill_embeddings.py --force

    # Custom batch size for low-memory machines
    python models/ml_training/generate_skill_embeddings.py --batch-size 64
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

# ── Path resolution ──────────────────────────────────────────────────────────
# This file lives at:  backend/models/ml_training/generate_skill_embeddings.py
# backend_dir  →       backend/
# data_dir     →       backend/models/data/          (raw training data)
# out_dir      →       backend/models/ml_training/data/  (generated artifacts)

_THIS_FILE  = Path(__file__).resolve()
backend_dir = _THIS_FILE.parent.parent.parent          # backend/
data_dir    = backend_dir / "models" / "data"
out_dir     = _THIS_FILE.parent / "data"               # ml_training/data/

SKILL_GAP_PAIRS_PATH = data_dir / "skill_gap_pairs.json"
EMB_PATH             = out_dir  / "skills_embeddings.npy"
VOCAB_PATH           = out_dir  / "skill_vocabulary.json"

MODEL_NAME  = "all-MiniLM-L6-v2"
EMB_DIM     = 384

# ── Versioning helper ────────────────────────────────────────────────────────
sys.path.insert(0, str(_THIS_FILE.parent))
from versioning import get_version_dir, save_version_artifacts  # noqa: E402

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Pre-compute BERT embeddings for the full skill vocabulary "
            "and save as NumPy arrays. (Issue #25)"
        )
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing embeddings even if the output files already exist.",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=256,
        metavar="N",
        help="Encoding batch size (default: 256). Lower this on memory-constrained machines.",
    )
    return p.parse_args()


# ── Core logic ────────────────────────────────────────────────────────────────

def load_skill_vocabulary() -> list[str]:
    """
    Extract every unique skill from ``skill_gap_pairs.json``.

    Both ``current_skills`` and ``missing_skills`` lists are collected so the
    vocabulary covers the entire corpus used by the LSTM and K-Means models.
    The result is sorted alphabetically to guarantee a deterministic
    skill ↔ row-index mapping across re-runs.

    Returns
    -------
    list[str]
        Sorted list of unique skill strings.
    """
    if not SKILL_GAP_PAIRS_PATH.exists():
        logger.error("Dataset not found: %s", SKILL_GAP_PAIRS_PATH)
        logger.error("Run process_industry_demand.py or check the data/ directory.")
        sys.exit(1)

    logger.info("Loading skill pairs from %s …", SKILL_GAP_PAIRS_PATH)
    with open(SKILL_GAP_PAIRS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)

    pairs = data.get("pairs", [])
    if not pairs:
        logger.error("No pairs found in %s. Cannot build vocabulary.", SKILL_GAP_PAIRS_PATH)
        sys.exit(1)

    logger.info("Loaded %d training pairs.", len(pairs))

    all_skills: set[str] = set()
    for pair in pairs:
        all_skills.update(pair.get("current_skills", []))
        all_skills.update(pair.get("missing_skills", []))

    if not all_skills:
        logger.error("No skills found in any pair. Cannot build vocabulary.")
        sys.exit(1)

    skills_sorted = sorted(all_skills)
    logger.info(
        "Vocabulary built: %d unique skills (from current + missing across all pairs).",
        len(skills_sorted),
    )
    return skills_sorted


def encode_skills(skills: list[str], batch_size: int) -> np.ndarray:
    """
    Encode ``skills`` with ``all-MiniLM-L6-v2`` in batches.

    Embeddings are L2-normalised (consistent with the LSTM branch) and
    returned as a float32 array of shape (len(skills), 384).

    Parameters
    ----------
    skills     : Ordered list of skill strings.
    batch_size : Number of skills per encoding batch.

    Returns
    -------
    np.ndarray
        Float32 array of shape (N_skills, 384).
    """
    logger.info("Initialising SentenceTransformer: %s …", MODEL_NAME)
    encoder = SentenceTransformer(MODEL_NAME)

    logger.info(
        "Encoding %d skills in batches of %d …",
        len(skills), batch_size,
    )
    embeddings = encoder.encode(
        skills,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,   # L2-normalise → unit-length vectors
    )

    # sentence-transformers may return float32 or float16 depending on device
    embeddings = embeddings.astype(np.float32)
    logger.info("Encoding complete. Embedding matrix shape: %s", embeddings.shape)
    return embeddings


def save_artifacts(skills: list[str], embeddings: np.ndarray) -> None:
    """
    Persist the two output artifacts to ``ml_training/data/``.

    Parameters
    ----------
    skills     : Ordered vocabulary list (alphabetically sorted).
    embeddings : Float32 array of shape (N_skills, 384).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. NumPy binary
    np.save(EMB_PATH, embeddings)
    logger.info("[1/2] Embeddings saved → %s  shape=%s", EMB_PATH, embeddings.shape)

    # 2. Vocabulary JSON  {skill_name: row_index}
    vocab = {skill: idx for idx, skill in enumerate(skills)}
    with open(VOCAB_PATH, "w", encoding="utf-8") as fh:
        json.dump(vocab, fh, indent=2, ensure_ascii=False)
    logger.info("[2/2] Vocabulary saved → %s  entries=%d", VOCAB_PATH, len(vocab))


def validate_artifacts(expected_n_skills: int) -> None:
    """
    Post-save sanity checks.

    Raises
    ------
    AssertionError
        If the saved array shape or vocabulary size is inconsistent.
    """
    logger.info("Validating saved artifacts …")

    loaded_emb  = np.load(EMB_PATH)
    loaded_vocab = json.loads(VOCAB_PATH.read_text(encoding="utf-8"))

    assert loaded_emb.shape == (expected_n_skills, EMB_DIM), (
        f"Embedding shape mismatch: expected ({expected_n_skills}, {EMB_DIM}), "
        f"got {loaded_emb.shape}"
    )
    assert len(loaded_vocab) == expected_n_skills, (
        f"Vocabulary size mismatch: expected {expected_n_skills}, "
        f"got {len(loaded_vocab)}"
    )

    # Spot-check: every vocab index is within range
    max_idx = max(loaded_vocab.values())
    assert max_idx == expected_n_skills - 1, (
        f"Max vocab index {max_idx} != expected {expected_n_skills - 1}"
    )

    logger.info(
        "Validation PASSED ✓  shape=(%d, %d)  vocab_size=%d",
        loaded_emb.shape[0], loaded_emb.shape[1], len(loaded_vocab),
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # ── Idempotency guard ────────────────────────────────────────────────────
    if EMB_PATH.exists() and VOCAB_PATH.exists() and not args.force:
        logger.info(
            "Output files already exist — nothing to do.\n"
            "  %s\n"
            "  %s\n"
            "Re-run with --force to regenerate.",
            EMB_PATH, VOCAB_PATH,
        )
        sys.exit(0)

    if args.force and (EMB_PATH.exists() or VOCAB_PATH.exists()):
        logger.info("--force flag set. Existing files will be overwritten.")

    # ── Step 1: Build vocabulary ─────────────────────────────────────────────
    skills = load_skill_vocabulary()

    # ── Step 2: Encode with BERT ─────────────────────────────────────────────
    embeddings = encode_skills(skills, batch_size=args.batch_size)

    # ── Step 3: Persist artifacts ────────────────────────────────────────────
    save_artifacts(skills, embeddings)

    # ── Step 4: Validate ─────────────────────────────────────────────────────
    validate_artifacts(expected_n_skills=len(skills))

    # ── Step 5: Update versioned metadata.json ───────────────────────────────
    MODELS_DIR = get_version_dir()
    logger.info("Updating metadata.json in %s …", MODELS_DIR)

    save_version_artifacts(
        model_name="Skill Vocabulary Embeddings",
        # Deterministic encoding — no train/test accuracy applies.
        # Use 1.0 as a sentinel so metadata.json fields remain valid.
        accuracy=1.0,
        f1_score=1.0,
        training_samples=len(skills),
        test_samples=0,
        extra_metadata={
            "embedding_model":  MODEL_NAME,
            "embedding_dim":    EMB_DIM,
            "vocab_size":       len(skills),
            "normalized":       True,
            "embeddings_file":  str(EMB_PATH),
            "vocabulary_file":  str(VOCAB_PATH),
        },
    )

    logger.info(
        "\n"
        "═══════════════════════════════════════════════\n"
        " Issue #25 — Skill Embeddings Generation DONE \n"
        "═══════════════════════════════════════════════\n"
        " Skills encoded : %d\n"
        " Embedding shape: (%d, %d)\n"
        " Embeddings file: %s\n"
        " Vocabulary file: %s\n"
        "═══════════════════════════════════════════════",
        len(skills),
        len(skills), EMB_DIM,
        EMB_PATH,
        VOCAB_PATH,
    )


if __name__ == "__main__":
    main()
