# Project Archive and Workspace Reset Design

## Status

Concept approved in conversation on 2026-07-30. Revised after independent
specification review; implementation remains pending final specification
approval.

## Purpose

Add a reusable root-level `archive-project.sh` command that preserves the
current single-video project as a verified, browsable archive and then restores
the same working-directory path to a clean project branch based on `main`.

This tool exists to enforce the repository boundary that reusable templates and
tools belong on `main`, while each video's content remains isolated on its own
branch or worktree.

## User-facing contract

Primary invocation:

```bash
./archive-project.sh \
  --next-project <new-project-id> \
  --confirm-clean
```

Optional flags:

```text
--archive-root <directory>  Override the default sibling ../_archive directory.
--archive-name <name>       Override the generated archive directory name.
--main-ref <git-ref>        Override the base ref; default origin/main, then main.
--dry-run                   Print the resolved plan without writing or deleting.
--archive-only              Create and verify an archive without cleaning.
--help                      Print usage.
```

`--next-project` and `--confirm-clean` are required for cleanup mode.
`--archive-only` does not require either flag. Cleanup is never inferred from
the absence of a flag.

The new branch name is:

```text
project/<sanitized-next-project-id>-<YYYYMMDD-HHMMSS>
```

The script must refuse to overwrite an existing branch or archive directory.

## Archive location and naming

The default archive root is a sibling of the repository:

```text
<repository-parent>/_archive/
```

The default archive directory name is:

```text
<old-project-id>-<YYYYMMDD-HHMMSS>
```

The old project ID is resolved in this order:

1. a project identifier in `production/production-config.json`;
2. the current Git branch;
3. the repository directory name.

All derived names must be normalized to a portable, non-empty slug. The
resolved archive directory must be outside the source worktree. Paths are
resolved to absolute canonical paths before any mutation.

## Archive layout

```text
_archive/<old-project-id>-<timestamp>/
├── snapshot/
├── recovery/
│   ├── git-state.txt
│   ├── tracked-changes.patch
│   ├── untracked-files.txt
│   └── RESTORE.md
├── archive-manifest.json
├── SHA256SUMS
└── archive-verification.json
```

Cleanup results are written after the archive transaction to an adjacent file,
not into the immutable archive:

```text
_archive/<old-project-id>-<timestamp>.reset-result.json
```

### `snapshot/`

The snapshot is a directly browsable copy of the project worktree. It includes:

- source articles, Markdown, text, reference subtitles, images, audio and video;
- `production/`, `scenes/`, `final.mp4`, `publish.md`, and final subtitles;
- scene source projects, render logs, quality-control evidence and approvals;
- tracked and untracked project-local code changes.

It excludes:

- `.git` worktree metadata;
- dependency directories such as `node_modules/`;
- package-manager, browser, build and disposable render caches;
- operating-system junk and temporary files;
- secret-bearing files such as `.env`, `.env.*`, private keys and authentication
  configuration.

Every exclusion rule and every excluded path is recorded in
`archive-manifest.json`. Files must never be skipped silently.

Included symbolic links are copied as links and are never dereferenced. A link
is accepted only when its resolved target is an existing path inside the source
worktree. Absolute, dangling and worktree-external links are hard failures.
Included sockets, devices, FIFOs and other special files are also hard failures.

### Recovery evidence

`git-state.txt` records, without credentials:

- absolute source path;
- current branch and commit;
- resolved `main` ref and commit;
- configured remote names and redacted remote locations;
- porcelain Git status;
- timestamp and script version.

`tracked-changes.patch` is generated as a binary-safe Git diff of tracked
working-tree and index changes. `untracked-files.txt` lists untracked paths.
The complete file content remains available under `snapshot/`.

Cleanup requires a named, existing, non-protected branch. Detached HEAD and an
unborn branch are supported by archive-only mode but are hard blockers for
cleanup.

`RESTORE.md` provides commands for:

- inspecting the original branch;
- copying the snapshot into a new worktree;
- applying the tracked patch when appropriate;
- verifying restored files against `SHA256SUMS`.

The repository's original branch and commit history are not deleted.

## Manifest and verification

`archive-manifest.json` is deterministic apart from explicitly recorded runtime
metadata. It contains:

- schema version and script version;
- archive creation time;
- source path, project ID, branch and commit;
- resolved base ref and base commit;
- archive mode and command options, excluding secrets;
- sorted inclusion and exclusion records;
- for every protected payload entry: relative path, file type, portable mode,
  byte size and SHA-256, or link target for a symbolic link;
