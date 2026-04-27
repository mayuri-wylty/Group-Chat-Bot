from __future__ import annotations

from typing import Any

import requests


class LLMError(RuntimeError):
    pass


def _build_messages(system_prompt: str, history: list[dict[str, str]], prompt: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    return messages


def _extract_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip()
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            text = item.get("text") or item.get("content")
                            if isinstance(text, str) and text.strip():
                                parts.append(text.strip())
                    if parts:
                        return "\n".join(parts)
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    raise LLMError(f"模型接口返回中没有可用文本：{payload}")


def ask_llm(
    prompt: str,
    *,
    api_base: str,
    api_key: str,
    model: str,
    system_prompt: str = "",
    history: list[dict[str, str]] | None = None,
    temperature: float = 0.7,
    timeout: int = 120,
) -> str:
    if not api_base.strip():
        raise LLMError("未配置大模型 API Base")
    if not model.strip():
        raise LLMError("未配置模型名称")

    url = api_base.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = f"{url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    payload = {
        "model": model.strip(),
        "messages": _build_messages(system_prompt, history or [], prompt),
        "temperature": float(temperature),
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise LLMError(f"模型接口调用失败：{exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError(f"模型接口返回不是 JSON：{response.text[:300]}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise LLMError(f"模型接口返回错误：{data.get('error')}")
    if not isinstance(data, dict):
        raise LLMError(f"模型接口返回格式异常：{data}")
    return _extract_text(data)
