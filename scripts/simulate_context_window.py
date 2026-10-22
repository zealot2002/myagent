#!/usr/bin/env python3
"""
模拟「上下文窗口撑满」：在可控 num_ctx 下灌入长 messages，观察 Ollama 行为。

用法:
  python scripts/simulate_context_window.py
  python scripts/simulate_context_window.py --num-ctx 512 --chunk-chars 4000
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import OLLAMA_BASE_URL, OLLAMA_MODEL  # noqa: E402


def _client() -> OpenAI:
    return OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        http_client=httpx.Client(trust_env=False, timeout=httpx.Timeout(300.0)),
    )


def _approx_tokens(text: str) -> int:
    """粗算：英文约 4 字符/token，中文约 1.5 字符/token；这里用 3 字符/token 估。"""
    return max(1, len(text) // 3)


def _messages_payload(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += _approx_tokens(str(m.get("content", "")))
        if m.get("tool_calls"):
            total += _approx_tokens(json.dumps(m["tool_calls"], ensure_ascii=False))
    return total


def run_simulation(*, num_ctx: int, chunk_chars: int, max_rounds: int) -> None:
    client = _client()
    messages: list[dict] = [
        {"role": "system", "content": "你是测试助手。用户会不断发送重复块，你只需回复 OK。"},
    ]
    chunk = ("窗口压力测试。" * (chunk_chars // 7 + 1))[:chunk_chars]

    print(f"model={OLLAMA_MODEL} num_ctx={num_ctx} chunk_chars={chunk_chars}\n")

    for i in range(1, max_rounds + 1):
        messages.append({"role": "user", "content": f"[块 {i}] {chunk}"})
        est = _messages_payload(messages)
        print(f"--- round {i}: messages={len(messages)} approx_input_tokens≈{est} (limit num_ctx={num_ctx}) ---")

        try:
            completion = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                extra_body={"options": {"num_ctx": num_ctx}},
            )
            reply = (completion.choices[0].message.content or "").strip()
            usage = completion.usage
            print(f"OK  reply={reply[:80]!r}")
            if usage:
                print(
                    f"     usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}"
                )
            messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"FAIL {type(e).__name__}: {e}")
            print("\n最后一次请求时的 messages 条数:", len(messages))
            print("approx_input_tokens≈", est)
            return

    print("\n未在本轮 max_rounds 内触发失败；可增大 chunk 或 max_rounds，或减小 num_ctx。")


def main() -> int:
    parser = argparse.ArgumentParser(description="模拟上下文窗口被撑满")
    parser.add_argument("--num-ctx", type=int, default=512, help="Ollama num_ctx，故意设小以便快速复现")
    parser.add_argument("--chunk-chars", type=int, default=3000, help="每轮追加的 user 文本长度")
    parser.add_argument("--max-rounds", type=int, default=20)
    args = parser.parse_args()
    run_simulation(num_ctx=args.num_ctx, chunk_chars=args.chunk_chars, max_rounds=args.max_rounds)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
