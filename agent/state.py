from __future__ import annotations

"""Project 3+：显式 Agent 状态（为后续 Memory / Planning 预留）。"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    messages: list[dict] = field(default_factory=list)
    steps: int = 0
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def append_tool_result(self, name: str, result: str) -> None:
        self.tool_results.append({"name": name, "result": result})
