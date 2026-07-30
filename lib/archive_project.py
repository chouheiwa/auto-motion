#!/usr/bin/env python3

import argparse
import re
import sys
import unicodedata
from typing import Optional, Sequence


def sanitize_project_id(value: str) -> str:
    parts = re.findall(r"[^\W_]+", value, flags=re.UNICODE)
    return "-".join(parts).lower()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Create a verified project archive and optionally prepare the "
            "worktree for a new project."
        )
    )
    parser.add_argument(
        "--archive-root",
        metavar="DIRECTORY",
        help="override the default sibling _archive directory",
    )
    parser.add_argument(
        "--archive-name",
        metavar="NAME",
        help="override the generated archive directory name",
    )
    parser.add_argument(
        "--main-ref",
        metavar="GIT_REF",
        help="override the base ref used for cleanup",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the resolved plan without writing or deleting",
    )
    parser.add_argument(
        "--archive-only",
        action="store_true",
        help="create and verify an archive without cleaning",
    )
    parser.add_argument(
        "--next-project",
        metavar="PROJECT_ID",
        help="project identifier used to name the new cleanup branch",
    )
    parser.add_argument(
        "--confirm-clean",
        action="store_true",
        help="explicitly authorize cleanup after archive verification",
    )
    return parser


def parse_args(
    argv: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.archive_name is not None and (
        not args.archive_name.strip()
        or args.archive_name in (".", "..")
        or "/" in args.archive_name
        or "\\" in args.archive_name
        or any(
            unicodedata.category(character) == "Cc"
            for character in args.archive_name
        )
    ):
        parser.error("--archive-name must be a single safe directory name")

    if args.archive_only:
        if args.next_project is not None:
            parser.error(
                "--archive-only cannot be combined with --next-project"
            )
        if args.confirm_clean:
            parser.error(
                "--archive-only cannot be combined with --confirm-clean"
            )
    else:
        if args.next_project is None:
            parser.error("cleanup mode requires --next-project")
        if not args.confirm_clean:
            parser.error("cleanup mode requires --confirm-clean")

    if (
        args.next_project is not None
        and not sanitize_project_id(args.next_project)
    ):
        parser.error("--next-project must contain letters or numbers")

    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    parse_args(argv)
    sys.stderr.write("archive-project: execution is not implemented yet\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
