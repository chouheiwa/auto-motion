# Publish Markdown Delivery Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make both video workflows deliver a root `publish.md` that is human-readable, machine-parseable, hash-bound, evidence-aware, and safe to reuse across projects.

**Architecture:** Add one syntactically valid generic template and one read-only Python validator. The validator owns schema, state, path, evidence, file-hash, and Markdown/frontmatter consistency rules; prompts own when and how project-specific values are generated. Static shell checks ensure both workflows and both READMEs keep the delivery contract visible.

**Tech Stack:** Markdown, YAML via PyYAML, Python 3 standard library, `unittest`, Bash, FFprobe/FFmpeg metadata already required by the project

---

## File Structure

- Create `templates/publish.md`: valid reusable draft template with YAML frontmatter and eleven canonical Markdown sections.
- Create `production/tools/validate_publish.py`: read-only parser and validator for templates and generated project files.
- Create `production/tests/test_publish_contract.py`: unit and integration tests covering schema, status, body consistency, paths, evidence, and hashes.
- Create `requirements.txt`: declare the existing PyYAML runtime dependency so the validator can be installed and audited reproducibly.
- Modify `PROMPT.md`: require draft-first and final-refresh `publish.md` behavior for the basic SRT workflow.
- Modify `PROMPT-PRODUCTION.md`: require evidence-backed `publish.md` behavior for the complete workflow.
- Modify `auto-test/validate-production-template.sh`: execute template validation and enforce both prompt contracts and bilingual documentation.
- Modify `auto-test/validate-main-boundary.sh`: reject a tracked root `publish.md` while allowing the template and validator.
- Modify `README.md` and `README.en.md`: document the new deliverable, status meaning, template, and validation command.

## Task 1: Parse and validate the reusable template

**Files:**
- Create: `templates/publish.md`
- Create: `production/tools/validate_publish.py`
- Create: `production/tests/test_publish_contract.py`
- Create: `requirements.txt`

- [ ] **Step 1: Write the failing template tests**

Create `production/tests/test_publish_contract.py` with:

```python
from copy import deepcopy
from pathlib import Path
import sys
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from production.tools.validate_publish import (  # noqa: E402
    PublishValidationError,
    parse_document,
    validate_document,
    validate_schema,
)


class PublishTemplateTests(unittest.TestCase):
    def test_template_parses_as_safe_yaml(self):
        data, body = parse_document(ROOT / "templates" / "publish.md")
        self.assertEqual(1, data["schema_version"])
        self.assertEqual("basic_srt", data["workflow"])
        self.assertEqual("draft", data["publish_status"])
        self.assertIn("## 发布状态", body)

    def test_template_passes_contract_without_project_files(self):
        validate_document(
            ROOT / "templates" / "publish.md",
            project_root=ROOT,
            template_mode=True,
        )

    def test_missing_top_level_key_fails(self):
        data, _ = parse_document(ROOT / "templates" / "publish.md")
        broken = deepcopy(data)
        del broken["copy"]
        with self.assertRaisesRegex(PublishValidationError, "copy"):
            validate_schema(broken)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  production/tests/test_publish_contract.py -v
```

Expected: FAIL because the template and validator do not exist.

- [ ] **Step 3: Create the valid generic draft template**

Create `requirements.txt` with the existing validator dependency:

```text
PyYAML>=6.0.2,<7
```

Create `templates/publish.md` using the exact frontmatter from the approved design, with these template defaults:

```yaml
schema_version: 1
workflow: basic_srt
publish_status: draft
platform: unspecified
generated_at: "1970-01-01T00:00:00Z"
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
  headphones: {status: not_applicable, note: no_audio_track}
  phone_speaker: {status: not_applicable, note: no_audio_track}
  cover_preview: {status: pending, note: ""}
  rights_confirmed: {status: pending, note: ""}
evidence:
  approval: ""
  machine_qc: ""
  visual_checklist: ""
  sound_checklist: ""
  asset_ledger: ""
  rights: []
```

The body must use this exact heading order:

```text
发布状态
发布平台
主标题
发布介绍
话题标签
封面文字
素材署名
成片规格与 SHA-256
证据索引
发布前人工检查
未完成事项
```

