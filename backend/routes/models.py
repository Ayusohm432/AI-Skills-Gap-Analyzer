"""
routes/models.py
================
Model versioning management API.

Endpoints
---------
GET  /api/v1/models/active
    Returns the currently active model version (ML_MODEL_VERSION env var)
    together with its full metadata.json and artifact inventory.

GET  /api/v1/models/versions
    Lists every version directory under models/ml_models/ with a summary
    of their metadata.json (accuracy, f1, etc.).

GET  /api/v1/models/metrics/{version}
    Returns only the numeric metrics from metadata.json for a specific
    version (distinct from the full-detail /versions/{version} endpoint).

POST /api/v1/models/activate/{version}
    Promotes a version to active by writing ML_MODEL_VERSION=<version>
    to the .env file.  Requires the X-Admin-Key header.
    Returns 202 Accepted — uvicorn --reload picks up the change automatically.

Authentication
--------------
GET  endpoints — no authentication required (metadata contains no PII/secrets).
POST endpoint  — requires X-Admin-Key header matching the ADMIN_API_KEY env var.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from security import require_admin_key

logger = logging.getLogger("routes.models")

router = APIRouter()

# ── Paths ─────────────────────────────────────────────────────────────────────

# Resolves to: <repo>/backend/models/ml_models/
_ML_MODELS_ROOT = (
    Path(__file__).resolve().parent.parent / "models" / "ml_models"
)

# The .env file that stores ML_MODEL_VERSION (and other server config).
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# ── Constants ─────────────────────────────────────────────────────────────────

_REQUIRED_METADATA_FIELDS = (
    "model_name",
    "version",
    "training_date",
    "accuracy",
    "f1_score",
    "training_samples",
    "test_samples",
    "git_commit",
)

# Metrics fields extracted from metadata.json for the /metrics endpoint.
_METRIC_FIELDS = ("accuracy", "f1_score", "training_samples", "test_samples")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _version_dirs() -> list[Path]:
    """Return sorted list of version sub-directories (e.g. v1.0, v1.1)."""
    if not _ML_MODELS_ROOT.exists():
        return []
    return sorted(
        [d for d in _ML_MODELS_ROOT.iterdir() if d.is_dir()],
        key=lambda p: p.name,
    )


def _read_metadata(version_dir: Path) -> dict | None:
    """Read and parse metadata.json; return None on any failure."""
    meta_path = version_dir / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def _sanitize_version(version: str) -> None:
    """Raise 400 if the version string looks like a path-traversal attempt."""
    if any(c in version for c in ("..", "/", "\\")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid version string.",
        )


def _active_version() -> str:
    """Return the currently active version from the ML_MODEL_VERSION env var."""
    return (
        os.getenv("ML_MODEL_VERSION")
        or os.getenv("MODEL_VERSION")
        or "v1.0"
    )


def _update_env_version(new_version: str) -> None:
    """
    Write ML_MODEL_VERSION=<new_version> into the .env file.

    If the key already exists, it is replaced in-place.
    If it doesn't exist, it is appended.
    Raises OSError on any file I/O failure.
    """
    if not _ENV_FILE.exists():
        raise OSError(f".env file not found at {_ENV_FILE}")

    content = _ENV_FILE.read_text(encoding="utf-8")

    # Replace existing key (handles optional surrounding whitespace / comments)
    pattern = re.compile(r"^(ML_MODEL_VERSION\s*=\s*).*$", re.MULTILINE)
    replacement = f"ML_MODEL_VERSION={new_version}"

    if pattern.search(content):
        new_content = pattern.sub(replacement, content)
    else:
        # Key absent — append it
        new_content = content.rstrip("\n") + f"\nML_MODEL_VERSION={new_version}\n"

    _ENV_FILE.write_text(new_content, encoding="utf-8")


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/models/active",
    summary="Get the currently active model version",
    description=(
        "Returns the version currently loaded by the server (read from the "
        "``ML_MODEL_VERSION`` environment variable) together with its full "
        "``metadata.json`` and artifact file list."
    ),
    tags=["Model Versioning"],
)
def get_active_model():
    """Return metadata for the currently active model version."""
    active = _active_version()
    version_dir = _ML_MODELS_ROOT / active

    if not version_dir.is_dir():
        # Version directory is missing — return the version name but flag the issue
        return {
            "active_version":  active,
            "metadata":        None,
            "artifacts":       [],
            "schema_complete": False,
            "warning":         f"Version directory '{active}' does not exist on disk.",
        }

    meta = _read_metadata(version_dir)
    artifacts = sorted(f.name for f in version_dir.iterdir() if f.is_file())

    return {
        "active_version":  active,
        "metadata":        meta,
        "artifacts":       artifacts,
        "schema_complete": all(f in (meta or {}) for f in _REQUIRED_METADATA_FIELDS),
    }


@router.get(
    "/models/versions",
    summary="List all trained model versions",
    description=(
        "Returns a summary of every versioned model directory found under "
        "``models/ml_models/``. Each entry includes the version name and "
        "key metrics from ``metadata.json`` (or a ``no_metadata`` flag if "
        "the file is absent or malformed)."
    ),
    tags=["Model Versioning"],
)
def list_model_versions():
    """List all available model versions with summary metadata."""
    active = _active_version()
    versions = []

    for vdir in _version_dirs():
        meta = _read_metadata(vdir)
        if meta:
            versions.append({
                "version":          vdir.name,
                "is_active":        vdir.name == active,
                "model_name":       meta.get("model_name", "unknown"),
                "training_date":    meta.get("training_date"),
                "accuracy":         meta.get("accuracy"),
                "f1_score":         meta.get("f1_score"),
                "training_samples": meta.get("training_samples"),
                "test_samples":     meta.get("test_samples"),
                "git_commit":       meta.get("git_commit"),
                "schema_complete":  all(
                    f in meta for f in _REQUIRED_METADATA_FIELDS
                ),
            })
        else:
            versions.append({
                "version":     vdir.name,
                "is_active":   vdir.name == active,
                "no_metadata": True,
            })

    return {"active_version": active, "versions": versions, "count": len(versions)}


@router.get(
    "/models/metrics/{version}",
    summary="Get numeric metrics for a specific model version",
    description=(
        "Returns only the numeric training and evaluation metrics from "
        "``metadata.json`` for the requested version. For the full metadata "
        "and artifact list, use ``GET /api/v1/models/versions/{version}``."
    ),
    tags=["Model Versioning"],
)
def get_model_metrics(version: str):
    """Return training and evaluation metrics for a specific model version."""
    _sanitize_version(version)

    version_dir = _ML_MODELS_ROOT / version
    if not version_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version}' not found.",
        )

    meta = _read_metadata(version_dir)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"metadata.json not found or malformed for version '{version}'.",
        )

    # Extract top-level numeric metrics
    metrics: dict[str, Any] = {field: meta.get(field) for field in _METRIC_FIELDS}

    # Surface any nested metrics from the "extra" block (e.g. silhouette_score)
    extra_metrics: dict[str, Any] = {}
    if isinstance(meta.get("extra"), dict):
        extra_metrics = meta["extra"].get("metrics", {})

    return {
        "version":        version,
        "is_active":      version == _active_version(),
        "model_name":     meta.get("model_name", "unknown"),
        "training_date":  meta.get("training_date"),
        "git_commit":     meta.get("git_commit"),
        **metrics,
        "extra_metrics":  extra_metrics,
    }


@router.post(
    "/models/activate/{version}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Activate a model version (admin only)",
    description=(
        "Promotes the specified version to active by updating ``ML_MODEL_VERSION`` "
        "in the server's ``.env`` file. "
        "The server will auto-reload if running with ``uvicorn --reload``. "
        "**Requires the ``X-Admin-Key`` header.**"
    ),
    tags=["Model Versioning"],
)
async def activate_model_version(
    version: str,
    _: None = Depends(require_admin_key),
):
    """
    Set a new active model version.

    Validates that the version directory and its metadata.json exist before
    writing to .env. Returns 202 Accepted with a reload_required flag.
    """
    _sanitize_version(version)

    version_dir = _ML_MODELS_ROOT / version
    if not version_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version}' not found. Available: {[d.name for d in _version_dirs()]}",
        )

    meta = _read_metadata(version_dir)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Version '{version}' exists but has no valid metadata.json. "
                "Refusing to activate an unverified model artifact."
            ),
        )

    previous_version = _active_version()

    if previous_version == version:
        return {
            "activated_version":  version,
            "previous_version":   previous_version,
            "reload_required":    False,
            "message":            f"Version '{version}' is already active. No change made.",
        }

    try:
        _update_env_version(version)
        # Reload the env var in the current process so subsequent calls to
        # _active_version() reflect the change without a restart.
        os.environ["ML_MODEL_VERSION"] = version
    except OSError as exc:
        logger.error("activate_model_version: failed to update .env: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update .env file: {exc}",
        )

    logger.info(
        "Model version activated: %s → %s (previous: %s)",
        previous_version, version, previous_version,
    )

    return {
        "activated_version": version,
        "previous_version":  previous_version,
        "reload_required":   True,
        "message": (
            f"Version '{version}' is now set as active in .env. "
            "The server will auto-reload if running with --reload. "
            "New analysis jobs will use this version after reload."
        ),
    }


# ── Legacy detail endpoint (kept for backward compatibility) ──────────────────

@router.get(
    "/models/versions/{version}",
    summary="Get full metadata for a specific model version",
    description=(
        "Returns the complete ``metadata.json`` and an inventory of all "
        "artifact files for the requested version. "
        "Returns 404 if the version directory or metadata file does not exist."
    ),
    tags=["Model Versioning"],
)
def get_model_version(version: str):
    """Return full metadata.json + artifact inventory for a specific version."""
    _sanitize_version(version)

    version_dir = _ML_MODELS_ROOT / version
    if not version_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version '{version}' not found.",
        )

    meta = _read_metadata(version_dir)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"metadata.json not found or malformed for version '{version}'.",
        )

    artifacts = sorted(f.name for f in version_dir.iterdir() if f.is_file())

    return {
        "version":         version,
        "is_active":       version == _active_version(),
        "metadata":        meta,
        "artifacts":       artifacts,
        "schema_complete": all(f in meta for f in _REQUIRED_METADATA_FIELDS),
    }
