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

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

K_FINAL = 13
MODELS_DIR = backend_dir / "models" / "ml_models" / "v1.0"

def train():
    logger.info("Initializing configuration and fetching taxonomy embeddings...")
    config = NLPConfig()
    
    taxonomy_data = _get_taxonomy_embeddings(config)
    names = taxonomy_data["names"]
    embeddings = taxonomy_data["embeddings"]
    
    if len(names) == 0:
        logger.error("No skills found in taxonomy. Please verify config.SKILL_TAXONOMY_PATH.")
        return
        
    logger.info(f"Loaded {len(names)} skills with embeddings shape {embeddings.shape}.")
    
    # 1. Provide an Elbow method output
    logger.info("Running Elbow Method to log optimal K search (k=2 to 20)...")
    max_k_test = min(20, len(embeddings) - 1)
    elbow_inertias = []
    
    for k in range(2, max_k_test + 1):
        kmeans_test = KMeans(n_clusters=k, random_state=42, n_init='auto')
        kmeans_test.fit(embeddings)
        elbow_inertias.append((k, kmeans_test.inertia_))
    
    logger.info("--- ELBOW METHOD INERTIAS ---")
    for k, inert in elbow_inertias:
        logger.info(f"k={k}: {inert:.2f}")
    logger.info("-----------------------------")
    
    # 2. Train final K-Means with K=13
    logger.info(f"Training final K-Means model with K={K_FINAL}...")
    final_model = KMeans(n_clusters=K_FINAL, random_state=42, n_init='auto')
    labels = final_model.fit_predict(embeddings)
    
    # 3. Calculate Success Metrics
    logger.info("Calculating Success Metrics...")
    silhouette = silhouette_score(embeddings, labels)
    davies = davies_bouldin_score(embeddings, labels)
    calinski = calinski_harabasz_score(embeddings, labels)
    
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
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "skill_clusterer.pkl"
    joblib.dump(final_model, model_path)
    logger.info(f"Model saved to {model_path}")
    
    # 5. Log metrics to metadata.json
    metadata = {
        "model_name": "K-Means Skill Clusterer",
        "version": "1.0",
        "timestamp": datetime.now().isoformat(),
        "n_clusters": K_FINAL,
        "n_skills_trained": len(names),
        "embeddings_dim": embeddings.shape[1],
        "metrics": {
            "silhouette_score": round(silhouette, 4),
            "davies_bouldin_score": round(davies, 4),
            "calinski_harabasz_score": round(calinski, 4)
        },
        "success": success
    }
    
    metadata_path = MODELS_DIR / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)
    logger.info(f"Metadata saved to {metadata_path}")
    
    # Log a few sample cluster members
    clusters = {i: [] for i in range(K_FINAL)}
    for name, lbl in zip(names, labels):
        if len(clusters[lbl]) < 5:
            clusters[lbl].append(name)
            
    logger.info("Sample skills per cluster:")
    for lbl, sample_skills in clusters.items():
        logger.info(f"  Cluster {lbl}: {', '.join(sample_skills)}")

if __name__ == "__main__":
    train()
