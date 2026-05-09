"""
tests/test_ml_fallback.py
=========================
Unit tests for the graceful ML fallback logic.

All three failure modes are covered:
  1. Role-predictor confidence < 0.60  →  source="low_confidence"
  2. Model file missing (bundle=None)  →  source="fallback" for both functions
  3. LSTM inference raises exception   →  source="fallback", empty skill list

No real models or MongoDB connection are required; all heavy objects are mocked.

Run with:
    pytest backend/tests/test_ml_fallback.py -v
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_role_bundle(confidence: float, role_labels: list[str] | None = None) -> dict:
    """
    Build a minimal ml_bundle that makes predict_role return *confidence*
    for the first label.
    """
    labels = role_labels or ["Data Scientist", "Backend Developer", "ML Engineer"]
    n = len(labels)

    model = MagicMock()
    model.predict.return_value = [0]                          # always pick index 0

    proba = np.zeros(n, dtype=np.float32)
    proba[0] = confidence
    # Distribute the remaining probability mass uniformly
    if n > 1:
        rest = (1.0 - confidence) / (n - 1)
        proba[1:] = rest
    model.predict_proba.return_value = [proba]

    return {
        "role_predictor": model,
        "role_config": {
            "feature_names": ["python", "sql", "docker"],
            "role_labels":   labels,
        },
    }


def _make_lstm_bundle(raise_on_predict: bool = False) -> dict:
    """
    Build a minimal ml_bundle for the LSTM path.
    If *raise_on_predict* is True the model.predict() call will raise RuntimeError.
    """
    lstm = MagicMock()
    if raise_on_predict:
        lstm.predict.side_effect = RuntimeError("CUDA out of memory")
    else:
        # Return all-zero probabilities (nothing recommended)
        lstm.predict.return_value = [np.zeros(3, dtype=np.float32)]

    mlb = MagicMock()
    mlb.classes_ = np.array(["TensorFlow", "Docker", "Kubernetes"])

    role_enc = MagicMock()
    role_enc.transform.return_value = np.zeros((1, 5), dtype=np.float32)

    sen_enc = MagicMock()
    sen_enc.transform.return_value = np.zeros((1, 4), dtype=np.float32)

    return {
        "lstm_model":        lstm,
        "lstm_mlb":          mlb,
        "role_encoder":      role_enc,
        "seniority_encoder": sen_enc,
    }


# ── Patch sentence-transformers so LSTM tests don't download models ────────────

def _patch_sentence_transformers():
    """Return a context-manager that stubs out SentenceTransformer."""
    st_mod   = types.ModuleType("sentence_transformers")
    st_class = MagicMock()
    # encode() returns a zero vector of the right shape
    st_class.return_value.encode.return_value = np.zeros(384, dtype=np.float32)
    st_mod.SentenceTransformer = st_class
    return patch.dict(sys.modules, {"sentence_transformers": st_mod})


# =============================================================================
# 1. Role-predictor: confidence below threshold
# =============================================================================

class TestRoleConfidenceFallback:
    """
    When the Random Forest's top-class probability < ROLE_CONFIDENCE_THRESHOLD (0.60)
    predict_role() must return source="low_confidence" instead of "ml".
    """

    def _call(self, confidence: float) -> dict:
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        bundle = _make_role_bundle(confidence)
        return ml_inference.predict_role(["python", "sql"], bundle)

    def test_below_threshold_returns_low_confidence_source(self):
        result = self._call(0.45)
        assert result["source"] == "low_confidence", (
            f"Expected source='low_confidence', got {result['source']!r}"
        )

    def test_below_threshold_preserves_predicted_role_for_logging(self):
        """The role name must be preserved so the caller can log what was discarded."""
        result = self._call(0.45)
        assert result["predicted_role"] == "Data Scientist"

    def test_below_threshold_preserves_actual_confidence_value(self):
        result = self._call(0.45)
        assert abs(result["confidence"] - 0.45) < 0.01

    def test_above_threshold_returns_ml_source(self):
        result = self._call(0.85)
        assert result["source"] == "ml"

    def test_exactly_at_threshold_returns_ml_source(self):
        """Boundary: 0.60 is inclusive (≥ threshold passes)."""
        result = self._call(0.60)
        assert result["source"] == "ml"

    def test_just_below_threshold_returns_low_confidence(self):
        result = self._call(0.599)
        assert result["source"] == "low_confidence"


# =============================================================================
# 2. Model file missing — bundle is None or all artifacts are None
# =============================================================================

class TestModelFileMissing:
    """
    When the ML bundle is None (startup failed to find model files) both
    predict_role() and predict_missing_skills() must return source="fallback"
    without raising any exception.
    """

    def test_predict_role_none_bundle_returns_fallback(self):
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        result = ml_inference.predict_role(["python"], {})
        assert result["source"] == "fallback"
        assert result["predicted_role"] is None
        assert result["confidence"] == 0.0
        assert result["top_roles"] == []

    def test_predict_role_none_model_inside_bundle_returns_fallback(self):
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        # Bundle present but model artifact is None (FileNotFoundError at load time)
        bundle = {"role_predictor": None, "role_config": {"feature_names": [], "role_labels": []}}
        result = ml_inference.predict_role(["python"], bundle)
        assert result["source"] == "fallback"

    def test_predict_missing_skills_none_bundle_returns_fallback(self):
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        result = ml_inference.predict_missing_skills(
            current_skills=["python"],
            target_role="Data Scientist",
            bundle=None,
        )
        assert result["source"] == "fallback"
        assert result["missing_skills"] == []
        assert result["confidences"] == {}

    def test_predict_missing_skills_missing_lstm_artifact_returns_fallback(self):
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        # Partial bundle – lstm_model present but role_encoder is None
        bundle = {
            "lstm_model":        MagicMock(),
            "lstm_mlb":          MagicMock(),
            "role_encoder":      None,      # ← missing artifact
            "seniority_encoder": MagicMock(),
        }
        result = ml_inference.predict_missing_skills(
            current_skills=["python"],
            target_role="Data Scientist",
            bundle=bundle,
        )
        assert result["source"] == "fallback"

    def test_no_exception_raised_when_bundle_is_none(self):
        """Pipeline must never raise; fallback dicts are always returned."""
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        try:
            ml_inference.predict_role([], {})
            ml_inference.predict_missing_skills([], "Unknown Role", bundle=None)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Unexpected exception raised: {exc}")


# =============================================================================
# 3. LSTM inference exception
# =============================================================================

class TestLSTMInferenceFallback:
    """
    When the LSTM model.predict() raises (e.g. shape mismatch, OOM)
    predict_missing_skills() must catch it and return source="fallback"
    with empty lists — never propagating the exception.
    """

    def _call(self, raise_on_predict: bool = True) -> dict:
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        bundle = _make_lstm_bundle(raise_on_predict=raise_on_predict)

        with _patch_sentence_transformers():
            return ml_inference.predict_missing_skills(
                current_skills=["python", "sql"],
                target_role="Data Scientist",
                seniority="Mid-level",
                bundle=bundle,
                top_n=5,
            )

    def test_lstm_exception_returns_fallback_source(self):
        result = self._call(raise_on_predict=True)
        assert result["source"] == "fallback"

    def test_lstm_exception_returns_empty_missing_skills(self):
        result = self._call(raise_on_predict=True)
        assert result["missing_skills"] == []

    def test_lstm_exception_returns_empty_confidences(self):
        result = self._call(raise_on_predict=True)
        assert result["confidences"] == {}

    def test_lstm_exception_does_not_propagate(self):
        """The exception must be swallowed and logged, not re-raised."""
        try:
            self._call(raise_on_predict=True)
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"Exception propagated to caller: {exc}")

    def test_lstm_no_exception_returns_ml_source(self):
        """Sanity check: a clean inference returns source='ml'."""
        import importlib
        import ml_inference
        importlib.reload(ml_inference)

        bundle = _make_lstm_bundle(raise_on_predict=False)
        # Patch mlb.classes_ and return a non-trivial prediction
        classes = np.array(["TensorFlow", "Docker", "Kubernetes"])
        bundle["lstm_mlb"].classes_ = classes
        # Make predictions: all skills already owned → recommended list empty
        bundle["lstm_model"].predict.return_value = [
            np.array([0.9, 0.8, 0.7], dtype=np.float32)
        ]

        with _patch_sentence_transformers():
            result = ml_inference.predict_missing_skills(
                current_skills=[],          # user has nothing → all recommended
                target_role="Data Scientist",
                bundle=bundle,
                top_n=3,
            )
        assert result["source"] == "ml"
        assert len(result["missing_skills"]) > 0


# =============================================================================
# 4. _static_skill_gap helper (worker.py)
# =============================================================================

class TestStaticSkillGap:
    """
    Unit tests for the _static_skill_gap() helper extracted in worker.py.
    Ensures it correctly subtracts found skills from the required set.
    """

    def _get_fn(self):
        import importlib
        import worker
        importlib.reload(worker)
        return worker._static_skill_gap

    def test_known_role_returns_missing_skills(self):
        fn = self._get_fn()
        result = fn("Backend Developer", ["Python", "Docker"])
        # Node.js, SQL, AWS, API Design, MongoDB, FastAPI should be missing
        assert "Node.js" in result
        assert "Python" not in result
        assert "Docker" not in result

    def test_case_insensitive_matching(self):
        fn = self._get_fn()
        result = fn("Data Scientist", ["python", "SQL"])   # lowercase input
        assert "Python" not in result
        assert "SQL" not in result

    def test_unknown_role_returns_empty_list(self):
        fn = self._get_fn()
        result = fn("Quantum Engineer", ["python"])
        assert result == []

    def test_empty_found_skills_returns_all_required(self):
        fn = self._get_fn()
        result = fn("Frontend Developer", [])
        assert len(result) > 0

    def test_all_skills_present_returns_empty(self):
        fn = self._get_fn()
        all_fe = ["React", "JavaScript", "HTML", "CSS", "TypeScript", "TailwindCSS", "Next.js"]
        result = fn("Frontend Developer", all_fe)
        assert result == []
