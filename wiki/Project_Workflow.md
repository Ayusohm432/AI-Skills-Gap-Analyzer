# AI Skill Gap Analyzer: Complete Platform Workflow

This document provides a detailed, illustrative workflow of the **AI Skill Gap Analyzer** platform, from user interaction to background AI processing.

---

## 1. High-Level System Architecture

The platform is built on a modern, asynchronous stack designed for high performance and scalability.

```mermaid
graph TD
    subgraph Client ["Client Layer (Frontend)"]
        UI["React / Vite Application"]
        Store["State Management & Persistence"]
    end

    subgraph API ["Service Layer (Backend)"]
        FastAPI["FastAPI Gateway"]
        Auth["Firebase & OAuth Service"]
        Worker["Async Task Worker"]
    end

    subgraph AI ["Intelligence Layer (ML/NLP)"]
        Parser["Text Extraction - pdfplumber"]
        NLP["Skill NER - SpaCy/Combined"]
        ML["ML Models - Random Forest & Decision Tree"]
        GenAI["Generative Roadmap Engine"]
    end

    subgraph Storage ["Data Layer"]
        Mongo[("MongoDB Atlas")]
        Redis[("Redis Cache")]
    end

    UI --- FastAPI
    FastAPI --> Auth
    FastAPI --> Worker
    Worker --> AI
    AI --> Mongo
    FastAPI --- Mongo
```

---

## 2. The Core Workflow: Resume Analysis & Roadmap Generation

The heart of the platform is the asynchronous analysis pipeline. Here is the step-by-step sequence:

### Phase 1: Submission & Ingestion
1.  **User Upload**: The user uploads their resume (PDF/DOCX) and selects a target job role (or chooses "Auto Detect").
2.  **API Validation**: The backend validates the file (MIME type, size < 10MB) and creates a **Job Document** in MongoDB with status `pending`.
3.  **Immediate Response**: The API returns a `job_id` to the frontend instantly (HTTP 202 Accepted).

### Phase 2: Background Processing (The "Brain")
Once enqueued, the `worker.py` takes over:

1.  **Text Extraction**: The PDF/DOCX is parsed into raw text using `pdfplumber`.
2.  **Skill Detection**:
    *   A combination of **Named Entity Recognition (NER)** and **Pattern Matching** identifies programming languages, tools, and frameworks.
    *   Skills are normalized and categorized.
3.  **Role Prediction (if "Auto Detect")**:
    *   The platform uses a **Random Forest model** to analyze the detected skills and predict the most likely job role (e.g., "Backend Developer").
4.  **Skill Gap Analysis**:
    *   The user's skills are compared against the target role's requirements.
    *   A **Decision Tree model** identifies critical missing skills.
5.  **Scoring & Roadmap**:
    *   A **Readiness Score** is calculated based on the match percentage.
    *   A **10-Week Learning Roadmap** is generated, prioritizing the most important missing skills.
    *   **Technical Interview Questions** are generated specifically for the detected skill gaps.

### Phase 3: Result Retrieval
1.  **Polling**: The frontend polls the status endpoint (`/api/v1/jobs/{job_id}`) every 2 seconds.
2.  **Completion**: Once the worker finishes, the job status moves to `completed`.
3.  **Visualization**: The frontend fetches the final analysis and renders:
    *   **Circular Progress** for the Readiness Score.
    *   **Skill Clouds** for detected vs. missing skills.
    *   **Interactive Timeline** for the roadmap.

---

## 3. Data Flow Sequence Diagram

```mermaid
sequenceDiagram
    participant User as "User (Frontend)"
    participant API as "FastAPI Backend"
    participant Worker as "Background Worker"
    participant ML as "ML Pipeline"
    participant DB as "MongoDB"

    User->>API: "POST /analyze/resume (File + Role)"
    API->>DB: "Create Job (status=pending)"
    API-->>User: "202 Accepted (job_id)"
    
    Note over User, API: "Frontend starts polling /jobs/{job_id}"

    API->>Worker: "Dispatch run_analysis(job_id)"
    Worker->>ML: "extract_text_from_pdf()"
    ML-->>Worker: "Raw Text"
    Worker->>ML: "detect_skills(text)"
    ML-->>Worker: "Skill List"
    Worker->>ML: "predict_role(skills)"
    ML-->>Worker: "Target Role"
    Worker->>ML: "compute_readiness_and_gap()"
    ML-->>Worker: "Score + Missing Skills"
    Worker->>ML: "generate_roadmap_and_qs()"
    ML-->>Worker: "Roadmap + Interview Qs"
    
    Worker->>DB: "Update Job (status=completed, result=...)"
    
    User->>API: "GET /jobs/{job_id} (Polling)"
    API->>DB: "Fetch Job Result"
    DB-->>API: "Result Data"
    API-->>User: "200 OK (Analysis JSON)"
```

---

## 4. 🚀 Detailed Execution Blueprint (Vertical Flow)

This blueprint illustrates the vertical progression of a single analysis request, highlighting the decision logic and background processing loops.

