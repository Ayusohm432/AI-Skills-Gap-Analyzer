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
# The RF model has 50+ role classes so per-class probability is diluted.
# With 98.4% test accuracy the model is reliable even at lower confidence
# because the probability is spread across many classes.
# We set 0.25 to allow the ML result to be used whenever it's the clear leader.
ROLE_CONFIDENCE_THRESHOLD: float = 0.25

# SLA targets (ms) — logged as WARNING when exceeded
_ROLE_SLA_MS: float = 50.0
_LSTM_SLA_MS: float = 100.0

# ── Module-level encoder cache ────────────────────────────────────────────────
# SentenceTransformer is a heavy object (~90 MB). Creating it inside
# predict_missing_skills() on every call costs 2-5 s per invocation and
# completely breaks the <100 ms latency target.
# We cache it here (lazy init, thread-safe for single-process uvicorn).
_lstm_encoder        = None   # SentenceTransformer instance once loaded
_lstm_encoder_tried  = False  # prevents repeated disk reads after a failure

# ── Role Readiness Constants ──────────────────────────────────────────────────

_DEFAULT_ROLES_DB = {
    "Data Scientist":            ["Python", "SQL", "Machine Learning", "Statistics", "Pandas", "TensorFlow"],
    "Machine Learning Engineer": ["Python", "Docker", "Machine Learning", "TensorFlow", "MLOps", "AWS"],
    "Backend Developer":         ["Node.js", "Python", "SQL", "Docker", "AWS", "API Design", "MongoDB", "FastAPI"],
    "Frontend Developer":        ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"],
    "Cyber Security Analyst":    ["Linux", "Networking", "Python", "SIEM", "Firewalls", "Cryptography"],
}

_ADVANCED_KEYWORDS = [
    "System Design", "Architecture", "Microservices", "Leadership",
    "Mentoring", "Distributed Systems", "Scalability", "Cloud Architecture",
    "Security Auditing", "Compliance", "Performance Optimization"
]

# ── Readiness level thresholds (configurable via env, read once at import) ─────
_BEGINNER_THRESHOLD:     int = int(os.getenv("BEGINNER_SKILLS_THRESHOLD", "5"))
_INTERMEDIATE_THRESHOLD: int = int(os.getenv("INTERMEDIATE_SKILLS_THRESHOLD", "10"))

# Normalised role-name lookup (lowercase → canonical key in _DEFAULT_ROLES_DB)
_ROLE_ALIAS_MAP: dict[str, str] = {
    k.lower(): k for k in _DEFAULT_ROLES_DB
}




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
    """
    Convert a list of skill strings to a binary feature vector.

    Uses multi-level matching to handle the vocabulary mismatch between NLP-extracted
    short skill names (e.g. "python") and roadmap node feature names
    (e.g. "Python", "Python Basics", "Basic Python", "Advanced Python"):

    Level 1 – Exact match (case-insensitive)
    Level 2 – Extracted skill is a substring of the feature name  ("python" in "Python Basics")
    Level 3 – Feature name is a substring of the extracted skill   ("AWS" in "AWS Lambda")
    """
    vec = np.zeros(len(feature_names), dtype=np.float32)
    skills_lower = [s.lower() for s in skills]
    feat_lower   = [f.lower() for f in feature_names]

    for i, feat in enumerate(feat_lower):
        for skill in skills_lower:
            # Level 1: exact
            if skill == feat:
                vec[i] = 1.0
                break
            # Level 2: extracted skill word appears in feature name
            # Guard: skill must be >=4 chars to avoid spurious hits like "go"
            if len(skill) >= 4 and skill in feat:
                vec[i] = 1.0
                break
            # Level 3: feature appears in extracted skill (e.g. feat="aws" skill="aws lambda")
            if len(feat) >= 4 and feat in skill:
                vec[i] = 1.0
                break
    return vec


