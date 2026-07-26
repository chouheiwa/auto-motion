# 视频开场镜头设计

## 目标

在现有正文前增加一段 12–15 秒的独立开场，让观众在进入技术细节前明确：

1. 视频讨论的是 AI 编程工具的视觉验证能力。
2. 内容会覆盖多模态模型的原理、准确率和工程接入。
3. 最终问题是怎样让 Vibe Coding 工具获得可用的“眼睛”。

现有 13 个正文镜头的文案、视觉设计、配音和内部节奏保持不变。

## 最终开场词

> AI 已经会写代码了，但它能不能看懂自己写出来的界面？这期视频，我们从原理、精度和工程接入三个层面，看看多模态模型怎样给 Vibe Coding 装上眼睛。

MiniMax TTS 朗读时应将第一句作为问题完整读完，不在“看懂自己写出来的界面”中间断句。第二句在“这期视频”后自然短停顿，“原理、精度和工程接入”作为并列结构连贯朗读。

## 镜头结构

- 新镜头编号：`scene-000`
- 位置：现有 `scene-001` 之前
- 目标时长：以真实 TTS 解码时长为基础，量化到 30fps 整帧后控制在 12–15 秒
- 输出：1080×1440、30fps、H.264、yuv420p、BT.709、静音镜头 MP4
- 配音：MiniMax `Chinese (Mandarin)_Sincere_Adult`，固定 `speech-2.8-hd`、speed `0.98`、vol `1`、pitch `0`、emotion `calm`，不做变速或变调

开场是独立的主题引导镜头。Claude 负责该镜头的视觉概念、MG 动效、代码实现和 MP4 渲染；调度脚本只提供开场文案、真实配音节拍、技术规格以及与正文衔接的约束，不预先设计镜头内部动效。

## 开场时长门禁

MiniMax 返回的音频先解码为 48kHz PCM，并读取每声道实际采样数 `speechSamples`。开场帧数使用：

```text
baseFrames = max(360, ceil((speechSamples + 24000) / 1600))
openingFrames = 3 × ceil(baseFrames / 3)
openingDuration = openingFrames / 30
openingDurationMs = openingFrames × 1000 / 30
breathingSamples = openingFrames × 1600 - speechSamples
breathingDuration = breathingSamples / 48000
```

`openingFrames` 强制为 3 的倍数，因此 `openingDurationMs` 必为整数；视频、48kHz PCM 和 SRT 可以使用完全相同的精确边界。

只有同时满足以下条件才可调用 Claude：

- `360 ≤ openingFrames ≤ 450`
- `0.5 ≤ breathingDuration ≤ 0.8`
- 问题句没有被 MiniMax 错误拆开

开场 PCM 补零到精确 `openingFrames × 1600` 个采样/声道。开场视频时长和正文音频起点使用 `openingDuration`，正文字幕使用与其完全等价的整数 `openingDurationMs`；不得使用未量化的原始毫秒时长。

如果固定文案生成后短于 12 秒或长于 15 秒，或者呼吸区间不合格，不对音频变速，也不静默改写已批准文案；停止在 TTS 阶段并请求确认新的短版或长版文案。

TTS 使用独立的 opening 配置和生成入口，不修改现有 V3 配置及其测试。请求文本只允许在句界或“这期视频”之后添加 MiniMax 支持的停顿控制，禁止在问题句内部插入停顿；生成字幕时必须剥离控制标记。保留以下审计产物：

- 请求配置和原始响应
- MiniMax subtitle JSON
- 原始音频与 48kHz PCM
- `speechSamples`、`openingFrames`、`openingDurationMs` 和呼吸长度报告

## 与正文的衔接

开场最后一句落在“给 Vibe Coding 装上眼睛”。随后进入原 `scene-001`：

> Claude Code 看不见它自己写出来的界面长什么样。

两段构成“提出主题—落到具体工具和痛点”的关系。开场末尾保留短暂视觉呼吸，不增加冗长静止尾帧；正文第一镜头不删句、不重录、不重新设计。

## 时间轴与字幕

1. 根据 MiniMax 返回的句子级字幕时间生成开场 SRT 条目，并重新连续编号。
2. 以整数 `openingDurationMs` 为唯一偏移量，将 `scenes-v3/transcription-retimed.srt` 的 37 条正文字幕逐条整体后移，毫秒精度保持不变。
3. 不填补正文原有的句间空白，不强行延长最后一条字幕。
4. 新字幕条目总数为“开场条目数 + 37”。
5. 正文最后一条结束于 `openingDurationMs + 152165ms`；最终视频结束于 `openingDuration + 152.733333` 秒，保留约 0.568 秒的正文收尾。
6. 验证所有字幕无负时间、无越界、无意外重叠，并逐条确认每条正文字幕与 V3 原字幕的起止时间差都精确等于 `openingDurationMs`。
7. 原 `transcription-retimed.srt` 保留，新文件单独交付，避免破坏已有版本。

## 目录与执行契约

新增 `scenes-v4/scene-000`，并保留现有 `scenes-v3` 作为可恢复版本。`scene-000` 至少包含：

