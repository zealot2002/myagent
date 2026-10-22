from __future__ import annotations

import json
import logging
from typing import Any

from openai.types.chat import ChatCompletionMessage

from config import AGENT_MAX_STEPS, LOG_TAG
from agent.context import prepare_messages
from agent.llm import chat
from agent.state import AgentState, new_state
from agent.tools import TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger(LOG_TAG)


def _build_assistant_turn(message: ChatCompletionMessage) -> dict[str, Any]:
    """
    博文伪代码里的 assistant_turn：本轮 assistant 消息 dict，追加到 messages。

    - 无 Tool 时：通常只有 content（最终答案或中间说明）。
    - 有 Tool 时：content 常为空，模型把调用意图放在 tool_calls（name + arguments JSON）。
    下一轮 LLM 必须看到完整的 assistant_turn，协议才连贯。
    """
    assistant_turn: dict[str, Any] = {
        "role": "assistant",
        "content": message.content or "",
    }
    if message.tool_calls:
        assistant_turn["tool_calls"] = [
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
    return assistant_turn


def _tool_result_turn(tool_call_id: str, name: str, content: str) -> dict[str, Any]:
    """
    博文伪代码里 execute_tool 之后 append 的 observation。
    role=tool，content 为工具返回字符串（含 Error: ... 时也原样给模型看）。
    """
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": name,
        "content": content,
    }


def _agent_loop(state: AgentState, steps_limit: int, *, log_steps: bool) -> str:
    """
    最小 Agent Loop（与博文一致）::

        while step < MAX_STEPS:
            response = llm(messages, tools=tools)
            if response.has_tool_call:
                result = execute_tool(...)
                messages.append(assistant_turn)
                messages.append(tool_result_turn)
            else:
                return response.text

    状态落在 state.messages；每 call 一次 LLM，state.steps += 1。
    """
    messages = state.messages

    for loop_i in range(1, steps_limit + 1):
        state.steps += 1
        if log_steps:
            logger.info(
                "agent loop %s/%s, cumulative llm_calls=%s",
                loop_i,
                steps_limit,
                state.steps,
            )

        prepare_messages(messages)
        completion = chat(messages, tools=TOOL_DEFINITIONS)
        message = completion.choices[0].message

        assistant_turn = _build_assistant_turn(message)
        messages.append(assistant_turn)

        if not message.tool_calls:
            return (message.content or "").strip()

        for tc in message.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if log_steps:
                logger.info("tool call: %s(%s)", name, args)
            result = execute_tool(name, args)
            state.append_tool_result(name, result)
            if log_steps:
                logger.info("tool result: %s", result)
            messages.append(_tool_result_turn(tc.id, name, result))

    return "达到最大步数，未能给出最终答案。请增大 AGENT_MAX_STEPS 或简化问题。"


def run_agent_state(
    state: AgentState,
    *,
    max_steps: int | None = None,
    log_steps: bool = True,
) -> str:
    """在已有 AgentState 上继续跑 Loop（单问或多轮对话共用）。"""
    steps_limit = max_steps if max_steps is not None else AGENT_MAX_STEPS
    return _agent_loop(state, steps_limit, log_steps=log_steps)


def run_agent(user_input: str, *, max_steps: int | None = None) -> str:
    """单次提问：新建 state → Loop → 返回答案。"""
    state = new_state(user_input)
    return run_agent_state(state, max_steps=max_steps, log_steps=True)


def run_agent_verbose(user_input: str, *, max_steps: int | None = None) -> tuple[str, AgentState]:
    """单次提问，返回最终 state（--trace 用）。"""
    state = new_state(user_input)
    answer = run_agent_state(state, max_steps=max_steps, log_steps=False)
    return answer, state
