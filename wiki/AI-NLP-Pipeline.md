# AI & NLP Pipeline

This page explains how the platform processes a resume from raw bytes to a fully scored analysis, roadmap, and interview questions.

---

## Overview

The pipeline runs as a **FastAPI background task** (`BackgroundTasks`) so the HTTP response (`202 Accepted`) is returned immediately to the client. The frontend polls `GET /api/v1/jobs/{job_id}` every ~2 seconds.

The main entry-point is `backend/worker.py → run_analysis()`.

---

## Pipeline Steps

```
Raw file bytes  (PDF / DOCX / TXT / image-PDF)
        │
        ▼  Step 1
┌─────────────────────────────┐
│  Document Parser            │
│  pdfplumber · PyMuPDF       │
│  python-docx · pytesseract  │
└────────────┬────────────────┘
             │  plain text
             ▼  Step 2
┌─────────────────────────────┐
│  Skill Extractor            │
│  SpaCy en_core_web_sm NER   │
│  + keyword pattern matching │
│  → skills_detected[]        │
│  → skill_confidences{}      │
│  → skill_categories{}       │
└────────────┬────────────────┘
             │  skill list
             ▼  Step 3
┌─────────────────────────────┐
│  ML Role Predictor          │
│  Random Forest classifier   │
│  trained on resume dataset  │
│  → predicted_role           │
│  → role_confidence          │
│  → role_probabilities{}     │
│  → top_predictive_skills[]  │
└────────────┬────────────────┘
             │  predicted role
             ▼  Step 4
┌─────────────────────────────┐
│  Missing Skill Predictor    │
│  SentenceTransformers       │
│  cosine-similarity matching │
│  → missing_skills[]         │
│  → missing_skills_ranked[]  │
└────────────┬────────────────┘
             │  missing skills
             ▼  Step 5
┌─────────────────────────────┐
│  Readiness Score Engine     │
│  matched / required * 100   │
│  → readiness_score (0–100)  │
└────────────┬────────────────┘
             ▼  Step 6
┌─────────────────────────────┐
│  Roadmap Generator          │
│  Template-based weekly plan │
│  focused on missing skills  │
│  → roadmap[]                │
└────────────┬────────────────┘
             ▼  Step 7
┌─────────────────────────────┐
│  Interview Question Gen     │
│  SpaCy templates + Gemini   │
│  targeted at weak points    │
│  → interview_questions[]    │
└─────────────────────────────┘
```

---

## Step 1 — Document Parsing

**Module:** `backend/nlp/engine.py → extract_text_from_pdf()`

Supports four input types, tried in priority order:

| Format | Parser |
|--------|--------|
| PDF (text-based) | `pdfplumber` |
| PDF (scanned / image) | `PyMuPDF` + `pytesseract` OCR |
| DOCX | `python-docx` |
| TXT | Direct UTF-8 read |

The result is a single cleaned string of extracted text.

---

## Step 2 — Skill Extraction

**Module:** `backend/nlp/engine.py → extract_skills_combined()`

Two complementary strategies run in parallel:

1. **SpaCy NER** — the `en_core_web_sm` model labels named entities; patterns are checked against a curated `KNOWN_SKILLS` dictionary.
2. **Keyword / regex matching** — fast O(n) scan over the same `KNOWN_SKILLS` set, catching skills that NER misses (e.g. version-qualified skills like "Python 3.10").

Skills are then:
- Normalized to lowercase.
- Deduplicated.
- Assigned a confidence score based on match type and frequency.
- Categorized into domains (`languages`, `frameworks`, `data`, `cloud`, `devops`, `security`, …) by `categorize_skills()`.

---

## Step 3 — ML Role Prediction

**Module:** `backend/ml_inference.py → predict_role()`  
**Artifact:** `backend/models/ml_models/v1.0/role_classifier.joblib`

A **Random Forest** classifier trained on the labeled resume dataset in `Data/resume_dataset.csv`.

- Feature vector: TF-IDF or binary bag-of-skills over the `KNOWN_SKILLS` vocabulary.
- Returns `predicted_role`, full `role_probabilities`, and `top_predictive_skills` via feature importance.
- If the top class probability is below **0.60**, the role is set to `"Auto Detect"` (low confidence fallback).

---

## Step 4 — Missing Skill Prediction

**Module:** `backend/ml_inference.py → predict_missing_skills()`  
**Artifact:** `backend/models/ml_models/v1.0/` (SentenceTransformer embeddings)

1. Load the required skills for the predicted role from the `job_descriptions` collection (or `_DEFAULT_ROLES` constants if the DB is empty).
2. Encode both detected and required skills using **SentenceTransformers** (`all-MiniLM-L6-v2` or equivalent).
3. Compute **cosine similarity** between each required skill embedding and all detected skill embeddings.
4. Skills with max cosine similarity < 0.75 are classified as **missing** (threshold prevents exact-string-only matching; catches aliases like "React" ↔ "React.js").
5. Missing skills are ranked by importance (derived from role definition weights).

---

## Step 5 — Readiness Score

**Module:** `backend/ml_inference.py → compute_readiness_score()`

```python
readiness_score = (len(matched_required_skills) / len(total_required_skills)) * 100
```

Capped at 100 and rounded to one decimal place.

---

## Step 6 — Roadmap Generation

**Module:** `backend/nlp/engine.py → generate_roadmap()`

Generates a structured, week-by-week learning plan where each week focuses on one or more missing skills. Each entry includes:

- **week** — week number (1–10 typically).
- **focus** — skill(s) to learn that week.
- **topics** — key sub-topics to cover.
- **resources** — suggested free/paid resources (courses, docs, projects).
- **milestone** — measurable outcome to achieve by end of week.

---

## Step 7 — Interview Question Generation

**Module:** `backend/nlp/engine.py → generate_interview_questions()`  
**LLM module:** `backend/nlp/llm_interview.py` (Google Gemini)

Generates 10–15 technical interview questions targeting the candidate's identified missing skills. Questions span:
- **Conceptual** — "Explain X."
- **Application** — "How would you use X to solve Y?"
- **System design** — "Design a pipeline using X."

When `GEMINI_API_KEY` is set, Gemini generates highly context-aware questions. Without it, the engine falls back to template-based generation.

---

## ML Model Versioning

Models are stored under `backend/models/ml_models/<version>/` and the active version is controlled by the `ML_MODEL_VERSION` environment variable (default: `v1.0`).

The `POST /api/v1/models/activate/{version}` endpoint (admin-only, requires `X-Admin-Key`) hot-swaps the active model without restarting the server.

### Retraining

1. Export a new `resume_dataset.csv` to `Data/`.
2. Run the training notebook / script to produce new artifacts.
3. Place artifacts in `backend/models/ml_models/v1.1/`.
4. Call `POST /api/v1/models/activate/v1.1` with the admin key.

---

## Conversational Mock Interview (Gemini)

**Module:** `backend/nlp/llm_interview.py → InterviewLLM`  
**Service:** `backend/services/ai_interview_service.py`

A stateful session is stored in the `interview_sessions` collection. The flow:

```
POST /mock-interview/start
  → Creates session, fetches user's analysis context
  → Sends system prompt to Gemini with role + missing skills
  → Returns session_id + first question

POST /mock-interview/{id}/respond
  → Appends user answer to conversation history
  → Sends updated history to Gemini
  → Returns next question + feedback on the previous answer

POST /mock-interview/{id}/end
  → Sends "summarize" prompt to Gemini
  → Returns overall performance report
  → Marks session as completed
```
