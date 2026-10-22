from __future__ import annotations

import httpx
from openai import OpenAI

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


def create_client() -> OpenAI:
    """OpenAI SDK 指向任意 OpenAI 兼容 /v1（Ollama、DeepSeek、OpenAI 等）。"""
    # macOS 开系统代理时，httpx 默认 trust_env=True 会把 localhost 走代理 → 502
    http_client = httpx.Client(trust_env=False, timeout=httpx.Timeout(120.0))
    return OpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        http_client=http_client,
    )


def chat(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str | None = None,
    *,
    force_tool_name: str | None = None,
):
    """
    一次 Chat Completions 请求。
    tools 非空时默认 tool_choice=auto；force_tool_name 时强制调用指定 function。
    """
    client = create_client()
    kwargs: dict = {
        "model": model or LLM_MODEL,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        if force_tool_name:
            kwargs["tool_choice"] = {
                "type": "function",
                "function": {"name": force_tool_name},
            }
        else:
            kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)
