import pandas as pd

# Load your CSV file
csv_path = '../datasets/job_skills_dataset.csv'
df = pd.read_csv(csv_path)

# Print basic information
print("=" * 60)
print("DATA LOADED SUCCESSFULLY!")
print(f"\nTotal rows: {len(df)}")
print(f"Total columns: {len(df.columns)}")
print(f"\nColumn names:")