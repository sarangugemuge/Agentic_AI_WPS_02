"""
Local GitHub Webhook Simulation Script for SkillSync.
Simulates realistic GitHub push and ping webhook events locally without
requiring external tunnels, public IP exposure, or third-party services.
"""
import argparse
import hashlib
import hmac
import json
import uuid
import httpx

DEFAULT_SECRET = "skillsync-webhook-secret"
DEFAULT_URL = "http://127.0.0.1:8000/api/webhooks/github"


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature matching GitHub's specification."""
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_push_payload(
    owner: str = "octocat",
    repo: str = "Hello-World",
    branch: str = "main",
    commit_sha: str = "c0ffee1234567890abcdef1234567890abcdef12",
    message: str = "feat: add automated skill integration tests",
) -> dict:
    """Build a realistic GitHub push event JSON payload."""
    return {
        "ref": f"refs/heads/{branch}",
        "before": "b4b3b2b11234567890abcdef1234567890abcdef",
        "after": commit_sha,
        "repository": {
            "id": 1296269,
            "name": repo,
            "full_name": f"{owner}/{repo}",
            "private": False,
            "owner": {
                "name": owner,
                "email": f"{owner}@users.noreply.github.com",
                "login": owner,
            },
            "default_branch": branch,
            "language": "Python",
        },
        "pusher": {
            "name": owner,
            "email": f"{owner}@github.com",
        },
        "head_commit": {
            "id": commit_sha,
            "message": message,
            "timestamp": "2026-10-16T18:00:00Z",
            "author": {
                "name": owner,
                "email": f"{owner}@github.com",
            },
        },
    }


def send_webhook(
    event: str = "push",
    owner: str = "octocat",
    repo: str = "Hello-World",
    branch: str = "main",
    secret: str = DEFAULT_SECRET,
    url: str = DEFAULT_URL,
    tamper_sig: bool = False,
    custom_delivery_id: str = None,
):
    delivery_id = custom_delivery_id or str(uuid.uuid4())

    if event == "ping":
        payload = {"zen": "Mind your words, they are important.", "hook_id": 123456}
    else:
        payload = build_push_payload(owner=owner, repo=repo, branch=branch)

    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    if tamper_sig:
        signature = "sha256=invalid_tampered_signature_hex_digest"
    else:
        signature = compute_signature(payload_bytes, secret)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery_id,
        "X-Hub-Signature-256": signature,
        "User-Agent": "GitHub-Hookshot/simulated",
    }

    print("=" * 60)
    print(f"Sending Simulated GitHub '{event}' Webhook")
    print(f"Target URL:    {url}")
    print(f"Delivery ID:   {delivery_id}")
    print(f"Signature:     {signature[:18]}...")
    print(f"Repository:    {owner}/{repo} (branch: {branch})")
    print("=" * 60)

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, content=payload_bytes, headers=headers)
            print(f"\nResponse HTTP Status: {resp.status_code}")
            try:
                data = resp.json()
                print(f"Response Body:\n{json.dumps(data, indent=2)}")
            except Exception:
                print(f"Response Raw: {resp.text}")
            return resp
    except Exception as e:
        print(f"Error sending request: {e}")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate GitHub Webhooks locally")
    parser.add_argument("--event", default="push", choices=["push", "ping", "issues"])
    parser.add_argument("--owner", default="octocat")
    parser.add_argument("--repo", default="Hello-World")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--secret", default=DEFAULT_SECRET)
    parser.add_argument("--tamper", action="store_true", help="Send invalid signature")
    args = parser.parse_args()

    send_webhook(
        event=args.event,
        owner=args.owner,
        repo=args.repo,
        branch=args.branch,
        secret=args.secret,
        tamper_sig=args.tamper,
    )
