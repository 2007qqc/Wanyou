import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from generators.browser_agent import export_browser_agent_payload
from generators.h5_generator import export_h5


def main():
    parser = argparse.ArgumentParser(description="Export Wanyou Markdown to H5 HTML and browser-agent payload.")
    parser.add_argument("markdown", help="Final Markdown path.")
    parser.add_argument("--html", default="", help="HTML output path.")
    parser.add_argument("--agent-payload", default="", help="Browser-agent payload JSON output path.")
    parser.add_argument("--title", default="万有预报", help="HTML title.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export.")
    parser.add_argument("--skip-agent-payload", action="store_true", help="Skip browser-agent payload export.")
    args = parser.parse_args()

    markdown_path = pathlib.Path(args.markdown).resolve()
    html_path = pathlib.Path(args.html).resolve() if args.html else markdown_path.with_suffix(".html")
    payload_path = pathlib.Path(args.agent_payload).resolve() if args.agent_payload else markdown_path.with_name(markdown_path.stem + "_agent.json")

    if not args.skip_html:
        export_h5(str(markdown_path), str(html_path), title=args.title)
        print(f"html_path: {html_path}")
    else:
        html_path = pathlib.Path("")

    if not args.skip_agent_payload:
        export_browser_agent_payload(str(markdown_path), str(payload_path), html_path=str(html_path) if str(html_path) else "")
        print(f"agent_payload_path: {payload_path}")


if __name__ == "__main__":
    main()
