import pandas as pd

# Load data
csv_path = '../datasets/job_skills_dataset.csv'
df = pd.read_csv(csv_path)

print("=" * 80)
print("CHECKING RAW SKILLS DATA")
print("=" * 80)

# Show first 5 rows of raw skills
for i in range(5):
    print(f"\nRow {i}:")
    print(f"  job_role: {df.iloc[i]['job_role']}")
    print(f"  seniority: {df.iloc[i]['seniority']}")
    print(f"  Raw skills (first 200 chars):")
    print(f"  {df.iloc[i]['required_skills'][:200]}")
    print(f"  ---")

print("\n" + "=" * 80)