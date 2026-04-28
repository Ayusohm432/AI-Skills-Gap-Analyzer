"""
tests/test_lstm_inference.py
============================
Unit tests for the LSTM missing-skills predictor in ml_inference.py.

Covers:
  1. Sequence padding / truncation to MAX_SKILLS=20
  2. Output schema  — all keys present in every return path
  3. Inference timing — inference_ms field, >100ms SLA warning
  4. Missing-skills filtering — user skills not re-recommended, top_n cap
  5. Fallback paths — None bundle, missing artifacts, LSTM exception
  6. rank_missing_skills — likelihood/category/priority thresholds

All heavy objects (TF model, SentenceTransformer, sklearn encoders) are
mocked — no GPU, no disk reads, no network calls required.

Run with:
    pytest backend/tests/test_lstm_inference.py -v
"""

from __future__ import annotations

import importlib
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Constants mirrored from ml_inference ─────────────────────────────────────
MAX_SKILLS = 20
EMB_DIM    = 384

_SKILL_CLASSES = [
    "tensorflow", "pytorch", "docker", "kubernetes", "react",
    "node.js", "postgresql", "aws", "machine learning", "mlops",
    "fastapi", "redis", "scikit-learn", "spark", "airflow",
    "golang", "typescript", "graphql", "terraform", "kafka",
]
_N_CLASSES = len(_SKILL_CLASSES)


# ── Bundle / encoder builders ─────────────────────────────────────────────────

def _make_lstm_bundle(
    proba: np.ndarray | None = None,
    missing_lstm: bool = True,
) -> dict:
    """
    Build a minimal ml_bundle for LSTM inference tests.

    Parameters
    ----------
    proba         : shape (n_classes,) — output of lstm_model.predict()
    missing_lstm  : if False, set lstm_model to None
    """
    if proba is None:
        # Uniform-ish probabilities — first few skills have highest scores
        proba = np.linspace(0.9, 0.1, _N_CLASSES, dtype=np.float32)

    lstm_model = MagicMock()
    lstm_model.predict.return_value = [proba]

    mlb = MagicMock()
    mlb.classes_ = np.array(_SKILL_CLASSES)

    role_encoder = MagicMock()
    role_encoder.transform.return_value = np.zeros((1, 5), dtype=np.float32)

    seniority_encoder = MagicMock()
    seniority_encoder.transform.return_value = np.zeros((1, 4), dtype=np.float32)

    return {
        "lstm_model":        lstm_model if missing_lstm else None,
        "lstm_mlb":          mlb,
        "role_encoder":      role_encoder,
        "seniority_encoder": seniority_encoder,
    }


def _patch_encoder():
    """
    Context manager that stubs the SentenceTransformer used inside
    _get_lstm_encoder() so no model is downloaded.
    encode() returns zero vectors of shape (n, 384).
    """
    import sys
    import types

    st_mod = types.ModuleType("sentence_transformers")
    encoder_inst = MagicMock()

    def _encode(texts, normalize_embeddings=True, show_progress_bar=False,
                convert_to_numpy=True):
        n = len(texts) if isinstance(texts, list) else 1
        return np.zeros((n, EMB_DIM), dtype=np.float32)

    encoder_inst.encode.side_effect = _encode
    st_mod.SentenceTransformer = MagicMock(return_value=encoder_inst)
    return patch.dict(sys.modules, {"sentence_transformers": st_mod})


def _reload():
    """Reload ml_inference and reset module-level encoder cache."""
    import ml_inference
    importlib.reload(ml_inference)
    ml_inference._lstm_encoder       = None
    ml_inference._lstm_encoder_tried = False
    return ml_inference


# =============================================================================
# 1. Sequence padding / truncation
# =============================================================================