Use empty canonical `~~~text` blocks for title, introduction, and cover; use “无需署名” for credits; use fixed Markdown tables for video, evidence, and manual checks; list the template’s missing items under “未完成事项.”

- [ ] **Step 4: Implement the parser and schema validator**

Create `production/tools/validate_publish.py` with these public interfaces:

```python
class PublishValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PublishValidationError(message)


def parse_document(path):
    """Return (frontmatter_mapping, markdown_body) using yaml.safe_load."""


def validate_schema(data):
    """Validate required keys, exact nested keys, types, enums and scalar formats."""


def validate_document(path, project_root=None, template_mode=False):
    """Run every validator and return parsed data."""
```

Define constants:

```python
WORKFLOWS = {"production", "basic_srt"}
PUBLISH_STATUSES = {"draft", "pending_manual_checks", "blocked", "ready"}
CHECK_STATUSES = {"pending", "passed", "failed", "not_applicable"}
COVER_SOURCE_TYPES = {
    "confirmed_config",
    "detected_frame_zero",
    "generated_candidate",
    "unconfirmed",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
```

`parse_document` must require `---\n` at byte zero, locate the next standalone `---`, call `yaml.safe_load`, require a mapping, and never use unsafe YAML constructors.

`validate_schema` must validate all approved design invariants, including exact field types, positive video values when non-null, `line_count == len(title_lines)`, unique string hashtags, check mapping shape, and the `credits.required` conditional.

Add `validate_no_secrets(raw_text)` and reject common credential-bearing forms anywhere in the document: MiniMax/OpenAI-style `sk-...` keys, `Authorization:`/`Bearer`, `Cookie:`, and query parameters named `token`, `signature`, `sig`, `api_key`, or `key`.

- [ ] **Step 5: Run focused tests**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  production/tests/test_publish_contract.py -v
```

Expected: 3 tests pass.

- [ ] **Step 6: Check and commit**

Run:

```bash
git diff --check
python3 -m pip_audit -r requirements.txt
git add requirements.txt templates/publish.md production/tools/validate_publish.py \
  production/tests/test_publish_contract.py
git commit -m "feat: add publish delivery template"
```

Expected: no whitespace errors and no known dependency vulnerability. If `pip_audit` is unavailable, install it outside the repository environment before proceeding; do not skip the audit.

## Task 2: Enforce status, cover, audio, credit, and evidence invariants

**Files:**
- Modify: `production/tools/validate_publish.py`
- Modify: `production/tests/test_publish_contract.py`

- [ ] **Step 1: Add failing table-driven invariant tests**

Add a helper that deep-copies the template mapping and tests:

```python
def test_ready_rejects_pending_and_failed_checks(self):
    for status in ("pending", "failed"):
        data = ready_document_data()
        data["manual_checks"]["cover_preview"]["status"] = status
        with self.subTest(status=status):
            with self.assertRaises(PublishValidationError):
                validate_schema(data)


def test_generated_cover_candidate_must_stay_draft(self):
    data = ready_document_data()
    data["cover"]["source_type"] = "generated_candidate"
    data["cover"]["source_path"] = ""
    with self.assertRaisesRegex(PublishValidationError, "generated_candidate"):
        validate_schema(data)


def test_silent_video_requires_not_applicable_listening(self):
    data = draft_document_data()
    data["manual_checks"]["headphones"] = {"status": "pending", "note": ""}
    with self.assertRaisesRegex(PublishValidationError, "no_audio_track"):
        validate_schema(data)


def test_audio_video_requires_sample_rate_channels_and_listening(self):
    data = ready_document_data(audio=True)
    data["video"]["audio_sample_rate_hz"] = None
    with self.assertRaisesRegex(PublishValidationError, "audio_sample_rate_hz"):
        validate_schema(data)


def test_required_credit_needs_text_and_rights(self):
    data = ready_document_data()
    data["credits"] = {"required": True, "text": ""}
    data["evidence"]["rights"] = []
    unfinished = derive_unfinished_items(data)
    self.assertIn("credits_evidence_missing", unfinished)
    self.assertEqual("blocked", derive_publish_status(data, unfinished))
