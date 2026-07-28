#!/usr/bin/env python3

from pathlib import Path
import shutil
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from production.tools.validate_style_guide import parse_frontmatter  # noqa: E402


def common_svg(tokens, title, chapter, body):
    colors = tokens["colors"]
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">
  <defs>
    <pattern id="grid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M 60 0 L 0 0 0 60" fill="none" stroke="{colors['engineering_blue']}" stroke-opacity="0.055" stroke-width="1"/>
    </pattern>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%">
      <feDropShadow dx="0" dy="16" stdDeviation="18" flood-color="{colors['ink']}" flood-opacity="0.07"/>
    </filter>
  </defs>
  <rect width="1080" height="1440" fill="{colors['canvas']}"/>
  <rect width="1080" height="1440" fill="url(#grid)"/>
  <ellipse cx="540" cy="1450" rx="620" ry="420" fill="{colors['blue_tint']}" opacity="0.72"/>
  <g fill="none" stroke="{colors['structure_line_strong']}" stroke-width="2">
    <path d="M40 140v-44h44 M996 96h44v44 M40 1340v40h44 M996 1380h44v-40"/>
  </g>
  <g font-family="Inter, Hiragino Sans GB, PingFang SC, sans-serif">
    <circle cx="96" cy="137" r="7.5" fill="{colors['engineering_blue']}"/>
    <text x="117" y="148" fill="{colors['engineering_blue']}" font-size="30" font-weight="700" letter-spacing="4">{chapter}</text>
    <text x="992" y="146" text-anchor="end" fill="{colors['support_gray']}" font-size="19" font-family="JetBrains Mono, monospace" letter-spacing="3">{title}</text>
    <rect x="88" y="180" width="904" height="2" fill="{colors['structure_line']}"/>
    <rect x="88" y="180" width="330" height="2" fill="{colors['engineering_blue']}"/>
  </g>
  {body}
