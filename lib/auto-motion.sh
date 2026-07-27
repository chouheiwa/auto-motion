#!/usr/bin/env bash
# auto-motion 共享 shell 库
# 提供配置加载、工具检查、编排/渲染分发功能

set -euo pipefail

_AM_VALID_TOOLS="codex claude qoder"

am_load_config() {
  local root="${AM_ROOT:-.}"
  local env_file="${root}/.env"
  local conf="${AM_CONFIG:-${root}/auto-motion.conf}"

  if [[ -f "$env_file" ]]; then
    # shellcheck source=/dev/null
    source "$env_file"
  fi
  if [[ -f "$conf" ]]; then
    # shellcheck source=auto-motion.conf
    source "$conf"
  fi

  if [[ ! " $_AM_VALID_TOOLS " =~ $ORCHESTRATOR ]]; then
    echo "无效的 ORCHESTRATOR: $ORCHESTRATOR（可选：$_AM_VALID_TOOLS）" >&2
    exit 1
  fi
  if [[ ! " $_AM_VALID_TOOLS " =~ $RENDERER ]]; then
    echo "无效的 RENDERER: $RENDERER（可选：$_AM_VALID_TOOLS）" >&2
    exit 1
  fi
  if [[ "$ORCHESTRATOR" == "$RENDERER" ]]; then
    echo "ORCHESTRATOR 和 RENDERER 不能相同：$ORCHESTRATOR" >&2
    exit 1
  fi
}

am_tool_binary() {
  case "$1" in
    codex)  echo "codex" ;;
    claude) echo "claude" ;;
    qoder)  echo "qoderclicn" ;;
    *)      echo "unknown tool: $1" >&2; exit 1 ;;
  esac
}

am_require_tool() {
  local tool="$1"
  local bin
  bin="$(am_tool_binary "$tool")"
  if ! command -v "$bin" >/dev/null 2>&1; then
    echo "缺少必需工具：$bin（配置：$tool）" >&2
    exit 127
  fi
}

am_run_orchestrator() {
  local workdir="$1"
  local prompt_file="$2"

  am_require_tool "$ORCHESTRATOR"

  case "$ORCHESTRATOR" in
    codex)
      codex exec \
        --cd "$workdir" \
        --sandbox danger-full-access \
        --ask-for-approval never \
        - <"$prompt_file"
      ;;
    claude)
      claude -p "$(cat "$prompt_file")" \
        --dangerously-skip-permissions
      ;;
    qoder)
      qoderclicn -p "$(cat "$prompt_file")" \
        --dangerously-skip-permissions \
        --output-format stream-json
      ;;
  esac
}

am_render_jq_filter() {
  cat <<'JQ_EOF'
fromjson?
| select(.type=="assistant")
| .message.content[]?
| select(.type=="text")
| .text
| split("\n")[]
| select(startswith("[[USER_MESSAGE]]"))
| sub("^\\[\\[USER_MESSAGE\\]\\]"; "")
JQ_EOF
}

am_run_renderer() {
  local prompt="$1"
  local raw_log="$2"
  local stderr_log="$3"

  am_require_tool "$RENDERER"

  case "$RENDERER" in
    claude)
      claude -p \
        --dangerously-skip-permissions \
        --verbose \
        --output-format stream-json \
        --prompt-suggestions false \
        "$prompt" \
        2>"$stderr_log" \
      | tee "$raw_log" \
      | jq -Rr --unbuffered "$(am_render_jq_filter)"
      ;;
    qoder)
      qoderclicn -p "$prompt" \
        --dangerously-skip-permissions \
        --output-format stream-json \
        2>"$stderr_log" \
      | tee "$raw_log" \
      | jq -Rr --unbuffered "$(am_render_jq_filter)"
      ;;
    codex)
      codex exec \
        --sandbox danger-full-access \
        --ask-for-approval never \
        --json \
        "$prompt" \
        2>"$stderr_log" \
      | tee "$raw_log" \
      | jq -Rr --unbuffered "$(am_render_jq_filter)"
      ;;
  esac
}
