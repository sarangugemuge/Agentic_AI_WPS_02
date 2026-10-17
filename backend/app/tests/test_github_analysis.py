"""
Phase 4 Tests — GitHub Repository Analysis, Normalization, and Provenance.
Verifies URL validation, binary/secret exclusions, provenance building, and error handling.
"""
from app.services.repository_normalizer import (
    is_path_excluded,
    detect_language,
    decode_and_sanitize_content,
    build_evidence_provenance,
    MAX_FILE_SIZE_BYTES,
)
from app.services.repository_service import RepositoryService
from app.services.github_client import GitHubClient
from app.core.exceptions import BusinessValidationError, NotFoundError, ServiceUnavailableError
import base64


def assert_raises(exc_type, func, *args, **kwargs):
    try:
        func(*args, **kwargs)
        assert False, f"Expected {exc_type.__name__} was not raised."
    except exc_type:
        pass


def test_url_validation_and_parsing():
    """Verify owner and repo extraction from GitHub URLs."""
    owner, repo = RepositoryService.parse_github_url("https://github.com/fastapi/fastapi")
    assert owner == "fastapi"
    assert repo == "fastapi"

    owner2, repo2 = RepositoryService.parse_github_url("https://github.com/torvalds/linux/")
    assert owner2 == "torvalds"
    assert repo2 == "linux"

    assert_raises(BusinessValidationError, RepositoryService.parse_github_url, "https://gitlab.com/owner/repo")
    assert_raises(BusinessValidationError, RepositoryService.parse_github_url, "not-a-url")


def test_excluded_directories_and_files():
    """Verify that node_modules, build artifacts, binaries, and secrets are excluded."""
    # Excluded directories
    assert is_path_excluded("node_modules/express/index.js") is True
    assert is_path_excluded(".git/HEAD") is True
    assert is_path_excluded("dist/bundle.js") is True
    assert is_path_excluded(".venv/lib/python3.14/site-packages/fastapi/main.py") is True
    assert is_path_excluded("__pycache__/app.cpython-314.pyc") is True

    # Excluded binary file extensions
    assert is_path_excluded("assets/logo.png") is True
    assert is_path_excluded("documents/spec.pdf") is True
    assert is_path_excluded("build/app.exe") is True
    assert is_path_excluded("media/audio.mp3") is True
    assert is_path_excluded("package-lock.json") is True

    # Excluded secrets and credentials
    assert is_path_excluded(".env") is True
    assert is_path_excluded(".env.production") is True
    assert is_path_excluded("certs/server.pem") is True
    assert is_path_excluded("keys/private.key") is True
    assert is_path_excluded("id_rsa") is True

    # Permitted valid source files
    assert is_path_excluded("backend/app/main.py") is False
    assert is_path_excluded("frontend/src/App.jsx") is False
    assert is_path_excluded("src/index.ts") is False
    assert is_path_excluded("Dockerfile") is False
    assert is_path_excluded("README.md") is False


def test_language_detection():
    """Verify accurate language inference from filenames."""
    assert detect_language("app/main.py") == "Python"
    assert detect_language("src/components/Header.jsx") == "React (JavaScript)"
    assert detect_language("src/index.tsx") == "React (TypeScript)"
    assert detect_language("Dockerfile") == "Dockerfile"
    assert detect_language("schema.sql") == "SQL"
    assert detect_language("styles.css") == "CSS"


def test_decode_and_sanitize_content():
    """Verify untrusted content decoding, sanitization, and truncation."""
    source_code = "def hello():\n    print('Hello SkillSync')\n"
    encoded = base64.b64encode(source_code.encode("utf-8")).decode("ascii")

    decoded = decode_and_sanitize_content(encoded, "test.py")
    assert "def hello():" in decoded
    assert "Hello SkillSync" in decoded

    # Test truncation of oversized text
    huge_text = "x = 1\n" * 1000
    huge_encoded = base64.b64encode(huge_text.encode("utf-8")).decode("ascii")
    sanitized_huge = decode_and_sanitize_content(huge_encoded, "huge.py")
    assert len(sanitized_huge) <= 3100
    assert "truncated" in sanitized_huge


def test_evidence_provenance_builder():
    """Verify evidence provenance metadata construction."""
    provenance = build_evidence_provenance(
        owner="myorg",
        repo="myproject",
        file_path="src/utils.py",
        commit_sha="abcdef1234567890abcdef1234567890abcdef12",
        snippet="def helper(): pass",
        start_line=10,
        end_line=20,
    )
    assert provenance["repository_url"] == "https://github.com/myorg/myproject"
    assert provenance["file_path"] == "src/utils.py"
    assert provenance["commit_sha"] == "abcdef1234567890abcdef1234567890abcdef12"
    assert (
        provenance["blob_url"]
        == "https://github.com/myorg/myproject/blob/abcdef1234567890abcdef1234567890abcdef12/src/utils.py"
    )
    assert provenance["language"] == "Python"
    assert provenance["start_line"] == 10
    assert provenance["end_line"] == 20
