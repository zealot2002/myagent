from __future__ import annotations

import logging
from pathlib import Path

from agent.tools.schema import tool_schema
from agent.tools.types import Tool
from config import LOG_TAG, REPORTS_DIR, SAVE_MARKDOWN_MAX_BYTES

logger = logging.getLogger(LOG_TAG)


def _resolve_path(filename: str) -> Path:
    raw = filename.strip().replace("\\", "/")
    if not raw:
        raise ValueError("empty filename")
    if raw.startswith("/") or raw.startswith("~"):
        raise ValueError("absolute paths are not allowed")
    parts = [p for p in raw.split("/") if p and p != "."]
    if ".." in parts:
        raise ValueError("'..' is not allowed")
    if parts and parts[0] == "reports":
        parts = parts[1:]
    if not parts:
        raise ValueError("need a filename under reports/")
    rel = "/".join(parts)
    if not rel.lower().endswith(".md"):
        rel = f"{rel}.md"

    root = Path(REPORTS_DIR).resolve()
    target = (root / rel).resolve()
    if root != target and root not in target.parents:
        raise ValueError("path must stay under reports/")
    return target


def save_markdown(filename: str, content: str) -> str:
    """将 Markdown 写入项目 reports/ 目录（沙箱路径）。"""
    try:
        path = _resolve_path(filename)
    except ValueError as e:
        return f"Error: {e}"

    body = content if content is not None else ""
    encoded = body.encode("utf-8")
    if len(encoded) > SAVE_MARKDOWN_MAX_BYTES:
        return f"Error: content too large ({len(encoded)} bytes, max {SAVE_MARKDOWN_MAX_BYTES})"

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    except OSError as e:
        logger.warning("save_markdown write failed: %s", e)
        return f"Error: write failed: {e}"

    rel = path.relative_to(Path(REPORTS_DIR).resolve())
    logger.info("save_markdown wrote %s (%d bytes)", path, len(encoded))
    return f"Saved: {REPORTS_DIR}/{rel.as_posix()}"


SAVE_MARKDOWN = Tool(
    name="save_markdown",
    schema=tool_schema(
        "save_markdown",
        (
            "把完整 Markdown 报告写入 reports/ 目录下的 .md 文件。"
            "用于：用户要求「报告 / 调研 / 保存到 reports/xxx.md」等交付落盘。"
            "不要用于：尚未撰写正文、只有大纲或模板、或用户未要求保存文件。"
            "保存前应先 search_web / fetch_url 收集事实；content 须为完整 Markdown（含标题与参考文献）。"
        ),
        {
            "filename": {
                "type": "string",
                "description": "相对 reports/ 的路径，如 python-313.md 或 reports/python-313.md",
            },
            "content": {
                "type": "string",
                "description": "要写入的完整 Markdown 正文",
            },
        },
        ["filename", "content"],
    ),
    fn=save_markdown,
)
