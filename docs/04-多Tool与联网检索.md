---
title: 从零手写 Agent（四）：多 Tool 与联网检索——Loop 还是那个 Loop
series: 从零手写 Agent
part: 4
date: 2026-10-22
tags: [Agent, WebSearch, ToolCalling, Python]
status: ready
---

# 从零手写 Agent（四）：多 Tool 与联网检索——Loop 还是那个 Loop

前面三篇，我基本把一个 Agent 最核心的骨架搭出来了：

- 第一篇：Tool Calling，让模型可以调用外部能力。
- 第二篇：messages，让 Agent 有了短期记忆。
- 第三篇：上下文超长，开始处理 Context Window 和历史消息治理。

做到这里，下一步很自然：

> 如果我再加两个 Tool，让 Agent 能搜索互联网、读取网页，是不是要继续给 Loop 加 `if/else`？

答案是：**不用。**

这一篇我给之前的 Calculator Agent 再加两个 Tool：

- `search_web`：搜索互联网
- `fetch_url`：读取网页

最终变成：

```text
用户问题
   ↓
LLM
   ↓
选择 Tool
   ├── calculator
   ├── search_web
   └── fetch_url
   ↓
Tool 执行
   ↓
结果放回 messages
   ↓
LLM 再判断
   ↓
继续 Tool / 直接回答
```

Loop 还是之前那个 Loop。

真正发生变化的是：

> **Tool 越来越多以后，Agent 的能力边界主要由 Tool Registry 决定，而不是由 Loop 决定。**

系列目录：[系列导读](./00-系列导读.md)

---

## 1. 为什么还是同一个 Loop？

之前的核心代码大概就是：

```python
while steps < MAX_STEPS:
    prepare_messages(messages)

    response = llm(
        messages,
        tools=ALL_TOOLS,
    )

    if response.tool_calls:
        for call in response.tool_calls:
            result = execute_tool(
                call.name,
                call.arguments,
            )

            messages.append({
                "role": "tool",
                "content": result,
            })

        continue

    return response.content
```

现在增加 `search_web` 和 `fetch_url`，这里基本不用动。

只需要：

```python
ALL_TOOLS = [
    CALCULATOR,
    SEARCH_WEB,
    FETCH_URL,
]
```

然后：

```python
response = llm(
    messages,
    tools=ALL_TOOLS,
)
```

模型自己决定：

```text
要不要搜索？
    ↓
search_web

拿到 URL 了
    ↓
fetch_url

还需要计算
    ↓
calculator

信息已经够了
    ↓
直接回答
```

所以从 Agent Loop 的角度看：

```text
Tool 变多
    ↓
Registry 变大
    ↓
模型可选择的动作变多
```

而不是：

```text
Tool 变多
    ↓
Loop 增加大量 if/else
```

这其实是这一篇最重要的结论。

---

# 2. 多 Tool 的关键：先把能力边界划清楚

这次增加的两个 Tool 看起来都和“联网”有关，但我没有把它们合成一个：

```text
web_tool
```

而是拆成：

```text
search_web
fetch_url
```

原因很简单：

> **搜索和读取网页，本来就是两个不同的动作。**

| Tool | 输入 | 输出 | 适合解决 |
|---|---|---|---|
| `calculator` | 数学表达式 | 数值 | 精确计算 |
| `search_web` | 搜索词 | 标题、URL、摘要 | 不知道去哪里找 |
| `fetch_url` | 完整 URL | 网页正文 | 已经知道去哪看 |

例如：

```text
“Python 3.13 是什么时候发布的？”
```

一开始并不知道哪个页面有答案：

```text
search_web
```

拿到：

```text
Python 3.13.0
https://www.python.org/downloads/release/python-3130/
```

这时候才适合：

```text
fetch_url
```

去读取具体页面。

如果一开始就让 `fetch_url` 负责搜索，就会把“搜索”和“读取”混成一个能力，Tool 的职责越来越模糊。

所以这里有一个很实用的原则：

> **一个 Tool 最好表达一个清晰的动作，而不是把一整段工作流塞进 Tool。**

---

## 2.1 `search_web`

给模型看的 Tool 描述大致是：

```text
用于搜索互联网信息、新闻、资料和网页链接。

不要用于：
- 纯数学计算
- 用户已经提供完整 URL 的情况
- 普通概念问答
```

参数：

```json
{
  "query": "Python 3.13 release date",
  "max_results": 5
}
```

其中：

```text
query
```

是搜索词。

```text
max_results
```

限制返回结果数量，当前范围：

```text
1 ~ 10
```

返回给模型的是普通字符串，例如：