```

Also cover:

- every enum’s invalid value;
- invalid and uppercase SHA-256;
- valid `draft`, `pending_manual_checks`, `blocked`, and `ready` fixtures for both `production` and `basic_srt`;
- exact priority cases where blocked overrides incomplete/pending, draft overrides pending, and pending overrides ready;
- combined cases where a failed check or replacement diagnostic overrides `cover_unconfirmed` and other draft conditions;
- `ready` with missing copy/platform/video;
- `pending_manual_checks` without any pending check;
- `blocked` with `video_replacement_in_progress` or a concrete failed/integrity diagnostic;
- `production` evidence matrix;
- `basic_srt` optional evidence matrix;
- `not_applicable` without a note.

- [ ] **Step 2: Run and verify failure**

Expected: new tests fail on missing state and conditional validation.

- [ ] **Step 3: Implement conditional validation**

Add focused functions:

```python
def validate_video(video, template_mode=False): ...
def validate_cover(cover): ...
def validate_copy(copy): ...
def validate_credits_structure(credits, evidence): ...
def validate_manual_checks(checks, has_audio, publish_status): ...
def validate_workflow_requirements(data, template_mode=False): ...
def derive_unfinished_items(data, diagnostics=None, template_mode=False): ...
def derive_publish_status(data, unfinished_items): ...
def validate_publish_status(data, unfinished_items): ...
```

Status rules:

- Derive unfinished items using the exhaustive spec list and exact order: replacement; decode/hash/spec/approval diagnostics; failed checks in canonical check order; credit evidence; missing video/platform/title/introduction/hashtags/cover; missing workflow evidence in matrix order; pending checks in canonical check order. The replacement code comes directly from `video.replacement_in_progress: true`.
- Derive exactly one status with strict priority: any replacement/integrity/failure diagnostic → `blocked`; otherwise any missing final/publishing/evidence field → `draft`; otherwise any pending applicable check → `pending_manual_checks`; otherwise → `ready`.
- Cover and credit validators only validate types and contribute `cover_unconfirmed` or `credits_evidence_missing`; they do not reject a truthful higher-priority `blocked` combination before state derivation.
- Require the declared `publish_status` to equal the derived status. Template mode has one explicit exception: the canonical empty template is `draft`.
- Every structurally valid fixture for both workflows must produce and declare the exact derived status.

- [ ] **Step 4: Run focused tests**

Expected: all invariant tests pass.

- [ ] **Step 5: Check and commit**

```bash
git diff --check
python3 -m pip_audit -r requirements.txt
git add production/tools/validate_publish.py production/tests/test_publish_contract.py
git commit -m "feat: validate publish delivery states"
```

## Task 3: Validate canonical Markdown, paths, actual files, and approval hashes

**Files:**
- Modify: `production/tools/validate_publish.py`
- Modify: `production/tests/test_publish_contract.py`
- Modify: `templates/publish.md`

- [ ] **Step 1: Add failing body and filesystem tests**

Use `tempfile.TemporaryDirectory` and create isolated project fixtures. Cover:

- missing or reordered required headings;
- status/platform mismatch;
- title/introduction/hashtags/cover/credits mismatch;
- video, evidence, or manual-check table mismatch;
- malformed or non-minimal `~~~text` fence;
- non-inline-code or extra-line status/platform sections;
- multiline, duplicated, reordered, or prose-contaminated hashtag output;
- wrong credits fallback;
- table cells containing `|`, backslashes, or newlines that are not canonically escaped;
- stale, omitted, duplicated, or reordered “未完成事项” codes;
- absolute, `..`, URL, query-string, control-character, regex-invalid and nonexistent evidence paths;
- the same unsafe-path cases for `cover.source_path`;
- symlink resolving outside project;
- credentials, authorization headers, cookies, and signed URLs anywhere in the document;
- actual `final.mp4` hash mismatch;
- existing decodable `final.mp4` with omitted hash or specifications;
- FFprobe metadata mismatch for duration, resolution, FPS, codec, pixel format, sample rate, or channels;
- an undecodable file that is not represented as `blocked`;
- `approval.expected_delivery.path` not equal to `final.mp4`;
- `approval.expected_delivery.sha256` mismatch;
- optional `approval.delivery_verification.actual_sha256` mismatch.
- missing or malformed `expected_delivery` and `delivery_verification` mappings.
- contract-valid blocked documents for decode, video-hash, video-spec, approval-hash and credit-evidence diagnostics;
- the same diagnostics mislabeled as draft/pending/ready or omitted from “未完成事项,” which must hard-fail.

Create fixture helpers:

```python
def write_publish(path, data, body): ...
def canonical_body(data, unfinished=None): ...
def fenced_text(value): ...
def sha256_file(path): ...
```

`canonical_body` must be independent test code, not imported from the validator.

- [ ] **Step 2: Run and verify failure**

Expected: new tests fail on missing body/path/file validation.

- [ ] **Step 3: Implement body parsing**

Add:

```python
REQUIRED_SECTIONS = (
    "发布状态",
    "发布平台",
    "主标题",
    "发布介绍",
    "话题标签",
    "封面文字",
    "素材署名",
    "成片规格与 SHA-256",
    "证据索引",
    "发布前人工检查",
    "未完成事项",
)


