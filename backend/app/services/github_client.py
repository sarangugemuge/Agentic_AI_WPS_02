"""
GitHub REST API v3 Client — Safe asynchronous integration for repository inspection.
Implements rate limit detection, safe timeouts, binary exclusion, and provenance tracking.
Treats all repository content as untrusted read-only data.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.exceptions import (
    BusinessValidationError,
    NotFoundError,
    ServiceUnavailableError,
)
from app.services.repository_normalizer import (
    is_path_excluded,
    detect_language,
    decode_and_sanitize_content,
    build_evidence_provenance,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES_ANALYZED,
)

logger = logging.getLogger("skillsync.services.github_client")

GITHUB_API_BASE = "https://api.github.com"


class GitHubClient:
    """
    Asynchronous client for inspecting public (and permitted private) GitHub repositories.
    """

    def __init__(self, token: Optional[str] = None, timeout_seconds: Optional[float] = None):
        self.token = token or settings.github_token
        self.timeout = timeout_seconds or settings.github_timeout_seconds

    def _get_headers(self) -> Dict[str, str]:
        """Construct standard GitHub REST API headers."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SkillSync-Assessment-Engine/0.1.0",
        }
        if self.token and self.token.strip():
            headers["Authorization"] = f"Bearer {self.token.strip()}"
        return headers

    async def _handle_response_errors(self, response: httpx.Response, owner: str, repo: str) -> None:
        """Translate GitHub HTTP error codes into domain exceptions."""
        if response.status_code == 404:
            raise NotFoundError("GitHub Repository", f"{owner}/{repo} (does not exist or is private)")

        if response.status_code == 401:
            raise BusinessValidationError("GitHub authentication failed. Check configured GITHUB_TOKEN.")

        if response.status_code in [403, 429]:
            reset_epoch = response.headers.get("x-ratelimit-reset")
            remaining = response.headers.get("x-ratelimit-remaining", "0")
            msg = f"GitHub API rate limit exceeded (remaining: {remaining})."
            if reset_epoch:
                msg += f" Rate limit resets at Unix timestamp {reset_epoch}."
            raise ServiceUnavailableError("GitHub API", msg)

        if response.status_code >= 500:
            raise ServiceUnavailableError("GitHub API", f"GitHub returned HTTP {response.status_code} server error.")

        response.raise_for_status()

    async def validate_repository(self, owner: str, repo: str) -> Dict[str, Any]:
        """Verify repository exists and is accessible via GitHub API."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    return {
                        "valid": False,
                        "is_accessible": False,
                        "owner": owner,
                        "repo": repo,
                        "message": f"Repository '{owner}/{repo}' was not found or is private.",
                    }
                await self._handle_response_errors(response, owner, repo)
                data = response.json()
                return {
                    "valid": True,
                    "is_accessible": True,
                    "owner": owner,
                    "repo": repo,
                    "default_branch": data.get("default_branch", "main"),
                    "is_private": data.get("private", False),
                    "message": f"Repository '{owner}/{repo}' is valid and accessible.",
                }
        except httpx.TimeoutException:
            raise ServiceUnavailableError("GitHub API", f"Timed out connecting to GitHub for repository {owner}/{repo}.")
        except httpx.RequestError as exc:
            raise ServiceUnavailableError("GitHub API", f"Network error connecting to GitHub: {str(exc)}")

    async def get_repository_metadata(self, owner: str, repo: str) -> Dict[str, Any]:
        """Fetch repository details, default branch, description, language, and latest commit SHA."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}"
        headers = self._get_headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                await self._handle_response_errors(response, owner, repo)
                repo_data = response.json()

                default_branch = repo_data.get("default_branch", "main")

                # Fetch latest commit on default branch
                commit_sha = None
                commits_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{default_branch}"
                commits_resp = await client.get(commits_url, headers=headers)
                if commits_resp.status_code == 200:
                    commit_sha = commits_resp.json().get("sha")

                return {
                    "github_owner": owner,
                    "repo_name": repo,
                    "full_name": f"{owner}/{repo}",
                    "default_branch": default_branch,
                    "latest_commit_sha": commit_sha,
                    "description": repo_data.get("description"),
                    "language": repo_data.get("language"),
                    "stargazers_count": repo_data.get("stargazers_count", 0),
                    "forks_count": repo_data.get("forks_count", 0),
                    "is_private": repo_data.get("private", False),
                }
        except httpx.TimeoutException:
            raise ServiceUnavailableError("GitHub API", f"Timed out fetching metadata for {owner}/{repo}.")
        except httpx.RequestError as exc:
            raise ServiceUnavailableError("GitHub API", f"Network error fetching metadata: {str(exc)}")

    async def get_commit_details(self, owner: str, repo: str, commit_sha: str) -> Dict[str, Any]:
        """Fetch commit message, changed files, author, and status from GitHub API."""
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits/{commit_sha}"
        headers = self._get_headers()
        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    commit_info = data.get("commit", {})
                    files = data.get("files", [])
                    changed_files = [f.get("filename") for f in files if f.get("filename")]
                    from app.services.scoring_engine import ScoringEngine
                    is_doc_only = ScoringEngine.is_documentation_only_commit(changed_files)
                    return {
                        "commit_sha": commit_sha,
                        "message": commit_info.get("message", ""),
                        "author": commit_info.get("author", {}).get("name", "Unknown"),
                        "date": commit_info.get("author", {}).get("date"),
                        "changed_files": changed_files,
                        "is_doc_only": is_doc_only,
                        "files_summary": {
                            "added": sum(1 for f in files if f.get("status") == "added"),
                            "modified": sum(1 for f in files if f.get("status") == "modified"),
                            "removed": sum(1 for f in files if f.get("status") == "removed"),
                        },
                    }
        except Exception as exc:
            logger.warning(f"Failed to fetch commit details for {owner}/{repo}@{commit_sha}: {exc}")
        return {
            "commit_sha": commit_sha,
            "message": "",
            "author": "GitHub",
            "changed_files": [],
            "is_doc_only": False,
            "files_summary": {"added": 0, "modified": 0, "removed": 0},
        }

    async def get_repository_evidence_artifacts(
        self,
        owner: str,
        repo: str,
        branch: Optional[str] = None,
        commit_sha: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Safely inspects the repository file tree, filters out binaries and secrets,
        and retrieves representative source code files for AI skill evaluation.
        Supports targeting an exact commit SHA or a branch.
        """
        metadata = await self.get_repository_metadata(owner, repo)
        target_branch = branch or metadata.get("default_branch", "main")
        target_ref = commit_sha or metadata.get("latest_commit_sha") or target_branch
        headers = self._get_headers()

        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            # 1. Fetch recursive tree via Git Trees API
            tree_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{target_ref}?recursive=1"
            tree_resp = await client.get(tree_url, headers=headers)
            await self._handle_response_errors(tree_resp, owner, repo)
            tree_data = tree_resp.json()

            raw_tree = tree_data.get("tree", [])

            # 2. Filter candidates: only blobs (files), not excluded, size within limits
            candidates: List[Dict[str, Any]] = []
            for item in raw_tree:
                if item.get("type") != "blob":
                    continue
                path = item.get("path", "")
                size = item.get("size", 0)

                if is_path_excluded(path):
                    continue
                if size > MAX_FILE_SIZE_BYTES:
                    continue

                candidates.append(item)

            # Cap file count to keep processing efficient and within LLM token budgets
            # Prioritize important architectural files (package manifests, config, main code)
            def file_priority(item: Dict[str, Any]) -> int:
                p = item.get("path", "").lower()
                if any(m in p for m in ["pyproject.toml", "package.json", "requirements.txt", "dockerfile", "main.py", "app.py", "index.ts", "index.js", "app.tsx"]):
                    return 0
                if any(ext in p for ext in [".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java"]):
                    return 1
                return 2

            candidates.sort(key=file_priority)
            selected_files = candidates[:MAX_FILES_ANALYZED]
            logger.info(f"Selected {len(selected_files)} candidate source files from {owner}/{repo} (total tree: {len(raw_tree)} items)")

            # 3. Retrieve and decode content concurrently for selected files
            sem = asyncio.Semaphore(8)

            async def fetch_blob(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
                async with sem:
                    file_path = item["path"]
                    blob_url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/blobs/{item['sha']}"
                    try:
                        blob_resp = await client.get(blob_url, headers=headers)
                        if blob_resp.status_code != 200:
                            return None
                        blob_json = blob_resp.json()
                        raw_base64 = blob_json.get("content", "")
                        sanitized_snippet = decode_and_sanitize_content(raw_base64, file_path)

                        provenance = build_evidence_provenance(
                            owner=owner,
                            repo=repo,
                            file_path=file_path,
                            commit_sha=commit_sha,
                            snippet=sanitized_snippet,
                            start_line=1,
                            end_line=len(sanitized_snippet.splitlines()),
                        )

                        return {
                            "path": file_path,
                            "language": detect_language(file_path),
                            "snippet": sanitized_snippet,
                            "provenance": provenance,
                        }
                    except Exception as exc:
                        logger.warning(f"Error fetching blob for {file_path}: {exc}")
                        return None

            blob_results = await asyncio.gather(*(fetch_blob(item) for item in selected_files), return_exceptions=True)
            artifacts: List[Dict[str, Any]] = [res for res in blob_results if isinstance(res, dict) and res is not None]

            return {
                "owner": owner,
                "repo": repo,
                "commit_sha": commit_sha,
                "branch": target_branch,
                "total_tree_count": len(raw_tree),
                "analyzed_file_count": len(artifacts),
                "files": artifacts,
            }