def _get_lstm_encoder():
    """
    Return a cached SentenceTransformer("all-MiniLM-L6-v2") instance.

    The encoder is created once and reused for every ``predict_missing_skills``
    call.  If sentence-transformers is not installed (or the first load fails),
    returns None so callers can fall back gracefully.
    """
    global _lstm_encoder, _lstm_encoder_tried
    if _lstm_encoder is not None:
        return _lstm_encoder
    if _lstm_encoder_tried:
        return None   # already failed — don't retry
    _lstm_encoder_tried = True
    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        _lstm_encoder = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("[LSTM] SentenceTransformer loaded and cached")
    except Exception as exc:
        logger.warning("[LSTM] SentenceTransformer unavailable: %s", exc)
        _lstm_encoder = None
    return _lstm_encoder


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

    Skill sequences are zero-padded / truncated to ``MAX_SKILLS`` (20) frames,
    each embedded with the cached ``all-MiniLM-L6-v2`` SentenceTransformer so
    a module-level instance is reused across calls (< 5 ms warm encoding vs
    2-5 s cold creation).

    Returns
    -------
    {
        "missing_skills": [str, ...],      # top_n skill names
        "confidences":    {skill: float},  # raw sigmoid probabilities
        "inference_ms":   float,           # wall-clock inference time
        "source":         "ml" | "fallback"
    }
    """
    _FALLBACK = {
        "missing_skills": [],
        "confidences":    {},
        "inference_ms":   0.0,
        "source":         "fallback",
    }

    if bundle is None:
        return _FALLBACK

    lstm_model        = bundle.get("lstm_model")
    mlb               = bundle.get("lstm_mlb")
    role_encoder      = bundle.get("role_encoder")
    seniority_encoder = bundle.get("seniority_encoder")

    if any(x is None for x in [lstm_model, mlb, role_encoder, seniority_encoder]):
        logger.warning("LSTM artifacts missing – returning source=fallback")
        return _FALLBACK

    # ── Encoder guard (must be ready before we start the timer) ──────────
    encoder = _get_lstm_encoder()
    if encoder is None:
        logger.warning(
            "[LSTM] SentenceTransformer unavailable – returning source=fallback"
        )
        return _FALLBACK

    try:
        t0 = time.perf_counter()

        # ── Branch B: metadata vector ─────────────────────────────────
        X_role = role_encoder.transform([[target_role]])    # (1, n_roles)
        X_sen  = seniority_encoder.transform([[seniority]]) # (1, 4)
        X_meta = np.concatenate([X_role, X_sen], axis=1).astype(np.float32)

        # ── Branch A: skill-sequence tensor (padded to MAX_SKILLS=20) ──
        # Truncate to at most MAX_SKILLS entries, then embed each one.
        # Remaining rows stay as zeros (zero-padding).
        skills_truncated = current_skills[:MAX_SKILLS]
        X_skills = np.zeros((1, MAX_SKILLS, EMB_DIM), dtype=np.float32)
        if skills_truncated:
            embeddings = encoder.encode(
                skills_truncated,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )  # shape: (len(skills_truncated), EMB_DIM)
            X_skills[0, : len(skills_truncated), :] = embeddings

        # ── Inference ─────────────────────────────────────────────────
        predictions = lstm_model.predict([X_skills, X_meta], verbose=0)[0]

        inference_ms = round((time.perf_counter() - t0) * 1000, 2)
        if inference_ms > _LSTM_SLA_MS:
            logger.warning(
                "[LSTM] inference took %.2f ms (> %.0f ms SLA) for %d skills / role '%s'",
                inference_ms, _LSTM_SLA_MS, len(current_skills), target_role,
            )
        else:
            logger.debug("[LSTM] inference %.2f ms", inference_ms)

        # ── Rank and filter ───────────────────────────────────────────
        classes        = mlb.classes_
        sorted_indices = np.argsort(predictions)[::-1]
        current_lower  = {s.lower() for s in current_skills}

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
            "inference_ms":   inference_ms,
            "source":         "ml",
        }
    except Exception as exc:
        logger.error(
            "predict_missing_skills error (%s) for role '%s': %s",
            type(exc).__name__, target_role, exc,
            exc_info=True,
        )
        return {
            "missing_skills": [],
            "confidences":    {},
            "inference_ms":   0.0,
            "source":         "fallback",
        }


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


def compute_level_scores(
    role: str,
    identified_skills: list[str],
    missing_skills_ranked: list[dict],
    has_projects: bool = False,
    has_github: bool = False,
    required_skills: list[str] | None = None,
) -> dict:
    """
    Calculate readiness scores for Beginner, Intermediate, and Advanced levels.

    Scoring Heuristic:
    - Beginner:     Top ``_BEGINNER_THRESHOLD`` core skills. +10 bonus if has_projects.
    - Intermediate: Top ``_INTERMEDIATE_THRESHOLD`` core + secondary skills. +10 if has_github.
    - Advanced:     Full skill set incl. architecture & leadership keywords. No bonus.

    Parameters
    ----------
    role              : Target role name (normalized to canonical key)
    identified_skills : Skills found in the resume
    missing_skills_ranked : Ranked missing skills from LSTM/gap analysis
    has_projects      : Whether resume has a roadmap/projects (beginner bonus)
    has_github        : Whether user has a GitHub account (intermediate bonus)
    required_skills   : Pre-fetched required skill list for this role (e.g. from
                        Gemini/Adzuna for custom roles). When provided, overrides
                        the _DEFAULT_ROLES_DB lookup. Prevents custom roles from
                        scoring 100% due to an empty required-skill list.
    """
    # ── Normalise role name ──────────────────────────────────────────────────
    canonical_role = _ROLE_ALIAS_MAP.get(role.strip().lower(), role)

    # Build a lowercase lookup set of all skills the candidate has.
    # NLP extractor stores them lowercase; Gemini/Adzuna may return mixed-case.
    # We normalise both sides to ensure case-insensitive matching.
    identified_set = {s.strip().lower() for s in identified_skills if s.strip()}
    missing_ranked_skills = [s["skill"] for s in missing_skills_ranked]

    # ── Resolve the canonical required skill list ────────────────────────────
    # Priority: caller-supplied list → _DEFAULT_ROLES_DB → ranked missing skills
    # → identified skills themselves (last resort so we never show a flat 0%).
    db_skills: list[str] = (
        required_skills
        or _DEFAULT_ROLES_DB.get(canonical_role, [])
    )

    # ── 1. Beginner ───────────────────────────────────────────────────
    core_skills = db_skills[:_BEGINNER_THRESHOLD]
    if not core_skills:
        # Try ranked missing skills as a proxy
        core_skills = missing_ranked_skills[:_BEGINNER_THRESHOLD]
    if not core_skills:
        # Last resort: the candidate's own skills are the "required" set —
        # they score 100% at beginner level (fully covers their own skills).
        core_skills = list(identified_skills)[:_BEGINNER_THRESHOLD]

    matched_beg = [s for s in core_skills if s.strip().lower() in identified_set]
    score_beg = (len(matched_beg) / len(core_skills) * 100) if core_skills else 0.0
    score_beg = min(100.0, score_beg + (10.0 if has_projects else 0.0))

    # ── 2. Intermediate ────────────────────────────────────────────────
    known_role_skills = db_skills[:_INTERMEDIATE_THRESHOLD]
    seen: set[str] = {s.strip().lower() for s in known_role_skills}
    inter_skills = list(known_role_skills)
    for s in missing_ranked_skills:
        if len(inter_skills) >= _INTERMEDIATE_THRESHOLD:
            break
        if s.strip().lower() not in seen:
            inter_skills.append(s)
            seen.add(s.strip().lower())
    if not inter_skills:
        inter_skills = list(identified_skills)[:_INTERMEDIATE_THRESHOLD]

    matched_inter = [s for s in inter_skills if s.strip().lower() in identified_set]
    score_inter = (len(matched_inter) / len(inter_skills) * 100) if inter_skills else 0.0
    score_inter = min(100.0, score_inter + (10.0 if has_github else 0.0))

    # ── 3. Advanced ───────────────────────────────────────────────────
    adv_seen: set[str] = set()
    adv_skills: list[str] = []
    for s in (db_skills + missing_ranked_skills + _ADVANCED_KEYWORDS):
        key = s.strip().lower()
        if key not in adv_seen:
            adv_skills.append(s)
            adv_seen.add(key)
    if not adv_skills:
        adv_skills = list(identified_skills) + _ADVANCED_KEYWORDS

    matched_adv = [s for s in adv_skills if s.strip().lower() in identified_set]
    score_adv = round(
        (len(matched_adv) / len(adv_skills) * 100) if adv_skills else 0.0, 2
    )

    return {
        "beginner": {
            "score":           round(score_beg, 2),
            "matched_skills":  matched_beg,
            "missing_skills":  [s for s in core_skills if s.lower() not in identified_set],
            "required_skills": core_skills,
        },
        "intermediate": {
            "score":           round(score_inter, 2),
            "matched_skills":  matched_inter,
            "missing_skills":  [s for s in inter_skills if s.lower() not in identified_set],
            "required_skills": inter_skills,
        },
        "advanced": {
            "score":           score_adv,
            "matched_skills":  matched_adv,
            "missing_skills":  [s for s in adv_skills if s.lower() not in identified_set],
            "required_skills": adv_skills,
        },
    }


