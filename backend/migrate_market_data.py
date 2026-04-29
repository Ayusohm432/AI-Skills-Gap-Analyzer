"""
migrate_market_data.py
======================
One-time migration script: drops old market_demand documents (which used
min_usd/max_usd/median_usd keys) and re-seeds all 7 roles fresh from Adzuna.

Run ONCE from the backend directory:
    python migrate_market_data.py

The uvicorn server does NOT need to be running.
"""

import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_market")


async def main():
    from dotenv import load_dotenv
    load_dotenv()

    from database import market_demand_collection
    from services.market_service import ROLES, SEED_DATA, _fetch_live_snapshot

    # 1. Drop all existing documents
    result = await market_demand_collection.delete_many({})
    logger.info("Dropped %d stale market_demand documents", result.deleted_count)

    # 2. Re-seed each role live from Adzuna (staggered to avoid rate limits)
    for role, query in ROLES.items():
        seed = SEED_DATA[role]
        logger.info("Fetching live Adzuna data for: %s ...", role)
        snap = await _fetch_live_snapshot(role, query, seed)

        await market_demand_collection.insert_one({
            "role":      role,
            "snapshots": [snap],
        })

        logger.info(
            "  ✓ role=%-30s  source=%-8s  demand_score=%d  postings=%d  top_skills=%s",
            role, snap["source"], snap["demand_score"],
            snap.get("total_postings", 0),
            snap["trending_skills"][:5],
        )
        await asyncio.sleep(1.0)   # be polite to Adzuna

    logger.info("Migration complete — %d roles seeded.", len(ROLES))


if __name__ == "__main__":
    asyncio.run(main())