def parse_sections(body): ...
def parse_fenced_text(section, name): ...
def parse_markdown_table(section, name): ...
def parse_inline_code_scalar(section, name): ...
def escape_table_cell(value): ...
def unescape_table_cell(value): ...
def validate_body_consistency(data, body, unfinished_items): ...
```

Require the eleven headings in order. Allow one optional `备选文案` section only after the eleven canonical sections. Reject duplicate headings.

`parse_fenced_text` must require a `~` fence of at least length 3, a `text` info string, matching closing fence, and a fence length exactly one greater than the longest `~` run in the payload or 3 when no longer run exists.

Tables must have exact canonical keys and no duplicate rows. Rights rows must be either `rights | 未提供` or contiguous `rights[0]`, `rights[1]`, etc.

Status and platform sections must contain exactly one backtick-wrapped scalar and nothing else. Hashtags must be a single line in YAML list order. Credits must use a canonical fenced block when nonempty and exactly “无需署名” otherwise. Table cells use a reversible one-pass algorithm: encode `\` as `\\`, newline as `\n`, and `|` as `\|`; reject unknown escapes while decoding.

Parse “未完成事项” as an ordered Markdown list of the exhaustive codes and exact ordering defined by the spec; use the single line “无” only when the derived list is empty.

- [ ] **Step 4: Implement safe paths and file binding**

Add:

```python
def safe_project_path(value, project_root, must_exist, field_name): ...
def sha256_file(path): ...
def probe_video_metadata(path): ...
def decode_video(path): ...
def collect_filesystem_diagnostics(data, project_root, template_mode=False): ...
def validate_evidence_paths(data, project_root, template_mode=False): ...
def validate_video_hash(data, project_root, template_mode=False): ...
def validate_approval_hash(data, project_root, template_mode=False): ...
```

Resolve every nonempty evidence path and confirmed `cover.source_path`; reject paths outside `project_root`. Require the lexical value to match `[A-Za-z0-9._/-]+`. Reject URLs, query/fragment characters, control characters, absolute paths, `..`, and escaping symlinks. For project delivery mode, require every nonempty path to exist.

When `project_root/final.mp4` physically exists, always hash it. Run FFprobe with JSON output for format duration plus video/audio stream fields, parse FPS with `fractions.Fraction`, and compare duration within one frame. Run FFmpeg with `-v error -i <file> -f null -` to require complete decode. A decodable file requires all declared hash/spec fields even in `draft`; an undecodable file requires a hash, may leave unreadable specs empty, emits `final_video_undecodable`, and derives `blocked`.

Hash/spec/approval mismatches are diagnostics, not immediate parser errors. A document passes only when it declares `blocked` and its canonical unfinished list exactly contains the collected diagnostics. The same mismatch under `draft`, `pending_manual_checks`, or `ready`, or with missing/stale diagnostic codes, is a hard validation failure.

For production workflow, parse `evidence.approval` as JSON and compare actual hash against `expected_delivery.sha256`; if present, also compare `delivery_verification.actual_sha256`.

- [ ] **Step 5: Add CLI behavior**

Support:

```bash
python3 production/tools/validate_publish.py templates/publish.md --template
python3 production/tools/validate_publish.py publish.md --project-root .
```

Print `publish validation passed: <path>` on success. On `PublishValidationError`, YAML/JSON parse failure, missing file, or type error, print `publish validation failed: <reason>` to stderr and return 1.

- [ ] **Step 6: Run focused tests**

Expected: all publish contract tests pass.

- [ ] **Step 7: Check and commit**

```bash
git diff --check
python3 -m pip_audit -r requirements.txt
git add templates/publish.md production/tools/validate_publish.py \
  production/tests/test_publish_contract.py