- total included files and bytes;
- hashes of key deliverables when present;
- warnings and non-fatal observations.

The protected payload includes all entries beneath `snapshot/` and `recovery/`.
`SHA256SUMS` contains hashes for all protected regular files and domain-separated
hashes of accepted symbolic-link targets in a standard sorted format. Paths
containing unsupported control characters cause a safe failure.

After copying, the tool recomputes every destination hash and validates file
types, modes and link targets. `archive-verification.json` records expected and
actual file counts, byte totals, metadata and hash results, plus overall status.
It is written before the staging directory is atomically committed and is not
part of the protected payload.

The immutable archive identity is a domain-separated SHA-256 calculated from the
exact bytes of `archive-manifest.json` and `SHA256SUMS`. Those two files bind the
complete protected payload without requiring a self-referential hash.
`archive-verification.json` records this identity, and the script prints it on
success. The adjacent reset-result file records the archive identity it refers
to but is explicitly outside the immutable archive boundary.

## Secret handling

No secret value may be written to the archive, terminal output, command log,
manifest or recovery files.

Secret detection has two layers:

1. known secret-bearing filenames and directories are excluded;
2. likely embedded credential patterns are scanned locally with redacted
   reporting that prints paths and rule identifiers only.

Any known secret-bearing path or credential-pattern match is a hard failure in
both archive-only and cleanup modes. A match reports only the relative path and
rule identifier; it never prints the matching content. There is no general
command-line bypass. Users must relocate or remove sensitive files themselves
and rerun the command.

Remote URLs are redacted before recording. URLs containing userinfo, access
tokens or credential-like query parameters must never be emitted verbatim.

## Transaction model

### Phase 1: read-only preflight

Before creating files, the script:

1. verifies that it is running at the root of a Git worktree;
2. refuses cleanup from protected branches such as `main` and `master`;
3. resolves the requested base ref to a fixed local commit without fetching;
4. validates that the new branch does not exist;
5. validates and canonicalizes the archive destination;
6. inventories included, excluded and sensitive paths;
7. rejects unsupported links, special files and unsafe path names;
8. captures a frozen source inventory containing every non-disposable entry's
   type, mode, size, link target or hash, plus exact Git status;
9. checks required commands and available destination space;
10. prints the resolved old project, archive destination, base commit and new
   branch.

`--dry-run` exits successfully after this phase and performs no writes.

### Phase 2: staged archive

The script creates a uniquely named staging directory beneath the archive root
on the same filesystem as the final archive. It copies the snapshot, writes
recovery evidence, generates manifests and verifies every copied file.

Verification compares the staged destination to the frozen source inventory,
not merely to a post-copy view of the source. This detects files that changed
while being copied.

If any operation fails, the script removes only the uniquely identified staging
directory and leaves the source worktree unchanged.

After verification passes, the staging directory is atomically renamed to the
final archive directory. An existing target is never replaced.

Immediately before cleanup, the tool rescans the source and compares it to the
frozen source inventory. The comparison covers the complete non-disposable file
set, file types, modes, sizes, link targets, hashes and exact Git status. Any
addition, deletion or change preserves the completed archive but refuses
cleanup. Changes beneath explicitly disposable cache directories may be
reported without blocking because those directories are neither archived nor
recoverable project evidence.

### Phase 3: workspace reset

This phase runs only when all of the following are true:

- cleanup mode was explicitly requested with `--confirm-clean`;
- archive verification passed;
- the final archive exists at the expected path;
- no excluded sensitive file would be lost;
- the base commit and new branch name still match preflight.

The tool then:

1. records the original branch ref and its target commit again;
2. creates the new branch ref at the frozen base commit without moving or
   rewriting the original branch ref;
3. previews the exact Git-native untracked/ignored cleanup set and verifies that
   every reported path is beneath the resolved worktree root;
4. force-switches the worktree to the already-created new branch, discarding
   only the archived tracked worktree state and files that obstruct checkout;
5. verifies immediately that the new branch and `HEAD` equal the frozen base
   commit and that the original branch ref still points to its original commit;
6. removes the previewed untracked and ignored project files with Git-native
   cleanup rooted at the verified worktree;
7. verifies again that the original branch ref was not moved;
8. verifies that no untracked or ignored entry remains using complete Git status
   and an equivalent Git-native cleanup dry run;
9. verifies that reusable template files required by the repository remain;
10. verifies that project-only paths such as `production/`, `scenes/`,
   `final.mp4`, and project subtitles are absent unless tracked by the base
   commit;
