# AI Skill Gap Analyzer Platform

"Google Maps for Career Development"

This platform analyzes a student's resume, compares it with real job descriptions, identifies missing skills, and generates a personalized learning roadmap with a Job Readiness Score.

## Architecture
- **Frontend**: React.js, Vite, TailwindCSS, Recharts
- **Backend API**: Python, FastAPI
- **Database**: MongoDB (motor async driver)
- **AI Engine**: 
  - **NLP**: SpaCy (NER & Skill Mapping)
  - **Extraction**: PyMuPDF (High-speed native PDF)
  - **OCR**: Pytesseract (Tesseract OCR fallback for scanned resumes)

## How to Run locally

### Prerequisites:
- **Node.js**: v18+
- **Python**: 3.10+
- **MongoDB**: You need MongoDB Community Server running locally on port `27017` or a MongoDB Atlas URI.
- **Tesseract OCR (Optional but Recommended)**: 
  - Required for reading scanned/image-only resumes.
  - **Windows**: Download and install from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki).
  - **Linux**: `sudo apt install tesseract-ocr`
  - **Mac**: `brew install tesseract`

### 1. Start the Backend API (FastAPI)
Open a terminal in the root folder:

```bash
cd backend
python -m venv venv

# On Windows (Git Bash / PowerShell):
source venv/Scripts/activate
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

## Testing the AI Pipeline

To verify the PDF extraction and text cleaning logic:

```bash
cd backend
# Ensure venv is active
python -m pytest tests/test_pdf_extractor.py -v
```

## Extraction Pipeline Strategy
The system uses a smart dual-stage extraction pipeline:
1. **NATIVE**: Attempts to extract embedded text using `PyMuPDF` (optimized for speed).
2. **OCR FALLBACK**: If the document yields <100 characters (scanned/image), it automatically re-processes the file using `Tesseract OCR`.
3. **CLEANING**: Strips headers/footers, removes noise (page numbers, dividers), and normalizes whitespace for better NLP analysis.
