# Project Archive and Workspace Reset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reusable `archive-project.sh` command that creates a verified, browsable project archive and, with explicit confirmation, resets the same worktree path to a clean new project branch based on a frozen `main` commit.

**Architecture:** A minimal Bash wrapper delegates to a Python 3 standard-library core. The Python core owns path safety, inventory, secret scanning, staged copy, canonical manifests, verification, atomic publication and guarded Git reset; Git remains authoritative for refs, status and cleanup. End-to-end `unittest` cases create isolated temporary repositories so no destructive test can touch a real worktree.

**Tech Stack:** Bash, Python 3 standard library, Git CLI, `unittest`

---

## File map

- Create `archive-project.sh`: stable executable entry point that locates the repository and invokes the Python core.
- Create `lib/archive_project.py`: CLI parsing, project discovery, inventory, security checks, archive transaction, verification and reset transaction.
- Create `auto-test/test_archive_project.py`: unit and end-to-end tests using temporary Git repositories.
- Modify `README.md`: concise English command reference and safety behavior.
- Modify `README.zh-CN.md`: concise Chinese command reference and safety behavior.

### Task 1: CLI contract and safe repository discovery

**Files:**
- Create: `auto-test/test_archive_project.py`
- Create: `archive-project.sh`
- Create: `lib/archive_project.py`

- [ ] **Step 1: Write failing CLI tests**

Add tests that execute the root script and assert:

```python
def test_help_succeeds(self):
    result = self.run_archive("--help")
    self.assertEqual(result.returncode, 0)
    self.assertIn("--archive-only", result.stdout)

def test_cleanup_requires_confirmation(self):
    result = self.run_archive("--next-project", "next")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("--confirm-clean", result.stderr)

def test_archive_only_does_not_require_next_project(self):
    result = self.run_archive("--archive-only", "--dry-run")
    self.assertEqual(result.returncode, 0)
```

Fixture helpers must initialize a repository with configured test-only author
identity, commit a reusable template, create `main`, then create a
`project/current` branch. Script subprocesses always use the temporary
repository as `cwd`.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: FAIL because `archive-project.sh` does not exist.

- [ ] **Step 3: Implement the parser and discovery shell**

`archive-project.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/lib/archive_project.py" "$@"
```

The Python parser defines all approved flags and validates mode combinations.
Repository discovery uses `git rev-parse --show-toplevel`, requires `cwd` to be
that exact canonical root, reads the current branch without guessing and
resolves `origin/main`, then `main`, unless `--main-ref` was supplied.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: all Task 1 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add archive-project.sh lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: add archive command contract"
```

### Task 2: Deterministic inventory, exclusions and secret safety

**Files:**
- Modify: `auto-test/test_archive_project.py`
- Modify: `lib/archive_project.py`

- [ ] **Step 1: Write failing inventory tests**

Cover:

- project ID from `production/production-config.json`, branch fallback and
  portable slug normalization;
- `--archive-name` rejects separators, `.` and `..`;
- archive destination inside the source is refused;
- `.git`, `node_modules`, caches and OS junk are excluded and recorded;
- tracked `.env.example` is accepted and scanned;
- `.env`, runtime `.env.*`, private-key paths and embedded credential patterns
  hard-fail without printing matched values;
- Unicode and spaces are retained;
- internal symlinks are retained without dereference;
- external, dangling and excluded-target symlinks fail;
- included special files fail.

Example:

```python
def test_secret_match_reports_rule_not_value(self):
    secret = "sk-" + "A" * 32
    self.write("notes.txt", secret)
    result = self.run_archive("--archive-only")
    self.assertNotEqual(result.returncode, 0)
    self.assertIn("credential-openai-style", result.stderr)
    self.assertNotIn(secret, result.stdout + result.stderr)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.InventoryTests -v
```

Expected: FAIL because inventory and safety policies are not implemented.

- [ ] **Step 3: Implement inventory primitives**

Add focused data structures and functions:

```python
@dataclass(frozen=True)
class Entry:
    path: str
    kind: str
    mode: int
    size: int
    sha256: str | None = None
    link_target: str | None = None

def build_inventory(root: Path, tracked: set[str]) -> Inventory: ...
def scan_secret_path(relative_path: str, tracked: set[str]) -> str | None: ...
def scan_secret_bytes(relative_path: str, data: bytes) -> str | None: ...
def resolve_internal_link(root: Path, path: Path, included: set[str]) -> str: ...
```

Use `os.scandir`/`lstat`, never follow links during traversal, classify every
path, and store sorted relative POSIX paths. Explicit disposable directory
rules are centralized and reported. Content scanning uses bounded binary/text
handling and named patterns; failures print only path and rule ID.

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.InventoryTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: all implemented tests PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: add safe project inventory"
```

### Task 3: Staged archive, recovery evidence and immutable verification

**Files:**
- Modify: `auto-test/test_archive_project.py`
- Modify: `lib/archive_project.py`

- [ ] **Step 1: Write failing archive transaction tests**

Cover:

