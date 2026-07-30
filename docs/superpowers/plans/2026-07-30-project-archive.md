# Project Archive and Workspace Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `archive-project.sh` command that creates a verified, browsable project archive and, with explicit confirmation, resets the same worktree path to a clean new project branch based on a frozen `main` commit.

**Architecture:** A minimal Bash wrapper delegates to a Python 3 standard-library core. The core runs one complete read-only preflight before creating staging state, then performs a staged immutable archive transaction, and only then enters a separately guarded Git reset transaction. End-to-end `unittest` cases use isolated temporary repositories; no destructive test may target the real worktree.

**Tech Stack:** Bash, Python 3 standard library (including `ctypes` for platform no-replace rename), Git CLI, `unittest`

---

## File map

- Create `archive-project.sh`: executable entry point; only locates and executes the Python core.
- Create `lib/archive_project.py`: argument parsing, preflight, inventory, archive transaction, verification and reset transaction.
- Create `auto-test/test_archive_project.py`: unit and end-to-end temporary-repository tests.
- Modify `auto-test/run.sh`: execute the archive suite in the repository test entry point.
- Modify `README.md`: English archive/reset usage and safety contract.
- Modify `README.zh-CN.md`: Chinese archive/reset usage and safety contract.

## Required implementation boundaries

`lib/archive_project.py` is split internally into focused sections with explicit
data contracts:

```python
@dataclass(frozen=True)
class FileIdentity:
    path: str
    device: int
    inode: int

@dataclass(frozen=True)
class Entry:
    path: str
    kind: Literal["file", "directory", "symlink"]
    mode: int
    size: int
    sha256: str | None
    link_target: str | None

@dataclass(frozen=True)
class Preflight:
    source: Path
    source_identity: FileIdentity
    archive_root: Path
    archive_parent_identity: FileIdentity
    final_archive: Path
    reset_result: Path
    old_branch: str | None
    old_commit: str | None
    old_ref_commit: str | None
    base_ref: str
    base_commit: str
    new_branch: str | None
    frozen_git_status: bytes
    inventory: tuple[Entry, ...]
    exclusions: tuple[Exclusion, ...]
```

All Git path/status parsing uses `-z` output. All destructive subprocesses use
argument arrays, explicit `cwd=source`, and no shell interpolation.

### Task 1: CLI contract and parser-only red/green cycle

**Files:**
- Create `auto-test/test_archive_project.py`
- Create `archive-project.sh`
- Create `lib/archive_project.py`

- [ ] **Step 1: Write failing parser tests**

Tests cover `--help`, unknown flags, incompatible `--archive-only` plus
`--next-project`, cleanup without `--confirm-clean`, missing cleanup project ID,
empty sanitized IDs, and unsafe `--archive-name` values containing separators,
`.` or `..`.

No Task 1 test claims dry-run succeeds: dry-run success belongs to the complete
preflight task.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: FAIL because the script is absent.

- [ ] **Step 3: Implement only the entry point and parser**

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/lib/archive_project.py" "$@"
```

Set executable mode and implement strict `argparse` validation. Do not return a
successful dry-run until Task 2 implements all preflight checks.

- [ ] **Step 4: Run GREEN and verify executable delivery**

```bash
python3 -m unittest auto-test/test_archive_project.py -v
test -x archive-project.sh
```

- [ ] **Step 5: Commit**

```bash
git add archive-project.sh lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: add archive command contract"
```

### Task 2: Complete read-only preflight gate

**Files:**
- Modify `auto-test/test_archive_project.py`
- Modify `lib/archive_project.py`

- [ ] **Step 1: Write failing preflight tests**

Create `PreflightTests` covering:

- exact worktree-root requirement and rejection of `/`, home, repository parent;
- `origin/main` preference, `main` fallback, explicit valid `--main-ref`,
  missing/non-commit ref failure, and proof that no fetch command runs;
- cleanup rejection on protected, detached and unborn branches before any
  archive root, staging path, reset result or branch is created;
- archive-only dry-run success from named, detached and unborn HEAD states;
- nullable branch/commit recovery fields and fallback project ID in those states;
- project ID from `production/production-config.json`, branch fallback and
  directory fallback with portable slug normalization;
- new branch pre-existence locally or checked out in another worktree;
- final archive and adjacent reset-result collision;
- archive destination inside source and archive-name traversal rejection;
- exact tracked `.env.example` acceptance and content scanning;
- `.env`, runtime `.env.*`, private/auth paths and embedded credentials hard
  failing without printing values;
- a tracked sensitive file deleted from the worktree hard failing by inspecting
  Git tree/index paths as well as current files;
- spaces/Unicode acceptance and control-character rejection;
- internal symlink preservation eligibility; external, absolute, dangling,
  excluded-target link and special-file rejection;
- `.git`, dependencies, cache and OS-junk exclusion records;
- required command availability and destination free-space failure;
- capture of source and nearest existing archive-parent device/inode identities;
- dry-run producing the resolved plan while creating no directory, file, branch
  or reset result.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test.test_archive_project.PreflightTests -v
```

Expected: FAIL because complete preflight is absent.

