#!/usr/bin/env python3

from pathlib import Path
import re
import struct
import sys

import yaml


ARCHETYPE_IDS = (
    "proposition",
    "comparison",
    "process",
    "capability_deck",
)

REQUIRED_KEYS = (
    "schema_version",
    "style_id",
    "style_name",
    "scope",
    "canvas",
    "safe_area",
    "colors",
    "typography",
    "spacing",
    "radius",
    "scene_archetypes",
    "motion",
    "audio",
    "subtitles",
    "cover",
    "forbidden",
)

SAFE_AREA_KEYS = (
    "structural",
    "main_content",
    "critical_text",
    "cover_title",
    "subtitles",
)

HEX_RE = re.compile(r"^#[0-9A-F]{6}$")


class StyleGuideValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise StyleGuideValidationError(message)


def parse_frontmatter(path):
    path = Path(path)
    require(path.is_file(), f"missing document: {path}")
    text = path.read_text(encoding="utf-8")
    require(text.startswith("---\n"), f"missing YAML frontmatter: {path}")
    closing = text.find("\n---\n", 4)
    require(closing != -1, f"unterminated YAML frontmatter: {path}")
    data = yaml.safe_load(text[4:closing])
    require(isinstance(data, dict), f"frontmatter must be a mapping: {path}")
    return data


def validate_box(box, name):
    require(isinstance(box, dict), f"{name} must be an object")
    for key in ("left_px", "right_px", "top_px", "bottom_px"):
        require(key in box, f"{name}.{key} is required")
        require(
            isinstance(box[key], int) and box[key] >= 0,
            f"{name}.{key} must be a non-negative integer",
        )


def validate_numeric_map(mapping, name, minimum=0):
    require(isinstance(mapping, dict), f"{name} must be an object")
    for key, value in mapping.items():
        require(
            isinstance(value, (int, float)) and value >= minimum,
            f"{name}.{key} must be numeric and >= {minimum}",
        )