```text
[1] Python 3.13.0
URL: https://www.python.org/downloads/release/python-3130/
Snippet: Python 3.13.0 was released...

---

[2] What's New In Python 3.13
URL: ...
Snippet: ...
```

最后还是：

```json
{
  "role": "tool",
  "content": "..."
}
```

所以对 Agent Loop 来说，搜索结果没有特殊待遇。

它就是一次 Observation。

如果搜索失败，也只是：

```text
Error: search failed (...)
```

模型拿到这个结果之后，可以：

- 换一个搜索词重试
- 换一个 Tool
- 或者直接告诉用户当前无法获取

Loop 本身不需要知道“搜索失败了”。

---

## 2.2 `fetch_url`

`fetch_url` 的职责更加单一：

> 用户或者前一步搜索已经给出了 URL，现在把这个网页内容读回来。

参数：

```json
{
  "url": "https://www.python.org/"
}
```

当前只接受：

```text
http://
https://
```

返回的是经过简单处理后的网页文本。

HTML 里的：

```text
<script>
<style>
```

等内容会被去掉。

同时限制返回长度，大约：

```text
8000 字符
```

超过以后：

```text
...(fetch truncated in tool)
```

这里有两个原因。

第一，网页本身可能非常长。

第二，也是第三篇刚处理过的问题：

> **Tool 返回太长，最终还是会进入 messages，继续消耗 Context Window。**

所以现在其实形成了两层控制：

```text
fetch_url
    ↓
先限制网页输出长度
    ↓
messages
    ↓
prepare_messages()
    ↓
必要时继续做 Tool 内容截断 / 历史滑窗
```

也就是说，第三篇的上下文治理并没有因为增加 Web Tool 而失效，反而变得更重要了。

---

# 3. 三个 Tool 怎么注册？

最终：

```python
ALL_TOOLS = [
    CALCULATOR,
    SEARCH_WEB,
    FETCH_URL,
]
```

每一个 Tool 还是之前的结构：

```python
Tool(
    name="search_web",
    schema=...,
    fn=search_web,
)
```

Agent Loop 只需要：

```python
execute_tool(name, arguments)
```

至于：

```text
search_web 到底怎么搜？
fetch_url 到底怎么抓？
```

这些都属于 Tool 自己的事情。

目录结构现在大概变成：

```text
agent/
├── tools/
│   ├── calculator.py
│   ├── search_web.py
│   ├── fetch_url.py
│   └── __init__.py
├── loop.py
└── state.py
```

依赖增加：

```text
ddgs
httpx
```

相关环境变量：

```text
SEARCH_TIMEOUT_SEC
SEARCH_BUDGET_SEC
FETCH_MAX_BYTES
FETCH_TIMEOUT_SEC
```

---

# 4. `search_web` 里面到底怎么实现？

这里有一个容易混淆的地方：

> **Agent 是多 Tool，不代表一个 Tool 内部只能访问一个数据源。**

我现在暴露给模型的仍然只有：

```text
search_web
```

但 `search_web` 内部可以尝试多个搜索来源。

当前学习版采用的是**串行 Failover**：

```text
ddgs
  ↓ 失败
DuckDuckGo Instant Answer
  ↓ 失败
Wikipedia
  ↓ 失败
Qwant
  ↓ 失败
SearXNG
```

哪个先成功，就返回哪个结果。

这样做的目的不是实现一个完整搜索引擎，而是让这个小项目在没有 API Key 的情况下，也能尽量跑起来。

单个来源有：

```text
SEARCH_TIMEOUT_SEC
```

整个搜索还有：

```text
SEARCH_BUDGET_SEC
```

避免所有来源轮流超时，把 Agent 卡很久。

运行：

```bash
python main.py -v --trace "Python 3.13 release date"
```

可以看到：

```text
search provider=ddgs success
search results=...
```

或者：

```text
search provider=ddgs failed
search provider=wikipedia success
```

这些信息属于日志，不应该直接塞进模型的 Observation。

模型只需要看到统一格式：

```text
title
url
snippet
```

这也是为什么多源搜索最好封装在一个 Tool 里面。

---

## 4.1 为什么不直接暴露多个搜索 Tool？

比如：

```text
search_duckduckgo
search_wikipedia
search_bing
search_qwant
```

看起来很灵活，但模型一下子多了很多选择。

而这些 Tool 的本质动作其实都是：

```text
query → 搜索结果
```

更合理的边界是：

```text
模型
 ↓
search_web
 ↓
内部决定数据源
```

未来想从串行改成并发，也应该改：

```text
search_web
```

内部，而不是修改 Agent Loop。

---

# 5. 串行还是并行？

如果继续往下做，多源搜索很自然会遇到这个问题。

