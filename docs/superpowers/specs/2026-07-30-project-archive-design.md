# Project archive design

## Purpose

`archive-project.sh` is a root-level Bash 3.2 command for the transition between
single-video projects. It performs two visible steps:

1. move files that belong only to the current project into a browsable archive;
2. detach the same worktree at a frozen `main` commit.

It never fetches, deletes a branch, or scans file contents for secrets.

## Command

```bash
./archive-project.sh \
  [--main-ref REF] \
  [--archive-root DIR] \
  [--archive-name NAME] \
  [--dry-run] [--yes]
```

The command must run from the exact repository root. `--main-ref` defaults to
`main` and is resolved once to a commit before planning. The archive root
defaults to the sibling `../_archive`. The final and staging paths must not
exist, and the archive root must be outside the source repository.

## Classification

The frozen main tree is the boundary:

- A candidate is an existing regular file or symlink whose changed tracked path
  does not exist in main, or an untracked, non-ignored file.
- A shared modification is any changed, deleted, type-changed, or renamed source
  path that exists in main.
- An ignored file is any result from
  `git ls-files -z --others --ignored --exclude-standard`.

Shared modifications block the command before mutation and direct the operator
to consult an agent. Ignored files also block before mutation, because the
correct action may be delete, archive, or keep. Paths containing newlines or
other control characters are unsupported and block. Printed paths are safely
quoted.

Git discovery is captured in temporary NUL-delimited files. Failures from
`git diff` or either `git ls-files` inventory are checked explicitly and block
before archive or worktree mutation.

## Transaction

After preflight, the command prints the frozen commit, destination, and candidate
count. `--dry-run` exits without writes. Otherwise the operator confirms, unless
`--yes` is present.

Candidates are moved into `staging/files/` with their relative paths intact;
archive metadata remains at `staging/MANIFEST.txt`, so a project file named
`MANIFEST.txt` cannot collide. Filesystem tools receive absolute operands.
Empty source parents are removed only with `rmdir`.

Moved paths are kept in a Bash array. Any staging-directory, move, or manifest
failure restores already moved files in reverse order before Git changes.
A failed, no-change Git switch uses the same rollback. Recovery output safely
quotes the affected path and staging location.

The reset is:

```bash
git switch --detach --discard-changes <frozen-main-commit>
```

This works even when `main` is checked out in another worktree. Success requires
exact HEAD equality, empty normal/untracked status, and no ignored files. The old
branch ref and history remain unchanged.

Before reset, `MANIFEST.txt` records the UTC timestamp, source branch and
commit, main ref and commit, safely quoted moved paths, SHA-256 for regular
files, and link targets for symlinks. After reset verification, staging is
renamed atomically to the final archive path. A publication failure reports and
preserves staging.

On success, the command prints the archive path, old branch/commit, detached
main commit, and asks the operator to have an agent create the next project
branch.

## Tests

The temporary-repository suite covers argument handling, blockers and
no-mutation guarantees, dry-run and decline, tracked additions, untracked files,
symlinks and hashes, detached reset and old-ref preservation, collisions,
switch rollback through a PATH-injected Git wrapper, discovery and second-move
failure injection, metadata-name collision, dash-prefixed paths, spaces and
Unicode, control-character rejection, and main checked out in another worktree.
