---
title: 从零手写 Agent（四）：多 Tool 与联网检索——Loop 不变
series: 从零手写 Agent
part: 4
date: 2026-10-22
tags: [Agent, Tools, Search, Multi-Step]
status: draft
---

# 从零手写 Agent（四）：多 Tool 与联网检索——Loop 不变

前三篇分别搞定：**Tool**、**messages 与窗口**、**超长治理**。  
第四篇做一件很具体的事：在同一个 `_agent_loop` 里挂上 **`search_web` + `fetch_url` + `calculator`**，让模型自己串「先搜 → 再抓 → 再算」。

**注意：** Loop 一行都不用改；变的是 **Tool 列表** 和 **system 里的互斥说明**。

第一篇只注册了 **`calculator`**。第四篇在 **`ALL_TOOLS`** 里 **追加** 两个联网 Tool（calculator 保留不动）：

| 新增 Tool | 文件 | 依赖 |
|-----------|------|------|
| **search_web** | `agent/tools/search_web.py` | `ddgs`、`httpx` |
| **fetch_url** | `agent/tools/fetch_url.py` | `httpx` |

注册方式与第一篇相同：每个 Tool 是一个 `Tool(name, schema, fn)`，在 `agent/tools/__init__.py` 汇总后交给 `build_registry`——**Loop 仍只调 `execute_tool(name, arguments)`**。

---

## 1. 为什么还是同一个 Loop？

伪代码没变：

```text
prepare_messages(messages)
response = llm(messages, tools=ALL_TOOLS)
有 tool_calls → execute_tool → append → 继续
无 tool_calls → 返回答案
```

Calculator 时代已经证明：**Agent 的能力边界 = 注册了什么 Tool + 模型会不会选**。  
加上联网 Tool 后，只是 **Observation 从 `"56877"` 变成「搜索结果 / 网页正文」**，步数往往 **> 2**。

---

## 2. 新增 Tool 说明：`search_web` 与 `fetch_url`

第一篇已经讲过 **Tool = Schema + 本地函数**；这里只写 **这两个新 Tool** 的契约与和 calculator 的差别。

### 2.1 一句话区分

| | **search_web** | **fetch_url** |
|---|----------------|---------------|
| 输入 | 检索词 `query` | 完整链接 `url` |
| 输出 | 多条 **标题 + URL + 短摘要**（像搜索结果） | **单页** 抽出来的正文（长，会截断） |
| 典型场景 | 还不知道去哪查、需要候选链接 | search 或用户已经给了 URL，要读细节 |

**注意：** 不是「联网就一个 Tool」。**搜**和**抓页**是两件能力：解析方式、返回体积、安全风险都不同，所以拆成两个 function，让模型分步选。

### 2.2 `search_web`

**给模型看的职责（schema description 摘要）：**

- 用于：需要互联网上的事实、新闻、资料、**链接**。
- 不要用于：纯算式（`calculator`）、用户已给出完整 URL（`fetch_url`）、纯概念闲聊。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `query` | string | 是 | 关键词或问句，如 `Python 3.13 release date` |
| `max_results` | integer | 否 | 1–10，默认 5 |

**返回（字符串，写入 `role: tool` 的 `content`）：**

成功时每条结果固定三块：**序号 + 标题、URL、摘要**，多条之间用 `---` 分隔，例如：

```text
1. Python Release Python 3.13.0 | Python.org
URL: https://www.python.org/downloads/release/python-3130/
Oct 7, 2024 · Release date: Oct. 7, 2024. Python 3.13.0 is the newest major release...

---（若 max_results > 1 还有下一条）---
```

失败时仍是 **普通字符串**，不是 Python 异常，例如：

```text
Error: search failed (ddgs: timed out after 12.0s; duckduckgo_instant: no results; …)
```

Loop 把上述字符串当作 **Observation** 继续下一轮 LLM——模型可以换关键词再搜，或向用户说明超时。

**实现要点（Tool 内部，模型不可见）：** 无 API Key 多源、当前为 **串行 failover**；详见 **§3.1、§3.3–3.6**。

### 2.3 `fetch_url`

**给模型看的职责：**

- 用于：已有 **明确 http(s) URL**，需要读页面正文细节。
- 不要用于：还没有 URL（先 `search_web`）、纯计算。

**参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | string | 是 | 以 `http://` 或 `https://` 开头的完整 URL |

