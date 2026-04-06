import json
import os
from typing import Dict

import config


def build_browser_agent_payload(markdown_path: str, html_path: str = "") -> Dict[str, object]:
    with open(markdown_path, "r", encoding="utf-8") as f:
        markdown_text = f.read()

    payload = {
        "agent": getattr(config, "BROWSER_AGENT_TARGET", "autoglm-browser-agent"),
        "enabled": bool(getattr(config, "BROWSER_AGENT_ENABLED", False)),
        "mcp_config": getattr(config, "BROWSER_AGENT_MCP_CONFIG", "./config/mcporter.json"),
        "inputs": {
            "markdown_path": os.path.abspath(markdown_path),
            "html_path": os.path.abspath(html_path) if html_path else "",
        },
        "slots": getattr(config, "XIUMI_TEMPLATE_SLOTS", {}),
        "instructions": [
            "读取 markdown_path 中的内容。",
            "打开秀米或其他 H5 编辑器。",
            "根据 slots 将标题、导语、正文填充到对应槽位。",
            "若正文中存在图片 markdown，保留图片在内容流中的位置。",
        ],
        "content_preview": markdown_text[:4000],
    }
    return payload


def export_browser_agent_payload(markdown_path: str, output_path: str, html_path: str = "") -> str:
    payload = build_browser_agent_payload(markdown_path, html_path=html_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return output_path
