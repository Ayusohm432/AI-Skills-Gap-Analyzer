import os
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Base paths
backend_dir = Path(__file__).resolve().parent.parent.parent
data_dir = backend_dir / "models" / "data"

def process_demand():
    logger.info("Initializing KaggleHub...")
    try:
        import kagglehub
        import pandas as pd
    except ImportError:
        logger.error("kagglehub or pandas not installed. Please install them.")
        return

    logger.info("Downloading mjawad17/tech-jobs-salaries-and-skills-dataset...")
    try:
        path = kagglehub.dataset_download("mjawad17/tech-jobs-salaries-and-skills-dataset")
        logger.info(f"Dataset downloaded to {path}")
    except Exception as e:
        logger.error(f"Failed to download dataset: {e}")
        return

    csv_files = list(Path(path).glob("*.csv"))
    if not csv_files:
        logger.error("No CSV files found in the dataset.")
        return
        
    csv_path = csv_files[0]
    df = pd.read_csv(csv_path)
    
    if "job_title" not in df.columns:
        logger.error("Required column 'job_title' not found in dataset.")
        return

    # Standardize job titles to map cleanly to our typical roles
    # Normally we do robust NLP here, but for demonstration we clean it up directly
    def map_role(title):
        title = str(title).lower()
        if "data scientist" in title or "machine learning" in title: return "Data Scientist"
        if "data analyst" in title: return "Data Analyst"
        if "backend" in title: return "Backend Engineer"
        if "frontend" in title: return "Frontend Engineer"
        if "full stack" in title or "fullstack" in title: return "Full Stack Engineer"
        if "devops" in title or "sre" in title: return "DevOps Engineer"
        if "product manager" in title: return "Product Manager"
        if "software engineer" in title or "developer" in title: return "Software Engineer"
        return str(title).title()

    df['mapped_role'] = df['job_title'].apply(map_role)
    
    # Calculate demand (frequencies)
    counts = df['mapped_role'].value_counts()
    
    # Normalize counts to a multiplier between 0.8 and 1.5
    min_count = counts.min()
    max_count = counts.max()
    
    # Avoid division by zero if all counts are the same
    def normalize_count(c):
        if max_count == min_count:
            return 1.0
        return 0.8 + (0.7 * ((c - min_count) / (max_count - min_count)))

    demand_json = {}
    for role, count in counts.items():
        demand_json[role] = {
            "demand_multiplier": round(normalize_count(count), 2),
            "openings": int(count)
        }

    # Ensure other roles fall back to 1.0 if not listed here
    output_path = data_dir / "industry_demand.json"
    with open(output_path, "w") as f:
        json.dump(demand_json, f, indent=4)
        
    logger.info(f"Industry demands successfully saved to {output_path}")

if __name__ == "__main__":
    process_demand()
