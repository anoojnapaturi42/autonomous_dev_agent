from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from autonomous_dev_agent.cloning import GitHubRepositoryReference, GitRepositoryCloner


class GitHubRepositoryReferenceTestCase(unittest.TestCase):
    def test_parses_https_url(self) -> None:
        ref = GitHubRepositoryReference.from_value("https://github.com/octocat/Hello-World")

        assert ref is not None
        self.assertEqual(ref.owner, "octocat")
        self.assertEqual(ref.repository_name, "Hello-World")
        self.assertEqual(ref.clone_url, "https://github.com/octocat/Hello-World.git")

    def test_parses_ssh_url(self) -> None:
        ref = GitHubRepositoryReference.from_value("git@github.com:octocat/Hello-World.git")

        assert ref is not None
        self.assertEqual(ref.owner, "octocat")
        self.assertEqual(ref.repository_name, "Hello-World")

    def test_parses_owner_repo_shorthand(self) -> None:
        ref = GitHubRepositoryReference.from_value("octocat/Hello-World")

        assert ref is not None
        self.assertEqual(ref.owner, "octocat")
        self.assertEqual(ref.repository_name, "Hello-World")

    def test_rejects_local_paths(self) -> None:
        self.assertIsNone(GitHubRepositoryReference.from_value("/some/local/path"))


class GitRepositoryClonerTestCase(unittest.TestCase):
    def test_clone_invokes_git_with_expected_arguments(self) -> None:
        cloner = GitRepositoryCloner()
        fake_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("autonomous_dev_agent.cloning.subprocess.run", return_value=fake_completed) as mock_run:
            result = cloner.clone(
                "octocat/Hello-World",
                destination="/tmp/some-destination",
                branch="main",
            )

        called_command = mock_run.call_args.args[0]
        self.assertIn("clone", called_command)
        self.assertIn("--branch", called_command)
        self.assertIn("main", called_command)
        self.assertIn("https://github.com/octocat/Hello-World.git", called_command)
        self.assertEqual(result.source_url, "https://github.com/octocat/Hello-World.git")
        self.assertEqual(result.repository_name, "Hello-World")

    def test_clone_embeds_token_in_command_but_not_in_stored_result(self) -> None:
        cloner = GitRepositoryCloner(github_token="secret-token")
        fake_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("autonomous_dev_agent.cloning.subprocess.run", return_value=fake_completed) as mock_run:
            result = cloner.clone("octocat/Hello-World", destination="/tmp/some-destination")

        called_command = mock_run.call_args.args[0]
        fetch_url = called_command[-2]
        self.assertIn("secret-token", fetch_url)
        # The stored result must never contain the token, so it is safe to
        # persist in memory files, logs, or CLI output.
        self.assertNotIn("secret-token", result.source_url)
        self.assertNotIn("secret-token", str(result.to_dict()))

    def test_clone_does_not_embed_token_for_non_github_urls(self) -> None:
        # _normalize_source resolves any recognized GitHub reference (https,
        # ssh, or owner/repo shorthand) to the same https clone_url, so
        # token embedding is judged on that resolved URL. A URL that stays
        # non-GitHub (e.g. another git host) must never get the token.
        cloner = GitRepositoryCloner(github_token="secret-token")
        fake_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("autonomous_dev_agent.cloning.subprocess.run", return_value=fake_completed) as mock_run:
            cloner.clone("https://gitlab.com/octocat/Hello-World.git", destination="/tmp/dest")

        called_command = mock_run.call_args.args[0]
        fetch_url = called_command[-2]
        self.assertNotIn("secret-token", fetch_url)
        self.assertEqual(fetch_url, "https://gitlab.com/octocat/Hello-World.git")

    def test_clone_embeds_token_for_ssh_shorthand_since_it_resolves_to_https(self) -> None:
        # SSH-form GitHub references are normalized to an https clone_url
        # before the command is built, so the token is correctly applied to
        # the URL that will actually be used for the outgoing request.
        cloner = GitRepositoryCloner(github_token="secret-token")
        fake_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        with patch("autonomous_dev_agent.cloning.subprocess.run", return_value=fake_completed) as mock_run:
            cloner.clone("git@github.com:octocat/Hello-World.git", destination="/tmp/dest")

        called_command = mock_run.call_args.args[0]
        fetch_url = called_command[-2]
        self.assertIn("secret-token", fetch_url)
        self.assertTrue(fetch_url.startswith("https://x-access-token:secret-token@github.com/"))

    def test_clone_local_repository_wraps_result_in_local_repository(self) -> None:
        cloner = GitRepositoryCloner()
        fake_completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        fixture_root = Path(__file__).resolve().parents[1] / "eval_repos" / "toy"

        with patch("autonomous_dev_agent.cloning.subprocess.run", return_value=fake_completed):
            with patch(
                "autonomous_dev_agent.cloning.GitRepositoryCloner._resolve_destination",
                return_value=fixture_root,
            ):
                repository = cloner.clone_local_repository("octocat/Hello-World")

        self.assertEqual(repository.root, fixture_root.resolve())


if __name__ == "__main__":
    unittest.main()
