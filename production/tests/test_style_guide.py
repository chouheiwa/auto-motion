from pathlib import Path
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from production.tools.validate_style_guide import (  # noqa: E402
    ARCHETYPE_IDS,
    compare_tokens,
    parse_frontmatter,
    validate_all,
    validate_examples,
    validate_schema,
)


class StyleGuideValidationTests(unittest.TestCase):
    def setUp(self):
        self.frame_path = PROJECT_ROOT / "frame.md"
        self.guide_path = PROJECT_ROOT / "docs" / "清晰系统蓝图-视频风格说明书.md"

    def test_required_documents_exist(self):
        self.assertTrue(self.frame_path.is_file())
        self.assertTrue(self.guide_path.is_file())

    def test_frontmatter_parses_and_matches(self):
        frame_tokens = parse_frontmatter(self.frame_path)
        guide_tokens = parse_frontmatter(self.guide_path)
        validate_schema(frame_tokens)
        validate_schema(guide_tokens)
        compare_tokens(frame_tokens, guide_tokens)

    def test_motion_phases_sum_to_one(self):
        tokens = parse_frontmatter(self.frame_path)
        phases = tokens["motion"]["phases"]
        self.assertAlmostEqual(
            phases["build"] + phases["breathe"] + phases["resolve"],
            1.0,
            places=6,
        )

    def test_four_archetype_examples_are_1080_by_1440(self):
        tokens = parse_frontmatter(self.frame_path)
        self.assertEqual(
            [item["id"] for item in tokens["scene_archetypes"]],
            list(ARCHETYPE_IDS),
        )
        validate_examples(tokens, PROJECT_ROOT)

    def test_full_validation(self):
        validate_all(PROJECT_ROOT)


if __name__ == "__main__":
    unittest.main()
