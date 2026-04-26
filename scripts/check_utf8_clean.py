import argparse
import re
from pathlib import Path

DEFAULT_PATHS = ["README.md", "wanyou", "generators", "scripts", "skills"]
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".ps1", ".txt"}
BAD_PATTERNS = [
    re.compile(r"\?{3,}"),
    re.compile(r"[\u00c0-\u00ff]{4,}"),
]


def iter_files(paths):
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in TEXT_SUFFIXES:
                yield path
            continue
        for child in path.rglob("*"):
            if any(part in SKIP_DIRS for part in child.parts):
                continue
            if child.is_file() and child.suffix.lower() in TEXT_SUFFIXES:
                yield child


def main():
    parser = argparse.ArgumentParser(description="Check obvious mojibake in UTF-8 text files.")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    args = parser.parse_args()

    problems = []
    for path in iter_files(args.paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            problems.append((path, 0, f"utf-8 decode failed: {exc}"))
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in BAD_PATTERNS:
                if pattern.search(line):
                    problems.append((path, lineno, line.strip()[:160]))
                    break

    if problems:
        for path, lineno, sample in problems:
            print(f"{path}:{lineno}: {sample}")
        raise SystemExit(1)
    print("utf8_mojibake_check_ok")


if __name__ == "__main__":
    main()
