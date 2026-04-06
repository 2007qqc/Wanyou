import json
import os
import time
from typing import Any, Optional

import requests

try:
    from zhipuai import ZhipuAI
except Exception:
    ZhipuAI = None

import config


def _api_key(env_name: Optional[str] = None) -> Optional[str]:
    key_name = env_name or config.LLM_API_KEY_ENV
    return os.getenv(key_name)


def _base_url(base_url: Optional[str] = None) -> str:
    return (base_url or config.LLM_BASE_URL).rstrip("/")


def _endpoint(base_url: Optional[str] = None) -> str:
    return f"{_base_url(base_url)}/chat/completions"


def _headers(api_key_env: Optional[str] = None):
    key = _api_key(api_key_env)
    if not key:
        return None
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def _build_messages(system_prompt: str, user_prompt: str):
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
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


def _log_payload(payload: dict):
    if not config.LLM_LOG_PATH:
        return
    try:
        with open(config.LLM_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key_env: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    max_tokens: int = 200,
    temperature: float = 0,
) -> Optional[str]:
    if not config.LLM_ENABLED:
        return None

    provider_name = provider or config.LLM_PROVIDER
    model_name = model or config.LLM_MODEL
    timeout = timeout_seconds or config.LLM_TIMEOUT_SECONDS
    messages = _build_messages(system_prompt, user_prompt)

    if provider_name == "zhipuai" and base_url is None and api_key_env is None:
        key = _api_key(api_key_env)
        if not key or ZhipuAI is None:
            return None
        try:
            client = ZhipuAI(api_key=key)
            resp: Any = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            _log_payload(
                {
                    "ts": time.time(),
                    "provider": provider_name,
                    "model": model_name,
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "raw": content,
                }
            )
            return content
        except Exception:
            return None

    headers = _headers(api_key_env)
    if not headers:
        return None

    body = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    try:
        resp = requests.post(
            _endpoint(base_url),
            headers=headers,
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        _log_payload(
            {
                "ts": time.time(),
                "provider": provider_name,
                "model": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "raw": content,
            }
        )
        return content
    except Exception:
        return None


def llm_decide_yes_no(context: str) -> Optional[bool]:
    content = chat_complete(
        config.LLM_SYSTEM_PROMPT,
        context,
        max_tokens=5,
        temperature=0,
    )
    return _parse_decision(content or "")
