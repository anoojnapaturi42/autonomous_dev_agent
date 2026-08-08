"""Minimal GitHub REST API client for issue fetching and pull request creation.

Kept separate from `cloning.py` (which only shells out to `git clone`) and
from `workspace.py` (which only performs local git operations): this module
is the one place that speaks to the GitHub REST API over HTTP. Uses the
standard library's `urllib` rather than adding a `requests` dependency,
since the two calls this module needs (fetch an issue, open a PR) don't
justify a new dependency.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_API_ROOT = "https://api.github.com"
_ISSUE_URL_RE = re.compile(
    r"^(?:https?://)?(?:github\.com/)?(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/issues/(?P<number>\d+)/?$"
)


class GitHubAPIError(RuntimeError):
    """Raised when a GitHub API request fails."""


@dataclass(frozen=True, slots=True)
class GitHubIssue:
    """A fetched GitHub issue, trimmed to what the agent needs."""

    owner: str
    repository: str
    number: int
    title: str
    body: str
    html_url: str
    labels: tuple[str, ...]

    @property
    def objective(self) -> str:
        """A single string combining the issue title and body, suitable as
        the autonomous engineer's objective."""

        body = self.body.strip() if self.body else "(no description provided)"
        return f"Fix issue #{self.number}: {self.title}\n\n{body}"

    def to_dict(self) -> dict[str, object]:
        return {
            "owner": self.owner,
            "repository": self.repository,
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "html_url": self.html_url,
            "labels": list(self.labels),
        }


@dataclass(frozen=True, slots=True)
class PullRequestResult:
    """A successfully created pull request."""

    number: int
    html_url: str
    title: str

    def to_dict(self) -> dict[str, object]:
        return {"number": self.number, "html_url": self.html_url, "title": self.title}


def parse_issue_reference(value: str) -> tuple[str, str, int] | None:
    """Parse an issue URL like https://github.com/owner/repo/issues/123
    into (owner, repo, number), or return None if it doesn't match."""

    match = _ISSUE_URL_RE.match(value.strip())
    if not match:
        return None
    return match.group("owner"), match.group("repo"), int(match.group("number"))


class GitHubClient:
    """Thin wrapper around the subset of the GitHub REST API this agent needs."""

    def __init__(self, *, token: str | None = None, api_root: str = _API_ROOT) -> None:
        self._token = token
        self._api_root = api_root.rstrip("/")

    def fetch_issue(self, owner: str, repository: str, number: int) -> GitHubIssue:
        payload = self._request(
            "GET", f"/repos/{owner}/{repository}/issues/{number}"
        )
        labels = tuple(
            label.get("name", "") if isinstance(label, dict) else str(label)
            for label in payload.get("labels", [])
        )
        return GitHubIssue(
            owner=owner,
            repository=repository,
            number=number,
            title=str(payload.get("title", "")),
            body=str(payload.get("body") or ""),
            html_url=str(payload.get("html_url", "")),
            labels=labels,
        )

    def create_pull_request(
        self,
        owner: str,
        repository: str,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> PullRequestResult:
        payload = self._request(
            "POST",
            f"/repos/{owner}/{repository}/pulls",
            data={"title": title, "head": head, "base": base, "body": body},
        )
        return PullRequestResult(
            number=int(payload.get("number", 0)),
            html_url=str(payload.get("html_url", "")),
            title=str(payload.get("title", title)),
        )

    def _request(self, method: str, path: str, *, data: dict[str, object] | None = None) -> dict[str, object]:
        url = f"{self._api_root}{path}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise GitHubAPIError(
                f"GitHub API request {method} {path} failed with {exc.code}: {detail}"
            ) from exc
        except URLError as exc:
            raise GitHubAPIError(f"GitHub API request {method} {path} failed: {exc.reason}") from exc

        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise GitHubAPIError(f"GitHub API returned malformed JSON for {method} {path}") from exc
        if not isinstance(parsed, dict):
            raise GitHubAPIError(f"GitHub API returned an unexpected payload shape for {method} {path}")
        return parsed
