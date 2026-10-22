from __future__ import annotations

from datetime import datetime

_SYSTEM_PROMPT_TEMPLATE = """你是一个有帮助的助手。

【系统环境】当前本地时间：{now_local}（日期以 YYYY-MM-DD 为准）。

规则：
- 需要精确数学表达式求值时，使用 calculator 工具，不要心算；得到 tool 结果后再组织回答。
- 聊天、概念解释、或上面已提供的系统环境能回答的问题（如「今天几号」），直接文字回答，不要调用 calculator。
- 只有注册了对应工具时，才去查实时外部数据；若没有合适工具，仍尽量用文字回答或说明局限，不要只回复「请提供工具」而拒绝作答。"""


def build_system_prompt() -> str:
    """每轮对话刷新 system：注入宿主当前时间（Agent 调优，非 Tool）。"""
    now_local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    return _SYSTEM_PROMPT_TEMPLATE.format(now_local=now_local)
