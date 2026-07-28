from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from production.tools.validate_publish import (  # noqa: E402
    CHECK_ORDER,
    EVIDENCE_ORDER,
    VIDEO_KEYS,
    PublishValidationError,
    derive_publish_status,
    derive_unfinished_items,
    escape_table_cell,
    parse_document,
    safe_project_path,
    validate_document,
    validate_schema,
)


def fenced(value):
    longest = max([len(run) for run in value.split("x") if set(run) == {"~"}] or [0])
    size = max(3, longest + 1)
    marks = "~" * size
    return "%stext\n%s\n%s" % (marks, value, marks)


def table(headers, rows):
    output = [
        "| %s |" % " | ".join(headers),
        "| %s |" % " | ".join("---" for _ in headers),
    ]
    for row in rows:
        output.append("| %s |" % " | ".join(escape_table_cell(value) for value in row))
    return "\n".join(output)


def rendered(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def canonical_body(data, unfinished):
    video_rows = [[key, rendered(data["video"][key])] for key in VIDEO_KEYS]
    evidence_rows = [[key, data["evidence"][key] or "未提供"]
                     for key in EVIDENCE_ORDER]
    if data["evidence"]["rights"]:
        evidence_rows += [["rights[%d]" % i, value]
                          for i, value in enumerate(data["evidence"]["rights"])]
    else:
        evidence_rows += [["rights", "未提供"]]
    checks = [[name, data["manual_checks"][name]["status"],
               data["manual_checks"][name]["note"]] for name in CHECK_ORDER]
    credits = fenced(data["credits"]["text"]) if data["credits"]["text"] else "无需署名"
    unfinished_text = "无" if not unfinished else "\n".join(
        "- %s" % item for item in unfinished)
    return """## 发布状态

`{status}`

## 发布平台

`{platform}`

## 主标题

{title}

## 发布介绍

{introduction}

## 话题标签

{hashtags}

## 封面文字

{cover}

## 素材署名

{credits}

## 成片规格与 SHA-256

{video}

## 证据索引

{evidence}

## 发布前人工检查

{checks}

## 未完成事项

{unfinished}
""".format(
        status=data["publish_status"], platform=data["platform"],
        title=fenced(data["copy"]["primary_title"]),
        introduction=fenced(data["copy"]["introduction"]),
        hashtags=" ".join(data["copy"]["hashtags"]),
        cover=fenced("\n".join(data["cover"]["title_lines"])),
        credits=credits, video=table(("字段", "值"), video_rows),
        evidence=table(("字段", "路径"), evidence_rows),
        checks=table(("检查", "状态", "备注"), checks),
        unfinished=unfinished_text,
    )


def write_publish(path, data, unfinished):
    frontmatter = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    path.write_text("---\n%s---\n\n%s" %
                    (frontmatter, canonical_body(data, unfinished)), encoding="utf-8")


class PublishContractTests(unittest.TestCase):
    def setUp(self):
        self.template_data, self.template_body = parse_document(
            ROOT / "templates" / "publish.md")

    def test_template_parses_as_safe_yaml(self):
        self.assertEqual(1, self.template_data["schema_version"])
        self.assertEqual("basic_srt", self.template_data["workflow"])
        self.assertIn("## 发布状态", self.template_body)

    def test_template_passes_contract_without_project_files(self):
        validate_document(ROOT / "templates" / "publish.md",
                          project_root=ROOT, template_mode=True)

    def test_missing_top_level_key_fails(self):
        broken = deepcopy(self.template_data)
        del broken["copy"]
        with self.assertRaisesRegex(PublishValidationError, "document keys"):
            validate_schema(broken)

    def test_invalid_enums_fail(self):
        fields = (
            ("workflow", "other"),
            ("publish_status", "published"),
        )
        for field, value in fields:
            broken = deepcopy(self.template_data)
            broken[field] = value
            with self.subTest(field=field):
                with self.assertRaises(PublishValidationError):
                    validate_schema(broken)
        broken = deepcopy(self.template_data)
        broken["cover"]["source_type"] = "guess"
        with self.assertRaises(PublishValidationError):
            validate_schema(broken)

    def test_uppercase_or_short_hash_fails(self):
        for value in ("abc", "A" * 64):
            broken = deepcopy(self.template_data)
            broken["video"]["sha256"] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(PublishValidationError, "SHA-256"):
                    validate_schema(broken)

    def test_cover_line_count_and_duplicate_hashtags_fail(self):
        broken = deepcopy(self.template_data)
        broken["cover"]["title_lines"] = ["一行"]
        with self.assertRaisesRegex(PublishValidationError, "line_count"):
            validate_schema(broken)
        broken = deepcopy(self.template_data)
        broken["copy"]["hashtags"] = ["#MG", "#MG"]
        with self.assertRaisesRegex(PublishValidationError, "unique"):
            validate_schema(broken)

    def test_silent_video_requires_exact_listening_exemptions(self):
        broken = deepcopy(self.template_data)
        broken["manual_checks"]["headphones"] = {"status": "pending", "note": ""}
        with self.assertRaisesRegex(PublishValidationError, "no_audio_track"):
            validate_schema(broken)

    def test_audio_requires_specs_and_listening_checks(self):
        broken = deepcopy(self.template_data)
        broken["video"]["audio_codec"] = "aac"
        broken["manual_checks"]["headphones"] = {"status": "pending", "note": ""}
        broken["manual_checks"]["phone_speaker"] = {"status": "pending", "note": ""}
        with self.assertRaisesRegex(PublishValidationError, "sample_rate"):
            validate_schema(broken)

    def test_blocked_priority_over_draft_and_pending(self):
        data = deepcopy(self.template_data)
        data["video"]["replacement_in_progress"] = True
        items = derive_unfinished_items(data, final_exists=False)
        self.assertIn("cover_unconfirmed", items)
        self.assertIn("manual_check_pending:cover_preview", items)
        self.assertEqual("blocked", derive_publish_status(data, items))

    def test_credit_evidence_missing_is_contract_diagnostic(self):
        data = deepcopy(self.template_data)
        data["credits"] = {"required": True, "text": ""}
        validate_schema(data)
        items = derive_unfinished_items(data, final_exists=False)
        self.assertIn("credits_evidence_missing", items)
        self.assertEqual("blocked", derive_publish_status(data, items))

    def test_production_adds_required_evidence_in_matrix_order(self):
        data = deepcopy(self.template_data)
        data["workflow"] = "production"
        items = derive_unfinished_items(data, final_exists=False)
        missing = [item for item in items if item.startswith("evidence_missing:")]
        self.assertEqual([
            "evidence_missing:approval",
            "evidence_missing:machine_qc",
            "evidence_missing:visual_checklist",
            "evidence_missing:asset_ledger",
        ], missing)

    def test_status_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish.md"
            data = deepcopy(self.template_data)
            data["publish_status"] = "ready"
            unfinished = derive_unfinished_items(data, final_exists=False)
            write_publish(path, data, unfinished)
            with self.assertRaisesRegex(PublishValidationError, "publish_status"):
                validate_document(path, project_root=directory)

    def test_body_field_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish.md"
            data = deepcopy(self.template_data)
            unfinished = derive_unfinished_items(data, final_exists=False)
            write_publish(path, data, unfinished)
            raw = path.read_text(encoding="utf-8")
            path.write_text(raw.replace("`unspecified`", "`douyin`", 1),
                            encoding="utf-8")
            with self.assertRaisesRegex(PublishValidationError, "platform mismatch"):
                validate_document(path, project_root=directory)

    def test_unfinished_order_and_heading_order_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish.md"
            data = deepcopy(self.template_data)
            unfinished = derive_unfinished_items(data, final_exists=False)
            write_publish(path, data, list(reversed(unfinished)))
            with self.assertRaisesRegex(PublishValidationError, "unfinished"):
                validate_document(path, project_root=directory)
            write_publish(path, data, unfinished)
            raw = path.read_text(encoding="utf-8")
            raw = raw.replace("## 发布状态", "## 临时章节", 1)
            path.write_text(raw, encoding="utf-8")
            with self.assertRaisesRegex(PublishValidationError, "sections"):
                validate_document(path, project_root=directory)

    def test_secrets_are_rejected_anywhere(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "publish.md"
            raw = (ROOT / "templates" / "publish.md").read_text(encoding="utf-8")
            path.write_text(raw + "\nAuthorization: Bearer secret\n", encoding="utf-8")
            with self.assertRaisesRegex(PublishValidationError, "credential"):
                parse_document(path)

    def test_safe_path_rejects_absolute_parent_url_and_external_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ("/tmp/a", "../a", "https://example.com/a", "a?token=x"):
                with self.subTest(value=value):
                    with self.assertRaises(PublishValidationError):
                        safe_project_path(value, root, False, "test")
            external = Path(directory).parent / "outside-publish-contract"
            external.mkdir(exist_ok=True)
            link = root / "escape"
            link.symlink_to(external, target_is_directory=True)
            with self.assertRaisesRegex(PublishValidationError, "escapes"):
                safe_project_path("escape", root, True, "test")
            link.unlink()
            external.rmdir()

    def test_actual_undecodable_video_can_be_truthfully_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            final = root / "final.mp4"
            final.write_bytes(b"not a video")
            data = deepcopy(self.template_data)
            data["video"]["sha256"] = hashlib.sha256(b"not a video").hexdigest()
            data["publish_status"] = "blocked"
            diagnostics = ["final_video_undecodable"]
            unfinished = derive_unfinished_items(
                data, diagnostics=diagnostics, final_exists=True)
            write_publish(root / "publish.md", data, unfinished)
            validated = validate_document(root / "publish.md", project_root=root)
            self.assertEqual("blocked", validated["publish_status"])

    @unittest.skipUnless(
        subprocess.run(["sh", "-c", "command -v ffmpeg >/dev/null"]).returncode == 0,
        "ffmpeg is required",
    )
    def test_actual_video_hash_mismatch_requires_blocked_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=black:s=16x16:r=30:d=0.1", "-c:v", "libx264",
                "-pix_fmt", "yuv420p", "-an", str(root / "final.mp4"),
            ], check=True)
            data = deepcopy(self.template_data)
            data["video"].update({
                "sha256": "0" * 64,
                "duration_seconds": 0.1,
                "width_px": 16,
                "height_px": 16,
                "fps": 30,
                "video_codec": "h264",
                "pixel_format": "yuv420p",
            })
            data["publish_status"] = "blocked"
            unfinished = derive_unfinished_items(
                data, diagnostics=["video_hash_mismatch"], final_exists=True)
            write_publish(root / "publish.md", data, unfinished)
            validated = validate_document(root / "publish.md", project_root=root)
            self.assertEqual("blocked", validated["publish_status"])

    def test_malformed_approval_structure_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "approval.json").write_text(json.dumps({}), encoding="utf-8")
            data = deepcopy(self.template_data)
            data["workflow"] = "production"
            data["evidence"]["approval"] = "approval.json"
            unfinished = derive_unfinished_items(data, final_exists=False)
            write_publish(root / "publish.md", data, unfinished)
            with self.assertRaisesRegex(PublishValidationError,
                                        "expected_delivery"):
                validate_document(root / "publish.md", project_root=root)

    def test_missing_final_rejects_stale_video_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = deepcopy(self.template_data)
            data["video"]["sha256"] = "0" * 64
            unfinished = derive_unfinished_items(data, final_exists=False)
            write_publish(root / "publish.md", data, unfinished)
            with self.assertRaisesRegex(PublishValidationError,
                                        "must be empty"):
                validate_document(root / "publish.md", project_root=root)


if __name__ == "__main__":
    unittest.main()
