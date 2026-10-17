# SkillSync — Manual Production Deployment & Operations Guide

This guide is designed for the project owner to independently configure, provision, and deploy SkillSync into production.

---

## 1. Hosting Architecture & Requirements

SkillSync is composed of two decoupled tiers:
1. **Frontend:** React 19 + Vite SPA (Static site: HTML/CSS/JS).
2. **Backend:** FastAPI + Uvicorn ASGI Application (Python 3.11+).
3. **Database:** Owner-controlled persistent database (SQLite on persistent volume or PostgreSQL).

```
                      ┌────────────────────────────────────────┐
                      │              Web User                  │
                      └──────────────────┬─────────────────────┘
                                         │ HTTPS
                      ┌──────────────────▼─────────────────────┐
                      │           Reverse Proxy                │
                      │       (Nginx / Caddy / Cloudflare)     │
                      └──────────┬──────────────────┬──────────┘
                                 │                  │
                     / (Static Assets)         /api (API Proxy)
                                 │                  │
                ┌────────────────▼────────┐  ┌──────▼──────────────────┐
                │     Frontend Host       │  │      Backend Service    │
                │  (Vercel / Netlify /    │  │  (Docker / VPS / Render │
                │   S3 / Nginx / Caddy)   │  │   Fly.io / Railway)     │
                └─────────────────────────┘  └──────┬──────────────────┘
                                                    │
                                   ┌────────────────┴──────────────────┐
                                   ▼                                   ▼
                       ┌───────────────────────┐           ┌───────────────────────┐
                       │  SQLite / PostgreSQL  │           │   External APIs:      │
                       │   Persistent Database │           │  • GitHub REST API    │
                       └───────────────────────┘           │  • Google Gemini API  │
                                                           └───────────────────────┘
```

### Minimum Resource Requirements
| Component | Minimum Specs | Recommended Specs |
| :--- | :--- | :--- |
| **Backend CPU** | 1 vCPU (shared) | 2 vCPUs |
| **Backend Memory** | 512 MB RAM | 1 GB to 2 GB RAM |
| **Storage** | 1 GB Persistent Volume | 10 GB+ SSD for SQLite and logs |
| **Network** | Outbound HTTPS (GitHub + Google Gemini) | Inbound HTTPS on Port 443 |

---

## 2. Environment Variables Specification

Store all production secrets in the hosting provider's secure secret manager or in an uncommitted `.env` file with restrictive filesystem permissions (`chmod 600 .env`).

### Backend Environment Variables (`backend/.env`)

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `APP_ENV` | **Yes** | `development` | Set to `production` in live environments. Masks verbose debug logs and internal details. |
| `APP_HOST` | **Yes** | `0.0.0.0` | Bind host IP. Use `0.0.0.0` for Docker/containers. |
| `APP_PORT` | **Yes** | `8000` | HTTP listen port. |
| `APP_SECRET_KEY` | **Yes** | — | Cryptographically random string (min 32 characters). Used for session signing. |
| `DATABASE_URL` | **Yes** | `sqlite+aiosqlite:///./skillsync.db` | Async SQLAlchemy database URL. For PostgreSQL: `postgresql+asyncpg://user:pass@host:5432/dbname`. |
| `GITHUB_TOKEN` | Optional* | `""` | GitHub Personal Access Token (classic with `repo` or fine-grained read). Highly recommended to avoid rate limits (60/hr unauthenticated vs 5,000/hr authenticated). |
| `GITHUB_WEBHOOK_SECRET`| Optional* | `""` | Secret configured in GitHub repository Webhook settings. Enables HMAC-SHA256 signature verification. |
| `GEMINI_API_KEY` | **Yes** | `""` | Google Gemini API Key from Google AI Studio. |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Gemini model tag. Recommended: `gemini-2.0-flash` for high throughput, low latency, and structured outputs. |
| `USE_TEST_DOUBLES` | **Yes** | `false` | **MUST BE `false` IN PRODUCTION** so the engine connects to live GitHub and Gemini APIs. |
| `GITHUB_TIMEOUT_SECONDS`| No | `10.0` | Outbound timeout for GitHub REST API requests. |
| `AI_TIMEOUT_SECONDS` | No | `30.0` | Outbound timeout for Gemini inference requests. |
| `CORS_ORIGINS` | **Yes** | `http://localhost:5173` | Comma-separated list of allowed frontend origins (e.g. `https://skillsync.yourdomain.com`). |

