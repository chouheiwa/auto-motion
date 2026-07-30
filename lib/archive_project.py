#!/usr/bin/env python3

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, FrozenSet, Optional, Sequence, Set, Tuple


class PreflightError(RuntimeError):
    """A safe, redacted preflight failure."""


@dataclass(frozen=True)
class FileIdentity:
    path: str
    device: int
    inode: int


@dataclass(frozen=True)
class Entry:
    path: str
    kind: str
    mode: int
    size: int
    sha256: Optional[str]
    link_target: Optional[str]


@dataclass(frozen=True)
class Exclusion:
    path: str
    rule: str


@dataclass(frozen=True)
class RepositoryState:
    root: Path
    branch: Optional[str]
    commit: Optional[str]
    status: bytes
    tracked: FrozenSet[str]


@dataclass(frozen=True)
class ResolvedRef:
    name: str
    commit: str


@dataclass(frozen=True)
class GitPaths:
    tracked: FrozenSet[str]
    historical: FrozenSet[str]


@dataclass(frozen=True)
class Inventory:
    entries: Tuple[Entry, ...]
    exclusions: Tuple[Exclusion, ...]


@dataclass(frozen=True)
class Preflight:
    source: Path
    source_identity: FileIdentity
    archive_root: Path
    archive_parent_identity: FileIdentity
    final_archive: Path
    reset_result: Path
    project_id: str
    old_branch: Optional[str]
    old_commit: Optional[str]
    old_ref_commit: Optional[str]
    base_ref: str
    base_commit: str
    new_branch: Optional[str]
    frozen_git_status: bytes
    inventory: Tuple[Entry, ...]
    exclusions: Tuple[Exclusion, ...]


