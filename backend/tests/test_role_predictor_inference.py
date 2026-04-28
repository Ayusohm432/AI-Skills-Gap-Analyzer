"""
tests/test_role_predictor_inference.py
=======================================
Unit tests for the enhanced predict_role() in ml_inference.py and the
new POST /api/v1/predict-role FastAPI endpoint.

Covers:
  1. top_predictive_skills — derived from feature_importances_
  2. role_probabilities    — full {role: prob} dict
  3. inference_ms          — timing field present in all return paths
  4. Output schema          — all new keys present regardless of source
  5. <50 ms SLA            — warning is triggered when mock is slow
  6. /predict-role endpoint — smoke tests via FastAPI TestClient

No real model files or MongoDB connections required — all heavy objects
are mocked.

Run with:
    pytest backend/tests/test_role_predictor_inference.py -v
"""

from __future__ import annotations

import importlib
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Shared constants ──────────────────────────────────────────────────────────

_ROLE_LABELS   = ["Data Scientist", "Backend Developer", "Frontend Developer"]
_FEAT_NAMES    = ["python", "sql", "react", "docker", "pandas", "scikit-learn"]
_N_FEATS       = len(_FEAT_NAMES)
_N_ROLES       = len(_ROLE_LABELS)


# ── Bundle builders ───────────────────────────────────────────────────────────

def _make_bundle(
    confidence: float = 0.85,
    pred_idx:   int   = 0,
    with_importances: bool = True,
) -> dict:
    """
    Build a minimal ml_bundle whose role_predictor behaves deterministically.

    Parameters
    ----------
    confidence       : probability assigned to pred_idx
    pred_idx         : index into _ROLE_LABELS to predict
    with_importances : whether model has feature_importances_ attribute
    """
    model = MagicMock()
    model.predict.return_value = [pred_idx]

    proba = np.zeros(_N_ROLES, dtype=np.float32)
    proba[pred_idx] = confidence
    remaining = (1.0 - confidence) / max(_N_ROLES - 1, 1)
    for i in range(_N_ROLES):
        if i != pred_idx:
            proba[i] = remaining
    model.predict_proba.return_value = [proba]

    if with_importances:
        # Give importance to python (idx 0) and pandas (idx 4)
        importances = np.zeros(_N_FEATS, dtype=np.float32)
        importances[0] = 0.40   # python
        importances[4] = 0.30   # pandas
        importances[5] = 0.20   # scikit-learn
        importances[1] = 0.10   # sql
        model.feature_importances_ = importances
    else:
        # Simulate a model that has no importances (e.g. SVM)
        del model.feature_importances_

    return {
        "role_predictor": model,
        "role_config": {
            "feature_names": _FEAT_NAMES,
            "role_labels":   _ROLE_LABELS,
        },
    }


def _reload() -> object:
    import ml_inference
    importlib.reload(ml_inference)
    return ml_inference


# =============================================================================
# 1. top_predictive_skills
# =============================================================================

