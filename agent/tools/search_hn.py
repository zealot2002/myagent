from __future__ import annotations

import logging
from typing import Any

import httpx

from agent.tools.schema import tool_schema
from agent.tools.types import Tool
from config import FETCH_TIMEOUT_SEC, HN_MAX_RESULTS, LOG_TAG

logger = logging.getLogger(LOG_TAG)

_HTTP_HEADERS = {"User-Agent": "myAgent/0.1 (learning bot)"}
_HN_ITEM_API = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
_HN_TOP_API = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ALGOLIA = "https://hn.algolia.com/api/v1/search"


def _format_hit(index: int, title: str, url: str, body: str) -> str:
    return f"{index}. {title}\nURL: {url or '(discussion only)'}\n{body}".strip()


def _fetch_item(client: httpx.Client, item_id: int) -> dict[str, Any] | None:
    resp = client.get(_HN_ITEM_API.format(id=item_id))
    resp.raise_for_status()
    data = resp.json()
    if not data or data.get("type") != "story":
        return None
    return data


def _story_lines(items: list[dict[str, Any]], max_results: int) -> list[str]:
    lines: list[str] = []
    for i, story in enumerate(items[:max_results], start=1):
        title = story.get("title") or "(no title)"
        url = story.get("url") or f"https://news.ycombinator.com/item?id={story.get('id')}"
        meta = []
        if story.get("score") is not None:
            meta.append(f"score={story['score']}")
        if story.get("descendants") is not None:
            meta.append(f"comments={story['descendants']}")
        if story.get("time"):
            meta.append(f"unix_time={story['time']}")
        body = " · ".join(meta) if meta else ""
        lines.append(_format_hit(i, title, url, body))
    return lines


def search_hn(query: str = "", max_results: int = 10) -> str:
    """Hacker News：无 API Key。空 query 取 top stories；有 query 走 Algolia 搜索。"""
    max_results = max(1, min(int(max_results), HN_MAX_RESULTS))
    timeout = httpx.Timeout(FETCH_TIMEOUT_SEC)

    try:
        with httpx.Client(
            trust_env=False,
            timeout=timeout,
            headers=_HTTP_HEADERS,
        ) as client:
            if query.strip():
                resp = client.get(
                    _HN_ALGOLIA,
                    params={
                        "query": query.strip(),
                        "tags": "story",
                        "hitsPerPage": max_results,
                    },
                )
                resp.raise_for_status()
                hits = resp.json().get("hits") or []
                stories = []
                for hit in hits:
                    stories.append(
                        {
                            "id": hit.get("objectID"),
                            "title": hit.get("title") or hit.get("story_title"),
                            "url": hit.get("url") or hit.get("story_url"),
                            "score": hit.get("points"),
                            "descendants": hit.get("num_comments"),
                            "time": hit.get("created_at_i"),
                        }
                    )
            else:
                resp = client.get(_HN_TOP_API)
                resp.raise_for_status()
                ids = (resp.json() or [])[: max_results * 2]
                stories = []
                for sid in ids:
                    if len(stories) >= max_results:
                        break
                    item = _fetch_item(client, int(sid))
                    if item:
                        stories.append(item)

        lines = _story_lines(stories, max_results)
        if not lines:
            return "Error: no HN results"
        logger.info("search_hn ok (%d hits, query=%r)", len(lines), query.strip() or "(top)")
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        logger.info("search_hn failed: %s", e)
        return f"Error: HN fetch failed: {e}"


SEARCH_HN = Tool(
    name="search_hn",
    schema=tool_schema(
        "search_hn",
        (
            "检索 Hacker News 热门或关键词故事（标题、链接、分数/评论数）。"
            "用于：科技圈热点、HN 讨论、英文 tech 资讯；query 留空则返回当前 top 条目。"
            "不要用于：非 HN 源、需要全文深度阅读（用 fetch_url）、通用网页搜索（用 search_web）。"
        ),
        {
            "query": {
                "type": "string",
                "description": "可选关键词；留空则 top stories",
            },
            "max_results": {
                "type": "integer",
                "description": f"条数，1–{HN_MAX_RESULTS}，默认 10",
            },
        },
        [],
    ),
    fn=search_hn,
)