**返回：**

- 成功：页面 **可读文本**（HTML 经简单解析去掉 script/style，**不跑浏览器、不执行 JS**）。超过约 **8000 字符** 在 Tool 内截断并标注 `…(fetch truncated in tool)`。
- 失败：`Error: only http/https URLs are allowed`、`Error: fetch failed: …` 等。

**和 search 的分工示例：**

```text
search_web("Python 3.13 发布日期")  →  得到 python.org 的 release 链接 + 一行摘要
fetch_url("https://www.python.org/downloads/release/python-3130/")  →  更长正文，便于核对细节
```

**注意：** 学习版只做 scheme 校验；**任意 URL 都能被 GET**——公网部署必须考虑 SSRF、限速（见 **§5**）。

### 2.4 与 `calculator` 并列：三个 Tool 怎么选？

| Tool | 做什么 | 何时不用 |
|------|--------|----------|
| **calculator** | 精确数学表达式 | 搜新闻、读网页 |
| **search_web** | 关键词 → 标题 / URL / 摘要 | 已有 URL、纯算式、概念闲聊 |
| **fetch_url** | GET 页面 → 简化正文 | 还没链接、纯算式 |

除 schema 里的 description 外，`agent/prompt.py` 的 system 里写了 **互斥规则** 和 **多步示例**（先 search、再 fetch、再 calculator）。小模型仍会误选，用 `python main.py --trace` 对照 messages 调 prompt。

### 2.5 注册与依赖（与第一篇同一套路）

```python
# agent/tools/__init__.py
ALL_TOOLS = [
    CALCULATOR,
    SEARCH_WEB,   # 第四篇新增
    FETCH_URL,    # 第四篇新增
]
```

`requirements.txt` 新增 **`ddgs`**（检索）、**`httpx`**（检索回退 + 抓页）。环境变量见 `.env.example`：`SEARCH_TIMEOUT_SEC`、`SEARCH_BUDGET_SEC`、`FETCH_MAX_BYTES`、`FETCH_TIMEOUT_SEC`。

---

## 3. search 与 fetch 的实现要点

### 3.1 search_web（本仓库当前：串行 failover）

- 对 LLM 仍是一个 Tool；**多源写在 `search_web.py` 里**，不需要额外 API Key。
- **当前策略：串行 failover**——按顺序试源，**某一源有结果就立刻返回**，不等待其它源（实现简单、对公共实例压力小）。
- 源顺序（格式统一为「标题 / URL / 摘要」）：
  1. **ddgs**（库内已聚合多搜索引擎，本身不是「再写 5 个爬虫」）
  2. **DuckDuckGo Instant Answer**
  3. **Wikipedia**（中/英 API）
  4. **Qwant** 公开 JSON
  5. **SearXNG** 公共实例（代码内写死若干 URL，非 Key）
- 单源超时 `SEARCH_TIMEOUT_SEC`，整次调用总预算 `SEARCH_BUDGET_SEC`（见 `.env.example`）。
- 开 `-v` 时可用 **`joyjoy`** 日志看是哪个源成功或失败。
- 返回 **纯文本** 给 `role: tool`，模型从中挑 URL 再 `fetch_url`。

**注意：** 检索依赖 **出网**；公共 SearX 实例可能随时不可用。失败时 `Error: search failed (...)` 会带上各源摘要——应把 Error 当作 Observation 还给模型，Loop 不必崩。

### 3.2 fetch_url

- **仅 http/https**；`httpx` + `trust_env=False`（与 Ollama 客户端同一套代理坑）。
- 下载上限 **`FETCH_MAX_BYTES`**；HTML 用简单解析抽正文，再 **在 Tool 内截到约 8000 字符**。
- 进入 messages 前还会走 **`prepare_messages` 的 tool 截断**（第三篇）——**两层限长**。

### 3.3 能并发搜多源，再整合结果吗？

**能。** 业内常见两种形态：

| 策略 | 行为 | 优点 | 缺点 |
|------|------|------|------|
| **串行 failover**（本仓库） | 按优先级试，先成功者返回 | 实现简单、总流量小、Observation 短 | 排在后面的源永远轮不到；单源「有结果但很差」也会直接返回 |
| **并发 fan-out + merge** | 同时请求 N 个源，在截止时间内收齐部分结果再合并 | 延迟≈最慢那条「有效响应」，覆盖率更高 | 实现复杂；易触发限流；合并后文本更长，吃窗口 |

