# `publish.md` 通用发布交付合同设计

日期：2026-07-28

## 目标

为完整制作流程 `PROMPT-PRODUCTION.md` 和基础 SRT 流程 `PROMPT.md` 增加统一的发布配置交付物：项目根目录 `publish.md`。

`publish.md` 同时服务两类使用者：

- 人类发布者可以直接复制平台、标题、介绍、话题、封面文字和署名信息，并查看发布前待办。
- 后续自动发布工具可以从 YAML frontmatter 读取稳定字段、状态和证据路径。

该合同属于通用模板，不得包含任何单片的固定标题、平台、素材或审批结果。

## 交付位置与生命周期

- 文件固定写入项目根目录：`publish.md`。
- 两条制作流程都必须生成该文件。
- 在平台、稿件或字幕、封面方向冻结后，先生成状态为 `draft` 的初版。
- 根目录 `final.mp4` 完成原子交付并获得最终规格和 SHA-256 后，刷新视频字段、证据和发布状态。
- 即使成片、审批或人工检查受阻，流程仍必须交付 `publish.md`，并使用 `draft`、`pending_manual_checks` 或 `blocked` 明确反映现状。
- 如果已有 `publish.md`，在替换 `final.mp4` 前先原子更新为 `blocked`，保留仍与旧视频匹配的旧哈希，并在“未完成事项”写入 `video_replacement_in_progress`，避免旧文件继续呈现为可发布状态。
- 如果 `final.mp4` 被替换，必须同步刷新 `publish.md`；哈希不一致时验证失败且不得完成交付。
- 生成或刷新失败不得静默忽略，最终汇报必须说明失败原因和旧文件状态。

## 文件结构

文件由 YAML frontmatter 和 Markdown 正文组成。

### YAML frontmatter

规范字段如下：

```yaml
---
schema_version: 1
workflow: production
publish_status: draft
platform: unspecified
generated_at: "YYYY-MM-DDTHH:MM:SSZ"
video:
  path: final.mp4
  sha256: ""
  duration_seconds: null
  width_px: null
  height_px: null
  fps: null
  video_codec: ""
  pixel_format: ""
  replacement_in_progress: false
  audio_codec: none
  audio_sample_rate_hz: null
  audio_channels: null
cover:
  title_lines: []
  line_count: 0
  frame: 0
  source_type: unconfirmed
  source_path: ""
copy:
  primary_title: ""
  introduction: ""
  hashtags: []
credits:
  required: false
  text: ""
manual_checks:
  headphones: {status: pending, note: ""}
  phone_speaker: {status: pending, note: ""}
  cover_preview: {status: pending, note: ""}
  rights_confirmed: {status: pending, note: ""}
evidence:
  approval: ""
  machine_qc: ""
  visual_checklist: ""
  sound_checklist: ""
  asset_ledger: ""
  rights: []
---
```

### Markdown 正文

正文固定包含十一个二级章节：

1. 发布状态。
2. 发布平台。
3. 主标题。
4. 发布介绍。
5. 话题标签。
6. 封面文字。
7. 素材署名。
8. 成片规格与 SHA-256。
9. 证据索引。
10. 发布前人工检查。
11. 未完成事项。

可以增加“备选文案”章节，但必须只有一个主标题和一则主发布介绍。

## Schema 约束

