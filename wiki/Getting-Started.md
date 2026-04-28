# Getting Started

This page guides you from a fresh checkout to a fully running local development environment.

---

## Prerequisites

| Requirement | Minimum Version | Notes |
|-------------|----------------|-------|
| Python | 3.10 | 3.11 / 3.12 also work |
| Node.js | 18 LTS | 20 LTS recommended |
| npm | 9+ | Bundled with Node.js |
| MongoDB | 6.0+ | Community Server **or** MongoDB Atlas |
| Tesseract OCR | 5.x | Optional — only needed for image-based PDFs |

### MongoDB

- **Local** — install [MongoDB Community Server](https://www.mongodb.com/try/download/community) and ensure it listens on `localhost:27017`.
- **Atlas** — create a free M0 cluster and copy the connection string (see [Deployment](Deployment.md) for the full walkthrough).

---

## 1. Clone the Repository

```bash
git clone https://github.com/Ayusohm432/AI-Skills-Gap-Analyzer.git
cd AI-Skills-Gap-Analyzer
```

---

## 2. Backend Setup

### 2a. Create and activate a virtual environment

```bash
cd backend

# macOS / Linux
python -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
venv\Scripts\Activate.ps1
```

### 2b. Install Python dependencies

```bash
pip install -r requirements.txt
```

> **Note:** `requirements.txt` includes a direct wheel link for the SpaCy model `en_core_web_sm`. If the link is stale, run `python -m spacy download en_core_web_sm` after installing.

### 2c. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values (see [Configuration](Configuration.md) for the full reference):

```env
MONGO_URL=mongodb://localhost:27017
SECRET_KEY=change-me-to-a-long-random-string
GEMINI_API_KEY=your-google-gemini-api-key
```

### 2d. Seed the database (optional but recommended)

```bash
python seed.py
```

This populates the `job_descriptions` collection with canonical roles (Data Scientist, ML Engineer, Backend Developer, Frontend Developer, Cyber Security Analyst) and their required skill sets.

### 2e. Start the API server

```bash
uvicorn main:app --reload
```

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000` | Base API |
| `http://127.0.0.1:8000/docs` | Swagger / OpenAPI UI |
| `http://127.0.0.1:8000/redoc` | ReDoc |
| `http://127.0.0.1:8000/health` | Health check (liveness + ML model status) |

---

## 3. Frontend Setup

Open a **new** terminal from the project root:

```bash
cd frontend
npm install
```

Create a local environment file:

```bash
# frontend/.env.local
VITE_API_URL=http://127.0.0.1:8000
```

Start the dev server:

```bash
npm run dev
```

The app will be available at **http://localhost:5173**.

---

## 4. Verify Everything Works

1. Open `http://localhost:5173` — you should see the landing page.
2. Click **Get Started** and register a new account.
3. Log in, go to `/upload`, and upload a sample resume PDF.
4. The analysis job is submitted; the dashboard will populate once the background task completes (usually a few seconds).

---

## Useful Development Commands

| Command | Description |
|---------|-------------|
| `uvicorn main:app --reload` | Run backend with hot-reload |
| `python seed.py` | Seed/re-seed job descriptions |
| `python -m pytest tests/` | Run backend test suite |
| `npm run dev` | Frontend dev server |
| `npm run build` | Production frontend build |
| `npm run lint` | ESLint |

---

## Common Issues

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: spacy` | Activate the virtual environment first |
| `en_core_web_sm not found` | `python -m spacy download en_core_web_sm` |
| `MongoServerError: connect ECONNREFUSED` | Make sure MongoDB is running on port 27017 |
| `401 Unauthorized` on every request | Set `VITE_API_URL` correctly and ensure the backend is running |
| Frontend shows blank page | Run `npm install` inside the `frontend/` directory |
