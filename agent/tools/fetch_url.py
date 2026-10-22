from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from agent.tools.schema import tool_schema
from agent.tools.types import Tool
from config import FETCH_MAX_BYTES, FETCH_TIMEOUT_SEC

_STRIP_RE = re.compile(r"\s+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip = False

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return _STRIP_RE.sub(" ", " ".join(self._chunks)).strip()


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return _STRIP_RE.sub(" ", re.sub(r"<[^>]+>", " ", html)).strip()
    return parser.text()


def fetch_url(url: str) -> str:
    """GET 页面并提取可读文本（非完整渲染）。"""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return "Error: only http/https URLs are allowed"
    if not parsed.netloc:
        return "Error: invalid url"

    try:
        with httpx.Client(
            trust_env=False,
            timeout=httpx.Timeout(FETCH_TIMEOUT_SEC),
            follow_redirects=True,
        ) as client:
            resp = client.get(
                url.strip(),
                headers={"User-Agent": "myAgent/0.1 (learning bot)"},
            )
            resp.raise_for_status()
            raw = resp.content[:FETCH_MAX_BYTES]
            ctype = (resp.headers.get("content-type") or "").lower()
            text = raw.decode(resp.encoding or "utf-8", errors="replace")
            if "html" in ctype or text.lstrip().startswith("<"):
                text = _html_to_text(text)
            if len(text) > 8000:
                text = text[:8000] + "\n…(fetch truncated in tool)"
            return text or "Error: empty page"
    except Exception as e:
        return f"Error: fetch failed: {e}"


FETCH_URL = Tool(
    name="fetch_url",
    schema=tool_schema(
        "fetch_url",
        (
            "请求一个 http/https URL，返回页面正文文本（简化提取）。"
            "用于：已有明确链接、需要读正文细节。"
            "不要用于：还没有 URL 时（先用 search_web）、纯计算（calculator）。"
        ),
        {"url": {"type": "string", "description": "完整 URL，以 http:// 或 https:// 开头"}},
        ["url"],
    ),
    fn=fetch_url,
)
