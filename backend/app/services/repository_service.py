"""
Repository Service — Manages GitHub repository tracking, validation, and database persistence.
"""
import logging
import re
from typing import Any, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, BusinessValidationError
from app.models.repository import Repository
from app.services.github_service import get_github_service

logger = logging.getLogger("skillsync.services.repository")


class RepositoryService:
    def __init__(self, github_service: Any = None):
        self.github_service = github_service or get_github_service()

    @staticmethod
    def parse_github_url(url: str) -> Tuple[str, str]:
        """Extract (owner, repo) from GitHub URL or owner/repo format."""
        if not url or not isinstance(url, str):
            raise BusinessValidationError("A GitHub repository URL or owner/repo is required.")
        cleaned = url.strip().strip("'\"").strip()
        cleaned = cleaned.rstrip("/")
        if cleaned.endswith(".git"):
            cleaned = cleaned[:-4]
        pattern = r"^(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_.\-]+)/([a-zA-Z0-9_.\-]+)(?:/.*)?$"
        match = re.match(pattern, cleaned)
        if match:
            repo = match.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            return match.group(1), repo
        short_pattern = r"^([a-zA-Z0-9_.\-]+)/([a-zA-Z0-9_.\-]+)$"
        short_match = re.match(short_pattern, cleaned)
        if short_match:
            repo = short_match.group(2)
            if repo.endswith(".git"):
                repo = repo[:-4]
            return short_match.group(1), repo
        raise BusinessValidationError(
            f"Invalid GitHub URL: '{url}'. Expected format: https://github.com/owner/repository"
        )

    async def validate_url(self, github_url: str) -> dict:
        """Validate repository URL format and check reachability via GitHub service."""
        owner, repo = self.parse_github_url(github_url)
        validation_result = await self.github_service.validate_repository(owner, repo)
        return validation_result

    async def create_or_update_repository(self, db: AsyncSession, github_url: str) -> Repository:
        """
        Validate URL, fetch repository metadata from GitHub service,
        and persist/update the repository record in the database.
        """
        owner, repo_name = self.parse_github_url(github_url)

        # Check repository accessibility
        check = await self.github_service.validate_repository(owner, repo_name)
        if not check.get("valid", False) or not check.get("is_accessible", False):
            raise BusinessValidationError(
                check.get("message", f"Repository {owner}/{repo_name} is not accessible.")
            )

        # Retrieve metadata
        metadata = await self.github_service.get_repository_metadata(owner, repo_name)

        # Check if already tracked
        stmt = select(Repository).where(
            Repository.github_owner == owner,
            Repository.repo_name == repo_name,
        )
        result = await db.execute(stmt)
        repo_obj = result.scalar_one_or_none()

        if repo_obj:
            logger.info(f"Repository {owner}/{repo_name} already exists (ID: {repo_obj.id}), updating metadata.")
            repo_obj.default_branch = metadata.get("default_branch", repo_obj.default_branch)
            repo_obj.latest_commit_sha = metadata.get("latest_commit_sha", repo_obj.latest_commit_sha)
            repo_obj.description = metadata.get("description", repo_obj.description)
            repo_obj.language = metadata.get("language", repo_obj.language)
        else:
            logger.info(f"Creating new repository record for {owner}/{repo_name}.")
            repo_obj = Repository(
                github_owner=owner,
                repo_name=repo_name,
                default_branch=metadata.get("default_branch", "main"),
                latest_commit_sha=metadata.get("latest_commit_sha"),
                description=metadata.get("description"),
                language=metadata.get("language"),
            )
            db.add(repo_obj)

        await db.commit()
        await db.refresh(repo_obj)
        return repo_obj

    async def get_repository_by_id(self, db: AsyncSession, repository_id: int) -> Repository:
        """Retrieve repository by ID or raise NotFoundError."""
        stmt = select(Repository).where(Repository.id == repository_id)
        result = await db.execute(stmt)
        repo = result.scalar_one_or_none()
        if not repo:
            raise NotFoundError("Repository", repository_id)
        return repo

    async def list_repositories(
        self, db: AsyncSession, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Repository], int]:
        """List repositories with pagination and return total count."""
        count_stmt = select(func.count(Repository.id))
        total_result = await db.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = select(Repository).order_by(Repository.id.desc()).offset(skip).limit(limit)
        result = await db.execute(stmt)
        repos = list(result.scalars().all())

        return repos, total

    async def delete_repository(self, db: AsyncSession, repository_id: int) -> None:
        """Delete repository and its associated assessments."""
        repo = await self.get_repository_by_id(db, repository_id)
        await db.delete(repo)
        await db.commit()
        logger.info(f"Deleted repository ID: {repository_id}")


def get_repository_service() -> RepositoryService:
    """FastAPI dependency provider for RepositoryService."""
    return RepositoryService()
