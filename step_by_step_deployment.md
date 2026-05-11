# The Ultimate Step-by-Step Production Deployment Guide

This comprehensive guide will walk you through every single click and command required to host the **AI Skill Gap Analyzer** from scratch. 
We will use entirely free-tier services to host this platform. Our production stack involves:
1. **Source Code:** GitHub
2. **Database:** MongoDB Atlas (Cloud)
3. **Backend API:** Render.com (Free) | **AWS App Runner** (Easiest) | **AWS EC2** (Full Control)
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

We will deploy our FastAPI python code to Render.com.

1. **Sign Up:** Go to [Render.com](https://render.com/) and create a free account linked with your GitHub.
2. **Create Service:** Click the **"New +"** button in the top right and select **"Web Service"**.
3. **Connect Repository:** 
   - Choose **"Build and deploy from a Git repository"**.
   - Click "Next", authorize GitHub if prompted, and select your `ai-skill-gap` repository.
4. **Configure the Web Service:** Fill in the following exact details:
   - **Name:** `ai-skill-gap-api` (or any unique name).
   - **Region:** Choose the region closest to your MongoDB database (e.g., Singapore or US East).
   - **Branch:** `main`
   - **Root Directory:** Type exactly `backend` (This tells Render our Python code is in the `/backend` folder).
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker`
   - **Instance Type:** Select the **Free** tier (0.1 CPU, 512 MB RAM).
5. **Add Environment Variables:**
   - Scroll down to the **"Environment Variables"** block.
   - Click "Add Environment Variable".
   - **Key 1:** `MONGO_URL` | **Value 1:** `[Paste your MongoDB URL]`
   - **Key 2:** `GEMINI_API_KEY` | **Value 2:** `[Paste your Gemini Key]`
   - *(Optional but recommended)* **Key 3:** `PYTHON_VERSION` | **Value 3:** `3.10.0`
6. **Deploy:** Click **"Create Web Service"**.
7. **Monitor the Build:** Render will now download your code, install dependencies, and start the server. You can watch the console logs. It will take roughly 3-5 minutes.
8. **Get your API URL:** Once deployed, you will see a green "Live" badge. In the top left, under your service name, copy your backend URL (e.g., `https://ai-skill-gap-api-123.onrender.com`). **Save this to your notepad.**

---

## Step 2 (Option B): Professional Deployment on AWS (App Runner)

If you find Render.com's free tier too slow (it sleeps after inactivity) or need more power for the ML models, **AWS App Runner** is the recommended professional choice. It is a fully managed service that handles scaling, security, and load balancing.

### Why AWS App Runner?
*   **No Sleep:** Your API is always on (unlike Render free tier).
*   **Performance:** Faster processing for PDF parsing and ML analysis.
*   **Docker-powered:** We use a `Dockerfile` to ensure `Tesseract OCR` and `SpaCy` work perfectly every time.

### Deployment Steps:
1.  **Sign Up:** Create an [AWS Account](https://aws.amazon.com/).
2.  **Go to App Runner:** Search for "App Runner" in the AWS Console search bar.
3.  **Create Service:** Click **"Create service"**.
4.  **Source and Deployment:**
    - **Repository type:** Source code repository.
    - **Connect to GitHub:** Link your account and select the `ai-skill-gap` repository.
    - **Deployment settings:** Choose **Automatic** (so it redeploys whenever you push code).
5.  **Configure Build:**
    - **Configuration file:** Choose **"Configure all settings here"**.
    - **Runtime:** Choose **"Dockerfile"**. (We've already created this in the `backend/` folder).
    - **Port:** `8080`.
6.  **Configure Service:**
    - **Service Name:** `ai-skills-analyzer-backend`.
    - **Virtual CPU & Memory:** Select **1 vCPU and 2 GB RAM** (Minimum recommended for the sentence-transformers model).
    - **Environment Variables:**
        - Add `MONGO_URL` -> `[Your MongoDB String]`.
        - Add `GEMINI_API_KEY` -> `[Your Gemini API Key from AI Studio]`.
        - Add `ENVIRONMENT` -> `production`.
7.  **Review & Create:** Click **"Create & Deploy"**. 
    - AWS will now build your container. This takes 5-7 minutes as it installs heavy ML libraries.
8.  **Get your URL:** Once the status is "Running", copy the **Default domain** URL (e.g., `https://xxxxxx.us-east-1.awsapprunner.com`). Use this as your `VITE_API_URL` in the next step.

---

## Step 2 (Option C): Full Control Deployment on AWS EC2 (VM)

If you prefer using a Virtual Machine (VM), you can use **AWS EC2**. Since you have $140 credits, we will use a powerful enough machine to run your AI models.

### ⚠️ IMPORTANT: Instance Selection
Do **NOT** use the `t2.micro` (Free Tier). It only has 1GB of RAM and your AI models will crash it.
Instead, use **`t3.small`** (2GB RAM) or **`t3.medium`** (4GB RAM). Your credits will easily cover this for several months.

### Deployment Steps:
1.  **Launch Instance:**
    *   Go to **EC2 Dashboard** -> **Launch Instance**.
    *   **Name:** `ai-gap-backend-server`.
    *   **OS:** `Ubuntu 22.04 LTS` (recommended).
    *   **Instance Type:** `t3.medium` (4GB RAM - safest for ML).
    *   **Key Pair:** Create a new key pair, download the `.pem` file, and keep it safe.
    *   **Network Settings:** 
        *   Allow SSH (Port 22).
        *   Allow HTTP (Port 80) and HTTPS (Port 443).
2.  **Edit Security Group:**
    *   Once launched, go to the instance "Security" tab.
    *   Click the Security Group ID -> **Edit Inbound Rules**.
    *   Add a rule: **Custom TCP**, Port: `8080`, Source: `Anywhere (0.0.0.0/0)`.
3.  **SSH into your Server:**
    ```bash
    ssh -i your-key.pem ubuntu@your-public-ip
    ```
4.  **Install Docker on the VM:**
    ```bash
    sudo apt-get update
    sudo apt-get install -y docker.io
    sudo systemctl start docker
    sudo usermod -aG docker ubuntu
    # Log out and log back in for permissions to take effect
    exit
    ssh -i your-key.pem ubuntu@your-public-ip
    ```
5.  **Clone and Run:**
    ```bash
    git clone https://github.com/Ayusohm432/AI-Skills-Gap-Analyzer.git
    cd ai-skill-gap/backend
    # Create your .env file
    nano .env
    # (Paste your MONGO_URL, GEMINI_API_KEY, etc. Press Ctrl+O, Enter, Ctrl+X)
    
    # Build and Run
    docker build -t ai-gap-backend .
    docker run -d --name backend -p 8080:8080 --env-file .env ai-gap-backend
    ```
6.  **Get your URL:** Your backend is now at `http://[YOUR-PUBLIC-IP]:8080`.

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
   - **Value:** `[Paste your AWS or Render Backend URL here]` (e.g., `http://1.2.3.4:8080`. Make sure there is NO trailing slash `/` at the end).
   - Click **"Add"**.
6. **Deploy:** Click the big **"Deploy"** button.
7. Vercel will build your UI and deploy it. This usually takes around 1-2 minutes.
8. **Get your Frontend URL:** Once the build finishes, it will show a congratulations screen with your live URL (e.g., `https://ai-skill-gap.vercel.app`). **Copy this URL to your notepad.**

---

## Step 4: Final Security Lock-down (Configure CORS)

Our API is currently live, but we need to tell the backend to trust requests coming specifically from our new Vercel frontend.

1. **If using Render:** Go to your Render dashboard -> Environment -> Add `FRONTEND_URL`.
2. **If using EC2:** Re-run your Docker container with the added variable:
   ```bash
   docker stop backend && docker rm backend
   docker run -d --name backend -p 8080:8080 -e FRONTEND_URL=https://your-vercel-app.vercel.app --env-file .env ai-gap-backend
   ```

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
* **Frontend says "Network Error" or cannot login:** Your `VITE_API_URL` on Vercel is incorrect, missing, or your backend is not accessible (check Security Groups on EC2 or "Logs" on Render).
* **Backend returns Error 500 when uploading resume:** Check the logs. Usually due to a malformed `MONGO_URL` or missing system dependencies (handled automatically by our Dockerfile).
