#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "python3 was not found. Install Python 3.10+ first."
  exit 1
fi

if [ -d "$VENV_DIR" ]; then
  VENV_PYTHON="$("$VENV_DIR/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || true)"
  TARGET_PYTHON="$("$PYTHON_BIN" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
  if [ "$VENV_PYTHON" != "$TARGET_PYTHON" ]; then
    "$PYTHON_BIN" -m venv --clear "$VENV_DIR"
  fi
else
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt PyYAML

cat <<'EOF'

macOS setup complete.

Next:
  source .venv/bin/activate
  export WANYOU_SELENIUM_BROWSER=chrome
  python skills/wanyou-full-run/scripts/run_wanyou_full_run.py --public-only --skip-docx

Optional DOCX export:
  brew install pandoc
EOF
