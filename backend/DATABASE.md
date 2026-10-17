# SkillSync — Owner-Controlled Database Guide

## 1. Overview & Architectural Principles

SkillSync utilizes an **owner-controlled database**. In accordance with global project rules and security standards:
- **No Third-Party Hosted Databases**: Never uses an AntiGravity-owned, vendor-managed, or silently provisioned cloud database.
- **Local Owner Ownership**: All application and assessment data resides in a local database file under the project owner's direct filesystem control.
- **Dialect Agnostic**: Engineered using async SQLAlchemy 2.0. The schema, constraints, and query layer use standard ANSI SQL abstractions, ensuring a seamless, approved transition to an owner-controlled PostgreSQL database without altering application business logic.
- **Zero Data Loss Migrations**: Automated, non-destructive schema migrations ensure all existing repositories, job profiles, assessments, citations, and findings are 100% preserved.

---

## 2. Database Location & Configuration

### Actual Database Location
- **Local SQLite File**: `d:\HACKTHON\SkillSync\backend\skillsync.db`
- **Driver**: `aiosqlite` (async SQLite driver)
- **Engine Concurrency**: Multi-threaded access configured with `check_same_thread=False` and safe async session pooling.

### Configuration via `DATABASE_URL`
The database connection string is read from the `DATABASE_URL` environment variable (or `.env` file). The system automatically normalizes standard connection strings:

| Target Database | Example `DATABASE_URL` | Normalized Driver |
| :--- | :--- | :--- |
| **Local SQLite (Default)** | `sqlite+aiosqlite:///./skillsync.db` | `aiosqlite` |
| **Standard SQLite** | `sqlite:///./skillsync.db` | Auto-normalized to `sqlite+aiosqlite` |
| **Owner PostgreSQL** | `postgresql://user:pass@localhost:5432/skillsync` | Auto-normalized to `postgresql+asyncpg` |
| **Async PostgreSQL** | `postgresql+asyncpg://user:pass@localhost:5432/skillsync` | `asyncpg` |

---

## 3. Entity Relationship Diagram (ERD)

```mermaid
erDiagram
    USERS {
        int id PK
        string username UK
        string email UK
        string full_name
        boolean is_active
        boolean is_owner
        datetime created_at
        datetime updated_at
    }

    REPOSITORIES {
        int id PK
        string github_owner
        string repo_name
        string default_branch
        string latest_commit_sha
        string webhook_secret_hash
        text description
        string language
        datetime created_at
        datetime updated_at
    }

    COMMIT_HISTORY {
        int id PK
        int repository_id FK
        string commit_sha
        text commit_message
        string author_name
        datetime committed_at
        datetime created_at
    }

    JOB_PROFILES {
        int id PK
        string title
        string company_context
        text raw_description
        text extracted_skills_json
        datetime created_at
    }

    JOB_SKILL_REQUIREMENTS {
        int id PK
        int job_profile_id FK
        string skill_name
        string category
        string importance
        datetime created_at
    }

    ASSESSMENTS {
        int id PK
        int repository_id FK
        int job_profile_id FK
        int version
        string commit_sha
        float overall_score
        text summary
        string trigger_event
        string status
        text error_message
        datetime created_at
    }

    SKILL_FINDINGS {
        int id PK
        int assessment_id FK
        string skill_name
        string category
        string status
        float confidence_score
        text rationale
        text limitations
        text recommended_next_steps
    }

    EVIDENCE_CITATIONS {
        int id PK
        int skill_finding_id FK
        string file_path
        int start_line
        int end_line
        string commit_sha
        text code_snippet
        text context_explanation
    }

    SKILL_GAPS {
        int id PK
        int assessment_id FK
        string skill_name
        string category
        string gap_severity
        text description
        text recommended_action
        int priority
        datetime created_at
    }

    REPOSITORIES ||--o{ COMMIT_HISTORY : "tracks revisions"
    REPOSITORIES ||--o{ ASSESSMENTS : "evaluated by"
    JOB_PROFILES ||--o{ JOB_SKILL_REQUIREMENTS : "defines required skills"
    JOB_PROFILES ||--o{ ASSESSMENTS : "evaluated against"
    ASSESSMENTS ||--o{ SKILL_FINDINGS : "produces"
    ASSESSMENTS ||--o{ SKILL_GAPS : "identifies"
    SKILL_FINDINGS ||--o{ EVIDENCE_CITATIONS : "verified by"
```

---

## 4. Entity Specifications & Indexes

### 1. `users`
- Stores workspace owners and authenticated team members.
- **Indexes**: `ix_users_username` (unique), `ix_users_email` (unique).

### 2. `repositories`
- Tracks GitHub repositories registered for skill evaluation.
- **Indexes & Constraints**: `uq_repository_owner_repo` (`github_owner`, `repo_name`), `ix_repositories_owner_name`.

### 3. `commit_history`
- Records immutable Git commit revisions, timestamps, author names, and messages for strict assessment provenance.
- **Indexes & Constraints**: `uq_repo_commit` (`repository_id`, `commit_sha`), `ix_commit_history_repo_committed`.

