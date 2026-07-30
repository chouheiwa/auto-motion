#!/usr/bin/env python3

import argparse
import concurrent.futures
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Tuple
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_COMMAND = REPOSITORY_ROOT / "archive-project.sh"
sys.path.insert(0, str(REPOSITORY_ROOT / "lib"))

import archive_project


class ArchiveProjectParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary_directory.name) / "hermetic-repository"
        self.repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=self.repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Archive Test"],
            cwd=self.repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "archive@example.invalid"],
            cwd=self.repo,
            check=True,
        )
        (self.repo / "README.md").write_text("safe\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=self.repo, check=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=self.repo,
            capture_output=True,
            check=True,
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_command(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(ARCHIVE_COMMAND), *arguments],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def assert_parser_error(
        self, arguments: Tuple[str, ...], expected_message: str
    ) -> None:
        result = self.run_command(*arguments)

        self.assertEqual(result.returncode, 2, result)
        self.assertIn(expected_message, result.stderr)

    def test_help_describes_the_command_contract(self) -> None:
        result = self.run_command("--help")

        self.assertEqual(result.returncode, 0, result)
        self.assertIn("usage:", result.stdout)
        for option in (
            "--archive-root",
            "--archive-name",
            "--main-ref",
            "--dry-run",
            "--archive-only",
            "--next-project",
            "--confirm-clean",
        ):
            self.assertIn(option, result.stdout)

    def test_unknown_flags_are_rejected(self) -> None:
        self.assert_parser_error(
            ("--not-a-real-option",),
            "unrecognized arguments: --not-a-real-option",
        )

    def test_near_miss_flags_are_not_abbreviated(self) -> None:
        self.assert_parser_error(
            ("--confirm-clea",),
            "unrecognized arguments: --confirm-clea",
        )

    def test_archive_only_executes_the_archive_transaction(self) -> None:
        archive_root = self.repo.parent / "parser archive"
        result = self.run_command(
            "--archive-only",
            "--archive-root",
            str(archive_root),
            "--archive-name",
            "snapshot",
        )

        self.assertEqual(result.returncode, 0, result)
        self.assertTrue((archive_root / "snapshot").is_dir())
        self.assertIn("archive verification: passed", result.stdout)

    def test_confirmed_cleanup_on_protected_branch_is_rejected(self) -> None:
        result = self.run_command(
            "--next-project", "next-video", "--confirm-clean"
        )
        self.assertEqual(result.returncode, 1, result)
        self.assertEqual(result.stdout, "")
        self.assertIn("protected branch", result.stderr)

    def test_archive_only_rejects_next_project(self) -> None:
        self.assert_parser_error(
            ("--archive-only", "--next-project", "next-video"),
            "--archive-only cannot be combined with --next-project",
        )

    def test_archive_only_rejects_cleanup_confirmation(self) -> None:
        self.assert_parser_error(
            ("--archive-only", "--confirm-clean"),
            "--archive-only cannot be combined with --confirm-clean",
        )

    def test_cleanup_requires_explicit_confirmation(self) -> None:
        self.assert_parser_error(
            ("--next-project", "next-video"),
            "cleanup mode requires --confirm-clean",
        )

    def test_cleanup_requires_a_next_project(self) -> None:
        self.assert_parser_error(
            ("--confirm-clean",),
            "cleanup mode requires --next-project",
        )

    def test_next_project_must_have_a_nonempty_sanitized_id(self) -> None:
        self.assert_parser_error(
            ("--next-project", "!!!", "--confirm-clean"),
            "--next-project must contain letters or numbers",
        )

    def test_archive_name_rejects_unsafe_values(self) -> None:
        for archive_name in (
            "",
            "   ",
            "nested/name",
            r"nested\name",
            ".",
            "..",
            "line\nbreak",
            "tab\tname",
            "unit\x1fname",
            "delete\x7fname",
            "c1\u0085name",
        ):
            with self.subTest(archive_name=archive_name):
                self.assert_parser_error(
                    ("--archive-only", "--archive-name", archive_name),
                    "--archive-name must be a single safe directory name",
                )


class PreflightTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temporary_directory.name)
        self.repo = self.test_root / "项目 with spaces"
        self.repo.mkdir()
        self.git("init", "-b", "project/current")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")
        self.write("README.md", "safe project\n")
        self.git("add", "README.md")
        self.git("commit", "-m", "initial")
        self.git("branch", "main")
        self.archive_root = self.test_root / "archives not created"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(
        self, *arguments: str, cwd: Path = None
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *arguments],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            check=True,
        )

    def write(self, relative: str, content: object = "content\n") -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding="utf-8")
        return path

    def args(self, *extra: str) -> argparse.Namespace:
        arguments = [
            "--archive-only",
            "--dry-run",
            "--archive-root",
            str(self.archive_root),
            "--archive-name",
            "snapshot",
            *extra,
        ]
        return archive_project.parse_args(arguments)

    def cleanup_args(self, *extra: str) -> argparse.Namespace:
        return archive_project.parse_args(
            [
                "--next-project",
                "下一部 Film",
                "--confirm-clean",
                "--dry-run",
                "--archive-root",
                str(self.archive_root),
                "--archive-name",
                "snapshot",
                *extra,
            ]
        )

    def preflight(self, args: argparse.Namespace = None) -> "archive_project.Preflight":
        with mock.patch.object(
            archive_project, "current_timestamp", return_value="20260730-120000"
        ):
            return archive_project.run_preflight(args or self.args(), self.repo)

    def remove_git_history(self) -> None:
        shutil.rmtree(self.repo / ".git")
        self.git("init", "-b", "project/unborn")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")

    def test_requires_the_exact_safe_worktree_root(self) -> None:
        nested = self.repo / "nested"
        nested.mkdir()
        for unsafe in (nested, self.repo.parent, Path("/"), Path.home()):
            with self.subTest(path=unsafe):
                with self.assertRaisesRegex(
                    archive_project.PreflightError,
                    "exact Git worktree root|unsafe source",
                ):
                    archive_project.discover_repository(unsafe)

        state = archive_project.discover_repository(self.repo)
        self.assertEqual(state.root, self.repo.resolve())

    def test_resolves_local_base_refs_without_fetching(self) -> None:
        main_commit = self.git("rev-parse", "main").stdout.strip()
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")
        state = archive_project.discover_repository(self.repo)
        original = archive_project._run_git
        calls = []

        def recording_git(*arguments, **kwargs):
            calls.append(arguments[1])
            return original(*arguments, **kwargs)

        with mock.patch.object(
            archive_project, "_run_git", side_effect=recording_git
        ):
            preferred = archive_project.resolve_base_ref(state, None)
        self.assertEqual(preferred.name, "origin/main")
        self.assertEqual(preferred.commit, main_commit)
        self.assertFalse(any("fetch" in call for call in calls))

        self.git("update-ref", "-d", "refs/remotes/origin/main")
        fallback = archive_project.resolve_base_ref(state, None)
        explicit = archive_project.resolve_base_ref(state, "HEAD")
        self.assertEqual(fallback.name, "main")
        self.assertEqual(explicit.commit, main_commit)

        for invalid in ("missing-ref", "README.md"):
            with self.subTest(ref=invalid):
                with self.assertRaisesRegex(
                    archive_project.PreflightError, "local commit"
                ):
                    archive_project.resolve_base_ref(state, invalid)

    def test_preflight_git_inspection_does_not_refresh_the_index(self) -> None:
        index = self.repo / ".git" / "index"
        readme = self.repo / "README.md"
        current = readme.stat()
        os.utime(
            str(readme),
            ns=(
                current.st_atime_ns,
                current.st_mtime_ns + 5_000_000_000,
            ),
        )
        before = index.stat().st_mtime_ns

        self.preflight()

        self.assertEqual(index.stat().st_mtime_ns, before)

    def test_cleanup_rejects_protected_detached_and_unborn_states_read_only(self) -> None:
        cases = []
        self.git("switch", "main")
        cases.append(("protected", self.repo))

        detached = self.test_root / "detached"
        self.git("clone", str(self.repo), str(detached), cwd=self.test_root)
        self.git("switch", "--detach", "HEAD", cwd=detached)
        cases.append(("detached", detached))

        unborn = self.test_root / "unborn"
        unborn.mkdir()
        self.git("init", "-b", "project/unborn", cwd=unborn)
        cases.append(("unborn", unborn))

        for label, repository in cases:
            archive_root = repository.parent / (label + "-archive")
            args = archive_project.parse_args(
                [
                    "--next-project",
                    "next",
                    "--confirm-clean",
                    "--dry-run",
                    "--archive-root",
                    str(archive_root),
                    "--archive-name",
                    "snapshot",
                ]
            )
            with self.subTest(state=label):
                with self.assertRaisesRegex(
                    archive_project.PreflightError,
                    "protected|detached|unborn",
                ):
                    archive_project.run_preflight(args, repository)
                self.assertFalse(archive_root.exists())
                self.assertFalse(
                    Path(str(archive_root / "snapshot") + ".reset-result.json").exists()
                )
                branches = self.git(
                    "for-each-ref",
                    "--format=%(refname)",
                    "refs/heads/project/next-",
                    cwd=repository,
                ).stdout
                self.assertEqual(branches, "")

    def test_archive_only_supports_named_detached_and_unborn_heads(self) -> None:
        named = self.preflight()
        self.assertEqual(named.old_branch, "project/current")
        self.assertIsNotNone(named.old_commit)

        self.git("switch", "--detach", "HEAD")
        detached = self.preflight()
        self.assertIsNone(detached.old_branch)
        self.assertIsNotNone(detached.old_commit)
        self.assertEqual(detached.project_id, "项目-with-spaces")

        self.remove_git_history()
        unborn = self.preflight()
        self.assertEqual(unborn.old_branch, "project/unborn")
        self.assertIsNone(unborn.old_commit)
        self.assertEqual(unborn.project_id, "project-unborn")

    def test_project_id_prefers_config_then_branch_then_directory(self) -> None:
        config = self.write(
            "production/production-config.json",
            json.dumps({"project_id": "  Café / 第一期  "}),
        )
        self.git("add", str(config.relative_to(self.repo)))
        self.git("commit", "-m", "config")
        configured = self.preflight()
        self.assertEqual(configured.project_id, "café-第一期")

        config.unlink()
        branch = self.preflight()
        self.assertEqual(branch.project_id, "project-current")

        self.git("switch", "--detach", "HEAD")
        directory = self.preflight()
        self.assertEqual(directory.project_id, "项目-with-spaces")

    def test_project_config_accepts_likely_identifier_keys(self) -> None:
        for key in ("projectId", "project_id", "id"):
            with self.subTest(key=key):
                self.write(
                    "production/production-config.json",
                    json.dumps({key: "Portable_Name"}),
                )
                result = self.preflight()
                self.assertEqual(result.project_id, "portable-name")

    def test_cleanup_blocks_existing_or_other_worktree_branch(self) -> None:
        new_branch = "project/下一部-film-20260730-120000"
        self.git("branch", new_branch)
        with self.assertRaisesRegex(
            archive_project.PreflightError, "branch already exists"
        ):
            self.preflight(self.cleanup_args())

        self.git("branch", "-D", new_branch)
        other = self.test_root / "other-worktree"
        self.git("worktree", "add", "-b", new_branch, str(other), "main")
        with self.assertRaisesRegex(
            archive_project.PreflightError, "checked out|already exists"
        ):
            self.preflight(self.cleanup_args())

    def test_archive_and_reset_result_collisions_block(self) -> None:
        self.archive_root.mkdir()
        final = self.archive_root / "snapshot"
        for collision in (final, Path(str(final) + ".reset-result.json")):
            with self.subTest(collision=collision):
                if collision.suffix == ".json":
                    collision.write_text("existing", encoding="utf-8")
                else:
                    collision.mkdir()
                with self.assertRaisesRegex(
                    archive_project.PreflightError, "already exists"
                ):
                    self.preflight()
                if collision.is_dir():
                    collision.rmdir()
                else:
                    collision.unlink()

    def test_dangling_symlink_archive_collisions_block(self) -> None:
        self.archive_root.mkdir()
        final = self.archive_root / "snapshot"
        reset_result = Path(str(final) + ".reset-result.json")
        for collision in (final, reset_result):
            with self.subTest(collision=collision):
                collision.symlink_to("missing-target")
                with self.assertRaisesRegex(
                    archive_project.PreflightError, "already exists"
                ):
                    self.preflight()
                collision.unlink()

    def test_destination_must_be_outside_source_and_name_must_be_safe(self) -> None:
        inside = self.args()
        inside.archive_root = str(self.repo / "archive")
        with self.assertRaisesRegex(
            archive_project.PreflightError, "outside the source"
        ):
            self.preflight(inside)

        for name in ("../escape", "nested/name", ".", "line\nbreak"):
            with self.subTest(name=name):
                with self.assertRaises(SystemExit):
                    archive_project.parse_args(
                        ["--archive-only", "--dry-run", "--archive-name", name]
                    )

    def test_existing_archive_root_must_be_a_directory(self) -> None:
        self.archive_root.write_text("not a directory", encoding="utf-8")

        with self.assertRaisesRegex(
            archive_project.PreflightError, "archive root.*directory"
        ):
            self.preflight()

    def test_archive_root_parent_must_resolve_through_a_directory(self) -> None:
        regular_ancestor = self.test_root / "not-a-directory"
        regular_ancestor.write_text("file ancestor", encoding="utf-8")
        args = self.args()
        args.archive_root = str(regular_ancestor / "child")

        with self.assertRaisesRegex(
            archive_project.PreflightError,
            "nearest existing archive.*directory",
        ):
            self.preflight(args)

    def test_tracked_env_example_is_included_and_scanned(self) -> None:
        env = self.write(".env.example", "OPENAI_API_KEY=sk-xxxxx\n")
        self.git("add", ".env.example")
        self.git("commit", "-m", "example")
        result = self.preflight()
        self.assertIn(".env.example", {entry.path for entry in result.inventory})

        env.write_text(
            "OPENAI_API_KEY=sk-" + ("a" * 32) + "\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(
            archive_project.PreflightError, r"\.env\.example.*credential"
        ) as caught:
            self.preflight()
        self.assertNotIn("sk-" + ("a" * 32), str(caught.exception))

    def test_tracked_env_example_rejects_credential_assignments_redacted(self) -> None:
        env = self.write(".env.example", "API_KEY=sk-xxxxx\n")
        self.git("add", ".env.example")
        self.git("commit", "-m", "safe placeholder")
        env.write_text("API_KEY=<your-api-key>\n", encoding="utf-8")
        self.assertIn(
            ".env.example",
            {entry.path for entry in self.preflight().inventory},
        )
        assignments = (
            "API_KEY",
            "api-key",
            "ACCESS_TOKEN",
            "ToKeN",
        )
        for key in assignments:
            value = (
                "AbCdEfGhIjKlMnOpQrSt1234"
                if key.lower() == "token"
                else "credential-value-" + key.replace("_", "-")
            )
            with self.subTest(key=key):
                env.write_text(
                    "{}={}\n".format(key, value), encoding="utf-8"
                )
                with self.assertRaisesRegex(
                    archive_project.PreflightError, "credential"
                ) as caught:
                    self.preflight()
                self.assertNotIn(value, str(caught.exception))

    def test_secret_scanner_handles_structured_and_bearer_credentials(self) -> None:
        examples = (
            b'{"api_key": "real-api-key-value-123456"}',
            b'{"api_key": "real(key)-value-123456"}',
            b"password: correct horse battery staple",
            b'password="correct(horse)battery-staple"',
            b"API_KEY=real-shell-key-value-123456",
            b"token = 0123456789abcdef0123456789abcdef",
            b'Authorization: Bearer header.payload.signature',
        )
        for content in examples:
            with self.subTest(content=content[:12]):
                rule = archive_project.scan_secret_stream(
                    "settings.txt", io.BytesIO(content)
                )
                self.assertIsNotNone(rule)
                self.assertNotIn(
                    content.decode("utf-8"), rule
                )

    def test_secret_scanner_ignores_ordinary_token_source_and_placeholders(self) -> None:
        examples = (
            b"token = parser.current_token",
            b'const token = "punctuation-token"',
            b'api_key = os.environ.get("API_KEY")',
            b"password: Optional[str] = None",
            b"password = request.password",
            b"password = build_password(defaults)",
            b"default_password = 'fixture-password-value'",
            b"not_api_key = 'fixture-api-key-value'",
            b"mock_secret = 'fixture-secret-value'",
            b'{"api_key": "<your-api-key>"}',
            b"API_KEY=sk-xxxxx",
        )
        for content in examples:
            with self.subTest(content=content[:16]):
                self.assertIsNone(
                    archive_project.scan_secret_stream(
                        "source.py", io.BytesIO(content)
                    )
                )

    def test_file_inventory_rejects_mutation_after_single_pass_read(self) -> None:
        source = self.write("race.txt", b"A" * 8192)

        def mutate_after_read(path: Path) -> None:
            if path.name == source.name:
                with path.open("ab") as stream:
                    stream.write(b"changed")

        with mock.patch.object(
            archive_project,
            "_after_file_read",
            side_effect=mutate_after_read,
            create=True,
        ):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "changed while being read"
            ):
                self.preflight()

    def test_filesystem_errors_are_redacted_preflight_failures(self) -> None:
        leaked = "/private/absolute/credential-value"
        with mock.patch(
            "pathlib.Path.open", side_effect=PermissionError(leaked)
        ):
            with self.assertRaises(archive_project.PreflightError) as caught:
                self.preflight()
        self.assertNotIn(leaked, str(caught.exception))

        target = self.write("target.txt", "safe")
        link = self.repo / "link"
        link.symlink_to(target.name)
        with mock.patch.object(
            archive_project.os,
            "readlink",
            side_effect=OSError(leaked),
        ):
            with self.assertRaises(archive_project.PreflightError) as caught:
                self.preflight()
        self.assertNotIn(leaked, str(caught.exception))

        with mock.patch.object(
            archive_project,
            "capture_identity",
            side_effect=PermissionError(leaked),
        ):
            with self.assertRaises(archive_project.PreflightError) as caught:
                self.preflight()
        self.assertNotIn(leaked, str(caught.exception))

    def test_sensitive_paths_and_deleted_tracked_sensitive_paths_fail(self) -> None:
        for relative in (
            ".env",
            ".env.production",
            "private/server.pem",
            "auth/credentials.json",
        ):
            with self.subTest(path=relative):
                path = self.write(relative, "secret-value")
                with self.assertRaisesRegex(
                    archive_project.PreflightError, "sensitive path"
                ) as caught:
                    self.preflight()
                self.assertNotIn("secret-value", str(caught.exception))
                path.unlink()
                parent = path.parent
                while parent != self.repo and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent

        deleted = self.write(".env.local", "historic-secret")
        self.git("add", ".env.local")
        self.git("commit", "-m", "tracked sensitive")
        deleted.unlink()
        with self.assertRaisesRegex(
            archive_project.PreflightError, r"\.env\.local.*sensitive path"
        ) as caught:
            self.preflight()
        self.assertNotIn("historic-secret", str(caught.exception))

    def test_auth_path_component_is_sensitive(self) -> None:
        self.write("auth/session.json", "safe")

        with self.assertRaisesRegex(
            archive_project.PreflightError, "sensitive path"
        ):
            self.preflight()

    def test_spaces_and_unicode_are_allowed_but_control_characters_fail(self) -> None:
        self.write("镜头 folder/clip one.txt", "safe")
        result = self.preflight()
        self.assertIn(
            "镜头 folder/clip one.txt", {entry.path for entry in result.inventory}
        )

        bad = self.write("bad\nname.txt", "safe")
        try:
            with self.assertRaisesRegex(
                archive_project.PreflightError, "control character"
            ):
                self.preflight()
        finally:
            bad.unlink()

    def test_deleted_tracked_control_character_path_fails(self) -> None:
        bad = self.write("deleted\nname.txt", "safe")
        self.git("add", str(bad.relative_to(self.repo)))
        self.git("commit", "-m", "control path")
        bad.unlink()

        with self.assertRaisesRegex(
            archive_project.PreflightError, "control character"
        ):
            self.preflight()

    def test_symlink_rules_and_special_file_rejection(self) -> None:
        target = self.write("assets/target.txt", "safe")
        link = self.repo / "link"
        link.symlink_to("assets/target.txt")
        result = self.preflight()
        entry = next(item for item in result.inventory if item.path == "link")
        self.assertEqual(entry.kind, "symlink")
        self.assertEqual(entry.link_target, "assets/target.txt")
        link.unlink()

        external = self.test_root / "external.txt"
        external.write_text("safe", encoding="utf-8")
        cases = (
            str(external),
            "../external.txt",
            "missing.txt",
            "node_modules/package/file.js",
        )
        for target_value in cases:
            with self.subTest(target=target_value):
                link.symlink_to(target_value)
                with self.assertRaisesRegex(
                    archive_project.PreflightError,
                    "symlink|absolute|outside|dangling|excluded",
                ):
                    self.preflight()
                link.unlink()

        fifo = self.repo / "pipe"
        os.mkfifo(str(fifo))
        try:
            with self.assertRaisesRegex(
                archive_project.PreflightError, "special file"
            ):
                self.preflight()
        finally:
            fifo.unlink()

    def test_symlink_chain_rejects_excluded_hops_and_external_returns(self) -> None:
        self.write("assets/target.txt", "safe")
        excluded = self.repo / "node_modules"
        excluded.mkdir()
        (excluded / "bridge").symlink_to("../assets/target.txt")
        link = self.repo / "link"
        link.symlink_to("node_modules/bridge")
        with self.assertRaisesRegex(
            archive_project.PreflightError, "excluded"
        ):
            self.preflight()
        link.unlink()

        outside_return = self.test_root / "outside-return"
        outside_return.symlink_to(self.repo / "assets" / "target.txt")
        link.symlink_to("../outside-return")
        with self.assertRaisesRegex(
            archive_project.PreflightError, "outside"
        ):
            self.preflight()

    def test_inventory_records_standard_exclusions(self) -> None:
        self.write("node_modules/pkg/index.js")
        self.write(".cache/tool/state")
        self.write("__pycache__/module.pyc", b"\0")
        self.write(".DS_Store")
        result = self.preflight()
        exclusions = {item.path for item in result.exclusions}
        self.assertTrue(
            {".git", "node_modules", ".cache", "__pycache__", ".DS_Store"}
            <= exclusions
        )

    def test_os_junk_names_only_exclude_regular_files(self) -> None:
        self.write(".DS_Store/payload.txt", "safe")
        self.write("target.txt", "safe")
        (self.repo / "Thumbs.db").symlink_to("target.txt")

        result = self.preflight()

        entries = {item.path: item.kind for item in result.inventory}
        self.assertEqual(entries[".DS_Store"], "directory")
        self.assertEqual(entries[".DS_Store/payload.txt"], "file")
        self.assertEqual(entries["Thumbs.db"], "symlink")

    def test_required_command_and_free_space_checks_are_patchable(self) -> None:
        with mock.patch.object(archive_project.shutil, "which", return_value=None):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "required command"
            ):
                self.preflight()

        disk_usage = shutil.disk_usage(self.test_root)
        with mock.patch.object(
            archive_project.shutil,
            "disk_usage",
            return_value=type(disk_usage)(
                disk_usage.total, disk_usage.used, 0
            ),
        ):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "free space"
            ):
                self.preflight()

    def test_captures_source_and_nearest_archive_parent_identity(self) -> None:
        result = self.preflight()
        source_stat = self.repo.stat()
        parent_stat = self.test_root.stat()
        self.assertEqual(
            (result.source_identity.device, result.source_identity.inode),
            (source_stat.st_dev, source_stat.st_ino),
        )
        self.assertEqual(
            (
                result.archive_parent_identity.device,
                result.archive_parent_identity.inode,
            ),
            (parent_stat.st_dev, parent_stat.st_ino),
        )

    def test_dry_run_prints_plan_and_creates_nothing(self) -> None:
        before_refs = self.git(
            "for-each-ref", "--format=%(refname)"
        ).stdout
        result = subprocess.run(
            [
                "bash",
                str(ARCHIVE_COMMAND),
                "--next-project",
                "next",
                "--confirm-clean",
                "--dry-run",
                "--archive-root",
                str(self.archive_root),
                "--archive-name",
                "snapshot",
            ],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("source:", result.stdout)
        self.assertIn("archive:", result.stdout)
        self.assertIn("base commit:", result.stdout)
        self.assertIn("new branch:", result.stdout)
        self.assertFalse(self.archive_root.exists())
        self.assertEqual(
            self.git("for-each-ref", "--format=%(refname)").stdout,
            before_refs,
        )


class ArchiveTransactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temporary_directory.name)
        self.repo = self.test_root / "project source"
        self.repo.mkdir()
        self.git("init", "-b", "project/current")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")
        self.write("tracked.txt", "committed\n")
        self.write("changed.txt", "before\n")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("branch", "main")
        self.write("changed.txt", "modified\n")
        self.write("loose/untracked.txt", "untracked\n")
        self.write("final.mp4", b"\x00final-video\xff")
        self.write("cache/node_modules/ignored.txt", "ignored\n")
        self.link = self.repo / "current-link"
        self.link.symlink_to("changed.txt")
        self.archive_root = self.test_root / "custom archives"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
        )

    def write(self, relative: str, content: object) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding="utf-8")
        return path

    def arguments(
        self, name: str = "snapshot", archive_root: Path = None
    ) -> list:
        return [
            "--archive-only",
            "--archive-root",
            str(archive_root or self.archive_root),
            "--archive-name",
            name,
        ]

    def run_command(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(ARCHIVE_COMMAND), *arguments],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=False,
        )

    def create(self, name: str = "snapshot") -> Path:
        result = self.run_command(*self.arguments(name))
        self.assertEqual(result.returncode, 0, result)
        return self.archive_root / name

    def test_archive_only_uses_overridden_and_default_sibling_paths(self) -> None:
        final = self.create("chosen-name")
        self.assertTrue(final.is_dir())

        default_name = "default-name"
        result = self.run_command(
            "--archive-only", "--archive-name", default_name
        )
        self.assertEqual(result.returncode, 0, result)
        self.assertTrue((self.test_root / "_archive" / default_name).is_dir())

    def test_snapshot_preserves_exact_content_and_internal_symlink(self) -> None:
        final = self.create()
        snapshot = final / "snapshot"

        self.assertEqual(
            (snapshot / "tracked.txt").read_bytes(),
            (self.repo / "tracked.txt").read_bytes(),
        )
        self.assertEqual(
            (snapshot / "changed.txt").read_bytes(), b"modified\n"
        )
        self.assertEqual(
            (snapshot / "loose/untracked.txt").read_bytes(), b"untracked\n"
        )
        self.assertTrue((snapshot / "current-link").is_symlink())
        self.assertEqual(os.readlink(snapshot / "current-link"), "changed.txt")
        self.assertFalse((snapshot / ".git").exists())
        self.assertFalse((snapshot / "cache/node_modules").exists())

    def test_manifest_records_entries_exclusions_and_portable_metadata(self) -> None:
        final = self.create()
        manifest_bytes = (final / "archive-manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        entries = {entry["path"]: entry for entry in manifest["entries"]}

        self.assertEqual(
            manifest_bytes,
            archive_project.canonical_json(manifest),
        )
        self.assertIn(
            {"path": ".git", "rule": "git-metadata"},
            manifest["exclusions"],
        )
        self.assertIn(
            {
                "path": "cache/node_modules",
                "rule": "dependencies",
            },
            manifest["exclusions"],
        )
        self.assertEqual(entries["snapshot/current-link"]["type"], "symlink")
        self.assertEqual(
            entries["snapshot/current-link"]["target"], "changed.txt"
        )
        self.assertEqual(entries["snapshot/changed.txt"]["type"], "file")
        self.assertEqual(entries["snapshot/changed.txt"]["size"], 9)
        self.assertEqual(
            entries["snapshot/changed.txt"]["sha256"],
            hashlib.sha256(b"modified\n").hexdigest(),
        )
        self.assertEqual(
            entries["snapshot/changed.txt"]["mode"],
            stat.S_IMODE((self.repo / "changed.txt").stat().st_mode),
        )
        self.assertEqual(entries["snapshot/loose"]["type"], "directory")
        self.assertEqual(
            manifest["key_deliverables"]["snapshot/final.mp4"],
            hashlib.sha256(b"\x00final-video\xff").hexdigest(),
        )

    def test_sums_are_sorted_regular_files_only_and_identity_is_bound(self) -> None:
        final = self.create()
        manifest_bytes = (final / "archive-manifest.json").read_bytes()
        sums_bytes = (final / "SHA256SUMS").read_bytes()
        lines = sums_bytes.decode("utf-8").splitlines()
        verification = json.loads(
            (final / "archive-verification.json").read_text(encoding="utf-8")
        )

        self.assertEqual(lines, sorted(lines, key=lambda line: line[66:]))
        self.assertTrue(all("  " in line for line in lines))
        self.assertFalse(any("current-link" in line for line in lines))
        self.assertEqual(
            verification["archive_identity"],
            archive_project.archive_identity(manifest_bytes, sums_bytes),
        )
        self.assertEqual(
            archive_project.archive_identity(manifest_bytes, sums_bytes),
            hashlib.sha256(
                b"auto-motion-archive-v1\0"
                + len(manifest_bytes).to_bytes(8, "big")
                + manifest_bytes
                + len(sums_bytes).to_bytes(8, "big")
                + sums_bytes
            ).hexdigest(),
        )

    def test_sums_use_standard_backslash_filename_escaping(self) -> None:
        content = b"portable checksum path\n"
        self.write(r"back\slash.txt", content)
        final = self.create()
        sums = (final / "SHA256SUMS").read_text(encoding="utf-8")

        self.assertIn(
            "\\{}  snapshot/back\\\\slash.txt\n".format(
                hashlib.sha256(content).hexdigest()
            ),
            sums,
        )

    def test_verification_is_outside_payload_and_has_exact_totals(self) -> None:
        final = self.create()
        manifest = json.loads(
            (final / "archive-manifest.json").read_text(encoding="utf-8")
        )
        verification = json.loads(
            (final / "archive-verification.json").read_text(encoding="utf-8")
        )
        protected_paths = {entry["path"] for entry in manifest["entries"]}

        self.assertNotIn("archive-verification.json", protected_paths)
        self.assertNotIn("archive-manifest.json", protected_paths)
        self.assertNotIn("SHA256SUMS", protected_paths)
        self.assertEqual(verification["status"], "passed")
        self.assertEqual(
            verification["expected"]["entries"],
            verification["actual"]["entries"],
        )
        self.assertEqual(
            verification["expected"]["files"],
            verification["actual"]["files"],
        )
        self.assertEqual(
            verification["expected"]["bytes"],
            verification["actual"]["bytes"],
        )

    def test_generated_metadata_and_output_are_scanned_before_publication(
        self,
    ) -> None:
        credential = "sk-" + ("Z" * 32)
        args = archive_project.parse_args(self.arguments())
        preflight = archive_project.run_preflight(args, self.repo)
        with mock.patch.object(
            archive_project,
            "_recovery_timestamp",
            return_value=credential,
        ):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "credential pattern"
            ) as caught:
                archive_project.create_archive(preflight)

        self.assertFalse((self.archive_root / "snapshot").exists())
        self.assertNotIn(credential, str(caught.exception))
        if self.archive_root.exists():
            self.assertEqual(list(self.archive_root.iterdir()), [])

    def test_mid_copy_mutation_fails_and_removes_only_its_staging(self) -> None:
        args = archive_project.parse_args(self.arguments())
        preflight = archive_project.run_preflight(args, self.repo)
        original = archive_project._copy_regular_file
        mutation_done = False

        def mutate_after_copy(source, destination, entry):
            nonlocal mutation_done
            original(source, destination, entry)
            if entry.path == "changed.txt" and not mutation_done:
                mutation_done = True
                (self.repo / "changed.txt").write_text(
                    "mutated during copy\n", encoding="utf-8"
                )

        self.archive_root.mkdir()
        unrelated = self.archive_root / ".unrelated-staging"
        unrelated.mkdir()
        with mock.patch.object(
            archive_project,
            "_copy_regular_file",
            side_effect=mutate_after_copy,
        ):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "changed|mismatch"
            ):
                archive_project.create_archive(preflight)

        self.assertTrue(unrelated.is_dir())
        self.assertFalse((self.archive_root / "snapshot").exists())
        self.assertEqual(
            (self.repo / "changed.txt").read_text(encoding="utf-8"),
            "mutated during copy\n",
        )
        self.assertEqual(
            [path.name for path in self.archive_root.iterdir()],
            [".unrelated-staging"],
        )

    def test_existing_empty_nonempty_and_dangling_targets_are_never_replaced(
        self,
    ) -> None:
        self.archive_root.mkdir()
        for kind in ("empty", "nonempty", "dangling"):
            final = self.archive_root / kind
            if kind == "dangling":
                final.symlink_to("missing")
            else:
                final.mkdir()
                if kind == "nonempty":
                    (final / "keep.txt").write_text("keep\n", encoding="utf-8")
            result = self.run_command(*self.arguments(kind))
            self.assertEqual(result.returncode, 1, result)
            if kind == "dangling":
                self.assertTrue(final.is_symlink())
            else:
                self.assertTrue(final.is_dir())
                if kind == "nonempty":
                    self.assertEqual(
                        (final / "keep.txt").read_text(encoding="utf-8"),
                        "keep\n",
                    )

    def test_two_concurrent_publishers_have_one_winner_without_replacement(
        self,
    ) -> None:
        self.archive_root.mkdir()
        staging_one = self.archive_root / ".staging-one"
        staging_two = self.archive_root / ".staging-two"
        staging_one.mkdir()
        staging_two.mkdir()
        (staging_one / "winner").write_text("one", encoding="utf-8")
        (staging_two / "winner").write_text("two", encoding="utf-8")
        final = self.archive_root / "same-name"
        barrier = threading.Barrier(2)

        def publish(staging: Path) -> object:
            barrier.wait()
            try:
                archive_project.publish_directory_no_replace(staging, final)
                return "won"
            except archive_project.PreflightError:
                return "lost"

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(publish, (staging_one, staging_two)))

        self.assertEqual(sorted(results), ["lost", "won"])
        self.assertIn(
            (final / "winner").read_text(encoding="utf-8"), {"one", "two"}
        )
        self.assertEqual(
            sum(path.exists() for path in (staging_one, staging_two)), 1
        )

    def test_archive_root_swap_and_source_change_block_publication(self) -> None:
        args = archive_project.parse_args(self.arguments())
        preflight = archive_project.run_preflight(args, self.repo)
        original_publish = archive_project.publish_directory_no_replace

        def swap_root(staging, final):
            moved = self.test_root / "moved archive root"
            self.archive_root.rename(moved)
            self.archive_root.mkdir()
            original_publish(staging, final)

        with mock.patch.object(
            archive_project,
            "publish_directory_no_replace",
            side_effect=swap_root,
        ):
            with self.assertRaisesRegex(
                archive_project.PreflightError, "identity"
            ):
                archive_project.create_archive(preflight)
        self.assertFalse((self.archive_root / "snapshot").exists())

    def test_cleanup_mode_archives_then_stops_before_reset(self) -> None:
        before = self.git("status", "--porcelain=v1", "-z").stdout
        result = self.run_command(
            "--next-project",
            "next",
            "--confirm-clean",
            "--archive-root",
            str(self.archive_root),
            "--archive-name",
            "cleanup-snapshot",
        )

        self.assertEqual(result.returncode, 1, result)
        self.assertTrue((self.archive_root / "cleanup-snapshot").is_dir())
        self.assertIn("reset is not implemented", result.stderr)
        self.assertEqual(
            self.git("status", "--porcelain=v1", "-z").stdout, before
        )
        self.assertEqual(
            self.git("branch", "--show-current").stdout.strip(),
            "project/current",
        )

    def test_success_output_is_sanitized_and_formally_reverified(self) -> None:
        result = self.run_command(*self.arguments())
        self.assertEqual(result.returncode, 0, result)
        final = (self.archive_root / "snapshot").resolve()
        output = result.stdout
        manifest = json.loads(
            (final / "archive-manifest.json").read_text(encoding="utf-8")
        )

        self.assertIn(str(final), output)
        self.assertIn("archive identity:", output)
        self.assertIn("old branch: project/current", output)
        self.assertIn("old commit:", output)
        self.assertIn("excluded:", output)
        self.assertIn("archive verification: passed", output)
        verification = archive_project.verify_payload(final, manifest)
        self.assertEqual(verification.status, "passed")


class RecoveryEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.test_root = Path(self.temporary_directory.name)
        self.repo = self.test_root / "recovery source"
        self.repo.mkdir()
        self.git("init", "-b", "project/recovery")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")
        self.write("notes.txt", "base text\n")
        self.write("remove.txt", "remove this text\n")
        self.write("modified.bin", b"\x00base-binary\xff")
        self.write("deleted.bin", b"\x00deleted-binary\xfe")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.git("branch", "main")
        self.archive_root = self.test_root / "archives"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def git(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            capture_output=True,
            text=True,
            check=True,
        )

    def write(self, relative: str, content: object) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(str(content), encoding="utf-8")
        return path

    def args(self) -> argparse.Namespace:
        return archive_project.parse_args(
            [
                "--archive-only",
                "--archive-root",
                str(self.archive_root),
                "--archive-name",
                "snapshot",
            ]
        )

    def generate(self) -> Tuple[Path, "archive_project.Preflight"]:
        preflight = archive_project.run_preflight(self.args(), self.repo)
        staging = self.test_root / "recovery staging"
        staging.mkdir()
        archive_project.write_recovery_files(preflight, staging)
        return staging / "recovery", preflight

    def test_staged_only_text_changes_have_an_index_patch(self) -> None:
        self.write("notes.txt", "staged text\n")
        self.git("add", "notes.txt")

        recovery, _ = self.generate()

        self.assertIn(
            "+staged text",
            (recovery / "index-changes.patch").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            (recovery / "worktree-changes.patch").read_text(encoding="utf-8"),
            "",
        )

    def test_unstaged_only_text_changes_have_a_worktree_patch(self) -> None:
        self.write("notes.txt", "unstaged text\n")

        recovery, _ = self.generate()

        self.assertEqual(
            (recovery / "index-changes.patch").read_text(encoding="utf-8"),
            "",
        )
        self.assertIn(
            "+unstaged text",
            (recovery / "worktree-changes.patch").read_text(encoding="utf-8"),
        )

    def test_mixed_text_changes_preserve_both_layers(self) -> None:
        self.write("notes.txt", "staged layer\n")
        self.git("add", "notes.txt")
        self.write("notes.txt", "staged layer\nworktree layer\n")

        recovery, _ = self.generate()

        self.assertIn(
            "+staged layer",
            (recovery / "index-changes.patch").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "+worktree layer",
            (recovery / "worktree-changes.patch").read_text(encoding="utf-8"),
        )

    def test_deleted_text_is_preserved_without_binary_patch_payloads(self) -> None:
        (self.repo / "remove.txt").unlink()

        recovery, _ = self.generate()
        patch = (recovery / "worktree-changes.patch").read_text(
            encoding="utf-8"
        )

        self.assertIn("-remove this text", patch)
        for path in recovery.iterdir():
            if path.is_file():
                self.assertNotIn(b"GIT binary patch", path.read_bytes())

    def test_modified_and_deleted_binary_paths_have_recovery_notes(self) -> None:
        self.write("modified.bin", b"\x00changed-binary\xfd")
        (self.repo / "deleted.bin").unlink()

        recovery, preflight = self.generate()
        report = (recovery / "binary-changes.txt").read_text(encoding="utf-8")

        self.assertIn("modified.bin", report)
        self.assertIn("modified", report)
        self.assertIn("deleted.bin", report)
        self.assertIn("deleted", report)
        self.assertIn(preflight.old_commit, report)
        self.assertIn("original committed content", report)
        patch = (recovery / "worktree-changes.patch").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("GIT binary patch", patch)
        self.assertNotIn("modified.bin", patch)
        self.assertNotIn("deleted.bin", patch)

    def test_untracked_spaces_and_unicode_are_unambiguous(self) -> None:
        self.write("loose file.txt", "safe\n")
        self.write("镜头/新 文件.txt", "safe\n")

        recovery, _ = self.generate()
        lines = (
            recovery / "untracked-files.txt"
        ).read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            [json.loads(line) for line in lines],
            ["loose file.txt", "镜头/新 文件.txt"],
        )

    def test_detached_head_state_is_explicit_and_remotes_are_redacted(self) -> None:
        self.git(
            "remote",
            "add",
            "origin",
            "https://user:top-secret@example.invalid/repo.git"
            "?token=query-secret&mode=read",
        )
        self.git("switch", "--detach", "HEAD")

        recovery, preflight = self.generate()
        state_text = (recovery / "git-state.json").read_text(encoding="utf-8")
        state = json.loads(state_text)

        self.assertIsNone(state["source"]["branch"])
        self.assertEqual(state["source"]["commit"], preflight.old_commit)
        self.assertEqual(state["base"]["ref"], preflight.base_ref)
        self.assertEqual(state["base"]["commit"], preflight.base_commit)
        self.assertEqual(state["source"]["path"], str(self.repo.resolve()))
        self.assertTrue(state["status"]["porcelain_v1_z_sha256"])
        self.assertEqual(state["format_version"], 1)
        self.assertEqual(archive_project.SCRIPT_VERSION, "1.0.0")
        self.assertEqual(state["script_version"], "1.0.0")
        self.assertTrue(state["generated_at"])
        self.assertNotIn("top-secret", state_text)
        self.assertNotIn("query-secret", state_text)
        self.assertIn("[REDACTED]", state_text)

    def test_scp_remote_colon_userinfo_is_structurally_redacted(self) -> None:
        password = "scp-password-" + ("A1b2" * 4)
        self.git(
            "remote",
            "add",
            "backup",
            "encoded%3Auser:{}@host.invalid:team/repo.git".format(password),
        )

        recovery, _ = self.generate()
        state_text = (recovery / "git-state.json").read_text(encoding="utf-8")
        state = json.loads(state_text)
        url = state["remotes"][0]["urls"][0]

        self.assertNotIn(password, state_text)
        self.assertNotIn("encoded%3Auser", state_text)
        self.assertEqual(url, "[REDACTED]@host.invalid:team/repo.git")

    def test_unborn_head_state_is_explicit_and_restore_guide_is_safe(self) -> None:
        shutil.rmtree(self.repo / ".git")
        self.git("init", "-b", "project/unborn")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")

        recovery, preflight = self.generate()
        state = json.loads(
            (recovery / "git-state.json").read_text(encoding="utf-8")
        )
        restore = (recovery / "RESTORE.md").read_text(encoding="utf-8")

        self.assertEqual(state["source"]["branch"], "project/unborn")
        self.assertIsNone(state["source"]["commit"])
        self.assertIsNone(preflight.old_commit)
        self.assertIn("index-changes.patch", restore)
        self.assertIn("worktree-changes.patch", restore)
        self.assertIn("untracked-files.txt", restore)
        self.assertIn("binary-changes.txt", restore)
        self.assertNotIn("git reset --hard", restore)
        self.assertNotIn("git clean", restore)

    def test_restore_guide_separates_snapshot_from_operational_replay(
        self,
    ) -> None:
        self.write("notes.txt", "staged layer\n")
        self.git("add", "notes.txt")
        self.write("notes.txt", "staged layer\nworktree layer\n")
        self.write("modified.bin", b"\x00current-binary\xfc")
        self.write("loose file.txt", "untracked\n")
        recovery, preflight = self.generate()
        restore = (recovery / "RESTORE.md").read_text(encoding="utf-8")
        replay = self.test_root / "history replay"
        subprocess.run(
            ["git", "clone", "--no-checkout", str(self.repo), str(replay)],
            capture_output=True,
            text=True,
            check=True,
        )
        subprocess.run(
            ["git", "checkout", "--detach", preflight.old_commit],
            cwd=replay,
            capture_output=True,
            text=True,
            check=True,
        )

        def replay_git(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", *arguments],
                cwd=replay,
                capture_output=True,
                text=True,
                check=True,
            )

        index_patch = recovery / "index-changes.patch"
        worktree_patch = recovery / "worktree-changes.patch"
        replay_git("apply", "--check", str(index_patch))
        replay_git("apply", "--index", str(index_patch))
        replay_git("apply", "--check", str(worktree_patch))
        replay_git("apply", str(worktree_patch))
        shutil.copy2(self.repo / "modified.bin", replay / "modified.bin")
        shutil.copy2(self.repo / "loose file.txt", replay / "loose file.txt")

        self.assertIn("Strategy A", restore)
        self.assertIn("Do not apply either patch", restore)
        self.assertIn("Strategy B", restore)
        self.assertIn("recorded source commit", restore)
        self.assertIn("copy only", restore.lower())
        self.assertIn("untracked-files.txt", restore)
        self.assertIn("current binary", restore.lower())
        self.assertEqual(
            (replay / "notes.txt").read_text(encoding="utf-8"),
            "staged layer\nworktree layer\n",
        )
        cached = replay_git("diff", "--cached", "--", "notes.txt").stdout
        unstaged = replay_git("diff", "--", "notes.txt").stdout
        self.assertIn("+staged layer", cached)
        self.assertNotIn("worktree layer", cached)
        self.assertIn("+worktree layer", unstaged)
        self.assertEqual(
            (replay / "modified.bin").read_bytes(),
            (self.repo / "modified.bin").read_bytes(),
        )
        self.assertIn(
            "loose file.txt",
            replay_git(
                "ls-files", "--others", "--exclude-standard"
            ).stdout.splitlines(),
        )

    def test_unborn_staged_binary_replay_uses_snapshot_payload(self) -> None:
        shutil.rmtree(self.repo / ".git")
        self.git("init", "-b", "project/unborn")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.invalid")
        self.write("seed.txt", "staged text\n")
        self.write("new binary.bin", b"\x00snapshot-binary\xfb")
        self.git("add", "seed.txt", "new binary.bin")

        recovery, preflight = self.generate()
        index_patch = recovery / "index-changes.patch"
        report = (recovery / "binary-changes.txt").read_text(encoding="utf-8")
        replay = self.test_root / "unborn replay"
        replay.mkdir()
        subprocess.run(
            ["git", "init", "-b", "project/replay"],
            cwd=replay,
            capture_output=True,
            text=True,
            check=True,
        )

        def replay_git(*arguments: str) -> subprocess.CompletedProcess:
            return subprocess.run(
                ["git", *arguments],
                cwd=replay,
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertIsNone(preflight.old_commit)
        self.assertIn('added (index): "new binary.bin"', report)
        self.assertNotIn(b"new binary.bin", index_patch.read_bytes())
        self.assertNotIn(b"Binary files", index_patch.read_bytes())
        replay_git("apply", "--check", str(index_patch))
        replay_git("apply", "--index", str(index_patch))
        shutil.copy2(
            self.repo / "new binary.bin", replay / "new binary.bin"
        )
        replay_git("add", "--", "new binary.bin")

        status = replay_git("status", "--porcelain=v1", "-z").stdout
        self.assertIn("A  seed.txt\0", status)
        self.assertIn("A  new binary.bin\0", status)
        self.assertEqual(
            (replay / "new binary.bin").read_bytes(),
            (self.repo / "new binary.bin").read_bytes(),
        )

    def test_generated_historic_credential_fails_closed_without_disclosure(
        self,
    ) -> None:
        credential = "deleted-value-" + ("A1b2" * 8)
        self.write("historic.txt", "password={}\n".format(credential))
        self.git("add", "historic.txt")
        self.git("commit", "-m", "historic credential fixture")
        (self.repo / "historic.txt").unlink()
        preflight = archive_project.run_preflight(self.args(), self.repo)
        staging = self.test_root / "credential staging"
        staging.mkdir()

        with self.assertRaises(archive_project.PreflightError) as caught:
            archive_project.write_recovery_files(preflight, staging)

        self.assertFalse(staging.exists())
        self.assertNotIn(credential, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
