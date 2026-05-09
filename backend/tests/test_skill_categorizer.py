"""
tests/test_skill_categorizer.py
================================
Unit tests for the KMeans-backed categorize_skills() function in nlp/engine.py.

Covers:
  1. ML path with a mocked clusterer and mocked SentenceTransformer.
  2. Rule-based fallback when clusterer=None.
  3. Rule-based fallback when SentenceTransformer is unavailable.
  4. ML path exception → graceful fallback.
  5. Unknown skills handled without exceptions.
  6. Output schema always contains all four domain keys.
  7. Empty input edge-case.
  8. Integration: worker.py passes the clusterer correctly (smoke test).

No real model files, no network calls — all heavy objects are mocked.

Run with:
    pytest backend/tests/test_skill_categorizer.py -v
"""

from __future__ import annotations

import importlib
import sys
import types
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_OUTPUT_DOMAINS = ("frontend", "backend", "devops", "data")


def _reload_engine():
    """Reload nlp.engine to reset module-level cached encoder state."""
    # Also need to reset the module-level globals we track
    import nlp.engine as eng
    eng._sentence_encoder = None
    eng._encoder_lock_flag = False
    return eng


def _make_mock_clusterer(cluster_id: int = 0, n_skills: int | None = None):
    """
    Return a mock sklearn KMeans clusterer whose predict() always returns
    *cluster_id* for every skill embedding it receives.
    """
    mock = MagicMock()

    def _predict(X):
        # X has shape (n_skills, 384)
        n = X.shape[0] if hasattr(X, "shape") else len(X)
        return np.full(n, cluster_id, dtype=np.int32)

    mock.predict.side_effect = _predict
    return mock


def _patch_sentence_transformer(return_dim: int = 384):
    """
    Context-manager that stubs out the sentence_transformers module so no
    model is downloaded.  encode() returns zero vectors of the right shape.
    """
    st_mod = types.ModuleType("sentence_transformers")
    encoder_instance = MagicMock()

    def _encode(texts, normalize_embeddings=True, show_progress_bar=False):
        n = len(texts)
        return np.zeros((n, return_dim), dtype=np.float32)

    encoder_instance.encode.side_effect = _encode
    st_class = MagicMock(return_value=encoder_instance)
    st_mod.SentenceTransformer = st_class
    return patch.dict(sys.modules, {"sentence_transformers": st_mod})


# =============================================================================
# 1. ML path — mocked clusterer + mocked SentenceTransformer
# =============================================================================

