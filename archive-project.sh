#!/usr/bin/env bash
set -euo pipefail
usage() {
  cat <<'EOF'
Usage: ./archive-project.sh [options]
Move project-only files to an archive, then detach this worktree at main.
Options:
  --main-ref REF         Main ref to freeze (default: main)
  --archive-root DIR     Archive parent (default: sibling ../_archive)
  --archive-name NAME    Archive directory name (default: branch-timestamp)
  --yes                  Skip the confirmation prompt
  --dry-run              Print the plan without writing anything
  --help                 Show this help
EOF
}
die() {
  printf 'Error: %s\n' "$*" >&2; exit 1
}
die_path() {
  printf 'Error: %s' "$1" >&2; quote "$2" >&2; printf '\n' >&2; exit 1
}
quote() {
  local rest="$1" prefix apostrophe="'"
  printf "'"
  while [[ "$rest" == *"$apostrophe"* ]]; do
    prefix="${rest%%"$apostrophe"*}"; printf "%s'\\\\''" "$prefix"
    rest="${rest#*"$apostrophe"}"
  done
  printf "%s'" "$rest"
}
has_control() {
  [[ "$1" == *$'\n'* || "$1" == *$'\r'* ]] && return 0
  printf '%s' "$1" | LC_ALL=C grep -q '[[:cntrl:]]'
}
normalize_absolute() {
  local value="$1" part result="" i
  local -a pieces stack
  [[ "$value" == /* ]] || value="$repo_root/$value"
  IFS='/' read -r -a pieces <<< "$value"
  for part in "${pieces[@]}"; do
    case "$part" in
      ""|.) ;;
      ..)
        if ((${#stack[@]} > 0)); then
          unset 'stack[${#stack[@]}-1]'
        fi
        ;;
      *) stack[${#stack[@]}]="$part" ;;
    esac
  done
  for ((i=0; i<${#stack[@]}; i++)); do
    result="$result/${stack[$i]}"
  done
  printf '%s\n' "${result:-/}"
}
canonicalize_absolute() {
  local path="$1" probe suffix="" base physical
  probe="$(normalize_absolute "$path")"
  while [[ ! -e "$probe" && ! -L "$probe" ]]; do
    base="${probe##*/}"; suffix="/$base$suffix"; probe="${probe%/*}"
    [[ -n "$probe" ]] || probe="/"
  done
  [[ -d "$probe" ]] || die_path "archive root ancestor is not a directory: " "$probe"
  physical="$(cd "$probe" && pwd -P)"
  physical="${physical%/}"; [[ -n "$physical$suffix" ]] || physical="/"
  printf '%s%s\n' "$physical" "$suffix"
}
contains_path() {
  local wanted="$1" item
  shift
  for item in "$@"; do
    [[ "$item" == "$wanted" ]] && return 0
  done
  return 1
}
print_paths() {
  local path
  for path in "$@"; do
    printf '  - '; quote "$path"; printf '\n'
  done
}
print_path_summary() {
  local shown=0 total=$# path
  for path in "$@"; do
    ((shown >= 20)) && break
    printf '  - '; quote "$path"; printf '\n'
    ((shown += 1))
  done
  ((total <= shown)) || printf '  ... and %s more\n' "$((total - shown))"
}
main_ref="main"; archive_root_arg=""; archive_name=""
assume_yes=0; dry_run=0
while (($#)); do
  case "$1" in
    --main-ref|--archive-root|--archive-name)
      (($# >= 2)) || die "$1 requires a value"
      case "$1" in
        --main-ref) main_ref="$2" ;;
        --archive-root) archive_root_arg="$2" ;;
        --archive-name) archive_name="$2" ;;
      esac
      shift 2
      ;;
    --yes) assume_yes=1; shift ;;
    --dry-run) dry_run=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done
repo_root="$(pwd -P)"
git_top="$(git rev-parse --show-toplevel 2>/dev/null)" ||
  die "current directory is not a Git worktree"
git_top="$(cd "$git_top" && pwd -P)"
[[ "$git_top" == "$repo_root" ]] ||
  die "run this command from the repository root"
has_control "$main_ref" && die "--main-ref contains unsupported control characters"
main_commit="$(git rev-parse --verify "$main_ref^{commit}" 2>/dev/null)" ||
  die "cannot resolve main ref: $main_ref"
source_branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
source_commit="$(git rev-parse --verify HEAD 2>/dev/null)" ||
  die "HEAD has no commit"
source_label="${source_branch:-detached}"
if [[ -z "$archive_root_arg" ]]; then
  archive_root_arg="$repo_root/../_archive"
fi
has_control "$archive_root_arg" && die "--archive-root contains unsupported control characters"
archive_root="$(canonicalize_absolute "$archive_root_arg")"
case "$archive_root" in
  "$repo_root"|"$repo_root"/*) die "archive root must be outside the source repository" ;;
esac
if [[ -z "$archive_name" ]]; then
  safe_label="${source_label//\//-}"
  archive_name="$safe_label-$(date -u '+%Y%m%dT%H%M%SZ')"
fi
[[ -n "$archive_name" && "$archive_name" != "." && "$archive_name" != ".." &&
   "$archive_name" != */* ]] ||
  die "archive name must be one path component"
has_control "$archive_name" && die "--archive-name contains unsupported control characters"
archive_prefix="${archive_root%/}"; final_archive="$archive_prefix/$archive_name"
staging_archive="$archive_prefix/.$archive_name.staging"
[[ ! -e "$final_archive" && ! -L "$final_archive" ]] ||
  die_path "archive destination already exists: " "$final_archive"
[[ ! -e "$staging_archive" && ! -L "$staging_archive" ]] ||
  die_path "archive staging path already exists: " "$staging_archive"
scan_dir="$(mktemp -d "${TMPDIR:-/tmp}/archive-project.XXXXXX")" ||
  die "cannot create temporary Git scan directory"
diff_scan="$scan_dir/diff"; untracked_scan="$scan_dir/untracked"
ignored_scan="$scan_dir/ignored"; status_scan="$scan_dir/status"
cleanup_scans() {
  local file
  for file in "$diff_scan" "$untracked_scan" "$ignored_scan" "$status_scan"; do
    [[ ! -e "$file" ]] || unlink "$file" 2>/dev/null || true
  done
  rmdir "$scan_dir" 2>/dev/null || true
}
trap cleanup_scans EXIT
git diff --name-status -z --find-renames --find-copies "$main_commit" -- \
  > "$diff_scan" || die "git diff discovery failed; no action taken"
git ls-files -z --others --exclude-standard > "$untracked_scan" ||
  die "git ls-files untracked discovery failed; no action taken"
git ls-files -z --others --ignored --exclude-standard > "$ignored_scan" ||
  die "git ls-files ignored discovery failed; no action taken"
declare -a candidates shared ignored
candidates=(); shared=(); ignored=(); unsupported=0
add_candidate() {
  local path="$1" target absolute="$repo_root/$1"
  if has_control "$path"; then
    printf 'Unsupported control character in candidate path: '
    quote "$path"
    printf '\n'
    unsupported=1
    return
  fi
  if [[ -L "$absolute" ]]; then
    target="$(readlink "$absolute")"
    if has_control "$target"; then
      printf 'Unsupported control character in symlink target for '
      quote "$path"
      printf ': '
      quote "$target"
      printf '\n'
      unsupported=1
      return
    fi
  fi
  if [[ -f "$absolute" || -L "$absolute" ]]; then
    contains_path "$path" "${candidates[@]+"${candidates[@]}"}" ||
      candidates[${#candidates[@]}]="$path"
  fi
}
classify_path() {
  local path="$1"
  if has_control "$path"; then
    printf 'Unsupported control character in changed path: '
    quote "$path"
    printf '\n'
    unsupported=1
  elif git cat-file -e "$main_commit:$path" 2>/dev/null; then
    contains_path "$path" "${shared[@]+"${shared[@]}"}" ||
      shared[${#shared[@]}]="$path"
  else
    add_candidate "$path"
  fi
}
while IFS= read -r -d '' status; do
  case "$status" in
    R*|C*)
      IFS= read -r -d '' source_path ||
        die "malformed Git rename/copy source record"
      IFS= read -r -d '' destination_path ||
        die "malformed Git rename/copy destination record"
      classify_path "$source_path"
      classify_path "$destination_path"
      ;;
    *)
      IFS= read -r -d '' path || die "malformed Git name-status record"
      classify_path "$path"
      ;;
  esac
done < "$diff_scan"
while IFS= read -r -d '' path; do
  if has_control "$path"; then
    printf 'Unsupported control character in untracked path: '
    quote "$path"
    printf '\n'
    unsupported=1
  else
    add_candidate "$path"
  fi
done < "$untracked_scan"
while IFS= read -r -d '' path; do
  if has_control "$path"; then
    printf 'Unsupported control character in ignored path: '
    quote "$path"
    printf '\n'
    unsupported=1
  else
    ignored[${#ignored[@]}]="$path"
  fi
done < "$ignored_scan"
if ((unsupported)); then
  printf 'No action taken. Consult an agent before handling unsupported control/newline paths.\n'
  exit 1
fi
if ((${#shared[@]})); then
  printf 'Shared modifications relative to frozen main:\n'
  print_paths "${shared[@]}"
  printf 'No action taken. Consult an agent to separate these shared changes safely.\n'
  exit 1
fi
if ((${#ignored[@]})); then
  printf 'Ignored files require a decision:\n'
  print_path_summary "${ignored[@]}"
  printf 'No action taken. Consult an agent whether to delete, archive, or keep them.\n'
  exit 1
fi
printf 'Frozen main commit: %s\n' "$main_commit"
printf 'Archive destination: '; quote "$final_archive"; printf '\n'
printf 'Candidate count: %s\n' "${#candidates[@]}"
if ((dry_run)); then
  printf 'Dry run: no files were moved and Git was not changed.\n'
  exit 0
fi
if ((!assume_yes)); then
  printf 'Archive these files and reset this worktree to main? [y/N] '
  IFS= read -r answer || answer=""
  case "$answer" in
    y|Y|yes|YES|Yes) ;;
    *) printf 'No action taken.\n'; exit 0 ;;
  esac
fi
archive_root_existed=0
[[ -d "$archive_root" ]] && archive_root_existed=1
mkdir -p "$archive_root" || die_path "cannot create archive root: " "$archive_root"
[[ -d "$archive_root" && ! -L "$archive_root" ]] ||
  die_path "archive root is not a real directory: " "$archive_root"
payload_root="$staging_archive/files"
mkdir -p "$payload_root" || {
  find "$staging_archive" -depth -type d -exec rmdir {} \; 2>/dev/null || true
  ((!archive_root_existed)) && rmdir "$archive_root" 2>/dev/null || true
  die_path "cannot create archive staging path: " "$staging_archive"
}
declare -a moved
moved=()
remove_empty_source_parents() {
  local parent="${1%/*}"
  while [[ "$parent" != "$repo_root" && "$parent" != "/" ]]; do
    rmdir "$parent" 2>/dev/null || break
    parent="${parent%/*}"
  done
}
rollback_moves() {
  local i path source source_parent archived failed=0
  [[ ! -e "$manifest" ]] || unlink "$manifest" 2>/dev/null || failed=1
  for ((i=${#moved[@]}-1; i>=0; i--)); do
    path="${moved[$i]}"
    source="$repo_root/$path"; source_parent="${source%/*}"
    archived="$payload_root/$path"
    mkdir -p "$source_parent" && mv "$archived" "$source" || failed=1
  done
  moved=()
  find "$staging_archive" -depth -type d -exec rmdir {} \; 2>/dev/null || true
  if ((!archive_root_existed)); then
    rmdir "$archive_root" 2>/dev/null || true
  fi
  return "$failed"
}
manifest="$staging_archive/MANIFEST.txt"
for path in "${candidates[@]+"${candidates[@]}"}"; do
  source="$repo_root/$path"; archived="$payload_root/$path"
  archived_parent="${archived%/*}"; move_failed=0
  mkdir -p "$archived_parent" || move_failed=1
  if ((move_failed == 0)) && ! mv "$source" "$archived"; then
    [[ -e "$source" || -L "$source" || (! -e "$archived" && ! -L "$archived") ]] ||
      moved[${#moved[@]}]="$path"
    move_failed=1
  elif ((move_failed == 0)); then
    moved[${#moved[@]}]="$path"
    remove_empty_source_parents "$source"
  fi
  if ((move_failed)); then
    if rollback_moves; then
      printf 'Move failed for ' >&2; quote "$path" >&2
      printf '; moved files were rolled back from ' >&2; quote "$staging_archive" >&2
      printf '.\n' >&2
    else
      printf 'Move failed for ' >&2; quote "$path" >&2
      printf '; rollback was incomplete at ' >&2; quote "$staging_archive" >&2
      printf '.\n' >&2
    fi
    exit 1
  fi
done
write_manifest() {
  local path archived target hash_line
  {
    printf 'timestamp: %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    printf 'source_branch: %s\n' "$source_label"
    printf 'source_commit: %s\n' "$source_commit"
    printf 'main_ref: '; quote "$main_ref"
    printf '\nmain_commit: %s\n' "$main_commit"
    printf 'moved_count: %s\n' "${#moved[@]}"
    for path in "${moved[@]+"${moved[@]}"}"; do
      archived="$payload_root/$path"
      printf '\npath: '; quote "$path"; printf '\n'
      if [[ -L "$archived" ]]; then
        target="$(readlink "$archived")" || return 1
        printf 'symlink_target: '; quote "$target"; printf '\n'
      else
        hash_line="$(shasum -a 256 "$archived")" || return 1
        printf 'sha256: %s\n' "${hash_line%% *}"
      fi
    done
  } > "$manifest"
}
if ! write_manifest; then
  if rollback_moves; then
    die_path "manifest write failed; moved files were rolled back from " "$staging_archive"
  fi
  die_path "manifest write failed; rollback was incomplete at " "$staging_archive"
fi
if ! git switch --detach --discard-changes "$main_commit"; then
  if [[ "$(git rev-parse --verify HEAD 2>/dev/null || true)" == "$source_commit" ]]; then
    if rollback_moves; then
      printf 'Git switch failed; moved files were rolled back.\n' >&2
    else
      printf 'Git switch failed and rollback was incomplete. Staging: ' >&2
      quote "$staging_archive" >&2
      printf '\n' >&2
    fi
  else
    printf 'Git switch failed after HEAD changed. Staging retained at: ' >&2
    quote "$staging_archive" >&2
    printf '\n' >&2
  fi
  exit 1
fi
[[ "$(git rev-parse --verify HEAD)" == "$main_commit" ]] ||
  die "reset verification failed: HEAD is not frozen main"
git status --porcelain=v1 --untracked-files=all > "$status_scan" ||
  die "reset verification failed: git status failed"
[[ ! -s "$status_scan" ]] ||
  die_path "reset verification failed; worktree is not clean; staging retained at " \
    "$staging_archive"
git ls-files -z --others --ignored --exclude-standard > "$ignored_scan" ||
  die "reset verification failed: ignored-file discovery failed"
[[ ! -s "$ignored_scan" ]] ||
  die_path "reset verification failed; ignored files remain; staging retained at " \
    "$staging_archive"
if ! mv "$staging_archive" "$final_archive"; then
  printf 'Could not publish final archive. Staging retained at: ' >&2
  quote "$staging_archive" >&2
  printf '\n' >&2
  exit 1
fi
printf 'Archive complete: '; quote "$final_archive"; printf '\n'
printf 'Old branch/commit: %s %s\n' "$source_label" "$source_commit"
printf 'Worktree detached at main: %s\n' "$main_commit"
printf 'Ask an agent to create the next project branch before starting new work.\n'
