import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run the Wanyou pipeline once.")
    parser.add_argument("--public-only", action="store_true", help="Skip login-only sources.")
    parser.add_argument("--with-login", action="store_true", help="Include login-only sources.")
    parser.add_argument("--skip-wechat", action="store_true", help="Skip WeChat collection.")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip summaries and transitions.")
    parser.add_argument("--skip-docx", action="store_true", help="Skip DOCX export.")
    parser.add_argument("--skip-html", action="store_true", help="Skip HTML export.")
    parser.add_argument("--skip-agent-payload", action="store_true", help="Skip browser-agent payload export.")
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
    )
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
