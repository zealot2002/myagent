from __future__ import annotations

import httpx
from openai import OpenAI

from config import OLLAMA_BASE_URL, OLLAMA_MODEL


def create_client() -> OpenAI:
    """OpenAI SDK 指向 Ollama 的 /v1；api_key 填占位即可。"""
    # macOS 开系统代理时，httpx 默认 trust_env=True 会把 localhost 走代理 → 502
    http_client = httpx.Client(trust_env=False, timeout=httpx.Timeout(120.0))
    return OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        http_client=http_client,
    )


def chat(messages: list[dict], tools: list[dict] | None = None, model: str | None = None):
    """
    一次 Chat Completions 请求。
    tools 非空时附带 tool_choice=auto，模型可返回 tool_calls。
    """
    client = create_client()
    kwargs: dict = {
        "model": model or OLLAMA_MODEL,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)
