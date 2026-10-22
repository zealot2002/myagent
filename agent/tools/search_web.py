from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from typing import Callable

import httpx

from agent.tools.schema import tool_schema
from agent.tools.types import Tool
from config import LOG_TAG, SEARCH_BUDGET_SEC, SEARCH_TIMEOUT_SEC

logger = logging.getLogger(LOG_TAG)

try:
    from ddgs import DDGS
except ImportError:  # pragma: no cover
    DDGS = None  # type: ignore

_HTTP_HEADERS = {"User-Agent": "myAgent/0.1 (learning bot)"}

# 无 API Key 的公开源；顺序 = 先快后慢、先广后专
_SEARX_INSTANCES = (
    "https://searx.be",
    "https://search.ononoki.org",
    "https://paulgo.io",
)


def _format_hit(title: str, url: str, body: str, index: int) -> str:
    return f"{index}. {title}\nURL: {url}\n{body}".strip()


def _run_bounded(
    fn: Callable[..., list[str]],
    timeout_sec: float,
    *args: object,
) -> list[str]:
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args)
        try:
            return fut.result(timeout=timeout_sec)
        except FuturesTimeout as e:
            raise TimeoutError(f"timed out after {timeout_sec}s") from e


def _search_ddgs(query: str, max_results: int) -> list[str]:
    if DDGS is None:
        return []
    lines: list[str] = []
    with DDGS() as ddgs:
        for i, item in enumerate(ddgs.text(query, max_results=max_results), start=1):
            title = item.get("title") or ""
            href = item.get("href") or item.get("link") or ""
            body = item.get("body") or item.get("snippet") or ""
            lines.append(_format_hit(title, href, body, i))
    return lines


def _search_duckduckgo_instant(query: str, max_results: int) -> list[str]:
    with httpx.Client(
        trust_env=False,
        timeout=SEARCH_TIMEOUT_SEC,
        headers=_HTTP_HEADERS,
    ) as client:
        resp = client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
        )
        resp.raise_for_status()
        data = resp.json()

    lines: list[str] = []
    if data.get("AbstractText"):
        lines.append(
            _format_hit(
                data.get("Heading") or "Summary",
                data.get("AbstractURL") or "",
                data.get("AbstractText") or "",
                1,
            )
        )
    for topic in data.get("RelatedTopics") or []:
        if len(lines) >= max_results:
            break
        if isinstance(topic, dict) and topic.get("Text"):
            lines.append(
                _format_hit(
                    topic["Text"],
                    topic.get("FirstURL") or "",
                    "",
                    len(lines) + 1,
                )
            )
    return lines[:max_results]


def _search_wikipedia(query: str, max_results: int) -> list[str]:
    lines: list[str] = []
    timeout = httpx.Timeout(SEARCH_TIMEOUT_SEC)
    with httpx.Client(trust_env=False, timeout=timeout, headers=_HTTP_HEADERS) as client:
        for lang in ("zh", "en"):
            if len(lines) >= max_results:
                break
            resp = client.get(
                f"https://{lang}.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": max_results,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            for item in resp.json().get("query", {}).get("search", []):
                if len(lines) >= max_results:
                    break
                title = item.get("title") or ""
                url = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                snippet = item.get("snippet") or ""
                lines.append(_format_hit(title, url, snippet, len(lines) + 1))
    return lines


def _search_qwant(query: str, max_results: int) -> list[str]:
    with httpx.Client(
        trust_env=False,
        timeout=SEARCH_TIMEOUT_SEC,
        headers=_HTTP_HEADERS,
    ) as client:
        resp = client.get(
            "https://api.qwant.com/v3/search/web",
            params={"q": query, "count": max_results, "locale": "zh_CN"},
        )
        resp.raise_for_status()
        data = resp.json()

    items = (
        data.get("data", {})
        .get("result", {})
        .get("items", [])
    )
    lines: list[str] = []
    for i, item in enumerate(items[:max_results], start=1):
        lines.append(
            _format_hit(
                item.get("title") or "",
                item.get("url") or item.get("link") or "",
                item.get("desc") or item.get("description") or "",
                i,
            )
        )
    return lines


def _search_searx(query: str, max_results: int) -> list[str]:
    timeout = httpx.Timeout(SEARCH_TIMEOUT_SEC)
    with httpx.Client(trust_env=False, timeout=timeout, headers=_HTTP_HEADERS) as client:
        for base in _SEARX_INSTANCES:
            try:
                resp = client.get(
                    f"{base.rstrip('/')}/search",
                    params={"q": query, "format": "json", "language": "zh-CN"},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue
            results = data.get("results") or []
            if not results:
                continue
            lines: list[str] = []
            for i, item in enumerate(results[:max_results], start=1):
                lines.append(
                    _format_hit(
                        item.get("title") or "",
                        item.get("url") or "",
                        item.get("content") or "",
                        i,
                    )
                )
            return lines
    return []


_PROVIDERS: tuple[tuple[str, Callable[[str, int], list[str]]], ...] = (
    ("ddgs", _search_ddgs),
    ("duckduckgo_instant", _search_duckduckgo_instant),
    ("wikipedia", _search_wikipedia),
    ("qwant", _search_qwant),
    ("searx", _search_searx),
)


def search_web(query: str, max_results: int = 5) -> str:
    """返回标题、URL、摘要文本，供模型决定是否 fetch_url。"""
    if not query.strip():
        return "Error: empty query"
    max_results = max(1, min(int(max_results), 10))
    q = query.strip()

    failures: list[str] = []
    deadline = time.monotonic() + SEARCH_BUDGET_SEC
    for name, provider in _PROVIDERS:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failures.append("budget exhausted")
            logger.info("search_web budget exhausted")
            break
        per_call = min(SEARCH_TIMEOUT_SEC, remaining)
        try:
            lines = _run_bounded(provider, per_call, q, max_results)
        except Exception as e:
            failures.append(f"{name}: {e}")
            logger.info("search_web %s failed: %s", name, e)
            continue
        if lines:
            logger.info("search_web %s ok (%d hits)", name, len(lines))
            return "\n\n---\n\n".join(lines)
        failures.append(f"{name}: no results")
        logger.info("search_web %s empty", name)

    detail = "; ".join(failures) if failures else "no providers"
    return f"Error: search failed ({detail})"


SEARCH_WEB = Tool(
    name="search_web",
    schema=tool_schema(
        "search_web",
        (
            "在互联网上检索摘要与链接。"
            "用于：需要外部事实、新闻、文档、网页地址，且 system 与 calculator 无法回答时。"
            "不要用于：纯数学表达式（用 calculator）、仅解释概念、或 user 已给出完整 URL（用 fetch_url）。"
        ),
        {
            "query": {"type": "string", "description": "检索关键词或问句，例如 Python asyncio tutorial"},
            "max_results": {
                "type": "integer",
                "description": "返回条数，1–10，默认 5",
            },
        },
        ["query"],
    ),
    fn=search_web,
)
