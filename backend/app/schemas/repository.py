"""
Pydantic schemas for Repository requests and responses.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
import re


# ── Request Schemas ──────────────────────────────────────────────────

class RepositoryCreate(BaseModel):
    """Schema for adding a new GitHub repository to track."""
    github_url: Optional[str] = Field(
        None,
        description="Full GitHub repository URL, e.g. https://github.com/owner/repo",
        examples=["https://github.com/tiangolo/fastapi"],
    )
    github_owner: Optional[str] = Field(None, description="GitHub repository owner username or org")
    repo_name: Optional[str] = Field(None, description="GitHub repository name")
    default_branch: Optional[str] = Field("main", description="Default branch name")
    description: Optional[str] = Field(None, description="Repository description")
    language: Optional[str] = Field(None, description="Primary language")

    @property
    def resolved_url(self) -> str:
        if self.github_url and self.github_url.strip():
            return self.github_url.strip()
        if self.github_owner and self.repo_name:
            return f"https://github.com/{self.github_owner.strip()}/{self.repo_name.strip()}"
        return ""

    @property
    def owner(self) -> str:
        if self.github_owner:
            return self.github_owner.strip()
        parts = self.resolved_url.rstrip("/").split("/")
        return parts[-2] if len(parts) >= 2 else ""

    @property
    def repo(self) -> str:
        if self.repo_name:
            return self.repo_name.strip()
        parts = self.resolved_url.rstrip("/").split("/")
        return parts[-1] if len(parts) >= 1 else ""


class RepositoryValidateRequest(BaseModel):
    """Schema for validating a repository URL without saving it."""
    github_url: Optional[str] = Field(
        None,
        description="Full GitHub repository URL to validate",
        examples=["https://github.com/fastapi/fastapi"],
    )
    repository_url: Optional[str] = Field(
        None,
        description="Alias for github_url accepted from frontend",
        examples=["https://github.com/fastapi/fastapi"],
    )
    url: Optional[str] = Field(None, description="Generic url alias")

    @property
    def resolved_url(self) -> str:
        val = self.github_url or self.repository_url or self.url or ""
        return val.strip()


class RepositoryValidateResponse(BaseModel):
    """Result of repository validation."""
    valid: bool
    owner: Optional[str] = None
    repo: Optional[str] = None
    default_branch: Optional[str] = None
    message: str
    is_accessible: bool = False


# ── Response Schemas ─────────────────────────────────────────────────

class RepositoryResponse(BaseModel):
    """Schema for a tracked repository response."""
    id: int
    github_owner: str
    repo_name: str
    full_name: str
    default_branch: str
    latest_commit_sha: Optional[str]
    description: Optional[str]
    language: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_full_name(cls, repo) -> "RepositoryResponse":
        return cls(
            id=repo.id,
            github_owner=repo.github_owner,
            repo_name=repo.repo_name,
            full_name=repo.full_name,
            default_branch=repo.default_branch,
            latest_commit_sha=repo.latest_commit_sha,
            description=repo.description,
            language=repo.language,
            created_at=repo.created_at,
            updated_at=repo.updated_at,
        )


class RepositoryListResponse(BaseModel):
    """Schema for a paginated list of repositories."""
    repositories: list[RepositoryResponse]
    total: int