class TestTopPredictiveSkills:
    """
    top_predictive_skills must:
      - be derived from feature_importances_ × user skill binary vector
      - only include skills the user actually has (vec[i] == 1)
      - be sorted descending by feature importance
      - be empty when the model has no feature_importances_
    """

    def test_returns_list_of_strings(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        result = mi.predict_role(["python", "pandas"], bundle)
        assert isinstance(result["top_predictive_skills"], list)
        assert all(isinstance(s, str) for s in result["top_predictive_skills"])

    def test_only_contains_user_skills(self):
        """Must not contain skills the user does NOT have."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        # User has python + sql only
        result = mi.predict_role(["python", "sql"], bundle)
        user_skills_lower = {"python", "sql"}
        for skill in result["top_predictive_skills"]:
            assert skill.lower() in user_skills_lower, (
                f"'{skill}' not in user skills — should not appear"
            )

    def test_sorted_by_importance_descending(self):
        """Skills with higher feature_importances_ must come first."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        # User has python (importance 0.40) and pandas (importance 0.30)
        result = mi.predict_role(["python", "pandas", "scikit-learn"], bundle)
        top = result["top_predictive_skills"]
        # python has highest importance — must be first if present
        assert len(top) > 0
        assert top[0].lower() == "python"

    def test_empty_when_no_feature_importances(self):
        """If the model has no feature_importances_, return []."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=False)
        result = mi.predict_role(["python", "pandas"], bundle)
        assert result["top_predictive_skills"] == []

    def test_empty_skills_input_returns_empty_list(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        result = mi.predict_role([], bundle)
        assert result["top_predictive_skills"] == []

    def test_capped_at_top_5_by_default(self):
        """At most 5 skills should be returned (the default _TOP_PREDICTIVE_SKILLS_N)."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        # Give the user all features
        result = mi.predict_role(list(_FEAT_NAMES), bundle)
        assert len(result["top_predictive_skills"]) <= 5

    def test_unknown_skills_not_in_result(self):
        """Skills not in the feature vocabulary should not appear (they map to 0)."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, with_importances=True)
        result = mi.predict_role(["unknownlanguage123"], bundle)
        assert "unknownlanguage123" not in result["top_predictive_skills"]


# =============================================================================
# 2. role_probabilities
# =============================================================================

class TestRoleProbabilities:
    """
    role_probabilities must:
      - contain ALL role labels as keys (not just top-N)
      - have float values in [0, 1]
      - sum to approximately 1.0
      - be an empty dict when source=fallback
    """

    def test_contains_all_role_labels(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85)
        result = mi.predict_role(["python"], bundle)
        assert set(result["role_probabilities"].keys()) == set(_ROLE_LABELS)

    def test_values_are_floats_in_0_1(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85)
        result = mi.predict_role(["python"], bundle)
        for role, prob in result["role_probabilities"].items():
            assert isinstance(prob, float), f"prob for '{role}' is not float"
            assert 0.0 <= prob <= 1.0, f"prob for '{role}' out of range: {prob}"

    def test_probabilities_sum_to_one(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85)
        result = mi.predict_role(["python"], bundle)
        total = sum(result["role_probabilities"].values())
        assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}, expected ~1.0"

    def test_predicted_role_has_highest_probability(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85, pred_idx=0)
        result = mi.predict_role(["python"], bundle)
        probs = result["role_probabilities"]
        best_role = max(probs, key=probs.get)
        assert best_role == _ROLE_LABELS[0]

    def test_empty_dict_when_fallback(self):
        mi = _reload()
        empty_bundle = {}
        result = mi.predict_role(["python"], empty_bundle)
        assert result["source"] == "fallback"
        assert result["role_probabilities"] == {}

    def test_empty_dict_when_low_confidence(self):
        """role_probabilities must still be present (not empty) when confidence is low."""
        mi = _reload()
        bundle = _make_bundle(confidence=0.30, pred_idx=0)
        result = mi.predict_role(["python"], bundle)
        assert result["source"] == "low_confidence"
        # Still populated — caller needs the full map to understand why confidence is low
        assert len(result["role_probabilities"]) == _N_ROLES


# =============================================================================
# 3. inference_ms timing
# =============================================================================

class TestInferenceTiming:
    """
    inference_ms must:
      - always be present and be a non-negative float
      - be 0.0 on fallback path
      - trigger a warning log when > 50 ms
    """

    def test_inference_ms_present_and_float(self):
        mi = _reload()
        bundle = _make_bundle(confidence=0.85)
        result = mi.predict_role(["python"], bundle)
        assert "inference_ms" in result
        assert isinstance(result["inference_ms"], float)
        assert result["inference_ms"] >= 0.0

    def test_inference_ms_zero_on_fallback(self):
        mi = _reload()
        result = mi.predict_role(["python"], {})
        assert result["inference_ms"] == 0.0

    def test_inference_ms_logged_warning_above_50ms(self, caplog):
        """A warning must be logged when inference_ms > 50."""
        import logging
        mi = _reload()

        # Make predict_proba artificially slow (60 ms)
        model = MagicMock()
        model.predict.return_value = [0]

        proba = np.array([0.85, 0.10, 0.05], dtype=np.float32)

        def slow_predict_proba(_):
            time.sleep(0.065)   # 65 ms
            return [proba]

        model.predict_proba.side_effect = slow_predict_proba
        model.feature_importances_ = np.zeros(_N_FEATS, dtype=np.float32)

        bundle = {
            "role_predictor": model,
            "role_config": {
                "feature_names": _FEAT_NAMES,
                "role_labels":   _ROLE_LABELS,
            },
        }

        with caplog.at_level(logging.WARNING, logger="ml_inference"):
            mi.predict_role(["python"], bundle)

        warning_msgs = [r.message for r in caplog.records if r.levelname == "WARNING"]
        sla_warnings = [m for m in warning_msgs if "50 ms SLA" in m or "> 50 ms" in str(m)]
        assert len(sla_warnings) >= 1, (
            f"Expected '>50 ms SLA' warning, got: {warning_msgs}"
        )

    def test_inference_ms_no_warning_below_50ms(self, caplog):
        """No SLA warning should appear when inference is fast (mocked)."""
        import logging
        mi = _reload()
        bundle = _make_bundle(confidence=0.85)

        with caplog.at_level(logging.WARNING, logger="ml_inference"):
            mi.predict_role(["python"], bundle)

        sla_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "50 ms" in r.message
        ]
        assert len(sla_warnings) == 0


# =============================================================================
# 4. Output schema — all new keys always present
# =============================================================================

class TestOutputSchema:
    """
    All three new keys (role_probabilities, top_predictive_skills, inference_ms)
    must be present in every return dict from predict_role(), regardless of source.
    """

    _NEW_KEYS = ("role_probabilities", "top_predictive_skills", "inference_ms")

    def test_ml_source_has_all_new_keys(self):
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.85))
        for key in self._NEW_KEYS:
            assert key in result, f"Missing key '{key}' in ml-source result"

    def test_low_confidence_has_all_new_keys(self):
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.30))
        assert result["source"] == "low_confidence"
        for key in self._NEW_KEYS:
            assert key in result, f"Missing key '{key}' in low_confidence result"

    def test_fallback_has_all_new_keys(self):
        mi = _reload()
        result = mi.predict_role(["python"], {})
        assert result["source"] == "fallback"
        for key in self._NEW_KEYS:
            assert key in result, f"Missing key '{key}' in fallback result"

    def test_exception_path_has_all_new_keys(self):
        """Even when predict() raises, the except-block must return all new keys."""
        mi = _reload()
        model = MagicMock()
        model.predict.side_effect = RuntimeError("GPU error")
        bundle = {
            "role_predictor": model,
            "role_config": {"feature_names": _FEAT_NAMES, "role_labels": _ROLE_LABELS},
        }
        result = mi.predict_role(["python"], bundle)
        assert result["source"] == "fallback"
        for key in self._NEW_KEYS:
            assert key in result, f"Missing key '{key}' after exception"


# =============================================================================
# 5. Confidence fallback < 0.60 → "Auto Detect" (regression)
# =============================================================================

class TestConfidenceFallbackRegression:
    """Ensure the existing confidence-gate still works with the new return shape."""

    def test_below_threshold_source_is_low_confidence(self):
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.45))
        assert result["source"] == "low_confidence"

    def test_at_threshold_source_is_ml(self):
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.60))
        assert result["source"] == "ml"

    def test_above_threshold_source_is_ml(self):
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.90))
        assert result["source"] == "ml"

    def test_low_confidence_predicted_role_still_present(self):
        """Worker uses this for logging — must not be None."""
        mi = _reload()
        result = mi.predict_role(["python"], _make_bundle(0.45, pred_idx=1))
        assert result["predicted_role"] == _ROLE_LABELS[1]


# =============================================================================
# 6. /predict-role FastAPI endpoint — smoke tests
# =============================================================================

# ── One-time stub registration ────────────────────────────────────────────────
# bcrypt is a PyO3 C-extension that can only be initialised ONCE per Python
# process.  Deleting and re-importing `security` between tests causes bcrypt
# to try to re-initialise → ImportError.  The solution: register the motor /
# database stubs in sys.modules *before* security is first imported (i.e. at
# test-module load time), then never evict security again.
import sys as _sys
import types as _types

def _install_db_stubs_once() -> None:
    """Register motor / database stubs exactly once at module import time."""
    motor_asyncio_mod = _types.ModuleType("motor.motor_asyncio")
    motor_asyncio_mod.AsyncIOMotorClient = MagicMock()

    motor_mod = _types.ModuleType("motor")
    motor_mod.motor_asyncio = motor_asyncio_mod

    db_mod = _types.ModuleType("database")
    for _col in (
        "users_collection",
        "refresh_tokens_collection",
        "analyses_collection",
        "analysis_jobs_collection",
        "jobs_collection",
    ):
        setattr(db_mod, _col, MagicMock())

    for _name, _mod in {
        "motor":               motor_mod,
        "motor.motor_asyncio": motor_asyncio_mod,
        "database":            db_mod,
    }.items():
        _sys.modules.setdefault(_name, _mod)   # only register if not already present


_install_db_stubs_once()

# Now it is safe to import security / routes once for the whole test session.
# bcrypt initialises exactly once here; subsequent tests reuse the cached module.
from security import get_current_user as _get_current_user  # noqa: E402
from routes.jobs import router as _jobs_router               # noqa: E402


class TestPredictRoleEndpoint:
    """
    Integration smoke tests using FastAPI's TestClient.

    motor + database are stubbed at module-load time (above) so no real
    MongoDB connection is needed.  Each test builds a fresh FastAPI app
    with a different ml_bundle but reuses the already-imported router and
    get_current_user dependency (so bcrypt is never re-initialised).
    """

    @staticmethod
    def _build_client(bundle):
        """Return a TestClient wired to the /predict-role route."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.state.ml_models = bundle
        # Bypass JWT auth — always return a dummy user
        app.dependency_overrides[_get_current_user] = lambda: {"id": "test_user"}
        app.include_router(_jobs_router, prefix="/api/v1")
        return TestClient(app, raise_server_exceptions=False)

    def test_returns_200_with_valid_skills(self):
        client = self._build_client(_make_bundle(confidence=0.85))
        resp = client.post("/api/v1/predict-role", json={"skills": ["python", "pandas"]})
        assert resp.status_code == 200

    def test_response_has_required_fields(self):
        client = self._build_client(_make_bundle(confidence=0.85))
        resp = client.post("/api/v1/predict-role", json={"skills": ["python", "pandas"]})
        data = resp.json()
        for field in (
            "predicted_role", "confidence", "role_probabilities",
            "top_predictive_skills", "role_alternatives", "inference_ms", "source",
        ):
            assert field in data, f"Missing field '{field}' in /predict-role response"

    def test_low_confidence_returns_auto_detect(self):
        client = self._build_client(_make_bundle(confidence=0.30))
        resp = client.post("/api/v1/predict-role", json={"skills": ["python"]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["predicted_role"] == "Auto Detect"
        assert data["source"] == "low_confidence"

    def test_empty_skills_returns_422(self):
        """An empty list must fail Pydantic min_length=1 validation → 422."""
        client = self._build_client(_make_bundle(confidence=0.85))
        resp = client.post("/api/v1/predict-role", json={"skills": []})
        assert resp.status_code == 422

    def test_role_probabilities_is_dict(self):
        client = self._build_client(_make_bundle(confidence=0.85))
        resp = client.post("/api/v1/predict-role", json={"skills": ["python", "sql"]})
        assert isinstance(resp.json()["role_probabilities"], dict)

    def test_top_predictive_skills_is_list(self):
        client = self._build_client(_make_bundle(confidence=0.85))
        resp = client.post("/api/v1/predict-role", json={"skills": ["python", "pandas"]})
        assert isinstance(resp.json()["top_predictive_skills"], list)

    def test_503_when_bundle_is_none(self):
        """If ML models are not loaded the endpoint must return HTTP 503."""
        client = self._build_client(None)   # app.state.ml_models = None
        resp = client.post("/api/v1/predict-role", json={"skills": ["python"]})
        assert resp.status_code == 503
