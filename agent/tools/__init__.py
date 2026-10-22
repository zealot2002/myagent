from __future__ import annotations

from agent.tools.calculator import CALCULATOR
from agent.tools.registry import build_registry, execute_tool as _execute_tool

# 新增 Tool：在此 import 并加入 ALL_TOOLS
ALL_TOOLS = [
    CALCULATOR,
]

TOOL_DEFINITIONS, _BY_NAME = build_registry(ALL_TOOLS)


def execute_tool(name: str, arguments: dict) -> str:
    return _execute_tool(_BY_NAME, name, arguments)


__all__ = ["ALL_TOOLS", "TOOL_DEFINITIONS", "execute_tool"]
