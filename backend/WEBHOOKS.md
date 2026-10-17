# SkillSync — GitHub Webhooks & Automated Reassessment Guide

## 1. Overview & Architectural Principles

SkillSync supports automated, push-triggered skill reassessments via GitHub Webhooks. When an engineer pushes new code, tests, or architecture improvements to a tracked repository, SkillSync automatically reruns the evaluation pipeline, increments the assessment version, and updates the candidate's skill profile.

### Core Security & Reliability Guarantees:
1. **HMAC-SHA256 Signature Verification**: Every webhook request is verified using the configured secret (`GITHUB_WEBHOOK_SECRET`). Requests with missing, mismatched, or tampered signatures are rejected immediately with HTTP 401 Unauthorized.
2. **Delivery Deduplication & Idempotency**: Every GitHub delivery ID (`X-GitHub-Delivery`) is recorded in the `webhook_deliveries` database table. Redundant or retried deliveries are identified and return HTTP 200 without executing duplicate background assessment jobs.
3. **Concurrency Locking**: A repository-level lock (`asyncio.Lock`) prevents race conditions if multiple pushes or webhooks arrive simultaneously for the same codebase.
4. **Non-Destructive Versioning**: Reassessments sequentially increment the version identifier (`v1` $\rightarrow$ `v2` $\rightarrow$ `v3`), updating `commit_sha` and provenance timestamps while preserving all previous assessment history intact.
5. **Branch Filtering**: Reassessments only execute on pushes to the repository's registered default branch (e.g., `main`); pushes to experimental feature branches or branch deletion events are safely ignored.

---

## 2. Webhook Endpoint Specification

- **Endpoint**: `POST /api/webhooks/github`
- **Supported Events**:
  - `ping`: GitHub initial webhook handshake. Responds with `{"status": "ok", "message": "pong"}`.
  - `push`: Code push to default branch. Triggers automated versioned reassessment.
- **Required Headers**:
  - `X-GitHub-Event`: Event name (`push`, `ping`)
  - `X-GitHub-Delivery`: Unique GUID for the delivery
  - `X-Hub-Signature-256`: Signature formatted as `sha256=<hex_digest>`
  - `Content-Type`: `application/json`

---

## 3. Local Testing with Simulated Events

In accordance with project security restrictions, local testing does not expose public tunnels (e.g. ngrok) or make unapproved external requests. Instead, a dedicated cryptographic test runner simulates realistic, signed GitHub webhooks locally.

### A. Run Automated Webhook Tests (32 Passed)
Execute the complete test suite covering signature verification, ping handling, delivery deduplication, branch filtering, and multi-version persistence:
```powershell
d:\HACKTHON\SkillSync\backend\.venv\Scripts\python.exe -m app.tests.run_tests
```

### B. Interactive Simulation via CLI Tool

SkillSync includes [`app/scripts/simulate_webhook.py`](file:///d:/HACKTHON/SkillSync/backend/app/scripts/simulate_webhook.py).

#### 1. Simulate GitHub `ping` Handshake:
```powershell
d:\HACKTHON\SkillSync\backend\.venv\Scripts\python.exe app\scripts\simulate_webhook.py --event ping
```
*Expected Output: HTTP 200 with `{"status": "ok", "message": "pong"}`.*

#### 2. Simulate Push Event & Trigger Automated Reassessment:
```powershell
d:\HACKTHON\SkillSync\backend\.venv\Scripts\python.exe app\scripts\simulate_webhook.py --event push --owner octocat --repo Hello-World
```
*Expected Output: HTTP 200 with `{"status": "reassessed", "assessment_id": <id>, "version": <v>, "commit_sha": "..."}`.*

#### 3. Test Signature Tampering Rejection:
```powershell
d:\HACKTHON\SkillSync\backend\.venv\Scripts\python.exe app\scripts\simulate_webhook.py --event push --tamper
```
*Expected Output: HTTP 401 Unauthorized with `{"detail": "Invalid webhook signature."}`.*

#### 4. Test Duplicate Delivery Idempotency:
Run the simulation with an identical delivery ID; SkillSync immediately detects the prior delivery and returns:
```json
{
  "status": "duplicate",
  "message": "Delivery '...' already processed."
}
```

---

## 4. Procedure for Project Owner to Configure Real GitHub Webhooks

When deploying SkillSync to production or exposing it via an owner-approved domain/tunnel:

### Step 1: Set Webhook Secret in Environment
Ensure `.env` contains your secure webhook secret:
```env
GITHUB_WEBHOOK_SECRET=your_super_secret_webhook_key_here
```

### Step 2: Configure Webhook in GitHub Repository
1. Navigate to your repository on GitHub: `https://github.com/<owner>/<repo>/settings/hooks`.
2. Click **Add webhook**.
3. Fill in the configuration:
   - **Payload URL**: `https://<your-domain>/api/webhooks/github`
   - **Content type**: Select `application/json` (do not use `application/x-www-form-urlencoded`).
   - **Secret**: Enter the exact secret string from `GITHUB_WEBHOOK_SECRET`.
   - **SSL verification**: Select `Enable SSL verification`.
   - **Which events would you like to trigger this webhook?**: Select `Just the push event`.
   - **Active**: Ensure checkbox is checked.
4. Click **Add webhook**.

### Step 3: Verify Delivery Handshake
- GitHub immediately sends a `ping` event.
- Check the "Recent Deliveries" tab in GitHub. You should see a green checkmark with status `200 OK` and response body:
  ```json
  {
    "status": "ok",
    "message": "pong",
    "event": "ping"
  }
  ```

### Step 4: Real Code Push Verification
1. Push a new commit to your repository's default branch (`git commit -m "..." && git push origin main`).
2. GitHub automatically delivers a signed `push` payload.
3. SkillSync verifies the HMAC signature, updates `latest_commit_sha`, reruns the AI assessment pipeline, and creates an incremented version (e.g. `v2`).
4. Refresh the SkillSync dashboard to view the new score, updated evidence citations, and assessment history.
