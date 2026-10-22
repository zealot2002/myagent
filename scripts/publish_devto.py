#!/usr/bin/env python3
"""Publish docs/*.md to DEV.to (requires DEVTO_API_KEY)."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
GITHUB = "https://github.com/zealot2002/myagent"
RAW = f"{GITHUB}/raw/main/docs"
# 换图后 DEV / CDN 可能仍缓存 raw URL，发布时可设 IMAGE_CACHE_BUST=1 或 git rev
IMAGE_CACHE_BUST = os.getenv("IMAGE_CACHE_BUST", "")

SERIES = "从零手写 Agent"
DEFAULT_TAGS = ["ai", "agents", "python", "ollama"]

# part -> (filename, skip if already on dev)
# 无 H1 时 DEV 标题（与系列导读一致）
FILE_TITLES: dict[str, str] = {
    "01-理解Agent里的Tool.md": "从零手写 Agent（一）：Tool 把我从 Chat 拽进了 Loop",
    "02-上下文窗口与多轮对话.md": "从零手写 Agent（二）：短期记忆，其实就是你一直带着的 messages",
    "03-上下文超长怎么办.md": "从零手写 Agent（三）：上下文超长，别等模型替你截断",
    "04-多Tool与联网检索.md": "从零手写 Agent（四）：多 Tool 与联网检索——Loop 还是那个 Loop",
    "05-调研报告与引用.md": "从零手写 Agent（五）：调研报告、引用与落盘——Loop 仍不变",
    "06-云模型与网页调研台.md": "从零手写 Agent（六）：云模型 API Key 与网页调研台——Loop 仍不变",
    "07-与商用Agent还差什么.md": "从零手写 Agent（七）：和商用 Agent 还差什么——个人调研 Agent 的边界",
}

ARTICLES = [
    (1, "01-理解Agent里的Tool.md", False),
    (2, "02-上下文窗口与多轮对话.md", False),
    (3, "03-上下文超长怎么办.md", False),
    (4, "04-多Tool与联网检索.md", False),
    (5, "05-调研报告与引用.md", False),
    (6, "06-云模型与网页调研台.md", False),
    (7, "07-与商用Agent还差什么.md", False),
]


def load_markdown(path: Path) -> tuple[str, str, list[str]]:
    text = path.read_text(encoding="utf-8")
    tags = DEFAULT_TAGS
    title = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            text = text[end + 4 :].lstrip("\n")
            m = re.search(r"^tags:\s*\[(.*)\]", fm, re.M)
            if m:
                raw = m.group(1)
                parsed = [t.strip().strip("'\"") for t in raw.split(",") if t.strip()]
                if parsed:
                    tags = [t.lower().replace(" ", "")[:20] for t in parsed[:4]]
            m = re.search(r"^title:\s*(.+)$", fm, re.M)
            if m:
                title = m.group(1).strip().strip("'\"")
    if not title:
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = FILE_TITLES.get(path.name, "")
    if not title:
        raise ValueError(f"No title in {path} (need # H1, frontmatter title, or FILE_TITLES)")
    if not text.lstrip().startswith("# "):
        text = f"# {title}\n\n{text}"
    return title, text, tags


def devify_body(body: str, *, series: str = SERIES) -> str:
    if not body.lstrip().startswith("---"):
        body = f"---\nseries: {series}\n---\n\n{body}"
    body = re.sub(
        r"\]\(\./([^)]+\.md)\)",
        lambda m: f"]({GITHUB}/blob/main/docs/{m.group(1)})",
        body,
    )
    bust = IMAGE_CACHE_BUST.strip()

    def _img_url(name: str) -> str:
        url = f"{RAW}/images/{name}"
        return f"{url}?v={bust}" if bust else url

    body = re.sub(
        r"\]\(\./images/([^)]+)\)",
        lambda m: f"]({_img_url(m.group(1))})",
        body,
    )
    body = body.replace("系列目录：[系列导读]", f"系列目录：[GitHub docs]({GITHUB}/tree/main/docs)")
    return body


def create_article(client: httpx.Client, title: str, body: str, tags: list[str], *, dry_run: bool) -> dict:
    payload = {
        "article": {
            "title": title,
            "body_markdown": body,
            "published": True,
            "series": SERIES,
            "tags": tags[:4],
        }
    }
    if dry_run:
        print(f"[dry-run] {title} ({len(body)} chars, tags={tags[:4]})")
        return {"url": "dry-run"}
    for attempt in range(6):
        r = client.post("https://dev.to/api/articles", json=payload)
        if r.status_code == 429:
            wait = 35 * (attempt + 1)
            print(f"Rate limited, sleep {wait}s…", file=sys.stderr)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            print(r.status_code, r.text[:800], file=sys.stderr)
            r.raise_for_status()
        return r.json()
    r.raise_for_status()
    return r.json()


def delete_series_part_one(client: httpx.Client, *, dry_run: bool) -> None:
    """删除 DEV 上系列第一篇（避免与更新稿重复）。"""
    page = 1
    to_delete: list[tuple[int, str]] = []
    while page <= 5:
        r = client.get(
            "https://dev.to/api/articles/me",
            params={"per_page": 100, "page": page},
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for art in batch:
            title = art.get("title") or ""
            series = (art.get("series") or {}).get("name") or art.get("series") or ""
            if series == SERIES and ("（一）" in title or "Part 1" in title or "第一篇" in title):
                to_delete.append((art["id"], title))
            elif "Tool 把我从 Chat 拽进了 Loop" in title:
                to_delete.append((art["id"], title))
        page += 1
    for aid, title in to_delete:
        print(f"Delete id={aid}: {title[:70]}")
        if not dry_run:
            # Forem 无 DELETE；下架公开可见性
            dr = client.put(
                f"https://dev.to/api/articles/{aid}",
                json={"article": {"published": False}},
            )
            if dr.status_code >= 400:
                dr = client.put(f"https://dev.to/api/articles/{aid}/unpublish")
            if dr.status_code >= 400:
                print(dr.status_code, dr.text[:500], file=sys.stderr)
                dr.raise_for_status()
            time.sleep(1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--from-part", type=int, default=1)
    parser.add_argument("--to-part", type=int, default=7)
    parser.add_argument("--skip-delete", action="store_true")
    parser.add_argument(
        "--update-part",
        type=int,
        default=0,
        help="仅更新已发布的该篇正文（换图后同步 DEV）",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    global IMAGE_CACHE_BUST
    if not IMAGE_CACHE_BUST:
        IMAGE_CACHE_BUST = os.getenv("IMAGE_CACHE_BUST", "")
    key = os.getenv("DEVTO_API_KEY", "").strip()
    if not key and not args.dry_run:
        print("Set DEVTO_API_KEY in environment or .env", file=sys.stderr)
        return 1

    headers = {"api-key": key, "Content-Type": "application/json"}
    client = httpx.Client(headers=headers, timeout=120.0)

    if args.update_part:
        part_map = {p: name for p, name, _ in ARTICLES}
        name = part_map.get(args.update_part)
        if not name:
            print("Invalid --update-part", file=sys.stderr)
            return 1
        cn = "一二三四五六七"[args.update_part - 1]
        needle = f"（{cn}）"
        r = client.get("https://dev.to/api/articles/me", params={"per_page": 100})
        r.raise_for_status()
        hit = next(
            (a for a in r.json() if needle in (a.get("title") or "") and "从零手写 Agent" in (a.get("title") or "")),
            None,
        )
        if not hit:
            print("DEV 上未找到该篇", file=sys.stderr)
            return 1
        title, body, _tags = load_markdown(DOCS / name)
        body = devify_body(body)
        if args.dry_run:
            print(f"[dry-run] update id={hit['id']} {title}")
            return 0
        u = client.put(
            f"https://dev.to/api/articles/{hit['id']}",
            json={
                "article": {
                    "title": title,
                    "body_markdown": body,
                    "series": SERIES,
                }
            },
        )
        u.raise_for_status()
        print("Updated:", u.json().get("url") or hit.get("url"))
        return 0

    if not args.skip_delete and args.from_part <= 1:
        delete_series_part_one(client, dry_run=args.dry_run)

    results = []

    for part, name, skip in ARTICLES:
        if skip or part < args.from_part or part > args.to_part:
            continue
        path = DOCS / name
        title, body, tags = load_markdown(path)
        body = devify_body(body)
        print(f"Publishing part {part}: {title[:60]}…")
        data = create_article(client, title, body, tags, dry_run=args.dry_run)
        if not args.dry_run and data.get("id"):
            cid = data.get("collection_id")
            if not cid:
                client.put(
                    f"https://dev.to/api/articles/{data['id']}",
                    json={"article": {"series": SERIES}},
                )
        url = data.get("url") or data.get("canonical_url")
        results.append((part, title, url))
        if not args.dry_run:
            time.sleep(35)

    print("\n--- Done ---")
    for part, title, url in results:
        print(f"{part}. {url}\n   {title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
