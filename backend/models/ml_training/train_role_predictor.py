import os
import sys
import json
import logging
from pathlib import Path
import numpy as np

# Adjust module path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import MultiLabelBinarizer, LabelEncoder
from sklearn.metrics import f1_score, classification_report, roc_auc_score, brier_score_loss

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

MODELS_DIR = backend_dir / "models" / "ml_models" / "v1.0"
DATA_DIR = backend_dir / "models" / "data"

def train():
    print("Starting train()...", flush=True)
    dataset_path = DATA_DIR / "skill_gap_pairs.json"
    logger.info(f"Loading data from {dataset_path}")
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    pairs = data.get("pairs", [])
    if not pairs:
        logger.error("No training pairs found.")
        return

    logger.info(f"Loaded {len(pairs)} records.")

    # Parse features and labels
    raw_X = [p.get("current_skills", []) for p in pairs]
    raw_y = [p.get("target_role", "Unknown") for p in pairs]

    # One-hot encode skills
    logger.info("Initializing MultiLabelBinarizer...")
    mlb = MultiLabelBinarizer()
    X = mlb.fit_transform(raw_X)
    
    # Encode target roles
    logger.info("Initializing LabelEncoder...")
    le = LabelEncoder()
    y = le.fit_transform(raw_y)

    logger.info(f"Feature matrix shape: {X.shape}")
    logger.info(f"Number of classes: {len(le.classes_)}")

    # 80/20 train/test split
    print("Splitting dataset (80/20)...", flush=True)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    print(f"Training on {X_train.shape[0]} samples, testing on {X_test.shape[0]} samples.", flush=True)
    
    rf = RandomForestClassifier(random_state=42, class_weight='balanced', n_jobs=1)
    
    param_grid = {
        'n_estimators': [150, 200, 250],
        'max_depth': [10, 15, 20]
    }
    
    print("Performing Hyperparameter Sweep using GridSearchCV (cv=5)...", flush=True)
    grid_search = GridSearchCV(estimator=rf, param_grid=param_grid, cv=5, scoring='f1_weighted', n_jobs=1)
    grid_search.fit(X_train, y_train)

    best_rf = grid_search.best_estimator_
    print(f"Training complete. Best parameters found: {grid_search.best_params_}", flush=True)

    # Metrics evaluation
    logger.info("Evaluating Model Success Metrics...")
    y_pred = best_rf.predict(X_test)
    y_prob = best_rf.predict_proba(X_test)

    # 1. Overall F1-Score
    f1 = f1_score(y_test, y_pred, average='weighted')
    logger.info(f"Overall F1-Score: {f1:.4f} (Target >0.85)")

    # 2. Per-role Precision/Recall
    report = classification_report(y_test, y_pred, target_names=le.classes_, output_dict=True)
    all_precisions = [metrics['precision'] for label, metrics in report.items() if label not in ('accuracy', 'macro avg', 'weighted avg')]
    all_recalls = [metrics['recall'] for label, metrics in report.items() if label not in ('accuracy', 'macro avg', 'weighted avg')]
    
    min_precision = np.min(all_precisions)
    min_recall = np.min(all_recalls)
    logger.info(f"Min Per-Role Precision: {min_precision:.4f} (Target >0.80)")
    logger.info(f"Min Per-Role Recall: {min_recall:.4f} (Target >0.80)")

    # 3. AUC-ROC per role
    try:
        auc_roc = roc_auc_score(y_test, y_prob, average='macro', multi_class='ovr')
        logger.info(f"AUC-ROC (macro): {auc_roc:.4f} (Target >0.90)")
    except ValueError as e:
        logger.warning(f"Could not calc complete AUC-ROC. Needed more samples per class. {e}")

    # 4. Brier score
    y_test_one_hot = np.eye(len(le.classes_))[y_test]
    brier_scores = []
    for i in range(len(le.classes_)):
        bs = brier_score_loss(y_test_one_hot[:, i], y_prob[:, i])
        brier_scores.append(bs)
    avg_brier = np.mean(brier_scores)
    logger.info(f"Average Brier Score: {avg_brier:.4f} (Target <0.15)")

    # Feature importances
    logger.info("Analyzing Top 5 Feature Importances...")
    importances = best_rf.feature_importances_
    indices = np.argsort(importances)[::-1]
    for i in range(5):
        logger.info(f"  {i+1}. {mlb.classes_[indices[i]]} ({importances[indices[i]]:.4f})")

    # Save artifacts
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model_path = MODELS_DIR / "role_predictor.pkl"
    joblib.dump(best_rf, model_path)
    logger.info(f"Model saved to {model_path}")

    config_path = MODELS_DIR / "config.json"
    config_data = {
        "feature_names": mlb.classes_.tolist(),
        "role_labels": le.classes_.tolist()
    }
    # Update existing config.json if there is one
    if config_path.exists():
        with open(config_path, "r") as f:
            try:
                existing_config = json.load(f)
            except json.JSONDecodeError:
                existing_config = {}
        existing_config.update(config_data)
        config_data = existing_config

    with open(config_path, "w") as f:
        json.dump(config_data, f, indent=4)
        
    logger.info(f"Config successfully updated with {len(mlb.classes_)} features at {config_path}")

if __name__ == "__main__":
    train()
