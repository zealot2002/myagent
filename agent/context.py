from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from config import CONTEXT_MAX_TOKENS, CONTEXT_TOOL_MAX_CHARS, CONTEXT_TRIM_ENABLED, LOG_TAG

logger = logging.getLogger(LOG_TAG)

_TRUNC_SUFFIX = "\n…(content truncated)"
_OMITTED_NOTICE = "\n\n【注意】更早的对话已因上下文长度限制被省略，请勿假设仍能看到被删内容。"


@dataclass
class TrimStats:
    """一次 prepare 的统计，便于日志与压测对比。"""

    enabled: bool
    tokens_before: int
    tokens_after: int
    tools_truncated: int = 0
    messages_dropped: int = 0
    notice_added: bool = False

    @property
    def trimmed(self) -> bool:
        return self.tools_truncated > 0 or self.messages_dropped > 0 or self.notice_added


def estimate_tokens(text: str) -> int:
    """粗估 token：混合中英文时用 len/3，与压测脚本一致。"""
    if not text:
        return 0
    return max(1, len(text) // 3)


def estimate_messages_tokens(messages: list[dict]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(str(m.get("content") or ""))
        if m.get("tool_calls"):
            total += estimate_tokens(json.dumps(m["tool_calls"], ensure_ascii=False))
    return total


def _truncate_tool_contents_inplace(messages: list[dict], max_chars: int, stats: TrimStats) -> None:
    if max_chars <= 0:
        return
    for m in messages:
        if m.get("role") != "tool":
            continue
        content = str(m.get("content") or "")
        if len(content) <= max_chars:
            continue
        keep = max(0, max_chars - len(_TRUNC_SUFFIX))
        m["content"] = content[:keep] + _TRUNC_SUFFIX
        stats.tools_truncated += 1


def _sliding_window_inplace(messages: list[dict], max_tokens: int, stats: TrimStats) -> None:
    """保留 system（若有），从最旧的消息起删，直到估 token 低于预算或只剩 system+一条。"""
    while len(messages) > 2 and estimate_messages_tokens(messages) > max_tokens:
        del messages[1]
        stats.messages_dropped += 1


def _append_omit_notice_to_system(messages: list[dict], stats: TrimStats) -> None:
    if stats.messages_dropped <= 0 or not messages:
        return
    if messages[0].get("role") != "system":
        messages.insert(0, {"role": "system", "content": _OMITTED_NOTICE.strip()})
        stats.notice_added = True
        return
    content = str(messages[0].get("content") or "")
    if _OMITTED_NOTICE.strip() in content:
        return
    messages[0]["content"] = content + _OMITTED_NOTICE
    stats.notice_added = True


def prepare_messages(
    messages: list[dict],
    *,
    max_tokens: int | None = None,
    tool_max_chars: int | None = None,
    enabled: bool | None = None,
) -> TrimStats:
    """
    在每次 LLM 请求前调用：就地截断 tool 正文 + 滑窗删旧消息。
    返回统计；messages 会被修改。
    """
    use_enabled = CONTEXT_TRIM_ENABLED if enabled is None else enabled
    budget = max_tokens if max_tokens is not None else CONTEXT_MAX_TOKENS
    tool_cap = tool_max_chars if tool_max_chars is not None else CONTEXT_TOOL_MAX_CHARS

    before = estimate_messages_tokens(messages)
    stats = TrimStats(enabled=use_enabled, tokens_before=before, tokens_after=before)

    if not use_enabled or budget <= 0:
        return stats

    _truncate_tool_contents_inplace(messages, tool_cap, stats)
    _sliding_window_inplace(messages, budget, stats)
    if stats.messages_dropped > 0:
        _append_omit_notice_to_system(messages, stats)

    stats.tokens_after = estimate_messages_tokens(messages)
    if stats.trimmed:
        logger.info(
            "context trim: tokens %s→%s, dropped_msgs=%s, tools_truncated=%s",
            stats.tokens_before,
            stats.tokens_after,
            stats.messages_dropped,
            stats.tools_truncated,
        )
    return stats
