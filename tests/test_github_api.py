from __future__ import annotations

import json
import unittest
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from autonomous_dev_agent.github_api import (
    GitHubAPIError,
    GitHubClient,
    parse_issue_reference,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None


class ParseIssueReferenceTestCase(unittest.TestCase):
    def test_parses_full_https_url(self) -> None:
        result = parse_issue_reference("https://github.com/octocat/Hello-World/issues/42")
        self.assertEqual(result, ("octocat", "Hello-World", 42))

    def test_parses_url_without_scheme(self) -> None:
        result = parse_issue_reference("github.com/octocat/Hello-World/issues/7")
        self.assertEqual(result, ("octocat", "Hello-World", 7))

    def test_rejects_non_issue_urls(self) -> None:
        self.assertIsNone(parse_issue_reference("https://github.com/octocat/Hello-World"))
        self.assertIsNone(parse_issue_reference("https://github.com/octocat/Hello-World/pull/5"))


class GitHubClientTestCase(unittest.TestCase):
    def test_fetch_issue_parses_title_body_and_labels(self) -> None:
        payload = {
            "title": "Bug: crashes on startup",
            "body": "Steps to reproduce...",
            "html_url": "https://github.com/octocat/Hello-World/issues/42",
            "labels": [{"name": "bug"}, {"name": "priority:high"}],
        }
        client = GitHubClient(token="test-token")

        with patch("autonomous_dev_agent.github_api.urlopen", return_value=_FakeResponse(payload)) as mock_urlopen:
            issue = client.fetch_issue("octocat", "Hello-World", 42)

        self.assertEqual(issue.title, "Bug: crashes on startup")
        self.assertEqual(issue.labels, ("bug", "priority:high"))
        self.assertIn("Fix issue #42", issue.objective)
        self.assertIn("Steps to reproduce", issue.objective)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
        self.assertIn("/repos/octocat/Hello-World/issues/42", request.full_url)

    def test_fetch_issue_handles_missing_body(self) -> None:
        payload = {"title": "No description", "html_url": "", "labels": []}
        client = GitHubClient()

        with patch("autonomous_dev_agent.github_api.urlopen", return_value=_FakeResponse(payload)):
            issue = client.fetch_issue("octocat", "Hello-World", 1)

        self.assertEqual(issue.body, "")
        self.assertIn("(no description provided)", issue.objective)

    def test_create_pull_request_sends_expected_payload(self) -> None:
        response_payload = {
            "number": 99,
            "html_url": "https://github.com/octocat/Hello-World/pull/99",
            "title": "Fix #42: Bug",
        }
        client = GitHubClient(token="test-token")

        with patch(
            "autonomous_dev_agent.github_api.urlopen", return_value=_FakeResponse(response_payload)
        ) as mock_urlopen:
            result = client.create_pull_request(
                "octocat",
                "Hello-World",
                head="autonomous-dev-agent/fix-42",
                base="main",
                title="Fix #42: Bug",
                body="Closes #42.",
            )

        self.assertEqual(result.number, 99)
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        sent_payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(sent_payload["head"], "autonomous-dev-agent/fix-42")
        self.assertEqual(sent_payload["base"], "main")

    def test_request_raises_github_api_error_on_http_error(self) -> None:
        client = GitHubClient(token="test-token")
        http_error = HTTPError(
            url="https://api.github.com/repos/octocat/Hello-World/issues/42",
            code=404,
            msg="Not Found",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b'{"message": "Not Found"}'),
        )

        with patch("autonomous_dev_agent.github_api.urlopen", side_effect=http_error):
            with self.assertRaises(GitHubAPIError):
                client.fetch_issue("octocat", "Hello-World", 42)


if __name__ == "__main__":
    unittest.main()
