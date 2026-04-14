import pandas as pd
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
import json

print("=" * 80)
print("TRAINING BERT ON YOUR DATA")
print("=" * 80)

# ============================================================================
# STEP 1: Load prepared data from outputs/
# ============================================================================

print("\n[STEP 1] Loading prepared data...")

output_dir = '../outputs'

# Load job descriptions
with open(f'{output_dir}/job_descriptions.txt', 'r') as f:
    job_descriptions = [line.strip() for line in f.readlines()]

# Load skill names
with open(f'{output_dir}/skill_names.json', 'r') as f:
    skill_names = json.load(f)

# Load binary labels
y = np.load(f'{output_dir}/y_labels.npy')

print(f"✓ Loaded {len(job_descriptions)} job descriptions")
print(f"✓ Loaded {len(skill_names)} skill names")
print(f"✓ Loaded binary labels shape: {y.shape}")

print(f"\nExample job description:")
print(f"  {job_descriptions[0]}")

print(f"\nExample skills to predict (first 5):")
print(f"  {skill_names[:5]}")

# ============================================================================
# STEP 2: Split data into TRAIN and TEST
# ============================================================================

print("\n[STEP 2] Splitting data into train/test...")

from sklearn.model_selection import train_test_split

X_train, X_test, y_train, y_test = train_test_split(
    job_descriptions,
    y,
    test_size=0.2,  # 20% for testing
    random_state=42
)

print(f"✓ Training set: {len(X_train)} examples")
print(f"✓ Testing set: {len(X_test)} examples")

# ============================================================================
# STEP 3: Create PyTorch Dataset Class
# ============================================================================

print("\n[STEP 3] Creating PyTorch dataset...")

class SkillDataset(Dataset):
    """Converts text and labels to format BERT understands"""
    
    def __init__(self, texts, labels, tokenizer, max_length=128):
        self.texts = texts
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_length = max_length
    
    def __len__(self):
        return len(self.texts)
    
    def __getitem__(self, idx):
        text = self.texts[idx]
        label = self.labels[idx]
        
        # Tokenize: convert text to numbers BERT understands
        encoding = self.tokenizer(
            text,
            max_length=self.max_length,
            padding='max_length',
            truncation=True,
            return_tensors='pt'
        )
        
        return {
            'input_ids': encoding['input_ids'].squeeze(),
            'attention_mask': encoding['attention_mask'].squeeze(),
            'labels': torch.tensor(label, dtype=torch.float)
        }

# ============================================================================
# STEP 4: Load BERT and Tokenizer
# ============================================================================

print("\n[STEP 4] Loading BERT model and tokenizer...")

# Load tokenizer (converts text to numbers)
tokenizer = AutoTokenizer.from_pretrained('distilbert-base-uncased')
print(f"✓ Loaded tokenizer")

# Load BERT model
model = AutoModelForSequenceClassification.from_pretrained(
    'distilbert-base-uncased',
    num_labels=len(skill_names),  # 50 skills to predict
    problem_type="multi_label_classification"
)
print(f"✓ Loaded BERT model")

# Move to GPU if available (faster training)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
model.to(device)
print(f"✓ Using device: {device}")

if device.type == 'cuda':
    print(f"  GPU available! Training will be ~10x faster!")
else:
    print(f"  Using CPU (slower but still works)")

# ============================================================================
# STEP 5: Create datasets
# ============================================================================

print("\n[STEP 5] Creating training datasets...")

train_dataset = SkillDataset(X_train, y_train, tokenizer)
test_dataset = SkillDataset(X_test, y_test, tokenizer)

print(f"✓ Training dataset created")
print(f"✓ Test dataset created")

# ============================================================================
# STEP 6: Configure training parameters
# ============================================================================

print("\n[STEP 6] Setting up training configuration...")

training_args = TrainingArguments(
    output_dir='../trained_model',      # Where to save
    num_train_epochs=3,                  # Train 3 times through data
    per_device_train_batch_size=4,       # 4 examples at a time
    per_device_eval_batch_size=4,
    warmup_steps=100,
    weight_decay=0.01,
    logging_steps=1,                     # Log progress every step
    eval_strategy="epoch",         # Evaluate after each epoch
    save_strategy="epoch",               # Save after each epoch
    learning_rate=2e-5,
    load_best_model_at_end=True,
)

