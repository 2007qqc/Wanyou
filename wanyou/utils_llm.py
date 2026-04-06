import json
import os
import time
from typing import Optional

import requests
from typing import Any

try:
    from zhipuai import ZhipuAI
except Exception:
    ZhipuAI = None

import config


def _api_key() -> Optional[str]:
    return os.getenv(config.LLM_API_KEY_ENV)


def _base_url() -> str:
    return config.LLM_BASE_URL.rstrip("/")


def _endpoint() -> str:
    return f"{_base_url()}/chat/completions"


def _headers():
    key = _api_key()
    if not key:
        return None
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _build_messages(context: str):
    return [
        {"role": "system", "content": config.LLM_SYSTEM_PROMPT},
        {"role": "user", "content": context},
    ]


def _parse_decision(text: str) -> Optional[bool]:
    if not text:
        return None
    head = text.strip().upper()
    if head.startswith("YES"):
        return True
    if head.startswith("NO"):
        return False
    return None


def _log_decision(payload: dict):
    if not config.LLM_LOG_PATH:
        return
    try:
        with open(config.LLM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _call_openai_compatible(context: str) -> Optional[bool]:
    if not config.LLM_ENABLED:
        return None

    headers = _headers()
    if not headers:
        return None

    body = {
        "model": config.LLM_MODEL,
        "messages": _build_messages(context),
        "temperature": 0,
        "max_tokens": 5,
    }

    try:
        resp = requests.post(
            _endpoint(),
            headers=headers,
            json=body,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        decision = _parse_decision(content)
        _log_decision(
            {
                "ts": time.time(),
                "provider": config.LLM_PROVIDER,
                "model": config.LLM_MODEL,
                "context": context,
                "raw": content,
                "decision": decision,
            }
        )
        return decision
    except Exception:
        return None


def _call_zhipuai_sdk(context: str) -> Optional[bool]:
    if not config.LLM_ENABLED:
        return None
    key = _api_key()
    if not key:
        return None
    if ZhipuAI is None:
        return None
    try:
        client = ZhipuAI(api_key=key)
        resp: Any = client.chat.completions.create(
            model=config.LLM_MODEL,
            messages=_build_messages(context),
            temperature=0,
            max_tokens=5,
        )
        content = resp.choices[0].message.content
        decision = _parse_decision(content)
        _log_decision(
            {
                "ts": time.time(),
                "provider": config.LLM_PROVIDER,
                "model": config.LLM_MODEL,
                "context": context,
                "raw": content,
                "decision": decision,
            }
        )
        return decision
    except Exception:
        return None


def llm_decide_yes_no(context: str) -> Optional[bool]:
    if config.LLM_PROVIDER == "zhipuai":
        return _call_zhipuai_sdk(context)
    return _call_openai_compatible(context)
