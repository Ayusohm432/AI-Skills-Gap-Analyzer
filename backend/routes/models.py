"""
routes/models.py
================
Read-only API for browsing trained model version metadata.

Endpoints
---------
GET /api/v1/models/versions
    List all available version directories with a summary of their metadata.

GET /api/v1/models/versions/{version}
    Return the full metadata.json + artifact inventory for a specific version.

No authentication is required — metadata.json contains only training metrics
(no PII, no secrets).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

router = APIRouter()

# Resolves to: <repo>/backend/models/ml_models/
_ML_MODELS_ROOT = (
    Path(__file__).resolve().parent.parent / "models" / "ml_models"
)

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

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
    versions = []

    for vdir in _version_dirs():
        meta = _read_metadata(vdir)
        if meta:
            versions.append({
                "version":          vdir.name,
                "model_name":       meta.get("model_name", "unknown"),
                "training_date":    meta.get("training_date"),
                "accuracy":         meta.get("accuracy"),
                "f1_score":         meta.get("f1_score"),
                "training_samples": meta.get("training_samples"),
                "test_samples":     meta.get("test_samples"),
                "git_commit":       meta.get("git_commit"),
                # Flag whether the metadata meets the required schema
                "schema_complete":  all(
                    f in meta for f in _REQUIRED_METADATA_FIELDS
                ),
            })
        else:
            versions.append({
                "version":     vdir.name,
                "no_metadata": True,
            })

    return {"versions": versions, "count": len(versions)}


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

    # Artifact inventory — list all files in the versioned directory
    artifacts = sorted(f.name for f in version_dir.iterdir() if f.is_file())

    return {
        "version":         version,
        "metadata":        meta,
        "artifacts":       artifacts,
        "schema_complete": all(f in meta for f in _REQUIRED_METADATA_FIELDS),
    }
