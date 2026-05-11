# AI Skill Gap Analyzer: Complete Platform Workflow
**Tagline:** "Google Maps for Career Development"

This document provides a comprehensive, technical walkthrough of the **AI Skill Gap Analyzer** platform. It covers the end-to-end journey from user interaction to deep semantic analysis and generative roadmap creation.

---

## 1. System Architecture Overview
The platform utilizes a high-performance, asynchronous microservices-inspired architecture designed for real-time AI inference and scalable data processing.

![System Architecture Diagram](/wiki/images/system_architecture_diagram_1778525242783.png)

---

## 2. Core Analysis Pipeline: Step-by-Step
The primary value proposition of the platform is its ability to turn a static resume into a dynamic learning journey.

### Phase 1: Intelligent Ingestion
1.  **Submission**: User uploads a resume (PDF/DOCX) and selects a target role or "Auto Detect".
2.  **Normalization**: The system validates MIME types and file size (< 10MB).
3.  **Job Enqueueing**: A unique `job_id` is generated, and a document is created in the `analysis_jobs` collection with a `pending` status.

### Phase 2: The ML Pipeline (The "Brain")
Once the background worker picks up the job, it executes the following sequence:

1.  **Text Extraction**: `pdfplumber` parses the document, maintaining structural integrity for better context.
2.  **Skill NER (Named Entity Recognition)**:
    *   Uses a combined approach of **SpaCy** and custom pattern matching.
    *   Detects technical skills (languages, frameworks, tools) and soft skills.
3.  **Role Prediction (Auto-Detect Mode)**:
    *   If the user didn't specify a role, a **Random Forest Classifier** analyzes the skill distribution to predict the most likely job profile.
4.  **Semantic Gap Analysis**:
    *   Matches detected skills against a database of 100+ canonical job roles.
    *   Uses a **Decision Tree model** to identify "critical" vs "nice-to-have" missing skills.
5.  **Scoring Engine**:
    *   Calculates a **Readiness Score (%)** using a weighted similarity metric.
6.  **Generative Generation**:
    *   **Roadmap**: Produces a weekly learning plan (Weeks 1-10) focused strictly on filling the detected gaps.
    *   **Interview Prep**: Generates technical questions targeted at the user's weak points.

### Phase 3: Real-time Visualization
1.  **Polling**: The React frontend polls the `/api/v1/jobs/{job_id}` endpoint.
2.  **Hydration**: Once the status hits `completed`, the frontend hydrates the dashboard.
3.  **Interaction**: Users can toggle between the **Readiness Chart**, **Skill Cloud**, and **Interactive Timeline Roadmap**.

---

## 3. Step-by-Step Execution Journey
This graph illustrates the linear path of a single analysis request from the moment the user clicks "Upload".

![Step-by-Step Execution Journey](/wiki/images/step_by_step_workflow_diagram_1778525258620.png)

---

## 4. Detailed Data Flow
This sequence diagram shows the communication flow between the user, backend, and AI engine during a typical analysis session.

![Detailed Data Flow Sequence Diagram](/wiki/images/data_flow_sequence_diagram_1778525274274.png)

---

## 5. Advanced System Features

### 🔐 Secure Authentication
*   **Multi-Provider OAuth**: Seamless login via Google or GitHub.
*   **Firebase Integration**: Secure OTP-based email verification for enhanced privacy.
*   **Session Management**: JWT tokens with automatic refresh logic.

### 📈 Market Intelligence
*   **Weekly Scrapers**: `APScheduler` runs background jobs every Monday to update market trends from job boards.
*   **Drift Detection**: The system monitors ML model performance weekly to ensure skill predictions stay relevant to current market demands.

### 🎯 Progress Tracking
*   **Interactive Roadmap**: Users can mark roadmap items as "In Progress" or "Completed".
*   **Skill Growth**: The platform tracks readiness score improvements over time as users gain new skills.

---

## 6. Technology Stack Summary

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 18, Vite, Tailwind CSS, Recharts, Framer Motion |
| **Backend** | FastAPI (Python 3.10+), Uvicorn, APScheduler, SlowAPI (Rate Limiting) |
| **Database** | MongoDB Atlas (NoSQL), Motor (Async Driver), Redis (Caching) |
| **AI / NLP** | SpaCy (NER), Scikit-Learn (ML), PDFPlumber, Gemini AI (Generative) |
| **DevOps** | Docker, GitHub Actions (CI/CD), Vercel (Frontend), Render/AWS (Backend) |
| **Monitoring**| Sentry (Error Tracking), ML Drift Monitoring Logs |
