#!/usr/bin/env python3
import argparse
import logging
import sys

from config import LOG_TAG, OLLAMA_BASE_URL, OLLAMA_MODEL
from agent.loop import run_agent, run_agent_verbose


def _setup_logging(verbose: bool) -> None:
    level = logging.INFO if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format=f"%(levelname)s [{LOG_TAG}] %(message)s",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="最小 Calculator Agent（Ollama + Tool Calling + Loop）")
    parser.add_argument("question", nargs="?", help="用户问题，例如：123 * 456 + 789 是多少？")
    parser.add_argument("-i", "--interactive", action="store_true", help="交互模式")
    parser.add_argument("-v", "--verbose", action="store_true", help="打印 tool 调用日志")
    parser.add_argument("--trace", action="store_true", help="打印完整 message 轨迹")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    print(f"LLM: {OLLAMA_MODEL} @ {OLLAMA_BASE_URL}\n")

    def ask(q: str) -> None:
        if args.trace:
            answer, messages = run_agent_verbose(q)
            print(answer)
            print("\n--- trace ---")
            for i, m in enumerate(messages):
                print(f"[{i}] {m}")
        else:
            print(run_agent(q))
        print()

    if args.interactive or not args.question:
        print("交互模式，输入 quit 退出。\n")
        while True:
            try:
                q = input("你> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not q or q.lower() in ("quit", "exit", "q"):
                break
            ask(q)
        return 0

    ask(args.question)
    return 0


if __name__ == "__main__":
    sys.exit(main())
