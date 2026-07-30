# Project Archive and Workspace Reset Design

## Status

Approved in conversation on 2026-07-30.

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
└── verification.json
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
- for every included regular file: relative path, byte size and SHA-256;
- total included files and bytes;
- hashes of key deliverables when present;
- warnings and non-fatal observations.

`SHA256SUMS` contains the same included-file hashes in a standard sorted format.
Paths containing unsupported control characters cause a safe failure.

After copying, the tool recomputes every destination hash. `verification.json`
records expected and actual file counts, byte totals, hash results and overall
status. Cleanup is allowed only when the verification status is `passed`.

The archive itself receives a summary digest calculated from the final
`SHA256SUMS` and manifest. The script prints this digest on success.

## Secret handling

No secret value may be written to the archive, terminal output, command log,
manifest or recovery files.

Secret detection has two layers:

1. known secret-bearing filenames and directories are excluded;
2. likely embedded credential patterns are scanned locally with redacted
   reporting that prints paths and rule identifiers only.

In archive-only mode, excluded sensitive files are reported but do not prevent
archiving. In cleanup mode, the presence of any excluded sensitive file is a
hard blocker because cleanup would destroy a file that was not preserved.
Users must relocate or remove those files themselves and rerun the command.

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
7. checks required commands and available destination space;
8. prints the resolved old project, archive destination, base commit and new
   branch.

`--dry-run` exits successfully after this phase and performs no writes.

### Phase 2: staged archive

The script creates a uniquely named staging directory beneath the archive root
on the same filesystem as the final archive. It copies the snapshot, writes
recovery evidence, generates manifests and verifies every copied file.

If any operation fails, the script removes only the uniquely identified staging
directory and leaves the source worktree unchanged.

After verification passes, the staging directory is atomically renamed to the
final archive directory. An existing target is never replaced.

### Phase 3: workspace reset

This phase runs only when all of the following are true:

- cleanup mode was explicitly requested with `--confirm-clean`;
- archive verification passed;
- the final archive exists at the expected path;
- no excluded sensitive file would be lost;
- the base commit and new branch name still match preflight.

The tool then:

1. creates and switches to the new project branch at the frozen base commit,
   discarding archived tracked worktree changes;
2. removes untracked and ignored project files from the explicitly resolved
   worktree root while preserving `.git` metadata;
3. verifies that `HEAD` equals the frozen base commit;
4. verifies the expected new branch name;
5. verifies that `git status --porcelain` is empty;
6. verifies that reusable template files required by the repository remain;
7. verifies that project-only paths such as `production/`, `scenes/`,
   `final.mp4`, and project subtitles are absent unless tracked by the base
   commit.

The reset implementation may use Git-native cleanup commands only after the
source root, branch, archive and confirmation guard have all been validated. It
must not accept `/`, a home directory, the repository parent, an unresolved
environment variable, or a glob as a cleanup target.

## Failure and recovery behavior

- **Preflight failure:** no archive or source mutation.
- **Copy or verification failure:** remove only the unique staging directory;
  leave the source worktree unchanged.
- **Archive committed, reset not started:** keep the verified archive and leave
  the source unchanged.
- **Reset failure after mutation starts:** keep the verified archive, return a
  non-zero status, print the archive and recovery-document paths, and do not
  claim that the workspace is ready.

The script should perform automatic rollback only when it can prove the
destination and source states. It must prefer a verified archive plus explicit
recovery instructions over an uncertain automatic overwrite.

## Output

Success output includes:

- absolute archive path;
- archive manifest path and summary digest;
- old branch and commit;
- new branch and frozen base commit, when cleanup ran;
- excluded disposable paths;
- archive verification status;
- final workspace cleanliness status.

Machine-readable status is also written to `verification.json`. Human output
must be concise and must not expose sensitive values.

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
- simulated copy and verification failures leaving the source unchanged;
- refusal on protected branches;
- refusal when the new branch already exists;
- successful reset to the frozen base commit in a temporary repository;
- final clean worktree and absence of project-only fixture paths;
- no overwrite of an existing archive;
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
