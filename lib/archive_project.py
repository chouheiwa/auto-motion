#!/usr/bin/env python3

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import unicodedata
import urllib.parse
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
)
EXACT_CREDENTIAL_PLACEHOLDERS = {
    b"<your-api-key>",
    b"sk-xxxxx",
    b"your-api-key-here",
    b"your_api_key_here",
}
ASSIGNMENT_PATTERN = re.compile(
    br"""(?im)
    (?<![A-Za-z0-9_])
    ["']?(api[_-]?key|access[_-]?token|token|password|passwd|secret)["']?
    (?![A-Za-z0-9_])
    \s*[:=]\s*
    (?:
        "([^"\r\n]{8,})"
        |
        '([^'\r\n]{8,})'
        |
        ([^\s#,\]}][^\r\n#,\]}]{7,})
    )
    """,
    re.VERBOSE,
)
BEARER_PATTERN = re.compile(
    br"""(?ix)
    ["']?authorization["']?\s*[:=]\s*["']?
    bearer\s+([A-Za-z0-9._~+/-]{12,})
    """
)
EXPRESSION_PREFIXES = (
    b"os.",
    b"process.",
    b"parser.",
    b"config.",
    b"settings.",
    b"self.",
    b"args.",
    b"request.",
    b"env.",
    b"get_",
    b"optional[",
    b"${",
)


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


def _looks_like_real_assignment(
    key: bytes, value: bytes, quoted: bool
) -> bool:
    normalized = value.strip()
    if normalized in EXACT_CREDENTIAL_PLACEHOLDERS:
        return False
    lowered = normalized.lower()
    if not quoted and (
        lowered.startswith(EXPRESSION_PREFIXES) or b"(" in normalized
    ):
        return False
    if key.lower() == b"token":
        lowercase_hex = (
            re.fullmatch(br"[a-f0-9]{32,}", normalized) is not None
            and re.search(br"[a-f]", normalized) is not None
            and re.search(br"[0-9]", normalized) is not None
        )
        mixed_token = (
            len(normalized) >= 24
            and any(65 <= byte <= 90 for byte in normalized)
            and any(97 <= byte <= 122 for byte in normalized)
            and any(48 <= byte <= 57 for byte in normalized)
        )
        return lowercase_hex or mixed_token
    return len(normalized) >= 8


def _scan_secret_bytes(content: bytes) -> Optional[str]:
    for rule, pattern in SECRET_PATTERNS:
        if pattern.search(content):
            return rule
    if BEARER_PATTERN.search(content):
        return "authorization-bearer"
    for match in ASSIGNMENT_PATTERN.finditer(content):
        quoted = match.group(2) is not None or match.group(3) is not None
        value = next(group for group in match.groups()[1:] if group is not None)
        if _looks_like_real_assignment(match.group(1), value, quoted):
            return "credential-assignment"
    return None


def scan_secret_stream(path: str, stream: BinaryIO) -> Optional[str]:
    overlap = b""
    detected = None
    while True:
        chunk = stream.read(64 * 1024)
        if not chunk:
            return detected
        sample = overlap + chunk
        detected = detected or _scan_secret_bytes(sample)
        overlap = sample[-4096:]


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
    relative_path = path.relative_to(root).as_posix()
    try:
        root_resolved = root.resolve()
        initial_target = os.readlink(str(path))
    except OSError:
        raise PreflightError(
            "unable to inspect symlink '{}'".format(relative_path)
        )
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
        try:
            target = os.readlink(str(candidate))
        except OSError:
            raise PreflightError(
                "unable to inspect symlink '{}'".format(relative_path)
            )
        if os.path.isabs(target):
            raise PreflightError(
                "symlink '{}' has an absolute target".format(relative_path)
            )
        pending = list(Path(target).parts) + pending
        current = candidate.parent

    return initial_target


def _after_file_read(path: Path) -> None:
    pass