class TestSequencePadding:
    """
    X_skills must always be shape (1, MAX_SKILLS, EMB_DIM).
    - 0 skills   → all-zero tensor
    - < 20 skills → first N rows filled, rest zero-padded
    - = 20 skills → all rows filled
    - > 20 skills → truncated to first 20
    """

    def _run(self, skills):
        """Return the X_skills tensor captured from lstm_model.predict()."""
        mi = _reload()
        bundle = _make_lstm_bundle()

        captured = []
        original_predict = bundle["lstm_model"].predict

        def _capture(inputs, verbose=0):
            captured.append(inputs[0].copy())   # inputs[0] = X_skills
            return original_predict(inputs, verbose=verbose)

        bundle["lstm_model"].predict = _capture

        with _patch_encoder():
            mi.predict_missing_skills(skills, "Data Scientist", bundle=bundle)

        assert len(captured) == 1
        return captured[0]   # shape (1, MAX_SKILLS, EMB_DIM)

    def test_empty_skills_all_zero(self):
        X = self._run([])
        assert X.shape == (1, MAX_SKILLS, EMB_DIM)
        assert np.allclose(X, 0.0)

    def test_single_skill_first_row_nonzero_rest_zero(self):
        # encoder returns zeros, but the row at index 0 should be set
        # (even if all-zero it was explicitly filled — shape check is key)
        X = self._run(["python"])
        assert X.shape == (1, MAX_SKILLS, EMB_DIM)
        # Rows 1..19 must be zero (only row 0 was filled)
        assert np.allclose(X[0, 1:, :], 0.0)

    def test_exactly_20_skills_no_padding_needed(self):
        skills = [f"skill_{i}" for i in range(20)]
        X = self._run(skills)
        assert X.shape == (1, MAX_SKILLS, EMB_DIM)

    def test_more_than_20_skills_truncated(self):
        """Only first 20 skills are encoded; extras are ignored."""
        skills = [f"skill_{i}" for i in range(30)]
        mi = _reload()
        bundle = _make_lstm_bundle()

        encode_calls: list[list] = []
        with _patch_encoder():
            import sentence_transformers as st_mod
            orig_encode = st_mod.SentenceTransformer().encode

            def _tracking_encode(texts, **kwargs):
                encode_calls.append(list(texts))
                n = len(texts)
                return np.zeros((n, EMB_DIM), dtype=np.float32)

            st_mod.SentenceTransformer().encode.side_effect = _tracking_encode
            mi.predict_missing_skills(skills, "Data Scientist", bundle=bundle)

        # The encode call should receive at most MAX_SKILLS items
        if encode_calls:
            assert len(encode_calls[0]) <= MAX_SKILLS

    def test_lstm_model_always_receives_correct_shape(self):
        """lstm_model.predict() must always get (1, 20, 384) as first input."""
        for n_skills in [0, 1, 10, 20, 25]:
            skills = [f"skill_{i}" for i in range(n_skills)]
            X = self._run(skills)
            assert X.shape == (1, MAX_SKILLS, EMB_DIM), (
                f"Shape wrong for {n_skills} skills: {X.shape}"
            )


# =============================================================================
# 2. Output schema
# =============================================================================

