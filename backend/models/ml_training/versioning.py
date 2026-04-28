"""
models/ml_training/versioning.py
=================================
Shared utility for saving standardized model versioning artifacts.

After every training run, call ``save_version_artifacts()`` to:
  1. Create (or reuse) the versioned model directory.
  2. Write a ``metadata.json`` with all 6 required fields.

The version string is resolved from the ``ML_MODEL_VERSION`` env var,
falling back to ``MODEL_VERSION``, then to the supplied default.

Usage
-----
    from versioning import save_version_artifacts

    out_dir = save_version_artifacts(
        model_name="RF Role Predictor",
        accuracy=0.923,
        f1_score=0.918,
        training_samples=4000,
        test_samples=1000,
        extra_metadata={"auc_roc": 0.97},
    )
    # out_dir == Path(".../ml_models/v1.0")
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("versioning")

# Root of the model store (sibling of this file's parent):
#   <repo>/backend/models/ml_models/
_ML_MODELS_ROOT = Path(__file__).resolve().parent.parent / "ml_models"


# ── Public helpers ────────────────────────────────────────────────────────────

def get_version() -> str:
    """
    Return the active model version string.

    Resolution order:
    1. ``ML_MODEL_VERSION`` env var  (e.g. ``"v1.2"``)
    2. ``MODEL_VERSION``   env var  (legacy alias)
    3. Hard-coded default ``"v1.0"``
    """
    return (
        os.getenv("ML_MODEL_VERSION")
        or os.getenv("MODEL_VERSION")
        or "v1.0"
    )


def get_version_dir(version: str | None = None) -> Path:
    """
    Return (and create) the versioned model directory.

    Parameters
    ----------
    version : explicit version string; defaults to ``get_version()``.

    Returns
    -------
    Path
        ``<repo>/backend/models/ml_models/<version>/``
    """
    v    = version or get_version()
    path = _ML_MODELS_ROOT / v
    path.mkdir(parents=True, exist_ok=True)
    logger.info("[versioning] version directory: %s", path)
    return path


def _detect_git_commit() -> str:
    """
    Return the short HEAD commit hash, or ``"unknown"`` if not in a git repo
    or if git is not installed.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def save_version_artifacts(
    model_name:       str,
    accuracy:         float,
    f1_score:         float,
    training_samples: int,
    test_samples:     int,
    version:          str | None        = None,
    extra_metadata:   dict[str, Any] | None = None,
) -> Path:
    """
    Write a standardized ``metadata.json`` to the versioned model directory
    and return that directory path.

    Parameters
    ----------
    model_name        : Human-readable name (e.g. ``"RF Role Predictor"``).
    accuracy          : Test-set accuracy in [0, 1].
    f1_score          : Weighted / macro F1 (or the primary evaluation metric).
    training_samples  : Number of training samples.
    test_samples      : Number of test/validation samples.
    version           : Version string; defaults to ``get_version()``.
    extra_metadata    : Optional dict of model-specific metrics stored under
                        the ``"extra"`` key (e.g. AUC-ROC, silhouette score).

    Returns
    -------
    Path
        The versioned model directory where ``metadata.json`` was written.

    Written ``metadata.json`` schema
    ---------------------------------
    {
        "model_name":       str,
        "version":          str,
        "training_date":    ISO-8601 UTC string,   ← required
        "accuracy":         float,                  ← required
        "f1_score":         float,                  ← required
        "training_samples": int,                    ← required
        "test_samples":     int,                    ← required
        "git_commit":       str,                    ← required
        "extra":            dict  (optional)
    }
    """
    v    = version or get_version()
    path = get_version_dir(v)

    metadata: dict[str, Any] = {
        # ── 6 required fields ──────────────────────────────────────────
        "model_name":       model_name,
        "version":          v,
        "training_date":    datetime.now(timezone.utc).isoformat(),
        "accuracy":         round(float(accuracy), 6),
        "f1_score":         round(float(f1_score), 6),
        "training_samples": int(training_samples),
        "test_samples":     int(test_samples),
        "git_commit":       _detect_git_commit(),
    }

    if extra_metadata:
        metadata["extra"] = extra_metadata

    metadata_path = path / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as fh:
        json.dump(metadata, fh, indent=4)

    logger.info(
        "[versioning] metadata.json written → %s  (git=%s, acc=%.4f, f1=%.4f)",
        metadata_path,
        metadata["git_commit"],
        metadata["accuracy"],
        metadata["f1_score"],
    )
    return path