</svg>
"""


def proposition(tokens):
    c = tokens["colors"]
    body = f"""
  <g font-family="Inter, Hiragino Sans GB, PingFang SC, sans-serif">
    <rect x="88" y="294" width="154" height="48" rx="24" fill="{c['engineering_blue']}"/>
    <text x="165" y="327" text-anchor="middle" fill="{c['white']}" font-size="21" font-weight="700" letter-spacing="3">核心命题</text>
    <text x="88" y="480" fill="{c['ink']}" font-size="92" font-weight="900" letter-spacing="-2">复杂系统</text>
    <text x="88" y="586" fill="{c['ink']}" font-size="92" font-weight="900" letter-spacing="-2">到底怎么</text>
    <text x="88" y="692" fill="{c['engineering_blue']}" font-size="92" font-weight="900" letter-spacing="-2">运转？</text>
    <rect x="88" y="750" width="76" height="5" rx="2.5" fill="{c['engineering_blue']}"/>
    <text x="88" y="820" fill="{c['support_gray']}" font-size="28" font-weight="400">先提出冲突，再展示这条视频要验证的机制。</text>
    <g transform="translate(88 980)">
      <rect width="812" height="154" rx="18" fill="{c['white']}" stroke="{c['structure_line']}" stroke-width="2"/>
      <text x="30" y="47" fill="{c['support_gray']}" font-size="19" font-family="JetBrains Mono, monospace" letter-spacing="3">QUESTION → STRUCTURE → ANSWER</text>
      <rect x="30" y="76" width="752" height="16" rx="8" fill="{c['blue_tint']}"/>
      <rect x="30" y="76" width="430" height="16" rx="8" fill="{c['engineering_blue']}"/>
      <text x="30" y="126" fill="{c['ink']}" font-size="25" font-weight="600">封面即完成态，稳定 18 帧后再转场</text>
    </g>
  </g>"""
    return common_svg(tokens, "PROPOSITION", "命题型", body)


def comparison(tokens):
    c = tokens["colors"]

    def card(x, label, emphasized=False):
        stroke = c["engineering_blue"] if emphasized else c["structure_line"]
        label_fill = c["engineering_blue"] if emphasized else c["blue_tint"]
        label_text = c["white"] if emphasized else c["support_gray"]
        return f"""
      <g transform="translate({x} 390)">
        <rect width="426" height="360" rx="18" fill="{c['white']}" stroke="{stroke}" stroke-width="2"/>
        <rect x="30" y="30" width="150" height="48" rx="12" fill="{label_fill}"/>
        <text x="105" y="62" text-anchor="middle" fill="{label_text}" font-size="20" font-family="JetBrains Mono, monospace" font-weight="700">{label}</text>
        <rect x="30" y="116" width="352" height="18" rx="9" fill="{c['blue_tint']}"/>
        <rect x="30" y="158" width="308" height="18" rx="9" fill="{c['blue_tint']}"/>
        <rect x="30" y="200" width="332" height="18" rx="9" fill="{c['blue_tint']}"/>
        <rect x="30" y="270" width="150" height="42" rx="21" fill="{label_fill}"/>
        <text x="105" y="298" text-anchor="middle" fill="{label_text}" font-size="19" font-weight="700">状态</text>
      </g>"""

    body = f"""
  <g font-family="Inter, Hiragino Sans GB, PingFang SC, sans-serif">
    <text x="88" y="278" fill="{c['ink']}" font-size="58" font-weight="700">同一个目标，为什么结果不同？</text>
    {card(88, "传统方案")}
    {card(566, "系统方案", True)}
    <text x="540" y="585" text-anchor="middle" fill="{c['engineering_blue']}" font-size="76" font-weight="700">≠</text>
    <g transform="translate(88 820)">
      <rect width="904" height="250" rx="22" fill="{c['capability_deck']}" stroke="#3F7CD0" stroke-width="2"/>
      <text x="34" y="58" fill="#9FC4F2" font-size="19" font-family="JetBrains Mono, monospace" letter-spacing="3">THE DIFFERENCE</text>
      <text x="34" y="132" fill="{c['white']}" font-size="42" font-weight="700">同样的目标，不同的执行层级</text>
      <rect x="34" y="172" width="836" height="2" fill="#3F7CD0"/>
      <text x="34" y="216" fill="#9FC4F2" font-size="23">比较卡只承载证据，结论独立占一层。</text>
    </g>
  </g>"""
    return common_svg(tokens, "COMPARISON", "对照型", body)


def process(tokens):
    c = tokens["colors"]
    nodes = [
        ("01", "输入被识别", "DISCOVER"),
        ("02", "按需读取信息", "LOAD"),
        ("03", "执行并校验", "VERIFY"),
        ("04", "结果被锁定", "LOCKED"),
    ]
    node_markup = []
    for index, (num, label, state) in enumerate(nodes):
        y = 360 + index * 178
        active = index < 3
        node_fill = c["engineering_blue"] if active else c["white"]
        node_stroke = c["engineering_blue"]
        node_markup.append(
            f"""
      <circle cx="140" cy="{y + 62}" r="15" fill="{node_fill}" stroke="{node_stroke}" stroke-width="4"/>
      <g transform="translate(190 {y})">
        <rect width="714" height="124" rx="18" fill="{c['white']}" stroke="{c['engineering_blue'] if active else c['structure_line']}" stroke-width="2"/>
        <text x="30" y="50" fill="{c['engineering_blue']}" font-size="21" font-family="JetBrains Mono, monospace" font-weight="700">{num}</text>
        <text x="94" y="52" fill="{c['ink']}" font-size="31" font-weight="700">{label}</text>
        <rect x="548" y="32" width="136" height="48" rx="24" fill="{c['blue_tint']}"/>
        <text x="616" y="63" text-anchor="middle" fill="{c['engineering_blue']}" font-size="17" font-family="JetBrains Mono, monospace" font-weight="700">{state}</text>
      </g>"""
        )
    body = f"""
  <g font-family="Inter, Hiragino Sans GB, PingFang SC, sans-serif">
    <text x="88" y="278" fill="{c['ink']}" font-size="58" font-weight="700">把复杂机制拆成可验证流程</text>
    <line x1="140" y1="420" x2="140" y2="956" stroke="{c['structure_line_strong']}" stroke-width="3"/>
    {''.join(node_markup)}
    <g transform="translate(88 1110)">
      <rect width="812" height="100" rx="12" fill="{c['capability_deck']}" fill-opacity="0.84"/>
      <text x="406" y="63" text-anchor="middle" fill="{c['canvas']}" font-size="34" font-weight="600">信息沿真实语义顺序被逐步确认</text>
    </g>
  </g>"""
    return common_svg(tokens, "PROCESS", "流程型", body)


def capability_deck(tokens):
    c = tokens["colors"]
    items = [
        ("01", "可读取", "READABLE"),
        ("02", "可执行", "EXECUTABLE"),
        ("03", "可验证", "VERIFIABLE"),
        ("04", "可复用", "REUSABLE"),
    ]
    item_markup = []
    for index, (num, label, meta) in enumerate(items):
        x = 36 + index * 207
        item_markup.append(
            f"""
        <g transform="translate({x} 154)">
          <rect width="181" height="190" rx="18" fill="#1D3B66" stroke="#3F7CD0" stroke-width="2"/>
          <text x="22" y="40" fill="#8FB4E4" font-size="17" font-family="JetBrains Mono, monospace">{num}</text>
          <circle cx="90" cy="88" r="25" fill="{c['engineering_blue']}"/>
          <circle cx="90" cy="88" r="8" fill="{c['white']}"/>
          <text x="90" y="142" text-anchor="middle" fill="{c['white']}" font-size="26" font-weight="700">{label}</text>
          <text x="90" y="168" text-anchor="middle" fill="#8FB4E4" font-size="13" font-family="JetBrains Mono, monospace">{meta}</text>
        </g>"""
        )
    body = f"""
  <g font-family="Inter, Hiragino Sans GB, PingFang SC, sans-serif">
    <text x="88" y="278" fill="{c['ink']}" font-size="58" font-weight="700">把方法固化成工程能力</text>
    <g transform="translate(88 360)">
      <rect width="904" height="520" rx="22" fill="{c['capability_deck']}" stroke="#3F7CD0" stroke-width="2"/>
      <text x="36" y="62" fill="#9FC4F2" font-size="20" font-family="JetBrains Mono, monospace" letter-spacing="3">CAPABILITY PACKAGE</text>
      <text x="868" y="62" text-anchor="end" fill="#8FD0B0" font-size="18" font-family="JetBrains Mono, monospace">● VERIFIED</text>
      <rect x="36" y="98" width="832" height="2" fill="#3F7CD0"/>
      {''.join(item_markup)}
      <text x="36" y="466" fill="#9FC4F2" font-size="23">深色板只承载系统、能力、工程资产和结果。</text>
    </g>
    <g transform="translate(88 944)">
      <rect width="904" height="180" rx="18" fill="{c['white']}" stroke="{c['structure_line']}" stroke-width="2"/>
      <text x="32" y="50" fill="{c['support_gray']}" font-size="19" font-family="JetBrains Mono, monospace" letter-spacing="3">INPUT MATERIAL</text>
      <rect x="32" y="78" width="160" height="48" rx="24" fill="{c['blue_tint']}"/>
      <rect x="208" y="78" width="160" height="48" rx="24" fill="{c['blue_tint']}"/>
      <rect x="384" y="78" width="160" height="48" rx="24" fill="{c['blue_tint']}"/>
      <text x="112" y="109" text-anchor="middle" fill="{c['support_gray']}" font-size="18">文档</text>
      <text x="288" y="109" text-anchor="middle" fill="{c['support_gray']}" font-size="18">数据</text>
      <text x="464" y="109" text-anchor="middle" fill="{c['support_gray']}" font-size="18">规则</text>
    </g>
  </g>"""
    return common_svg(tokens, "CAPABILITY DECK", "能力板型", body)


def main():
    tokens = parse_frontmatter(PROJECT_ROOT / "frame.md")
    output_dir = PROJECT_ROOT / "production" / "style-guide" / "examples"
    output_dir.mkdir(parents=True, exist_ok=True)

    renderers = {
        "proposition": proposition,
        "comparison": comparison,
        "process": process,
        "capability_deck": capability_deck,
    }
    magick = shutil.which("magick")
    if not magick:
        raise RuntimeError("ImageMagick `magick` is required")

    png_paths = []
    for name, renderer in renderers.items():
        svg_path = output_dir / f"{name}.svg"
        png_path = output_dir / f"{name}.png"
        svg = "\n".join(line.rstrip() for line in renderer(tokens).splitlines()) + "\n"
        svg_path.write_text(svg, encoding="utf-8")
        subprocess.run(
            [magick, "-background", "none", str(svg_path), str(png_path)],
            check=True,
        )
        png_paths.append(png_path)
        print(f"generated {svg_path.relative_to(PROJECT_ROOT)}")
        print(f"generated {png_path.relative_to(PROJECT_ROOT)}")

    contact_path = output_dir / "contact-sheet.png"
    subprocess.run(
        [
            magick,
            "montage",
            *[str(path) for path in png_paths],
            "-thumbnail",
            "405x540",
            "-tile",
            "4x1",
            "-geometry",
            "405x540+10+10",
            "-background",
            tokens["colors"]["structure_line"],
            str(contact_path),
        ],
        check=True,
    )
    print(f"generated {contact_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
