# Deployment

This guide covers deploying the AI Skill Gap Analyzer to production using entirely **free-tier** services:

| Layer | Service |
|-------|---------|
| Database | MongoDB Atlas (M0 free cluster) |
| Backend | Render.com (Python Web Service) |
| Frontend | Vercel |

---

## Prerequisites

- All source code pushed to a GitHub repository.
- Accounts on [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register), [Render.com](https://render.com/), and [Vercel](https://vercel.com/).

---

## Step 1 — Cloud Database (MongoDB Atlas)

1. Log in to MongoDB Atlas and click **Build a Database**.
2. Choose the **M0 Free** tier; select a cloud region close to your users.
3. Create a database user (save the password — you cannot retrieve it later).
4. Under **Network Access** add IP `0.0.0.0/0` to allow connections from Render.
5. From your cluster dashboard click **Connect → Drivers (Python 3.6+)** and copy the connection string:
   ```
   mongodb+srv://admin:<password>@cluster.abcde.mongodb.net/?retryWrites=true&w=majority
   ```
6. Replace `<password>` with your actual password. This is your `MONGO_URL`.

---

## Step 2 — Backend (Render.com)

1. Log in to Render and click **New + → Web Service**.
2. Connect your GitHub repository.
3. Configure the service:

   | Setting | Value |
   |---------|-------|
   | **Name** | `ai-skill-gap-api` |
   | **Root Directory** | `backend` |
   | **Runtime** | Python 3 |
   | **Build Command** | `pip install -r requirements.txt` |
   | **Start Command** | `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker` |
   | **Instance Type** | Free |

4. Add environment variables (see [Configuration](Configuration.md) for the full list):

   | Key | Value |
   |-----|-------|
   | `MONGO_URL` | Your Atlas connection string |
   | `SECRET_KEY` | A long random string |
   | `GEMINI_API_KEY` | Your Google Gemini key |
   | `ML_MODEL_VERSION` | `v1.0` |
   | `ADMIN_API_KEY` | A random 32-byte hex string |
   | `PYTHON_VERSION` _(optional)_ | `3.10.0` |

5. Click **Create Web Service**. Monitor the build logs — the first deploy takes 3–5 minutes.
6. Copy the service URL (e.g. `https://ai-skill-gap-api-xyz.onrender.com`). This is your **backend URL**.

> **Free-tier note:** Render's free tier spins down after 15 minutes of inactivity. The backend includes a keep-alive background thread that pings `RENDER_EXTERNAL_URL` every 10 minutes. Set `RENDER_EXTERNAL_URL` to the service URL to keep it warm.

---

## Step 3 — Frontend (Vercel)

1. Log in to Vercel and click **Add New → Project**.
2. Import your GitHub repository.
3. Configure the project:

   | Setting | Value |
   |---------|-------|
   | **Framework Preset** | Vite (auto-detected) |
   | **Root Directory** | `frontend` |

4. Add environment variable:

   | Name | Value |
   |------|-------|
   | `VITE_API_URL` | Your Render backend URL (**no trailing slash**) |

5. Click **Deploy**. Vercel builds and deploys in ~1–2 minutes.
6. Copy the generated URL (e.g. `https://ai-skill-gap.vercel.app`). This is your **frontend URL**.

---

## Step 4 — Configure CORS

The backend must whitelist the Vercel domain:

1. Go to your Render service → **Environment**.
2. Add:

   | Key | Value |
   |-----|-------|
   | `FRONTEND_URL` | Your Vercel URL (**no trailing slash**) |

3. Click **Save Changes**. Render restarts the service automatically.

---

## Step 5 — Seed the Production Database

With the production backend live but the database empty, run the seed script locally against the Atlas cluster:

```bash
cd backend

# Temporarily point to production DB
export MONGO_URL="mongodb+srv://admin:password@cluster.mongodb.net/..."

python seed.py

# Restore local DB for development
export MONGO_URL="mongodb://localhost:27017"
```

---

## Step 6 — Smoke Test

1. Open the Vercel URL.
2. Register a new account.
3. Upload a sample resume and select a role.
4. Wait for the analysis to complete and verify the dashboard populates.

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| "Network Error" in the frontend | `VITE_API_URL` is wrong or Render is sleeping | Check env var; wait ~50 s for Render cold start |
| `500 Internal Server Error` on upload | `MONGO_URL` wrong or SpaCy model missing | Check Render logs; ensure `en_core_web_sm` wheel is in `requirements.txt` |
| SpaCy `OSError: [E050]` in Render logs | SpaCy model not installed | Add `https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` to `requirements.txt` |
| Login returns `401` immediately | `SECRET_KEY` not set on Render | Add `SECRET_KEY` env var |
| CORS errors in browser | `FRONTEND_URL` not set or wrong | Add/correct `FRONTEND_URL` on Render and redeploy |

---

## Docker (Optional Local / Self-Hosted)

A sample `Dockerfile` for the backend:

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and run:
```bash
docker build -t ai-skill-gap-backend ./backend
docker run -p 8000:8000 --env-file backend/.env ai-skill-gap-backend
```