### 4. `job_profiles`
- Stores job listings, titles, companies, and raw requirements text.
- Maintains `extracted_skills_json` for backward compatibility.

### 5. `job_skill_requirements`
- Normalized individual required skills per job profile.
- **Columns**: `importance` ("required", "preferred", "inferred"), `category`, `skill_name`.
- **Indexes**: `ix_job_skills_profile_skill` (`job_profile_id`, `skill_name`).

### 6. `assessments`
- Represents a discrete assessment run evaluating a repository at a specific revision against a job profile.
- **Multi-version tracking**: Sequentially increments `version` for the same `(repository_id, job_profile_id)`.
- **Provenance**: Records `commit_sha`, `created_at` timestamp, and `trigger_event`.
- **Indexes**: `ix_assessments_repo_job`, `ix_assessments_repo_version`, `ix_assessments_created_at`, `ix_assessments_status`.

### 7. `skill_findings`
- Assessment outcome for each skill (`demonstrated`, `partially_demonstrated`, `not_found`, `manual_verification`).
- Includes confidence score, rationale, limitations, and recommended next steps.
- **Indexes**: `ix_skill_findings_assessment_id`.

### 8. `evidence_citations`
- Traceable citations linking findings to physical repository files (`file_path`, `start_line`, `end_line`, `commit_sha`, `code_snippet`).
- Disallows invented paths or hallucinations.
- **Indexes**: `ix_evidence_citations_skill_finding_id`.

### 9. `skill_gaps`
- Dedicated entity tracking actionable deficits for skills evaluated as `not_found` or `partially_demonstrated`.
- **Attributes**: `gap_severity`, `priority` (1 = highest priority), `description`, `recommended_action`.
- **Indexes**: `ix_skill_gaps_assessment_priority` (`assessment_id`, `priority`).

---

## 5. Migration Strategy

Migrations are managed programmatically via [`app.core.migrations`](file:///d:/HACKTHON/SkillSync/backend/app/core/migrations.py).

### Safety Guarantees:
1. **Zero Data Loss**: Existing records in `repositories`, `job_profiles`, `assessments`, `skill_findings`, and `evidence_citations` are never dropped or reset.
2. **Idempotent Column Additions**: Inspects SQLite `PRAGMA table_info` before attempting `ALTER TABLE ... ADD COLUMN`.
3. **Idempotent Indexes**: Uses `CREATE INDEX IF NOT EXISTS`.
4. **Automatic Entity Backfilling**:
   - Converts legacy JSON skills in `job_profiles` into normalized `job_skill_requirements` rows.
   - Backfills missing `skill_gaps` for legacy assessments from non-demonstrated findings.
   - Sets default `version=1` for pre-existing assessment runs.

To execute migrations manually:
```powershell
d:\HACKTHON\SkillSync\backend\.venv\Scripts\python.exe -c "import asyncio; from app.core.database import init_db; asyncio.run(init_db())"
```

---

## 6. Backup & Restore Procedures

### A. Local SQLite Backup

#### Method 1: Hot Online Backup (Recommended)
Performs an active, non-blocking backup while the application is running:
```powershell
sqlite3 d:\HACKTHON\SkillSync\backend\skillsync.db ".backup 'd:\HACKTHON\SkillSync\backend\skillsync_backup.db'"
```

#### Method 2: SQL Text Dump
Creates a portable, human-readable SQL dump:
```powershell
sqlite3 d:\HACKTHON\SkillSync\backend\skillsync.db .dump > d:\HACKTHON\SkillSync\backend\skillsync_dump.sql
```

#### Method 3: Cold File Copy
When the FastAPI application is stopped:
```powershell
Copy-Item "d:\HACKTHON\SkillSync\backend\skillsync.db" -Destination "d:\HACKTHON\SkillSync\backend\skillsync_backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').db"
```

### B. SQLite Restore

To restore from a backup:
1. Stop the backend server.
2. Replace `skillsync.db` with the verified backup file:
```powershell
Copy-Item "d:\HACKTHON\SkillSync\backend\skillsync_backup.db" -Destination "d:\HACKTHON\SkillSync\backend\skillsync.db" -Force
```
3. Start the backend service. Migrations will verify schema integrity automatically.

---

## 7. Migration to Owner's PostgreSQL (Future Phase)

When transitioning to an owner-managed PostgreSQL instance:
1. **Provision PostgreSQL Database**:
   ```sql
   CREATE DATABASE skillsync;
   CREATE USER skillsync_user WITH ENCRYPTED PASSWORD 'your_secure_password';
   GRANT ALL PRIVILEGES ON DATABASE skillsync TO skillsync_user;
   ```
2. **Configure `.env`**:
   ```env
   DATABASE_URL=postgresql+asyncpg://skillsync_user:your_secure_password@localhost:5432/skillsync
   ```
3. **Export and Load Data**:
   Use standard SQL dumps or SQLAlchemy transfer scripts to migrate existing records.
4. **Start Application**:
   `app.core.migrations` will automatically construct all tables, constraints, foreign keys, and indexes on the PostgreSQL instance.