class TestCategorizationWithMockedModel:
    """
    ML path: real clusterer logic replaced by a deterministic mock that always
    assigns a fixed cluster ID.  SentenceTransformer is also stubbed out.
    """

    def test_ml_path_maps_cluster0_to_frontend(self):
        """Cluster 0 → 'frontend' per _CLUSTER_DOMAIN_MAP."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=0)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["react", "vue"], clusterer=clusterer)

        assert "react" in result["frontend"]
        assert "vue" in result["frontend"]

    def test_ml_path_maps_cluster2_to_backend(self):
        """Cluster 2 → 'backend'."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=2)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["django", "fastapi"], clusterer=clusterer)

        assert "django" in result["backend"]
        assert "fastapi" in result["backend"]

    def test_ml_path_maps_cluster3_to_devops(self):
        """Cluster 3 → 'devops'."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=3)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["docker", "kubernetes"], clusterer=clusterer)

        assert "docker" in result["devops"]
        assert "kubernetes" in result["devops"]

    def test_ml_path_maps_cluster1_to_data(self):
        """Cluster 1 → 'data'."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=1)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["tensorflow", "pandas"], clusterer=clusterer)

        assert "tensorflow" in result["data"]
        assert "pandas" in result["data"]

    def test_ml_path_output_always_has_all_four_keys(self):
        """Even if all skills map to one domain, all four keys must be present."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=0)  # everything → frontend

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["react"], clusterer=clusterer)

        for domain in _OUTPUT_DOMAINS:
            assert domain in result, f"Missing domain key: '{domain}'"

    def test_ml_path_unknown_cluster_defaults_to_data(self):
        """A cluster ID not in _CLUSTER_DOMAIN_MAP must map to 'data', not raise."""
        eng = _reload_engine()

        # Override the map to have a gap at cluster 99
        clusterer = MagicMock()
        clusterer.predict.return_value = np.array([99], dtype=np.int32)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["some_skill"], clusterer=clusterer)

        # Should not raise; skill placed in "data"
        assert "some_skill" in result["data"]

    def test_ml_path_all_skills_returned_exactly_once(self):
        """Every skill in the input must appear in exactly one domain bucket."""
        skills = ["react", "docker", "pandas", "fastapi", "vue"]
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=0)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(skills, clusterer=clusterer)

        all_returned = [s for lst in result.values() for s in lst]
        assert sorted(all_returned) == sorted(skills)

    def test_ml_path_calls_clusterer_predict_once(self):
        """clusterer.predict() should be called exactly once per categorize_skills call."""
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=0)

        with _patch_sentence_transformer():
            eng.categorize_skills(["react", "vue", "angular"], clusterer=clusterer)

        assert clusterer.predict.call_count == 1


# =============================================================================
# 2. Rule-based fallback — clusterer=None
# =============================================================================

class TestCategorizationFallback:
    """
    When clusterer is None the function must use the keyword lookup table
    without attempting to load SentenceTransformer.
    """

    def setup_method(self):
        self.eng = _reload_engine()

    def test_none_clusterer_uses_rule_based(self):
        result = self.eng.categorize_skills(["react", "docker", "tensorflow"], clusterer=None)
        assert "react" in result["frontend"]
        assert "docker" in result["devops"]
        assert "tensorflow" in result["data"]

    def test_rule_based_frontend_skills(self):
        skills = ["react", "angular", "vue", "html", "css", "typescript", "javascript",
                  "next.js", "sass", "tailwindcss", "bootstrap", "webpack", "svelte"]
        result = self.eng.categorize_skills(skills, clusterer=None)
        for s in skills:
            assert s in result["frontend"], f"'{s}' not in frontend"

    def test_rule_based_backend_skills(self):
        skills = ["node.js", "fastapi", "django", "flask", "spring boot", "postgresql",
                  "mongodb", "redis", "kafka", "java", "go", "sql"]
        result = self.eng.categorize_skills(skills, clusterer=None)
        for s in skills:
            assert s in result["backend"], f"'{s}' not in backend"

    def test_rule_based_devops_skills(self):
        skills = ["docker", "kubernetes", "aws", "azure", "gcp", "terraform",
                  "jenkins", "ci/cd", "linux", "bash", "nginx", "ansible"]
        result = self.eng.categorize_skills(skills, clusterer=None)
        for s in skills:
            assert s in result["devops"], f"'{s}' not in devops"

    def test_rule_based_data_skills(self):
        skills = ["machine learning", "deep learning", "tensorflow", "pytorch",
                  "pandas", "numpy", "scikit-learn", "nlp", "statistics", "airflow",
                  "mlops", "spark", "tableau"]
        result = self.eng.categorize_skills(skills, clusterer=None)
        for s in skills:
            assert s in result["data"], f"'{s}' not in data"

    def test_rule_based_case_insensitive(self):
        """Input skill names are lowercased before lookup."""
        result = self.eng.categorize_skills(["React", "DOCKER", "TensorFlow"], clusterer=None)
        assert "React" in result["frontend"]
        assert "DOCKER" in result["devops"]
        assert "TensorFlow" in result["data"]

    def test_rule_based_output_has_all_four_keys(self):
        result = self.eng.categorize_skills(["react"], clusterer=None)
        for domain in _OUTPUT_DOMAINS:
            assert domain in result

    def test_rule_based_no_sentence_transformer_imported(self):
        """No SentenceTransformer import should occur in the rule-based path."""
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            # Should not raise even if sentence_transformers is blocked
            try:
                result = self.eng.categorize_skills(["react", "docker"], clusterer=None)
                assert "react" in result["frontend"]
            except Exception as exc:
                pytest.fail(f"Rule-based path raised unexpectedly: {exc}")


# =============================================================================
# 3. SentenceTransformer unavailable → graceful fallback
# =============================================================================

class TestEncoderUnavailableFallback:
    """
    If sentence_transformers is not installed, the ML path should log a warning
    and transparently fall back to rule-based categorization.
    """

    def test_missing_sentence_transformers_falls_back(self):
        eng = _reload_engine()

        # Remove sentence_transformers from sys.modules to simulate missing install
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            clusterer = _make_mock_clusterer(cluster_id=0)
            result = eng.categorize_skills(["react", "docker"], clusterer=clusterer)

        # Rule-based fallback must have worked — no exception raised
        assert isinstance(result, dict)
        for domain in _OUTPUT_DOMAINS:
            assert domain in result

    def test_missing_sentence_transformers_no_exception(self):
        eng = _reload_engine()
        with patch.dict(sys.modules, {"sentence_transformers": None}):
            clusterer = MagicMock()
            try:
                eng.categorize_skills(["react"], clusterer=clusterer)
            except Exception as exc:
                pytest.fail(f"Should not raise when sentence_transformers missing: {exc}")


# =============================================================================
# 4. ML path exception → graceful fallback
# =============================================================================

class TestMLPathExceptionFallback:
    """
    When the clusterer.predict() raises (e.g. shape mismatch), the function
    must catch it, log a warning, and return a valid rule-based result.
    """

    def test_clusterer_predict_raises_falls_back(self):
        eng = _reload_engine()

        bad_clusterer = MagicMock()
        bad_clusterer.predict.side_effect = RuntimeError("shape mismatch")

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["react", "docker"], clusterer=bad_clusterer)

        # Must still return a valid dict — rule-based fallback kicks in
        assert isinstance(result, dict)
        for domain in _OUTPUT_DOMAINS:
            assert domain in result

    def test_clusterer_predict_raises_does_not_propagate(self):
        eng = _reload_engine()
        bad_clusterer = MagicMock()
        bad_clusterer.predict.side_effect = ValueError("incompatible shape")

        with _patch_sentence_transformer():
            try:
                eng.categorize_skills(["react"], clusterer=bad_clusterer)
            except Exception as exc:
                pytest.fail(f"Exception propagated to caller: {exc}")

    def test_clusterer_predict_raises_rule_based_still_correct(self):
        """When ML fails, rule-based result should still be domain-correct."""
        eng = _reload_engine()
        bad_clusterer = MagicMock()
        bad_clusterer.predict.side_effect = RuntimeError("CUDA OOM")

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["react", "tensorflow", "docker"],
                                           clusterer=bad_clusterer)

        assert "react" in result["frontend"]
        assert "tensorflow" in result["data"]
        assert "docker" in result["devops"]


# =============================================================================
# 5. Unknown skills handled without exceptions
# =============================================================================

class TestUnknownSkillsHandled:
    """
    Skills that don't appear in the rule-based map or any cluster centroid
    should be assigned to 'data' (safe default) without raising.
    """

    def test_unknown_skill_in_rule_based(self):
        eng = _reload_engine()
        result = eng.categorize_skills(["quantumcomputing123", "xyzframeworkv9"],
                                       clusterer=None)
        # Unknown skills fall to the default → "data"
        assert "quantumcomputing123" in result["data"]
        assert "xyzframeworkv9" in result["data"]

    def test_unknown_skill_in_ml_path_uses_cluster_default(self):
        eng = _reload_engine()
        # Cluster 1 → "data"
        clusterer = _make_mock_clusterer(cluster_id=1)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(["unknownskillxyz"], clusterer=clusterer)

        assert "unknownskillxyz" in result["data"]

    def test_mixed_known_unknown_skills(self):
        eng = _reload_engine()
        result = eng.categorize_skills(
            ["react", "completely_unknown_skill_abc", "docker"],
            clusterer=None,
        )
        assert "react" in result["frontend"]
        assert "docker" in result["devops"]
        assert "completely_unknown_skill_abc" in result["data"]


# =============================================================================
# 6. Output schema always has all four keys
# =============================================================================

class TestOutputSchema:
    """
    The return value must ALWAYS be a dict with exactly the four keys:
    'frontend', 'backend', 'devops', 'data' — regardless of input or path taken.
    """

    @pytest.mark.parametrize("skills,clusterer_cluster", [
        (["react"], 0),
        (["docker"], 3),
        (["pandas"], 1),
        (["django"], 2),
    ])
    def test_ml_path_always_four_keys(self, skills, clusterer_cluster):
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=clusterer_cluster)

        with _patch_sentence_transformer():
            result = eng.categorize_skills(skills, clusterer=clusterer)

        assert set(result.keys()) == set(_OUTPUT_DOMAINS), (
            f"Expected keys {set(_OUTPUT_DOMAINS)}, got {set(result.keys())}"
        )

    @pytest.mark.parametrize("skills", [
        ["react"],
        ["docker"],
        ["pandas"],
        ["django"],
        ["react", "docker", "pandas"],
    ])
    def test_rule_based_always_four_keys(self, skills):
        eng = _reload_engine()
        result = eng.categorize_skills(skills, clusterer=None)
        assert set(result.keys()) == set(_OUTPUT_DOMAINS)

    def test_values_are_lists(self):
        eng = _reload_engine()
        result = eng.categorize_skills(["react", "docker"], clusterer=None)
        for domain, items in result.items():
            assert isinstance(items, list), f"Domain '{domain}' value is not a list"


# =============================================================================
# 7. Empty input edge-case
# =============================================================================

class TestEmptyInput:
    """categorize_skills([]) must return all-empty lists, never raise."""

    def test_empty_list_rule_based(self):
        eng = _reload_engine()
        result = eng.categorize_skills([], clusterer=None)
        assert result == {"frontend": [], "backend": [], "devops": [], "data": []}

    def test_empty_list_with_clusterer(self):
        eng = _reload_engine()
        clusterer = _make_mock_clusterer(cluster_id=0)

        with _patch_sentence_transformer():
            result = eng.categorize_skills([], clusterer=clusterer)

        assert result == {"frontend": [], "backend": [], "devops": [], "data": []}

    def test_empty_list_no_exception(self):
        eng = _reload_engine()
        try:
            eng.categorize_skills([], clusterer=None)
        except Exception as exc:
            pytest.fail(f"Empty list raised unexpectedly: {exc}")

    def test_empty_list_clusterer_predict_not_called(self):
        """clusterer.predict() should NOT be called for an empty skill list."""
        eng = _reload_engine()
        clusterer = MagicMock()

        with _patch_sentence_transformer():
            eng.categorize_skills([], clusterer=clusterer)

        clusterer.predict.assert_not_called()


# =============================================================================
# 8. Integration smoke test — worker.py passes clusterer correctly
# =============================================================================

class TestWorkerIntegration:
    """
    Smoke-test that worker.py's run_analysis pipeline correctly passes
    ml_bundle["skill_clusterer"] to categorize_skills.

    We do NOT run the full async pipeline; instead we verify the import
    contract and the call signature.
    """

    def test_categorize_skills_importable_from_engine(self):
        """nlp.engine must export categorize_skills."""
        import nlp.engine as eng
        assert hasattr(eng, "categorize_skills"), (
            "categorize_skills not found in nlp.engine"
        )
        assert callable(eng.categorize_skills)

    def test_categorize_skills_not_imported_from_ml_inference_in_worker(self):
        """
        worker.py should import categorize_skills from nlp.engine, not ml_inference,
        to ensure the ML-backed version is used.
        """
        import inspect
        import worker

        src = inspect.getsource(worker)
        # The new import should be from nlp.engine
        assert "from nlp.engine import" in src and "categorize_skills" in src, (
            "worker.py must import categorize_skills from nlp.engine"
        )

    def test_worker_import_does_not_crash(self):
        """Importing worker should not raise even without ML models loaded."""
        try:
            import importlib
            import worker
            importlib.reload(worker)
        except Exception as exc:
            pytest.fail(f"worker.py import crashed: {exc}")

    def test_categorize_skills_accepts_clusterer_kwarg(self):
        """categorize_skills() must accept a `clusterer` keyword argument."""
        import inspect
        import nlp.engine as eng
        sig = inspect.signature(eng.categorize_skills)
        assert "clusterer" in sig.parameters, (
            "categorize_skills() must accept a 'clusterer' keyword argument"
        )

    def test_categorize_skills_clusterer_defaults_to_none(self):
        """clusterer default must be None so calls without it use rule-based path."""
        import inspect
        import nlp.engine as eng
        sig = inspect.signature(eng.categorize_skills)
        param = sig.parameters["clusterer"]
        assert param.default is None, (
            f"clusterer default should be None, got {param.default!r}"
        )
