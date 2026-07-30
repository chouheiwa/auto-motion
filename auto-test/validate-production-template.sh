#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRODUCTION_PROMPT="$ROOT_DIR/PROMPT-PRODUCTION.md"
BASIC_PROMPT="$ROOT_DIR/PROMPT.md"
PUBLISH_TEMPLATE="$ROOT_DIR/templates/publish.md"
PUBLISH_VALIDATOR="$ROOT_DIR/production/tools/validate_publish.py"

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
require_file "$BASIC_PROMPT"
require_file "$PUBLISH_TEMPLATE"
require_file "$PUBLISH_VALIDATOR"

python3 "$PUBLISH_VALIDATOR" "$PUBLISH_TEMPLATE" --template ||
  fail "publish template validation failed"

required_contracts=(
  '一次性项目|单次项目'
  '干净目录|独立 worktree'
  '文章|口播稿'
  'MiniMax'
  'mmx auth|~/\.mmx'
  '实际语音|真实.*时间戳'
  '顺序.*渲染|渲染.*顺序'
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
  '内容边界|内容范围'
  '语速.*试听.*确认|试听.*确认.*语速'
  '配音.*变更.*失效|变更配音.*重新生成'
  'phrase-timeline\.json'
  'visible_event|visible-event|可见事件'
  '强制对齐|词级对齐'
  '未来信息|不得早于.*短语'
  '复合标题'
  '最短可读|最小可读'
  '一拍一个焦点|一个主视觉'
  'setpts'
  '源级.*重渲染|源工程.*重渲染'
  '结尾留白|尾留白'
  '最后.*有效语音.*节目终点|节目终点.*最后.*有效语音'
  '候选.*SHA-256|SHA-256.*候选'
  '不得硬编码.*revision|不得.*版本.*常量'
)

for pattern in "${required_contracts[@]}"; do
  require_pattern "$pattern" "$PRODUCTION_PROMPT" \
    "PROMPT-PRODUCTION.md missing contract: $pattern"
done

publish_contracts=(
  'publish\.md'
  'templates/publish\.md'
  'SHA-256'
  '同一文件系统'
  'yaml\.safe_dump'
  '临时文件'
  '验证通过.*原子重命名|原子重命名.*验证通过'
  'production/tools/validate_publish\.py'
  '汇报.*失败|失败.*汇报'
)

for prompt in "$BASIC_PROMPT" "$PRODUCTION_PROMPT"; do
  for pattern in "${publish_contracts[@]}"; do
    require_pattern "$pattern" "$prompt" \
      "$(basename "$prompt") missing publish contract: $pattern"
  done
done

production_publish_contracts=(
  'expected_delivery\.sha256'
  '素材账本.*授权证据|授权证据.*素材账本'
  '耳机'
  '手机外放'
  '封面预览'
  '版权确认'
  'draft'
  'pending_manual_checks'
  'blocked'
  'ready'
)

for pattern in "${production_publish_contracts[@]}"; do
  require_pattern "$pattern" "$PRODUCTION_PROMPT" \
    "PROMPT-PRODUCTION.md missing publish contract: $pattern"
done

basic_publish_contracts=(
  'workflow: basic_srt'
  'unspecified'
  'generated_candidate'
  'no_audio_track'
  '证据.*空值|不存在.*证据'
)

for pattern in "${basic_publish_contracts[@]}"; do
  require_pattern "$pattern" "$BASIC_PROMPT" \
    "PROMPT.md missing publish contract: $pattern"
done

if grep -Eiq '你是[^。]*(Codex|agent)|主控[[:space:]]*agent|执行(者|这份说明)[^。]*(Codex|agent)' \
  "$PRODUCTION_PROMPT"; then
  fail "PROMPT-PRODUCTION.md exposes an executor identity"
fi

require_file "$ROOT_DIR/exampleFolder/run-scene.sh"
require_pattern 'RENDERER' "$ROOT_DIR/exampleFolder/run-scene.sh" \
  "run-scene.sh missing RENDERER dispatch"
require_pattern 'render-' "$ROOT_DIR/auto-test/validate.sh" \
  "validate.sh missing render- log prefix"
require_pattern '渲染工具' "$ROOT_DIR/PROMPT.md" \
  "PROMPT.md missing tool-agnostic 渲染工具 reference"

for readme in "$ROOT_DIR/README.md" "$ROOT_DIR/README.en.md"; do
  require_pattern 'PROMPT\.md' "$readme" "$(basename "$readme") missing basic entry point"
  require_pattern 'PROMPT-PRODUCTION\.md' "$readme" \
    "$(basename "$readme") missing production entry point"
  require_pattern 'worktree|干净目录|clean directory' "$readme" \
    "$(basename "$readme") missing one-run isolation guidance"
  require_pattern 'publish\.md' "$readme" "$(basename "$readme") missing publish.md"
  require_pattern 'templates/publish\.md' "$readme" \
    "$(basename "$readme") missing publish template"
  require_pattern 'publish_status' "$readme" \
    "$(basename "$readme") missing publish status"
  require_pattern 'validate_publish\.py' "$readme" \
    "$(basename "$readme") missing publish validator command"
  require_pattern 'ready.*(不|does not|not mean).*(发布|published)' "$readme" \
    "$(basename "$readme") missing ready-state caveat"
done

echo "production-template PASS: full and basic workflow contracts are intact."
