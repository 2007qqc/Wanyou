import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import run_pipeline


def main():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Run the Wanyou pipeline once.")
    parser.add_argument("--public-only", action="store_true", help="Skip login-only sources.")
    parser.add_argument("--with-login", action="store_true", help="Include login-only sources.")
    parser.add_argument("--skip-wechat", action="store_true", help="Skip WeChat collection.")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip summaries and transitions.")
    parser.add_argument("--skip-docx", action="store_true", help="Skip DOCX export.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export.")
    parser.add_argument("--skip-agent-payload", action="store_true", help="Skip browser-agent payload export.")
    parser.add_argument("--ranked-raw", action="store_true", help="Collect raw items, hard-filter by recent publish date, clean text, and LLM-rank by importance.")
    parser.add_argument("--ranked-raw-no-clean", action="store_true", help="Run ranked raw, but skip LLM text cleaning before importance ranking.")
    parser.add_argument("--todo-richtext", action="store_true", help="Generate ranked raw, pick top items per section, then build final themed Markdown and HTML.")
    args = parser.parse_args()

    public_only = True
    if args.with_login:
        public_only = False
    elif args.public_only:
        public_only = True

    result = run_pipeline(
        public_only=public_only,
        include_wechat=not args.skip_wechat,
        synthesize=not args.skip_synthesis,
        export_docx=not args.skip_docx,
        export_html=not args.skip_html,
        export_agent_payload=not args.skip_agent_payload,
        ranked_raw=args.ranked_raw or args.ranked_raw_no_clean,
        ranked_raw_skip_clean=args.ranked_raw_no_clean,
        todo_richtext=args.todo_richtext,
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
