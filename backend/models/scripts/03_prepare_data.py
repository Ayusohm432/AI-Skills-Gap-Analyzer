import pandas as pd
from sklearn.preprocessing import MultiLabelBinarizer, LabelEncoder
from collections import Counter

print("=" * 80)
print("SMART DATA PREPARATION")
print("=" * 80)

# Load data
csv_path = '../datasets/job_skills_dataset.csv'
df = pd.read_csv(csv_path)

print(f"\n✓ Data loaded: {len(df)} rows")

# ============================================================================
# STEP 1: Clean skills (convert text to list)
# ============================================================================

def clean_skills(skill_string):
    """Convert skill string to a list of skills"""
    if pd.isna(skill_string):
        return []
    
    # Split by comma and clean
    skills = str(skill_string).split(',')
    skills = [s.strip() for s in skills if s.strip()]
    return skills

df['required_skills_list'] = df['required_skills'].apply(clean_skills)

print(f"\n✓ Skills cleaned")
print(f"  Example row 0: {df.iloc[0]['required_skills_list'][:3]}...")

# ============================================================================
# STEP 2: Count skill frequency (find most common skills)
# ============================================================================

all_skills = []
for skills_list in df['required_skills_list']:
    all_skills.extend(skills_list)

skill_counts = Counter(all_skills)
total_unique_skills = len(skill_counts)

print(f"\n✓ Found {total_unique_skills} unique skills (TOO MANY!)")

# Get top 50 most common skills
top_n = 50
top_skills = skill_counts.most_common(top_n)
top_skill_names = [skill for skill, count in top_skills]

print(f"\n✓ Selected TOP {top_n} most common skills:")
print(f"  {top_skill_names[:10]}...")
print(f"\n  Skill frequencies:")
for skill, count in top_skills[:5]:
    print(f"    '{skill}': appears in {count} job roles")

# ============================================================================
# STEP 3: Filter skills (only keep top 50)
# ============================================================================

def filter_skills(skills_list):
    """Keep only top 50 skills"""
    return [s for s in skills_list if s in top_skill_names]

df['filtered_skills'] = df['required_skills_list'].apply(filter_skills)

print(f"\n✓ Skills filtered to top {top_n}")

# ============================================================================
# STEP 4: Create binary labels for filtered skills
# ============================================================================

mlb = MultiLabelBinarizer(classes=top_skill_names)
y = mlb.fit_transform(df['filtered_skills'])

print(f"\n✓ Binary labels created")
print(f"  Shape: {y.shape}")
print(f"  ({y.shape[0]} job descriptions, {y.shape[1]} skills)")
print(f"\n  Example - Row 0 Skills Present:")
for idx, skill in enumerate(top_skill_names[:5]):
    has_skill = y[0][idx]
    print(f"    {skill}: {has_skill}")

# ============================================================================
# STEP 5: Encode categorical variables
# ============================================================================

job_role_encoder = LabelEncoder()
seniority_encoder = LabelEncoder()

df['job_role_encoded'] = job_role_encoder.fit_transform(df['job_role'])
df['seniority_encoded'] = seniority_encoder.fit_transform(df['seniority'])

print(f"\n✓ Categorical variables encoded")
print(f"  Job roles encoding:")
for role, code in zip(job_role_encoder.classes_, job_role_encoder.transform(job_role_encoder.classes_)):
    print(f"    {role}: {code}")

print(f"\n  Seniority levels encoding:")
for level, code in zip(seniority_encoder.classes_, seniority_encoder.transform(seniority_encoder.classes_)):
    print(f"    {level}: {code}")

# ============================================================================
# STEP 6: Create text descriptions (for BERT)
# ============================================================================

def create_job_description(row):
    """Create a natural language description from structured data"""
    job = row['job_role']
    seniority = row['seniority']
    exp = row['experience_years']
    
    return f"{seniority} {job} engineer with {exp} years of experience"

df['job_description'] = df.apply(create_job_description, axis=1)

print(f"\n✓ Job descriptions created:")
print(f"  {df.iloc[0]['job_description']}")
print(f"  {df.iloc[1]['job_description']}")
print(f"  {df.iloc[2]['job_description']}")

# ============================================================================
# STEP 7: Summary
# ============================================================================

print("\n" + "=" * 80)
print("DATA PREPARATION COMPLETE!")
print("=" * 80)
print(f"\nPrepared Data Summary:")
print(f"  - Total rows: {len(df)}")
print(f"  - Unique job roles: {df['job_role'].nunique()}")
print(f"  - Unique seniority levels: {df['seniority'].nunique()}")
print(f"  - Original unique skills: {total_unique_skills}")
print(f"  - Selected top skills: {len(top_skill_names)}")
print(f"  - Binary labels shape: {y.shape}")
print(f"  - Memory efficient: YES ✓")

# ============================================================================
# STEP 8: Save prepared data for next steps
# ============================================================================

import pickle
import json

# Save for later use
output_dir = '../outputs'

# Save numpy array
import numpy as np
np.save(f'{output_dir}/y_labels.npy', y)
print(f"\n✓ Saved binary labels to: {output_dir}/y_labels.npy")

# Save job descriptions
with open(f'{output_dir}/job_descriptions.txt', 'w') as f:
    for desc in df['job_description']:
        f.write(desc + '\n')
print(f"✓ Saved job descriptions to: {output_dir}/job_descriptions.txt")

# Save skill names
with open(f'{output_dir}/skill_names.json', 'w') as f:
    json.dump(top_skill_names, f, indent=2)
print(f"✓ Saved skill names to: {output_dir}/skill_names.json")

# Save encoders
with open(f'{output_dir}/job_role_encoder.pkl', 'wb') as f:
    pickle.dump(job_role_encoder, f)
print(f"✓ Saved job role encoder to: {output_dir}/job_role_encoder.pkl")

with open(f'{output_dir}/seniority_encoder.pkl', 'wb') as f:
    pickle.dump(seniority_encoder, f)
print(f"✓ Saved seniority encoder to: {output_dir}/seniority_encoder.pkl")

print("\n" + "=" * 80)