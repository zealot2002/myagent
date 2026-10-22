from __future__ import annotations

import json
import logging
from datetime import datetime

from config import AGENT_MAX_STEPS, LOG_TAG
from agent.llm import chat
from agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(LOG_TAG)

_SYSTEM_PROMPT_TEMPLATE = """你是一个有帮助的助手。

【系统环境】当前本地时间：{now_local}（日期以 YYYY-MM-DD 为准）。

规则：
- 需要精确数学表达式求值时，使用 calculator 工具，不要心算；得到 tool 结果后再组织回答。
- 聊天、概念解释、或上面已提供的系统环境能回答的问题（如「今天几号」），直接文字回答，不要调用 calculator。
- 只有注册了对应工具时，才去查实时外部数据；若没有合适工具，仍尽量用文字回答或说明局限，不要只回复「请提供工具」而拒绝作答。"""


def build_system_prompt() -> str:
    now_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    return _SYSTEM_PROMPT_TEMPLATE.format(now_local=now_local)


def _tool_result_message(tool_call_id: str, name: str, content: str) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
    }


def run_agent(user_input: str, *, max_steps: int | None = None) -> str:
    """
    最小 Agent Loop:
      LLM → tool call? → execute → observation → LLM → … → 最终文本
    """
    steps_limit = max_steps if max_steps is not None else AGENT_MAX_STEPS
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_input},
    ]

    for step in range(steps_limit):
        logger.info("agent step %s/%s", step + 1, steps_limit)
        completion = chat(messages, tools=TOOL_DEFINITIONS)
        choice = completion.choices[0]
        message = choice.message

        assistant_msg: dict = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        if not message.tool_calls:
            return (message.content or "").strip()

        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            logger.info("tool call: %s(%s)", name, args)
            result = execute_tool(name, args)
            logger.info("tool result: %s", result)
            messages.append(_tool_result_message(tc.id, name, result))

    return "达到最大步数，未能给出最终答案。请增大 AGENT_MAX_STEPS 或简化问题。"


def run_agent_verbose(user_input: str, *, max_steps: int | None = None) -> tuple[str, list[dict]]:
    """与 run_agent 相同，但返回完整 messages 便于调试 ReAct 轨迹。"""
    steps_limit = max_steps if max_steps is not None else AGENT_MAX_STEPS
    messages: list[dict] = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_input},
    ]

    for step in range(steps_limit):
        completion = chat(messages, tools=TOOL_DEFINITIONS)
        message = completion.choices[0].message

        assistant_msg: dict = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        messages.append(assistant_msg)

        if not message.tool_calls:
            return (message.content or "").strip(), messages

        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute_tool(name, args)
            messages.append(_tool_result_message(tc.id, name, result))

    return "达到最大步数。", messages
