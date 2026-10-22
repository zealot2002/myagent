from __future__ import annotations

from agent.tools.calculator import CALCULATOR
from agent.tools.fetch_rss import FETCH_RSS
from agent.tools.fetch_url import FETCH_URL
from agent.tools.save_markdown import SAVE_MARKDOWN
from agent.tools.search_hn import SEARCH_HN
from agent.tools.search_web import SEARCH_WEB
from agent.tools.registry import build_registry, execute_tool as _execute_tool

# 新增 Tool：import 后 append，Loop 无需修改
ALL_TOOLS = [
    CALCULATOR,
    SEARCH_WEB,
    SEARCH_HN,
    FETCH_RSS,
    FETCH_URL,
    SAVE_MARKDOWN,
]

TOOL_DEFINITIONS, _BY_NAME = build_registry(ALL_TOOLS)


def execute_tool(name: str, arguments: dict) -> str:
    """Loop 调用的统一入口。"""
    return _execute_tool(_BY_NAME, name, arguments)


__all__ = ["ALL_TOOLS", "TOOL_DEFINITIONS", "execute_tool"]