### Frontend Environment Variables (`frontend/.env.production`)

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `VITE_API_BASE_URL` | Optional | `""` (uses `/api`) | If frontend is on a different domain than backend, set to `https://api.yourdomain.com/api`. If reverse-proxied under same domain, leave empty. |

---

## 3. Database Setup, Migrations & Maintenance

### Option A: SQLite (Default — Single-Node / VPS / Container with Volume)
SkillSync automatically initializes SQLite on boot using `backend/app/core/migrations.py`.
- **Database File:** Configured by `DATABASE_URL=sqlite+aiosqlite:////data/skillsync.db`.
- **Persistent Volume:** If deploying to Render, Fly.io, or Railway, mount a persistent disk to the directory containing `skillsync.db` (e.g., `/data`).
- **Pragmas Enabled Automatically:**
  - `journal_mode = WAL` (Write-Ahead Logging for high-concurrency read operations).
  - `foreign_keys = ON` (Referential integrity enforcement).
  - `synchronous = NORMAL` (Optimized durability balance).

### Option B: PostgreSQL (Recommended for Distributed / High-Volume Deployments)
1. Provision a PostgreSQL instance (AWS RDS, Supabase, Neon, Railway Postgres).
2. Install `asyncpg` in the backend virtualenv or container:
   ```bash
   pip install asyncpg==0.30.0
   ```
3. Set the database URL:
   ```bash
   DATABASE_URL=postgresql+asyncpg://db_user:db_password@db_host:5432/skillsync_db
   ```
4. Start the backend. The migration manager in `backend/app/core/migrations.py` will inspect the schema, create missing tables, and register the current schema version automatically.

### Backup and Disaster Recovery

#### SQLite Backup Procedure
SQLite supports safe online backups without interrupting active operations:
```bash
# Safely snapshot the SQLite database using sqlite3 CLI
sqlite3 /data/skillsync.db ".backup '/backups/skillsync_$(date +%Y%m%d_%H%M%S).db'"
```

#### PostgreSQL Backup Procedure
```bash
# Dump compressed PostgreSQL database
pg_dump -h db_host -U db_user -Fc skillsync_db > "/backups/skillsync_$(date +%Y%m%d_%H%M%S).dump"
```

#### Restoration Procedure
1. Stop backend service.
2. Restore database file or dump:
   ```bash
   # SQLite:
   cp /backups/skillsync_YYYYMMDD_HHMMSS.db /data/skillsync.db
   # PostgreSQL:
   pg_restore -h db_host -U db_user -d skillsync_db /backups/skillsync_YYYYMMDD_HHMMSS.dump
   ```
3. Restart backend service.

---

## 4. Manual Deployment Walkthroughs

### Walkthrough 1: Unified VPS Deployment (Ubuntu / Debian + Nginx + Systemd)

#### Step 1: System Preparation
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nodejs npm nginx git
git clone <your-repository-url> /opt/skillsync
cd /opt/skillsync
```

#### Step 2: Build the Frontend
```bash
cd /opt/skillsync/frontend
npm install --production=false
npm run build
# Built files are placed in /opt/skillsync/frontend/dist
```

#### Step 3: Configure Backend Virtualenv & Dependencies
```bash
cd /opt/skillsync/backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

