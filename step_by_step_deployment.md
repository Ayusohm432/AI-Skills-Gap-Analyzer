# The Ultimate Step-by-Step Production Deployment Guide

This comprehensive guide will walk you through every single click and command required to host the **AI Skill Gap Analyzer** from scratch. 
We will use entirely free-tier services to host this platform. Our production stack involves:
1. **Source Code:** GitHub
2. **Database:** MongoDB Atlas (Cloud)
3. **Backend API:** Render.com (FastAPI / Python)
4. **Frontend UI:** Vercel (React / Vite)

---

## Pre-requisite: Push Your Code to GitHub

Both Render and Vercel fetch your code directly from GitHub and deploy it automatically.

1. Create a free account on [GitHub](https://github.com/).
2. Create a new repository (e.g., `ai-skill-gap`). Make it Public or Private based on your preference.
3. Open a terminal on your computer in the root folder of your project (`Ai-Skills-Gap-Analyzer/`).
4. Run the following commands to push your code:
   ```bash
   git init
   git add .
   git commit -m "Initial commit for production"
   git branch -M main
   # Replace the URL below with YOUR repository URL
   git remote add origin https://github.com/yourusername/ai-skill-gap.git
   git push -u origin main
   ```

---

## Step 1: Set up the Cloud Database (MongoDB Atlas)

Your application needs a live, universally accessible database server for production.

1. **Sign Up:** Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) and sign up for a free account.
2. **Create a Cluster:**
   - Once logged in, click **"Build a Database"** (or "+ Create").
   - Choose the **M0 Free/Shared** plan.
   - Provider: AWS, region: Choose the one closest to your location (e.g., `Mumbai (ap-south-1)` or `N. Virginia (us-east-1)`).
   - Give cluster a name (e.g., `AiSkillGapCluster`) and click **"Create Cluster"**.
3. **Security Configuration - Create User:**
   - You will be prompted to create a database user.
   - Enter a **Username** (e.g., `admin`).
   - Enter a **Password** (or click Auto-Generate and copy it). 
   - **CRITICAL:** Save this password in a notepad! You cannot retrieve it later. Click **"Create User"**.
4. **Security Configuration - Network Access:**
   - Scroll down to "Where would you like to connect from?".
   - Choose **"My Local Environment"**.
   - In the IP Access List, enter `0.0.0.0/0` (This allows access from anywhere, including Render.com servers).
   - Description: "Allow All". Click **"Add Entry"** and then **"Finish and Close"**.
5. **Get Your Connection String:**
   - Go to your cluster overview dashboard.
   - Click the **"Connect"** button next to your cluster name.
   - Select **"Drivers"** under "Connect to your application".
   - Driver: `Python`, Version: `3.6 or later`.
   - Copy the connection string. It will look like this:
     `mongodb+srv://admin:<password>@aiskillgapcluster.abcde.mongodb.net/?retryWrites=true&w=majority&appName=AiSkillGapCluster`
   - **Replace `<password>`** with the exact password you created in step 3. 
   - **Save this full URL securely in your notepad.** This is your `MONGO_URL`.

---

## Step 2: Deploy the Backend API (Render.com)

We will use **Render Blueprints** to deploy the backend. This uses the `render.yaml` file to automatically configure the service as a **Docker** environment, ensuring Tesseract OCR is installed.

