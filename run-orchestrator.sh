#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AM_ROOT="$ROOT_DIR"

source "$ROOT_DIR/lib/auto-motion.sh"
am_load_config

PROMPT_FILE="${1:-$ROOT_DIR/PROMPT.md}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "找不到 prompt 文件: $PROMPT_FILE" >&2
  exit 1
fi

echo "编排工具: $ORCHESTRATOR"
echo "渲染工具: $RENDERER"
echo "Prompt: $PROMPT_FILE"
echo "---"

am_run_orchestrator "$ROOT_DIR" "$PROMPT_FILE"
