import os
import json
import joblib
import numpy as np
from pathlib import Path

# Setup paths
backend_dir = Path(__file__).resolve().parent.parent
MODELS_DIR = backend_dir / "models" / "ml_models" / "v1.0"

def test_inference(skills_list):
    print(f"\n--- Testing Prediction for Skills: {skills_list} ---")
    
    # 1. Load the model and configuration
    model_path = MODELS_DIR / "role_predictor.pkl"
    config_path = MODELS_DIR / "config.json"
    
    if not model_path.exists() or not config_path.exists():
        print("Error: Model or config not found. Did you finish running train_role_predictor.py?")
        return

    # Load Random Forest Model
    model = joblib.load(model_path)
    
    # Load Vocabulary Config
    with open(config_path, "r") as f:
        config = json.load(f)
        
    feature_names = config["feature_names"]
    role_labels = config["role_labels"]
    
    # 2. Transform the raw skills into a 1s and 0s binary vector
    # We create a vector of 0s that matches the exact length of the features the model was trained on
    input_vector = np.zeros(len(feature_names))
    
    # Convert input skills to lowercase to ensure matching if needed, 
    # but we will just match directly depending on how they were trained
    found_skills = []
    for skill in skills_list:
        if skill in feature_names:
            idx = feature_names.index(skill)
            input_vector[idx] = 1.0
            found_skills.append(skill)
            
    print(f"Recognized Skills: {found_skills}")
    
    # 3. Make Prediction
    # Sklearn expects a 2D array, so we wrap it in a list: [input_vector]
    pred_idx = model.predict([input_vector])[0]
    probabilities = model.predict_proba([input_vector])[0]
    
    # 4. Map back to Role Name
    predicted_role = role_labels[pred_idx]
    confidence = probabilities[pred_idx] * 100
    
    print(f"-> Predicted Role: {predicted_role}")
    print(f"-> Confidence: {confidence:.2f}%")
    
    # Show top 3 alternative roles
    top_3_indices = np.argsort(probabilities)[::-1][:3]
    print("\nTop 3 Possibilities:")
    for i in top_3_indices:
        print(f"  {role_labels[i]}: {probabilities[i]*100:.2f}%")

if __name__ == "__main__":
    # Feel free to change these skills to whatever you want!
    mock_resume_skills = ["python", "pandas", "machine learning", "scikit-learn", "sql"]
    test_inference(mock_resume_skills)

    mock_resume_skills_2 = ["react", "javascript", "css", "html", "node.js"]
    test_inference(mock_resume_skills_2)
