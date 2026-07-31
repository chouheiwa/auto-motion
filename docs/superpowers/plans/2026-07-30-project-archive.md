# Project archive implementation plan

## Goal

Replace the Python archive subsystem with one small, macOS-compatible
`archive-project.sh` that archives project-only files and detaches the worktree
at a frozen main commit.

## TDD sequence

1. Replace the old broad test suite with concise end-to-end tests using isolated
   temporary Git repositories.
2. Run the suite against the old Python workflow and record the expected RED.
3. Implement argument parsing and read-only preflight in Bash.
4. Implement staged moves, switch rollback, detached-main verification,
   `MANIFEST.txt`, and final rename.
5. Run the focused suite to GREEN.

The tests cover help and invalid arguments; shared-modification and ignored-file
blockers without mutation; dry-run and prompt decline; candidate moves with
paths, symlinks, and hashes; detached reset with the old ref unchanged;
destination collision; injected switch failure rollback; spaces and Unicode;
control-character paths; checked Git-discovery failures; second-move rollback;
the `files/` payload boundary; dash-prefixed paths; and main checked out in
another worktree.

## Documentation and integration

1. Document the two-step operator flow and its blockers in the Chinese and
   English READMEs.
2. Run the archive unit suite from `auto-test/run.sh` before its external-tool
   end-to-end checks.
3. Remove `lib/archive_project.py` and obsolete archive-only, new-branch,
   immutable-JSON, secret-scan, and recovery-record claims.

## Verification

Run:

```bash
bash -n archive-project.sh
python3 -m unittest auto-test/test_archive_project.py -v
bash auto-test/run.sh
git diff --check
bash auto-test/validate-main-boundary.sh
```

Also confirm `archive-project.sh` is executable, the implementation and tests
remain within their size targets, and the final diff contains no per-video
content.
