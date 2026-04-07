import pathlib

import config
from generators.browser_agent import build_browser_agent_payload
from generators.h5_generator import markdown_to_h5_html
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
    html_text = markdown_to_h5_html(augmented, title="万有预报 Smoke Test")

    output_dir = pathlib.Path("output")
    output_dir.mkdir(exist_ok=True)
    markdown_path = output_dir / "_smoke_test.md"
    markdown_path.write_text(augmented, encoding="utf-8")

    payload = build_browser_agent_payload(str(markdown_path), html_path="output/_smoke_test.html")

    assert "要点透视：" in augmented
    assert "<html" in html_text and "<img" in html_text
    assert payload["agent"] == config.BROWSER_AGENT_TARGET

    providers = ["zhipuai", "openai", "chatgpt", "deepseek", "gemini"]
    normalized = [_normalize_provider(name) for name in providers]
    print("providers:", normalized)
    print("smoke test passed")


if __name__ == "__main__":
    main()