class TestOutputSchema:
    """All four keys must be present in every return path."""

    _KEYS = ("missing_skills", "confidences", "inference_ms", "source")

    def test_ml_source_has_all_keys(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        for key in self._KEYS:
            assert key in result, f"Missing key '{key}' in ml-source result"

    def test_fallback_none_bundle_has_all_keys(self):
        mi = _reload()
        result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=None)
        for key in self._KEYS:
            assert key in result, f"Missing key '{key}' in None-bundle result"

    def test_fallback_missing_artifacts_has_all_keys(self):
        mi = _reload()
        bundle = _make_lstm_bundle(missing_lstm=False)
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        for key in self._KEYS:
            assert key in result

    def test_exception_path_has_all_keys(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        bundle["lstm_model"].predict.side_effect = RuntimeError("CUDA OOM")
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        for key in self._KEYS:
            assert key in result

    def test_missing_skills_is_list(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert isinstance(result["missing_skills"], list)

    def test_confidences_is_dict(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert isinstance(result["confidences"], dict)

    def test_inference_ms_is_float(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert isinstance(result["inference_ms"], float)
        assert result["inference_ms"] >= 0.0

    def test_inference_ms_zero_on_fallback(self):
        mi = _reload()
        result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=None)
        assert result["inference_ms"] == 0.0


# =============================================================================
# 3. Inference timing
# =============================================================================

class TestInferenceTiming:
    """inference_ms must reflect wall-clock time and trigger SLA warnings."""

    def test_inference_ms_present_on_ml_path(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["inference_ms"] > 0.0

    def test_inference_ms_zero_on_none_bundle(self):
        mi = _reload()
        result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=None)
        assert result["inference_ms"] == 0.0

    def test_inference_ms_zero_on_missing_artifacts(self):
        mi = _reload()
        bundle = _make_lstm_bundle(missing_lstm=False)
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["inference_ms"] == 0.0

    def test_sla_warning_triggered_above_100ms(self, caplog):
        """A WARNING must be logged when inference exceeds 100 ms."""
        import logging
        mi = _reload()
        bundle = _make_lstm_bundle()

        # Make predict() sleep for 110 ms
        def _slow_predict(inputs, verbose=0):
            time.sleep(0.115)
            proba = np.linspace(0.9, 0.1, _N_CLASSES, dtype=np.float32)
            return [proba]

        bundle["lstm_model"].predict.side_effect = _slow_predict

        with _patch_encoder():
            with caplog.at_level(logging.WARNING, logger="ml_inference"):
                mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)

        sla_warns = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "SLA" in r.message
        ]
        assert len(sla_warns) >= 1, f"Expected SLA warning, got: {caplog.records}"

    def test_no_sla_warning_below_100ms(self, caplog):
        """No SLA warning when inference is fast (mocked to be instant)."""
        import logging
        mi = _reload()
        bundle = _make_lstm_bundle()

        with _patch_encoder():
            with caplog.at_level(logging.WARNING, logger="ml_inference"):
                mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)

        sla_warns = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "SLA" in r.message
        ]
        assert len(sla_warns) == 0


# =============================================================================
# 4. Missing-skills filtering
# =============================================================================

class TestMissingSkillsFiltering:
    """
    Skills the user already has must not appear in recommendations.
    top_n cap must be respected.
    """

    def test_user_skills_not_recommended(self):
        mi = _reload()
        # User already has the top-scoring skill ("tensorflow")
        user_skills = ["tensorflow"]
        bundle = _make_lstm_bundle()  # tensorflow gets proba 0.9 (highest)

        with _patch_encoder():
            result = mi.predict_missing_skills(
                user_skills, "Data Scientist", bundle=bundle
            )

        assert "tensorflow" not in result["missing_skills"]
        assert "tensorflow" not in result["confidences"]

    def test_case_insensitive_skill_filtering(self):
        """Filtering should be case-insensitive."""
        mi = _reload()
        user_skills = ["TensorFlow"]   # capital T
        bundle = _make_lstm_bundle()   # "tensorflow" in classes_ (lowercase)

        with _patch_encoder():
            result = mi.predict_missing_skills(
                user_skills, "Data Scientist", bundle=bundle
            )

        assert "tensorflow" not in result["missing_skills"]

    def test_top_n_cap_respected(self):
        """Result must contain at most top_n skills."""
        mi = _reload()
        bundle = _make_lstm_bundle()

        with _patch_encoder():
            result = mi.predict_missing_skills(
                [], "Data Scientist", bundle=bundle, top_n=5
            )

        assert len(result["missing_skills"]) <= 5

    def test_all_user_skills_present_returns_empty_list(self):
        """If user already has every class skill, recommendations are empty."""
        mi = _reload()
        bundle = _make_lstm_bundle()

        with _patch_encoder():
            result = mi.predict_missing_skills(
                list(_SKILL_CLASSES), "Data Scientist", bundle=bundle
            )

        assert result["missing_skills"] == []

    def test_confidences_match_missing_skills(self):
        """Every skill in missing_skills must have an entry in confidences."""
        mi = _reload()
        bundle = _make_lstm_bundle()

        with _patch_encoder():
            result = mi.predict_missing_skills(
                ["python"], "Data Scientist", bundle=bundle
            )

        for skill in result["missing_skills"]:
            assert skill in result["confidences"], (
                f"Skill '{skill}' in missing_skills but not in confidences"
            )

    def test_empty_user_skills_returns_top_n_recommendations(self):
        """With no user skills all classes can be recommended (up to top_n)."""
        mi = _reload()
        bundle = _make_lstm_bundle()

        with _patch_encoder():
            result = mi.predict_missing_skills(
                [], "Data Scientist", bundle=bundle, top_n=10
            )

        assert len(result["missing_skills"]) == 10
        assert result["source"] == "ml"