EXCLUDED_DIRECTORY_RULES = {
    ".git": "git-metadata",
    "node_modules": "dependencies",
    "vendor": "dependencies",
    ".cache": "cache",
    "__pycache__": "cache",
    ".pytest_cache": "cache",
    ".mypy_cache": "cache",
    ".next": "build-cache",
    "dist": "build-output",
}
EXCLUDED_FILE_RULES = {
    ".DS_Store": "os-junk",
    "Thumbs.db": "os-junk",
}
SECRET_PATTERNS = (
    ("openai-api-key", re.compile(br"sk-[A-Za-z0-9_-]{20,}")),
    ("aws-access-key", re.compile(br"AKIA[A-Z0-9]{16}")),
    (
        "private-key",
        re.compile(br"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
    (
        "github-token",
        re.compile(br"(?:ghp|github_pat)_[A-Za-z0-9_]{20,}"),
    ),
    (
        "credential-assignment",
        re.compile(
            br"(?i)(?:api[_-]?key|access[_-]?token|token|"
            br"password|passwd|secret)"
            br"\s*[:=]\s*[\"']?"
            br"([A-Za-z0-9_./+<>{}@:$-]{12,})(?=$|[\s\"'])"
        ),
    ),
)
EXACT_CREDENTIAL_PLACEHOLDERS = {
    b"<your-api-key>",
    b"<your-api-key>\\n",
}


def sanitize_project_id(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    parts = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return "-".join(parts).lower()


def current_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Create a verified project archive and optionally prepare the "
            "worktree for a new project."
        ),
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


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
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


def _run_git(
    cwd: Path, arguments: Sequence[str], check: bool = True
) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    result = subprocess.run(
        ["git", *arguments],
        cwd=str(cwd),
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise PreflightError("local Git inspection failed")
    return result


def _nul_paths(data: bytes) -> FrozenSet[str]:
    try:
        return frozenset(
            item.decode("utf-8", "surrogateescape")
            for item in data.split(b"\0")
            if item
        )
    except UnicodeError:
        raise PreflightError("Git returned an undecodable path")


def _local_commit(root: Path, reference: str) -> Optional[str]:
    result = _run_git(
        root, ["rev-parse", "--verify", reference + "^{commit}"], check=False
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("ascii").strip()


def discover_repository(cwd: Path) -> RepositoryState:
    requested = Path(cwd).expanduser().resolve()
    if requested == Path("/") or requested == Path.home().resolve():
        raise PreflightError("unsafe source path")
    result = _run_git(
        requested, ["rev-parse", "--show-toplevel"], check=False
    )
    if result.returncode != 0:
        raise PreflightError("source must be the exact Git worktree root")
    root = Path(
        result.stdout.decode("utf-8", "surrogateescape").strip()
    ).resolve()
    if root != requested:
        raise PreflightError("source must be the exact Git worktree root")
    if root == Path("/") or root == Path.home().resolve():
        raise PreflightError("unsafe source path")

    branch_result = _run_git(
        root, ["symbolic-ref", "--quiet", "--short", "HEAD"], check=False
    )
    branch = (
        branch_result.stdout.decode("utf-8", "surrogateescape").strip()
        if branch_result.returncode == 0
        else None
    )
    commit = _local_commit(root, "HEAD")
    status = _run_git(
        root,
        ["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    ).stdout
    tracked = _nul_paths(_run_git(root, ["ls-files", "-z"]).stdout)
    return RepositoryState(root, branch, commit, status, tracked)


def resolve_base_ref(
    repo: RepositoryState, requested: Optional[str]
) -> ResolvedRef:
    candidates = (requested,) if requested else ("origin/main", "main")
    for candidate in candidates:
        commit = _local_commit(repo.root, candidate)
        if commit is not None:
            return ResolvedRef(candidate, commit)
    if requested:
        raise PreflightError(
            "requested --main-ref does not resolve to a local commit"
        )
    raise PreflightError(
        "neither origin/main nor main resolves to a local commit"
    )


def scan_secret_path(path: str, tracked: Set[str]) -> Optional[str]:
    pure = Path(path)
    name = pure.name.lower()
    components = {part.lower() for part in pure.parts}
    if path == ".env.example":
        return None if path in tracked else "untracked-env-template"
    if name == ".env" or name.startswith(".env."):
        return "environment-file"
    if components & {"private", "auth"}:
        return "private-or-auth-path"
    if name in {
        "credentials",
        "credentials.json",
        "auth.json",
        ".npmrc",
        ".pypirc",
        "id_rsa",
        "id_ed25519",
    }:
        return "authentication-file"
    if pure.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        return "private-key-file"
    return None


def scan_secret_stream(path: str, stream: BinaryIO) -> Optional[str]:
    overlap = b""
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            return None
        sample = overlap + chunk
        for rule, pattern in SECRET_PATTERNS:
            matches = tuple(pattern.finditer(sample))
            if not matches:
                continue
            if rule == "credential-assignment" and all(
                match.group(1) in EXACT_CREDENTIAL_PLACEHOLDERS
                for match in matches
            ):
                continue
            return rule
        overlap = sample[-512:]


def _contains_control(path: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in path)


def _is_within(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath((str(child), str(parent))) == str(parent)
    except ValueError:
        return False


def validate_link_chain(
    root: Path, path: Path, included: Set[str]
) -> str:
    root_resolved = root.resolve()
    relative_path = path.relative_to(root).as_posix()
    initial_target = os.readlink(str(path))
    current = root_resolved
    pending = list(path.relative_to(root).parts)
    visited = set()

    while pending:
        component = pending.pop(0)
        if component in ("", "."):
            continue
        if component == "..":
            current = current.parent
            if not _is_within(current, root_resolved):
                raise PreflightError(
                    "symlink '{}' has an outside chain hop".format(
                        relative_path
                    )
                )
            continue
        candidate = current / component
        if not _is_within(candidate, root_resolved):
            raise PreflightError(
                "symlink '{}' has an outside chain hop".format(relative_path)
            )
        candidate_relative = candidate.relative_to(
            root_resolved
        ).as_posix()
        if candidate_relative not in included:
            raise PreflightError(
                "symlink '{}' has an excluded chain hop".format(
                    relative_path
                )
            )
        try:
            metadata = candidate.lstat()
        except OSError:
            raise PreflightError(
                "symlink '{}' is dangling".format(relative_path)
            )
        if not stat.S_ISLNK(metadata.st_mode):
            current = candidate
            continue
        if candidate in visited:
            raise PreflightError(
                "symlink '{}' is cyclic".format(relative_path)
            )
        visited.add(candidate)
        target = os.readlink(str(candidate))
        if os.path.isabs(target):
            raise PreflightError(
                "symlink '{}' has an absolute target".format(relative_path)
            )
        pending = list(Path(target).parts) + pending
        current = candidate.parent

    return initial_target


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)


def build_inventory(root: Path, git_paths: GitPaths) -> Inventory:
    tracked = set(git_paths.tracked)
    for historical_path in sorted(git_paths.historical | git_paths.tracked):
        if _contains_control(historical_path):
            raise PreflightError(
                "tracked path contains a control character: {!r}".format(
                    historical_path
                )
            )
        rule = scan_secret_path(historical_path, tracked)
        if rule is not None:
            raise PreflightError(
                "{}: sensitive path ({})".format(historical_path, rule)
            )

    entries = []
    exclusions = []
    symlinks = []
    included = set()

    def visit(directory: Path) -> None:
        try:
            children = sorted(
                os.scandir(str(directory)), key=lambda item: item.name
            )
        except OSError:
            raise PreflightError("unable to inspect source directory")
        for child in children:
            path = Path(child.path)
            relative = path.relative_to(root).as_posix()
            if _contains_control(relative):
                raise PreflightError(
                    "path contains a control character: {!r}".format(relative)
                )
            if child.name in EXCLUDED_DIRECTORY_RULES and (
                child.is_dir(follow_symlinks=False)
                or child.name == ".git"
            ):
                exclusions.append(
                    Exclusion(
                        relative, EXCLUDED_DIRECTORY_RULES[child.name]
                    )
                )
                continue
            if child.name in EXCLUDED_FILE_RULES:
                exclusions.append(
                    Exclusion(relative, EXCLUDED_FILE_RULES[child.name])
                )
                continue
            secret_rule = scan_secret_path(relative, tracked)
            if secret_rule is not None:
                raise PreflightError(
                    "{}: sensitive path ({})".format(relative, secret_rule)
                )
            metadata = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISDIR(metadata.st_mode):
                included.add(relative)
                entries.append(
                    Entry(relative, "directory", mode, 0, None, None)
                )
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                with path.open("rb") as stream:
                    content_rule = scan_secret_stream(relative, stream)
                if content_rule is not None:
                    raise PreflightError(
                        "{}: credential pattern ({})".format(
                            relative, content_rule
                        )
                    )
                included.add(relative)
                entries.append(
                    Entry(
                        relative,
                        "file",
                        mode,
                        metadata.st_size,
                        _hash_file(path),
                        None,
                    )
                )
            elif stat.S_ISLNK(metadata.st_mode):
                included.add(relative)
                symlinks.append((relative, path, mode))
            else:
                raise PreflightError(
                    "{}: included special file is not supported".format(
                        relative
                    )
                )

    visit(root)
    for relative, path, mode in symlinks:
        target = validate_link_chain(root, path, included)
        entries.append(
            Entry(relative, "symlink", mode, 0, None, target)
        )
    return Inventory(
        tuple(sorted(entries, key=lambda entry: entry.path)),
        tuple(sorted(exclusions, key=lambda exclusion: exclusion.path)),
    )


def capture_identity(path_or_nearest_parent: Path) -> FileIdentity:
    candidate = Path(path_or_nearest_parent).expanduser().resolve()
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            raise PreflightError("no existing archive parent is available")
        candidate = parent
    if not candidate.is_dir():
        raise PreflightError(
            "nearest existing archive parent must be a directory"
        )
    metadata = candidate.stat()
    return FileIdentity(
        str(candidate), metadata.st_dev, metadata.st_ino
    )


def check_space(archive_parent: Path, required_bytes: int) -> None:
    identity = capture_identity(archive_parent)
    free = shutil.disk_usage(identity.path).free
    if free < required_bytes:
        raise PreflightError("insufficient destination free space")


def _historical_paths(repo: RepositoryState) -> FrozenSet[str]:
    if repo.commit is None:
        return frozenset()
    result = _run_git(
        repo.root,
        ["ls-tree", "-r", "--name-only", "-z", "HEAD"],
    )
    return _nul_paths(result.stdout)


def _project_id(repo: RepositoryState) -> str:
    config_path = repo.root / "production" / "production-config.json"
    if config_path.is_file():
        try:
            content = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise PreflightError(
                "production/production-config.json is not valid JSON"
            )
        if isinstance(content, dict):
            for key in ("projectId", "project_id", "id"):
                value = content.get(key)
                if isinstance(value, str) and sanitize_project_id(value):
                    return sanitize_project_id(value)
    fallback = repo.branch or repo.root.name
    project_id = sanitize_project_id(fallback)
    if not project_id:
        project_id = "project"
    return project_id


def _validate_cleanup_state(
    repo: RepositoryState, args: argparse.Namespace, timestamp: str
) -> Optional[str]:
    if args.archive_only:
        return None
    if repo.branch is None:
        raise PreflightError("cleanup is forbidden from detached HEAD")
    if repo.commit is None:
        raise PreflightError("cleanup is forbidden from an unborn branch")
    if repo.branch in {"main", "master"}:
        raise PreflightError(
            "cleanup is forbidden from protected branch '{}'".format(
                repo.branch
            )
        )
    new_branch = "project/{}-{}".format(
        sanitize_project_id(args.next_project), timestamp
    )
    existing = _run_git(
        repo.root,
        ["show-ref", "--verify", "--quiet", "refs/heads/" + new_branch],
        check=False,
    )
    if existing.returncode == 0:
        raise PreflightError(
            "new branch already exists or is checked out: {}".format(
                new_branch
            )
        )
    return new_branch


def run_preflight(
    args: argparse.Namespace, cwd: Path
) -> Preflight:
    if shutil.which("git") is None:
        raise PreflightError("required command is unavailable: git")
    repo = discover_repository(Path(cwd))
    timestamp = current_timestamp()
    new_branch = _validate_cleanup_state(repo, args, timestamp)
    try:
        base = resolve_base_ref(repo, args.main_ref)
    except PreflightError:
        if not args.archive_only or args.main_ref is not None:
            raise
        base = ResolvedRef("(unavailable)", "")
    project_id = _project_id(repo)

    archive_root_input = (
        Path(args.archive_root).expanduser()
        if args.archive_root
        else repo.root.parent / "_archive"
    )
    if (
        os.path.lexists(str(archive_root_input))
        and not archive_root_input.is_dir()
    ):
        raise PreflightError("existing archive root must be a directory")
    archive_root = archive_root_input.resolve()
    if _is_within(archive_root, repo.root):
        raise PreflightError(
            "archive destination must be outside the source worktree"
        )
    archive_name = args.archive_name or "{}-{}".format(
        project_id, timestamp
    )
    final_archive = archive_root / archive_name
    reset_result = Path(str(final_archive) + ".reset-result.json")
    if os.path.lexists(str(final_archive)):
        raise PreflightError(
            "final archive already exists: {}".format(final_archive)
        )
    if os.path.lexists(str(reset_result)):
        raise PreflightError(
            "reset result already exists: {}".format(reset_result)
        )

    git_paths = GitPaths(repo.tracked, _historical_paths(repo))
    inventory = build_inventory(repo.root, git_paths)
    required_bytes = (
        sum(entry.size for entry in inventory.entries) + 1024 * 1024
    )
    check_space(archive_root, required_bytes)
    return Preflight(
        source=repo.root,
        source_identity=capture_identity(repo.root),
        archive_root=archive_root,
        archive_parent_identity=capture_identity(archive_root),
        final_archive=final_archive,
        reset_result=reset_result,
        project_id=project_id,
        old_branch=repo.branch,
        old_commit=repo.commit,
        old_ref_commit=repo.commit,
        base_ref=base.name,
        base_commit=base.commit,
        new_branch=new_branch,
        frozen_git_status=repo.status,
        inventory=inventory.entries,
        exclusions=inventory.exclusions,
    )


def _print_plan(preflight: Preflight) -> None:
    print("source: {}".format(preflight.source))
    print("project: {}".format(preflight.project_id))
    print("archive: {}".format(preflight.final_archive))
    print("base ref: {}".format(preflight.base_ref))
    print("base commit: {}".format(preflight.base_commit))
    print("new branch: {}".format(preflight.new_branch or "(archive only)"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        preflight = run_preflight(args, Path.cwd())
    except PreflightError as error:
        sys.stderr.write("archive-project: {}\n".format(error))
        return 1
    if args.dry_run:
        _print_plan(preflight)
        return 0
    sys.stderr.write("archive-project: execution is not implemented yet\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