并发时的典型流水线（**仍在 Tool 内部**，Loop 不变）：

```text
query
  ├─ provider A ──┐
  ├─ provider B ──┼─→ 归一化为 SearchHit[] → 去重 / 排序 / 截断 → 格式化成一段文本 → role: tool
  └─ provider C ──┘
        ↑ 全局 deadline（与 SEARCH_BUDGET_SEC 同类）
```

伪代码（概念）：

```python
@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str  # "ddgs" | "wikipedia" | ...

def search_web(query, max_results):
    deadline = time.monotonic() + BUDGET
    with ThreadPoolExecutor(max_workers=len(providers)) as pool:
        futures = {pool.submit(p.search, query): p.name for p in providers}
        hits: list[SearchHit] = []
        for fut in as_completed(futures, timeout=remaining(deadline)):
            hits.extend(normalize(fut.result(), source=futures[fut]))
    merged = dedupe_by_url(hits)
    merged = rank_or_interleave(merged)[:max_results]
    return format_for_llm(merged)
```

**注意：**

- 并发不等于「无限开线程」——要有 **全局 deadline** 和 **每源 timeout**，到点 **丢弃未完成的 future**（Python 里线程无法强杀，至少不再 `result()` 即可）。
- 整合后的条数仍要 **`max_results` 截断**，否则多源 × 每源 5 条会撑爆 context（第三篇 trim 只能兜底，不该当主策略）。
- 学习版先用 **串行** 把 Loop / Observation 跑通；要上并发，优先改 `search_web` 内部，**不要**给模型注册 `search_bing`、`search_google` 五个 Tool。

### 3.4 每个源都要单独的「爬虫 / 解析」吗？

**不必每个源一套重型爬虫**，但几乎 **每个源都要一个 Adapter（适配器）**：

| 源类型 | 你要写什么 | 例子 |
|--------|------------|------|
| **官方 / 聚合 JSON API** | HTTP GET + JSON 字段映射 → `SearchHit` | DuckDuckGo Instant、Wikipedia API、Qwant JSON、SearX `format=json` |
| **第三方库封装** | 调库 + 映射字段 | `ddgs`（库内已对接多引擎 HTML/API） |
| **裸 HTML 搜索页** | HTTP + **解析器**（CSS/XPath/正则，易碎） | 一般不手写，交给 ddgs / SearX |
| **读正文（fetch）** | GET + **正文抽取**（非完整浏览器） | 本仓库 `fetch_url`：`HTMLParser` 去 script/style；产品常用 readability、trafilatura、Playwright（成本高） |

可以抽象成统一接口：

```text
Provider.search(query, limit) -> list[SearchHit]
```

**search** 阶段：目标是 **标题 + URL + 短摘要**（SERP 级）。  
**fetch** 阶段：目标是 **单 URL 长正文**——算法不同，所以拆成 `search_web` 与 `fetch_url` 两个 Tool 仍然合理。

**注意：** 「一个源一个爬虫」在工程上指的是 **一个源一个 adapter 文件**，而不是复制五份 httpx 样板；解析逻辑能复用就复用（例如共用一个 `_format_hit` / 共用一个 JSON client）。

### 3.5 多源检索：坑与注意点

1. **超时与尾延迟**  
   串行：总耗时 ≈ 各失败源超时之和（所以有 `SEARCH_BUDGET_SEC`）。  
   并发：总耗时 ≈ min(deadline, max(慢源))，但 **同时打多个公共 SearX** 更容易被限流。

2. **结果质量 vs 有结果**  
   failover 在「首页无关条目」也会返回，模型可能像实测那样 **再搜一次**。合并策略里常见：**按 URL 域名加权、或丢弃过短 snippet**。

3. **去重**  
   同一新闻多源会重复：对 URL **去掉 tracking 参数**（`utm_*`）、http/https 归一、必要时 title 相似度。  
   合并后再编号 `1. 2. 3.`，避免模型看到三条相同链接。

4. **排序 / 融合**  
   简单：**轮询 interleave**（A1, B1, C1, A2…）保证多样性。  
   稍好：**RRF（Reciprocal Rank Fusion）** 按各源排名融合（Metasearch 常用）。  
   有 Key 的商业源（Tavily、Bing Web Search 等）常作为 **高优先级单源**，未必需要 5 路免费源并发。

