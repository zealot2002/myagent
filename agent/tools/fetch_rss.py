from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urlparse

import feedparser
import httpx

from agent.tools.schema import tool_schema
from agent.tools.types import Tool
from config import FETCH_TIMEOUT_SEC, LOG_TAG, RSS_MAX_BYTES, RSS_MAX_ENTRIES

logger = logging.getLogger(LOG_TAG)

_HTTP_HEADERS = {"User-Agent": "myAgent/0.1 (learning bot)"}


class _StripHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._parts.append(data.strip())

    def text(self) -> str:
        return " ".join(self._parts)


def _plain_summary(raw: str, limit: int = 400) -> str:
    if not raw:
        return ""
    if "<" in raw and ">" in raw:
        parser = _StripHTML()
        try:
            parser.feed(raw)
            raw = parser.text()
        except Exception:
            pass
    raw = " ".join(raw.split())
    if len(raw) > limit:
        return raw[:limit] + "…"
    return raw


def fetch_rss(feed_url: str, max_entries: int = 10) -> str:
    """拉取 RSS/Atom 源，返回最近条目（标题、链接、摘要）。无 API Key。"""
    parsed = urlparse(feed_url.strip())
    if parsed.scheme not in ("http", "https"):
        return "Error: only http/https feed URLs are allowed"
    if not parsed.netloc:
        return "Error: invalid feed url"

    max_entries = max(1, min(int(max_entries), RSS_MAX_ENTRIES))

    try:
        with httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(FETCH_TIMEOUT_SEC),
            headers=_HTTP_HEADERS,
        ) as client:
            resp = client.get(feed_url.strip())
            resp.raise_for_status()
            raw = resp.content[:RSS_MAX_BYTES]

        parsed_feed = feedparser.parse(raw)
        if parsed_feed.bozo and not parsed_feed.entries:
            return f"Error: RSS parse failed: {parsed_feed.bozo_exception}"

        lines: list[str] = []
        for i, entry in enumerate(parsed_feed.entries[:max_entries], start=1):
            title = entry.get("title") or "(no title)"
            link = entry.get("link") or ""
            summary = _plain_summary(
                entry.get("summary") or entry.get("description") or "",
            )
            published = entry.get("published") or entry.get("updated") or ""
            body = summary
            if published:
                body = f"{published}\n{summary}".strip()
            lines.append(f"{i}. {title}\nURL: {link}\n{body}".strip())

        if not lines:
            return "Error: empty feed"
        logger.info("fetch_rss ok (%d entries, %s)", len(lines), parsed.netloc)
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        logger.info("fetch_rss failed: %s", e)
        return f"Error: RSS fetch failed: {e}"


FETCH_RSS = Tool(
    name="fetch_rss",
    schema=tool_schema(
        "fetch_rss",
        (
            "读取 RSS/Atom 订阅 URL，返回最近条目（标题、链接、摘要）。"
            "用于：已知 feed 地址的资讯聚合（如官方博客 RSS、hnrss.org 等）。"
            "不要用于：未知链接的全网搜索（用 search_web）、单篇 HTML 全文（用 fetch_url）。"
        ),
        {
            "feed_url": {
                "type": "string",
                "description": "RSS/Atom 地址，如 https://hnrss.org/frontpage",
            },
            "max_entries": {
                "type": "integer",
                "description": f"条数，1–{RSS_MAX_ENTRIES}，默认 10",
            },
        },
        ["feed_url"],
    ),
    fn=fetch_rss,
)
