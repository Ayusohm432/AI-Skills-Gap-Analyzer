import os
import sys
import json
import logging
import time
from pathlib import Path
import numpy as np
import joblib

# Adjust module path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))

from collections import Counter
from sentence_transformers import SentenceTransformer
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer, StandardScaler, OneHotEncoder

# Deep Learning Imports
import tensorflow as tf
from tensorflow.keras.models import Model
from tensorflow.keras.layers import (
    LSTM, Dense, Dropout, Masking, Input, Concatenate
)
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping

# ── Versioning helper (standardized metadata.json) ───────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))
from versioning import get_version_dir, save_version_artifacts  # noqa: E402

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

DATA_DIR = backend_dir / "models" / "data"


MAX_SKILLS = 20
EMB_DIM = 384
VOCAB_SIZE = 50


def calculate_metrics(y_true, y_pred, k_values=[10, 20]):
    """Compute Recall@K and MRR for multi-label predictions."""
    recalls = {k: [] for k in k_values}
    mrrs = []

    for i in range(len(y_true)):
        true_idx = set(np.where(y_true[i] == 1)[0])
        if not true_idx:
            continue

        pred_sorted_idx = np.argsort(y_pred[i])[::-1]

        for k in k_values:
            top_k = set(pred_sorted_idx[:k])
            intersection = true_idx.intersection(top_k)
            recalls[k].append(len(intersection) / len(true_idx))

        # Mean Reciprocal Rank — rank of the first correct prediction
        rank = 0
        for r, idx in enumerate(pred_sorted_idx):
            if idx in true_idx:
                rank = r + 1
                break
        mrrs.append(1.0 / rank if rank > 0 else 0.0)

    return {
        "MRR": float(np.mean(mrrs)),
        "Recall@10": float(np.mean(recalls[10])),
        "Recall@20": float(np.mean(recalls[20])),
    }


def build_model(meta_dim: int) -> Model:
    """
    Dual-input Keras Functional API model.

    Branch A (Skills Sequence):
        Input(20, 384) -> Masking -> LSTM(128) -> LSTM(64)

    Branch B (Context Metadata):
        Input(meta_dim) -> Dense(32)

    Nexus:
        Concatenate([A_out, B_out]) -> Dense(256) -> Dropout(0.2) -> Dense(50, sigmoid)
    """
    # --- Branch A: Skill Sequence ---
    skills_input = Input(shape=(MAX_SKILLS, EMB_DIM), name="skills_input")
    x = Masking(mask_value=0.0)(skills_input)
    x = LSTM(128, return_sequences=True, dropout=0.2, name="lstm_1")(x)
    x = LSTM(64, return_sequences=False, dropout=0.2, name="lstm_2")(x)

    # --- Branch B: Role + Seniority Metadata ---
    meta_input = Input(shape=(meta_dim,), name="meta_input")
    m = Dense(32, activation="relu", name="meta_dense")(meta_input)

    # --- Nexus: Merge Both Branches ---
    merged = Concatenate(name="merge")([x, m])          # (64 + 32) = 96 features
    out = Dense(256, activation="relu", name="shared_dense")(merged)
    out = Dropout(0.2, name="dropout")(out)
    out = Dense(VOCAB_SIZE, activation="sigmoid", name="output")(out)

    model = Model(inputs=[skills_input, meta_input], outputs=out)
    model.compile(
        loss="binary_crossentropy",
        optimizer=Adam(learning_rate=0.001),
        metrics=["accuracy"],
    )
    return model


