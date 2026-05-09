# AI Skill Gap Analyzer Platform

## 🌐 Platforms

- **Production (Live App):** [Visit Production](https://ayusohm432.github.io/AI-Skills-Gap-Analyzer/)
- **Development (Staging App):** [Visit Development](https://ayusohm432.github.io/AI-Skills-Gap-Analyzer/dev/)


"Google Maps for Career Development"

This platform analyzes a student's resume, compares it with real job descriptions, identifies missing skills, and generates a personalized learning roadmap with a Job Readiness Score.

## Architecture
- **Frontend**: React.js, Vite, TailwindCSS, Recharts
- **Backend API**: Python, FastAPI
- **Database**: MongoDB (motor async driver)
- **AI Engine**: SpaCy NLP, PDFPlumber

## How to Run locally

Prerequisites:
- **Node.js**: v18+
- **Python**: 3.10+
- **MongoDB**: You need MongoDB Community Server running locally on port `27017` or a MongoDB Atlas URI.

### 1. Start the Backend API (FastAPI)
Open a terminal in the root folder:aa

```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt

# Start FastAPI (Ensure MongoDB is running locally)
uvicorn main:app --reload
```
*API will run at http://127.0.0.1:8000*
*Swagger Docs available at http://127.0.0.1:8000/docs*

### 2. Start the Frontend (React + Vite)
Open a **new** terminal in the root folder:

```bash
cd frontend
npm install
npm run dev
```
*Application will run at http://localhost:5173*
