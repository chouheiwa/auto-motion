#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

forbidden_patterns=(
  '^final\.mp4$'
  '^transcription-production\.srt$'
  '^scenes/'
  '^production/approval[^/]*\.json$'
  '^production/audio/'
  '^production/baseline\.json$'
  '^production/douyin-publish-copy\.md$'
  '^production/failures\.md$'
  '^production/input-inventory\.md$'
  '^production/input-manifest\.json$'
  '^production/production-config\.json$'
  '^production/scene-plan\.(json|md)$'
  '^production/scene-qc\.json$'
  '^production/script-change-log\.md$'
  '^production/script-final\.md$'
  '^production/silent-master[^/]*\.mp4$'
  '^production/timing-report\.json$'
  '^production/tts/'
  '^production/versions/'
  '^production/visual-qc/'
  '^production/tests/test_publish_copy\.py$'
  '^docs/superpowers/(plans|specs)/[^/]*douyin-publish-copy[^/]*\.md$'
)

tracked_files="$(git ls-files)"
violations=()

for pattern in "${forbidden_patterns[@]}"; do
  while IFS= read -r path; do
    [[ -n "$path" ]] && violations+=("$path")
  done < <(printf '%s\n' "$tracked_files" | grep -E "$pattern" || true)
done

if (( ${#violations[@]} > 0 )); then
  printf '%s\n' "main-boundary FAIL: project-specific files are tracked:" >&2
  printf '  %s\n' "${violations[@]}" | sort -u >&2
  exit 1
fi

echo "main-boundary PASS: tracked files are reusable repository assets."
