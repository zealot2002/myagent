#!/usr/bin/env python3
"""压测对比：无 trim vs 有 trim（同一 num_ctx，最后一轮问「最早是第几块」）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "scripts" / "simulate_context_window.py"
PY = ROOT / ".venv" / "bin" / "python"

COMMON = [
    str(PY),
    str(SIM),
    "--num-ctx",
    "256",
    "--chunk-chars",
    "4000",
    "--max-rounds",
    "6",
]


def _run(label: str, extra: list[str]) -> None:
    print("=" * 60)
    print(label)
    print("=" * 60)
    subprocess.run(COMMON + extra, cwd=ROOT, check=False)


def main() -> int:
    if not PY.is_file():
        print("请先创建 .venv", file=sys.stderr)
        return 1
    _run("A. 无 trim（依赖 Ollama 静默截断）", [])
    _run("B. 有 trim（prepare_messages max_tokens=1200）", ["--with-trim", "--max-tokens", "1200"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
