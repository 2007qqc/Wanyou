
import datetime as dt
import json
import os
import threading
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_DEBUG_DIR = ""
_LOG_PATH = ""


def configure_filter_debug(debug_dir: str, reset: bool = False) -> str:
    global _DEBUG_DIR, _LOG_PATH
    if not debug_dir:
        return ""
    _DEBUG_DIR = os.path.abspath(debug_dir)
    Path(_DEBUG_DIR).mkdir(parents=True, exist_ok=True)
    _LOG_PATH = os.path.join(_DEBUG_DIR, "filter_decisions.jsonl")
    if reset:
        Path(_LOG_PATH).write_text("", encoding="utf-8")
        summary_path = os.path.join(_DEBUG_DIR, "filter_decisions_summary.json")
        try:
            Path(summary_path).unlink()
        except FileNotFoundError:
            pass
    os.environ["WANYOU_FILTER_DEBUG_DIR"] = _DEBUG_DIR
    return _LOG_PATH


def configure_filter_debug_from_markdown(markdown_path: str) -> str:
    if _LOG_PATH:
        return _LOG_PATH
    if markdown_path:
        run_dir = os.path.dirname(os.path.abspath(markdown_path))
        return configure_filter_debug(os.path.join(run_dir, "debug"), reset=False)
    env_dir = os.environ.get("WANYOU_FILTER_DEBUG_DIR", "").strip()
    if env_dir:
        return configure_filter_debug(env_dir, reset=False)
    return ""


def log_filter_decision(
    *,
    section: str,
    title: str = "",
    status: str,
    reason: str = "",
    stage: str = "",
    date: str = "",
    url: str = "",
    source: str = "",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    path = _LOG_PATH or configure_filter_debug_from_markdown("")
    if not path:
        return
    record = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "section": section or "unknown",
        "title": title or "",
        "status": status,
        "reason": reason or "",
        "stage": stage or "",
        "date": date or "",
        "url": url or "",
        "source": source or "",
    }
    if details:
        record["details"] = details
    with _LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def finalize_filter_debug() -> str:
    path = _LOG_PATH or configure_filter_debug_from_markdown("")
    if not path or not os.path.exists(path):
        return ""
    counts = defaultdict(Counter)
    total = Counter()
    records = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            records += 1
            section = record.get("section") or "unknown"
            status = record.get("status") or "unknown"
            reason = record.get("reason") or "unknown"
            counts[section][status] += 1
            counts[f"{section}::reason"][reason] += 1
            total[status] += 1
    summary = {
        "records": records,
        "total_by_status": dict(total),
        "sections": {},
    }
    for key, counter in counts.items():
        if key.endswith("::reason"):
            continue
        reason_key = f"{key}::reason"
        summary["sections"][key] = {
            "by_status": dict(counter),
            "by_reason": dict(counts.get(reason_key, Counter())),
        }
    out_path = os.path.join(os.path.dirname(path), "filter_decisions_summary.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    return out_path
