"""
Repository Normalizer — Content sanitization, binary filtering, and provenance tracking.
Ensures that all repository content retrieved from GitHub is treated as untrusted text,
never executed, and filtered to remove binaries, secrets, and oversized files.
"""
import base64
import os
import re
from typing import Any, Dict, List, Optional, Set

# Ignored directories
EXCLUDED_DIRECTORIES: Set[str] = {
    "node_modules",
    ".git",
    ".github",
    "dist",
    "build",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
    "htmlcov",
    ".tox",
}

# Binary and non-source file extensions
EXCLUDED_EXTENSIONS: Set[str] = {
    # Images & media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp", ".tiff",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".flv", ".webm",
    # Documents & archives
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".7z", ".rar",
    # Binaries & compiled artifacts
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj",
    ".pyc", ".pyo", ".pyd", ".class", ".jar", ".war",
    # Fonts
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    # Database files
    ".db", ".sqlite", ".sqlite3", ".rdb",
    # Large generated locks
    ".lock",
}

# Excluded lock and generated files
EXCLUDED_FILENAMES: Set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "composer.lock",
    "gemfile.lock",
    "cargo.lock",
}

# Secret and credential file patterns
EXCLUDED_SECRET_PATTERNS = [
    r"^\.env(\..+)?$",
    r".*secret.*",
    r".*credential.*",
    r".*\.pem$",
    r".*\.key$",
    r".*\.cert$",
    r".*\.pfx$",
    r"^id_rsa.*",
    r"^id_ed25519.*",
    r".*token.*",
]

# File size and extraction limits
MAX_FILE_SIZE_BYTES = 100 * 1024  # 100 KB max per file
MAX_FILES_ANALYZED = 25            # Maximum source files to analyze
MAX_SNIPPET_LENGTH_CHARS = 3000   # Max snippet characters stored in evidence

# Map file extensions to language names
EXTENSION_LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "React (JavaScript)",
    ".ts": "TypeScript",
    ".tsx": "React (TypeScript)",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".md": "Markdown",
    ".dockerfile": "Dockerfile",
}


def is_path_excluded(path: str) -> bool:
    """Check if a file path is inside an excluded directory or matches secret patterns."""
    normalized = path.replace("\\", "/").strip("/")
    parts = normalized.split("/")

    # Check directory exclusion
    for part in parts[:-1]:
        if part.lower() in EXCLUDED_DIRECTORIES:
            return True

    filename = parts[-1].lower()

    # Check specific excluded filenames
    if filename in EXCLUDED_FILENAMES:
        return True

    # Check secret patterns
    for pattern in EXCLUDED_SECRET_PATTERNS:
        if re.match(pattern, filename, re.IGNORECASE):
            return True

    # Check extension exclusion
    _, ext = os.path.splitext(filename)
    if ext.lower() in EXCLUDED_EXTENSIONS:
        return True

    return False


def detect_language(path: str) -> str:
    """Infer programming or markup language from file path/extension."""
    normalized = path.replace("\\", "/").lower()
    filename = normalized.split("/")[-1]

    if filename == "dockerfile":
        return "Dockerfile"
    if filename in ["makefile", "cmakelists.txt"]:
        return "Build Script"

    _, ext = os.path.splitext(filename)
    return EXTENSION_LANGUAGE_MAP.get(ext, "Plain Text")


def decode_and_sanitize_content(raw_base64: str, file_path: str) -> str:
    """
    Safely decode Base64 file content from GitHub API.
    Treats all content as untrusted text, strips non-printable characters,
    and limits snippet size. Never executes content.
    """
    try:
        raw_bytes = base64.b64decode(raw_base64)
    except Exception:
        return "[Error: Content could not be decoded]"

    # Decode with fallback encoding
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = raw_bytes.decode("latin-1")
        except Exception:
            return "[Binary content excluded from analysis]"

    # Sanitize: normalize line endings and cap character length
    sanitized = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(sanitized) > MAX_SNIPPET_LENGTH_CHARS:
        sanitized = sanitized[:MAX_SNIPPET_LENGTH_CHARS] + "\n... [content truncated for length] ..."

    return sanitized


def build_evidence_provenance(
    owner: str,
    repo: str,
    file_path: str,
    commit_sha: Optional[str] = None,
    snippet: Optional[str] = None,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Constructs a verifiable provenance record for a code evidence citation.
    """
    commit = commit_sha or "main"
    blob_url = f"https://github.com/{owner}/{repo}/blob/{commit}/{file_path}"

    return {
        "repository_url": f"https://github.com/{owner}/{repo}",
        "file_path": file_path,
        "commit_sha": commit_sha,
        "blob_url": blob_url,
        "language": detect_language(file_path),
        "start_line": start_line or 1,
        "end_line": end_line or 1,
        "code_snippet": snippet or "",
    }
