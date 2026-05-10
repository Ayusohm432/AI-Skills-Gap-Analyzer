import argparse
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Adjust module path to allow importing from backend root
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

import joblib
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score, davies_bouldin_score, calinski_harabasz_score

from nlp.config import NLPConfig
from nlp.semantic import _get_taxonomy_embeddings

# ── Versioning helper (standardized metadata.json) ───────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from versioning import get_version_dir, save_version_artifacts  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

K_FINAL = 13   # hardcoded fallback — overridden by --k or --k-auto

# ── CLI ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Train the K-Means skill clusterer."
    )
    p.add_argument(
        "--k", type=int, default=None,
        help="Override the number of clusters directly (e.g. --k 18)."
    )
    p.add_argument(
        "--k-auto", action="store_true",
        help="Read the recommended K from ml_training/outputs/elbow_result.json "
             "(produced by find_optimal_k.py). Falls back to K_FINAL if file is missing."
    )
    return p.parse_args()


def train():
    args = parse_args()

    # ── Resolve K to use ─────────────────────────────────────────────────────
    k_to_use = K_FINAL
    if args.k is not None:
        k_to_use = args.k
        logger.info("--k flag: using K=%d (explicit override)", k_to_use)
    elif args.k_auto:
        _elbow_path = Path(__file__).resolve().parent / "outputs" / "elbow_result.json"
        if _elbow_path.exists():
            _elbow_data = json.loads(_elbow_path.read_text(encoding="utf-8"))
            k_to_use = int(_elbow_data["optimal_k"])
            logger.info(
                "--k-auto: using K=%d from elbow_result.json (method: %s)",
                k_to_use, _elbow_data.get("detection_method", "unknown"),
            )
        else:
            logger.warning(
                "--k-auto set but outputs/elbow_result.json not found. "
                "Run find_optimal_k.py first. Falling back to K=%d.", K_FINAL
            )
    else:
        logger.info("Using hardcoded K_FINAL = %d (pass --k-auto or --k N to override)", k_to_use)

    logger.info("Initializing configuration and fetching taxonomy embeddings...")
    config = NLPConfig()

    # ── Resolve versioned output directory ───────────────────────────────────
    MODELS_DIR = get_version_dir()   # reads ML_MODEL_VERSION env var -> default v1.0
    logger.info(f"Output directory: {MODELS_DIR}")

    taxonomy_data = _get_taxonomy_embeddings(config)
    names      = taxonomy_data["names"]
    embeddings = taxonomy_data["embeddings"]

    if len(names) == 0:
        logger.error("No skills found in taxonomy. Please verify config.SKILL_TAXONOMY_PATH.")
        return

    logger.info(f"Loaded {len(names)} skills with embeddings shape {embeddings.shape}.")

    # 1. Provide an Elbow method output
    logger.info("Running Elbow Method to log optimal K search (k=2 to 20)...")
    max_k_test    = min(20, len(embeddings) - 1)
    elbow_inertias = []

    for k in range(2, max_k_test + 1):
        kmeans_test = KMeans(n_clusters=k, random_state=42, n_init='auto')
        kmeans_test.fit(embeddings)
        elbow_inertias.append((k, kmeans_test.inertia_))

    logger.info("--- ELBOW METHOD INERTIAS ---")
    for k, inert in elbow_inertias:
        logger.info(f"k={k}: {inert:.2f}")
    logger.info("-----------------------------")

    # 2. Train final K-Means with resolved K
    logger.info(f"Training final K-Means model with K={k_to_use}...")
    final_model = KMeans(n_clusters=k_to_use, random_state=42, n_init='auto')
    labels      = final_model.fit_predict(embeddings)

    # 3. Calculate Success Metrics
    logger.info("Calculating Success Metrics...")
    silhouette = silhouette_score(embeddings, labels)
    davies     = davies_bouldin_score(embeddings, labels)
    calinski   = calinski_harabasz_score(embeddings, labels)

    logger.info(f"Silhouette Score: {silhouette:.4f} (Target: >0.6)")
    logger.info(f"Davies-Bouldin Index: {davies:.4f} (Target: <1.0)")
    logger.info(f"Calinski-Harabasz Index: {calinski:.4f} (Target: >100)")

    success = True
    if silhouette <= 0.6:
        logger.warning(f"Note: Silhouette {silhouette:.4f} is <= 0.6 (Typical for high-dim text embeddings)")
    if davies >= 1.0:
        logger.warning(f"Note: Davies-Bouldin {davies:.4f} is >= 1.0")
    if calinski <= 100:
        logger.warning(f"Note: Calinski-Harabasz {calinski:.4f} is <= 100")

    logger.info("Proceeding to serialize model.")

    # 4. Serialize to disk
    model_path = MODELS_DIR / "skill_clusterer.pkl"
    joblib.dump(final_model, model_path)
    logger.info(f"Model saved to {model_path}")

    # 5. Log sample cluster members
    clusters: dict[int, list[str]] = {i: [] for i in range(k_to_use)}
    for name, lbl in zip(names, labels):
        if len(clusters[lbl]) < 5:
            clusters[lbl].append(name)

    logger.info("Sample skills per cluster:")
    for lbl, sample_skills in clusters.items():
        logger.info(f"  Cluster {lbl}: {', '.join(sample_skills)}")

    # ── Write standardized metadata.json ──────────────────────────────────────
    # Clustering has no accuracy/F1 in the classification sense.
    # We use silhouette as the primary quality metric (mapped to f1_score field).
    # accuracy = 1 - normalised_davies (proxy — lower Davies means better clusters).
    normalised_davies = min(davies / 10.0, 1.0)   # rough normalisation
    proxy_accuracy    = round(1.0 - normalised_davies, 6)

    save_version_artifacts(
        model_name="K-Means Skill Clusterer",
        accuracy=proxy_accuracy,
        f1_score=round(float(silhouette), 6),       # silhouette as primary metric
        training_samples=len(names),
        test_samples=0,                              # unsupervised — no test split
        extra_metadata={
            "n_clusters":              k_to_use,
            "embeddings_dim":          int(embeddings.shape[1]),
            "silhouette_score":        round(float(silhouette), 6),
            "davies_bouldin_score":    round(float(davies), 6),
            "calinski_harabasz_score": round(float(calinski), 6),
            "success":                 success,
        },
    )


if __name__ == "__main__":
    train()

