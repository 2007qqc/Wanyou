import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import run_pipeline
from scripts.publish_xiumi_draft import publish_xiumi_draft


def _configure_console():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main():
    _configure_console()

    parser = argparse.ArgumentParser(description="Run Wanyou end to end and send the final result to a Xiumi draft.")
    parser.add_argument("--public-only", action="store_true", help="Skip login-only campus sources.")
    parser.add_argument("--with-login", action="store_true", help="Include login-only campus sources.")
    parser.add_argument("--skip-wechat", action="store_true", help="Skip WeChat collection.")
    parser.add_argument("--skip-docx", action="store_true", help="Skip DOCX export.")
    parser.add_argument("--skip-agent-payload", action="store_true", help="Skip browser-agent payload export.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export.")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip summaries and transitions.")
    parser.add_argument("--title", default="", help="Title to fill in Xiumi draft.")
    parser.add_argument("--author", default="物理系学生会", help="Author to fill in Xiumi draft.")
    parser.add_argument("--digest", default="", help="Digest to fill in Xiumi draft.")
    parser.add_argument("--source-url", default="", help="Original link to fill in Xiumi draft.")
    parser.add_argument("--xiumi-dry-run", action="store_true", help="Fill Xiumi editor without clicking save.")
    parser.add_argument(
        "--xiumi-profile-dir",
        default="",
        help=(
            "Optional Xiumi browser profile directory. By default --leave-open uses an isolated one-time "
            "profile; normal runs reuse the configured profile."
        ),
    )
    parser.add_argument("--leave-open", action="store_true", help="Leave Xiumi browser window open after the script exits.")
    args = parser.parse_args()

    public_only = True
    if args.with_login:
        public_only = False
    elif args.public_only:
        public_only = True

    print("[1/2] Running Wanyou pipeline...")
    result = run_pipeline(
        public_only=public_only,
        include_wechat=not args.skip_wechat,
        synthesize=not args.skip_synthesis,
        export_docx=not args.skip_docx,
        export_html=not args.skip_html,
        export_agent_payload=not args.skip_agent_payload,
        todo_richtext=True,
    )

    html_path = str(result.get("html_path") or "").strip()
    final_markdown_path = str(result.get("final_markdown_path") or "").strip()
    if not html_path:
        raise SystemExit("HTML output path is empty. Re-run without --skip-html.")

    print("[2/2] Sending content to Xiumi draft editor...")
    xiumi_result = publish_xiumi_draft(
        html_path,
        markdown=final_markdown_path,
        title=args.title,
        author=args.author,
        digest=args.digest,
        source_url=args.source_url,
        profile_dir=args.xiumi_profile_dir,
        dry_run=args.xiumi_dry_run,
        leave_open=args.leave_open,
    )

    for key, value in result.items():
        print(f"{key}: {value}")
    for key, value in xiumi_result.items():
        print(f"xiumi_{key}: {value}")


if __name__ == "__main__":
    main()
