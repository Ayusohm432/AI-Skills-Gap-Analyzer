import os
import sys
import numpy as np
import joblib
from pathlib import Path
import warnings

# Suppress TensorFlow boot messages for clean output
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import tensorflow as tf
from sentence_transformers import SentenceTransformer

# Setup paths
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

MODELS_DIR = backend_dir / "models" / "ml_models" / "v1.0"
MAX_SKILLS = 20
EMB_DIM = 384


def test_inference(current_skills: list, target_role: str, seniority: str, top_n: int = 10):
    """
    Run inference using the multi-input LSTM model.

    Args:
        current_skills: List of skills the user currently owns.
        target_role:    The job title the user desires (e.g. "Data Scientist").
        seniority:      Career level (Fresher / Junior / Mid-level / Senior).
        top_n:          How many recommended missing skills to display.
    """
    print(f"\n{'='*62}")
    print(f"  Role     : {target_role}")
    print(f"  Seniority: {seniority}")
    print(f"  Skills   : {current_skills}")
    print(f"{'='*62}")

    # ── Verify all artifacts exist ───────────────────────────────────
    required = {
        "Model (.keras)":         MODELS_DIR / "missing_skills_lstm.keras",
        "Vocabulary (mlb.pkl)":   MODELS_DIR / "missing_skills_mlb.pkl",
        "Role Encoder":           MODELS_DIR / "role_encoder.pkl",
        "Seniority Encoder":      MODELS_DIR / "seniority_encoder.pkl",
    }
    for name, path in required.items():
        if not path.exists():
            print(f"[ERROR] Missing artifact: {name} at {path}")
            print("        Did you finish running `train_missing_skills_lstm.py`?")
            return

    # ── Load all artifacts ───────────────────────────────────────────
    model     = tf.keras.models.load_model(required["Model (.keras)"])
    mlb       = joblib.load(required["Vocabulary (mlb.pkl)"])
    role_enc  = joblib.load(required["Role Encoder"])
    sen_enc   = joblib.load(required["Seniority Encoder"])
    classes   = mlb.classes_
    print(f"[ OK ] Loaded model + {len(classes)}-class vocabulary + context encoders.")

    # ── Build metadata vector (Branch B) ────────────────────────────
    # handle_unknown='ignore' means unseen roles / seniorities produce zeros — no crash!
    X_role = role_enc.transform([[target_role]])        # (1, 63)
    X_sen  = sen_enc.transform([[seniority]])           # (1,  4)
    X_meta = np.concatenate([X_role, X_sen], axis=1).astype(np.float32)  # (1, 67)

    # ── Build skills sequence tensor (Branch A) ──────────────────────
    print("[ .. ] Encoding current skills with BERT...")
    encoder  = SentenceTransformer("all-MiniLM-L6-v2")
    X_skills = np.zeros((1, MAX_SKILLS, EMB_DIM), dtype=np.float32)

    for idx, skill in enumerate(current_skills[:MAX_SKILLS]):
        emb = encoder.encode(skill, convert_to_numpy=True, normalize_embeddings=True)
        X_skills[0, idx, :] = emb

    # ── Predict (dual-input injection) ──────────────────────────────
    print("[ .. ] Predicting missing skills...\n")
    predictions = model.predict([X_skills, X_meta], verbose=0)[0]

    # ── Display ranked results ───────────────────────────────────────
    sorted_indices = np.argsort(predictions)[::-1]
    print(f"  🎯  Top {top_n} Recommended Missing Skills for '{target_role}' ({seniority}):\n")
    print(f"  {'Rank':<6} {'Skill':<35} {'Confidence':>10}")
    print(f"  {'-'*6} {'-'*35} {'-'*10}")
    for rank in range(top_n):
        idx        = sorted_indices[rank]
        skill_name = classes[idx]
        confidence = predictions[idx] * 100
        print(f"  {rank+1:<6} {skill_name:<35} {confidence:>9.2f}%")
    print()


if __name__ == "__main__":
    # ── Test Case 1: Data Science, Mid-Level ────────────────────────
    test_inference(
        current_skills=["Python", "Pandas", "NumPy", "SQL", "Data Visualization"],
        target_role="Data Scientist",
        seniority="Mid-level",
    )

    # ── Test Case 2: Product Management, Junior ──────────────────────
    test_inference(
        current_skills=["A/B Testing", "Jira", "Stakeholder Management", "Agile Methodology"],
        target_role="Product Manager",
        seniority="Junior",
    )

    # ── Test Case 3: Android Dev, Fresher (tests unknown-role safety) ─
    test_inference(
        current_skills=["Java", "XML Layouts", "Android Studio"],
        target_role="Android",
        seniority="Fresher",
    )
