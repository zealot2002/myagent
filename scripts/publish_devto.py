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

SERIES = "从零手写 Agent"
DEFAULT_TAGS = ["ai", "agents", "python", "ollama"]

# part -> (filename, skip if already on dev)
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
    title = ""
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    if not title:
        raise ValueError(f"No H1 title in {path}")
    return title, text, tags


def devify_body(body: str, *, series: str = SERIES) -> str:
    if not body.lstrip().startswith("---"):
        body = f"---\nseries: {series}\n---\n\n{body}"
    body = re.sub(
        r"\]\(\./([^)]+\.md)\)",
        lambda m: f"]({GITHUB}/blob/main/docs/{m.group(1)})",
        body,
    )
    body = re.sub(
        r"\]\(\./images/([^)]+)\)",
        lambda m: f"]({RAW}/images/{m.group(1)})",
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
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    key = os.getenv("DEVTO_API_KEY", "").strip()
    if not key and not args.dry_run:
        print("Set DEVTO_API_KEY in environment or .env", file=sys.stderr)
        return 1

    headers = {"api-key": key, "Content-Type": "application/json"}
    client = httpx.Client(headers=headers, timeout=120.0)

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