11. writes the adjacent reset-result file with the archive identity, old and new
   refs, cleanup result and final workspace status.

The reset has no persistent local-file whitelist: a reusable configuration that
must survive belongs in the tracked `main` template, while secrets must live
outside the project directory.

The reset implementation may use Git-native forced switch and cleanup commands
only after the source root, named old branch, unchanged old ref, archive
identity, source freeze and confirmation guard have all been validated. It must
never reset or force-update the original branch ref. It must not accept `/`, a
home directory, the repository parent, an unresolved environment variable, or
a glob as a cleanup target.

## Failure and recovery behavior

- **Preflight failure:** no archive or source mutation.
- **Copy or verification failure:** remove only the unique staging directory;
  leave the source worktree unchanged.
- **Archive committed, reset not started:** keep the verified archive and leave
  the source unchanged.
- **Reset failure after mutation starts:** keep the verified archive, return a
  non-zero status, write a failed adjacent reset-result when possible, print the
  archive and recovery-document paths, and do not claim that the workspace is
  ready.

The script should perform automatic rollback only when it can prove the
destination and source states. It must prefer a verified archive plus explicit
recovery instructions over an uncertain automatic overwrite.

## Output

Success output includes:

- absolute archive path;
- archive manifest path and immutable archive identity;
- old branch and commit;
- new branch and frozen base commit, when cleanup ran;
- excluded disposable paths;
- archive verification status;
- final workspace cleanliness status.

Machine-readable archive status is written to `archive-verification.json`.
Machine-readable cleanup status is written to the adjacent reset-result file.
Human output must be concise and must not expose sensitive values.

## Implementation architecture and portability

`archive-project.sh` is a small Bash entry point that resolves its own location
and executes a Python 3 standard-library implementation under `lib/`. Python
performs argument parsing, canonical path validation, inventory, copy, metadata
handling, hashing, JSON serialization, secret scanning and subprocess
coordination. This avoids incompatible macOS/Linux variants of `sha256sum`,
`stat`, `readlink` and `cp`.

Git remains the authority for branch operations, status and cleanup. Structured
Git output uses NUL delimiters where available so spaces, Unicode and newlines
cannot be misparsed. Unsupported control characters are rejected before an
archive is created.

The tool records the source and archive-root device/inode identities during
preflight and revalidates them immediately before atomic rename and every
destructive Git action. A symlink swap, directory replacement or source-root
identity change is a hard failure.

## Main-branch boundary

The reusable implementation, tests and documentation belong on `main`. Tests
must use generated fixtures and temporary Git repositories. They must not
contain or depend on any specific article, scene number, voice, production
record, archive, final video or project-branch evidence.

Before merge, the implementation must pass:

```bash
auto-test/validate-main-boundary.sh
```

## Test strategy

Tests should cover at least:

- help, invalid flags and missing cleanup confirmation;
- archive-only mode with tracked and untracked fixture files;
- project-ID resolution and slug sanitization;
- default and overridden archive paths;
- refusal when the archive is inside the source worktree;
- deterministic sorted manifests and valid SHA-256 values;
- preservation of spaces and Unicode in filenames;
- exclusions recorded without silent omission;
- refusal to clean when excluded sensitive files exist;
- redaction of credential-bearing remote URLs;
- hard failure for embedded credential matches without leaking matched values;
- preservation of internal symbolic links without dereferencing;
- refusal of external, absolute and dangling links and included special files;
- source changes during copying being detected by destination verification;
- source changes after archive commit refusing cleanup;
- simulated copy and verification failures leaving the source unchanged;
- refusal on protected branches;
- refusal from detached HEAD and unborn branches in cleanup mode;
- refusal when the new branch already exists;
- checkout obstruction by untracked files without moving the old branch ref;
- successful reset to the frozen base commit in a temporary repository;
- original branch ref remaining unchanged through a successful reset;
- final absence of tracked changes, untracked files and ignored files;
- final clean worktree and absence of project-only fixture paths;
- no overwrite of an existing archive;
- traversal rejection in `--archive-name` and safe resolution of nonexistent
  destination paths;
- macOS-compatible operation using Python standard-library file primitives;
- boundary-validator success.

Destructive-path tests must run only inside temporary directories created by
the test harness.

## Non-goals

- Uploading archives to cloud storage.
- Deleting Git branches or repository history.
- Fetching or updating `main` from a remote.
- Archiving user-level MiniMax credentials or other authentication state.
- Compressing archives by default.
- Starting TTS, rendering or any production workflow for the next project.
