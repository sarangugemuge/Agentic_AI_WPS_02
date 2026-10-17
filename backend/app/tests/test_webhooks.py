"""
Tests for Phase 8: Automatic Skill Reassessment via GitHub Webhooks.
Verifies:
1. HMAC-SHA256 signature verification (valid, invalid, missing).
2. Event type handling (ping, push, unsupported events).
3. Delivery deduplication (idempotency prevents redundant work).
4. Non-default branch filtering.
5. Automatic versioned reassessment triggering and data preservation.
"""
import hashlib
import hmac
import json
import uuid
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.repository import Repository
from app.models.job_profile import JobProfile
from app.models.assessment import Assessment, AssessmentStatus, TriggerEvent
from app.models.webhook_delivery import WebhookDelivery


def sign_payload(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def make_push_payload(
    owner: str = "octocat",
    repo: str = "Hello-World",
    branch: str = "main",
    commit_sha: str = "c0ffee99991234567890abcdef1234567890abc",
) -> dict:
    return {
        "ref": f"refs/heads/{branch}",
        "after": commit_sha,
        "repository": {
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "default_branch": branch,
            "owner": {"login": owner},
        },
    }


async def test_webhook_missing_or_invalid_signature(client: AsyncClient):
    """Webhook requests with missing or tampered signatures must be rejected with 401."""
    payload = json.dumps({"test": "data"}).encode("utf-8")

    # 1. Missing signature
    res = await client.post(
        "/api/webhooks/github",
        content=payload,
        headers={"Content-Type": "application/json", "X-GitHub-Event": "push"},
    )
    assert res.status_code == 401
    assert "Missing webhook signature" in res.json()["detail"]

    # 2. Invalid / tampered signature
    res = await client.post(
        "/api/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=invalidtamperedsignature00000000000000000000000000000000",
        },
    )
    assert res.status_code == 401
    assert "Invalid webhook signature" in res.json()["detail"]


async def test_webhook_ping_event(client: AsyncClient):
    """GitHub sends a ping event when a webhook is created. Must respond with 200 pong."""
    payload = json.dumps({"zen": "Keep it logically awesome."}).encode("utf-8")
    sig = sign_payload(payload, settings.github_webhook_secret)

    res = await client.post(
        "/api/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["message"] == "pong"


async def test_webhook_unsupported_event(client: AsyncClient):
    """Unsupported events (e.g. issues, star) must be ignored gracefully with 200 OK."""
    payload = json.dumps({"action": "opened"}).encode("utf-8")
    sig = sign_payload(payload, settings.github_webhook_secret)

    res = await client.post(
        "/api/webhooks/github",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ignored"
    assert "Unsupported event type" in data["message"]


async def test_webhook_untracked_repository(client: AsyncClient):
    """Push events for repositories not tracked in SkillSync must be ignored gracefully."""
    payload_dict = make_push_payload(owner="random-user", repo="untracked-repo-xyz")
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = sign_payload(payload_bytes, settings.github_webhook_secret)
    deliv_id = str(uuid.uuid4())

    res = await client.post(
        "/api/webhooks/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ignored"
    assert "is not registered in SkillSync" in data["message"]


async def test_webhook_delivery_deduplication(client: AsyncClient):
    """Duplicate deliveries with the same X-GitHub-Delivery must be detected and not re-executed."""
    # First, ensure octocat/Hello-World exists and has a prior assessment
    # Create repo
    repo_res = await client.post(
        "/api/repositories",
        json={
            "github_url": "https://github.com/octocat/Hello-World",
            "description": "Test repo for webhook deduplication",
        },
    )
    repo_data = repo_res.json()
    repo_id = repo_data["id"]


    # Create job profile and run initial assessment
    prof_res = await client.post(
        "/api/job-profiles",
        json={
            "title": "Webhook Python Engineer",
            "raw_description": "We need an engineer proficient in Python, Git, and automated testing.",
        },
    )
    prof_id = prof_res.json()["id"]

    init_assess_res = await client.post(
        "/api/assessments",
        json={"repository_id": repo_id, "job_profile_id": prof_id},
    )
    assert init_assess_res.status_code == 201
    init_version = init_assess_res.json()["version"]

    # Now simulate a push webhook
    deliv_id = str(uuid.uuid4())
    payload_dict = make_push_payload(
        owner="octocat",
        repo="Hello-World",
        branch="main",
        commit_sha="e0e1e2e3e4e51234567890abcdef1234567890ab",
    )
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = sign_payload(payload_bytes, settings.github_webhook_secret)

    # 1. First delivery -> must succeed and reassess
    first_res = await client.post(
        "/api/webhooks/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": sig,
        },
    )
    assert first_res.status_code == 200
    first_data = first_res.json()
    assert first_data["status"] == "reassessed"
    assert first_data["version"] > init_version

    # 2. Second delivery with identical delivery ID -> must be flagged duplicate
    second_res = await client.post(
        "/api/webhooks/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": sig,
        },
    )
    assert second_res.status_code == 200
    second_data = second_res.json()
    assert second_data["status"] == "duplicate"
    assert "already processed" in second_data["message"]


async def test_webhook_non_default_branch_ignored(client: AsyncClient):
    """Pushes to feature branches must be ignored if default branch is main."""
    deliv_id = str(uuid.uuid4())
    payload_dict = make_push_payload(
        owner="octocat",
        repo="Hello-World",
        branch="feature/experimental-branch",
        commit_sha="f0f1f2f3f4f51234567890abcdef1234567890ab",
    )
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    sig = sign_payload(payload_bytes, settings.github_webhook_secret)

    res = await client.post(
        "/api/webhooks/github",
        content=payload_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": deliv_id,
            "X-Hub-Signature-256": sig,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ignored"
    assert "non-default branch" in data["message"]
