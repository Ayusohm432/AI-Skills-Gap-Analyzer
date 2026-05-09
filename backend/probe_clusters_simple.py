"""
probe_clusters_simple.py
Probes skill_clusterer.pkl without sentence-transformers by checking
the model's internal attributes (centroids shape, etc.) and using
the feature vocabulary from config.json to understand cluster composition.

Run from backend/ directory:
    python probe_clusters_simple.py
"""
import json
import joblib
from pathlib import Path
import numpy as np

PKL_PATH = Path("models/ml_models/v1.0/skill_clusterer.pkl")
CFG_PATH = Path("models/ml_models/v1.0/config.json")

# Load
clusterer = joblib.load(PKL_PATH)
print(f"Type         : {type(clusterer).__name__}")
print(f"n_clusters   : {clusterer.n_clusters}")
print(f"Attrs        : {[a for a in dir(clusterer) if not a.startswith('__')]}")

# Cluster center shape
centers = clusterer.cluster_centers_
print(f"centers shape: {centers.shape}")   # (13, 384) expected

# Load feature names from config
with open(CFG_PATH, "r") as f:
    cfg = json.load(f)

feature_names = cfg.get("feature_names", [])
print(f"feature_names count: {len(feature_names)}")
print(f"first 20 features: {feature_names[:20]}")

# If feature_names count matches centers columns, we can use binary vectors
# (role predictor path — but skill_clusterer was trained on EMBEDDINGS not binary vecs)
print(f"\nnote: centers dim={centers.shape[1]}, features={len(feature_names)}")
if centers.shape[1] == len(feature_names):
    print("Clusterer uses binary feature vectors (same as role predictor vocab)")
    
    # Find top features per cluster (highest centroid value)
    DOMAIN_KEYWORDS = {
        "frontend": {"react","angular","vue","html","css","next.js","typescript",
                     "tailwindcss","svelte","webpack","sass","bootstrap","figma","nuxt"},
        "backend":  {"node.js","fastapi","django","flask","spring boot","express",
                     "rest api","graphql","postgresql","mysql","mongodb","redis",
                     "rabbitmq","kafka","java","go","ruby","spring","asp.net"},
        "devops":   {"docker","kubernetes","aws","azure","gcp","terraform","jenkins",
                     "ci/cd","ansible","github actions","linux","nginx","helm",
                     "prometheus","grafana","bash","shell","vagrant"},
        "data":     {"python","pandas","numpy","machine learning","deep learning",
                     "tensorflow","pytorch","scikit-learn","nlp","data analysis",
                     "statistics","sql","tableau","power bi","spark","airflow",
                     "mlops","feature engineering","keras","xgboost","hadoop"},
    }
    
    feat_lower = [f.lower() for f in feature_names]
    
    # Domain index sets
    domain_indices = {}
    for domain, kws in DOMAIN_KEYWORDS.items():
        domain_indices[domain] = [i for i, f in enumerate(feat_lower) if f in kws]
        print(f"  {domain}: {len(domain_indices[domain])} keyword features found")
    
    print("\n=== Cluster → domain mapping ===")
    mapping = {}
    for cid in range(clusterer.n_clusters):
        row = centers[cid]
        scores = {}
        for domain, idxs in domain_indices.items():
            if idxs:
                scores[domain] = float(np.mean(row[idxs]))
            else:
                scores[domain] = 0.0
        
        # Also show top-10 features by centroid value
        top_idx = np.argsort(row)[::-1][:10]
        top_feats = [feature_names[i] for i in top_idx]
        
        winner = max(scores, key=scores.get)
        mapping[cid] = winner
        print(f"  Cluster {cid:2d}: scores={scores}  winner={winner}")
        print(f"             top features: {top_feats}")
    
    print("\n=== CLUSTER_DOMAIN_MAP (copy into engine.py) ===")
    print("CLUSTER_DOMAIN_MAP: dict[int, str] = {")
    for cid in range(clusterer.n_clusters):
        print(f"    {cid}: \"{mapping[cid]}\",")
    print("}")
else:
    print(f"Clusterer uses {centers.shape[1]}-dim embeddings — need sentence-transformers to probe")
    # Still useful: print n_clusters for the map template
    print("\n=== Default CLUSTER_DOMAIN_MAP template ===")
    print("CLUSTER_DOMAIN_MAP: dict[int, str] = {")
    for cid in range(clusterer.n_clusters):
        print(f"    {cid}: \"data\",  # TODO: label")
    print("}")