- `.claude/`
- `run-claude-ai.sh`
- 完整新版 `transcription.srt`
- 开场 `voiceover.wav`
- Claude 流日志、stderr 日志和用户阶段日志
- `scene-000.mp4`

V4 还需交付：

- `scenes-v4/manifest.json`
- `scenes-v4/timing-report.json`
- 可复现的合成清单或脚本
- 完整的 V4 PCM 音频时间轴

时间报告必须记录 `speechSamples`、呼吸长度、`openingFrames`、`openingDurationMs`、正文固定 4582 帧和最终总帧数。

`run-claude-ai.sh` 的固定字段为：

```bash
SCENE_ID="${SCENE_ID:-scene-000}"
SCENE_DURATION_SECONDS="${SCENE_DURATION_SECONDS:-<openingDuration>}"
OUTPUT_FILE="${OUTPUT_FILE:-${SCENE_ID}.mp4}"
FULL_TRANSCRIPT_PATH="${FULL_TRANSCRIPT_PATH:-transcription.srt}"
```

Claude 调用继续使用：

- 非交互式 Claude 调用
- `claude -p --dangerously-skip-permissions --verbose --output-format stream-json --prompt-suggestions false`
- 固定输出文件名和完整字幕路径
- 完整 MP4 交付要求

必须原样、按顺序且各出现一次：

```text
[[USER_MESSAGE]]需求理解和素材检查已完成
[[USER_MESSAGE]]开始联网搜索
[[USER_MESSAGE]]代码已完成，开始渲染
[[USER_MESSAGE]]视频已渲染完成：scene-000.mp4
```

日志继续使用原 jq 过滤逻辑：

```jq
fromjson?
| select(.type=="assistant")
| .message.content[]?
| select(.type=="text")
| .text
| split("\n")[]
| select(startswith("[[USER_MESSAGE]]"))
| sub("^\\[\\[USER_MESSAGE\\]\\]"; "")
```

同一时间只运行一个 Claude 调用。

## 最终合成

1. 复用已验证的 V3 正文，不重新调用 Claude 渲染 scene-001 至 scene-013。
2. 正文画面的唯一允许来源是 `final-v3-silent.mp4`，或者 `scenes-v3/normalized/scene-*.mp4` 的既有 4582 帧分配；禁止直接使用合计 4587 帧的 `scenes-v3/scene-*/scene-*.mp4`。
3. 正文音频唯一来源是 `scenes-v3/voiceover.wav`，正文字幕唯一来源是 `scenes-v3/transcription-retimed.srt`。整个 V4 流程只读 V3。
4. 将 `scene-000` 与固定 4582 帧正文拼接，最终视频总帧数必须等于 `openingFrames + 4582`。
5. 开场 PCM 与正文 PCM 按同一帧时间轴拼接，并补齐或裁切到精确 `(openingFrames + 4582) × 1600` 个采样/声道。
6. 对整条最终语音执行两遍 loudnorm：第一遍测量，第二遍显式传入 `measured_I`、`measured_LRA`、`measured_TP`、`measured_thresh` 和 offset；处理目标为 `I=-16`、`TP=-2.0`，为 AAC 编码保留真峰值余量。
7. 响度处理和 48kHz 重采样后，将 PCM 再次补齐或裁切到精确 `(openingFrames + 4582) × 1600` 个采样/声道，再编码为 AAC、48kHz、双声道。编码后重新扫描，最终文件必须为 `-16 ± 0.5 LUFS` 且 true peak 不高于 `-1.5 dBTP`。
8. 在 `timing-report.json` 中记录 V3 来源文件、正文帧数、时长和校验值。
9. 新结果先写入临时文件。替换前将当前 `final.mp4` 复制或硬链接为 `final-pre-v4.mp4` 并验证校验值一致；只有临时文件全部验证通过后，才将其原子 rename 为 `final.mp4`。当前 `final-v3.mp4` 和 `final-pre-v4.mp4` 始终保留。

## 验证与失败处理

交付前验证：

- `openingDuration` 在 12–15 秒内，且尾部呼吸为 0.5–0.8 秒
- 开场问题句没有错误断句
- 新字幕满足上述逐条偏移、空白和末尾时间约束
- `scene-000` 和所有正文镜头规格一致
- 最终总帧数精确等于 `openingFrames + 4582`
- 最终视频和音频时长相差不超过一帧
- 最终响度为 `-16 ± 0.5 LUFS`，true peak 不高于 `-1.5 dBTP`
- 全片完整 FFmpeg 解码无错误
- 抽帧检查开场、开场到正文的切换和现有图标修复均正常
- Claude 四条阶段消息各出现一次且顺序正确，stderr 无未处理错误

每次 TTS 或 Claude 尝试使用 `attempt-01`、`attempt-02` 等独立日志和产物目录，失败证据不得被下一次重试截断。TTS 失败只重试 TTS；Claude 失败只重试 `scene-000`；合成或验证失败只重做合成或对应验证阶段，不重新调用 Claude。任何失败都不得覆盖已验证的 V3 和上一个有效 `final.mp4`。