def _read_inventory_file(
    path: Path, relative: str
) -> Tuple[int, int, str, Optional[str]]:
    digest = hashlib.sha256()
    total = 0
    overlap = b""
    detected = None
    try:
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                digest.update(chunk)
                sample = overlap + chunk
                detected = detected or _scan_secret_bytes(sample)
                overlap = sample[-4096:]
            _after_file_read(path)
            after = os.fstat(stream.fileno())
    except OSError:
        raise PreflightError(
            "{}: unable to read included file".format(relative)
        )
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or total != before.st_size:
        raise PreflightError(
            "{}: file changed while being read".format(relative)
        )
    return (
        stat.S_IMODE(before.st_mode),
        total,
        digest.hexdigest(),
        detected,
    )


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
            try:
                metadata = child.stat(follow_symlinks=False)
            except OSError:
                raise PreflightError(
                    "{}: unable to inspect source entry".format(relative)
                )
            if child.name in EXCLUDED_DIRECTORY_RULES and (
                stat.S_ISDIR(metadata.st_mode) or child.name == ".git"
            ):
                exclusions.append(
                    Exclusion(
                        relative, EXCLUDED_DIRECTORY_RULES[child.name]
                    )
                )
                continue
            if (
                child.name in EXCLUDED_FILE_RULES
                and stat.S_ISREG(metadata.st_mode)
            ):
                exclusions.append(
                    Exclusion(relative, EXCLUDED_FILE_RULES[child.name])
                )
                continue
            secret_rule = scan_secret_path(relative, tracked)
            if secret_rule is not None:
                raise PreflightError(
                    "{}: sensitive path ({})".format(relative, secret_rule)
                )
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISDIR(metadata.st_mode):
                included.add(relative)
                entries.append(
                    Entry(relative, "directory", mode, 0, None, None)
                )
                visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                mode, size, sha256, content_rule = _read_inventory_file(
                    path, relative
                )
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
                        size,
                        sha256,
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


