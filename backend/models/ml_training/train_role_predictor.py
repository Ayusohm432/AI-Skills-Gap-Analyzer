import os
import sys
import json
import logging
from pathlib import Path
import numpy as np
import pandas as pd

# Adjust module path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import MultiLabelBinarizer, LabelEncoder
from sklearn.metrics import f1_score, classification_report, roc_auc_score, brier_score_loss

# ── Versioning helper (standardized metadata.json) ───────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from versioning import get_version_dir, save_version_artifacts  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = backend_dir / "models" / "data"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"


# ── CV visualisation helpers ──────────────────────────────────────────────────

def plot_cv_heatmap(cv_results: dict, best_params: dict, output_path: Path) -> None:
    """
    Save a heatmap of mean CV F1 scores (n_estimators × max_depth),
    averaged over min_samples_split and max_features.
    """
    import matplotlib                     # noqa: PLC0415
    matplotlib.use("Agg")                 # headless-safe
    import matplotlib.pyplot as plt       # noqa: PLC0415

    # Build a DataFrame from cv_results
    df = pd.DataFrame(cv_results)

    # Extract individual param columns
    df["n_estimators"]     = df["params"].apply(lambda p: p["n_estimators"])
    df["max_depth"]        = df["params"].apply(lambda p: str(p["max_depth"]))
    df["min_samples_split"]= df["params"].apply(lambda p: p["min_samples_split"])
    df["max_features"]     = df["params"].apply(lambda p: p["max_features"])

    # Pivot: average F1 over min_samples_split × max_features for each
    # (n_estimators, max_depth) cell
    pivot = df.pivot_table(
        values="mean_test_score",
        index="max_depth",
        columns="n_estimators",
        aggfunc="mean",
    )

    # Sort rows so "None" (unlimited) is last
    depth_order = [str(d) for d in [10, 15, 20, None]]
    pivot = pivot.reindex([d for d in depth_order if d in pivot.index])

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(pivot.values, cmap="YlGnBu", aspect="auto")

    # Axis labels
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=11)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=11)
    ax.set_xlabel("n_estimators", fontsize=13)
    ax.set_ylabel("max_depth", fontsize=13)
    ax.set_title("RF 5-Fold CV  --  Mean F1 (weighted)", fontsize=14, fontweight="bold")

    # Annotate cells with scores
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            # Highlight the best-param cell
            best_depth = str(best_params["max_depth"])
            best_est   = best_params["n_estimators"]
            is_best = (pivot.index[i] == best_depth and pivot.columns[j] == best_est)
            color = "#E84545" if is_best else "black"
            weight = "bold" if is_best else "normal"
            ax.text(j, i, f"{val:.4f}", ha="center", va="center",
                    fontsize=11, color=color, fontweight=weight)

    fig.colorbar(im, ax=ax, label="Mean CV F1")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    logger.info(f"CV heatmap saved -> {output_path}")


