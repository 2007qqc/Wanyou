import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
from generators.browser_agent import build_browser_agent_payload
from generators.h5_generator import decorate_markdown_with_theme, markdown_to_h5_html
from wanyou.synthesizer import build_augmented_markdown
from wanyou.utils_llm import _normalize_provider


def main():
    sample_markdown = """# 教务通知

## 退课提醒
日期: 2026-04-07

链接: https://example.com/course

请相关同学在本周内完成退课流程。
![配图](https://example.com/test.jpg)
"""
    augmented = build_augmented_markdown(sample_markdown)

    output_dir = pathlib.Path("output")
    output_dir.mkdir(exist_ok=True)
    markdown_path = output_dir / "_smoke_test.md"
    themed_markdown = decorate_markdown_with_theme(augmented, str(markdown_path))
    markdown_path.write_text(themed_markdown, encoding="utf-8")

    html_text = markdown_to_h5_html(
        themed_markdown,
        markdown_path=str(markdown_path),
        output_path="output/_smoke_test.html",
        title="万有预报 Smoke Test",
    )

    payload = build_browser_agent_payload(str(markdown_path), html_path="output/_smoke_test.html")

    assert "教务通知" in augmented and "退课提醒" in augmented
    assert "物理系风格标识" in themed_markdown
    assert "<html" in html_text and "hero" in html_text and "section-kicker" in html_text
    assert payload["agent"] == config.BROWSER_AGENT_TARGET

    providers = ["zhipuai", "openai", "chatgpt", "deepseek", "gemini"]
    normalized = [_normalize_provider(name) for name in providers]
    print("providers:", normalized)
    print("smoke test passed")


if __name__ == "__main__":
    main()
