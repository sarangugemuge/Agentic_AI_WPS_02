import asyncio
import os
import sys
import httpx

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings

print("=" * 60)
print("SkillSync Live API Credentials Diagnostic")
print("=" * 60)
print(f"USE_TEST_DOUBLES:        {settings.use_test_doubles}")
print(f"GITHUB_TOKEN set:        {bool(settings.github_token.strip())} (length: {len(settings.github_token.strip())})")
print(f"GEMINI_API_KEY set:      {bool(settings.gemini_api_key.strip())} (length: {len(settings.gemini_api_key.strip())})")
print(f"GEMINI_MODEL:            {settings.gemini_model}")
print("-" * 60)

async def test_github():
    print("\n[1] Testing GitHub REST API...")
    token = settings.github_token.strip()
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SkillSync-Assessment-Engine/0.1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        print("  Notice: GITHUB_TOKEN is empty in settings! Making unauthenticated request.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.github.com/rate_limit", headers=headers)
            print(f"  GitHub /rate_limit HTTP Status: {resp.status_code}")
            if resp.status_code == 200:
                core = resp.json().get("resources", {}).get("core", {})
                print(f"  Rate Limit Remaining: {core.get('remaining')} / {core.get('limit')}")
                print(f"  Authentication Active: {bool(token)}")
            elif resp.status_code == 401:
                print("  [ERROR] GitHub Token is INVALID or Expired (HTTP 401 Bad credentials)!")
                print(f"  Response: {resp.text}")
            else:
                print(f"  GitHub response: {resp.status_code} - {resp.text[:200]}")

            # Test validating a real repository
            test_repo = "octocat/Hello-World"
            r2 = await client.get(f"https://api.github.com/repos/{test_repo}", headers=headers)
            print(f"  Test repo lookup ({test_repo}): HTTP {r2.status_code}")
    except Exception as exc:
        print(f"  [ERROR] GitHub connection failed: {type(exc).__name__}: {exc}")

async def test_gemini():
    print("\n[2] Testing Google Gemini API...")
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        print("  [ERROR] GEMINI_API_KEY is empty in settings!")
        return

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents="Say 'SkillSync Gemini Connection OK'",
        )
        print("  [+] Gemini API call SUCCEEDED!")
        print(f"  Model response: {response.text.strip()}")
    except Exception as exc:
        print(f"  [ERROR] Gemini API failed: {type(exc).__name__}: {exc}")

async def main():
    await test_github()
    await test_gemini()
    print("\n" + "=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