1. **Push your code:** Make sure you have pushed the latest code (including `render.yaml` and the `backend/Dockerfile`) to GitHub.
2. **Open Blueprints:** Go to your [Render Dashboard](https://dashboard.render.com/) and click on **"Blueprints"** in the top navigation bar.
3. **Connect Blueprint:** 
   - Click **"New Blueprint Instance"**.
   - Connect your `ai-skill-gap` repository.
4. **Configure Instance:**
   - **Service Group Name:** `ai-skill-gap` (or any name).
   - Render will detect the `render.yaml` file and show the `ai-skill-gap-api` service.
   - Click **"Update Existing Resources"** or **"Deploy"**.
5. **Set Environment Variables:**
   - Find your new `ai-skill-gap-api` service in the dashboard.
   - Go to **Environment**.
   - You will see the `SECRET_KEY` was generated for you. 
   - Manually add `MONGO_URL` and `FRONTEND_URL` as described in Step 4.
6. **Deploy:** Render will build your Docker image (installs Tesseract + Python deps). This takes roughly 5-8 minutes on first deploy.
7. **Get your API URL:** Once deployed, copy your backend URL from the service dashboard.

---

## Step 3: Deploy the Frontend UI (Vercel)

We will host the React frontend on Vercel, designed for absolute speed and ease.

1. **Sign Up:** Go to [Vercel](https://vercel.com/) and sign up with your GitHub account.
2. **Create Project:** Click **"Add New"** -> **"Project"**.
3. **Import Repository:** Find your `ai-skill-gap` repository in the list and click **"Import"**.
4. **Configure Project:**
   - **Project Name:** `ai-skill-gap`
   - **Framework Preset:** Vercel should auto-detect **Vite**.
   - **Root Directory:** Click the **"Edit"** button. Select the `frontend` folder and click "Save". (This tells Vercel our React code lives there).
5. **Add Environment Variables:**
   - Expand the "Environment Variables" section.
   - **Name:** `VITE_API_URL`
   - **Value:** `[Paste your Render Backend URL here]` (e.g., `https://ai-skill-gap-api-123.onrender.com`. Make sure there is NO trailing slash `/` at the end).
   - Click **"Add"**.
6. **Deploy:** Click the big **"Deploy"** button.
7. Vercel will build your UI and deploy it. This usually takes around 1-2 minutes.
8. **Get your Frontend URL:** Once the build finishes, it will show a congratulations screen with your live URL (e.g., `https://ai-skill-gap.vercel.app`). **Copy this URL to your notepad.**

---

## Step 4: Final Security Lock-down (Configure CORS)

Our API is currently live, but we need to tell the backend to trust requests coming specifically from our new Vercel frontend.

1. Go back to your **Render.com dashboard** and click on your `ai-skill-gap-api` web service.
2. On the left sidebar, click **"Environment"**.
3. Under Environment Variables, click "Add Environment Variable".
4. **Key:** `FRONTEND_URL`
5. **Value:** `[Paste your Vercel URL]` (e.g., `https://ai-skill-gap.vercel.app`. Remove any trailing slash `/`).
6. Click **"Save Changes"**.
7. Render will automatically restart your backend. Wait a minute for the new configuration to take effect.

---

## Step 5: Initialize the Production Database (Seed Data)

The deployment is live, but your production database is entirely empty. Let's pre-create the necessary collections and seed our Default Job Roles (like Data Scientist, ML Engineer, etc.) so users have roles to test against.

1. Open a terminal on your **local computer**.
2. Navigate to your backend directory:
   ```bash
   cd Ai-Skills-Gap-Analyzer/backend
   ```
3. Open your local `.env` file inside the `backend/` folder and comment out the local mongo URL, temporarily inserting the live Atlas URL:
   ```env
   # MONGO_URL=mongodb://localhost:27017/aigap
   MONGO_URL=mongodb+srv://admin:yoursecretpassword@aiskillgapcluster.abcde.mongodb.net/?retryWrites=true&w=majority&appName=AiSkillGapCluster
   ```
4. Run the database seed script:
   ```bash
   python seed.py
   ```
5. You should see logs indicating collections were created successfully and default roles were inserted.
6. **(Important Cleanup)** Revert your `.env` file back to `mongodb://localhost:27017/aigap` so your local development doesn't accidentally mess with production data.

---

## Step 6: Test the Production Build

1. Open your Vercel frontend URL in your browser.
2. Register a new user account. You should see a success message.
3. Log in.
4. Upload a sample Resume and analyze it against a Target Role.
5. If you receive your skills report, **Congratulations! Your system is officially live in production! 🎉**

### Troubleshooting Tips
* **Frontend says "Network Error" or cannot login:** Your `VITE_API_URL` on Vercel is incorrect, missing, or your Render backend is asleep (Render free tiers sleep after 15 minutes of inactivity and take ~50 seconds to wake up). 
* **Backend returns Error 500 when uploading resume:** Check the "Logs" tab on Render. It might be due to a malformed `MONGO_URL` or a missing SpaCy model (ensure `requirements.txt` has the `.whl` link we added for `en_core_web_sm`).
* **SpaCy error in Render Logs:** Make sure your `requirements.txt` specifically has the line `https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl` instead of just `spacy`.