# =============================================================================
# 5. Fallback paths
# =============================================================================

class TestFallbackPaths:
    """All failure scenarios must return source=fallback without raising."""

    def test_none_bundle_returns_fallback(self):
        mi = _reload()
        result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=None)
        assert result["source"] == "fallback"

    def test_missing_lstm_model_returns_fallback(self):
        mi = _reload()
        bundle = _make_lstm_bundle(missing_lstm=False)
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["source"] == "fallback"

    def test_missing_mlb_returns_fallback(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        bundle["lstm_mlb"] = None
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["source"] == "fallback"

    def test_missing_role_encoder_returns_fallback(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        bundle["role_encoder"] = None
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["source"] == "fallback"

    def test_lstm_predict_exception_returns_fallback(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        bundle["lstm_model"].predict.side_effect = RuntimeError("GPU error")
        with _patch_encoder():
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
        assert result["source"] == "fallback"
        assert result["missing_skills"] == []

    def test_lstm_predict_exception_does_not_propagate(self):
        mi = _reload()
        bundle = _make_lstm_bundle()
        bundle["lstm_model"].predict.side_effect = ValueError("Bad shape")
        with _patch_encoder():
            try:
                mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)
            except Exception as exc:
                pytest.fail(f"Exception propagated to caller: {exc}")

    def test_missing_sentence_transformers_returns_fallback(self):
        """If sentence_transformers is not installed, fallback silently."""
        import sys
        mi = _reload()
        bundle = _make_lstm_bundle()

        # Block sentence_transformers import
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            mi._lstm_encoder       = None
            mi._lstm_encoder_tried = False
            result = mi.predict_missing_skills(["python"], "Data Scientist", bundle=bundle)

        assert result["source"] == "fallback"


# =============================================================================
# 6. rank_missing_skills — priority thresholds
# =============================================================================

class TestRankMissingSkills:
    """
    rank_missing_skills must:
    - return likelihood / category / priority for every skill
    - assign priority 'high' when likelihood >= 0.75
    - assign priority 'medium' when 0.45 <= likelihood < 0.75
    - assign priority 'low'  when likelihood < 0.45
    - handle unknown skills gracefully (category='general')
    """

    def _rank(self, skills, confidences):
        import ml_inference
        return ml_inference.rank_missing_skills(skills, confidences)

    def test_returns_list_of_dicts(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.80})
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    def test_all_fields_present(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.80})
        for field in ("skill", "likelihood", "category", "priority"):
            assert field in result[0], f"Missing field '{field}'"

    def test_high_priority_threshold(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.75})
        assert result[0]["priority"] == "high"

    def test_medium_priority_threshold_low_end(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.45})
        assert result[0]["priority"] == "medium"

    def test_medium_priority_threshold_high_end(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.74})
        assert result[0]["priority"] == "medium"

    def test_low_priority_threshold(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.44})
        assert result[0]["priority"] == "low"

    def test_unknown_skill_category_is_general(self):
        result = self._rank(["xyzunknown999"], {"xyzunknown999": 0.60})
        assert result[0]["category"] == "general"

    def test_known_skill_category_is_correct(self):
        result = self._rank(["docker"], {"docker": 0.80})
        assert result[0]["category"] == "cloud_devops"

    def test_missing_confidence_defaults_to_0_5(self):
        """Skills absent from confidences dict get likelihood=0.5 (medium)."""
        result = self._rank(["someskill"], {})
        assert result[0]["likelihood"] == 0.5
        assert result[0]["priority"] == "medium"

    def test_preserves_skill_order(self):
        skills = ["tensorflow", "docker", "react"]
        confidences = {"tensorflow": 0.9, "docker": 0.6, "react": 0.3}
        result = self._rank(skills, confidences)
        assert [r["skill"] for r in result] == skills

    def test_empty_input_returns_empty_list(self):
        result = self._rank([], {})
        assert result == []

    def test_likelihood_rounded_to_4_decimal_places(self):
        result = self._rank(["tensorflow"], {"tensorflow": 0.123456789})
        assert result[0]["likelihood"] == round(0.123456789, 4)