- [ ] **Step 3: Implement `run_preflight()` as one read-only gate**

Implement:

```python
def discover_repository(cwd: Path) -> RepositoryState: ...
def resolve_base_ref(repo: RepositoryState, requested: str | None) -> ResolvedRef: ...
def build_inventory(root: Path, git_paths: GitPaths) -> Inventory: ...
def scan_secret_path(path: str, tracked: set[str]) -> str | None: ...
def scan_secret_stream(path: str, stream: BinaryIO) -> str | None: ...
def validate_link_chain(root: Path, path: Path, included: set[str]) -> str: ...
def capture_identity(path_or_nearest_parent: Path) -> FileIdentity: ...
def check_space(archive_parent: Path, required_bytes: int) -> None: ...
def run_preflight(args: Args, cwd: Path) -> Preflight: ...
```

Secret scanning reads every included regular file completely in chunks,
including binary data; it cannot skip large/binary files. Known placeholders
such as documented `sk-xxxxx` are not credentials, but every exception is an
exact tested pattern rather than a broad bypass.

All cleanup-specific branch/ref checks occur inside preflight. `--dry-run`
returns success only after `run_preflight()` completes and asserts no mutation.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m unittest auto-test.test_archive_project.PreflightTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: add archive safety preflight"
```

### Task 3: Recovery evidence for every Git state

**Files:**
- Modify `auto-test/test_archive_project.py`
- Modify `lib/archive_project.py`

- [ ] **Step 1: Write failing recovery tests**

Create fixtures for staged-only, unstaged-only, mixed staged/unstaged, deleted
text, modified/deleted binary, and untracked spaces/Unicode. Assert:

- staged and unstaged text evidence are both preserved;
- no `GIT binary patch` payload exists;
- `binary-changes.txt` lists modified and deleted binary paths;
- `untracked-files.txt` is NUL-safely derived and human-readable;
- detached and unborn archive-only recovery state is explicit;
- remote URLs with userinfo/query credentials are redacted;
- every generated recovery file is scanned before publication;
- a generated patch containing a historic deleted credential causes failure and
  removes staging without exposing the value.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test.test_archive_project.RecoveryEvidenceTests -v
```

- [ ] **Step 3: Implement recovery generation**

Use separate cached and worktree text diffs without `--binary`, exact NUL-safe
name/status commands, explicit binary change classification, redacted remote
metadata, and deterministic UTF-8 recovery documents. Never forward raw Git
stderr to user output before redaction/scanning.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m unittest auto-test.test_archive_project.RecoveryEvidenceTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: preserve archive recovery evidence"
```

### Task 4: Immutable staged archive and portable no-replace publication

**Files:**
- Modify `auto-test/test_archive_project.py`
- Modify `lib/archive_project.py`

- [ ] **Step 1: Write failing archive transaction tests**

Create `ArchiveTransactionTests` covering:

- default sibling and overridden archive paths;
- snapshot coverage of tracked, modified and untracked content;
- every exclusion path and rule recorded;
- exact protected entry set including directories, regular files and symlink
  type/mode/target;
- expected/actual counts and bytes, key-deliverable hashes, canonical JSON and
  sorted `SHA256SUMS`;
- domain-separated archive identity from exact manifest/checksum bytes;
- `archive-verification.json` outside protected payload but secret-scanned;
- secret scanning of manifest, checksum, verification and all success/error
  output before emission;
- initial-source versus staged-target mismatch on mid-copy mutation;
- staging cleanup on failure without source mutation;
- existing empty/nonempty target refusal;
- two concurrent publishers for the same name yielding one winner and one safe
  failure with no replacement.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test.test_archive_project.ArchiveTransactionTests -v
```

- [ ] **Step 3: Implement the archive transaction**

Implement:

```python
def copy_snapshot(preflight: Preflight, staging: Path) -> None: ...
def build_payload_manifest(staging: Path, preflight: Preflight) -> bytes: ...
def verify_payload(root: Path, manifest: dict) -> Verification: ...
def archive_identity(manifest: bytes, sums: bytes) -> str: ...
def publish_directory_no_replace(staging: Path, final: Path) -> None: ...
```

No-replace publication is concrete:

- macOS: call `renamex_np(..., RENAME_EXCL)` through `ctypes`;
- Linux: call `renameat2(..., RENAME_NOREPLACE)` through `ctypes`;
- unsupported platforms: fail before staging rather than weaken semantics.

Immediately before publication, revalidate source/archive-parent identities and
source freeze. Scan all copied and generated files, including manifest,
checksum and verification JSON. Fsync stable files/directories where supported.
The platform rename primitive is the single atomic commit point.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m unittest auto-test.test_archive_project.ArchiveTransactionTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: publish verified project archives"
```

### Task 5: Guarded Git reset transaction

**Files:**
- Modify `auto-test/test_archive_project.py`
- Modify `lib/archive_project.py`

- [ ] **Step 1: Write failing reset tests**

Create `ResetTransactionTests` covering:

- source change after publication blocks cleanup and preserves archive/source;
- formal archive mutation blocks cleanup;
- source root or archive-parent inode replacement blocks cleanup;
- old branch or base ref movement after publication blocks cleanup;
- atomic new ref creation conflict, including a branch in another worktree;
- checkout-obstructing untracked files without moving the old ref;
- nested repository cleanup preview and execution equivalence;
- old branch ref remains at original commit;
- new branch and HEAD equal frozen base commit;
- complete NUL-safe preview and removal of untracked/ignored files;
- complete post-reset status and clean dry-run set;
- required template files remain and project-only paths are absent;
- reset-result collision, concurrent creation, atomic no-replace publication;
- reset-result content/output secret scanning;
- reset success plus result-write failure returns nonzero while accurately
  reporting the verified clean workspace.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test.test_archive_project.ResetTransactionTests -v
```

