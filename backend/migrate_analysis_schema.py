"""
migrate_analysis_schema.py
==========================
One-shot migration script to bring existing MongoDB documents into the updated
analysis schema.  Safe to re-run; all operations use $set / $rename which are
idempotent.

Operations
----------
1.  analyses collection
    a. Rename ``target_role`` → ``predicted_role`` on documents that still use
       the old field name.
    b. Set default values for new ML-enrichment fields that may be absent in
       older documents:
         - role_confidence      (float)  → 0.0
         - role_alternatives    (array)  → []
         - skill_categories     (object) → {}
         - missing_skills_ranked (array) → []
         - model_version        (string) → "pre-migration"

2.  analysis_jobs collection  (result sub-document)
    a. For completed jobs, rename ``result.target_role`` → ``result.predicted_role``.
    b. Backfill missing ML-enrichment keys inside the embedded ``result`` object.

Usage
-----
    # From the backend/ directory, with venv activated:
    python migrate_analysis_schema.py [--dry-run]

Environment
-----------
Reads MONGO_URL from the .env file (falls back to mongodb://localhost:27017).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("migrate")

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME   = "ai_skills_gap"

# Default values injected for missing ML-enrichment fields
_ML_DEFAULTS = {
    "role_confidence":       0.0,
    "role_alternatives":     [],
    "skill_categories":      {},
    "missing_skills_ranked": [],
    "model_version":         "pre-migration",
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _set_if_missing(defaults: dict) -> dict:
    """Build a $set payload that only fills in keys not already present."""
    return {
        f"$set": {
            k: v
            for k, v in defaults.items()
        }
    }


async def migrate_analyses(collection, *, dry_run: bool) -> None:
    """
    Migrate the ``analyses`` collection.

    Steps
    -----
    1. Rename ``target_role`` → ``predicted_role`` (field rename via $rename).
    2. Backfill missing ML-enrichment default values only for documents that
       lack them (using ``$exists: false`` filters to avoid overwriting real data).
    """
    logger.info("=== analyses collection ===")

    # ── Step 1: rename target_role → predicted_role ───────────────────
    rename_filter = {
        "target_role": {"$exists": True},
        "predicted_role": {"$exists": False},
    }
    rename_update = {"$rename": {"target_role": "predicted_role"}}

    if dry_run:
        count = await collection.count_documents(rename_filter)
        logger.info("[DRY RUN] Would rename target_role on %d documents.", count)
    else:
        result = await collection.update_many(rename_filter, rename_update)
        logger.info(
            "Renamed target_role → predicted_role on %d document(s).",
            result.modified_count,
        )

    # ── Step 2: backfill missing ML-enrichment fields ─────────────────
    for field, default_value in _ML_DEFAULTS.items():
        backfill_filter = {field: {"$exists": False}}

        if dry_run:
            count = await collection.count_documents(backfill_filter)
            logger.info(
                "[DRY RUN] Would backfill '%s' with default on %d document(s).",
                field, count,
            )
        else:
            result = await collection.update_many(
                backfill_filter,
                {"$set": {field: default_value}},
            )
            logger.info(
                "Backfilled '%s' on %d document(s).",
                field, result.modified_count,
            )


async def migrate_analysis_jobs(collection, *, dry_run: bool) -> None:
    """
    Migrate embedded ``result`` objects inside the ``analysis_jobs`` collection.

    For completed jobs, rename ``result.target_role`` → ``result.predicted_role``
    and backfill missing ML-enrichment keys inside the ``result`` sub-document.
    """
    logger.info("=== analysis_jobs collection ===")

    # Only touch completed jobs that have a result sub-document
    base_filter = {"status": "completed", "result": {"$ne": None}}

    # ── Step 1: rename result.target_role → result.predicted_role ─────
    rename_filter = {
        **base_filter,
        "result.target_role": {"$exists": True},
        "result.predicted_role": {"$exists": False},
    }
    rename_update = {"$rename": {"result.target_role": "result.predicted_role"}}

    if dry_run:
        count = await collection.count_documents(rename_filter)
        logger.info(
            "[DRY RUN] Would rename result.target_role on %d job document(s).",
            count,
        )
    else:
        result = await collection.update_many(rename_filter, rename_update)
        logger.info(
            "Renamed result.target_role → result.predicted_role on %d job(s).",
            result.modified_count,
        )

    # ── Step 2: backfill missing ML-enrichment fields in result ───────
    for field, default_value in _ML_DEFAULTS.items():
        embedded_field = f"result.{field}"
        backfill_filter = {**base_filter, embedded_field: {"$exists": False}}

        if dry_run:
            count = await collection.count_documents(backfill_filter)
            logger.info(
                "[DRY RUN] Would backfill 'result.%s' with default on %d job(s).",
                field, count,
            )
        else:
            result = await collection.update_many(
                backfill_filter,
                {"$set": {embedded_field: default_value}},
            )
            logger.info(
                "Backfilled 'result.%s' on %d job(s).",
                field, result.modified_count,
            )


async def create_indexes(db, *, dry_run: bool) -> None:
    """Ensure the required indexes exist on the analyses collection."""
    logger.info("=== Creating indexes on analyses collection ===")
    if dry_run:
        logger.info(
            "[DRY RUN] Would create indexes: predicted_role, model_version, user_id."
        )
        return

    analyses = db["analyses"]
    await analyses.create_index("predicted_role")
    await analyses.create_index("model_version")
    await analyses.create_index("user_id")
    logger.info("Indexes created (or already exist).")


# ── entrypoint ────────────────────────────────────────────────────────────────

async def main(dry_run: bool) -> None:
    if dry_run:
        logger.info("Running in DRY RUN mode – no writes will be performed.")

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    try:
        # Ping to verify connectivity
        await client.admin.command("ping")
        logger.info("Connected to MongoDB at %s  db=%s", MONGO_URL, DB_NAME)

        await migrate_analyses(db["analyses"], dry_run=dry_run)
        await migrate_analysis_jobs(db["analysis_jobs"], dry_run=dry_run)
        await create_indexes(db, dry_run=dry_run)

        if not dry_run:
            logger.info(
                "Migration completed at %s",
                datetime.now(timezone.utc).isoformat(),
            )
        else:
            logger.info("Dry run complete – rerun without --dry-run to apply changes.")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate analyses collection to new ML schema."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to MongoDB.",
    )
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
