"""Lightweight GitHub client for public repositories.

Downloads the repository tarball in a single request (via the GitHub API, which
redirects to codeload) and reads the file tree and a bounded selection of
interesting file contents in-memory. This keeps us well under the unauthenticated
rate limit — only the metadata calls hit the REST API.
"""
from __future__ import annotations

import io
import logging
import re
import tarfile
from dataclasses import dataclass, field
from typing import Optional

import httpx

from .config import get_settings
from .models import RepoMeta

logger = logging.getLogger("githubiq.github")

API = "https://api.github.com"

# Files that are most useful for architecture / schema / data-flow analysis.
INTERESTING_PATTERNS = re.compile(
    r"(readme|main|app|server|index|route|router|controller|handler|service|"
    r"model|schema|migration|entity|dockerfile|docker-compose|requirements|"
    r"package\.json|go\.mod|pom\.xml|settings|config|urls)",
    re.IGNORECASE,
)

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".rs", ".cs",
    ".php", ".sql", ".yml", ".yaml", ".json", ".md", ".toml", ".mod",
}

SKIP_DIRS = ("node_modules/", "dist/", "build/", ".git/", "vendor/", "__pycache__/",
             "/test", "/spec", ".github/")


@dataclass
class RepoFile:
    path: str
    content: str


# Files worth reading in full as "anchors" for the researcher agent.
ANCHOR_PATTERNS = re.compile(
    r"(readme|main\.|__main__|app\.|server\.|index\.(js|ts|jsx|tsx)|manage\.py|"
    r"wsgi|asgi|cmd/|package\.json|pyproject|requirements|go\.mod|pom\.xml|"
    r"cargo\.toml|gemfile|composer\.json|dockerfile|docker-compose|makefile|"
    r"settings\.|config\.|urls\.|routes|schema|migration|models?\.)",
    re.IGNORECASE,
)


@dataclass
class RepoContext:
    meta: RepoMeta
    tree: list[str] = field(default_factory=list)
    files: list[RepoFile] = field(default_factory=list)
    contents: dict[str, str] = field(default_factory=dict)  # path -> full text

    def file_listing(self, limit: int = 600) -> str:
        return "\n".join(self.tree[:limit])

    def sampled_sources(self, limit: int = 24) -> str:
        chunks = []
        for f in self.files[:limit]:
            chunks.append(f"### FILE: {f.path}\n{f.content}")
        return "\n\n".join(chunks)

    def anchor_sources(self, total_budget: int = 90_000) -> str:
        """README + manifests + likely entry points, for the researcher agent."""
        paths = [p for p in self.contents if ANCHOR_PATTERNS.search(p.lower())]
        # readmes and manifests first, then shallow files
        paths.sort(key=lambda p: (p.count("/"), 0 if "readme" in p.lower() else 1))
        return self.read_files(paths, total_budget=total_budget, per_file=12_000)

    def read_files(
        self, paths: list[str], *, total_budget: int = 60_000, per_file: int = 12_000
    ) -> str:
        """Return concatenated contents for the given paths, within a token budget."""
        chunks: list[str] = []
        used = 0
        seen: set[str] = set()
        for path in paths:
            if not path or path in seen:
                continue
            seen.add(path)
            body = self.contents.get(path) or self._fuzzy_get(path)
            if not body:
                continue
            snippet = body[:per_file]
            block = f"### FILE: {path}\n{snippet}"
            if used + len(block) > total_budget:
                break
            chunks.append(block)
            used += len(block)
        return "\n\n".join(chunks)

    def _fuzzy_get(self, path: str) -> str:
        """Match an assigned path against stored files by suffix/basename."""
        low = path.lower().lstrip("./")
        for p, body in self.contents.items():
            pl = p.lower()
            if pl == low or pl.endswith("/" + low) or pl.endswith(low):
                return body
        base = low.rsplit("/", 1)[-1]
        for p, body in self.contents.items():
            if p.lower().rsplit("/", 1)[-1] == base:
                return body
        return ""



