#!/usr/bin/env python3
"""Read-only validator for the publish.md delivery contract."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import yaml


class PublishValidationError(ValueError):
    pass


WORKFLOWS = {"production", "basic_srt"}
PUBLISH_STATUSES = {"draft", "pending_manual_checks", "blocked", "ready"}
CHECK_STATUSES = {"pending", "passed", "failed", "not_applicable"}
COVER_SOURCE_TYPES = {
    "confirmed_config", "detected_frame_zero",
    "generated_candidate", "unconfirmed",
}
CHECK_ORDER = ("headphones", "phone_speaker", "cover_preview", "rights_confirmed")
EVIDENCE_ORDER = (
    "approval", "machine_qc", "visual_checklist",
    "sound_checklist", "asset_ledger",
)
REQUIRED_SECTIONS = (
    "发布状态", "发布平台", "主标题", "发布介绍", "话题标签", "封面文字",
    "素材署名", "成片规格与 SHA-256", "证据索引", "发布前人工检查",
    "未完成事项",
)
VIDEO_KEYS = (
    "path", "sha256", "duration_seconds", "width_px", "height_px", "fps",
    "video_codec", "pixel_format", "replacement_in_progress", "audio_codec",
    "audio_sample_rate_hz", "audio_channels",
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ISO8601_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b", re.I),
    re.compile(r"\bAuthorization\s*:", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]+", re.I),
    re.compile(r"\bCookie\s*:", re.I),
    re.compile(r"[?&](?:token|signature|sig|api_key|key)=", re.I),
)


def require(condition, message):
    if not condition:
        raise PublishValidationError(message)


def _exact_keys(value, expected, name):
    require(isinstance(value, dict), "%s must be a mapping" % name)
    expected = set(expected)
    require(set(value) == expected, "%s keys must be exactly %s" %
            (name, ", ".join(sorted(expected))))


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_document(path):
    raw = Path(path).read_text(encoding="utf-8")
    validate_no_secrets(raw)
    require(raw.startswith("---\n"), "frontmatter must start at byte zero")
    marker = raw.find("\n---\n", 4)
    require(marker >= 0, "frontmatter closing delimiter is missing")
    data = yaml.safe_load(raw[4:marker])
    require(isinstance(data, dict), "frontmatter must be a mapping")
    return data, raw[marker + 5:]


def validate_no_secrets(raw_text):
    for pattern in SECRET_PATTERNS:
        require(not pattern.search(raw_text), "credential-like content is forbidden")


def validate_schema(data, template_mode=False):
    _exact_keys(data, (
        "schema_version", "workflow", "publish_status", "platform",
        "generated_at", "video", "cover", "copy", "credits",
        "manual_checks", "evidence",
    ), "document")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "schema_version must be integer 1")
    require(data["workflow"] in WORKFLOWS, "invalid workflow")
    require(data["publish_status"] in PUBLISH_STATUSES, "invalid publish_status")
    require(isinstance(data["platform"], str) and data["platform"],
            "platform must be a non-empty string")
    require(isinstance(data["generated_at"], str) and
            ISO8601_RE.match(data["generated_at"]), "invalid generated_at")

    video = data["video"]
    _exact_keys(video, VIDEO_KEYS, "video")
    require(video["path"] == "final.mp4", "video.path must equal final.mp4")
    require(isinstance(video["sha256"], str), "video.sha256 must be a string")
    require(not video["sha256"] or SHA256_RE.match(video["sha256"]),
            "video.sha256 must be lowercase SHA-256")
    for key in ("duration_seconds", "width_px", "height_px", "fps",
                "audio_sample_rate_hz", "audio_channels"):
        require(video[key] is None or
                (_is_number(video[key]) and video[key] > 0),
                "%s must be positive or null" % key)
    for key in ("video_codec", "pixel_format", "audio_codec"):
        require(isinstance(video[key], str), "%s must be a string" % key)
    require(type(video["replacement_in_progress"]) is bool,
            "replacement_in_progress must be boolean")

    cover = data["cover"]
    _exact_keys(cover, (
        "title_lines", "line_count", "frame", "source_type", "source_path",
    ), "cover")
    require(isinstance(cover["title_lines"], list) and
            all(isinstance(x, str) for x in cover["title_lines"]),
            "cover.title_lines must be a string list")
    require(type(cover["line_count"]) is int and
            cover["line_count"] == len(cover["title_lines"]),
            "cover.line_count must equal title_lines length")
    require(type(cover["frame"]) is int and cover["frame"] == 0,
            "cover.frame must be integer 0")
    require(cover["source_type"] in COVER_SOURCE_TYPES,
            "invalid cover.source_type")
    require(isinstance(cover["source_path"], str),
            "cover.source_path must be a string")
    if cover["source_type"] != "confirmed_config":
        require(not cover["source_path"],
                "only confirmed_config may have cover.source_path")
    elif not template_mode:
        require(bool(cover["source_path"]),
                "confirmed_config requires cover.source_path")

    copy = data["copy"]
    _exact_keys(copy, ("primary_title", "introduction", "hashtags"), "copy")
    require(isinstance(copy["primary_title"], str), "primary_title must be a string")
    require(isinstance(copy["introduction"], str), "introduction must be a string")
    require(isinstance(copy["hashtags"], list) and
            all(isinstance(x, str) and x for x in copy["hashtags"]),
            "hashtags must be a list of non-empty strings")
    require(len(copy["hashtags"]) == len(set(copy["hashtags"])),
            "hashtags must be unique")

    credits = data["credits"]
    _exact_keys(credits, ("required", "text"), "credits")
    require(type(credits["required"]) is bool, "credits.required must be boolean")
    require(isinstance(credits["text"], str), "credits.text must be a string")

    checks = data["manual_checks"]
    _exact_keys(checks, CHECK_ORDER, "manual_checks")
    for name in CHECK_ORDER:
        _exact_keys(checks[name], ("status", "note"),
                    "manual_checks.%s" % name)
        require(checks[name]["status"] in CHECK_STATUSES,
                "invalid manual check status")
        require(isinstance(checks[name]["note"], str),
                "manual check note must be a string")
        if checks[name]["status"] == "not_applicable":
            require(bool(checks[name]["note"]),
                    "not_applicable requires a note")

    evidence = data["evidence"]
    _exact_keys(evidence, EVIDENCE_ORDER + ("rights",), "evidence")
    for key in EVIDENCE_ORDER:
        require(isinstance(evidence[key], str),
                "evidence.%s must be a string" % key)
    require(isinstance(evidence["rights"], list) and
            all(isinstance(x, str) for x in evidence["rights"]),
            "evidence.rights must be a string list")

    has_audio = video["audio_codec"] != "none"
    if has_audio:
        require(bool(video["audio_codec"]), "audio_codec is required")
        require(video["audio_sample_rate_hz"] is not None,
                "audio_sample_rate_hz is required with audio")
        require(video["audio_channels"] is not None,
                "audio_channels is required with audio")
        for name in ("headphones", "phone_speaker"):
            require(checks[name]["status"] != "not_applicable",
                    "%s applies when audio exists" % name)
    else:
        require(video["audio_sample_rate_hz"] is None and
                video["audio_channels"] is None,
                "silent video audio values must be null")
        for name in ("headphones", "phone_speaker"):
            require(checks[name] == {
                "status": "not_applicable", "note": "no_audio_track",
            }, "%s must use no_audio_track exemption" % name)


def safe_project_path(value, project_root, must_exist, field_name):
    require(isinstance(value, str) and value, "%s path is empty" % field_name)
    require(SAFE_PATH_RE.match(value) is not None, "%s path is unsafe" % field_name)
    posix = Path(value)
    require(not posix.is_absolute() and ".." not in posix.parts,
            "%s path must be project-relative" % field_name)
    root = Path(project_root).resolve()
    resolved = (root / posix).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise PublishValidationError("%s path escapes project root" % field_name)
    if must_exist:
        require(resolved.exists(), "%s path does not exist" % field_name)
    return resolved


def validate_evidence_paths(data, project_root, template_mode=False):
    if template_mode:
        return
    for key in EVIDENCE_ORDER:
        value = data["evidence"][key]
        if value:
            safe_project_path(value, project_root, True, "evidence.%s" % key)
    for index, value in enumerate(data["evidence"]["rights"]):
        safe_project_path(value, project_root, True, "evidence.rights[%d]" % index)
    if data["cover"]["source_path"]:
        safe_project_path(data["cover"]["source_path"], project_root, True,
                          "cover.source_path")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video_metadata(path):
    command = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,"
        "r_frame_rate,sample_rate,channels",
        "-of", "json", str(path),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    require(result.returncode == 0, "ffprobe failed")
    payload = json.loads(result.stdout)
    video_streams = [s for s in payload.get("streams", [])
                     if s.get("codec_type") == "video"]
    require(video_streams, "final video has no video stream")
    stream = video_streams[0]
    audio_streams = [s for s in payload.get("streams", [])
                     if s.get("codec_type") == "audio"]
    fps = float(Fraction(stream["r_frame_rate"]))
    meta = {
        "duration_seconds": float(payload["format"]["duration"]),
        "width_px": int(stream["width"]),
        "height_px": int(stream["height"]),
        "fps": fps,
        "video_codec": stream["codec_name"],
        "pixel_format": stream["pix_fmt"],
        "audio_codec": "none",
        "audio_sample_rate_hz": None,
        "audio_channels": None,
    }
    if audio_streams:
        audio = audio_streams[0]
        meta.update({
            "audio_codec": audio["codec_name"],
            "audio_sample_rate_hz": int(audio["sample_rate"]),
            "audio_channels": int(audio["channels"]),
        })
    return meta


def decode_video(path):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def load_approval(data, project_root):
    if data["workflow"] != "production" or not data["evidence"]["approval"]:
        return None
    approval_path = safe_project_path(
        data["evidence"]["approval"], project_root, True, "evidence.approval")
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise PublishValidationError("approval JSON is invalid: %s" % exc)
    require(isinstance(approval, dict), "approval must be a mapping")
    expected = approval.get("expected_delivery")
    require(isinstance(expected, dict), "approval.expected_delivery is required")
    require(expected.get("path") == "final.mp4",
            "approval expected_delivery.path must equal final.mp4")
    expected_hash = expected.get("sha256")
    require(isinstance(expected_hash, str) and SHA256_RE.match(expected_hash),
            "approval expected_delivery.sha256 is invalid")
    verification = approval.get("delivery_verification")
    if verification is not None:
        require(isinstance(verification, dict),
                "approval.delivery_verification must be a mapping")
        verified_hash = verification.get("actual_sha256")
        require(isinstance(verified_hash, str) and SHA256_RE.match(verified_hash),
                "delivery_verification.actual_sha256 is invalid")
    return approval


def _matches_metadata(video, actual):
    for key in ("width_px", "height_px", "video_codec", "pixel_format",
                "audio_codec", "audio_sample_rate_hz", "audio_channels"):
        if video[key] != actual[key]:
            return False
    if video["fps"] is None or abs(float(video["fps"]) - actual["fps"]) > 0.001:
        return False
    if video["duration_seconds"] is None:
        return False
    return abs(float(video["duration_seconds"]) -
               actual["duration_seconds"]) <= 1.0 / actual["fps"]


def collect_filesystem_diagnostics(data, project_root, template_mode=False,
                                   approval=None):
    if template_mode:
        return []
    final_path = Path(project_root) / "final.mp4"
    if not final_path.exists():
        return []
    diagnostics = []
    actual_hash = sha256_file(final_path)
    if data["video"]["sha256"] != actual_hash:
        diagnostics.append("video_hash_mismatch")
    if not decode_video(final_path):
        diagnostics.insert(0, "final_video_undecodable")
        return diagnostics
    try:
        actual = probe_video_metadata(final_path)
    except (PublishValidationError, KeyError, ValueError, json.JSONDecodeError):
        diagnostics.insert(0, "final_video_undecodable")
        return diagnostics
    if not _matches_metadata(data["video"], actual):
        diagnostics.append("video_spec_mismatch")
    if approval is not None:
        expected_hash = approval["expected_delivery"]["sha256"]
        verification = approval.get("delivery_verification")
        actual_values = [actual_hash, data["video"]["sha256"]]
        if expected_hash not in actual_values or len(set(actual_values + [expected_hash])) != 1:
            diagnostics.append("approval_hash_mismatch")
        if verification is not None:
            require(isinstance(verification, dict),
                    "approval.delivery_verification must be a mapping")
            verified_hash = verification.get("actual_sha256")
            require(isinstance(verified_hash, str) and SHA256_RE.match(verified_hash),
                    "delivery_verification.actual_sha256 is invalid")
            if verified_hash != actual_hash:
                if "approval_hash_mismatch" not in diagnostics:
                    diagnostics.append("approval_hash_mismatch")
    return diagnostics


def derive_unfinished_items(data, diagnostics=None, template_mode=False,
                            final_exists=None):
    diagnostics = diagnostics or []
    items = []
    if data["video"]["replacement_in_progress"]:
        items.append("video_replacement_in_progress")
    for code in ("final_video_undecodable", "video_hash_mismatch",
                 "video_spec_mismatch", "approval_hash_mismatch"):
        if code in diagnostics:
            items.append(code)
    for name in CHECK_ORDER:
        if data["manual_checks"][name]["status"] == "failed":
            items.append("manual_check_failed:%s" % name)
    if data["credits"]["required"] and (
            not data["credits"]["text"] or not data["evidence"]["rights"]):
        items.append("credits_evidence_missing")
    if final_exists is None:
        final_exists = bool(data["video"]["sha256"])
    if not final_exists:
        items.append("final_video_missing")
    if data["platform"] == "unspecified":
        items.append("platform_unconfirmed")
    if not data["copy"]["primary_title"]:
        items.append("primary_title_missing")
    if not data["copy"]["introduction"]:
        items.append("introduction_missing")
    if not data["copy"]["hashtags"]:
        items.append("hashtags_missing")
    if data["cover"]["source_type"] in ("generated_candidate", "unconfirmed"):
        items.append("cover_unconfirmed")
    if data["workflow"] == "production":
        required = ["approval", "machine_qc", "visual_checklist"]
        if data["video"]["audio_codec"] != "none":
            required.append("sound_checklist")
        required.append("asset_ledger")
        for field in EVIDENCE_ORDER:
            if field in required and not data["evidence"][field]:
                items.append("evidence_missing:%s" % field)
    for name in CHECK_ORDER:
        if data["manual_checks"][name]["status"] == "pending":
            items.append("manual_check_pending:%s" % name)
    return items


def derive_publish_status(data, unfinished_items):
    blocked = (
        "video_replacement_in_progress", "final_video_undecodable",
        "video_hash_mismatch", "video_spec_mismatch", "approval_hash_mismatch",
        "credits_evidence_missing",
    )
    if any(item in blocked or item.startswith("manual_check_failed:")
           for item in unfinished_items):
        return "blocked"
    if any(item == "final_video_missing" or item.endswith("_missing") or
           item in ("platform_unconfirmed", "cover_unconfirmed") or
           item.startswith("evidence_missing:")
           for item in unfinished_items):
        return "draft"
    if any(item.startswith("manual_check_pending:")
           for item in unfinished_items):
        return "pending_manual_checks"
    return "ready"


def escape_table_cell(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("|", "\\|")


def unescape_table_cell(value):
    output = []
    index = 0
    while index < len(value):
        if value[index] != "\\":
            output.append(value[index])
            index += 1
            continue
        require(index + 1 < len(value), "dangling table escape")
        char = value[index + 1]
        require(char in ("\\", "n", "|"), "unknown table escape")
        output.append("\n" if char == "n" else char)
        index += 2
    return "".join(output)


def parse_sections(body):
    matches = list(re.finditer(r"(?m)^## ([^\n]+)\n", body))
    names = [match.group(1) for match in matches]
    require(len(names) == len(set(names)), "duplicate Markdown section")
    require(tuple(names[:len(REQUIRED_SECTIONS)]) == REQUIRED_SECTIONS,
            "required Markdown sections are missing or reordered")
    require(len(names) in (len(REQUIRED_SECTIONS), len(REQUIRED_SECTIONS) + 1),
            "unexpected Markdown section")
    if len(names) > len(REQUIRED_SECTIONS):
        require(names[-1] == "备选文案", "only 备选文案 may follow required sections")
    sections = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        sections[match.group(1)] = body[match.end():end].strip("\n")
    return sections


def parse_inline_code_scalar(section, name):
    match = re.fullmatch(r"\s*`([^`\n]*)`\s*", section)
    require(match is not None, "%s must be one inline-code scalar" % name)
    return match.group(1)


def _canonical_fence_length(payload):
    runs = [len(match.group(0)) for match in re.finditer(r"~+", payload)]
    return max(3, (max(runs) + 1) if runs else 3)


def parse_fenced_text(section, name):
    value = section.strip("\n")
    lines = value.split("\n")
    require(len(lines) >= 2, "%s must be a fenced text block" % name)
    opening = re.fullmatch(r"(~{3,})text", lines[0])
    require(opening is not None and lines[-1] == opening.group(1),
            "%s has invalid text fence" % name)
    payload = "\n".join(lines[1:-1])
    require(len(opening.group(1)) == _canonical_fence_length(payload),
            "%s fence is not minimal" % name)
    return payload


def _split_table_row(line):
    require(line.startswith("|") and line.endswith("|"), "malformed Markdown table row")
    cells, current, escaped = [], [], False
    for char in line[1:-1]:
        if escaped:
            current.extend(("\\", char))
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append(unescape_table_cell("".join(current).strip()))
            current = []
        else:
            current.append(char)
    require(not escaped, "dangling table escape")
    cells.append(unescape_table_cell("".join(current).strip()))
    return cells


def parse_markdown_table(section, name, columns):
    lines = [line for line in section.strip().splitlines() if line.strip()]
    require(len(lines) >= 2, "%s table is incomplete" % name)
    require(_split_table_row(lines[0]) == list(columns), "%s table header mismatch" % name)
    separator = _split_table_row(lines[1])
    require(len(separator) == len(columns) and
            all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator),
            "%s table separator mismatch" % name)
    return [_split_table_row(line) for line in lines[2:]]


def _render_value(value):
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def validate_body_consistency(data, body, unfinished_items):
    sections = parse_sections(body)
    require(parse_inline_code_scalar(sections["发布状态"], "发布状态") ==
            data["publish_status"], "Markdown publish status mismatch")
    require(parse_inline_code_scalar(sections["发布平台"], "发布平台") ==
            data["platform"], "Markdown platform mismatch")
    require(parse_fenced_text(sections["主标题"], "主标题") ==
            data["copy"]["primary_title"], "Markdown title mismatch")
    require(parse_fenced_text(sections["发布介绍"], "发布介绍") ==
            data["copy"]["introduction"], "Markdown introduction mismatch")
    require(sections["话题标签"].strip() == " ".join(data["copy"]["hashtags"]),
            "Markdown hashtags mismatch")
    require(parse_fenced_text(sections["封面文字"], "封面文字") ==
            "\n".join(data["cover"]["title_lines"]), "Markdown cover mismatch")
    if data["credits"]["text"]:
        require(parse_fenced_text(sections["素材署名"], "素材署名") ==
                data["credits"]["text"], "Markdown credits mismatch")
    else:
        require(sections["素材署名"].strip() == "无需署名",
                "Markdown credits fallback mismatch")

    video_rows = parse_markdown_table(
        sections["成片规格与 SHA-256"], "成片规格与 SHA-256", ("字段", "值"))
    require(video_rows == [[key, _render_value(data["video"][key])]
                           for key in VIDEO_KEYS], "Markdown video table mismatch")

    evidence_rows = parse_markdown_table(
        sections["证据索引"], "证据索引", ("字段", "路径"))
    expected_evidence = [[key, data["evidence"][key] or "未提供"]
                         for key in EVIDENCE_ORDER]
    if data["evidence"]["rights"]:
        expected_evidence.extend([
            ["rights[%d]" % index, value]
            for index, value in enumerate(data["evidence"]["rights"])
        ])
    else:
        expected_evidence.append(["rights", "未提供"])
    require(evidence_rows == expected_evidence, "Markdown evidence table mismatch")

    check_rows = parse_markdown_table(
        sections["发布前人工检查"], "发布前人工检查", ("检查", "状态", "备注"))
    expected_checks = [[name, data["manual_checks"][name]["status"],
                        data["manual_checks"][name]["note"]]
                       for name in CHECK_ORDER]
    require(check_rows == expected_checks, "Markdown manual check table mismatch")
    unfinished_section = sections["未完成事项"].strip()
    actual_items = [] if unfinished_section == "无" else [
        line[2:] for line in unfinished_section.splitlines()
        if line.startswith("- ")
    ]
    require((unfinished_section == "无" or
             len(actual_items) == len(unfinished_section.splitlines())),
            "unfinished items must be an exact Markdown list")
    require(actual_items == unfinished_items, "unfinished item list mismatch")


def validate_document(path, project_root=None, template_mode=False):
    data, body = parse_document(path)
    validate_schema(data, template_mode=template_mode)
    root = Path(project_root) if project_root is not None else Path(path).parent
    validate_evidence_paths(data, root, template_mode=template_mode)
    approval = None if template_mode else load_approval(data, root)
    final_exists = False if template_mode else (root / "final.mp4").exists()
    if not final_exists and not template_mode:
        video = data["video"]
        require(not video["sha256"] and video["duration_seconds"] is None and
                video["width_px"] is None and video["height_px"] is None and
                video["fps"] is None and not video["video_codec"] and
                not video["pixel_format"],
                "video fields must be empty when final.mp4 is missing")
    diagnostics = collect_filesystem_diagnostics(
        data, root, template_mode=template_mode, approval=approval)
    unfinished = derive_unfinished_items(
        data, diagnostics=diagnostics, template_mode=template_mode,
        final_exists=final_exists)
    derived = derive_publish_status(data, unfinished)
    require(data["publish_status"] == derived,
            "publish_status must be %s, got %s" %
            (derived, data["publish_status"]))
    validate_body_consistency(data, body, unfinished)
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--project-root")
    parser.add_argument("--template", action="store_true")
    args = parser.parse_args(argv)
    try:
        data = validate_document(
            args.path, project_root=args.project_root, template_mode=args.template)
    except (PublishValidationError, OSError, ValueError, TypeError,
            yaml.YAMLError, json.JSONDecodeError) as exc:
        print("publish validation failed: %s" % exc, file=sys.stderr)
        return 1
    print("publish validation passed: %s (%s)" %
          (args.path, data["publish_status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