5. **Observation 体积**  
   多源合并 = 更多 snippet → 占 **上下文窗口**；Tool 内先截断，再交给 `prepare_messages`（双层限长）。

6. **网络与代理**  
   本仓库 `trust_env=False` 避免 macOS 系统代理把 Ollama 搞成 502；search/fetch 同样 **不走系统代理**，直连不稳就会 **时好时超时**。产品上要 **可配置代理**，且与 LLM 分流。

7. **合规与 ToS**  
    scraping 搜索页可能违反站点条款；优先 **官方 API / 库 / 自建 SearX**。公共实例 **不要当生产依赖**。

8. **安全（fetch 侧）**  
   search 只返回链接；**SSRF、内网 IP、file://** 等风险在 **fetch_url** 爆发。学习版仅校验 scheme；上线要 **域名 allowlist、禁止 RFC1918、限速**。

9. **可观测性**  
   每个源 **成功/失败/耗时/条数** 打日志（本仓库 tag：**`joyjoy`**），否则只能看到 `Error: timed out` 却不知道卡在哪一路。

10. **模型行为**  
    Tool 失败字符串是正常 Observation；小模型可能 **不重试 search**。要在 system 里写「失败可换关键词再搜」，或换更大模型——这是 Agent 层策略，不是多源本身能解决的。

### 3.6 业内最佳实践（简表）

| 做法 | 说明 |
|------|------|
| **对模型暴露一个 `search_web`** | 选源、并发、合并都在 Tool 内；避免让 LLM 选搜索引擎 |
| **内部 `SearchHit` 结构化，出口再 stringify** | 方便 dedupe、排序、测试；给 LLM 的仍是固定文本模板 |
| **Provider 插件化 + 配置优先级** | 无 Key 源与商业 API 可共存；Key 只放 env，不进 prompt |
| **deadline 优先于 per-provider timeout** | 用户感知延迟有上限 |
| **失败可部分成功** | 并发时 2/5 源成功也应返回 merged + 可选 `partial failures` 脚注 |
| **缓存** | 同 query 短 TTL 缓存（内存/Redis），减轻限流 |
| **熔断** | 某源连续失败则跳过一段时间（circuit breaker） |
| **search 与 fetch 分离** | SERP 摘要 vs 单页正文，解析器不同 |
| **评测** | 固定 query 集看：延迟、成功率、nDCG@k（有标注时）、Token 占用 |

本系列 **手写学习版** 刻意采用：**无 Key、串行 failover、统一文本 Observation**——与上表「生产形态」的差距，本身就是值得写进博文的对比。

---

## 4. 典型轨迹（概念）

用户：「查一下 Python 官方站是做什么的，并把 123*456 算出来。」

```text
[ user ]
[ assistant → search_web("Python official site") ]
[ tool → 摘要 + python.org URL ]
[ assistant → fetch_url("https://www.python.org/...") ]
[ tool → 页面正文片段 ]
[ assistant → calculator("123*456") ]
[ tool → 56088 ]
[ assistant → 自然语言汇总 ]
```

**注意：**

- 顺序 **不保证**；模型可能先算再搜，或只搜不 fetch——取决于 prompt、模型、问题表述。
- **`state.steps`** 会随每次 LLM 调用递增；**`tool_results`** 便于 `--trace` 旁路查看。
- 长 fetch 会 **占窗口**；第三篇的 trim 在这里从「理论」变成「刚需」。

### 4.2 实测对比：同一类需求，两种问法（`qwen2.5:3b`）

下面两次都在本机跑通 **Loop + search_web**（`python main.py -v --trace`），说明：**Tool 没坏不等于调研质量够用**——问法、query 语言、命中页类型会决定 Observation 有没有「可写进摘要」的料。

#### 案例 A：宽问法 ——「今日新闻摘要」

**用户输入：**

```bash
python main.py -v "今日新闻摘要"
```

**模型行为摘要：**

| 项 | 内容 |
|----|------|
| Tool | `search_web({"query": "Today's news summary", "max_results": 1})` |
| 注意 | 中文题被改成 **英文 query** |
| `joyjoy` | `search_web ddgs ok (1 hits)` |
| Tool 命中 | **Google News 首页**（`https://news.google.com/`），snippet 多为 Sign in、地区、导航 |
| 步数 | 2（search → 文字回答） |
| 最终回答 | 实质是 **甩链接**：「Here is a link to today's news summary…」 |

