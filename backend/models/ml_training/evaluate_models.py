"""
models/ml_training/evaluate_models.py
======================================
Standalone evaluation script for all 3 trained ML models.

Usage
-----
    python evaluate_models.py --version 1.0

Outputs
-------
  1. Console summary table (stdout)
  2. ml_models/v<version>/evaluation_report.json
  3. ml_models/v<version>/metadata.json  ← patched with "evaluation" key

Exit codes
----------
  0  all models passed / warned
  1  any model failed or artifact missing
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.metrics import (
    silhouette_score,
    davies_bouldin_score,
    calinski_harabasz_score,
    f1_score,
    classification_report,
    roc_auc_score,
    brier_score_loss,
)
from sklearn.model_selection import train_test_split

# ── Path setup ────────────────────────────────────────────────────────────────
_THIS_DIR   = Path(__file__).resolve().parent          # ml_training/
_BACKEND    = _THIS_DIR.parent.parent                  # backend/
_ML_MODELS  = _THIS_DIR.parent / "ml_models"           # backend/models/ml_models/
_DATA_DIR   = _THIS_DIR.parent / "data"               # backend/models/data/

sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_THIS_DIR))

from versioning import _detect_git_commit              # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger("evaluate_models")

# ── Target thresholds ─────────────────────────────────────────────────────────
TARGETS = {
    "kmeans": {
        "silhouette":         (">=", 0.06),
        "davies_bouldin":     ("<=", 5.00),
        "calinski_harabasz":  (">=", 40.0),
    },
    "rf": {
        "f1_weighted":  (">=", 0.85),
        "min_precision":(">=", 0.80),
        "min_recall":   (">=", 0.80),
        "auc_roc":      (">=", 0.90),
        "avg_brier":    ("<=", 0.15),
        "inference_ms": ("<=", 50.0),
    },
    "lstm": {
        "recall_at_10": (">=", 0.75),
        "recall_at_20": (">=", 0.85),
        "mrr":          (">=", 0.80),
        "latency_ms":   ("<=", 100.0),
    },
}


def _check(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    return False


def _targets_met(metrics: dict, model_key: str) -> dict[str, bool]:
    result = {}
    for name, (op, thr) in TARGETS[model_key].items():
        val = metrics.get(name)
        result[name] = _check(val, op, thr) if val is not None else False
    return result


def _status(tm: dict) -> str:
    if all(tm.values()):
        return "pass"
    if any(tm.values()):
        return "warn"
    return "fail"


# ── calculate_metrics (copied from train_missing_skills_lstm.py) ──────────────
def calculate_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                      k_values: list[int] = None) -> dict:
    """Compute Recall@K and MRR for multi-label predictions."""
    if k_values is None:
        k_values = [10, 20]
    recalls = {k: [] for k in k_values}
    mrrs: list[float] = []

    for i in range(len(y_true)):
        true_idx = set(np.where(y_true[i] == 1)[0])
        if not true_idx:
            continue
        pred_sorted = np.argsort(y_pred[i])[::-1]
        for k in k_values:
            top_k = set(pred_sorted[:k])
            recalls[k].append(len(true_idx & top_k) / len(true_idx))
        rank = 0
        for r, idx in enumerate(pred_sorted):
            if idx in true_idx:
                rank = r + 1
                break
        mrrs.append(1.0 / rank if rank > 0 else 0.0)

    return {
        "MRR":       float(np.mean(mrrs)) if mrrs else 0.0,
        "Recall@10": float(np.mean(recalls[10])) if recalls[10] else 0.0,
        "Recall@20": float(np.mean(recalls[20])) if recalls[20] else 0.0,
    }


# ── Artifact loader ───────────────────────────────────────────────────────────
def load_artifacts(version_dir: Path) -> dict[str, Any]:
    """Load all model artifacts; missing ones are set to None."""
    bundle: dict[str, Any] = {}

    def _load(key: str, fn):
        try:
            bundle[key] = fn()
            logger.info("  [OK]  %s", key)
        except FileNotFoundError:
            bundle[key] = None
            logger.warning("  [--]  %s  NOT FOUND", key)
        except Exception as exc:
            bundle[key] = None
            logger.error("  [ERR] %s  %s", key, exc)

    logger.info("Loading artifacts from %s", version_dir)
    _load("skill_clusterer",   lambda: joblib.load(version_dir / "skill_clusterer.pkl"))
    _load("role_predictor",    lambda: joblib.load(version_dir / "role_predictor.pkl"))
    _load("lstm_mlb",          lambda: joblib.load(version_dir / "missing_skills_mlb.pkl"))
    _load("role_encoder",      lambda: joblib.load(version_dir / "role_encoder.pkl"))
    _load("seniority_encoder", lambda: joblib.load(version_dir / "seniority_encoder.pkl"))

    cfg_path = version_dir / "config.json"
    try:
        bundle["role_config"] = json.loads(cfg_path.read_text(encoding="utf-8"))
        logger.info("  [OK]  config.json")
    except Exception as exc:
        bundle["role_config"] = None
        logger.warning("  [--]  config.json  %s", exc)

    keras_path = version_dir / "missing_skills_lstm.keras"
    h5_path    = version_dir / "missing_skills_lstm.h5"
    try:
        os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
        import tensorflow as tf  # noqa: PLC0415
        if keras_path.exists():
            bundle["lstm_model"] = tf.keras.models.load_model(keras_path)
        elif h5_path.exists():
            bundle["lstm_model"] = tf.keras.models.load_model(h5_path)
        else:
            raise FileNotFoundError("No LSTM model file found")
        logger.info("  [OK]  lstm_model")
    except Exception as exc:
        bundle["lstm_model"] = None
        logger.warning("  [--]  lstm_model  %s", exc)

    return bundle


# ── K-Means evaluator ─────────────────────────────────────────────────────────
def evaluate_kmeans(bundle: dict, data_dir: Path) -> dict:
    """Evaluate K-Means skill clusterer."""
    model = bundle.get("skill_clusterer")
    if model is None:
        return {"status": "error", "error": "skill_clusterer.pkl not loaded"}

    logger.info("\n=== K-Means Evaluation ===")
    logger.info("Embedding taxonomy skills (this may take ~30s)...")

    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        skill_cats_path = data_dir / "skill_categories.json"
        with open(skill_cats_path, encoding="utf-8") as fh:
            raw = json.load(fh)

        # Parse skills from skill_categories.json
        # Format: {"_meta": {...}, "skills": [{"name": "...", ...}, ...]}
        skills_list: list[str] = []
        if isinstance(raw, dict) and "skills" in raw:
            for entry in raw["skills"]:
                if isinstance(entry, dict) and "name" in entry:
                    skills_list.append(entry["name"])
                elif isinstance(entry, str):
                    skills_list.append(entry)
        elif isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict) and "name" in entry:
                    skills_list.append(entry["name"])
                elif isinstance(entry, str):
                    skills_list.append(entry)
        skills_list = list(dict.fromkeys(skills_list))  # deduplicate, preserve order

        encoder = SentenceTransformer("all-MiniLM-L6-v2")
        embeddings = encoder.encode(
            skills_list, batch_size=256,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )

        labels = model.predict(embeddings)
        n_clusters = len(set(labels))

        sil   = float(silhouette_score(embeddings, labels))
        db    = float(davies_bouldin_score(embeddings, labels))
        ch    = float(calinski_harabasz_score(embeddings, labels))

        logger.info("Silhouette Score:         %.4f  (target >= 0.06)", sil)
        logger.info("Davies-Bouldin Index:     %.4f  (target <= 5.0)", db)
        logger.info("Calinski-Harabasz Index:  %.4f  (target >= 40)", ch)

        # Cluster samples — human validation (print only)
        clusters: dict[int, list[str]] = {}
        for name, lbl in zip(skills_list, labels):
            clusters.setdefault(int(lbl), [])
            if len(clusters[int(lbl)]) < 5:
                clusters[int(lbl)].append(name)

        logger.info("\n-- Human Validation: Top-5 skills per cluster --")
        for lbl in sorted(clusters):
            logger.info("  Cluster %2d: %s", lbl, ", ".join(clusters[lbl]))
        logger.info("------------------------------------------------")

        metrics = {
            "silhouette":        round(sil, 6),
            "davies_bouldin":    round(db, 6),
            "calinski_harabasz": round(ch, 6),
            "n_clusters":        n_clusters,
            "n_skills":          len(skills_list),
        }
        tm = _targets_met(metrics, "kmeans")
        return {
            "status":        _status(tm),
            "metrics":       metrics,
            "cluster_samples": {str(k): v for k, v in clusters.items()},
            "targets_met":   tm,
        }

    except Exception as exc:
        logger.error("K-Means evaluation failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


# ── Random Forest evaluator ───────────────────────────────────────────────────
def evaluate_rf(bundle: dict, data_dir: Path) -> dict:
    """Evaluate Random Forest role predictor."""
    model       = bundle.get("role_predictor")
    role_config = bundle.get("role_config")

    if model is None:
        return {"status": "error", "error": "role_predictor.pkl not loaded"}
    if role_config is None:
        return {"status": "error", "error": "config.json not loaded"}

    logger.info("\n=== Random Forest Evaluation ===")

    try:
        from sklearn.preprocessing import MultiLabelBinarizer, LabelEncoder  # noqa: PLC0415

        dataset_path = data_dir / "skill_gap_pairs.json"
        with open(dataset_path, encoding="utf-8") as fh:
            data = json.load(fh)
        pairs = data.get("pairs", [])
        logger.info("Loaded %d records from skill_gap_pairs.json", len(pairs))

        feature_names = role_config["feature_names"]
        role_labels   = role_config["role_labels"]

        raw_X = [p.get("current_skills", []) for p in pairs]
        raw_y = [p.get("target_role", "Unknown") for p in pairs]

        # Re-use training encoding (same random_state=42, test_size=0.20)
        mlb = MultiLabelBinarizer(classes=feature_names)
        X   = mlb.fit_transform(raw_X)

        le  = LabelEncoder()
        le.classes_ = np.array(role_labels)
        y   = le.transform(raw_y)

        _, X_test, _, y_test = train_test_split(
            X, y, test_size=0.20, random_state=42, stratify=y
        )
        logger.info("Test set: %d samples", len(y_test))

        t0       = time.perf_counter()
        y_pred   = model.predict(X_test)
        y_prob   = model.predict_proba(X_test)
        inf_ms   = round((time.perf_counter() - t0) * 1000 / len(y_test), 3)

        acc     = float(model.score(X_test, y_test))
        f1_w    = float(f1_score(y_test, y_pred, average="weighted"))
        report  = classification_report(
            y_test, y_pred, target_names=role_labels, output_dict=True
        )

        skip = ("accuracy", "macro avg", "weighted avg")
        per_role = {
            role: {
                "precision": round(v["precision"], 6),
                "recall":    round(v["recall"], 6),
                "f1":        round(v["f1-score"], 6),
                "support":   int(v["support"]),
            }
            for role, v in report.items() if role not in skip
        }

        precisions = [v["precision"] for v in per_role.values()]
        recalls    = [v["recall"]    for v in per_role.values()]
        min_prec   = float(np.min(precisions))
        min_rec    = float(np.min(recalls))

        auc_roc = None
        try:
            auc_roc = float(roc_auc_score(y_test, y_prob, average="macro", multi_class="ovr"))
        except ValueError as exc:
            logger.warning("AUC-ROC skipped: %s", exc)

        y_test_ohe  = np.eye(len(role_labels))[y_test]
        brier_scores = [brier_score_loss(y_test_ohe[:, i], y_prob[:, i])
                        for i in range(len(role_labels))]
        avg_brier = float(np.mean(brier_scores))

        logger.info("Accuracy:         %.4f", acc)
        logger.info("F1 (weighted):    %.4f  (target >= 0.85)", f1_w)
        logger.info("Min Precision:    %.4f  (target >= 0.80)", min_prec)
        logger.info("Min Recall:       %.4f  (target >= 0.80)", min_rec)
        if auc_roc is not None:
            logger.info("AUC-ROC (macro):  %.4f  (target >= 0.90)", auc_roc)
        logger.info("Avg Brier Score:  %.4f  (target <= 0.15)", avg_brier)
        logger.info("Inference latency:%.2f ms/sample (target <= 50)", inf_ms)

        metrics: dict[str, Any] = {
            "accuracy":     round(acc, 6),
            "f1_weighted":  round(f1_w, 6),
            "min_precision":round(min_prec, 6),
            "min_recall":   round(min_rec, 6),
            "avg_brier":    round(avg_brier, 6),
            "inference_ms": inf_ms,
        }
        if auc_roc is not None:
            metrics["auc_roc"] = round(auc_roc, 6)

        tm = _targets_met(metrics, "rf")
        return {
            "status":      _status(tm),
            "metrics":     metrics,
            "per_role":    per_role,
            "targets_met": tm,
        }

    except Exception as exc:
        logger.error("RF evaluation failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


# ── LSTM evaluator ────────────────────────────────────────────────────────────
def evaluate_lstm(bundle: dict, data_dir: Path) -> dict:
    """Evaluate LSTM missing-skills predictor."""
    lstm_model        = bundle.get("lstm_model")
    mlb               = bundle.get("lstm_mlb")
    role_encoder      = bundle.get("role_encoder")
    seniority_encoder = bundle.get("seniority_encoder")

    if any(x is None for x in [lstm_model, mlb, role_encoder, seniority_encoder]):
        return {"status": "error", "error": "One or more LSTM artifacts not loaded"}

    logger.info("\n=== LSTM Evaluation ===")

    MAX_SKILLS = 20
    EMB_DIM    = 384

    try:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415
        from collections import Counter                         # noqa: PLC0415

        dataset_path = data_dir / "skill_gap_pairs.json"
        with open(dataset_path, encoding="utf-8") as fh:
            data = json.load(fh)
        pairs = data.get("pairs", [])
        logger.info("Loaded %d records", len(pairs))

        VOCAB_SIZE  = len(mlb.classes_)
        top_50_set  = set(mlb.classes_)

        raw_skills, raw_roles, raw_sens, raw_y = [], [], [], []
        for p in pairs:
            raw_skills.append(p.get("current_skills", []))
            raw_roles.append([p.get("target_role", "Unknown")])
            raw_sens.append([p.get("seniority", "Unknown")])
            raw_y.append([s for s in p.get("missing_skills", []) if s in top_50_set])

        X_role  = role_encoder.transform(raw_roles)
        X_sen   = seniority_encoder.transform(raw_sens)
        X_meta  = np.concatenate([X_role, X_sen], axis=1).astype(np.float32)

        logger.info("Embedding %d unique skills...", len({s for seq in raw_skills for s in seq}))
        encoder     = SentenceTransformer("all-MiniLM-L6-v2")
        unique      = list({s for seq in raw_skills for s in seq})
        emb_matrix  = encoder.encode(unique, batch_size=256, show_progress_bar=False,
                                     convert_to_numpy=True, normalize_embeddings=True)
        emb_dict    = dict(zip(unique, emb_matrix))

        X_skills = np.zeros((len(raw_skills), MAX_SKILLS, EMB_DIM), dtype=np.float32)
        for i, seq in enumerate(raw_skills):
            for j, sk in enumerate(seq[:MAX_SKILLS]):
                if sk in emb_dict:
                    X_skills[i, j, :] = emb_dict[sk]

        y = mlb.transform(raw_y).astype(np.float32)

        indices = np.arange(len(y))
        _, idx_te = train_test_split(indices, test_size=0.2, random_state=42)

        X_sk_te = X_skills[idx_te]
        X_me_te = X_meta[idx_te]
        y_te    = y[idx_te]
        logger.info("Test set: %d samples", len(idx_te))

        t0      = time.perf_counter()
        y_pred  = lstm_model.predict([X_sk_te, X_me_te], batch_size=32, verbose=0)
        lat_ms  = round((time.perf_counter() - t0) * 1000 / len(idx_te), 3)

        m = calculate_metrics(y_te, y_pred, k_values=[10, 20])
        r10 = round(m["Recall@10"], 6)
        r20 = round(m["Recall@20"], 6)
        mrr = round(m["MRR"],       6)

        logger.info("Recall@10:        %.4f  (target >= 0.75)", r10)
        logger.info("Recall@20:        %.4f  (target >= 0.85)", r20)
        logger.info("MRR:              %.4f  (target >= 0.80)", mrr)
        logger.info("Latency:          %.2f ms/sample (target <= 100)", lat_ms)

        metrics = {
            "recall_at_10": r10,
            "recall_at_20": r20,
            "mrr":          mrr,
            "latency_ms":   lat_ms,
        }
        tm = _targets_met(metrics, "lstm")
        return {
            "status":      _status(tm),
            "metrics":     metrics,
            "targets_met": tm,
        }

    except Exception as exc:
        logger.error("LSTM evaluation failed: %s", exc, exc_info=True)
        return {"status": "error", "error": str(exc)}


# ── Console summary ───────────────────────────────────────────────────────────
def print_console_summary(results: dict, version: str) -> None:
    # ASCII-safe icons (avoids cp1252 UnicodeEncodeError on Windows)
    ICONS = {"pass": "[PASS]", "warn": "[WARN]", "fail": "[FAIL]", "error": "[ERR ]"}
    line  = "-" * 60

    print(f"\n{'=' * 60}")
    print(f"  MODEL EVALUATION REPORT  --  version {version}")
    print(f"{'=' * 60}")

    for model_key, label in [
        ("skill_clusterer",    "K-Means Skill Clusterer"),
        ("role_predictor",     "Random Forest Role Predictor"),
        ("missing_skills_lstm","LSTM Missing-Skills Predictor"),
    ]:
        r = results.get("models", {}).get(model_key, {})
        status = r.get("status", "error")
        icon   = ICONS.get(status, "?")
        print(f"\n{icon}  {label}  [{status.upper()}]")
        print(line)
        if "error" in r:
            print(f"   Error: {r['error']}")
            continue
        for k, v in r.get("metrics", {}).items():
            tm  = r.get("targets_met", {})
            chk = "+" if tm.get(k, True) else "x"
            print(f"   [{chk}]  {k:<25} {v}")

    overall = results.get("overall_status", "error")
    print(f"\n{'=' * 60}")
    print(f"  OVERALL: {ICONS.get(overall, '?')}  {overall.upper()}")
    print(f"  {results.get('summary', '')}")
    print(f"{'=' * 60}\n")


# ── Report writer ─────────────────────────────────────────────────────────────
def write_report(results: dict, version_dir: Path, report_dir: Path | None) -> None:
    out_dir = report_dir or version_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=4)
    logger.info("Evaluation report written → %s", report_path)

    # Patch metadata.json (preserve all existing fields)
    meta_path = version_dir / "metadata.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            models_r = results.get("models", {})

            km  = models_r.get("skill_clusterer", {}).get("metrics", {})
            rf  = models_r.get("role_predictor",  {}).get("metrics", {})
            lst = models_r.get("missing_skills_lstm", {}).get("metrics", {})

            meta["evaluation"] = {
                "evaluated_at":              results.get("evaluated_at"),
                "overall_status":            results.get("overall_status"),
                "skill_clusterer_silhouette":km.get("silhouette"),
                "role_predictor_f1_weighted":rf.get("f1_weighted"),
                "lstm_recall_at_10":         lst.get("recall_at_10"),
                "lstm_recall_at_20":         lst.get("recall_at_20"),
                "lstm_mrr":                  lst.get("mrr"),
            }
            with open(meta_path, "w", encoding="utf-8") as fh:
                json.dump(meta, fh, indent=4)
            logger.info("metadata.json patched with 'evaluation' key → %s", meta_path)
        except Exception as exc:
            logger.warning("Could not patch metadata.json: %s", exc)
    else:
        logger.warning("metadata.json not found at %s — skipping patch", meta_path)


# ── CLI & main ────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Evaluate all 3 ML models and write an evaluation report."
    )
    p.add_argument("--version",    default="1.0",
                   help="Model version to evaluate (default: 1.0)")
    p.add_argument("--data-dir",   type=Path, default=None,
                   help="Override path to models/data/ directory")
    p.add_argument("--report-dir", type=Path, default=None,
                   help="Write evaluation_report.json to this directory instead of version dir")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    version     = f"v{args.version}" if not args.version.startswith("v") else args.version
    version_dir = _ML_MODELS / version
    data_dir    = args.data_dir or _DATA_DIR

    if not version_dir.exists():
        logger.error("Version directory not found: %s", version_dir)
        return 1

    logger.info("Evaluating models in %s", version_dir)

    bundle = load_artifacts(version_dir)

    km_result   = evaluate_kmeans(bundle, data_dir)
    rf_result   = evaluate_rf(bundle, data_dir)
    lstm_result = evaluate_lstm(bundle, data_dir)

    model_results = {
        "skill_clusterer":    km_result,
        "role_predictor":     rf_result,
        "missing_skills_lstm": lstm_result,
    }

    statuses    = [r.get("status", "error") for r in model_results.values()]
    if all(s == "pass" for s in statuses):
        overall = "pass"
    elif any(s in ("error", "fail") for s in statuses):
        overall = "fail"
    else:
        overall = "warn"

    n_pass = sum(1 for s in statuses if s == "pass")
    n_warn = sum(1 for s in statuses if s == "warn")
    n_fail = sum(1 for s in statuses if s in ("fail", "error"))

    summary = f"{n_pass}/3 models passed, {n_warn} warned, {n_fail} failed."

    full_report: dict[str, Any] = {
        "version":        version,
        "evaluated_at":   datetime.now(timezone.utc).isoformat(),
        "git_commit":     _detect_git_commit(),
        "models":         model_results,
        "overall_status": overall,
        "summary":        summary,
    }

    print_console_summary(
        {"models": model_results, "overall_status": overall, "summary": summary},
        version,
    )
    write_report(full_report, version_dir, args.report_dir)

    return 0 if overall in ("pass", "warn") else 1


if __name__ == "__main__":
    sys.exit(main())
