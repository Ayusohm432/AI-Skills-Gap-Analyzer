import pandas as pd

# Load data
csv_path = '../datasets/job_skills_dataset.csv'
df = pd.read_csv(csv_path)

print("=" * 80)
print("ANALYZING YOUR DATA STRUCTURE")
print("=" * 80)

# Show data types
print("\n1. DATA TYPES:")
print("-" * 80)
print(df.dtypes)

# Show unique job roles
print("\n2. UNIQUE JOB ROLES:")
print("-" * 80)
unique_roles = df['job_role'].unique()
print(f"Total unique roles: {len(unique_roles)}")
print(f"Roles: {list(unique_roles)}")

# Show unique seniority levels
print("\n3. UNIQUE SENIORITY LEVELS:")
print("-" * 80)
unique_seniority = df['seniority'].unique()
print(f"Total seniority levels: {len(unique_seniority)}")
print(f"Levels: {list(unique_seniority)}")

# Show experience range
print("\n4. EXPERIENCE RANGE:")
print("-" * 80)
print(f"Min experience: {df['experience_years'].min()} years")
print(f"Max experience: {df['experience_years'].max()} years")
print(f"Average experience: {df['experience_years'].mean():.2f} years")

# Show skills example
print("\n5. EXAMPLE - REQUIRED SKILLS:")
print("-" * 80)
print(f"Row 1 (job_role: {df.iloc[0]['job_role']}, seniority: {df.iloc[0]['seniority']}):")
print(f"Skills: {df.iloc[0]['required_skills']}\n")

print(f"Row 5 (job_role: {df.iloc[5]['job_role']}, seniority: {df.iloc[5]['seniority']}):")
print(f"Skills: {df.iloc[5]['required_skills']}\n")

# Check for missing values
print("6. MISSING VALUES:")
print("-" * 80)
print(df.isnull().sum())

print("\n" + "=" * 80)