def validate_schema(tokens):
    require(isinstance(tokens, dict), "tokens must be an object")
    for key in REQUIRED_KEYS:
        require(key in tokens, f"missing required key: {key}")

    require(tokens["schema_version"] == 1, "schema_version must be 1")
    require(isinstance(tokens["style_id"], str), "style_id must be a string")
    require(isinstance(tokens["style_name"], str), "style_name must be a string")
    require(isinstance(tokens["scope"], list) and tokens["scope"], "scope must be a list")

    canvas = tokens["canvas"]
    require(canvas["width_px"] == 1080, "canvas.width_px must be 1080")
    require(canvas["height_px"] == 1440, "canvas.height_px must be 1440")
    require(canvas["fps"] == 30, "canvas.fps must be 30")
    require(canvas["orientation"] == "vertical", "canvas.orientation must be vertical")

    safe_area = tokens["safe_area"]
    require(isinstance(safe_area, dict), "safe_area must be an object")
    for key in SAFE_AREA_KEYS:
        require(key in safe_area, f"safe_area.{key} is required")
        validate_box(safe_area[key], f"safe_area.{key}")

    colors = tokens["colors"]
    require(isinstance(colors, dict) and colors, "colors must be a non-empty object")
    for key, value in colors.items():
        require(isinstance(value, str) and HEX_RE.fullmatch(value), f"invalid HEX: colors.{key}")

    typography = tokens["typography"]
    require(isinstance(typography, dict), "typography must be an object")
    for key in ("primary_stack", "mono_stack", "sizes_px", "weights", "line_heights"):
        require(key in typography, f"typography.{key} is required")
    validate_numeric_map(typography["sizes_px"], "typography.sizes_px", minimum=1)
    validate_numeric_map(typography["weights"], "typography.weights", minimum=1)
    validate_numeric_map(typography["line_heights"], "typography.line_heights", minimum=0.5)

    validate_numeric_map(tokens["spacing"], "spacing")
    validate_numeric_map(tokens["radius"], "radius")
    require(tokens["radius"]["pill_px"] == 999, "radius.pill_px must be 999")

    archetypes = tokens["scene_archetypes"]
    require(isinstance(archetypes, list), "scene_archetypes must be a list")
    ids = [item.get("id") for item in archetypes if isinstance(item, dict)]
    require(ids == list(ARCHETYPE_IDS), "scene_archetypes must use the four canonical IDs")
    for item in archetypes:
        require(isinstance(item.get("name"), str), "archetype name must be a string")
        require(isinstance(item.get("example_png"), str), "archetype example_png is required")

    motion = tokens["motion"]
    for key in (
        "phases",
        "entrance_seconds",
        "exit_seconds",
        "transition_seconds",
        "entrance_ease",
        "exit_ease",
        "verbs",
    ):
        require(key in motion, f"motion.{key} is required")
    validate_numeric_map(motion["phases"], "motion.phases")
    require(
        abs(sum(motion["phases"].values()) - 1.0) < 1e-6,
        "motion phases must sum to 1.0",
    )

    audio = tokens["audio"]
    for key in (
        "sample_rate_hz",
        "channels",
        "final_integrated_lufs",
        "final_lufs_tolerance",
        "true_peak_max_dbtp",
        "bgm_ducking_db",
        "bgm_fade_seconds",
        "sfx_max_simultaneous",
    ):
        require(key in audio, f"audio.{key} is required")
    require(audio["sample_rate_hz"] == 48000, "audio.sample_rate_hz must be 48000")
    require(audio["channels"] == 2, "audio.channels must be 2")

    subtitles = tokens["subtitles"]
    for key in (
        "required",
        "font_size_px",
        "max_lines",
        "max_fullwidth_chars_per_line",
        "line_height",
        "background",
        "text_color",
        "padding_px",
        "radius_px",
        "break_rules",
    ):
        require(key in subtitles, f"subtitles.{key} is required")

    cover = tokens["cover"]
    for key in (
        "frame_zero_complete",
        "default_lines",
        "max_lines",
        "font_size_px",
        "max_width_px",
        "contrast_ratio_min",
        "stable_frames",
    ):
        require(key in cover, f"cover.{key} is required")
    require(cover["frame_zero_complete"] is True, "cover.frame_zero_complete must be true")
    require(cover["stable_frames"] >= 18, "cover.stable_frames must be >= 18")

    forbidden = tokens["forbidden"]
    require(
        isinstance(forbidden, list)
        and forbidden
        and all(isinstance(item, str) for item in forbidden),
        "forbidden must be a non-empty string list",
    )


def compare_tokens(frame_tokens, guide_tokens):
    require(frame_tokens == guide_tokens, "frame.md and human guide tokens differ")


def png_dimensions(path):
    with Path(path).open("rb") as handle:
        header = handle.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}")
    return struct.unpack(">II", header[16:24])


def validate_examples(tokens, project_root):
    project_root = Path(project_root)
    for item in tokens["scene_archetypes"]:
        example_path = project_root / item["example_png"]
        require(example_path.is_file(), f"missing example: {example_path}")
        require(
            png_dimensions(example_path) == (1080, 1440),
            f"example must be 1080x1440: {example_path}",
        )


def validate_all(project_root):
    project_root = Path(project_root)
    frame_tokens = parse_frontmatter(project_root / "frame.md")
    guide_tokens = parse_frontmatter(
        project_root / "docs" / "清晰系统蓝图-视频风格说明书.md"
    )
    validate_schema(frame_tokens)
    validate_schema(guide_tokens)
    compare_tokens(frame_tokens, guide_tokens)
    validate_examples(frame_tokens, project_root)
    return frame_tokens


def main():
    try:
        validate_all(Path.cwd())
    except (StyleGuideValidationError, KeyError, TypeError, yaml.YAMLError) as error:
        print(f"style guide validation failed: {error}", file=sys.stderr)
        return 1
    print("style guide validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