def _run_preflight(
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


def run_preflight(
    args: argparse.Namespace, cwd: Path
) -> Preflight:
    try:
        return _run_preflight(args, cwd)
    except PreflightError:
        raise
    except OSError:
        raise PreflightError("filesystem inspection failed")


def _recovery_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _decode_git_path(path: bytes) -> str:
    try:
        decoded = path.decode("utf-8", "surrogateescape")
    except UnicodeError:
        raise PreflightError("Git returned an undecodable recovery path")
    if _contains_control(decoded):
        raise PreflightError(
            "Git returned a recovery path containing a control character"
        )
    return decoded


def _redact_remote_url(value: str) -> str:
    if _contains_control(value):
        return "[REDACTED]"
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return "[REDACTED]"
    if parsed.scheme and parsed.netloc:
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = "[{}]".format(hostname)
        port = ""
        try:
            if parsed.port is not None:
                port = ":{}".format(parsed.port)
        except ValueError:
            return "[REDACTED]"
        userinfo = (
            "[REDACTED]@" if "@" in parsed.netloc else ""
        )
        query = ""
        if parsed.query:
            names = []
            for item in parsed.query.split("&"):
                name = item.split("=", 1)[0]
                names.append("{}=[REDACTED]".format(name))
            query = "&".join(names)
        redacted = urllib.parse.urlunsplit(
            (
                parsed.scheme,
                userinfo + hostname + port,
                parsed.path,
                query,
                "[REDACTED]" if parsed.fragment else "",
            )
        )
    elif re.match(r"^[^/@:\s]+@[^:\s]+:", value):
        redacted = "[REDACTED]@" + value.split("@", 1)[1]
    else:
        redacted = value
    for _, pattern in SECRET_PATTERNS:
        redacted = pattern.sub(b"[REDACTED]", redacted.encode("utf-8")).decode(
            "utf-8"
        )
    return redacted


def _remote_state(source: Path) -> list:
    names_result = _run_git(source, ["remote"], check=False)
    if names_result.returncode != 0:
        raise PreflightError("local Git remote inspection failed")
    try:
        names = names_result.stdout.decode("utf-8").splitlines()
    except UnicodeError:
        raise PreflightError("Git returned undecodable remote metadata")
    remotes = []
    for name in sorted(names):
        if _contains_control(name):
            raise PreflightError("Git returned unsafe remote metadata")
        urls_result = _run_git(
            source, ["remote", "get-url", "--all", name], check=False
        )
        if urls_result.returncode != 0:
            raise PreflightError("local Git remote inspection failed")
        try:
            urls = urls_result.stdout.decode("utf-8").splitlines()
        except UnicodeError:
            raise PreflightError("Git returned undecodable remote metadata")
        remotes.append(
            {
                "name": name,
                "urls": [_redact_remote_url(url) for url in urls],
            }
        )
    return remotes


def _status_state(status: bytes) -> dict:
    records = [
        _decode_git_path(record)
        for record in status.split(b"\0")
        if record
    ]
    return {
        "format": "porcelain=v1 -z",
        "records": records,
        "porcelain_v1_z_sha256": hashlib.sha256(status).hexdigest(),
    }


def _diff_bytes(
    source: Path,
    cached: bool,
    mode: str,
    excluded_paths: Sequence[bytes] = (),
) -> bytes:
    arguments = [
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-renames",
    ]
    if cached:
        arguments.append("--cached")
    if mode == "patch":
        arguments.extend(["--full-index", "--"])
        arguments.extend(
            ":(literal,exclude){}".format(_decode_git_path(path))
            for path in sorted(excluded_paths)
        )
    elif mode == "name-status":
        arguments.extend(["--name-status", "-z", "--diff-filter=MD", "--"])
    elif mode == "numstat":
        arguments.extend(["--numstat", "-z", "--diff-filter=MD", "--"])
    else:
        raise ValueError("unsupported Git diff mode")
    return _run_git(source, arguments).stdout


def _binary_paths(source: Path, cached: bool) -> Set[bytes]:
    binary_paths = set()
    for record in _diff_bytes(source, cached, "numstat").split(b"\0"):
        if not record:
            continue
        fields = record.split(b"\t", 2)
        if len(fields) != 3:
            raise PreflightError("Git returned malformed binary metadata")
        if fields[0] == b"-" and fields[1] == b"-":
            binary_paths.add(fields[2])
    return binary_paths


def _binary_changes(
    source: Path, cached: bool, binary_paths: Set[bytes]
) -> list:
    tokens = [
        token
        for token in _diff_bytes(
            source, cached, "name-status"
        ).split(b"\0")
        if token
    ]
    if len(tokens) % 2:
        raise PreflightError("Git returned malformed change metadata")
    changes = []
    for index in range(0, len(tokens), 2):
        status = tokens[index].decode("ascii", "strict")
        path = tokens[index + 1]
        if path not in binary_paths:
            continue
        changes.append(
            {
                "layer": "index" if cached else "worktree",
                "change": "deleted" if status == "D" else "modified",
                "path": _decode_git_path(path),
            }
        )
    return changes


def _untracked_paths(source: Path) -> list:
    output = _run_git(
        source,
        ["ls-files", "--others", "--exclude-standard", "-z"],
    ).stdout
    return sorted(_decode_git_path(path) for path in output.split(b"\0") if path)


def _binary_report(
    changes: list, original_commit: Optional[str]
) -> bytes:
    lines = [
        "# Binary changes",
        "",
        (
            "Binary payloads are intentionally omitted from the patches. "
            "Existing modified files are preserved by the archive snapshot."
        ),
    ]
    if original_commit:
        lines.append(
            (
                "The original committed content can be recovered from "
                "commit {}."
            ).format(original_commit)
        )
    else:
        lines.append(
            "No original commit exists for this unborn repository."
        )
    lines.append("")
    if changes:
        for change in sorted(
            changes,
            key=lambda item: (
                item["path"],
                item["layer"],
                item["change"],
            ),
        ):
            lines.append(
                "{} ({}): {}".format(
                    change["change"],
                    change["layer"],
                    json.dumps(change["path"], ensure_ascii=False),
                )
            )
    else:
        lines.append("(none)")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _restore_guide() -> bytes:
    return b"""# Restore this archive safely

Work in a new, disposable Git worktree or clone. Read `git-state.json` first and
verify the recorded source commit and base commit before making changes.

1. Restore the archived snapshot into the chosen worktree without overwriting
   unrelated files.
2. Review `untracked-files.txt`; each line is a JSON-quoted path.
3. Inspect `binary-changes.txt`. Binary payloads are not embedded in patches.
4. Check the staged layer with:
   `git apply --check recovery/index-changes.patch`
5. If the check succeeds, apply it with:
   `git apply --index recovery/index-changes.patch`
6. Check and apply the unstaged layer afterward:
   `git apply --check recovery/worktree-changes.patch`
   `git apply recovery/worktree-changes.patch`

Empty patch files require no action. Review `git status` and the resulting diff
before committing. Destructive reset or cleanup commands are unnecessary.
"""


def _scan_and_write_recovery(
    recovery: Path, name: str, content: bytes
) -> None:
    relative = "recovery/{}".format(name)
    detected = scan_secret_stream(relative, io.BytesIO(content))
    if detected is not None:
        raise PreflightError(
            "{}: credential pattern ({})".format(relative, detected)
        )
    try:
        (recovery / name).write_bytes(content)
    except OSError:
        raise PreflightError(
            "{}: unable to write recovery evidence".format(relative)
        )


def write_recovery_files(preflight: Preflight, staging: Path) -> None:
    staging = Path(staging)
    recovery = staging / "recovery"
    try:
        if not staging.is_dir() or os.path.lexists(str(recovery)):
            raise PreflightError("recovery staging directory is not empty")
        recovery.mkdir()
        index_binary_paths = _binary_paths(preflight.source, True)
        worktree_binary_paths = _binary_paths(preflight.source, False)
        index_patch = _diff_bytes(
            preflight.source,
            True,
            "patch",
            tuple(index_binary_paths),
        )
        worktree_patch = _diff_bytes(
            preflight.source,
            False,
            "patch",
            tuple(worktree_binary_paths),
        )
        binary_changes = (
            _binary_changes(
                preflight.source, True, index_binary_paths
            )
            + _binary_changes(
                preflight.source, False, worktree_binary_paths
            )
        )
        untracked = _untracked_paths(preflight.source)
        state = {
            "format_version": 1,
            "generated_at": _recovery_timestamp(),
            "source": {
                "path": str(preflight.source),
                "branch": preflight.old_branch,
                "commit": preflight.old_commit,
                "ref_commit": preflight.old_ref_commit,
            },
            "base": {
                "ref": preflight.base_ref,
                "commit": preflight.base_commit or None,
            },
            "status": _status_state(preflight.frozen_git_status),
            "remotes": _remote_state(preflight.source),
        }
        documents = (
            ("index-changes.patch", index_patch),
            ("worktree-changes.patch", worktree_patch),
            (
                "binary-changes.txt",
                _binary_report(binary_changes, preflight.old_commit),
            ),
            (
                "untracked-files.txt",
                (
                    "".join(
                        json.dumps(path, ensure_ascii=False) + "\n"
                        for path in untracked
                    )
                ).encode("utf-8"),
            ),
            (
                "git-state.json",
                (
                    json.dumps(
                        state,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8"),
            ),
            ("RESTORE.md", _restore_guide()),
        )
        for name, content in documents:
            _scan_and_write_recovery(recovery, name, content)
    except PreflightError:
        shutil.rmtree(str(staging), ignore_errors=True)
        raise
    except (OSError, UnicodeError, ValueError):
        shutil.rmtree(str(staging), ignore_errors=True)
        raise PreflightError("recovery evidence generation failed")


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
