#!/usr/bin/env python3
from __future__ import annotations

"""CLI：单次提问、交互模式、-v 日志、--trace 打印 state。"""
import argparse
import logging
import re
import sys

from config import LOG_TAG, OLLAMA_BASE_URL, OLLAMA_MODEL
from agent.loop import run_agent, run_agent_state, run_agent_verbose
from agent.state import AgentState, new_state

# 交互模式下跨轮次保留的 state；quit 后清空
_session: AgentState | None = None


def _setup_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format=f"%(levelname)s [{LOG_TAG}] %(message)s",
    )


def _print_trace(state: AgentState) -> None:
    print("\n--- trace (messages) ---")
    for i, m in enumerate(state.messages):
        print(f"[{i}] {m}")
    print(f"\n--- state: steps={state.steps}, tool_results={state.tool_results} ---")


def main() -> int:
    global _session

    parser = argparse.ArgumentParser(description="最小 Calculator Agent（Ollama + Tool Calling + Loop）")
    parser.add_argument("question", nargs="?", help="用户问题，例如：123 * 456 + 789 是多少？")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互模式（多轮共享 AgentState）")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印 tool 调用日志")
    parser.add_argument("--trace", action="store_true", help="打印 messages 与 state 摘要")
    parser.add_argument("--reset", action="store_true", help="交互模式下清空会话 state")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    print(f"LLM: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}")
    if not args.interactive:
        print("（单次命令 = 新会话，不含上一轮；多轮追问请用: python main.py -i）\n")
    else:
        print()

    def ask(q: str, *, continue_session: bool) -> None:
        global _session
        if continue_session and _session is not None:
            _session.refresh_system_prompt()
            _session.append_user(q)
            answer = run_agent_state(_session, log_steps=args.verbose)
        else:
            if args.trace:
                answer, _session = run_agent_verbose(q)
            else:
                _session = new_state(q)
                answer = run_agent_state(_session, log_steps=args.verbose)

        print(answer)
        if args.trace and _session is not None:
            _print_trace(_session)
        print()

    if args.interactive or not args.question:
        print("交互模式：多轮对话共用 messages（短期记忆）。输入 quit 退出，reset 清空会话。\n")
        while True:
            try:
                q = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q or q.lower() in ("quit", "exit", "q"):
                _session = None
                break
            if q.lower() == "reset":
                _session = None
                print("（已清空会话 state）\n")
                continue
            ask(q, continue_session=True)
        return 0

    if args.reset:
        _session = None
    if args.question and re.search(r"刚才|之前|上次|上一轮|上一个问题", args.question):
        print(
            "提示: 你正在单次命令模式，messages 里只有本条 user，没有上一条命令的历史。\n"
            "      若需「刚才我问了啥」，请先: python main.py -i\n",
            file=sys.stderr,
        )
    ask(args.question, continue_session=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