**结论：** 检索 **成功**，但 SERP 落在 **门户页** 而非 **带日期的条目**；又没有 `fetch_url` 去读具体文章，Observation 里几乎没有「今天发生了什么」。对用户来说像 **没调研**，像 **书签**。

同一问法在网络差时还可能先 `Error: search failed (… timed out …)`，模型会如实说搜不到——见 **§5**；那是 **源/网络** 问题，案例 A 则是 **query + 命中质量** 问题。

#### 案例 B：具体问法 + 明确输出格式

**用户输入：**

```bash
python main.py -v --trace \
  '用 search_web 检索「新华社 今日要闻」或「BBC world news today」，根据返回的标题和摘要用中文列 3 条，不要只给链接。'
```

**模型行为摘要：**

| 项 | 内容 |
|----|------|
| Tool | `search_web({"query": "新华社 今日要闻"})`（默认 `max_results=5`） |
| `joyjoy` | `search_web ddgs ok (5 hits)` |
| Tool 内容 | 多条 **新华网 / 新华国际** URL，snippet 含 **`2026-10-22`** 与标题式短句（中欧班列 14 万列、俄交通事故 7 人死亡、央行长征 90 周年纪念币等） |
| 步数 | 2；`approx_tokens≈497` |
| 最终回答 | 中文 **3 条摘要**，未再堆门户链接 |

**相对案例 A 的改善：**

- **中文、可检索的具体 query** → 命中 **要闻列表页 / 即时新闻** 而非 Google News 首页。
- **5 条 Observation** → 模型有足够 snippet 拼 3 条（仍 **未调用 fetch_url**）。

**仍存在的瑕疵（给第五篇「引用」埋伏笔）：**

- 用户要求「**标题和摘要**」，回答却是 **改写句**，未逐条贴 **Tool 里的标题原文**。
- 出现 **「权力建报」** 一类笔误，Tool 中为 **「权威快报」**——说明 **有 Observation 也可能改写失真**，不能替代 **参考文献 + 原文引用**（见 [`05-调研报告与引用.md`](./05-调研报告与引用.md)）。
- Prompt 里写了「或 BBC…」，实际 **只搜了新华社**；要中英各 N 条，需在问题里要求 **两次 search** 或写清子任务。

#### 两案对照（一览）

| 维度 | 案例 A「今日新闻摘要」 | 案例 B「新华社 今日要闻…列 3 条」 |
|------|------------------------|-----------------------------------|
| 用户 query 宽度 | 极宽 | 较窄 + 指定媒体/类型 |
| 模型 search query | 英文 `Today's news summary` | 中文 `新华社 今日要闻` |
| SERP 类型 | 新闻 **门户首页** | **要闻 / 即时新闻** 列表 snippet |
| Tool 是否成功 | 是 | 是 |
| 用户感知 | 只得到链接 | 得到 3 条中文概要 |
| fetch_url | 未用 | 未用 |
| 可信度 | 低（几乎无事实 snippet） | 中（大意可对上 Tool，但有改写） |

**注意：**

- **宽问法 + 小模型** 容易 **英文化 query** 并 **max_results=1**，放大门户页问题。
- 案例 B 仍 **不是产品级「今日新闻」**：无 RSS/新闻 API、无逐条 URL 引用、无 fetch 单篇；已是 **Web 调研原型** 里较合理的一次 `--trace` 样本，可对照案例 A 写进评测集。

**建议自测命令（与上面对应）：**

```bash
python main.py -v --trace "今日新闻摘要"
python main.py -v --trace '用 search_web 检索「新华社 今日要闻」，根据返回的标题和摘要用中文列 3 条，不要只给链接。'
```

---

## 5. 困惑与踩坑

**Q：加了 Tool，Loop 要加分支吗？**  
不要。`execute_tool(name, args)` 统一分发；新 Tool 只改 registry。

**Q：search 空结果怎么办？**  
Tool 返回 `Error: no results` 或 `search failed (...)`；模型应换关键词或向用户说明，而不是空 loop。

**Q：search 成功但回答像「只给个链接」？**  
多半是 **query 太宽** 或命中 **门户首页**（§4.2 案例 A）。收窄关键词、提高 `max_results`、要求 **列标题/摘要**，或 **search 后再 fetch 具体文章 URL**。