- `schema_version` 必须是整数 `1`。
- `workflow` 只允许 `production` 或 `basic_srt`。
- `publish_status` 只允许 `draft`、`pending_manual_checks`、`blocked`、`ready`。
- `platform` 必须是非空字符串；未知时使用 `unspecified`。
- `generated_at` 必须是带时区的 ISO 8601 时间。
- `video.path` 固定为安全的项目相对路径 `final.mp4`。
- 存在最终视频时，`video.sha256` 必须是 64 位小写十六进制字符串。非 `blocked` 状态必须与实际哈希一致；`blocked` 可以保留不一致的旧哈希，但必须包含 `video_hash_mismatch`。
- 存在且可解码的最终视频必须填写完整视频规格；视频数值字段必须为正数，并与 FFprobe 实测结果一致。
- 没有最终视频时使用空哈希、空 codec 和 `null` 数值，不得用 `0` 冒充检测结果。
- 最终视频存在但无法解码时仍记录实际文件哈希，无法可信读取的规格可以为空，并将状态标记为 `blocked`。
- `video.replacement_in_progress` 必须是布尔值；替换前设为 `true`，新视频和新哈希验证完成后恢复为 `false`。
- `cover.title_lines` 必须是字符串列表，`line_count` 必须等于列表长度，`frame` 固定为整数 `0`。
- `cover.source_type` 只允许 `confirmed_config`、`detected_frame_zero`、`generated_candidate`、`unconfirmed`。
- `confirmed_config` 必须有安全且存在的项目相对 `source_path`；其他类型的 `source_path` 必须为空。
- `generated_candidate` 或 `unconfirmed` 形成 `cover_unconfirmed`。没有更高优先级诊断时状态为 `draft`；存在替换、完整性或失败诊断时，严格优先得到 `blocked`。
- `copy.primary_title` 和 `copy.introduction` 是字符串，`copy.hashtags` 是去重后的字符串列表。
- `credits.required: true` 且缺少 `credits.text` 或 `evidence.rights` 时形成 `credits_evidence_missing`，文档必须标记为 `blocked`；该缺失属于可表达的发布阻塞，不属于 YAML 结构错误。
- 检查状态只允许 `pending`、`passed`、`failed`、`not_applicable`。
- 检查为 `not_applicable` 时必须提供非空 `note`。
- 有音轨时，音频 codec、采样率和声道数必须来自实际检测，耳机和手机外放不得标记 `not_applicable`。
- 无音轨时使用 `audio_codec: none`，采样率和声道数为 `null`；耳机和手机外放标记 `not_applicable`，note 写明 `no_audio_track`。
- YAML 与 Markdown 中的平台、主标题、介绍、话题、封面文字、署名、视频规格、哈希、状态和证据必须一致。

## 发布状态机

状态按以下优先级计算：

1. `blocked`：`video.replacement_in_progress: true`、最终视频无法解码、哈希或规格不一致，任一必需检查为 `failed`，或已确认需要署名但缺少授权证据。
2. `draft`：不存在最终视频，平台或主发布信息未确认，封面候选未确认，或必填字段/证据仍缺失。
3. `pending_manual_checks`：最终视频和发布信息完整、机器验证通过、没有失败项，但至少一项适用的人工检查为 `pending`。
4. `ready`：最终视频哈希绑定正确，所有必填发布信息和证据完整，所有适用检查均为 `passed`，其余检查具有合理的 `not_applicable` 说明。

机器检查通过不能自动替代耳机试听、手机外放、封面预览或版权确认。`ready` 只表示文件和发布配置已准备好，不表示已经在平台完成发布。

## 工作流要求矩阵

下表定义进入 `pending_manual_checks` 或 `ready` 前的必填证据；未列为必填的字段允许为空，但非空时仍必须是安全且存在的项目相对路径。

| Evidence 字段 | `production` | `basic_srt` |
| --- | --- | --- |
| `approval` | 必填 | 可选 |
| `machine_qc` | 必填 | 可选 |
| `visual_checklist` | 必填 | 可选 |
| `sound_checklist` | 有音轨时必填；无音轨可选 | 可选 |
| `asset_ledger` | 必填，包括“未使用第三方素材”的空账本 | 可选 |
| `rights` | `credits.required: true` 时至少一条 | `credits.required: true` 时至少一条 |

人工检查要求：

| 检查 | 有音轨 | 无音轨 |
| --- | --- | --- |
| `headphones` | `ready` 前必须 `passed` | 必须 `not_applicable`，note 为 `no_audio_track` |
| `phone_speaker` | `ready` 前必须 `passed` | 必须 `not_applicable`，note 为 `no_audio_track` |
| `cover_preview` | `ready` 前必须 `passed` | `ready` 前必须 `passed` |
| `rights_confirmed` | `ready` 前必须 `passed` | `ready` 前必须 `passed` |

`production` 使用 `confirmed_config` 作为已确认封面来源。`basic_srt` 可以使用 `confirmed_config` 或 `detected_frame_zero` 进入后续状态；`generated_candidate` 和 `unconfirmed` 始终保持 `draft`。

## 正文规范化格式

为保证 YAML 与正文可以确定性比对，固定使用以下格式：

