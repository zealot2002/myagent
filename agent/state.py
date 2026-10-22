from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.prompt import build_system_prompt


@dataclass
class AgentState:
    """
    Agent 的短期状态：Loop 每跑一轮都会读写这里。

    - messages：发给 LLM 的完整对话（含 system / user / assistant / tool），即短期记忆。
    - steps：累计 LLM 调用次数（含多轮用户对话、多步 Tool）。
    - tool_results：结构化留底，便于调试或以后做 Planning / 日志。
    """

    messages: list[dict] = field(default_factory=list)
    steps: int = 0
    tool_results: list[dict[str, Any]] = field(default_factory=list)

    def refresh_system_prompt(self) -> None:
        """更新 messages[0] 的 system（例如刷新注入的当前时间）。"""
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = build_system_prompt()
        else:
            self.messages.insert(0, {"role": "system", "content": build_system_prompt()})

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_tool_result(self, name: str, result: str) -> None:
        self.tool_results.append({"name": name, "result": result})


def new_state(user_input: str) -> AgentState:
    """新任务：system + 第一条 user。"""
    return AgentState(
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": user_input},
        ]
    )
