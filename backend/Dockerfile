# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – Base image with system-level dependencies
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.10-slim

# Install Tesseract OCR engine + required image libs + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    curl \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – Python application
# ─────────────────────────────────────────────────────────────────────────────
WORKDIR /app

# Copy and install Python dependencies first (layer cache optimisation)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port Gunicorn will listen on (Render injects $PORT at runtime)
EXPOSE 8000

# Start the server with Gunicorn + Uvicorn workers
# Render sets the PORT env variable automatically
CMD ["sh", "-c", "gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}"]