**Q：有摘要但和 Tool 措辞对不上？**  
模型会 **改写** snippet（§4.2 案例 B「权威快报」→「权力建报」）。要可靠性需 **引用原文 + 来源列表**（第五篇）。

**Q：要不要并发多源？**  
可以，在 `search_web` 内 fan-out + merge；不要拆成多个 search Tool。见 **§3.3–3.6**。

**Q：fetch 会执行任意 URL 吗？**  
当前学习版 **仅 scheme 校验**，无域名白名单——**不要对公网开放未鉴权实例**；产品上要加速率、SSRF 防护。

**Q：和 MCP 的关系？**  
MCP 是把 Tool 放到独立服务；**Loop 仍是 client**。本篇是 **手写 Tool**；以后可把 search/fetch 换成 MCP 暴露，Loop 逻辑不变。

---

## 6. 本地怎么用

```bash
pip install -r requirements.txt   # 含 ddgs、httpx
ollama pull qwen2.5:7b
```

**单独测 Tool（不经过 LLM）：**

```bash
python -c "from agent.tools.search_web import search_web; print(search_web('Python 3.13 release date', 2))"
python -c "from agent.tools.fetch_url import fetch_url; print(fetch_url('https://www.python.org/downloads/release/python-3130/')[:600])"
```

**经 Agent 测（看是否发起 tool_calls）：**

```bash
# 倾向触发 search_web（问法要具体；常识题可能直答不调 Tool）
python main.py -v --trace '请用 search_web 查 Python 3.13 正式版发布日期，并写出结果里的来源标题。'

# 倾向只触发 fetch_url
python main.py -v --trace '请用 fetch_url 读取 https://www.python.org/downloads/release/python-3130/ 并中文概括发布日期。'

# 多 Tool 链：模型自行决定步数
python main.py -v "Python 3.12 有什么新特性？简述并给出来源。"
python main.py -i --trace

# 新闻类：宽 vs 窄问法对比（详见 §4.2）
python main.py -v --trace "今日新闻摘要"
python main.py -v --trace '用 search_web 检索「新华社 今日要闻」，根据返回的标题和摘要用中文列 3 条，不要只给链接。'
```

**注意：** 引号用英文；整句外包 **单引号** 可避免 zsh `dquote>`。依赖出网；search 超时见 **§3.1** 与 `joyjoy` 日志（macOS 系统代理 + `trust_env=False` 与 `llm` / `fetch` 一致）。

---

## 7. 到这儿算不算「调研 Agent」？

第四篇跑通之后，仓库已经具备 **Web 调研的最小闭环**：用户提问 → 模型可选 `search_web` / `fetch_url` → 多步 Loop → 一段自然语言回答。  
更贴切的名字是：**Web Research Agent 的学习原型**——还不是「行业调研交付系统」。

### 7.1 已经具备什么

| 能力 | 在本仓库中的位置 |
|------|------------------|
| 多步推理 + Tool | `_agent_loop`、`AGENT_MAX_STEPS` |
| 联网检索 | `search_web` |
| 读页 | `fetch_url` |
| 精确算数 | `calculator` |
| 短期记忆 | `messages`、`-i` 多轮 |
| 长对话不爆窗 | `prepare_messages`（第三篇） |
| 可观测 | `-v`、`--trace`、`joyjoy` |

典型轨迹仍是 **search → fetch → 汇总**（顺序由模型决定）。显式要求检索时，一次「查发布日期、找官网说明」已经是 **小型调研任务**。

### 7.2 还算不上完整调研 Agent 的部分

当前 **交付物 = 终端里一段聊天**，没有固定的 **报告结构、引用规范、落盘文件**。常见缺口如下：

**行为层（Agent 逻辑）**

- 显式 **规划**：先拆子问题 / 搜索计划，再执行（Plan-and-Execute）。
- **迭代检索**：结果差 → 换 query、补 fetch；小模型常搜一次就停。
- search **并发合并**（§3.3 已讨论，代码仍为串行 failover）。

**数据层（Tool）**

- 无 Key 检索 **时好时超时**；商用多依赖付费 API 或自建索引。
- 深读 **PDF / 表格 / 垂直库** 尚未覆盖。
- `fetch_url` 学习版 **SSRF、域名策略** 几乎未做。