git commit -m "test: enforce publish evidence binding"
```

## Task 4: Add `publish.md` to both workflow contracts

**Files:**
- Modify: `auto-test/validate-production-template.sh`
- Modify: `PROMPT.md`
- Modify: `PROMPT-PRODUCTION.md`

- [ ] **Step 1: Make static contract checks fail first**

Extend `auto-test/validate-production-template.sh` with:

```bash
BASIC_PROMPT="$ROOT_DIR/PROMPT.md"
PUBLISH_TEMPLATE="$ROOT_DIR/templates/publish.md"
PUBLISH_VALIDATOR="$ROOT_DIR/production/tools/validate_publish.py"

require_file "$BASIC_PROMPT"
require_file "$PUBLISH_TEMPLATE"
require_file "$PUBLISH_VALIDATOR"

python3 "$PUBLISH_VALIDATOR" "$PUBLISH_TEMPLATE" --template ||
  fail "publish template validation failed"
```

Require both prompts to mention root `publish.md`, `templates/publish.md`, final SHA-256, same-filesystem temporary files, validation-before-rename, safe YAML serialization, atomic refresh, validator execution, and failure reporting.

Require the production prompt to mention `expected_delivery.sha256`, evidence-backed credits, all four manual checks, and all four publish statuses.

Require the basic prompt to mention `workflow: basic_srt`, `unspecified`, `generated_candidate`, `no_audio_track`, and explicit missing evidence.

- [ ] **Step 2: Run and verify failure**

Run:

```bash
bash auto-test/validate-production-template.sh
```

Expected: FAIL because the prompts lack the new contract.

- [ ] **Step 3: Extend the basic workflow**

Add a “发布配置交付” section to `PROMPT.md` before final delivery:

- copy `templates/publish.md` as structural reference, never as filled project output;
- create a draft after subtitle analysis;
- derive copy only from the complete final SRT;
- use platform `unspecified` when absent;
- source cover from confirmed input, detected frame-zero title, or a clearly unconfirmed generated candidate;
- when an existing final video will be replaced, first set `video.replacement_in_progress: true` and atomically write a valid `blocked` file that preserves the old hash and lists `video_replacement_in_progress`;
- inspect the actual final video and fill exact specs/hash;
- use `audio_codec: none` and `no_audio_track` listening exemptions for silent output;
- preserve missing evidence as empty/pending;
- serialize frontmatter with `yaml.safe_dump`, never concatenate unescaped external text;
- write a same-filesystem temporary file, run `python3 production/tools/validate_publish.py <temp> --project-root .`, and only then atomically rename it to `publish.md`;
- if no final video exists, keep a valid `draft` with `final_video_missing`; if an invalid final file exists, construct and validate a `blocked` refresh with the appropriate decode/hash/spec code;
- never rename an invalid temporary document. If a valid replacement document cannot be constructed, retain the last valid `publish.md`, report the refresh failure, and never claim `ready`.

Add `publish.md` to the final-delivery bullet list.

- [ ] **Step 4: Extend the complete workflow**

Add a “发布配置生命周期” subsection near the platform/script/cover freeze point and a “第十二阶段：刷新发布配置” after final approval:

- create the first draft immediately after platform/script/cover freeze, before rendering and approval;
- before replacing an existing final video, set `video.replacement_in_progress: true` and atomically update old `publish.md` to blocked with `video_replacement_in_progress`;
- after final delivery, fill actual specs/hash;
- after the new video and hash validate, set `video.replacement_in_progress: false`;
- read `approval.expected_delivery.sha256` and optional delivery verification hash;
- populate evidence and credits from real project files;
- compute the four-state status;
- use `yaml.safe_dump`; write a same-filesystem temporary file, validate the temporary file, and only then atomically rename;
- use `draft` when no final video exists, `blocked` for replacement/integrity/failure diagnostics, and `pending_manual_checks` only when all non-manual data is complete;
- never rename an invalid temporary document; retain the last valid file and report the refresh failure if no valid status document can be constructed.

Add root `publish.md` to the final delivery checklist and final report.

- [ ] **Step 5: Run static and Python tests**

```bash
bash auto-test/validate-production-template.sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  production/tests/test_publish_contract.py -v
```

Expected: all pass.

- [ ] **Step 6: Check and commit**

```bash
git diff --check
python3 -m pip_audit -r requirements.txt
git add PROMPT.md PROMPT-PRODUCTION.md auto-test/validate-production-template.sh
git commit -m "feat: deliver publish metadata in video workflows"
```

## Task 5: Document and enforce the generic Main boundary

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `auto-test/validate-main-boundary.sh`
- Modify: `auto-test/validate-production-template.sh`

- [ ] **Step 1: Add failing documentation and boundary checks**

Require both READMEs to contain:

- `publish.md`;
- `templates/publish.md`;
- `publish_status`;
- the validator command;
- an explanation that ready does not mean already published.

Add `'^publish\.md$'` to `forbidden_patterns` in `auto-test/validate-main-boundary.sh`.

- [ ] **Step 2: Update the Chinese README**

Update:

- workflow deliverables table;
- orchestration steps;
- generated-file tree;
- complete-flow output paragraph;
- result-viewing section;
- test commands;
- repository layout;
- notes explaining status semantics.

- [ ] **Step 3: Update the English README**

Mirror the same information in English without changing the existing workflow meaning.

- [ ] **Step 4: Run the complete verification suite**

```bash
bash auto-test/validate-main-boundary.sh
bash auto-test/validate-production-template.sh
PYTHONDONTWRITEBYTECODE=1 python3 production/tools/validate_style_guide.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  production/tests/test_style_guide.py \
  production/tests/test_publish_contract.py -v
