from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from config import LOG_TAG, SOURCES_MAX_IN_PROMPT

logger = logging.getLogger(LOG_TAG)

_STRIP_TRACKING = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})


def normalize_url(url: str) -> str:
    url = url.strip()
    if not url or url.startswith("("):
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return url.lower()
    query = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.startswith("utm_") and k not in _STRIP_TRACKING
    ]
    cleaned = parsed._replace(query=urlencode(query), fragment="")
    return urlunparse(cleaned).rstrip("/")


def _parse_serp_style(result: str) -> list[dict[str, str]]:
    """解析 search_web / search_hn / fetch_rss 的「序号. 标题 + URL:」格式。"""
    entries: list[dict[str, str]] = []
    for block in re.split(r"\n---+\n", result):
        block = block.strip()
        if not block:
            continue
        lines = block.split("\n")
        title = ""
        url = ""
        m = re.match(r"^\d+\.\s+(.+)$", lines[0].strip())
        if m:
            title = m.group(1).strip()
        body_lines: list[str] = []
        for line in lines[1:]:
            if line.startswith("URL:"):
                url = line[4:].strip()
            elif line.strip():
                body_lines.append(line.strip())
        snippet = " ".join(body_lines)[:300]
        norm = normalize_url(url)
        if norm:
            entries.append({"title": title or norm, "url": url.strip(), "snippet": snippet})
    return entries


def extract_sources_from_tool(
    tool_name: str,
    arguments: dict[str, Any],
    result: str,
) -> list[dict[str, str]]:
    if not result or result.startswith("Error:"):
        return []

    if tool_name in ("search_web", "search_hn", "fetch_rss"):
        return _parse_serp_style(result)

    if tool_name == "fetch_url":
        url = str(arguments.get("url") or "").strip()
        norm = normalize_url(url)
        if not norm:
            return []
        snippet = result.replace("\n", " ")[:300]
        return [{"title": norm, "url": url, "snippet": snippet}]

    return []


def merge_sources(
    existing: list[dict[str, Any]],
    new_entries: list[dict[str, str]],
    *,
    via_tool: str,
) -> list[dict[str, Any]]:
    by_url: dict[str, dict[str, Any]] = {}
    for item in existing:
        key = item.get("norm_url") or normalize_url(str(item.get("url") or ""))
        if key:
            by_url[key] = item

    added = 0
    for entry in new_entries:
        norm = normalize_url(entry["url"])
        if not norm or norm in by_url:
            continue
        by_url[norm] = {
            "title": entry.get("title") or norm,
            "url": entry["url"],
            "norm_url": norm,
            "snippet": entry.get("snippet") or "",
            "via": via_tool,
        }
        added += 1

    merged = list(by_url.values())
    for i, item in enumerate(merged, start=1):
        item["id"] = i
    if added:
        logger.info("sources +%d (total %d)", added, len(merged))
    return merged


def format_sources_block(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""
    lines = [
        "【本轮已收集来源】正文与参考文献中的 URL 应优先来自下列列表；"
        "标题引用尽量与列表一致，勿编造未出现的链接。"
    ]
    for item in sources[:SOURCES_MAX_IN_PROMPT]:
        sid = item.get("id", "?")
        title = item.get("title") or ""
        url = item.get("url") or ""
        via = item.get("via") or ""
        suffix = f" ({via})" if via else ""
        lines.append(f"[{sid}] {title} — {url}{suffix}")
    if len(sources) > SOURCES_MAX_IN_PROMPT:
        lines.append(f"… 另有 {len(sources) - SOURCES_MAX_IN_PROMPT} 条未列出")
    return "\n".join(lines)