def parse_repo_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL or ``owner/repo`` shorthand."""
    url = url.strip().rstrip("/")
    url = re.sub(r"\.git$", "", url)
    match = re.search(r"github\.com[:/]+([^/]+)/([^/]+)", url)
    if match:
        return match.group(1), match.group(2)
    parts = url.split("/")
    if len(parts) == 2:
        return parts[0], parts[1]
    raise ValueError(f"Could not parse a GitHub owner/repo from: {url}")


class GitHubClient:
    def __init__(self, token: Optional[str] = None) -> None:
        settings = get_settings()
        self.token = token or settings.github_token
        self.max_files = settings.max_files_scanned
        self.max_bytes = settings.max_file_bytes
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(headers=headers, timeout=60.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _get(self, path: str) -> httpx.Response:
        resp = self._client.get(f"{API}{path}")
        resp.raise_for_status()
        return resp

    def fetch_context(self, owner: str, repo: str) -> RepoContext:
        info = self._get(f"/repos/{owner}/{repo}").json()
        branch = info.get("default_branch", "main")

        languages: list[str] = []
        try:
            languages = list(self._get(f"/repos/{owner}/{repo}/languages").json().keys())
        except httpx.HTTPError:
            pass

        meta = RepoMeta(
            owner=owner,
            name=repo,
            default_branch=branch,
            description=info.get("description") or "",
            primary_language=info.get("language") or (languages[0] if languages else ""),
            languages=languages,
            stars=info.get("stargazers_count", 0),
        )

        tree, files, contents = self._download_tarball(owner, repo, branch)
        meta.file_count = len(tree)
        return RepoContext(meta=meta, tree=tree, files=files, contents=contents)

    def _download_tarball(
        self, owner: str, repo: str, branch: str
    ) -> tuple[list[str], list[RepoFile], dict[str, str]]:
        """Fetch the whole repo as one gzipped tar and read it in-memory.

        Builds a full content map (path -> text) for all eligible source files up
        to a total budget, so the researcher agent can assign specific files to
        each specialist — the key to capturing deep context.
        """
        resp = self._client.get(f"{API}/repos/{owner}/{repo}/tarball/{branch}")
        resp.raise_for_status()

        tree: list[str] = []
        selected: list[tuple[int, tarfile.TarInfo, str]] = []
        files: list[RepoFile] = []
        contents: dict[str, str] = {}
        total_budget = 3_000_000  # ~3MB of source kept in memory
        used = 0

        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                # Strip the leading "owner-repo-sha/" directory the tarball adds.
                rel = member.name.split("/", 1)[1] if "/" in member.name else member.name
                if not rel:
                    continue
                tree.append(rel)
                score = self._score(rel, member.size)
                if score <= 0:
                    continue
                selected.append((score, member, rel))
                # Populate the full content map within budget.
                if used < total_budget and len(contents) < 400:
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        raw = extracted.read(self.max_bytes)
                        text = raw.decode("utf-8", errors="replace")
                        contents[rel] = text
                        used += len(text)

            selected.sort(key=lambda t: t[0], reverse=True)
            for _score, _member, rel in selected[:16]:
                body = contents.get(rel)
                if body:
                    files.append(RepoFile(path=rel, content=body))

        tree.sort()
        return tree[: self.max_files], files, contents

    def _score(self, path: str, size: int) -> int:
        lower = path.lower()
        if any(skip in lower for skip in SKIP_DIRS):
            return 0
        ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
        if ext not in CODE_EXTENSIONS:
            return 0
        if size > self.max_bytes * 4:
            return 0
        score = 1
        if INTERESTING_PATTERNS.search(lower):
            score += 5
        if path.count("/") <= 1:
            score += 2
        if lower.endswith("readme.md"):
            score += 6
        if any(k in lower for k in ("migration", "schema", "model", "entity")):
            score += 4
        return score
