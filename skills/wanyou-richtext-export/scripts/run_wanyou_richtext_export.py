import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generators.browser_agent import export_browser_agent_payload
from generators.h5_generator import export_h5


IMG_SRC_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I | re.S)


def audit_html_images(html_path: pathlib.Path) -> dict:
    """统计 HTML 里 <img> 的来源分布。

    产物契约是**单文件自包含**：本地图片必须已经由 `wanyou.inline_images` 压成
    ``data:``，否则 HTML 一被单独拷贝（发给别人、丢进共享盘、删掉 output/）
    就会断图。``local`` 非空即视为导出失败。
    """

    text = html_path.read_text(encoding="utf-8")
    inlined = 0
    remote = 0
    local = []
    total = 0
    for match in IMG_SRC_RE.finditer(text):
        src = (match.group(1) if match.group(1) is not None else (match.group(2) or "")).strip()
        total += 1
        lowered = src.lower()
        if lowered.startswith(("data:", "blob:")):
            inlined += 1
        elif lowered.startswith(("http://", "https://", "//")):
            remote += 1
        else:
            local.append(src[:120])
    return {"total": total, "inlined": inlined, "remote": remote, "local": local}


def main():
    parser = argparse.ArgumentParser(description="Export Wanyou Markdown to H5 HTML and browser-agent payload.")
    parser.add_argument("markdown", help="Final Markdown path.")
    parser.add_argument("--html", default="", help="HTML output path.")
    parser.add_argument("--agent-payload", default="", help="Browser-agent payload JSON output path.")
    parser.add_argument("--title", default="万有预报", help="HTML title.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export.")
    parser.add_argument("--skip-agent-payload", action="store_true", help="Skip browser-agent payload export.")
    parser.add_argument(
        "--allow-local-images",
        action="store_true",
        help="把「HTML 里仍有本地图片路径」从失败降级为警告（默认失败：那样的 HTML 不能单独移动）。",
    )
    args = parser.parse_args()

    markdown_path = pathlib.Path(args.markdown).resolve()
    html_path = pathlib.Path(args.html).resolve() if args.html else markdown_path.with_suffix(".html")
    payload_path = pathlib.Path(args.agent_payload).resolve() if args.agent_payload else markdown_path.with_name(markdown_path.stem + "_agent.json")

    exit_code = 0

    if not args.skip_html:
        export_h5(str(markdown_path), str(html_path), title=args.title)
        print(f"html_path: {html_path}")

        # 产物验收：页面本体与复制源都必须只剩内联 data: 图片
        audit = audit_html_images(html_path)
        print(
            "html_images: total={total} inline={inlined} remote={remote} local={local_count} "
            "size={size:,} bytes".format(local_count=len(audit["local"]), size=html_path.stat().st_size, **audit)
        )
        if audit["local"]:
            message = (
                f"HTML 里还有 {len(audit['local'])} 张本地图片路径，单独拷贝这个 HTML 会断图：\n  "
                + "\n  ".join(audit["local"])
            )
            if args.allow_local_images:
                print(f"[warn] {message}", file=sys.stderr)
                print("[warn] 已按 --allow-local-images 降级为警告；产物不可单独移动。", file=sys.stderr)
            else:
                print(f"[error] {message}", file=sys.stderr)
                print(
                    "[error] 先跑 scripts/prepare_xiumi_markdown.py 把图片路径落地（去掉被 Markdown 吃掉的路径），"
                    "再重新导出；确认要保留本地路径时加 --allow-local-images。",
                    file=sys.stderr,
                )
                exit_code = 1
        else:
            print("html_self_contained: yes（HTML 可单独移动，图片全内联）")
    else:
        html_path = pathlib.Path("")

    if not args.skip_agent_payload:
        export_browser_agent_payload(str(markdown_path), str(payload_path), html_path=str(html_path) if str(html_path) else "")
        print(f"agent_payload_path: {payload_path}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