- “发布状态”和“发布平台”章节的首个非空行分别是反引号包裹的单一 YAML 值。
- “主标题”“发布介绍”和非空“素材署名”使用规范化 fenced text block。围栏字符固定为 `~`，长度取正文中最长连续 `~` 数加一且至少为 3；开始行是对应数量的 `~` 加 `text`，结束行只包含相同数量的 `~`。围栏内保留原始换行和字符，验证器必须无损取回。
- “话题标签”按 YAML 列表顺序在一行中以空格连接。
- “封面文字”使用一个规范化 fenced text block，每个标题行对应围栏内一行，顺序与 `cover.title_lines` 完全一致。
- 不需要署名且 `credits.text` 为空时，“素材署名”固定写“无需署名”。
- “成片规格与 SHA-256”使用固定键名表格，逐项呈现 `video` 字段。
- “证据索引”使用固定键名表格，逐项呈现 `approval`、`machine_qc`、`visual_checklist`、`sound_checklist`、`asset_ledger`；空字符串固定呈现“未提供”。`rights` 按 YAML 列表顺序展开为 `rights[0]`、`rights[1]` 等独立行，空列表用单行 `rights | 未提供`。
- “发布前人工检查”使用固定键名表格，逐项呈现检查状态和 note。
- “未完成事项”根据状态、空字段、`pending` 和 `failed` 自动列出；没有未完成项时固定写“无”。

验证器必须解析这些章节并与 frontmatter 逐字段比对，不接受仅凭章节存在即通过。

“未完成事项”只允许以下代码，并按此固定顺序生成；带字段名的代码按括号中的固定字段顺序展开：

1. `video_replacement_in_progress`
2. `final_video_undecodable`
3. `video_hash_mismatch`
4. `video_spec_mismatch`
5. `approval_hash_mismatch`
6. `manual_check_failed:<name>`（`headphones`、`phone_speaker`、`cover_preview`、`rights_confirmed`）
7. `credits_evidence_missing`
8. `final_video_missing`
9. `platform_unconfirmed`
10. `primary_title_missing`
11. `introduction_missing`
12. `hashtags_missing`
13. `cover_unconfirmed`
14. `evidence_missing:<field>`（按工作流要求矩阵中的字段顺序）
15. `manual_check_pending:<name>`（按上述检查顺序）

文件系统诊断先于状态计算：验证器先探测最终文件、解码、规格、哈希和审批绑定，形成诊断代码，再与 frontmatter 字段和人工检查共同推导状态。

验证分为两层：

- 硬错误：YAML/Markdown 无法解析、类型或枚举错误、不安全路径、凭据泄露、正文与 frontmatter 不一致、状态或“未完成事项”没有真实反映诊断。硬错误返回非零。
- 合同有效但受阻：解码失败、视频哈希/规格不一致、审批哈希不一致、必需检查失败或署名证据缺失。只要状态为 `blocked` 且诊断代码完整准确，验证返回成功并报告当前受阻状态。

## 两条流程的取值规则

### 完整制作流程

- 平台来自制作配置。
- 视频规格和 SHA-256 来自最终 `final.mp4` 的实际检测。
- 封面文字来自已确认封面配置，`cover.source_type` 写 `confirmed_config`，`cover.source_path` 写对应配置路径。
- 标题、介绍和话题必须根据最终稿与成片生成，不得使用早期草稿。
- 署名信息来自素材账本与授权证据，不得凭印象补写。
- 人工检查状态来自声音、视觉和审批检查表。
- Evidence 至少覆盖存在的审批、机器 QC、视觉检查、声音检查、素材账本和授权证据。
- `approval.json` 必须提供 `expected_delivery.path: final.mp4` 和 64 位小写十六进制 `expected_delivery.sha256`。验证器以该字段作为批准哈希，并要求它与 `publish.md` 及实际 `final.mp4` 一致。
- 如果审批文件同时存在 `delivery_verification.actual_sha256`，该值也必须与上述三个哈希一致。

### 基础 SRT 流程

- 视频规格和 SHA-256 来自最终 `final.mp4`。
- 根据完整字幕生成与内容一致的主标题、介绍和话题。
- 平台未提供时写 `unspecified`，状态保持 `draft`。
- 封面文字优先来自用户输入或第 0 帧已存在的完整标题；对应使用 `confirmed_config` 或 `detected_frame_zero`。两者都没有时可以根据完整字幕给出候选，但 `cover.source_type` 写 `generated_candidate`、`source_path` 为空，状态保持 `draft`。
- 没有音轨时按无音轨规则填写音频字段，并将耳机、手机外放标记为 `not_applicable`。
- 没有素材账本、审批文件或人工检查记录时，使用空字符串、空列表和 `pending`，并在“未完成事项”中明确列出。

## 证据路径与安全边界

