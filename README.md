<p align="right">
  简体中文 | <a href="./README.en.md">English</a>
</p>

# auto-motion

`auto-motion` 提供两条竖屏 MG 视频制作流程：已有定稿字幕时，可以直接把 SRT 拆成多个动画镜头；只有文章或口播稿时，也可以完成稿件整理、TTS、真实字幕时间轴、首帧封面、BGM、音效、混音和最终成片。

## 选择工作流

| 入口 | 适用情况 | 交付结果 |
| --- | --- | --- |
| [`PROMPT.md`](./PROMPT.md) | 已有定稿 `transcription.srt`，只需要制作静音 MG 动画 | 分镜 MP4、Claude 日志、静音 `final.mp4` |
| [`PROMPT-PRODUCTION.md`](./PROMPT-PRODUCTION.md) | 从文章、口播稿或参考 SRT 开始，需要配音和完整声音制作 | 终稿、TTS、真实 SRT、分镜、封面、BGM/SFX、混音成片和验收证据 |

两个入口共享同一个单镜头 Claude Code 执行模板。`PROMPT-PRODUCTION.md` 在基础流程外增加了稿件、配音、节奏、封面和声音制作关卡，不会改变 `PROMPT.md` 的轻量行为。

每篇内容都是一次独立制作。开始新项目时，请使用新的干净目录，或基于 `main` 创建专用 Git worktree；不要把上一条视频的 `scenes/`、音频、素材、日志、审批文件或 `final.mp4` 带入新项目。

## 效果演示

演示截取自成片的 `00:00:03,000 → 00:00:13,000`。左侧是输入给 auto-motion 的 [SRT 字幕片段](./readme-assets/auto-motion-demo.srt)，右侧是自动生成并加回字幕的动画。

<table>
  <thead>
    <tr>
      <th width="50%">输入：SRT</th>
      <th width="50%">输出：生成的动画</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td valign="top"><pre><code>1
00:00:00,000 --> 00:00:02,033
由GPT5.6sol和qwen 3.8 Max Preview做的

2
00:00:02,100 --> 00:00:03,466
GPT负责对文案脚本

3
00:00:03,466 --> 00:00:05,566
进行切割、查资料、找素材

4
00:00:05,666 --> 00:00:07,600
qwen 3.8则负责写react代码

5
00:00:07,600 --> 00:00:09,133
再用remotion将创意渲染

6
00:00:09,133 --> 00:00:10,000
为motion graphics动画</code></pre></td>
      <td valign="top"><img src="./readme-assets/auto-motion-demo.gif" alt="auto-motion 根据左侧 SRT 生成的 MG 动画" width="420" /></td>
    </tr>
  </tbody>
</table>

## 运行证据

下面是一段真实运行过程截图：多镜头任务已经连续运行 1 小时 36 分钟，Codex 正在等待 Claude Code 完成后续镜头的代码实现和渲染。

<img src="./readme-assets/evidence.png" alt="auto-motion long-running Codex and Claude Code workflow evidence" width="720" />

## 架构

### 1. 配置层：auto-motion.conf

`auto-motion.conf` 定义编排工具和渲染工具的组合。编排层和渲染层都可以从 Codex、Claude Code、Qoder 中三选一，但同一个工具不能同时担任两个角色。

```bash
# 编排工具：codex | claude | qoder
ORCHESTRATOR=codex
# 渲染工具：codex | claude | qoder（必须与 ORCHESTRATOR 不同）
RENDERER=claude
```

也可以通过环境变量或 `.env` 文件覆盖：`ORCHESTRATOR=qoder RENDERER=claude bash run-orchestrator.sh`。

### 2. 调度层：编排工具 + PROMPT.md

`PROMPT.md` 定义整个自动化流程：

- 读取当前目录的 `transcription.srt`。
- 按语义把字幕拆成连续、完整覆盖总时长的镜头。
- 为每个镜头创建 `scenes/scene-001`、`scenes/scene-002` 等独立目录。
- 从 `exampleFolder` 复制运行模板和 HyperFrames 相关技能。
- 顺序调用渲染工具生成每个镜头的动画 MP4。
- 检查镜头时长和产物规格，并用 FFmpeg 拼接为 `final.mp4`。

### 3. 执行层：渲染工具 + run-scene.sh

`exampleFolder/run-scene.sh` 是单镜头执行模板。编排工具会为每个镜头填写：

- `SCENE_ID`
- `SCENE_DURATION_SECONDS`
- `SCENE_TEXT`
- `OUTPUT_FILE`
- `FULL_TRANSCRIPT_PATH`

脚本根据 `RENDERER` 配置选择对应的 CLI 非交互式调用，并要求输出固定阶段消息。原始日志、错误日志和用户可读进度分别写入镜头目录中的：

- `render-<scene>.stream.jsonl`
- `render-<scene>.stderr.log`
- `render-<scene>.user.log`

### 4. 动画层：HyperFrames

