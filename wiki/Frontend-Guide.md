# Frontend Guide

The frontend is a single-page application built with **React 18**, **Vite**, **Tailwind CSS**, and **Framer Motion** for animated page transitions.

---

## Tech Stack

| Library | Purpose |
|---------|---------|
| React 18 | UI framework |
| Vite | Dev server & bundler |
| React Router v6 | Client-side routing |
| Tailwind CSS | Utility-first styling |
| Framer Motion (`motion/react`) | Page transition animations |
| Recharts | Charts (readiness score, market trends) |
| Axios / `fetch` | API communication |

---

## Project Structure

```
frontend/
├── src/
│   ├── main.jsx            # React entry — mounts <App /> to #root
│   ├── App.jsx             # BrowserRouter + AnimatePresence + route definitions
│   ├── index.css           # Tailwind base styles
│   │
│   ├── pages/
│   │   ├── LandingPage.jsx     # /
│   │   ├── LoginPage.jsx       # /login
│   │   ├── RegisterPage.jsx    # /register
│   │   ├── UploadPage.jsx      # /upload  (protected)
│   │   ├── DashboardPage.jsx   # /dashboard  (protected)
│   │   └── ProfilePage.jsx     # /profile  (protected)
│   │
│   ├── components/
│   │   ├── ProtectedRoute.jsx  # Redirects unauthenticated users to /login
│   │   └── …                  # Other shared UI components
│   │
│   ├── context/
│   │   └── AuthContext.jsx     # Global auth state (user, token, login/logout helpers)
│   │
│   └── api/
│       └── …                  # Centralised API request functions
│
├── public/                 # Static assets served as-is
├── index.html              # Vite entry HTML
├── package.json
├── vite.config.js
└── eslint.config.js
```

---

## Routing

Routes are defined in `App.jsx` using React Router v6. `AnimatePresence` wraps the routes to animate page transitions.

| Path | Component | Auth Required |
|------|-----------|:---:|
| `/` | `LandingPage` | ❌ |
| `/login` | `LoginPage` | ❌ |
| `/register` | `RegisterPage` | ❌ |
| `/upload` | `UploadPage` | ✅ |
| `/dashboard` | `DashboardPage` | ✅ |
| `/profile` | `ProfilePage` | ✅ |

`ProtectedRoute` checks `AuthContext` for a valid user; unauthenticated visitors are redirected to `/login`.

---

## Pages

### `/` — Landing Page
- Hero banner with tagline and "Get Started" CTA.
- Overview of platform features.

### `/login` — Login
- Email + password form.
- On success, stores the JWT access token in `AuthContext` and navigates to `/upload`.

### `/register` — Register
- Name, email, password form.
- On success, auto-logs in the new user.

### `/upload` — Resume Upload _(protected)_
- Drag-and-drop or click-to-browse resume upload (PDF, DOCX, TXT).
- Role selector dropdown (populated from `GET /api/v1/jobs/roles`).
- Submits `POST /api/v1/analyze/resume` and polls `GET /api/v1/jobs/{job_id}` until complete.
- Navigates to `/dashboard` with the analysis result.

### `/dashboard` — Analysis Dashboard _(protected)_
- **Job Readiness Score** — circular progress bar.
- **Detected Skills** — tag list.
- **Missing Skills** — ranked tag list.
- **Market Trends** — Recharts bar chart from `GET /api/v1/market/demand`.
- **Learning Roadmap** — weekly timeline.
- **Interview Questions** — collapsible Q&A list.

### `/profile` — User Profile _(protected)_
- Account details.
- XP and level progress.
- Badge catalogue (earned + locked).
- Analysis history.

---

## Authentication Flow

```
AuthContext (React Context)
  ├─ user       { id, email, name }
  ├─ token      JWT access token (stored in memory)
  ├─ login()    POST /api/v1/auth/login → set user + token
  ├─ logout()   POST /api/v1/auth/logout → clear user + token
  └─ refresh()  POST /api/v1/auth/refresh → obtain new token using cookie
```

The refresh-token is stored as an **HttpOnly cookie** by the backend — the frontend never touches it directly. `AuthContext` automatically calls `refresh()` when the access token is close to expiry (15-minute TTL).

---

## Environment Variables

Create `frontend/.env.local` (git-ignored):

```env
VITE_API_URL=http://127.0.0.1:8000
```

In production (Vercel), set:
```
VITE_API_URL=https://your-backend.onrender.com
```

> **Important:** Do NOT include a trailing slash.

---

## Build & Deploy

```bash
# Development
npm run dev         # → http://localhost:5173

# Production build
npm run build       # outputs to dist/
npm run preview     # preview the production build locally

# Lint
npm run lint
```

Vercel auto-detects Vite and sets the root directory to `frontend/` (configure in Vercel project settings).