现在是：

```text
A
↓
失败
B
↓
失败
C
```

最简单，但延迟可能比较高。

另一种方式是：

```text
        ┌─ A
query ──┼─ B
        └─ C
             ↓
        merge + dedupe
             ↓
          ranking
             ↓
        SearchHit[]
```

例如内部统一成：

```python
@dataclass
class SearchHit:
    title: str
    url: str
    snippet: str
    source: str
```

不同搜索源负责：

```text
原始响应
   ↓
adapter
   ↓
SearchHit
```

最后再统一格式化成：

```text
role: tool
```

这是后面如果要继续升级时比较自然的方向。

但这篇的学习版没有把复杂度继续往上堆，仍然采用串行 Failover。

---

# 6. 多 Tool 真正跑起来是什么样？

假设用户问：

```text
查一下 Python 官方站是做什么的，并把 123*456 算出来。
```

一个可能的轨迹是：

```text
User
 ↓
LLM
 ↓
search_web
 ↓
搜索结果
 ↓
LLM
 ↓
fetch_url
 ↓
网页内容
 ↓
LLM
 ↓
calculator
 ↓
56088
 ↓
LLM
 ↓
Final Answer
```

注意：

**这个顺序不是写死的。**

模型也可能：

```text
calculator
 ↓
search_web
 ↓
fetch_url
```

甚至只搜索，不抓取网页。

所以 Agent Loop 的职责依然只是：

```text
LLM → Tool → Observation → LLM
```

至于下一步是什么，由模型决定。

---

# 7. 实际测试：Tool 能调用，不代表结果就好

这一部分我觉得比单纯展示代码更有价值。

因为加上联网 Tool 后，很容易产生一个错觉：

> “现在 Agent 会搜索了，所以它已经是 Research Agent 了。”

实际并不是。

我用：

```text
qwen2.5:3b
```

做了两个测试。

---

## 7.1 测试一：直接问“今日新闻”

执行：

```bash
python main.py -v "今日新闻摘要"
```

模型实际发出的搜索词是：

```text
Today's news summary
```

并且：

```text
max_results=1
```

`ddgs` 成功返回了结果，但结果比较尴尬：

```text
Google News
```

页面本身更像一个新闻门户入口，摘要主要是：

```text
登录
地区
导航
```

最终 Agent 基本变成：

```text
这里有一个今日新闻链接……
```

也就是说：

```text
Tool 调用成功
        ≠
得到高质量研究结果
```

问题并不是网络失败。

而是：

```text
用户问题太宽
    ↓
模型生成了英文宽泛 Query
    ↓
只取 1 条结果
    ↓
命中了门户首页
    ↓
没有继续 fetch
    ↓
最终只能给链接
```

---

## 7.2 测试二：把搜索目标说具体

换一个：

```bash
python main.py -v --trace '用 search_web 检索「新华社 今日要闻」或「BBC world news today」，根据返回的标题和摘要用中文列 3 条，不要只给链接。'
```

这次模型搜索：

```text
新华社 今日要闻
```

返回 5 条结果。

结果里出现了比较明确的新华社页面：

```text
标题
URL
Snippet
```

最后模型能够根据这些摘要整理出 3 条中文内容。

这次没有调用 `fetch_url`。

其实已经够解释一个很重要的问题：

> **搜索质量很大程度取决于模型给搜索 Tool 的 Query，以及搜索结果本身是什么类型。**

两个测试对比：

| | 测试一 | 测试二 |
|---|---|---|
| Query | 今日新闻 | 新华社 今日要闻 |
| Query 语言 | 英文 | 中文 |
| max_results | 1 | 5 |
| 结果 | 新闻门户 | 具体新闻页面 |
| fetch | 没有 | 没有 |
| 最终结果 | 基本给链接 | 能整理 3 条摘要 |
| Tool | 成功 | 成功 |

所以这里暂时不能把第二个测试说成“已经可以做今日新闻调研”。

它只是说明：

```text
search_web
    ↓
返回质量还可以的 Observation
    ↓
小模型能够继续加工
```

另外测试里还出现了一个很典型的问题：

模型把 Tool 返回的：

```text
权威快报
```

写成了：

```text
权力建报
```

这意味着：

> **Tool 返回的内容进入模型以后，模型仍然可能改写甚至产生错误。**

这也是下一篇要解决的引用问题。

---

# 8. 这里到底算不算 Research Agent？

如果只看能力链路：

```text
用户问题
 ↓
search
 ↓
fetch
 ↓
多步推理
 ↓
answer
```

现在已经具备一个最小的 Web Research Agent 雏形。

但我更愿意把它叫：

