# ML Training – Data

This directory contains the training data pipeline for the AI Skills Gap Analyzer.

## Dataset: `data/resumes_labeled.csv`

A 1000-sample labeled resume dataset assembled to train and evaluate the role-classification
and skill-gap models.

### Quick stats

| Attribute        | Value |
|------------------|-------|
| Total samples    | 1 000 |
| Number of classes| 7     |
| Median skills/record | ~10 |
| PII present      | **No** |

### Class distribution

See [`data/class_distribution.md`](data/class_distribution.md) for the full breakdown.

### Data sources

| Source tag                    | Share  | Description |
|-------------------------------|--------|-------------|
| `synthetic`                   | ~70 %  | Procedurally generated, parameterised records |
| `kaggle_anonymized`           | ~15 %  | Anonymised records derived from Kaggle datasets |
| `public_profile_anonymized`   | ~15 %  | Anonymised public GitHub profile data |

No source contains real names, email addresses, phone numbers, or any other PII.

### Reproducing the dataset

```bash
python ml_training/generate_dataset.py
```

The script uses a fixed random seed (`42`) so the output is deterministic.

### CSV columns

| Column                | Description |
|-----------------------|-------------|
| `id`                  | Unique record ID (`RES-NNNN`) |
| `role_label`          | Target class label |
| `experience_years`    | Years of experience (integer, 1–12) |
| `education_level`     | Highest education level |
| `degree`              | Degree / qualification title |
| `skills`              | Pipe-separated technical skills |
| `certifications`      | Pipe-separated certifications (may be empty) |
| `projects_summary`    | Notable project achievements (double-slash separated) |
| `professional_summary`| Free-text career summary |
| `source`              | Provenance tag |