- [ ] **Step 3: Implement reset with exact Git primitives**

Before every destructive action, revalidate frozen source/archive identities,
source inventory/status, full formal archive payload, base commit and old ref.

Create the target ref atomically:

```bash
git update-ref refs/heads/<new> <base-commit> 0000000000000000000000000000000000000000
```

Explicitly forbid `switch -C`, `checkout -B`, `reset`, and any force-update of
the old ref. Use `git clean -ndx -z` (or an equivalent NUL-safe Git command) to
derive and validate the exact cleanup set, then `git switch --discard-changes`
to the already-created branch and Git-native cleanup rooted at the verified
worktree. Revalidate the old ref after each step.

Publish reset-result by writing/fsyncing a same-directory temporary regular
file, then `os.link(temp, final)` as the atomic no-replace commit and unlink the
temporary name. A concurrent existing result is never overwritten.

- [ ] **Step 4: Run GREEN**

```bash
python3 -m unittest auto-test.test_archive_project.ResetTransactionTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: reset archived workspaces safely"
```

### Task 6: Documentation, integration and full security gates

**Files:**
- Modify `auto-test/test_archive_project.py`
- Modify `auto-test/run.sh`
- Modify `README.md`
- Modify `README.zh-CN.md`

- [ ] **Step 1: Write failing documentation tests**

Assert both READMEs document every approved flag, default archive location,
secret blockers, no-fetch behavior, immutable verification, new branch naming,
dry run and recovery evidence.

- [ ] **Step 2: Run RED**

```bash
python3 -m unittest auto-test.test_archive_project.DocumentationTests -v
```

- [ ] **Step 3: Add documentation, then integrate the test runner**

Document:

```bash
./archive-project.sh --archive-only
./archive-project.sh --next-project <id> --confirm-clean
```

Then add the archive suite to `auto-test/run.sh`.

- [ ] **Step 4: Run GREEN and repository gates**

```bash
python3 -m unittest auto-test/test_archive_project.py -v
bash auto-test/run.sh
bash auto-test/validate-main-boundary.sh
bash -n archive-project.sh
python3 -m py_compile lib/archive_project.py auto-test/test_archive_project.py
git diff --check
test -x archive-project.sh
```

- [ ] **Step 5: Run dependency/security checks**

This implementation adds no package dependency. Still run the repository
applicable audit and record unsupported package managers explicitly:

```bash
if [[ -f package-lock.json ]]; then npm audit; fi
if [[ -f requirements.txt ]]; then python3 -m pip_audit -r requirements.txt; fi
```

- [ ] **Step 6: Review the complete implementation range**

Use the base captured before implementation, not the working-tree-only diff:

```bash
git diff --stat c029185...HEAD
git diff --name-status c029185...HEAD
git diff c029185...HEAD -- \
  archive-project.sh lib/archive_project.py auto-test/test_archive_project.py \
  auto-test/run.sh README.md README.zh-CN.md
git ls-files --others --exclude-standard
```

Confirm no project artifact, secret, unsafe broad target, remote fetch/mutation,
or project-specific evidence entered `main`.

- [ ] **Step 7: Commit**

```bash
git add auto-test/test_archive_project.py auto-test/run.sh README.md README.zh-CN.md
git commit -m "docs: document project archive workflow"
```

### Task 7: Completion audit against the approved specification

**Files:**
- Verify: `docs/superpowers/specs/2026-07-30-project-archive-design.md`
- Verify: all implementation and test files above

- [ ] **Step 1: Build a requirement-to-evidence checklist**

For every spec section, name the implementation function, automated test and
fresh command output that proves it. Treat missing evidence as incomplete.

- [ ] **Step 2: Run fresh full verification**

```bash
python3 -m unittest auto-test/test_archive_project.py -v
bash auto-test/run.sh
bash auto-test/validate-main-boundary.sh
bash -n archive-project.sh
python3 -m py_compile lib/archive_project.py auto-test/test_archive_project.py
git diff --check
git status --short
```

- [ ] **Step 3: Perform a manual temporary-repository smoke test**

Create a fresh temporary Git repository, commit a `main` template, create a
dirty project branch, run archive-only, verify hashes, then run confirmed
cleanup and inspect old/new refs and final status. Never run cleanup against the
real repository.

- [ ] **Step 4: Commit any audit-only corrections after a new RED/GREEN cycle**

Do not claim completion until all requirements have direct current-state
evidence and the worktree contains only intentional changes.
