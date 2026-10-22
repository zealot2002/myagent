#!/usr/bin/env python3
"""
模拟「上下文窗口撑满」：在可控 num_ctx 下灌入长 messages，观察 Ollama 行为。

用法:
  python scripts/simulate_context_window.py --num-ctx 512
  python scripts/simulate_context_window.py --num-ctx 256 --chunk-chars 8000 --with-trim --max-tokens 1500
  python scripts/compare_context_trim.py
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

from agent.context import estimate_messages_tokens, prepare_messages  # noqa: E402
from config import OLLAMA_BASE_URL, OLLAMA_MODEL  # noqa: E402


def _client() -> OpenAI:
    return OpenAI(
        base_url=OLLAMA_BASE_URL,
        api_key="ollama",
        http_client=httpx.Client(trust_env=False, timeout=httpx.Timeout(300.0)),
    )


def run_simulation(
    *,
    num_ctx: int,
    chunk_chars: int,
    max_rounds: int,
    with_trim: bool,
    max_tokens: int,
    tool_max_chars: int,
) -> None:
    client = _client()
    messages: list[dict] = [
        {
            "role": "system",
            "content": "你是测试助手。每块 user 以 [块 N] 开头。用户问「最早是第几块」时，只根据仍可见的 user 消息回答数字。",
        },
    ]
    chunk = ("窗口压力测试。" * (chunk_chars // 7 + 1))[:chunk_chars]
    mode = "trim" if with_trim else "no-trim"
    print(f"model={OLLAMA_MODEL} num_ctx={num_ctx} chunk_chars={chunk_chars} mode={mode}\n")

    for i in range(1, max_rounds + 1):
        if i == max_rounds:
            messages.append({"role": "user", "content": "最早是第几块？只答数字。"})
        else:
            messages.append({"role": "user", "content": f"[块 {i}] {chunk}"})

        est = estimate_messages_tokens(messages)
        print(f"--- round {i}: messages={len(messages)} approx_tokens≈{est} ---")

        if with_trim:
            stats = prepare_messages(
                messages,
                max_tokens=max_tokens,
                tool_max_chars=tool_max_chars,
                enabled=True,
            )
            if stats.trimmed:
                print(
                    f"     trim: tokens {stats.tokens_before}→{stats.tokens_after}, "
                    f"dropped_msgs={stats.messages_dropped}, tools_truncated={stats.tools_truncated}"
                )
            est = estimate_messages_tokens(messages)

        try:
            completion = client.chat.completions.create(
                model=OLLAMA_MODEL,
                messages=messages,
                extra_body={"options": {"num_ctx": num_ctx}},
            )
            reply = (completion.choices[0].message.content or "").strip()
            usage = completion.usage
            print(f"OK  reply={reply[:100]!r}")
            if usage:
                print(
                    f"     usage: prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}"
                )
            if i < max_rounds:
                messages.append({"role": "assistant", "content": reply})
        except Exception as e:
            print(f"FAIL {type(e).__name__}: {e}")
            return

    print(f"\n完成 rounds={max_rounds}；最终 messages 条数={len(messages)} approx_tokens≈{est}")


def main() -> int:
    parser = argparse.ArgumentParser(description="模拟上下文窗口被撑满")
    parser.add_argument("--num-ctx", type=int, default=512, help="Ollama num_ctx，故意设小以便快速复现")
    parser.add_argument("--chunk-chars", type=int, default=3000, help="每轮追加的 user 文本长度")
    parser.add_argument("--max-rounds", type=int, default=8)
    parser.add_argument("--with-trim", action="store_true", help="调用 agent.context.prepare_messages")
    parser.add_argument("--max-tokens", type=int, default=1500, help="with-trim 时的 CONTEXT 预算（估 token）")
    parser.add_argument("--tool-max-chars", type=int, default=2000)
    args = parser.parse_args()
    run_simulation(
        num_ctx=args.num_ctx,
        chunk_chars=args.chunk_chars,
        max_rounds=args.max_rounds,
        with_trim=args.with_trim,
        max_tokens=args.max_tokens,
        tool_max_chars=args.tool_max_chars,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