def save_cv_results(cv_results: dict, output_path: Path) -> None:
    """
    Save the full GridSearchCV cv_results_ table as a JSON file.
    """
    records = []
    for i in range(len(cv_results["params"])):
        records.append({
            "rank":            int(cv_results["rank_test_score"][i]),
            "mean_test_score":  round(float(cv_results["mean_test_score"][i]), 6),
            "std_test_score":   round(float(cv_results["std_test_score"][i]), 6),
            "mean_fit_time":    round(float(cv_results["mean_fit_time"][i]), 3),
            "params":           {k: (v if v is not None else "None")
                                 for k, v in cv_results["params"][i].items()},
        })
    records.sort(key=lambda r: r["rank"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=4)
    logger.info(f"Full CV results ({len(records)} combos) saved -> {output_path}")


def train():
    print("Starting train()...", flush=True)

    # ── Resolve versioned output directory ───────────────────────────────────
    MODELS_DIR = get_version_dir()   # reads ML_MODEL_VERSION env var → default v1.0
    print(f"Output directory: {MODELS_DIR}", flush=True)

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

    # ── Issue #24: expanded hyperparameter grid (72 combos × 5 folds) ─────────
    param_grid = {
        'n_estimators':     [100, 200, 300],
        'max_depth':        [10, 15, 20, None],
        'min_samples_split': [2, 5, 10],
        'max_features':     ['sqrt', 'log2'],
    }
    total_combos = 1
    for v in param_grid.values():
        total_combos *= len(v)
    print(f"Performing Hyperparameter Sweep using GridSearchCV (cv=5, {total_combos} combos)...", flush=True)

    grid_search = GridSearchCV(
        estimator=rf,
        param_grid=param_grid,
        cv=5,
        scoring='f1_weighted',
        n_jobs=1,
        verbose=1,
        return_train_score=False,
    )
    grid_search.fit(X_train, y_train)

    best_rf = grid_search.best_estimator_
    print(f"\nTraining complete. Best parameters found: {grid_search.best_params_}", flush=True)
    print(f"Best 5-fold CV F1 (weighted): {grid_search.best_score_:.6f}", flush=True)

    # ── Save CV outputs ───────────────────────────────────────────────────────
    cv_plot_path    = OUTPUTS_DIR / "rf_cv_scores.png"
    cv_results_path = OUTPUTS_DIR / "rf_cv_results.json"

    plot_cv_heatmap(grid_search.cv_results_, grid_search.best_params_, cv_plot_path)
    save_cv_results(grid_search.cv_results_, cv_results_path)

    # ── Metrics evaluation ────────────────────────────────────────────────────
    logger.info("Evaluating Model Success Metrics...")
    y_pred = best_rf.predict(X_test)
    y_prob = best_rf.predict_proba(X_test)

    # 1. Accuracy
    accuracy = float(best_rf.score(X_test, y_test))
    logger.info(f"Accuracy: {accuracy:.4f}")

    # 2. Overall F1-Score
    f1 = f1_score(y_test, y_pred, average='weighted')
    logger.info(f"Overall F1-Score: {f1:.4f} (Target >0.85)")

    # 3. Per-role Precision/Recall
    report = classification_report(y_test, y_pred, target_names=le.classes_, output_dict=True)
    all_precisions = [metrics['precision'] for label, metrics in report.items() if label not in ('accuracy', 'macro avg', 'weighted avg')]
    all_recalls    = [metrics['recall']    for label, metrics in report.items() if label not in ('accuracy', 'macro avg', 'weighted avg')]

    min_precision = np.min(all_precisions)
    min_recall    = np.min(all_recalls)
    logger.info(f"Min Per-Role Precision: {min_precision:.4f} (Target >0.80)")
    logger.info(f"Min Per-Role Recall: {min_recall:.4f} (Target >0.80)")

    # 4. AUC-ROC per role
    auc_roc = None
    try:
        auc_roc = roc_auc_score(y_test, y_prob, average='macro', multi_class='ovr')
        logger.info(f"AUC-ROC (macro): {auc_roc:.4f} (Target >0.90)")
    except ValueError as e:
        logger.warning(f"Could not calc complete AUC-ROC. Needed more samples per class. {e}")

    # 5. Brier score
    y_test_one_hot = np.eye(len(le.classes_))[y_test]
    brier_scores = [
        brier_score_loss(y_test_one_hot[:, i], y_prob[:, i])
        for i in range(len(le.classes_))
    ]
    avg_brier = float(np.mean(brier_scores))
    logger.info(f"Average Brier Score: {avg_brier:.4f} (Target <0.15)")

    # 6. Feature importances
    logger.info("Analyzing Top 5 Feature Importances...")
    importances = best_rf.feature_importances_
    indices = np.argsort(importances)[::-1]
    for i in range(5):
        logger.info(f"  {i+1}. {mlb.classes_[indices[i]]} ({importances[indices[i]]:.4f})")

    # ── Save model artifact ────────────────────────────────────────────────────
    model_path = MODELS_DIR / "role_predictor.pkl"
    joblib.dump(best_rf, model_path)
    logger.info(f"Model saved to {model_path}")

    # ── Save / update config.json ─────────────────────────────────────────────
    config_path = MODELS_DIR / "config.json"
    config_data = {
        "feature_names": mlb.classes_.tolist(),
        "role_labels":   le.classes_.tolist(),
    }
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

    # ── Write standardized metadata.json ──────────────────────────────────────
    # Serialize best_params with None -> "None" for JSON safety
    serializable_best_params = {
        k: (v if v is not None else "None")
        for k, v in grid_search.best_params_.items()
    }
    extra: dict = {
        "best_params":       serializable_best_params,
        "best_cv_score":     round(float(grid_search.best_score_), 6),
        "param_grid":        {k: [(vi if vi is not None else "None") for vi in v]
                              for k, v in param_grid.items()},
        "total_combinations": total_combos,
        "cv_plot_path":      str(cv_plot_path),
        "cv_results_path":   str(cv_results_path),
        "min_precision":     round(min_precision, 6),
        "min_recall":        round(min_recall, 6),
        "avg_brier_score":   round(avg_brier, 6),
    }
    if auc_roc is not None:
        extra["auc_roc"] = round(auc_roc, 6)

    save_version_artifacts(
        model_name="RF Role Predictor",
        accuracy=accuracy,
        f1_score=f1,
        training_samples=X_train.shape[0],
        test_samples=X_test.shape[0],
        extra_metadata=extra,
    )


if __name__ == "__main__":
    train()