`exampleFolder/.claude/skills/` 中包含 HyperFrames 相关技能。Claude Code 渲染时自动发现这些技能；Qoder 使用内置 HyperFrames 技能；Codex 渲染时由 `run-scene.sh` 在提示词中引用技能文件。渲染工具基于这些技能编写 HTML 动画项目，并渲染 1080x1440、30fps、静音、无音轨的 MP4。

### 5. 验收层：auto-test

`auto-test/run.sh` 提供端到端测试入口。它会创建临时工作区，复制测试字幕和模板，按配置启动编排工具执行完整流程，然后用 `auto-test/validate.sh` 检查：

- 渲染工具阶段消息是否完整。
- 单镜头 MP4 和 `final.mp4` 是否存在。
- 视频是否为 1080x1440。
- 帧率是否约为 30fps。
- 时长是否接近字幕总时长。
- 是否没有音轨。

## 前提条件

请先确保本机已安装并登录以下工具中的**至少两个**（编排层和渲染层各一个，不能相同）：

- [Codex CLI](https://developers.openai.com/codex/cli)
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code)
- [QoderCN CLI](https://help.aliyun.com/document_detail/3033350.html)
- Node.js 22 或更高版本
- FFmpeg 和 FFprobe
- `jq`
- 可联网环境，用于渲染工具搜索素材、安装依赖或下载品牌视觉资产

可以用下面的命令做基础检查：

```bash
codex --version
claude --version
qoderclicn --version
node --version
ffmpeg -version
ffprobe -version
jq --version
```

## 快速开始

### 1. 准备字幕文件

把 SRT 字幕文件放到仓库根目录，并命名为 `transcription.srt`：

```bash
cp /path/to/transcription.srt ./transcription.srt
```

### 2. 执行基础 SRT 流程

编辑 `auto-motion.conf` 选择编排工具和渲染工具，然后在仓库根目录运行：

```bash
bash run-orchestrator.sh
```

或者通过环境变量一次性指定：

```bash
ORCHESTRATOR=qoder RENDERER=claude bash run-orchestrator.sh
```

编排工具会读取 `PROMPT.md`，拆分字幕、创建镜头目录、逐个调用渲染工具，并最终生成：

```text
scenes/
  scene-001/
    scene-001.mp4
    render-scene-001.stream.jsonl
    render-scene-001.stderr.log
    render-scene-001.user.log
  scene-002/
    scene-002.mp4
final.mp4
```

### 3. 执行完整制作流程

准备文章、口播稿和参考 SRT，并在项目根目录的 `.env` 中配置 MiniMax TTS 凭据。然后运行：

```bash
bash run-orchestrator.sh PROMPT-PRODUCTION.md
```

完整流程包含四个人工审核点：口播稿与开场、TTS 音色与断句、首帧封面、耳机与手机外放试听。一次执行在审核点结束后，可以在同一 worktree 中继续；不要另建项目或复用其他作品的产物。

除 `final.mp4` 外，制作证据保存在 `production/`，最终配音字幕为 `transcription-production.srt`。

### 4. 查看结果

最终视频在仓库根目录：

```bash
open final.mp4
```

## 测试

运行内置端到端测试：

```bash
bash auto-test/run.sh
```

测试产物会写入 `auto-test/.tmp/`。该目录已被 `.gitignore` 忽略。

检查完整制作模板的静态合同：

```bash
bash auto-test/validate-production-template.sh
```

## 目录说明

```text
.
├── auto-motion.conf              # 编排/渲染工具配置
├── run-orchestrator.sh            # 便捷入口：按配置启动编排工具
├── lib/
│   └── auto-motion.sh             # 共享 shell 库（CLI 分发）
├── PROMPT.md                      # 已有 SRT 的基础静音流程
├── PROMPT-PRODUCTION.md           # 从稿件到带声音成片的完整流程
├── transcription.srt              # 输入字幕文件
├── exampleFolder/
│   ├── run-scene.sh               # 单镜头渲染模板（支持 claude/qoder/codex）
│   ├── run-claude-ai.sh           # 旧版 Claude Code 专用模板（保留兼容）
│   └── .claude/skills/            # HyperFrames 相关技能
├── auto-test/
│   ├── run.sh                     # 端到端测试入口
│   ├── validate.sh                # 视频产物校验脚本
│   ├── validate-production-template.sh # 完整模板合同检查
│   └── transcription.srt          # 测试字幕
├── production/                    # 单次完整制作的配置、音频和验收证据
└── final.mp4                      # 生成后的视频交付文件
```

## 注意事项

- 同一时间只运行一个渲染工具调用，不并行渲染多个镜头。
- 每个镜头必须完整覆盖字幕时间轴，镜头时长总和应等于字幕总时长。
- 若某个镜头失败，优先查看对应目录下的 `stderr.log`、`stream.jsonl` 和 `user.log`。
- 如果视频规格不一致，应先统一转码后再拼接。
- 完整制作流程中的机器声音检查不能代替发布前的耳机和手机外放试听。
