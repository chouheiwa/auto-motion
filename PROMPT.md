读取当前工作目录的 `transcription.srt`，按语义拆分镜头，为每个镜头创建独立工作目录，顺序调用渲染工具制作 MG 动画，最后用 ffmpeg 拼接并交付 `final.mp4`。

## 工作边界

- 不设计镜头内部的具体 MG 动效，也不替渲染工具写动画方案；渲染工具负责单个镜头的创意、代码实现和 mp4 渲染。
- 你负责调用渲染工具，修改`run-scene.sh`中的提示词。可以根据当前镜头文案调整提示词描述，不要求逐字沿用模板中的 `PROMPT`。调整目标是让单个镜头的艺术效果、视觉概念和动效表达更贴合文案。
- 不得改变模板中的执行契约：非交互式运行、输出文件名、完整字幕路径、阶段性汇报格式、日志过滤方式和最终 mp4 交付要求必须保持确定。

## 镜头拆分

根据 `transcription.srt` 做粗粒度分镜。一个镜头可以包含单条字幕，也可以合并连续多条字幕；合并依据是文案是否表达同一主题、同一因果关系或同一视觉概念。

每个镜头必须对应一个连续时间区间，所有镜头按顺序首尾相接，完整覆盖 `transcription.srt` 从第一条字幕开始到最后一条字幕结束的总跨度。字幕之间的无文字空白不能丢失，应并入前一个镜头作为停顿、收尾或转场；空白很长时也可以单独做静默/转场镜头。

每个镜头的时长用“秒”作为单位，保留 SRT 毫秒精度，写成小数秒，例如 `2.833`、`6.500`，不要四舍五入或截断为整数秒。调用渲染工具前必须复核：所有 `SCENE_DURATION_SECONDS` 之和应等于 `最后一条字幕结束时间 - 第一条字幕开始时间`，误差不超过 0.1 秒。

## 镜头目录

为每个镜头创建独立目录，建议使用 `scenes/scene-001`、`scenes/scene-002` 这样的命名。目录结构参考 `exampleFolder`，至少包含：

- `.claude/`：放置 hyperframes 相关 skills 或项目指令（Claude Code 渲染时自动发现；其他渲染工具由 `run-scene.sh` 自行处理）。
- `run-scene.sh`：从模板复制后按当前镜头填写。
- `transcription.srt`：复制完整字幕文件，供渲染工具理解整体上下文。

`run-scene.sh` 模板中已有镜头编号、镜头时长、输出文件名、完整字幕路径和镜头文案等字段；先阅读模板，再为当前镜头填写这些字段。可以改写模板中的 `PROMPT` 内容来强化当前镜头的表达，但必须保留上述字段、阶段性汇报规则和交付约束。

## 调度和等待

同一时间只运行一个渲染工具调用，按镜头顺序执行，不并行启动多个渲染工具。

使用 `run-scene.sh` 模板中定义的阶段性汇报规则；脚本只放行以 `[[USER_MESSAGE]]` 开头的消息给你和用户。

如果一段时间没有新的 `[[USER_MESSAGE]]` 输出，不要立即判定失败；先检查：

- `render-<scene>.stream.jsonl` 和 `render-<scene>.stderr.log` 是否仍在写入。
- 项目文件、渲染目录或 mp4 文件是否有更新时间。
- 是否存在 hyperframes、ffmpeg、Chromium 或 Node 渲染进程。
- `run-scene.sh` 的最终退出码。

只有在进程退出失败，或长时间无日志、无文件更新且无渲染进程时，才判定该镜头失败并记录失败原因。

## 发布配置交付

除视频外，根目录必须交付 `publish.md`。以 `templates/publish.md` 为结构参考，但不得把模板当成已经填写的项目结果。

- 完成字幕分析后先生成 `workflow: basic_srt` 的草稿。标题、介绍、话题和封面候选必须来自完整终稿 SRT；平台未知时写 `unspecified`。
- 封面只可标记为用户已确认的 `confirmed_config`、第 0 帧实测得到的 `detected_frame_zero`，或尚待确认的 `generated_candidate`。候选未确认时保持 `draft`。
- 最终视频为静音时写 `audio_codec: none`，耳机和手机外放检查使用 `not_applicable` 与 `no_audio_track`。不存在的审批、账本或检查证据保持空值或 `pending`，并在未完成事项中明确列出。
- 如果将替换已有 `final.mp4`，先保留旧哈希，将 `video.replacement_in_progress: true`，以 `video_replacement_in_progress` 原子刷新为有效 `blocked` 文档；新视频、最终 SHA-256 和规格全部验证后才能恢复为 `false`。
- 使用 FFprobe 和完整解码读取实际成片规格并计算最终 SHA-256。没有成片时保留包含 `final_video_missing` 的有效 `draft`；成片无法解码或存在哈希/规格异常时，生成含对应诊断的有效 `blocked` 文档。
- YAML frontmatter 必须用 `yaml.safe_dump` 安全序列化，不得拼接未转义外部文本。临时文件与 `publish.md` 必须位于同一文件系统。
- 每次生成或刷新都先对临时文件执行 `python3 production/tools/validate_publish.py <临时文件> --project-root .`；只有验证通过后才原子重命名为根目录 `publish.md`。无效临时文件不得替换现有文件；保留最后一个有效版本，汇报刷新失败，且不得声称 `ready`。

## 最终交付

所有镜头 mp4 完成后，使用 ffmpeg 按镜头顺序拼接为 `final.mp4`。拼接前确认每个镜头满足统一规格；如规格不一致，先转码规范化。只有一个镜头时，也需要将该镜头 mp4 复制或转码为 `final.mp4`。

最终交付：

- 每个镜头目录中的渲染日志和镜头 mp4。
- 拼接后的 `final.mp4`。
- 根目录 `publish.md`，包含实际成片规格、最终 SHA-256、发布文案和未完成事项。
- 如有失败，提供失败镜头编号、失败阶段、关键日志和建议重试方式。