**产物层（调研报告）——第五篇主线**

- 无 **Markdown 报告模板**（摘要、分节、参考文献）。
- 无 **引用绑定**：答案里的 URL 未必来自 Tool 返回，存在「像引用」的幻觉。
- 无 **`write_file` / 落盘`**；`-i` 能改口，但没有持久的「报告对象」。

**工程层**

- 固定评测集、鉴权限速、分钟级长任务与进度——商用调研产品的常态，本系列刻意后置。

### 7.3 和商用「行业调研 Agent」差在哪

不绑定某一家产品 UI，共性对比如下：

| 维度 | 本仓库（第四篇止） | 商用调研产品常见形态 |
|------|-------------------|----------------------|
| 目标 | 单次问答、多步 Tool | 课题级交付（行业、竞品、政策等） |
| 检索 | 免费多源 failover | 付费 API + 垂直库 + 有时私有数据 |
| 阅读 | 单页 HTML 抽文本 | 多页、PDF、表格、摘要链 |
| 规划 | 模型即兴 | 大纲 → 分源搜集 → 交叉验证 |
| 可信度 | 靠 prompt 与模型自觉 | 强制引用、冲突标注、「未找到则写明」 |
| 输出 | 聊天字符串 | 结构化报告、可分享、可编辑 |
| 时延与成本 | 本地 Ollama、几步 | 多轮搜索 + 长文，分钟级、按量计费 |

**注意：** 差距主要在 **工作流（规划 → 搜集 → 综合 → 引用 → 排版）** 和 **可靠性工程**，不是 Loop 会不会写。第四篇解决的是 **「能上网读材料」**；**「像一份调研报告一样交差」** 留给第五篇。

### 7.4 下一篇预告：从聊天到报告

第五篇 [`05-调研报告与引用.md`](./05-调研报告与引用.md) 在 **Loop 仍不变** 的前提下，补三块：

1. **报告 Schema**（system / 模板）：摘要、正文分节、参考文献。  
2. **来源状态**：把 search/fetch 里出现过的 URL 记入 `AgentState`，生成时 **只允许引用列表内的链接**。  
3. **落盘 Tool**：例如 `save_markdown`，把最终稿写入 `reports/`。

那是 **同一套调研 Agent 的「输出层」**——第四篇是搜集能力，第五篇是交付能力。

---

## 8. 小节

1. **第四篇新增 `search_web`、`fetch_url`**：前者 **query → 链接与摘要**，后者 **url → 页内正文**；calculator 不变，**Loop 不变**。
2. **多 Tool = 多几个模块 + ALL_TOOLS**；State、context trim **复用**。
3. **互斥 description + system** 是多 Tool 选型第一道防线。
4. **search → fetch → calculator** 是经典多步链，步数由模型决定。
5. **多 search 源放在 `search_web` 内**：**本仓库为串行 failover**，并发合并是同一 Tool 内的升级路径（§3.3–3.6）。
6. **坑**：deadline、去重、Observation 体积、代理、限流、SSRF、公共实例不可用。
7. **联网 Tool 返回大文本**，与 **上下文治理** 必须一起设计。
8. Tool 返回 **Error 字符串** 是正常 Observation，不是异常退出。
9. **已是 Web 调研原型，尚非行业级报告系统**；报告、引用、落盘见 **第五篇**。
10. **§4.2 两次新闻实测**：Tool 成功 ≠ 调研有用；问法与 SERP 类型决定 Observation 质量。

---

## 附录 A：OpenAI 侧看到的 Tool 名（节选）

模型在 `tool_calls` 里只会出现 **function 名** 与 **JSON 参数**，与第一篇 calculator 相同：

| function.name | 参数 JSON 示例 |
|---------------|----------------|
| `search_web` | `{"query": "Python 3.13 release date", "max_results": 3}` |
| `fetch_url` | `{"url": "https://www.python.org/"}` |
| `calculator` | `{"expression": "123*456"}` |
| `save_markdown` | `{"filename": "python-313.md", "content": "# …"}`（第五篇，报告落盘） |

## 附录 B：`ALL_TOOLS` 注册

```python
ALL_TOOLS = [CALCULATOR, SEARCH_WEB, FETCH_URL, SAVE_MARKDOWN]  # SAVE_MARKDOWN 见第五篇
```

**代码：** https://github.com/zealot2002/myagent
