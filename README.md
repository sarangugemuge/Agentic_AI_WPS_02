# SkillSync — Evidence-Backed AI Skill Assessment Platform

SkillSync analyzes software engineering candidates by evaluating their real GitHub repositories against job descriptions using Google Gemini AI. Every demonstrated skill is backed by file-level citations, commit identifiers, and line-level code provenance. When candidates push new commits, SkillSync automatically re-evaluates the repository and records versioned assessment histories.

---

## Architecture Overview

```
                               ┌────────────────────────────────┐
                               │     SkillSync React Frontend   │
                               │  (Dashboard, History, Assess)  │
                               └───────────────┬────────────────┘
                                               │ HTTP / REST
                               ┌───────────────▼────────────────┐
                               │      FastAPI Backend API       │
                               │   (7-Step Assessment Engine)   │
                               └───────┬───────┬────────┬───────┘
                                       │       │        │
                     ┌─────────────────┘       │        └─────────────────┐
                     ▼                         ▼                          ▼
        ┌─────────────────────────┐ ┌────────────────────┐ ┌───────────────────────────┐
        │  GitHub REST API Client │ │  Gemini AI Engine  │ │  Owner-Controlled DB      │
        │  • Repo/Commit Fetcher  │ │  • Skill Extractor │ │  (SQLite / PostgreSQL)    │
        │  • Content Sanitizer    │ │  • Anti-Hallucinate│ │  • Multi-Version History  │
        │  • Tree/AST Inspector   │ │  • Gap Prioritizer │ │  • Automated Migrations   │
        └─────────────────────────┘ └────────────────────┘ └───────────────────────────┘
```

---

## Key Features

1. **AI-Powered Skill Extraction:** Extracts core and inferred technical requirements from arbitrary job postings.
2. **Repository Evidence Inspection:** Inspects GitHub repositories, reads source files, filters out vendor files (`node_modules`, binaries, `.env`), and parses commit histories.
3. **Strict Anti-Hallucination Guardrails:** Validates all model-generated citations against real files and commit SHAs; discards invented code snippets.
4. **Missing Evidence vs. Skill Deficiency:** Strictly distinguishes between "candidate lacks skill" and "skill not evidenced in this specific repository".
5. **Multi-Version Assessment History:** Preserves historical assessments across repository updates for longitudinal progress tracking.
6. **Automated Push Reassessment via Webhooks:** Dedicated GitHub Webhook receiver with HMAC-SHA256 signature verification and delivery deduplication.
7. **Interactive Assessment Dashboard:** Glassmorphism UI displaying skill matches, evidence code snippets, skill gaps, and learning pathways.

---

## Tech Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 19, Vite 8, CSS3 Design System (Glassmorphic) |
| **Backend** | Python 3.12, FastAPI 0.115+, Uvicorn, Pydantic v2 |
| **Database** | SQLite (Default with WAL mode) or PostgreSQL via SQLAlchemy 2.0 Async |
| **AI Engine** | Google Gemini (`google-genai` / `gemini-2.0-flash`) |
| **External APIs** | GitHub REST API v3, GitHub Webhooks (HMAC-SHA256) |
| **Lint & Build** | `oxlint` (Frontend Linter), Vite (Production Bundle) |

---

## Quick Start (Local Development)

### 1. Prerequisites
- **Node.js:** `>= 18` (Node 20+ recommended)
- **Python:** `>= 3.11` (Python 3.12 recommended)
- **Git**

### 2. Configure Environment
```bash
# Clone the repository
git clone <repository-url>
cd SkillSync

# Copy environment template
cp .env.example .env
```
Edit `.env` and set:
- `GEMINI_API_KEY`: Your Gemini API key from [Google AI Studio](https://aistudio.google.com/app/apikey).
- `GITHUB_TOKEN`: Personal Access Token from [GitHub Settings](https://github.com/settings/tokens) (`repo` read scope).
- `USE_TEST_DOUBLES=false` for live API calls, or `true` for offline development.

### 3. Start Backend Service
```bash
cd backend
python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
- API Base URL: `http://localhost:8000`
- Interactive Swagger UI: `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/api/health`

### 4. Start Frontend Client
In a separate terminal:
```bash
cd frontend
npm install
npm run dev
```
- Frontend UI: `http://localhost:5173`

---

## Verification & Testing

SkillSync includes an automated asynchronous test suite covering API routes, GitHub analysis, AI schemas, SQLite persistence, and webhook security:

```bash
# Run complete test suite (37 tests across Phases 3 to 9)
cd backend
.venv\Scripts\python.exe -m app.tests.run_tests

# Run frontend linting
cd ../frontend
npm run lint

# Run frontend production build
npm run build
```

---

## Documentation Directory

| Document | Purpose |
| :--- | :--- |
| [DEPLOYMENT.md](file:///d:/HACKTHON/SkillSync/DEPLOYMENT.md) | **Production Deployment Guide** (VPS, Nginx, Systemd, Docker, Cloud hosting) |
| [TEST_REPORT.md](file:///d:/HACKTHON/SkillSync/TEST_REPORT.md) | **Phase 9 QA & Security Audit Report** (37 passed tests, zero defects) |
| [backend/DATABASE.md](file:///d:/HACKTHON/SkillSync/backend/DATABASE.md) | **Database Architecture & PostgreSQL Migration Guide** |
| [backend/WEBHOOKS.md](file:///d:/HACKTHON/SkillSync/backend/WEBHOOKS.md) | **GitHub Webhook Setup & Simulation Guide** |
| [backend/API_CONTRACT.md](file:///d:/HACKTHON/SkillSync/backend/API_CONTRACT.md) | **REST API Contracts, Schemas & Endpoints** |

---

## Production Deployment Checklist

The application is completely prepared for independent manual deployment by the project owner. See [DEPLOYMENT.md](file:///d:/HACKTHON/SkillSync/DEPLOYMENT.md) for full walkthroughs.

1. **Hosting:** Deploy backend to a Python ASGI container/host (VPS, Render, Railway, Fly.io).
2. **Frontend:** Build static files (`npm run build`) and host on Nginx, Cloudflare Pages, Vercel, or Netlify.
3. **Database:** Mount persistent volume for SQLite or provision PostgreSQL (`DATABASE_URL=postgresql+asyncpg://...`).
4. **Environment Variables:** Set `USE_TEST_DOUBLES=false`, `APP_ENV=production`, `APP_SECRET_KEY`, `GEMINI_API_KEY`, and `GITHUB_TOKEN`.
5. **Webhooks:** Point GitHub Webhook to `https://yourdomain.com/api/webhooks/github` with secret `GITHUB_WEBHOOK_SECRET`.
