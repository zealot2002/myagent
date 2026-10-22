from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.prompt import build_system_prompt
from agent.sources import format_sources_block


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
    sources: list[dict[str, Any]] = field(default_factory=list)

    def sync_system_message(self) -> None:
        """刷新 system：基础 prompt + 当前 sources 块。"""
        base = build_system_prompt()
        block = format_sources_block(self.sources)
        content = f"{base}\n\n{block}" if block else base
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = content
        else:
            self.messages.insert(0, {"role": "system", "content": content})

    def refresh_system_prompt(self) -> None:
        """更新 messages[0] 的 system（时间刷新 + sources 注入）。"""
        self.sync_system_message()

    def ingest_tool_sources(self, tool_name: str, arguments: dict[str, Any], result: str) -> None:
        from agent.sources import extract_sources_from_tool, merge_sources

        new_entries = extract_sources_from_tool(tool_name, arguments, result)
        if not new_entries:
            return
        self.sources = merge_sources(self.sources, new_entries, via_tool=tool_name)
        self.sync_system_message()

    def append_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_tool_result(self, name: str, result: str) -> None:
        self.tool_results.append({"name": name, "result": result})


def empty_state() -> AgentState:
    """仅 system，供网页会话等多轮入口。"""
    state = AgentState()
    state.sync_system_message()
    return state


def new_state(user_input: str) -> AgentState:
    """新任务：system + 第一条 user。"""
    state = empty_state()
    state.append_user(user_input)
    return state