- Evidence 路径必须使用项目相对路径，并匹配 `[A-Za-z0-9._/-]+`。
- 禁止绝对路径、`..`、URL、凭据、查询参数和指向项目外部的符号链接。
- 非空 evidence 路径必须存在；目录型授权证据可以使用相对目录，文件型证据使用相对文件。
- `publish.md` 不得包含 API 密钥、认证头、Cookie、签名 URL 或其他凭据。
- 标题、介绍、署名和其他外部文本必须使用安全 YAML 序列化；不得用字符串拼接生成未转义 frontmatter。
- 多行文本优先使用 YAML block scalar，正文中的 Markdown 控制字符也要安全转义。
- Markdown 表格单元格使用可逆编码：先把反斜杠编码为 `\\`，再把换行编码为 `\n`，最后把竖线编码为 `\|`。解析时使用单次状态机逆向还原并拒绝其他未知反斜杠转义，不使用有歧义的 `<br>` 替换。
- 文件必须在同一文件系统内写入临时文件、完成解析和一致性验证后，再原子重命名为 `publish.md`。

## 模板、验证器与测试

新增 `templates/publish.md`，提供可解析的默认 YAML、正文结构和通用说明。

新增通用验证器 `production/tools/validate_publish.py`：

- 读取 `publish.md` 或指定路径。
- 使用安全 YAML 解析。
- 校验 schema、字段类型、枚举、状态转换、哈希格式、音频条件字段、封面行数、署名条件和安全 evidence 路径。
- 对实际项目文件校验最终视频哈希和非空证据路径。
- 最终视频存在时使用 FFprobe 读取流与容器规格，并用 FFmpeg 完整解码；将实际时长、分辨率、帧率、codec、pixel format 和音频规格与 YAML 对比。
- 文件存在且可解码时，即使状态为 `draft` 也不得省略哈希或规格；文件存在但不可解码时必须形成 `final_video_undecodable` 并标记 `blocked`。
- 校验 frontmatter 与 Markdown 正文的一致性。
- 对硬错误返回非零退出码；对合同有效的 `draft`、`pending_manual_checks`、`blocked`、`ready` 返回成功并打印真实状态。验证器不修改输入文件。

新增 `production/tests/test_publish_contract.py`，至少包含：

- 两种 workflow 下合法的 `draft`、`pending_manual_checks`、`blocked` 和 `ready` 样例。
- 缺字段、非法枚举、无效 SHA-256、封面行数不一致。
- 有音轨但缺采样率/声道、无音轨但试听状态错误。
- 需要署名但缺授权证据。
- `pending` 或 `failed` 被错误标记为 `ready`。
- 绝对路径、父目录穿越、URL、项目外符号链接和不存在 evidence。
- YAML 与 Markdown 的状态、平台、文案、封面、规格、证据或检查表不一致。
- 实际 `final.mp4` 哈希与 frontmatter 或审批证据不一致。

扩展 `auto-test/validate-production-template.sh`：

- 运行模板验证器。
- 验证 `PROMPT.md` 和 `PROMPT-PRODUCTION.md` 都要求生成根目录 `publish.md`。
- 验证完整流程包含最终哈希、署名证据、人工检查和原子刷新要求。
- 验证基础流程包含 `unspecified`、候选封面、静音检查和缺失信息规则。

扩展 `auto-test/validate-main-boundary.sh`，禁止根目录单片产物 `publish.md` 进入 `main`，但允许通用模板、验证器和测试。

## 文档更新

同时更新 `README.md` 和 `README.en.md`：

- 两条流程的交付结果都加入 `publish.md`。
- `final.mp4` 是媒体交付，`publish.md` 是发布配置交付。
- 说明 YAML 供自动读取、Markdown 供人工复制。
- 说明 `publish_status: ready` 不表示平台已经实际发布。
- 给出模板和验证命令入口。

## 验收标准

- 两条流程都明确生成根目录 `publish.md`，受阻时也会生成带真实状态的文件。
- 通用模板是合法 YAML，并包含十一个固定正文章节。
- 状态机覆盖成功、待人工、信息未确认和失败四种结果。
- 完整流程和基础流程的封面、音频和缺失信息处理不同且清晰。
- 视频哈希与实际文件、审批证据一致。
- Evidence 路径存在、安全且不泄露凭据。
- YAML 与正文中的发布信息一致。
- 验证器具有正面和负面测试，不只依赖文本 grep。
- 中英文 README、两条 Prompt、模板、验证器和测试入口同步更新。
- Main 边界检查、生产模板检查和发布合同测试全部通过。
