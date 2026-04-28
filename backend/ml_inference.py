"""
ml_inference.py
===============
Thin inference wrappers around the models stored in app.state.ml_models.

All public functions accept the **bundle** dict returned by ml_loader.load_all_models()
and a few inputs, then return plain Python objects (no TF/sklearn types leak out).

Each function degrades gracefully when its model artifact is None (i.e. failed
to load at startup) so the rest of the pipeline keeps working.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger("ml_inference")

# ── Constants (must match training hyper-params) ──────────────────────────────
MAX_SKILLS = 20   # sequence length fed to LSTM branch A
EMB_DIM    = 384  # all-MiniLM-L6-v2 embedding dimension

# Minimum role-predictor confidence to trust the ML output.
# Below this threshold the worker falls back to NLP role matching and the
# predicted_role field is set to "Auto Detect" in the stored result.
ROLE_CONFIDENCE_THRESHOLD: float = 0.60


# ── Internal helpers ──────────────────────────────────────────────────────────

def _feature_names(bundle: dict) -> list[str]:
    """Return the ordered feature/skill vocabulary from config.json."""
    cfg = bundle.get("role_config") or {}
    return cfg.get("feature_names", [])


def _role_labels(bundle: dict) -> list[str]:
    """Return the ordered role label list from config.json."""
    cfg = bundle.get("role_config") or {}
    return cfg.get("role_labels", [])


def _skills_to_vector(skills: list[str], feature_names: list[str]) -> np.ndarray:
    """Convert a list of skill strings to a binary feature vector."""
    vec = np.zeros(len(feature_names), dtype=np.float32)
    skills_lower = {s.lower() for s in skills}
    for i, feat in enumerate(feature_names):
        if feat.lower() in skills_lower:
            vec[i] = 1.0
    return vec


# ── Public API ────────────────────────────────────────────────────────────────

# Number of top predictive skills to surface in the response.
_TOP_PREDICTIVE_SKILLS_N: int = 5


def _top_predictive_skills(
    vec: "np.ndarray",
    feat_names: list[str],
    model,
    top_n: int = _TOP_PREDICTIVE_SKILLS_N,
) -> list[str]:
    """
    Return the names of the user's skills that contributed most to the
    Random Forest prediction, ranked by ``feature_importances_``.

    Only features where the user has the skill (vec[i] == 1) are considered.
    Returns an empty list if the model has no ``feature_importances_`` attribute.
    """
    importances = getattr(model, "feature_importances_", None)
    if importances is None or len(importances) != len(feat_names):
        return []

    # Mask to only the skills the user actually has
    user_mask   = vec.astype(bool)
    scores      = importances * user_mask          # zero out skills not in resume
    top_indices = np.argsort(scores)[::-1][:top_n]

    return [
        feat_names[i]
        for i in top_indices
        if user_mask[i]  # double-check — guard against floating-point edge cases
    ]


def predict_role(
    skills: list[str],
    bundle: dict,
    top_n: int = 3,
) -> dict:
    """
    Use the Random Forest role predictor to identify the best-matching role.

    Returns
    -------
    {
        "predicted_role":        str,
        "confidence":            float  (0-1),
        "top_roles":             [{"role": str, "confidence": float}, ...],
        "role_probabilities":    {role: float, ...},          # full dict
        "top_predictive_skills": [str, ...],                  # from feature_importances_
        "inference_ms":          float,                       # wall-clock ms
        "source":                "ml" | "low_confidence" | "fallback"
    }
    """
    model       = bundle.get("role_predictor")
    feat_names  = _feature_names(bundle)
    role_labels = _role_labels(bundle)

    _EMPTY = {
        "predicted_role":        None,
        "confidence":            0.0,
        "top_roles":             [],
        "role_probabilities":    {},
        "top_predictive_skills": [],
        "inference_ms":          0.0,
        "source":                "fallback",
    }

    if model is None or not feat_names or not role_labels:
        logger.warning("role_predictor not available – returning source=fallback")
        return _EMPTY

    try:
        t0  = time.perf_counter()

        vec      = _skills_to_vector(skills, feat_names)
        pred_idx = int(model.predict([vec])[0])
        proba    = model.predict_proba([vec])[0]

        inference_ms = round((time.perf_counter() - t0) * 1000, 2)
        if inference_ms > 50:
            logger.warning(
                "predict_role: inference took %.2f ms (> 50 ms SLA) for %d skills",
                inference_ms, len(skills),
            )
        else:
            logger.debug("predict_role: inference %.2f ms", inference_ms)

        # ── Top-N role list (backward compat) ────────────────────────
        top_indices = np.argsort(proba)[::-1][:top_n]
        top_roles   = [
            {"role": role_labels[i], "confidence": round(float(proba[i]), 4)}
            for i in top_indices
        ]

        # ── Full probability map {role: prob} ─────────────────────────
        role_probabilities = {
            role_labels[i]: round(float(proba[i]), 4)
            for i in range(len(role_labels))
        }

        # ── Top skills that drove the prediction ──────────────────────
        top_pred_skills = _top_predictive_skills(vec, feat_names, model)

        confidence = round(float(proba[pred_idx]), 4)

        # ── Confidence threshold gate ─────────────────────────────────
        if confidence < ROLE_CONFIDENCE_THRESHOLD:
            logger.warning(
                "predict_role: confidence %.4f < threshold %.2f for role '%s' – "
                "returning source=low_confidence so worker falls back to NLP",
                confidence, ROLE_CONFIDENCE_THRESHOLD, role_labels[pred_idx],
            )
            return {
                "predicted_role":        role_labels[pred_idx],  # kept for logging
                "confidence":            confidence,
                "top_roles":             top_roles,
                "role_probabilities":    role_probabilities,
                "top_predictive_skills": top_pred_skills,
                "inference_ms":          inference_ms,
                "source":                "low_confidence",
            }

        return {
            "predicted_role":        role_labels[pred_idx],
            "confidence":            confidence,
            "top_roles":             top_roles,
            "role_probabilities":    role_probabilities,
            "top_predictive_skills": top_pred_skills,
            "inference_ms":          inference_ms,
            "source":                "ml",
        }

    except Exception as exc:
        logger.error(
            "predict_role error (%s): %s",
            type(exc).__name__, exc,
            exc_info=True,
        )
        return {
            "predicted_role":        None,
            "confidence":            0.0,
            "top_roles":             [],
            "role_probabilities":    {},
            "top_predictive_skills": [],
            "inference_ms":          0.0,
            "source":                "fallback",
        }


def predict_missing_skills(
    current_skills: list[str],
    target_role:    str,
    seniority:      str = "Mid-level",
    bundle:         dict | None = None,
    top_n:          int = 15,
) -> dict:
    """
    Use the multi-input LSTM to predict the most likely missing skills.

    Returns
    -------
    {
        "missing_skills": [str, ...],      # top_n skill names
        "confidences":    {skill: float},  # raw sigmoid probabilities
        "source":         "ml" | "fallback"
    }
    """
    if bundle is None:
        return {"missing_skills": [], "confidences": {}, "source": "fallback"}

    lstm_model        = bundle.get("lstm_model")
    mlb               = bundle.get("lstm_mlb")
    role_encoder      = bundle.get("role_encoder")
    seniority_encoder = bundle.get("seniority_encoder")

    if any(x is None for x in [lstm_model, mlb, role_encoder, seniority_encoder]):
        logger.warning("LSTM artifacts missing – returning source=fallback")
        return {"missing_skills": [], "confidences": {}, "source": "fallback"}

    try:
        # ── Branch B: metadata vector ────────────────────────────────
        X_role = role_encoder.transform([[target_role]])   # (1, n_roles)
        X_sen  = seniority_encoder.transform([[seniority]])  # (1, 4)
        X_meta = np.concatenate([X_role, X_sen], axis=1).astype(np.float32)

        # ── Branch A: skill-sequence tensor ──────────────────────────
        # Import sentence-transformers lazily so cold-start is faster
        # when LSTM is not used.
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        encoder  = SentenceTransformer("all-MiniLM-L6-v2")
        X_skills = np.zeros((1, MAX_SKILLS, EMB_DIM), dtype=np.float32)
        for idx, skill in enumerate(current_skills[:MAX_SKILLS]):
            emb = encoder.encode(skill, convert_to_numpy=True, normalize_embeddings=True)
            X_skills[0, idx, :] = emb

        # ── Inference ────────────────────────────────────────────────
        predictions = lstm_model.predict([X_skills, X_meta], verbose=0)[0]

        classes         = mlb.classes_
        sorted_indices  = np.argsort(predictions)[::-1]
        current_lower   = {s.lower() for s in current_skills}

        recommended: list[str] = []
        confidences:  dict     = {}
        for idx in sorted_indices:
            skill_name = classes[idx]
            # Skip skills the user already has
            if skill_name.lower() in current_lower:
                continue
            recommended.append(skill_name)
            confidences[skill_name] = round(float(predictions[idx]), 4)
            if len(recommended) >= top_n:
                break

        return {
            "missing_skills": recommended,
            "confidences":    confidences,
            "source":         "ml",
        }
    except Exception as exc:
        logger.error(
            "predict_missing_skills error (%s) for role '%s': %s",
            type(exc).__name__, target_role, exc,
            exc_info=True,
        )
        return {"missing_skills": [], "confidences": {}, "source": "fallback"}


def cluster_skills(
    skills: list[str],
    bundle: dict,
) -> dict:
    """
    Use the KMeans skill clusterer to group detected skills into clusters.

    Returns
    -------
    {
        "clusters": {int: [skill, ...]},
        "source": "ml" | "fallback"
    }
    """
    model      = bundle.get("skill_clusterer")
    feat_names = _feature_names(bundle)

    if model is None or not feat_names or not skills:
        return {"clusters": {}, "source": "fallback"}

    try:
        vec    = _skills_to_vector(skills, feat_names).reshape(1, -1)
        labels = model.predict(vec)          # cluster id per sample
        result: dict[int, list[str]] = {}
        for skill, label in zip(skills, labels if len(labels) > 1 else [labels[0]] * len(skills)):
            result.setdefault(int(label), []).append(skill)
        return {"clusters": result, "source": "ml"}
    except Exception as exc:
        logger.error("cluster_skills error: %s", exc)
        return {"clusters": {}, "source": "fallback"}


def compute_readiness_score(
    found_skills:   list[str],
    missing_skills: list[str],
) -> float:
    """
    Simple coverage-based readiness score (0-100).
    
    score = found / (found + missing) * 100
    """
    total = len(found_skills) + len(missing_skills)
    if total == 0:
        return 0.0
    return round(len(found_skills) / total * 100, 2)


# ── Skill categorization (rule-based taxonomy) ────────────────────────────────

# Lightweight keyword → category mapping.
# Extend this dict as the skill taxonomy grows.
_SKILL_CATEGORY_MAP: dict[str, str] = {
    # Languages
    "python": "languages", "javascript": "languages", "typescript": "languages",
    "java": "languages", "go": "languages", "rust": "languages", "c++": "languages",
    "c#": "languages", "kotlin": "languages", "swift": "languages", "r": "languages",
    "scala": "languages", "php": "languages", "ruby": "languages",
    # Frontend
    "react": "frontend", "vue": "frontend", "angular": "frontend", "next.js": "frontend",
    "html": "frontend", "css": "frontend", "tailwindcss": "frontend", "svelte": "frontend",
    # Backend / APIs
    "node.js": "backend", "fastapi": "backend", "django": "backend", "flask": "backend",
    "spring boot": "backend", "express": "backend", "api design": "backend",
    "rest": "backend", "graphql": "backend",
    # Databases
    "sql": "databases", "postgresql": "databases", "mysql": "databases",
    "mongodb": "databases", "redis": "databases", "elasticsearch": "databases",
    "cassandra": "databases", "dynamodb": "databases",
    # Cloud / DevOps
    "aws": "cloud_devops", "gcp": "cloud_devops", "azure": "cloud_devops",
    "docker": "cloud_devops", "kubernetes": "cloud_devops", "terraform": "cloud_devops",
    "ci/cd": "cloud_devops", "jenkins": "cloud_devops", "github actions": "cloud_devops",
    # ML / Data Science
    "machine learning": "ml_ai", "deep learning": "ml_ai", "tensorflow": "ml_ai",
    "pytorch": "ml_ai", "scikit-learn": "ml_ai", "nlp": "ml_ai",
    "pandas": "data", "numpy": "data", "statistics": "data",
    "data visualization": "data", "tableau": "data", "power bi": "data",
    # MLOps
    "mlops": "mlops", "mlflow": "mlops", "kubeflow": "mlops",
    "feature engineering": "mlops", "model deployment": "mlops",
    # Security
    "linux": "security", "networking": "security", "firewalls": "security",
    "siem": "security", "cryptography": "security", "penetration testing": "security",
}


def _skill_category(skill: str) -> str:
    """Return the category for a single skill name."""
    return _SKILL_CATEGORY_MAP.get(skill.lower(), "general")


def categorize_skills(skills: list[str]) -> dict[str, list[str]]:
    """
    Group a list of skill names into domain categories.

    Returns
    -------
    dict mapping category name → list of skills in that category.
    Only non-empty categories are included.
    """
    groups: dict[str, list[str]] = {}
    for skill in skills:
        cat = _skill_category(skill)
        groups.setdefault(cat, []).append(skill)
    return groups


def rank_missing_skills(
    missing_skills: list[str],
    confidences:    dict[str, float],
) -> list[dict]:
    """
    Attach ML metadata to each missing skill and assign a priority tier.

    Parameters
    ----------
    missing_skills : ordered list of missing skill names
    confidences    : {skill: float} sigmoid probabilities from LSTM
                     (may be empty when falling back to rule-based)

    Returns
    -------
    List of dicts matching the MissingSkillRanked schema:
        [{"skill": str, "likelihood": float, "category": str, "priority": str}]
    """
    ranked = []
    for skill in missing_skills:
        likelihood = round(float(confidences.get(skill, 0.5)), 4)
        category   = _skill_category(skill)
        # Priority tiers based on LSTM probability
        if likelihood >= 0.75:
            priority = "high"
        elif likelihood >= 0.45:
            priority = "medium"
        else:
            priority = "low"
        ranked.append({
            "skill":      skill,
            "likelihood": likelihood,
            "category":   category,
            "priority":   priority,
        })
    return ranked
