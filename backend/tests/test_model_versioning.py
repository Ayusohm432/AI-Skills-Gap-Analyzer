"""
tests/test_model_versioning.py
================================
Unit tests for the model versioning infrastructure.

Covers:
  1. versioning.py helpers — get_version(), get_version_dir(), save_version_artifacts()
  2. routes/models.py endpoints — list and detail, 404s, path traversal guard

All tests use tmp_path (pytest fixture) — no writes to the real models directory.

Run with:
    pytest backend/tests/test_model_versioning.py -v
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ── Fix for 'models is not a package' ────────────────────────────────────────
# backend/models.py (Pydantic schemas file) shadows the backend/models/
# directory.  We cannot use `import models.ml_training.versioning` because
# Python resolves `models` to the file, not the folder.
# Instead we load versioning.py directly from its absolute path once and
# register it under a unique module name so patch.object works correctly.

_VERSIONING_PATH = (
    Path(__file__).resolve().parent.parent
    / "models" / "ml_training" / "versioning.py"
)

def _get_vm():
    """Return the versioning module (cached after first load)."""
    mod_name = "_versioning_test_module"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, _VERSIONING_PATH)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Eagerly load so patch.object has a stable reference throughout the session
vm = _get_vm()


# ── Required metadata fields (acceptance criteria) ───────────────────────────
REQUIRED_FIELDS = (
    "model_name",
    "version",
    "training_date",
    "accuracy",
    "f1_score",
    "training_samples",
    "test_samples",
    "git_commit",
)


# =============================================================================
# 1. versioning.py helpers
# =============================================================================

class TestGetVersion:
    """get_version() resolution order: ML_MODEL_VERSION → MODEL_VERSION → v1.0"""

    def test_default_is_v1_0(self):
        env = {k: v for k, v in os.environ.items()
               if k not in ("ML_MODEL_VERSION", "MODEL_VERSION")}
        with patch.dict(os.environ, env, clear=True):
            assert vm.get_version() == "v1.0"

    def test_ml_model_version_env_takes_priority(self):
        with patch.dict(os.environ, {"ML_MODEL_VERSION": "v2.3", "MODEL_VERSION": "v1.9"}):
            assert vm.get_version() == "v2.3"

    def test_model_version_fallback(self):
        env = {k: v for k, v in os.environ.items() if k != "ML_MODEL_VERSION"}
        env["MODEL_VERSION"] = "v1.5"
        env.pop("ML_MODEL_VERSION", None)
        with patch.dict(os.environ, env, clear=True):
            assert vm.get_version() == "v1.5"


class TestGetVersionDir:
    """get_version_dir() must create the directory on disk."""

    def test_creates_directory(self, tmp_path):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            result = vm.get_version_dir("v9.9")
        assert result.is_dir()
        assert result.name == "v9.9"

    def test_uses_get_version_when_no_arg(self, tmp_path):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            with patch.dict(os.environ, {"ML_MODEL_VERSION": "v3.0"}):
                result = vm.get_version_dir()
        assert result.name == "v3.0"

    def test_idempotent_when_dir_exists(self, tmp_path):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            r1 = vm.get_version_dir("v1.0")
            r2 = vm.get_version_dir("v1.0")
        assert r1 == r2


class TestSaveVersionArtifacts:
    """save_version_artifacts() must write metadata.json with all 6 required fields."""

    def _save(self, tmp_path, **kwargs):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            return vm.save_version_artifacts(
                model_name=kwargs.get("model_name", "Test Model"),
                accuracy=kwargs.get("accuracy", 0.90),
                f1_score=kwargs.get("f1_score", 0.88),
                training_samples=kwargs.get("training_samples", 800),
                test_samples=kwargs.get("test_samples", 200),
                version=kwargs.get("version", "v1.0"),
                extra_metadata=kwargs.get("extra_metadata"),
            )

    def test_returns_path_object(self, tmp_path):
        result = self._save(tmp_path)
        assert isinstance(result, Path)

    def test_creates_version_directory(self, tmp_path):
        self._save(tmp_path)
        assert (tmp_path / "v1.0").is_dir()

    def test_writes_metadata_json(self, tmp_path):
        self._save(tmp_path)
        assert (tmp_path / "v1.0" / "metadata.json").exists()

    def test_all_required_fields_present(self, tmp_path):
        self._save(tmp_path)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        for field in REQUIRED_FIELDS:
            assert field in meta, f"Required field '{field}' missing from metadata.json"

    def test_accuracy_value_stored_correctly(self, tmp_path):
        self._save(tmp_path, accuracy=0.9231)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert meta["accuracy"] == pytest.approx(0.9231, abs=1e-5)

    def test_f1_score_value_stored_correctly(self, tmp_path):
        self._save(tmp_path, f1_score=0.8765)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert meta["f1_score"] == pytest.approx(0.8765, abs=1e-5)

    def test_training_samples_is_int(self, tmp_path):
        self._save(tmp_path, training_samples=4000)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert meta["training_samples"] == 4000
        assert isinstance(meta["training_samples"], int)

    def test_test_samples_is_int(self, tmp_path):
        self._save(tmp_path, test_samples=1000)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert meta["test_samples"] == 1000

    def test_training_date_is_iso_string(self, tmp_path):
        self._save(tmp_path)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert "T" in meta["training_date"]
        assert "+" in meta["training_date"] or "Z" in meta["training_date"]

    def test_git_commit_is_string(self, tmp_path):
        self._save(tmp_path)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert isinstance(meta["git_commit"], str)
        assert len(meta["git_commit"]) > 0

    def test_git_commit_falls_back_to_unknown_outside_repo(self, tmp_path):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            with patch.object(vm, "_detect_git_commit", return_value="unknown"):
                vm.save_version_artifacts(
                    model_name="Test", accuracy=0.9, f1_score=0.9,
                    training_samples=100, test_samples=20, version="v1.0"
                )
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert meta["git_commit"] == "unknown"

    def test_extra_metadata_stored_under_extra_key(self, tmp_path):
        self._save(tmp_path, extra_metadata={"auc_roc": 0.97, "brier": 0.04})
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert "extra" in meta
        assert meta["extra"]["auc_roc"] == pytest.approx(0.97)

    def test_no_extra_key_when_not_provided(self, tmp_path):
        self._save(tmp_path, extra_metadata=None)
        meta = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        assert "extra" not in meta

    def test_version_directory_created_automatically(self, tmp_path):
        """A brand-new version directory must be created without error."""
        self._save(tmp_path, version="v99.0")
        assert (tmp_path / "v99.0").is_dir()

    def test_different_versions_write_separate_files(self, tmp_path):
        with patch.object(vm, "_ML_MODELS_ROOT", tmp_path):
            vm.save_version_artifacts("M1", 0.9, 0.9, 100, 20, version="v1.0")
            vm.save_version_artifacts("M2", 0.95, 0.94, 200, 40, version="v2.0")
        assert (tmp_path / "v1.0" / "metadata.json").exists()
        assert (tmp_path / "v2.0" / "metadata.json").exists()
        m1 = json.loads((tmp_path / "v1.0" / "metadata.json").read_text())
        m2 = json.loads((tmp_path / "v2.0" / "metadata.json").read_text())
        assert m1["model_name"] == "M1"
        assert m2["model_name"] == "M2"


# =============================================================================
# 2. routes/models.py — API endpoints
# =============================================================================

def _write_std_meta(directory: Path, version: str, model_name: str) -> None:
    """Write a complete standardized metadata.json into a version directory."""
    directory.mkdir(parents=True, exist_ok=True)
    meta = {
        "model_name":       model_name,
        "version":          version,
        "training_date":    "2026-04-28T08:00:00+00:00",
        "accuracy":         0.92,
        "f1_score":         0.91,
        "training_samples": 4000,
        "test_samples":     1000,
        "git_commit":       "abc1234",
    }
    (directory / "metadata.json").write_text(json.dumps(meta))


class TestListVersionsEndpoint:

    def _setup(self, tmp_path):
        """Create v1.0, v1.1 with metadata, and v0.9 without metadata."""
        _write_std_meta(tmp_path / "v1.0", "v1.0", "RF Role Predictor")
        _write_std_meta(tmp_path / "v1.1", "v1.1", "LSTM Missing Skills")
        (tmp_path / "v0.9").mkdir()   # no metadata.json
        return tmp_path

    def _client(self, root):
        import routes.models as rm
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            return TestClient(app), rm

    def test_returns_200(self, tmp_path):
        import routes.models as rm
        root = self._setup(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            resp = TestClient(app).get("/api/v1/models/versions")
        assert resp.status_code == 200

    def test_count_correct(self, tmp_path):
        import routes.models as rm
        root = self._setup(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions").json()
        assert data["count"] == 3

    def test_version_with_no_metadata_has_flag(self, tmp_path):
        import routes.models as rm
        root = self._setup(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions").json()
        no_meta = [v for v in data["versions"] if v.get("version") == "v0.9"]
        assert len(no_meta) == 1
        assert no_meta[0].get("no_metadata") is True

    def test_schema_complete_flag_true_for_complete_metadata(self, tmp_path):
        import routes.models as rm
        root = self._setup(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions").json()
        v10 = next(v for v in data["versions"] if v.get("version") == "v1.0")
        assert v10["schema_complete"] is True

    def test_empty_models_root_returns_zero_count(self, tmp_path):
        import routes.models as rm
        empty = tmp_path / "empty_root"
        empty.mkdir()
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", empty):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions").json()
        assert data["count"] == 0

    def test_missing_models_root_returns_zero_count(self, tmp_path):
        import routes.models as rm
        nonexistent = tmp_path / "does_not_exist"
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", nonexistent):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions").json()
        assert data["count"] == 0


class TestGetVersionDetailEndpoint:

    def _write_meta(self, tmp_path, version="v1.0"):
        d = tmp_path / version
        _write_std_meta(d, version, "RF Role Predictor")
        (d / "role_predictor.pkl").write_bytes(b"fake")
        (d / "config.json").write_text("{}")
        return tmp_path

    def test_returns_200_for_existing_version(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            resp = TestClient(app).get("/api/v1/models/versions/v1.0")
        assert resp.status_code == 200

    def test_returns_metadata(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions/v1.0").json()
        assert data["metadata"]["model_name"] == "RF Role Predictor"
        assert data["metadata"]["git_commit"] == "abc1234"

    def test_returns_artifact_inventory(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions/v1.0").json()
        assert "role_predictor.pkl" in data["artifacts"]
        assert "config.json" in data["artifacts"]
        assert "metadata.json" in data["artifacts"]

    def test_schema_complete_flag_present(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            data = TestClient(app).get("/api/v1/models/versions/v1.0").json()
        assert "schema_complete" in data

    def test_returns_404_for_unknown_version(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            resp = TestClient(app, raise_server_exceptions=False).get(
                "/api/v1/models/versions/v99.0"
            )
        assert resp.status_code == 404

    def test_path_traversal_rejected(self, tmp_path):
        import routes.models as rm
        root = self._write_meta(tmp_path)
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", root):
            app.include_router(rm.router, prefix="/api/v1")
            resp = TestClient(app, raise_server_exceptions=False).get(
                "/api/v1/models/versions/..%2Fsecrets"
            )
        assert resp.status_code in (400, 404, 422)

    def test_returns_404_when_metadata_json_missing(self, tmp_path):
        import routes.models as rm
        d = tmp_path / "v2.0"
        d.mkdir(parents=True)   # no metadata.json
        app = FastAPI()
        with patch.object(rm, "_ML_MODELS_ROOT", tmp_path):
            app.include_router(rm.router, prefix="/api/v1")
            resp = TestClient(app, raise_server_exceptions=False).get(
                "/api/v1/models/versions/v2.0"
            )
        assert resp.status_code == 404
