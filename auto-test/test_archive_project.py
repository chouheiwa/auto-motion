#!/usr/bin/env python3
"""End-to-end tests for the deliberately small archive-project.sh workflow."""

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest


SOURCE_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SOURCE_ROOT / "archive-project.sh"


class ArchiveProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.repo = self.base / "project"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Archive Test")
        self.git("config", "user.email", "archive@example.test")
        (self.repo / "shared.txt").write_text("shared\n", encoding="utf-8")
        (self.repo / ".gitignore").write_text("ignored/\n.env\n", encoding="utf-8")
        self.git("add", ".")
        self.git("commit", "-m", "main")
        self.main_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("switch", "-c", "video-one")
        self.old_commit = self.git("rev-parse", "HEAD").stdout.strip()
        self.archive_root = self.base / "archives"

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args, cwd=None, check=True, env=None):
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=check,
        )

    def run_script(self, *args, input_text=None, env=None):
        merged = os.environ.copy()
        if env:
            merged.update(env)
        return subprocess.run(
            [str(SCRIPT), *args],
            cwd=self.repo,
            env=merged,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def archive_args(self, name="saved"):
        return ("--archive-root", str(self.archive_root), "--archive-name", name)

    def assert_clean_on_old_branch(self):
        self.assertEqual("video-one", self.git("branch", "--show-current").stdout.strip())
        self.assertEqual(self.old_commit, self.git("rev-parse", "HEAD").stdout.strip())

    def test_help_and_invalid_arguments(self):
        help_result = self.run_script("--help")
        self.assertEqual(0, help_result.returncode, help_result.stdout)
        self.assertIn("--main-ref", help_result.stdout)
        self.assertIn("--dry-run", help_result.stdout)
        self.assertNotIn("--archive-only", help_result.stdout)
        invalid = self.run_script("--not-a-real-option")
        self.assertNotEqual(0, invalid.returncode)
        self.assertIn("Unknown option", invalid.stdout)

    def test_shared_modification_blocks_without_mutation(self):
        (self.repo / "shared.txt").write_text("changed\n", encoding="utf-8")
        before = self.git("status", "--porcelain=v1").stdout
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("shared modifications", result.stdout.lower())
        self.assertIn("shared.txt", result.stdout)
        self.assertIn("consult an agent", result.stdout.lower())
        self.assertEqual(before, self.git("status", "--porcelain=v1").stdout)
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_renamed_main_file_is_a_shared_blocker(self):
        self.git("mv", "shared.txt", "project-only.txt")
        before = self.git("status", "--porcelain=v1").stdout
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("shared modifications", result.stdout.lower())
        self.assertIn("shared.txt", result.stdout)
        self.assertEqual(before, self.git("status", "--porcelain=v1").stdout)
        self.assertTrue((self.repo / "project-only.txt").exists())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_ignored_file_blocks_without_mutation(self):
        ignored = self.repo / "ignored" / "cache.bin"
        ignored.parent.mkdir()
        ignored.write_bytes(b"cache")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("ignored files", result.stdout.lower())
        self.assertIn("ignored/cache.bin", result.stdout)
        self.assertIn("delete, archive, or keep", result.stdout.lower())
        self.assertTrue(ignored.exists())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_dry_run_reports_plan_and_writes_nothing(self):
        (self.repo / "notes.txt").write_text("notes\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--dry-run")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn(self.main_commit, result.stdout)
        self.assertIn("Candidate count: 1", result.stdout)
        self.assertTrue((self.repo / "notes.txt").exists())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_git_discovery_failure_blocks_without_mutation(self):
        added = self.repo / "tracked-added.txt"
        added.write_text("tracked\n", encoding="utf-8")
        self.git("add", "tracked-added.txt")
        bin_dir = self.base / "git-fail-bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "git"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "${1-}" == "diff" ]]; then exit 73; fi\n'
            'exec "$REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        env = {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": shutil.which("git"),
        }
        result = self.run_script(*self.archive_args(), "--yes", env=env)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("git diff", result.stdout.lower())
        self.assertEqual("tracked\n", added.read_text())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_moves_added_untracked_and_symlink_and_writes_manifest(self):
        tracked = self.repo / "shots" / "clip.txt"
        tracked.parent.mkdir()
        tracked.write_text("clip bytes\n", encoding="utf-8")
        self.git("add", "shots/clip.txt")
        untracked = self.repo / "notes" / "idea.txt"
        untracked.parent.mkdir()
        untracked.write_text("an idea\n", encoding="utf-8")
        os.symlink("../shots/clip.txt", self.repo / "notes" / "clip-link")
        candidate_manifest = self.repo / "MANIFEST.txt"
        candidate_manifest.write_text("project manifest\n", encoding="utf-8")

        result = self.run_script(*self.archive_args(), "--yes")
        self.assertEqual(0, result.returncode, result.stdout)
        archive = self.archive_root / "saved"
        files = archive / "files"
        self.assertEqual("clip bytes\n", (files / "shots" / "clip.txt").read_text())
        self.assertEqual("an idea\n", (files / "notes" / "idea.txt").read_text())
        self.assertEqual("../shots/clip.txt", os.readlink(str(files / "notes" / "clip-link")))
        self.assertEqual("project manifest\n", (files / "MANIFEST.txt").read_text())
        self.assertFalse(tracked.exists())
        self.assertFalse(untracked.exists())
        manifest = (archive / "MANIFEST.txt").read_text(encoding="utf-8")
        expected_hash = hashlib.sha256(b"clip bytes\n").hexdigest()
        self.assertIn("source_branch: video-one", manifest)
        self.assertIn("main_commit: " + self.main_commit, manifest)
        self.assertIn("shots/clip.txt", manifest)
        self.assertIn(expected_hash, manifest)
        self.assertIn("symlink_target: '../shots/clip.txt'", manifest)

    def test_reset_is_detached_at_main_and_old_ref_is_unchanged(self):
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual("", self.git("branch", "--show-current").stdout.strip())
        self.assertEqual(self.main_commit, self.git("rev-parse", "HEAD").stdout.strip())
        self.assertEqual(self.old_commit, self.git("rev-parse", "video-one").stdout.strip())
        self.assertEqual("", self.git("status", "--porcelain=v1").stdout)
        self.assertIn("ask an agent to create the next project branch", result.stdout.lower())

    def test_declining_prompt_writes_nothing(self):
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), input_text="no\n")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("[y/N]", result.stdout)
        self.assertTrue((self.repo / "project.txt").exists())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_existing_archive_collision_is_refused(self):
        final = self.archive_root / "saved"
        final.mkdir(parents=True)
        marker = final / "keep"
        marker.write_text("keep\n", encoding="utf-8")
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("already exists", result.stdout)
        self.assertEqual("keep\n", marker.read_text())
        self.assertTrue((self.repo / "project.txt").exists())
        self.assert_clean_on_old_branch()

    def test_switch_failure_rolls_back_moved_files(self):
        tracked = self.repo / "added.txt"
        tracked.write_text("tracked\n", encoding="utf-8")
        self.git("add", "added.txt")
        untracked = self.repo / "loose.txt"
        untracked.write_text("loose\n", encoding="utf-8")
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "git"
        real_git = shutil.which("git")
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'if [[ "${1-}" == "switch" ]]; then exit 88; fi\n'
            'exec "$REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        env = {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "REAL_GIT": real_git,
        }
        result = self.run_script(*self.archive_args(), "--yes", env=env)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("rolled back", result.stdout.lower())
        self.assertEqual("tracked\n", tracked.read_text())
        self.assertEqual("loose\n", untracked.read_text())
        self.assertFalse((self.archive_root / "saved").exists())
        self.assert_clean_on_old_branch()

    def test_second_move_failure_rolls_back_every_file(self):
        first = self.repo / "one.txt"
        second = self.repo / "two.txt"
        first.write_text("one\n", encoding="utf-8")
        second.write_text("two\n", encoding="utf-8")
        bin_dir = self.base / "mv-fail-bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "mv"
        wrapper.write_text(
            "#!/usr/bin/env bash\n"
            'count=0; [[ ! -f "$MV_COUNT_FILE" ]] || count="$(cat "$MV_COUNT_FILE")"\n'
            'count=$((count + 1)); printf "%s" "$count" > "$MV_COUNT_FILE"\n'
            'if [[ "$count" -eq 2 ]]; then exit 74; fi\n'
            'exec "$REAL_MV" "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
        env = {
            "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
            "REAL_MV": shutil.which("mv"),
            "MV_COUNT_FILE": str(self.base / "mv-count"),
        }
        result = self.run_script(*self.archive_args(), "--yes", env=env)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("rolled back", result.stdout.lower())
        self.assertIn("'two.txt'", result.stdout)
        self.assertEqual("one\n", first.read_text())
        self.assertEqual("two\n", second.read_text())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_dash_prefixed_root_file_archives_safely(self):
        path = self.repo / "-i"
        path.write_text("dash\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(
            "dash\n", (self.archive_root / "saved" / "files" / "-i").read_text()
        )
        self.assertEqual("", self.git("branch", "--show-current").stdout.strip())
        self.assertEqual(self.main_commit, self.git("rev-parse", "HEAD").stdout.strip())

    def test_spaces_and_unicode_paths_are_preserved(self):
        path = self.repo / "镜头 notes" / "第一 幕.txt"
        path.parent.mkdir()
        path.write_text("内容\n", encoding="utf-8")
        result = self.run_script(*self.archive_args("归档 one"), "--yes")
        self.assertEqual(0, result.returncode, result.stdout)
        archived = self.archive_root / "归档 one" / "files" / "镜头 notes" / "第一 幕.txt"
        self.assertEqual("内容\n", archived.read_text(encoding="utf-8"))
        self.assertIn("镜头", (self.archive_root / "归档 one" / "MANIFEST.txt").read_text())

    def test_newline_path_is_blocked(self):
        odd = self.repo / "bad\nname.txt"
        odd.write_text("bad\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unsupported control", result.stdout.lower())
        self.assertTrue(odd.exists())
        self.assertFalse(self.archive_root.exists())

    def test_newline_symlink_target_is_blocked(self):
        link = self.repo / "unsafe-link"
        os.symlink("bad\ntarget", str(link))
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertNotEqual(0, result.returncode)
        self.assertIn("symlink target", result.stdout.lower())
        self.assertIn("consult an agent", result.stdout.lower())
        self.assertTrue(link.is_symlink())
        self.assertFalse(self.archive_root.exists())
        self.assert_clean_on_old_branch()

    def test_archive_root_symlink_resolving_inside_repo_is_blocked(self):
        link = self.base / "repo-link"
        os.symlink(str(self.repo), str(link))
        inside = link / "archives"
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(
            "--archive-root", str(inside), "--archive-name", "saved", "--yes"
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("outside the source repository", result.stdout)
        self.assertFalse((self.repo / "archives").exists())
        self.assertTrue((self.repo / "project.txt").exists())
        self.assert_clean_on_old_branch()

    def test_root_archive_canonicalization_preserves_slash_in_dry_run(self):
        source = SCRIPT.read_text(encoding="utf-8")
        helper_source = source.split("\ncontains_path() {", 1)[0]
        helper = subprocess.run(
            ["/bin/bash", "-c", helper_source + '\nrepo_root=/unused\ncanonicalize_absolute /'],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(0, helper.returncode, helper.stdout)
        self.assertEqual("/\n", helper.stdout)

        name = "auto-motion-root-dry-run-{0}".format(os.getpid())
        destination = Path("/") / name
        self.assertFalse(destination.exists())
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(
            "--archive-root", "/", "--archive-name", name, "--dry-run"
        )
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("Archive destination: '/{0}'".format(name), result.stdout)
        self.assertFalse(destination.exists())
        self.assert_clean_on_old_branch()

    def test_user_controlled_destination_is_shell_quoted(self):
        root = self.base / "archive root"
        name = "director's cut"
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(
            "--archive-root", str(root), "--archive-name", name, "--dry-run"
        )
        self.assertEqual(0, result.returncode, result.stdout)
        destination = str(root.resolve() / name)
        quoted = "'" + destination.replace("'", "'\\''") + "'"
        self.assertIn("Archive destination: " + quoted, result.stdout)

    def test_main_checked_out_in_other_worktree_is_supported(self):
        other = self.base / "main-worktree"
        self.git("worktree", "add", str(other), "main")
        (self.repo / "project.txt").write_text("project\n", encoding="utf-8")
        result = self.run_script(*self.archive_args(), "--yes")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual("", self.git("branch", "--show-current").stdout.strip())
        self.assertEqual(self.main_commit, self.git("rev-parse", "HEAD").stdout.strip())
        self.assertEqual("main", self.git("branch", "--show-current", cwd=other).stdout.strip())


if __name__ == "__main__":
    unittest.main()
