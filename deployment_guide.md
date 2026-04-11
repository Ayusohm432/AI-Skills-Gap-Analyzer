# AI Skill Gap Analyzer - Deployment Guide

This guide provides a step-by-step walkthrough for deploying your application to **Render** (Backend) and **GitHub Pages** (Frontend) with automated CI/CD for both `main` and `development` branches.

---

## 🏗️ 1. Backend Setup (Render)

You will need two separate Web Services on Render to support separate Production and Staging environments.

### Step A: Create Production Service (Main)
1. Log in to [Render](https://render.com).
2. Click **New +** > **Web Service**.
3. Connect your GitHub repository: `Ayusohm432/AI-Skills-Gap-Analyzer`.
4. **Name**: `ai-skills-prod`
5. **Branch**: `main`
6. **Root Directory**: `backend`
7. **Runtime**: `Python 3`
8. **Build Command**: `pip install -r requirements.txt`
9. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
10. Click **Advanced** and add Environment Variables:
    - `MONGO_URL`: Your MongoDB Atlas string.
    - `SECRET_KEY`: A secure random string (e.g., `openssl rand -hex 32`).
    - `ACCESS_TOKEN_EXPIRE_MINUTES`: `15`
    - `REFRESH_TOKEN_EXPIRE_DAYS`: `7`
11. Click **Create Web Service**.

### Step B: Create Staging Service (Development)
1. Repeat the steps above.
2. **Name**: `ai-skills-staging`
3. **Branch**: `development`
4. Follow the same build/start commands and env vars (you can use the same or a different MongoDB database/cluster).

### Step C: Get Deploy Hooks
1. For each service, go to **Settings** > **Deploy Hook**.
2. Copy the URLs. You will need these for GitHub Secrets.

---

## 🎨 2. Frontend Setup (GitHub Pages)

### Step A: Enable Pages
1. Go to your GitHub Repository > **Settings** > **Pages**.
2. Under **Build and deployment** > **Source**, select **GitHub Actions**.

---

## 🔐 3. GitHub Secrets Configuration

To allow automated deployment, you must add the following secrets to your GitHub repository:
1. Go to **Settings** > **Secrets and Variables** > **Actions**.
2. Click **New repository secret** for each of these:

| Secret Name | Description | Example |
| :--- | :--- | :--- |
| `RENDER_DEPLOY_HOOK_PROD` | Deploy hook from Render `ai-skills-prod` | `https://api.render.com/deploy/...` |
| `RENDER_DEPLOY_HOOK_DEV` | Deploy hook from Render `ai-skills-staging` | `https://api.render.com/deploy/...` |
| `VITE_API_URL_PROD` | Production Backend URL | `https://ai-skills-prod.onrender.com` |
| `VITE_API_URL_DEV` | Staging Backend URL | `https://ai-skills-staging.onrender.com` |

---

## 🚀 4. How the Automation Works

### Production (`main` branch)
When you push to `main`:
1. **GitHub Action** builds the frontend with the `VITE_API_URL_PROD` and base path `/AI-Skills-Gap-Analyzer/`.
2. It deploys the build to the `gh-pages` branch.
3. It pings Render to redeploy the latest backend code.
4. **Result**: Your app is live at `https://ayusohm432.github.io/AI-Skills-Gap-Analyzer/`.

### Staging (`development` branch)
When you push to `development`:
1. **GitHub Action** builds the frontend with the `VITE_API_URL_DEV` and base path `/AI-Skills-Gap-Analyzer/dev/`.
2. It deploys the build to the `dev` folder in the `gh-pages` branch.
3. It pings Render to redeploy the staging backend code.
4. **Result**: Your app is live at `https://ayusohm432.github.io/AI-Skills-Gap-Analyzer/dev/`.

---

## 💡 Troubleshooting

- **CORS Issues**: Ensure that in `backend/main.py`, the `allowed_origins` includes your GitHub Pages domains.
- **Port Errors**: Render provides a dynamic `$PORT`. Ensure your start command uses the `--port $PORT` flag.
- **Base Path**: If the site shows a blank page, check the console for "404 Not Found" on assets. Ensure `vite.config.js` is using the `VITE_BASE_PATH` correctly.