def train():
    logger.info("Starting Multi-Input LSTM training for Missing Skills Prediction...")
    dataset_path = DATA_DIR / "skill_gap_pairs.json"

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data.get("pairs", [])
    if not pairs:
        logger.error("No training pairs found.")
        return

    logger.info(f"Loaded {len(pairs)} records.")

    # ── 1. Build Top-50 Missing Skills Vocabulary ────────────────────
    all_missing = [skill for p in pairs for skill in p.get("missing_skills", [])]
    missing_counter = Counter(all_missing)
    top_50_missing = [skill for skill, _ in missing_counter.most_common(VOCAB_SIZE)]
    top_50_set = set(top_50_missing)
    logger.info(f"Top-50 vocab built. Most common: {missing_counter.most_common(1)[0]}")

    # ── 2. Parse All Four Fields from Every Record ───────────────────
    raw_skills, raw_roles, raw_seniorities, raw_y = [], [], [], []

    for p in pairs:
        raw_skills.append(p.get("current_skills", []))
        raw_roles.append([p.get("target_role", "Unknown")])
        raw_seniorities.append([p.get("seniority", "Unknown")])
        filtered_missing = [s for s in p.get("missing_skills", []) if s in top_50_set]
        raw_y.append(filtered_missing)

    # ── 3. Fit Context Encoders (future-proof: handle_unknown='ignore') ─
    logger.info("Fitting OneHotEncoders for Role and Seniority...")
    role_enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    seniority_enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)

    role_enc.fit(raw_roles)
    seniority_enc.fit(raw_seniorities)

    X_role = role_enc.transform(raw_roles)           # (N, 63)
    X_sen = seniority_enc.transform(raw_seniorities)  # (N,  4)
    X_meta = np.concatenate([X_role, X_sen], axis=1).astype(np.float32)  # (N, 67)
    meta_dim = X_meta.shape[1]
    logger.info(f"Metadata tensor shape: {X_meta.shape}  (roles={X_role.shape[1]}, seniorities={X_sen.shape[1]})")

    # ── 4. Embed Current Skills → (N, 20, 384) ──────────────────────
    logger.info("Initializing SentenceTransformer to embed skills...")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")
    unique_skills = list({s for seq in raw_skills for s in seq})
    logger.info(f"Encoding {len(unique_skills)} unique skills...")
    emb_matrix = encoder.encode(
        unique_skills, batch_size=256,
        show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True,
    )
    emb_dict = dict(zip(unique_skills, emb_matrix))

    X_skills = np.zeros((len(raw_skills), MAX_SKILLS, EMB_DIM), dtype=np.float32)
    for i, seq in enumerate(raw_skills):
        for j, skill in enumerate(seq[:MAX_SKILLS]):
            X_skills[i, j, :] = emb_dict[skill]

    # ── 5. Encode Target Labels → (N, 50) ───────────────────────────
    mlb = MultiLabelBinarizer(classes=top_50_missing)
    y = mlb.fit_transform(raw_y).astype(np.float32)
    logger.info(f"Skills tensor: {X_skills.shape} | Meta tensor: {X_meta.shape} | Labels: {y.shape}")

    # ── 6. Train / Test Split ────────────────────────────────────────
    indices = np.arange(len(y))
    idx_tr, idx_te = train_test_split(indices, test_size=0.2, random_state=42)

    X_skills_tr, X_skills_te = X_skills[idx_tr], X_skills[idx_te]
    X_meta_tr, X_meta_te     = X_meta[idx_tr],   X_meta[idx_te]
    y_tr, y_te               = y[idx_tr],         y[idx_te]
    logger.info(f"Train: {len(idx_tr)} | Test: {len(idx_te)}")

    # ── 7. Build & Summarise Model ───────────────────────────────────
    logger.info("Building dual-input Keras Functional API model...")
    keras_model = build_model(meta_dim)
    keras_model.summary(print_fn=logger.info)

    # ── 8. Train with Early Stopping ────────────────────────────────
    logger.info("Starting model training (max 50 epochs, patience=5)...")
    early_stop = EarlyStopping(
        monitor="val_loss", patience=5,
        restore_best_weights=True, verbose=1,
    )
    keras_model.fit(
        [X_skills_tr, X_meta_tr], y_tr,
        epochs=50,
        batch_size=32,
        validation_split=0.1,
        callbacks=[early_stop],
        verbose=1,
    )

    # ── 9. Evaluation Metrics ────────────────────────────────────────
    logger.info("Running inference on test set for metric evaluation...")
    t0 = time.time()
    y_pred = keras_model.predict([X_skills_te, X_meta_te], batch_size=32)
    latency_ms = (time.time() - t0) / len(X_skills_te) * 1000

    metrics = calculate_metrics(y_te, y_pred, k_values=[10, 20])
    logger.info(f"Recall@10 : {metrics['Recall@10']:.4f}  (Target >0.75)")
    logger.info(f"Recall@20 : {metrics['Recall@20']:.4f}  (Target >0.85)")
    logger.info(f"MRR       : {metrics['MRR']:.4f}  (Target >0.80)")
    logger.info(f"Latency   : {latency_ms:.2f} ms/sample  (Target <100 ms)")

    # ── 10. Evaluate accuracy on test set ────────────────────────────────────
    _, test_accuracy = keras_model.evaluate(
        [X_skills_te, X_meta_te], y_te, verbose=0
    )
    logger.info(f"Test binary accuracy: {test_accuracy:.4f}")

    # ── 11. Resolve versioned output directory ────────────────────────────────
    MODELS_DIR = get_version_dir()   # reads ML_MODEL_VERSION env var → default v1.0
    logger.info(f"Saving artifacts to: {MODELS_DIR}")

    # ── 12. Serialise All Four Artifacts ─────────────────────────────────────
    model_path = MODELS_DIR / "missing_skills_lstm.keras"
    keras_model.save(model_path)
    logger.info(f"[1/4] Model   → {model_path}  (native Keras format)")

    mlb_path = MODELS_DIR / "missing_skills_mlb.pkl"
    joblib.dump(mlb, mlb_path)
    logger.info(f"[2/4] MLB     → {mlb_path}")

    role_enc_path = MODELS_DIR / "role_encoder.pkl"
    joblib.dump(role_enc, role_enc_path)
    logger.info(f"[3/4] Role enc→ {role_enc_path}")

    sen_enc_path = MODELS_DIR / "seniority_encoder.pkl"
    joblib.dump(seniority_enc, sen_enc_path)
    logger.info(f"[4/4] Sen enc → {sen_enc_path}")

    # ── 13. Write standardized metadata.json ─────────────────────────────────
    save_version_artifacts(
        model_name="Missing-Skills LSTM",
        accuracy=round(float(test_accuracy), 6),
        f1_score=round(float(metrics["Recall@10"]), 6),   # Recall@10 as primary metric
        training_samples=int(len(idx_tr)),
        test_samples=int(len(idx_te)),
        extra_metadata={
            "recall_at_10":     round(float(metrics["Recall@10"]), 6),
            "recall_at_20":     round(float(metrics["Recall@20"]), 6),
            "mrr":              round(float(metrics["MRR"]), 6),
            "latency_ms":       round(float(latency_ms), 4),
            "vocab_size":       VOCAB_SIZE,
            "max_skills":       MAX_SKILLS,
            "embedding_dim":    EMB_DIM,
        },
    )

    logger.info("Training script completed successfully.")


if __name__ == "__main__":
    train()
