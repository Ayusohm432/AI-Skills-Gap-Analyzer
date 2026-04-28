"""
routes/monitoring.py
====================
Admin-only endpoints for monitoring ML model health and performance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from security import require_admin_key
from services.monitoring_service import run_performance_audit

router = APIRouter()

@router.get(
    "/admin/ml/performance",
    summary="Get ML Model Health Report (Admin Only)",
    description=(
        "Returns an audit of ML performance metrics including average confidence scores, "
        "fallback ratios, and active alerts for model drift. "
        "Requires the `X-Admin-Key` header."
    ),
    tags=["Model Versioning"],
)
async def get_performance_report(
    days: int = Query(7, ge=1, le=90),
    _: None = Depends(require_admin_key)
):
    """GET /api/v1/admin/ml/performance"""
    return await run_performance_audit(days=days)