#### Step 4: Configure Production Secrets
Create `/opt/skillsync/backend/.env`:
```ini
APP_ENV=production
APP_HOST=127.0.0.1
APP_PORT=8000
APP_SECRET_KEY=generate_with_openssl_rand_hex_32
DATABASE_URL=sqlite+aiosqlite:////opt/skillsync/backend/skillsync.db
GITHUB_TOKEN=ghp_your_personal_access_token
GITHUB_WEBHOOK_SECRET=your_configured_webhook_secret
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL=gemini-2.0-flash
USE_TEST_DOUBLES=false
CORS_ORIGINS=https://skillsync.yourdomain.com
```

#### Step 5: Configure Systemd Service
Create `/etc/systemd/system/skillsync.service`:
```ini
[Unit]
Description=SkillSync FastAPI Backend
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/skillsync/backend
EnvironmentFile=/opt/skillsync/backend/.env
ExecStart=/opt/skillsync/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable skillsync
sudo systemctl start skillsync
```

#### Step 6: Configure Nginx & SSL (Certbot)
Create `/etc/nginx/sites-available/skillsync`:
```nginx
server {
    server_name skillsync.yourdomain.com;

    # Frontend Static Files
    root /opt/skillsync/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # Backend API Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 90s;
    }

    # Swagger Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_set_header Host $host;
    }
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
        proxy_set_header Host $host;
    }
}
```

Enable site and acquire Let's Encrypt SSL:
```bash
sudo ln -s /etc/nginx/sites-available/skillsync /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo certbot --nginx -d skillsync.yourdomain.com
```

---

### Walkthrough 2: Docker Container Deployment

Create a `Dockerfile` in `backend/` for containerized hosting (Render, Railway, Fly.io, Cloud Run):

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Build and test locally before deploying:
```bash
docker build -t skillsync-backend:latest ./backend
docker run -p 8000:8000 --env-file backend/.env skillsync-backend:latest
```

---

## 5. Webhook Setup on GitHub

To enable automated reassessment when candidates push new code commits:

1. Navigate to your target repository on GitHub: **Settings -> Webhooks -> Add webhook**.
2. **Payload URL:** `https://skillsync.yourdomain.com/api/webhooks/github`
3. **Content type:** `application/json`
4. **Secret:** Provide the string matching `GITHUB_WEBHOOK_SECRET` in your backend configuration.
5. **Events to trigger:** Select **"Just the push event"**.
6. Check **Active** and click **Add webhook**.
7. GitHub will send a test `ping` event. SkillSync will respond with `200 OK` and log:
   `[Webhook] Received ping event from GitHub. Webhook configuration verified.`

---

## 6. External Service Dependencies, Quotas & Costs

### 1. Google Gemini API
- **API Surface:** `gemini-2.0-flash`
- **Pricing:**
  - Free Tier: Up to 15 Requests Per Minute (RPM), 1,500 Requests Per Day (RPD).
  - Pay-as-you-go: ~$0.10 / 1M input tokens, ~$0.40 / 1M output tokens.
  - Typical Skill Assessment: ~3,000 input tokens + ~800 output tokens = **~$0.0006 per assessment**.
- **Rate Limits:** Keep concurrent requests below quota. The orchestrator uses safe timeout handling (`AI_TIMEOUT_SECONDS=30.0`).

### 2. GitHub REST API v3
- **Unauthenticated Rate Limit:** 60 requests/hour per IP.
- **Authenticated Rate Limit (`GITHUB_TOKEN`):** 5,000 requests/hour per token.
- **Cost:** Free.

---

## 7. Security & Hardening Checklist for Production

- [ ] `USE_TEST_DOUBLES=false` is set in production.
- [ ] `APP_ENV=production` is set (masks internal tracebacks).
- [ ] Strong `APP_SECRET_KEY` generated (`openssl rand -hex 32`).
- [ ] `.env` file permissions set to `600` and owned by execution user (`www-data`).
- [ ] HTTPS enabled on all public endpoints with valid SSL certificate.
- [ ] `CORS_ORIGINS` strictly limited to authorized domain names.
- [ ] GitHub Webhook Secret configured with HMAC-SHA256 verification.
- [ ] Persistent storage backup routine configured (daily cron for SQLite or Postgres dump).
- [ ] Database storage volume mounted on persistent disk.
