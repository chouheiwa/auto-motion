#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRODUCTION_PROMPT="$ROOT_DIR/PROMPT-PRODUCTION.md"

fail() {
  echo "production-template FAIL: $*" >&2
  exit 1
}

require_file() {
  local file="$1"
  [[ -s "$file" ]] || fail "missing or empty file: $file"
}

require_pattern() {
  local pattern="$1"
  local file="$2"
  local label="$3"
  grep -Eq "$pattern" "$file" || fail "$label"
}

require_file "$PRODUCTION_PROMPT"

required_contracts=(
  '一次性项目|单次项目'
  '干净目录|独立 worktree'
  '文章|口播稿'
  'MiniMax'
  '\.env'
  '实际语音|真实.*时间戳'
  '顺序.*Claude|Claude.*顺序'
  '\[\[USER_MESSAGE\]\]'
  'SCENE_DURATION_SECONDS'
  '第 0 帧|首帧'
  'BGM'
  'SFX|音效'
  '授权|许可证'
  'SHA-256'
  '侧链|自动压低'
  '原子.*final\.mp4|final\.mp4.*原子'
  '耳机'
  '手机外放'
  '不得.*复用|禁止.*复用'
  '密钥.*日志|日志.*密钥'
)

for pattern in "${required_contracts[@]}"; do
  require_pattern "$pattern" "$PRODUCTION_PROMPT" \
    "PROMPT-PRODUCTION.md missing contract: $pattern"
done

if grep -Eiq '你是[^。]*(Codex|agent)|主控[[:space:]]*agent|执行(者|这份说明)[^。]*(Codex|agent)' \
  "$PRODUCTION_PROMPT"; then
  fail "PROMPT-PRODUCTION.md exposes an executor identity"
fi

git -C "$ROOT_DIR" diff --quiet main -- \
  PROMPT.md \
  exampleFolder/run-claude-ai.sh \
  auto-test/run.sh \
  auto-test/validate.sh \
  || fail "the basic workflow contract changed"

for readme in "$ROOT_DIR/README.md" "$ROOT_DIR/README.en.md"; do
  require_pattern 'PROMPT\.md' "$readme" "$(basename "$readme") missing basic entry point"
  require_pattern 'PROMPT-PRODUCTION\.md' "$readme" \
    "$(basename "$readme") missing production entry point"
  require_pattern 'worktree|干净目录|clean directory' "$readme" \
    "$(basename "$readme") missing one-run isolation guidance"
done

echo "production-template PASS: full and basic workflow contracts are intact."