git diff --check
python3 -m pip_audit -r requirements.txt
```

Expected:

- Main boundary passes while the generic template remains tracked.
- Production-template contract passes for both prompts and READMEs.
- Style guide validation passes.
- All Python tests pass.
- No whitespace errors.

- [ ] **Step 5: Verify changed-file scope**

Run:

```bash
git status --short
git diff --name-only main...HEAD
```

Expected: only the spec/plan and generic files listed in this plan; no root `publish.md`, final video, script, subtitles, scenes, audio, or single-project evidence.

- [ ] **Step 6: Commit documentation and boundary changes**

```bash
git add README.md README.en.md auto-test/validate-main-boundary.sh \
  auto-test/validate-production-template.sh
git commit -m "docs: explain publish delivery metadata"
```

## Task 6: Final verification and integration readiness

**Files:**
- Verify all files changed by Tasks 1–5.

- [ ] **Step 1: Re-run all contract checks from a clean worktree state**

```bash
bash auto-test/validate-main-boundary.sh
bash auto-test/validate-production-template.sh
PYTHONDONTWRITEBYTECODE=1 python3 production/tools/validate_style_guide.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s production/tests -p 'test_*.py' -v
python3 -m pip_audit -r requirements.txt
git diff --check
git status --short
```

Expected: every check passes and the worktree is clean.

- [ ] **Step 2: Inspect the final generic diff**

```bash
git diff --stat main...HEAD
git diff --name-status main...HEAD
```

Reject the integration if any project-specific file appears.

- [ ] **Step 3: Record the commit range**

```bash
git log --oneline main..HEAD
```

Expected: only the publish-contract implementation commits and the approved plan commit.
