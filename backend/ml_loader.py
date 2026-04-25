"""
ml_loader.py
============
Centralized loader for all trained ML model artifacts.

Loaded once at FastAPI startup (via lifespan) and stored in app.state.
Callers access models via:
    request.app.state.ml_models

Bundle keys
-----------
role_predictor      sklearn Pipeline (RandomForest + mlb)
role_config         dict  – feature_names & role_labels from config.json
skill_clusterer     sklearn KMeans / AgglomerativeClustering
lstm_model          tf.keras Model  (missing-skills LSTM)
lstm_mlb            MultiLabelBinarizer for LSTM output labels
role_encoder        OneHotEncoder for target role
seniority_encoder   OneHotEncoder for seniority
scaler              StandardScaler (used during LSTM training)

load_status         dict  – per-artifact load status ("ok" | "missing" | "error")
load_time_seconds   float – wall-clock time spent loading
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("ml_loader")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _models_dir() -> Path:
    """
    Resolve the versioned models directory.

    Priority:
    1. ML_MODEL_VERSION  env var  (e.g. "v1.2")
    2. MODEL_VERSION     env var  (legacy alias)
    3. Hard-coded default "v1.0"
    """
    version = (
        os.getenv("ML_MODEL_VERSION")
        or os.getenv("MODEL_VERSION")
        or "v1.0"
    )
    base = Path(__file__).resolve().parent / "models" / "ml_models" / version
    logger.info("ML model directory: %s", base)
    return base


def _try_load(name: str, loader_fn, status: dict) -> Any:
    """
    Call *loader_fn()* and record the result in *status*.
    Returns the loaded object, or None on failure.
    """
    try:
        obj = loader_fn()
        status[name] = "ok"
        logger.info("  [OK]  %-30s loaded", name)
        return obj
    except FileNotFoundError:
        status[name] = "missing"
        logger.warning("  [--]  %-30s NOT FOUND (graceful skip)", name)
        return None
    except Exception as exc:
        status[name] = f"error: {exc}"
        logger.error("  [ERR] %-30s %s", name, exc)
        return None


# ── Public API ────────────────────────────────────────────────────────────────

def load_all_models() -> dict:
    """
    Load all ML artifacts and return a bundle dict.

    Called once during FastAPI lifespan startup.  Should complete in < 10 s
    under normal conditions (TensorFlow cold-start is the slowest step).

    Returns
    -------
    dict with keys described in the module docstring plus:
        ``load_status``       – per-artifact status
        ``load_time_seconds`` – total wall-clock seconds spent loading
    """
    # Suppress verbose TF / TF-Lite logs at import time
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

    t0 = time.perf_counter()
    status: dict[str, str] = {}
    models_dir = _models_dir()

    logger.info("=" * 55)
    logger.info("Loading ML model artifacts …")
    logger.info("=" * 55)

    # ── 1. joblib (sklearn) ───────────────────────────────────────────
    import joblib  # lazy: only imported when this function runs

    role_predictor = _try_load(
        "role_predictor",
        lambda: joblib.load(models_dir / "role_predictor.pkl"),
        status,
    )

    skill_clusterer = _try_load(
        "skill_clusterer",
        lambda: joblib.load(models_dir / "skill_clusterer.pkl"),
        status,
    )

    lstm_mlb = _try_load(
        "missing_skills_mlb",
        lambda: joblib.load(models_dir / "missing_skills_mlb.pkl"),
        status,
    )

    role_encoder = _try_load(
        "role_encoder",
        lambda: joblib.load(models_dir / "role_encoder.pkl"),
        status,
    )

    seniority_encoder = _try_load(
        "seniority_encoder",
        lambda: joblib.load(models_dir / "seniority_encoder.pkl"),
        status,
    )

    scaler = _try_load(
        "scaler",
        lambda: joblib.load(models_dir / "scaler.pkl"),
        status,
    )

    # ── 2. config.json (vocabulary / label map) ───────────────────────
    config_path = models_dir / "config.json"

    def _load_config():
        if not config_path.exists():
            raise FileNotFoundError(config_path)
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    role_config = _try_load("role_config (config.json)", _load_config, status)

    # ── 3. TensorFlow / Keras LSTM ────────────────────────────────────
    # We prefer the .keras SavedModel format; fall back to .h5 if missing.
    keras_path = models_dir / "missing_skills_lstm.keras"
    h5_path    = models_dir / "missing_skills_lstm.h5"

    def _load_lstm():
        try:
            import tensorflow as tf  # noqa: PLC0415
            if keras_path.exists():
                logger.info("  [..] Loading LSTM from .keras format …")
                return tf.keras.models.load_model(keras_path)
            elif h5_path.exists():
                logger.info("  [..] .keras not found – falling back to .h5 …")
                return tf.keras.models.load_model(h5_path)
            else:
                raise FileNotFoundError(
                    f"Neither {keras_path} nor {h5_path} found"
                )
        except ImportError as exc:
            raise ImportError("TensorFlow is not installed") from exc

    lstm_model = _try_load("missing_skills_lstm", _load_lstm, status)

    # ── Summary ───────────────────────────────────────────────────────
    elapsed = round(time.perf_counter() - t0, 2)
    ok_count = sum(1 for v in status.values() if v == "ok")
    logger.info("=" * 55)
    logger.info(
        "Loaded %d/%d artifacts in %.2f s", ok_count, len(status), elapsed
    )
    if elapsed > 10:
        logger.warning(
            "Startup exceeded 10 s target (%.2f s). "
            "Consider pre-warming or reducing model size.",
            elapsed,
        )
    logger.info("=" * 55)

    return {
        # ── sklearn models
        "role_predictor":    role_predictor,
        "role_config":       role_config,
        "skill_clusterer":   skill_clusterer,
        # ── LSTM artifacts
        "lstm_model":        lstm_model,
        "lstm_mlb":          lstm_mlb,
        "role_encoder":      role_encoder,
        "seniority_encoder": seniority_encoder,
        "scaler":            scaler,
        # ── metadata
        "load_status":       status,
        "load_time_seconds": elapsed,
    }


def health_summary(bundle: dict | None) -> dict:
    """
    Return a JSON-serialisable health payload for the /health endpoint.

    Parameters
    ----------
    bundle : the dict returned by load_all_models(), or None if loading failed.
    """
    if bundle is None:
        return {
            "ml_models": "not_loaded",
            "artifacts": {},
            "load_time_seconds": None,
        }

    status = bundle.get("load_status", {})
    overall = (
        "all_ok"
        if all(v == "ok" for v in status.values())
        else "partial" if any(v == "ok" for v in status.values())
        else "failed"
    )

    return {
        "ml_models": overall,
        "artifacts": status,
        "load_time_seconds": bundle.get("load_time_seconds"),
    }
