# Class Distribution – `resumes_labeled.csv`

## Summary

| Role Label           | Count | % of Total |
|----------------------|------:|-----------:|
| Backend Developer    |   200 |      20.0% |
| Frontend Developer   |   175 |      17.5% |
| Full-Stack Developer |   175 |      17.5% |
| Data Scientist       |   150 |      15.0% |
| DevOps Engineer      |   125 |      12.5% |
| Cloud Architect      |   100 |      10.0% |
| Mobile Developer     |    75 |       7.5% |
| **Total**            | **1000** | **100%** |

## Notes

- The original issue specification listed 175 samples for Data Scientist, which would bring
  the total to 1025.  The count was reduced to 150 to hit the 1000-sample target while
  preserving all other class sizes exactly as specified.
- All records are **fully synthetic** or derived from anonymised public sources —
  no Personally Identifiable Information (PII) is present.
- ~70 % of samples are labelled `source = synthetic`; the remaining ~30 % are labelled
  `kaggle_anonymized` or `public_profile_anonymized`.

## Column Descriptions

| Column                | Type    | Description |
|-----------------------|---------|-------------|
| `id`                  | string  | Unique record identifier (`RES-NNNN`) |
| `role_label`          | string  | Target class label |
| `experience_years`    | integer | Years of professional experience (1–12) |
| `education_level`     | string  | Highest education level attained |
| `degree`              | string  | Degree / qualification name |
| `skills`              | string  | Pipe-separated list of technical skills |
| `certifications`      | string  | Pipe-separated list of certifications |
| `projects_summary`    | string  | Double-slash-separated project achievements |
| `professional_summary`| string  | Free-text career summary |
| `source`              | string  | Provenance tag (`synthetic`, `kaggle_anonymized`, `public_profile_anonymized`) |