> **学习版 Research Agent，而不是完整的调研系统。**

目前已经有：

- 多 Tool
- Web Search
- 网页读取
- 多步 Tool Calling
- 短期记忆
- Context Trim
- Trace / Debug

但距离真正的“调研交付”还差几个关键东西。

### 第一，缺少明确的调研流程

现在主要依赖模型临场决定：

```text
搜什么
搜几次
什么时候 fetch
什么时候停止
```

还没有：

```text
规划
→ 搜索
→ 补充搜索
→ 交叉验证
→ 汇总
```

这样的显式流程。

### 第二，来源没有被结构化保存

现在：

```text
search_web
```

返回：

```text
标题 + URL + 摘要
```

模型读完之后自己组织答案。

如果模型改写错了，Agent 很难约束它：

```text
这个说法到底来自哪个 URL？
```

### 第三，还没有真正的报告产物

现在最终结果还是：

```text
response.content
```

如果要做成真正的调研 Agent，应该有类似：

```text
summary
sections
references
```

这样的结构，并且最终能保存成：

```text
reports/xxx.md
```

这就是下一篇准备解决的问题。

---

# 9. 多 Tool 以后，Agent 的边界到底在哪里？

做到这里，可以重新看一下整个 Agent。

第一篇的时候：

```text
LLM
+
calculator
+
Loop
```

现在：

```text
LLM
+
calculator
+
search_web
+
fetch_url
+
Loop
+
State
+
Context Governance
```

但 Loop 还是：

```python
while steps < MAX_STEPS:
    prepare_messages(messages)

    response = llm(
        messages,
        tools=ALL_TOOLS,
    )

    if response.tool_calls:
        ...
        continue

    return response.content
```

所以我现在越来越倾向于把 Agent 理解成：

```text
Agent
=
LLM
+
Tool Registry
+
Loop
+
State
+
Context Governance
```

其中：

```text
Tool Registry
```

决定 Agent **能做什么**。

```text
LLM
```

决定当前 **想做什么**。

```text
Loop
```

负责把：

```text
想做
→ 执行
→ 观察
→ 再想
```

串起来。

而：

```text
State / Context Governance
```

负责让这个过程不要因为历史消息和 Tool 输出越来越长而失控。

---

# 10. 本地运行

安装依赖：

```bash
pip install -r requirements.txt
```

启动模型：

```bash
ollama pull qwen2.5:7b
```

直接测试搜索：

```bash
python -c "from agent.tools.search_web import search_web; print(search_web('Python 3.13 release date', 2))"
```

测试网页读取：

```bash
python -c "from agent.tools.fetch_url import fetch_url; print(fetch_url('https://www.python.org/downloads/release/python-3130/')[:600])"
```

让 Agent 自己调用搜索：

```bash
python main.py -v --trace '请用 search_web 查 Python 3.13 正式版发布日期，并写出结果里的来源标题。'
```

直接测试 `fetch_url`：

```bash
python main.py -v --trace '请用 fetch_url 读取 https://www.python.org/downloads/release/python-3130/ 并中文概括发布日期。'
```

测试多 Tool：

```bash
python main.py -v "Python 3.12 有什么新特性？简述并给出来源。"
```

如果需要交互调试：

```bash
python main.py -i --trace
```

搜索相关功能依赖网络。

另外，如果终端出现：

```text
dquote>
```

这类提示，通常是 Shell 引号没有闭合。命令里的整句提示建议用英文单引号包起来。

---

## 11. 收束

演进线：Tool → `messages` → trim → **多 Tool 联网**。第四篇一句话：

> **加能力 = 加 Tool 并注册；Loop 形状不变。**

`search_web`（及后续的 `search_hn`、`fetch_rss`）解决「去哪找」；`fetch_url` 解决「打开已知 URL」。失败、超时、HTML 简抽、结果截断都封在 Tool 内。§4.2 的对比说明：**Tool 成功 ≠ 研究结果合格** — query 宽窄与是否继续 fetch 同样关键。

边界应划清：**Tool Contract、Registry、State、Context Governance**。

Repo：[zealot2002/myagent](https://github.com/zealot2002/myagent)

---

## 下一篇

《[从零手写 Agent（五）：调研报告、引用与落盘——Loop 仍不变](./05-调研报告与引用.md)》——`save_markdown`、`sources`、save nudge。

系列目录：[系列导读](./00-系列导读.md)

---

## 附录：当前 Tool Registry（发表时）

```python
ALL_TOOLS = [
    CALCULATOR,
    SEARCH_WEB,
    SEARCH_HN,
    FETCH_RSS,
    FETCH_URL,
    SAVE_MARKDOWN,
]
```