- default sibling `_archive/<project>-<timestamp>`;
- override root/name and refusal to overwrite;
- snapshot contains tracked, modified and untracked fixture files;
- recovery files exist and remote credentials are redacted;
- text patch contains no `GIT binary patch`; binary paths are listed separately;
- generated recovery files are secret-scanned;
- manifest is canonical and sorted with type/mode/hash metadata;
- `SHA256SUMS` covers protected regular files only;
- `archive-verification.json` reports `passed`;
- archive identity recomputes from manifest and checksum bytes;
- simulated copy/source mutation fails and never publishes a final archive;
- staging cleanup removes only its unique temporary directory.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.ArchiveTransactionTests -v
```

Expected: FAIL because the archive transaction is missing.

- [ ] **Step 3: Implement archive transaction**

Implement:

```python
def write_recovery_files(ctx: Context, staging: Path) -> None: ...
def copy_snapshot(ctx: Context, staging: Path) -> None: ...
def build_payload_manifest(staging: Path, ctx: Context) -> dict: ...
def verify_payload(archive: Path, manifest: dict) -> Verification: ...
def archive_identity(manifest_bytes: bytes, sums_bytes: bytes) -> str: ...
def publish_no_replace(staging: Path, final: Path) -> None: ...
```

Publication must have no-replace semantics. Create staging below the archive
root, verify the frozen source against staged content, scan all generated
outputs, fsync stable files where supported, then commit only when the final
path still does not exist. A concurrent winner causes safe failure.

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.ArchiveTransactionTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: create verified project archives"
```

### Task 4: Guarded workspace reset

**Files:**
- Modify: `auto-test/test_archive_project.py`
- Modify: `lib/archive_project.py`

- [ ] **Step 1: Write failing reset transaction tests**

Cover:

- cleanup refuses protected, detached and unborn branches;
- cleanup requires `--confirm-clean` and a valid new project slug;
- existing new branch refuses before archive mutation;
- source change after archive publication preserves archive and refuses cleanup;
- formal archive mutation preserves source and refuses cleanup;
- old branch ref remains at its original commit;
- new branch points at the frozen base commit;
- tracked, untracked and ignored project fixture files are absent;
- `git status --porcelain --untracked-files=all --ignored` contains no
  non-template residue;
- reset-result is adjacent, atomic and no-replace;
- result write failure returns non-zero while accurately reporting a clean
  reset;
- checkout obstruction and injected failures never move the old branch ref.

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.ResetTransactionTests -v
```

Expected: FAIL because reset mode is not implemented.

- [ ] **Step 3: Implement guarded reset**

Add:

```python
def assert_source_unchanged(ctx: Context) -> None: ...
def assert_archive_unchanged(ctx: Context) -> None: ...
def preview_clean_paths(root: Path) -> list[str]: ...
def reset_workspace(ctx: Context) -> ResetResult: ...
def write_reset_result_no_replace(ctx: Context, result: ResetResult) -> None: ...
```

Before the first destructive command, revalidate source/archive identities,
source freeze, full formal archive payload, old ref, base ref and target branch.
Create the new ref without moving the old ref, preview/validate cleanup paths,
force-switch to the new ref, perform Git-native cleanup, then verify old ref,
new ref, HEAD, ignored/untracked absence and required template files.

- [ ] **Step 4: Run focused and full tests**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.ResetTransactionTests -v
python3 -m unittest auto-test/test_archive_project.py -v
```

Expected: PASS with all destructive operations confined to temporary fixtures.

- [ ] **Step 5: Commit**

```bash
git add lib/archive_project.py auto-test/test_archive_project.py
git commit -m "feat: reset archived workspaces safely"
```

### Task 5: Documentation and repository gates

**Files:**
- Modify: `README.md`
- Modify: `README.zh-CN.md`
- Modify: `auto-test/run.sh`

- [ ] **Step 1: Write a failing integration assertion**

Extend the test suite to assert the documented command exists in both READMEs
and add the archive test command to `auto-test/run.sh`.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
python3 -m unittest auto-test.test_archive_project.DocumentationTests -v
```

Expected: FAIL because the usage section is absent.

- [ ] **Step 3: Add concise usage documentation**

Document:

```bash
./archive-project.sh --archive-only
./archive-project.sh --next-project <id> --confirm-clean
```

Explain the default sibling `_archive`, secret blockers, immutable verification,
new branch naming, no fetch, dry run and recovery evidence.

- [ ] **Step 4: Run all verification**

Run:

```bash
python3 -m unittest auto-test/test_archive_project.py -v
bash auto-test/run.sh
bash auto-test/validate-main-boundary.sh
bash -n archive-project.sh
python3 -m py_compile lib/archive_project.py auto-test/test_archive_project.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 5: Review security-sensitive diff**

Run:

```bash
git diff --check
git status --short
git diff -- archive-project.sh lib/archive_project.py auto-test/test_archive_project.py README.md README.zh-CN.md auto-test/run.sh
```

Verify no project-specific artifact, secret, broad unvalidated deletion target
or remote mutation was introduced.

- [ ] **Step 6: Commit**

```bash
git add archive-project.sh lib/archive_project.py auto-test/test_archive_project.py README.md README.zh-CN.md auto-test/run.sh
git commit -m "docs: document project archive workflow"
```
