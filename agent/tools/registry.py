from __future__ import annotations

import logging
from typing import Any

from agent.tools.types import Tool
from config import LOG_TAG

logger = logging.getLogger(LOG_TAG)


def build_registry(tools: list[Tool]) -> tuple[list[dict], dict[str, Tool]]:
    """
    从 Tool 列表生成：
    - schemas → 传给 LLM 的 TOOL_DEFINITIONS
    - by_name → 执行时按 name 查找 Python 实现
    """
    by_name: dict[str, Tool] = {}
    schemas: list[dict] = []
    for t in tools:
        if t.name in by_name:
            raise ValueError(f"duplicate tool name: {t.name}")
        by_name[t.name] = t
        schemas.append(t.schema)
    return schemas, by_name


def execute_tool(by_name: dict[str, Tool], name: str, arguments: dict[str, Any]) -> str:
    """模型提议的 function call 在此落地；异常转为 Error 字符串，避免打断 Loop。"""
    tool = by_name.get(name)
    if tool is None:
        logger.warning("unknown tool requested: %s", name)
        return f"Error: unknown tool '{name}'"
    try:
        return tool.fn(**arguments)
    except Exception as e:
        logger.warning("tool %s failed: %s", name, e)
        return f"Error: {e}"
