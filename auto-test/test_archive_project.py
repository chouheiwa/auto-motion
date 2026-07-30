#!/usr/bin/env python3

import subprocess
import unittest
from pathlib import Path
from typing import Tuple


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_COMMAND = REPOSITORY_ROOT / "archive-project.sh"


class ArchiveProjectParserTests(unittest.TestCase):
    def run_command(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(ARCHIVE_COMMAND), *arguments],
            cwd=REPOSITORY_ROOT,
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

    def test_archive_only_rejects_next_project(self) -> None:
        self.assert_parser_error(
            ("--archive-only", "--next-project", "next-video"),
            "--archive-only cannot be combined with --next-project",
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
        for archive_name in ("nested/name", r"nested\name", ".", ".."):
            with self.subTest(archive_name=archive_name):
                self.assert_parser_error(
                    ("--archive-only", "--archive-name", archive_name),
                    "--archive-name must be a single safe directory name",
                )


if __name__ == "__main__":
    unittest.main()
