import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

try:
    from zhipuai import ZhipuAI
except Exception:
    ZhipuAI = None

import config


_OPENAI_COMPATIBLE_PROVIDERS = {"openai", "chatgpt", "deepseek", "zhipuai"}


def _normalize_provider(provider: Optional[str] = None) -> str:
    raw = (provider or config.LLM_PROVIDER or "").strip().lower()
    aliases = {
        "chatgpt": "openai",
        "openai": "openai",
        "deepseek": "deepseek",
        "gemini": "gemini",
        "zhipu": "zhipuai",
        "zhipuai": "zhipuai",
    }
    return aliases.get(raw, raw or "openai")


def _provider_defaults(provider_name: str) -> Dict[str, str]:
    if provider_name == "deepseek":
        return {
            "api_key_env": getattr(config, "DEEPSEEK_API_KEY_ENV", "DEEPSEEK_API_KEY"),
            "base_url": getattr(config, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        }
    if provider_name == "gemini":
        return {
            "api_key_env": getattr(config, "GEMINI_API_KEY_ENV", "GEMINI_API_KEY"),
            "base_url": getattr(config, "GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"),
        }
    if provider_name == "zhipuai":
        return {
            "api_key_env": getattr(config, "ZHIPUAI_API_KEY_ENV", "ZHIPUAI_API_KEY"),
            "base_url": getattr(config, "ZHIPUAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
        }
    return {
        "api_key_env": getattr(config, "OPENAI_API_KEY_ENV", "OPENAI_API_KEY"),
        "base_url": getattr(config, "OPENAI_BASE_URL", "https://api.openai.com/v1"),
    }


def _resolve_api_key_env(provider_name: str, api_key_env: Optional[str] = None) -> str:
    if api_key_env:
        return api_key_env
    configured = getattr(config, "LLM_API_KEY_ENV", "").strip()
    if configured:
        return configured
    return _provider_defaults(provider_name)["api_key_env"]


def _resolve_base_url(provider_name: str, base_url: Optional[str] = None) -> str:
    if base_url:
        return base_url.rstrip("/")
    configured = getattr(config, "LLM_BASE_URL", "").strip()
    if configured:
        return configured.rstrip("/")
    return _provider_defaults(provider_name)["base_url"].rstrip("/")


def _resolve_max_tokens() -> Optional[int]:
    """本次请求下发的 max_tokens；None 表示不下发，交给服务端。

    不下发时服务端按模式给默认值：非思考 8K、思考 64K（effort=max 时 128K），
    上限 384K。以前各调用点写死的 5~800 本身就偏小，而截断是静默的——返回空
    内容后调用方的 `or 兜底值` 会悄悄降级，日志上看不出错。所以默认不下发
    （config.LLM_MAX_TOKENS = 0），确实要限长再显式设成正数。
    """
    configured = int(getattr(config, "LLM_MAX_TOKENS", 0) or 0)
    return configured if configured > 0 else None


def _resolve_reasoning_effort(provider_name: str) -> Optional[str]:
    """本次请求下发的 reasoning_effort；None 表示不下发。

    只对 deepseek 下发——这个字段是 DeepSeek 特有的，别的 provider 不认。
    取值 none/low/high/max；none 关闭思考模式，其余开启。medium、minimal、
    xhigh、ultra 是官方兼容别名，不报错但会被映射到上面的档位。
    """
    if provider_name != "deepseek":
        return None
    return str(getattr(config, "DEEPSEEK_REASONING_EFFORT", "") or "").strip().lower() or None


def _api_key(env_name: str) -> Optional[str]:
    return os.getenv(env_name, "").strip() or None


def _headers(api_key: Optional[str]):
    if not api_key:
        return None
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _build_messages(system_prompt: str, user_prompt: str):
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = str(item.get("text", "")).strip()
                if text:
                    parts.append(text)
            elif isinstance(item, str):
                text = item.strip()
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


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


def _call_zhipu_sdk(
    api_key: str,
    model_name: str,
    messages: List[dict],
    temperature: float,
) -> Optional[str]:
    if ZhipuAI is None:
        return None
    kwargs = {"model": model_name, "messages": messages, "temperature": temperature}
    max_tokens = _resolve_max_tokens()
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    try:
        client = ZhipuAI(api_key=api_key)
        resp: Any = client.chat.completions.create(**kwargs)
        return _extract_text(resp.choices[0].message.content)
    except Exception:
        return None


def _call_openai_compatible(
    provider_name: str,
    model_name: str,
    api_key: str,
    base_url: str,
    messages: List[dict],
    timeout: int,
    temperature: float,
) -> Optional[str]:
    headers = _headers(api_key)
    if not headers:
        return None

    body = {
        "model": model_name,
        "messages": messages,
        "temperature": temperature,
    }
    max_tokens = _resolve_max_tokens()
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    reasoning_effort = _resolve_reasoning_effort(provider_name)
    if reasoning_effort is not None:
        body["reasoning_effort"] = reasoning_effort
    endpoint = f"{base_url}/chat/completions"

    try:
        resp = requests.post(endpoint, headers=headers, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return _extract_text(data["choices"][0]["message"]["content"])
    except Exception:
        return None


def _gemini_parts_from_text(system_prompt: str, user_prompt: str) -> dict:
    return {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
    }


def _call_gemini_text(
    model_name: str,
    api_key: str,
    base_url: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int,
    temperature: float,
) -> Optional[str]:
    endpoint = f"{base_url}/models/{model_name}:generateContent"
    body = _gemini_parts_from_text(system_prompt, user_prompt)
    generation_config = {"temperature": temperature}
    max_tokens = _resolve_max_tokens()
    if max_tokens is not None:
        generation_config["maxOutputTokens"] = max_tokens
    body["generationConfig"] = generation_config
    try:
        resp = requests.post(endpoint, params={"key": api_key}, json=body, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = []
        for part in parts:
            text = str(part.get("text", "")).strip()
            if text:
                texts.append(text)
        return "\n".join(texts).strip() or None
    except Exception:
        return None


def chat_complete(
    system_prompt: str,
    user_prompt: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key_env: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    temperature: float = 0,
    task_label: str = "\u004c\u004c\u004d\u4efb\u52a1",
) -> Optional[str]:
    if not config.LLM_ENABLED:
        return None

    print(f"\u7b49\u5f85LLM\u8f93\u51fa\u4e2d\uff1a{task_label}")

    provider_name = _normalize_provider(provider)
    model_name = model or config.LLM_MODEL
    timeout = timeout_seconds or config.LLM_TIMEOUT_SECONDS
    api_key_name = _resolve_api_key_env(provider_name, api_key_env)
    api_key = _api_key(api_key_name)
    if not api_key:
        return None

    messages = _build_messages(system_prompt, user_prompt)
    content = None

    attempts = 2
    for attempt in range(attempts):
        if provider_name == "zhipuai" and not base_url and not api_key_env:
            content = _call_zhipu_sdk(api_key, model_name, messages, temperature)

        if content is None and provider_name in _OPENAI_COMPATIBLE_PROVIDERS:
            content = _call_openai_compatible(
                provider_name,
                model_name,
                api_key,
                _resolve_base_url(provider_name, base_url),
                messages,
                timeout,
                temperature,
            )
        elif content is None and provider_name == "gemini":
            content = _call_gemini_text(
                model_name,
                api_key,
                _resolve_base_url(provider_name, base_url),
                system_prompt,
                user_prompt,
                timeout,
                temperature,
            )
        if content:
            break
        if attempt + 1 < attempts:
            content = None

    if content is not None:
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


def multimodal_complete(
    system_prompt: str,
    user_prompt: str,
    image_url: str,
    *,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key_env: Optional[str] = None,
    base_url: Optional[str] = None,
    timeout_seconds: Optional[int] = None,
    temperature: float = 0,
) -> Optional[str]:
    if not config.LLM_ENABLED:
        return None

    provider_name = _normalize_provider(provider)
    model_name = model or config.LLM_MODEL
    timeout = timeout_seconds or config.LLM_TIMEOUT_SECONDS
    api_key_name = _resolve_api_key_env(provider_name, api_key_env)
    api_key = _api_key(api_key_name)
    if not api_key or not image_url:
        return None

    try:
        if provider_name in _OPENAI_COMPATIBLE_PROVIDERS:
            endpoint = f"{_resolve_base_url(provider_name, base_url)}/chat/completions"
            body = {
                "model": model_name,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            }
            max_tokens = _resolve_max_tokens()
            if max_tokens is not None:
                body["max_tokens"] = max_tokens
            reasoning_effort = _resolve_reasoning_effort(provider_name)
            if reasoning_effort is not None:
                body["reasoning_effort"] = reasoning_effort
            resp = requests.post(endpoint, headers=_headers(api_key), json=body, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = _extract_text(data["choices"][0]["message"]["content"])
        elif provider_name == "gemini":
            endpoint = f"{_resolve_base_url(provider_name, base_url)}/models/{model_name}:generateContent"
            generation_config = {"temperature": temperature}
            max_tokens = _resolve_max_tokens()
            if max_tokens is not None:
                generation_config["maxOutputTokens"] = max_tokens
            body = {
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {"text": user_prompt},
                            {"file_data": {"mime_type": "image/jpeg", "file_uri": image_url}},
                        ],
                    }
                ],
                "generationConfig": generation_config,
            }
            resp = requests.post(endpoint, params={"key": api_key}, json=body, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts", [])
            content = "\n".join(
                str(part.get("text", "")).strip() for part in parts if str(part.get("text", "")).strip()
            ).strip()
        else:
            return None
    except Exception:
        return None

    if content:
        _log_payload(
            {
                "ts": time.time(),
                "provider": provider_name,
                "model": model_name,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "image_url": image_url,
                "raw": content,
            }
        )
    return content or None


def llm_decide_yes_no(context: str) -> Optional[bool]:
    content = chat_complete(
        config.LLM_SYSTEM_PROMPT,
        context,
        temperature=0,
        task_label="\u6b63\u5728\u5224\u65ad\u6761\u76ee\u662f\u5426\u4fdd\u7559",
    )
    return _parse_decision(content or "")