print(f"✓ Training configuration:")
print(f"  - Epochs: 3")
print(f"  - Batch size: 4")
print(f"  - Learning rate: 2e-5")
print(f"  - Output dir: ../trained_model/")

# ============================================================================
# STEP 7: Create Trainer
# ============================================================================

print("\n[STEP 7] Creating Trainer...")

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=test_dataset,
)

print(f"✓ Trainer created and ready!")

# ============================================================================
# STEP 8: START TRAINING! (THIS TAKES TIME)
# ============================================================================

print("\n" + "=" * 80)
print("STARTING TRAINING!")
print("=" * 80)
print(f"\nThis will take 5-15 minutes...")
print(f"Estimated time depends on your computer (CPU vs GPU)")
print(f"\nYou'll see progress like this:")
print(f"  Epoch 1: Loss decreasing ✓")
print(f"  Epoch 2: Loss decreasing ✓")
print(f"  Epoch 3: Loss decreasing ✓")
print(f"\nJust wait patiently!\n")

# START TRAINING
trainer.train()

print("\n" + "=" * 80)
print("✓ TRAINING COMPLETE!")
print("=" * 80)

# ============================================================================
# STEP 9: Save the trained model
# ============================================================================

print("\n[STEP 9] Saving trained model...")

model.save_pretrained('../trained_model')
tokenizer.save_pretrained('../trained_model')

print(f"✓ Model saved to: backend/models/trained_model/")

# Save skill names for later use
with open('../trained_model/skill_names.json', 'w') as f:
    json.dump(skill_names, f, indent=2)

print(f"✓ Skill names saved")

# ============================================================================
# STEP 10: Test the trained model
# ============================================================================

print("\n[STEP 10] Testing the trained model...")
print("\nTesting on examples from your test set:\n")

model.eval()  # Set to evaluation mode

def predict_skills(job_description, threshold=0.5):
    """Predict skills for a job description"""
    
    # Tokenize
    inputs = tokenizer(
        job_description,
        max_length=128,
        padding='max_length',
        truncation=True,
        return_tensors='pt'
    )
    
    # Move to device
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    # Predict
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.sigmoid(logits)
    
    probs_np = probs.cpu().numpy()[0]
    
    # Get skills above threshold
    predicted = []
    for i, prob in enumerate(probs_np):
        if prob > threshold:
            predicted.append({
                'skill': skill_names[i],
                'confidence': float(prob)
            })
    
    predicted.sort(key=lambda x: x['confidence'], reverse=True)
    return predicted

# Test on a few examples
for i in range(min(3, len(X_test))):
    job_desc = X_test[i]
    predicted = predict_skills(job_desc)
    
    print(f"Example {i+1}:")
    print(f"  Job: {job_desc}")
    print(f"  Predicted skills (top 5):")
    
    if predicted:
        for skill in predicted[:5]:
            print(f"   ✓ {skill['skill']}: {skill['confidence']:.1%}")
    else:
        print(f"  No skills above threshold")
    
    print()

# ============================================================================
# FINAL SUMMARY
# ============================================================================

print("=" * 80)
print("TRAINING COMPLETE! ✓")
print("=" * 80)
print(f"""
✓ WHAT YOU HAVE NOW:
  - Trained BERT model
  - Saved to: backend/models/trained_model/
  - Can predict skills for any job description!

✓ FILES CREATED:
  - pytorch_model.bin (trained weights)
  - config.json
  - tokenizer.json
  - skill_names.json
  - vocab.txt

✓ NEXT STEPS:
  1. Use the model to make predictions
  2. Build backend API endpoint
  3. Connect frontend to API
  4. Deploy!

✓ HOW TO USE LATER:
  from transformers import AutoModelForSequenceClassification, AutoTokenizer
  
  model = AutoModelForSequenceClassification.from_pretrained('trained_model')
  tokenizer = AutoTokenizer.from_pretrained('trained_model')
  
  # Make predictions!
  result = predict_skills("Senior Nextjs engineer with 7.2 years")

Congratulations! You've trained your first AI model! 🎉
""")