```mermaid
graph TD
    %% User Interaction Layer
    subgraph UserLayer ["<b>👤 USER INTERACTION</b>"]
        Start([<b>START</b>]) --> Upload[/<b><font color='#4f46e5'>Step 1: Resume Submission</font></b><br/><font color='#6366f1'>📄 Upload PDF/DOCX</font>/]
        PollLoop{<b><font color='#475569'>Step 10: Result?</font></b><br/><font color='#64748b'>🔄 Frontend Polling Loop</font>} -->|Wait| PollLoop
        PollLoop -->|Ready| Dashboard["<b><font color='#059669'>Step 11: Dashboard</font></b><br/><font color='#10b981'>🖥️ Interactive UI Render</font>"]
    end

    %% Backend Validation & Queue
    subgraph BackendLayer ["<b>⚙️ SERVICE GATEWAY</b>"]
        Upload --> CreateJob["<b><font color='#4338ca'>Step 2: Job Enqueuing</font></b><br/><font color='#4f46e5'>🏗️ MongoDB status: 'pending'</font>"]
        CreateJob --> Response[/<b><font color='#4338ca'>Immediate Response</font></b><br/><font color='#4f46e5'>✅ 202 Accepted + JobID</font>/]
        Response -.-> PollLoop
    end

    %% AI & Intelligence Engine
    subgraph EngineLayer ["<b>🧠 INTELLIGENCE ENGINE (Worker)</b>"]
        CreateJob --> Parse["<b><font color='#7c3aed'>Step 3: Text Parsing</font></b><br/><font color='#8b5cf6'>📑 pdfplumber Extraction</font>"]
        Parse --> SkillNER["<b><font color='#7c3aed'>Step 4: Skill Extraction</font></b><br/><font color='#8b5cf6'>🔍 Combined NER Engine</font>"]
        
        %% Decision Logic for Role
        SkillNER --> RoleChoice{<b><font color='#7c3aed'>Auto Detect?</font></b><br/><font color='#8b5cf6'>❓ Logic Branch</font>}
        RoleChoice -->|Yes| MLPredict["<b><font color='#7c3aed'>Step 5a: AI Role Prediction</font></b><br/><font color='#8b5cf6'>🤖 Random Forest Model</font>"]
        RoleChoice -->|No| ManualRole["<b><font color='#7c3aed'>Step 5b: Manual Role</font></b><br/><font color='#8b5cf6'>👤 User Selection</font>"]
        
        MLPredict --> GapAnal
        ManualRole --> GapAnal
        
        GapAnal["<b><font color='#db2777'>Step 6: Gap Analysis</font></b><br/><font color='#ec4899'>⚖️ Skill Matrix Comparison</font>"]
        GapAnal --> Scoring["<b><font color='#db2777'>Step 7: Scoring Engine</font></b><br/><font color='#ec4899'>📈 Readiness % Computation</font>"]
        Scoring --> Roadmap["<b><font color='#db2777'>Step 8: Roadmap Gen</font></b><br/><font color='#ec4899'>🗺️ Generative AI Plan</font>"]
    end

    %% Data Persistence
    subgraph StorageLayer ["<b>💾 PERSISTENCE</b>"]
        Roadmap --> Persist[("<b><font color='#059669'>Step 9: Storage</font></b><br/><font color='#10b981'>📁 MongoDB Result Update</font>")]
        Persist -.-> PollLoop
    end

    %% Premium Styling
    style Start fill:#f8fafc,stroke:#334155,stroke-width:4px
    style Dashboard fill:#ecfdf5,stroke:#059669,stroke-width:2px
    style MLPredict fill:#f5f3ff,stroke:#7c3aed,stroke-width:2px
    style Roadmap fill:#fff1f2,stroke:#db2777,stroke-width:2px
    
    classDef UserNode fill:#f1f5f9,stroke:#64748b,stroke-width:2px;
    classDef ServiceNode fill:#e0e7ff,stroke:#4338ca,stroke-width:2px;
    classDef EngineNode fill:#f5f3ff,stroke:#7c3aed,stroke-width:2px;
    classDef StorageNode fill:#ecfdf5,stroke:#059669,stroke-width:2px;

    class Start,Upload,PollLoop,Dashboard UserNode;
    class CreateJob,Response ServiceNode;
    class Parse,SkillNER,RoleChoice,MLPredict,ManualRole,GapAnal,Scoring,Roadmap EngineNode;
    class Persist StorageNode;

    %% Interactive Links
    click MLPredict "#phase-2-background-processing-the-brain" "ML Model Details"
    click Roadmap "#phase-2-background-processing-the-brain" "Generative Logic"
```

---

## 5. Secondary Workflows

### Authentication Flow (Hybrid)
*   **OAuth**: Users can sign in via Google or GitHub.
*   **OTP**: Email-based login uses Firebase to send One-Time Passwords for secure, passwordless entry.
*   **JWT**: The backend issues short-lived Access Tokens and long-lived Refresh Tokens.

### Market Trends & Monitoring
*   **Weekly Refresh**: Every Monday, a scheduler (`APScheduler`) triggers a market data refresh, scraping/updating trending skills for each role.
*   **Model Monitoring**: The system audits ML model performance weekly, checking for "concept drift" to ensure skill predictions remain accurate.
*   **Alerts**: If a user is "subscribed" to a role, they receive alerts when new trending skills are detected in the market.

---

## 6. Technology Stack Summary

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React, Vite, Tailwind CSS, Recharts, Framer Motion |
| **Backend** | FastAPI (Python), Uvicorn, APScheduler |
| **Database** | MongoDB (NoSQL), Motor (Async Driver) |
| **AI/ML** | SpaCy, Scikit-Learn, PDFPlumber, Gemini AI |
| **Infrastructure**| Vercel (Frontend), Render/AWS (Backend), MongoDB Atlas |
| **Auth** | Firebase Admin SDK, GitHub/Google OAuth2 |
