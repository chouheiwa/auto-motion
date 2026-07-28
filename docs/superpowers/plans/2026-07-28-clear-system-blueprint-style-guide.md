# “清晰系统蓝图”视频风格说明书 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成一份人类可读说明书、一份机器可读 `frame.md`、自动一致性校验和四类 1080×1440 示例帧。

**Architecture:** `frame.md` 与人类说明书使用同一份 YAML frontmatter schema，作为可自动比对的规范层；正文分别服务渲染工具和人类读者。Python 校验器解析两份 frontmatter、验证 schema/token，并检查四类示例帧存在且尺寸正确。

**Tech Stack:** Markdown、YAML、Python 3 + PyYAML、SVG、ImageMagick、Node test runner（现有回归测试）。

---

### Task 1: 建立失败的风格规范校验测试

**Files:**
- Create: `production/tests/test_style_guide.py`
- Create: `production/tools/validate_style_guide.py`

- [ ] **Step 1: 写失败测试**

测试必须覆盖：

- `frame.md` 和 `docs/清晰系统蓝图-视频风格说明书.md` 存在。
- 两份 frontmatter 都能解析。
- 必填键、类型、枚举、HEX 和单位合法。
- 两份规范 token 完全一致。
- motion 三阶段比例合计为 1。
- 四类 1080×1440 示例 PNG 存在。

- [ ] **Step 2: 运行测试并确认失败**

Run:

```bash
python3 -m unittest production/tests/test_style_guide.py -v
```

Expected: FAIL，提示目标文档或校验模块尚不存在。

- [ ] **Step 3: 编写最小校验器接口**

在 `production/tools/validate_style_guide.py` 提供：

```python
def parse_frontmatter(path): ...
def validate_schema(tokens): ...
def compare_tokens(frame_tokens, guide_tokens): ...
def validate_examples(tokens, project_root): ...
def validate_all(project_root): ...
```

CLI 成功时输出 `style guide validation passed`，失败时以非零状态退出。

### Task 2: 生成人类说明书与 `frame.md`

**Files:**
- Create: `docs/清晰系统蓝图-视频风格说明书.md`
- Create: `frame.md`

- [ ] **Step 1: 写入相同 YAML frontmatter**

frontmatter 必须完整实现设计规格中的 schema，并包含：

- 1080×1440、30fps。
- 五类安全区。
- 核心色、字体、空间和圆角 token。
- 四类镜头骨架。
- Build/Breathe/Resolve 动态 token。
- 声音、字幕、封面和 forbidden token。

- [ ] **Step 2: 编写人类说明书正文**

正文按设计规格 15 个章节展开，必须包含：

- 品牌人格、构图、色彩、字体、组件和动画语法。
- 四类镜头骨架及选择规则。
- 不可变项与可变项。
- Do / Don’t。
- 制作和发布检查表。
- 可复制镜头提示词模板。
- 当前成片联系表与封面检查图的证据链接。

- [ ] **Step 3: 编写 `frame.md` 正文**

正文必须短于人类说明书，强调：

- frontmatter 是规范性品牌层。
- 品牌规范不是固定布局。
- 渲染工具负责根据语义选择镜头骨架、图形隐喻和局部构图。
- 不得改写核心 token。

### Task 3: 生成四类示例帧

**Files:**
- Create: `production/tools/generate_style_examples.py`
- Generate: `production/style-guide/examples/proposition.svg`
- Generate: `production/style-guide/examples/comparison.svg`
- Generate: `production/style-guide/examples/process.svg`
- Generate: `production/style-guide/examples/capability_deck.svg`
- Generate: corresponding `.png` files at 1080×1440.

- [ ] **Step 1: 编写确定性 SVG 生成器**

生成器从 `frame.md` frontmatter 读取颜色、安全区、字体、间距和圆角，不内置第二套 token。

- [ ] **Step 2: 生成 SVG 和 PNG**

Run:

```bash
python3 production/tools/generate_style_examples.py
```

Expected: 输出 4 个 SVG，并调用 ImageMagick 生成 4 个 1080×1440 PNG。

- [ ] **Step 3: 人工查看联系表**

生成 `production/style-guide/examples/contact-sheet.png`，检查四类骨架、标题、字幕和安全区均清晰，无裁切与贴边。

### Task 4: 完成校验、回归测试和提交

**Files:**
- Modify as needed: `frame.md`
- Modify as needed: `docs/清晰系统蓝图-视频风格说明书.md`
- Modify as needed: `production/tools/validate_style_guide.py`

- [ ] **Step 1: 运行风格规范校验**

```bash
python3 production/tools/validate_style_guide.py
```

Expected: `style guide validation passed`

- [ ] **Step 2: 运行专项测试**

```bash
python3 -m unittest production/tests/test_style_guide.py -v
```

Expected: PASS。

- [ ] **Step 3: 运行项目回归测试**

```bash
node --test production/tests/*.test.mjs
```

Expected: 35 tests pass。

- [ ] **Step 4: 校验 Markdown、YAML 和示例尺寸**

```bash
python3 - <<'PY'
from pathlib import Path
from production.tools.validate_style_guide import validate_all
validate_all(Path.cwd())
PY
identify production/style-guide/examples/*.png
```

Expected: 4 个示例均为 1080×1440。

- [ ] **Step 5: 提交**

```bash
git add frame.md docs/清晰系统蓝图-视频风格说明书.md \
  production/tools/validate_style_guide.py \
  production/tools/generate_style_examples.py \
  production/tests/test_style_guide.py \
  production/style-guide/examples
git commit -m "docs: add clear system blueprint video style guide"
```
