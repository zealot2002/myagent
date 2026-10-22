---
title: 从零手写 Agent：不先上框架，先把 Loop 跑通
status: ready
repo: /Users/zzy/study/myAgent
started: 2026-10-22
tags: [Agent, ReAct, Tool-Calling, Ollama, Python]
---

> **写作说明（给自己）**  
> - 本文随 `myAgent` 仓库迭代而扩充，每完成一个 Project 就补全对应章节。  
> - 已写实的部分标 `[已完成]`；计划中的章节保留提纲，发表前再润色导语与总结。  
> - 代码以仓库当前版本为准，行号可能变化，引用时优先写文件路径。

---

## 摘要

我想搞懂 Agent **到底在干什么**，而不是只会 `from langgraph import ...`。  
路线是：**LLM API → Tool Calling → 最小 Loop → ReAct 思想 → State → Planning → 多 Agent → 最后再碰框架**。

本仓库是这条路上的实验场：Python + OpenAI 兼容 API + 本地 Ollama，**不依赖 LangChain / LangGraph**。

**已拆分的发表稿：** 见 [`00-系列导读.md`](./00-系列导读.md)（七篇 + 导读、`status: ready`、DEV 发表清单）。第一篇曾发 DEV；2–7 按导读表续发，第六篇含网页截图。

| 篇 | 文件 |
|----|------|
| 导读 | [`00-系列导读.md`](./00-系列导读.md) |
| 一–七 | [`01`](./01-理解Agent里的Tool.md) … [`07`](./07-与商用Agent还差什么.md) |

---

## 学习路线图

| 阶段 | 主题 | 仓库状态 | 博文章节 |
|------|------|----------|----------|
| ① | LLM API（OpenAI 兼容 / Ollama） | `[已完成]` | §2 |
| ② | Tool Calling | `[已完成]` | §3 |
| ③ | 最小 Agent Loop | `[已完成]` | §4 |
| ④ | ReAct（思想 + 现代 API 映射） | `[进行中]` | §5 |
| ⑤ | State / Memory（上下文窗口 + trim） | `[进行中]` | §6、第二/三篇博文 |
| ⑥ | Web Research Agent | `[进行中]` | §7、第四 / 五篇博文 |
| ⑦ | Coding Agent | `[未开始]` | §8 |
| ⑧ | Planning | `[未开始]` | §9 |
| ⑨ | Multi-Agent | `[未开始]` | §10 |
| ⑩ | LangGraph 等框架（对照手写 Loop） | `[未开始]` | §11 |

---

## 1. 普通 Chat 和 Agent 差在哪？

**普通对话**：

```text
User → LLM → Answer
```

**Agent**：

```text
User → LLM → 是否调用 Tool？
              ├─ 是 → Tool → Observation → LLM → …
              └─ 否 → Final Answer
```

一句话抽象：

> **Agent ≈ LLM + Tools + Loop + State**

Agent 不是「特别长的 Prompt」，而是让模型在**可执行环境**里反复 **Action → Observation**，直到可以回答用户。  
框架只是把这套 Loop 做成可组合、可持久化、可调试的图；**核心仍是 while 循环**。

---

## 2. LLM 后端：本地 Ollama + OpenAI SDK `[已完成]`

### 2.1 为什么用 OpenAI 兼容接口？

习惯用 `openai` 官方 SDK，把 `base_url` 指到 Ollama 的 `/v1` 即可，本地不需要真实 API Key：

- 默认：`http://localhost:11434/v1`
- 模型：默认 `qwen2.5:7b`（M4 16GB 可跑；支持 tool calling；博文部分实测仍为 3b 记录）

配置见仓库根目录 `config.py`、`.env.example`。

### 2.2 实现要点

`agent/llm.py` 里创建一个 `OpenAI` 客户端，封装 `chat(messages, tools=...)`。

### 2.3 踩坑：系统代理与 localhost

在 macOS 开启 HTTP 代理时，`httpx` 默认 `trust_env=True`，可能把 `localhost:11434` 也走代理，表现为 **502 Bad Gateway**。  
本仓库对 Ollama 使用 `httpx.Client(trust_env=False)`。若你换环境又连不上，先查这一项。

### 2.4 踩坑：Python 3.9 与类型注解

系统自带 Python 3.9 不支持在运行时解析 `list[dict] | None`，需在模块顶部加：

```python
from __future__ import annotations
```

或改用 `typing.Optional` / `typing.List`。

---

## 3. Tool Calling：第一个 Tool 是计算器 `[已完成]`

> **发表版**：Tool 的原理、疑惑、写法已整理为系列第一篇 → [`01-理解Agent里的Tool.md`](./01-理解Agent里的Tool.md)。本节保留仓库向的简要笔记。

### 3.1 为什么从 Calculator 开始？

搜索、读文件、跑命令都依赖「多步 Loop」。  
**一个 Tool + 一次调用**能把「模型决定调用函数 → 你执行 → 结果塞回对话」这条链路摸清楚。

### 3.2 Tool 的两张「脸」

1. **给模型看的 schema**（名字、描述、参数 JSON Schema）→ `agent/tools/` 汇总为 `TOOL_DEFINITIONS`  
2. **真正执行的 Python 函数** → 各模块实现 + `registry.execute_tool()`

模型只会根据 schema **提议**调用；**执行权在你手里**，这是 Agent 安全边界的第一课。

### 3.3 不要用裸 `eval`

示例文章里常用 `eval(expression)` 图省事。本仓库用 `ast` 只允许数字与四则运算，避免代码注入。

### 3.4 一次完整交互（概念）

用户：`123 * 456 + 789 是多少？`

1. LLM 返回 `tool_calls: [{ name: calculator, arguments: {...} }]`
2. `execute_tool` → `"56877"`
3. 追加 `role: tool` 的 message
4. LLM 再跑一轮 → 自然语言：`56877`

**到这一步，已经是一个 Agent。**

---

## 4. 最小 Agent Loop：`while` 才是本体 `[已完成]`

### 4.1 伪代码（所有框架的祖先）

```python
while step < MAX_STEPS:
    response = llm(messages, tools=tools)

    if response.has_tool_call:
        for tool_call in response.tool_calls:
            result = execute_tool(tool_call)
            messages.append(assistant_turn)
            messages.append(tool_result(result))
    else:
        return response.text
```

### 4.2 仓库里的实现

核心在 `agent/loop.py` 的 `_agent_loop(state, ...)`：

- **`AgentState`**（`agent/state.py`）：`messages` + `steps` + `tool_results`
- `AGENT_MAX_STEPS` 防止死循环
- system 文案在 `agent/prompt.py`，由 `build_system_prompt()` 注入时间

CLI：`main.py` 单次提问；**`-i` 多轮共用同一 state**；`--trace` 打印 messages 与 `state.steps` / `tool_results`。

> 发表稿：[`02-上下文窗口与多轮对话.md`](./02-上下文窗口与多轮对话.md)

### 4.3 和 LangGraph 的预告关系

手写 Loop 等价于这样一张图：

```text
START → Agent(LLM) → 有 tool? → Tools → Agent → … → END
```

以后在 LangGraph 里不过是把节点命名、边条件化、状态持久化。**先手写一遍，再看框架不会晕。**

---

## 5. ReAct：Reasoning + Acting `[进行中]`

### 5.1 经典文本格式

```text
Thought → Action → Observation → Thought → … → Final Answer
```

例如查天气：先想「需要纽约天气」→ `weather("New York")` → 读 Observation → 再总结。

### 5.2 现代 API 下的 ReAct

很多模型不再强制输出 `<thought>` 标签，而是：

- 在 `content` 里隐式推理，或  
- 直接发出 **structured tool call**

**学习时：理解 ReAct 是「交替推理与行动」；实现上：Tool call + Tool result + 再 call LLM 就够。**

### 5.3 待补充（学完 Project 2 后写）

- [ ] 用 `--trace` 贴一条真实 messages 轨迹并逐条注释  
- [ ] 对比：同一问题「纯 Chat」vs「带 calculator」的可靠性差异  
- [ ] 小模型不调 Tool 时的 fallback 策略（改 prompt / 换模型 / 重试）

---

## 6. State / Memory `[进行中]`

> 第二篇博文草稿：[`02-上下文窗口与多轮对话.md`](./02-上下文窗口与多轮对话.md)

- [x] `AgentState` + `_agent_loop(state)`；交互模式多轮共用 messages  
- [x] `agent/context.py`：`prepare_messages` 截 tool + 滑窗；Loop 每轮 LLM 前调用  
- [ ] 长期记忆（文件 / 向量库）  
- [ ] 按 turn 成对删除、摘要压缩  

---

## 7. Web Research Agent `[进行中]`

> 第四篇博文：[`04-多Tool与联网检索.md`](./04-多Tool与联网检索.md)

- [x] `search_web`（无 Key 多源 **串行 failover**）、`fetch_url`（httpx + 正文抽取）  
- [x] `search_hn`（Firebase + Algolia，无 Key）、`fetch_rss`（feedparser）  
- [x] `ALL_TOOLS` 三件套；`prompt.py` 互斥规则  
- [x] 第四篇 §7：调研 Agent 定位、与商用差距、第五篇衔接  
- [ ] 公网部署的 SSRF / 域名策略；search 在受限网络的稳定 fallback  
- [x] 第五篇：`save_markdown` + §2.1 踩坑实录；sources / 引用校验仍待做（见 [`05-调研报告与引用.md`](./05-调研报告与引用.md)）  

---

## 7b. 调研报告与落盘 `[进行中 — 第五篇]`

> 第五篇博文：[`05-调研报告与引用.md`](./05-调研报告与引用.md)

- [x] `save_markdown`（`reports/` 沙箱）、`prompt` 报告示例  
- [x] 从 search/fetch/HN/RSS 结果抽取 URL 写入 `AgentState.sources` 并注入 system  
- [ ] 可选：成稿 URL 白名单校验脚本  

---

## 8. Project 3：Coding Agent `[未开始 — 提纲]`

Tools 方向：`read_file`、`write_file`、`list_files`、`run_command`。

价值：贴近 Cursor / Claude Code 一类产品的最小内核。

待写：

- [ ] 工作区沙箱（只允许项目目录）  
- [ ] 「改代码 → 跑测试 → 再改」的 Loop 实例  
- [ ] 与 Calculator Agent 的架构对比（Loop 不变，只增 Tool）  

---

## 9. Planning `[未开始 — 提纲]`

从逐步 ReAct 到：

```text
Plan → Execute → Check → Re-plan
```

待写：

- [ ] 计划是单独一轮 LLM 还是嵌在 Loop 里  
- [ ] 计划失败 / 步骤跳过怎么处理  

---

## 10. Multi-Agent `[未开始 — 提纲]`

在 **单 Agent Loop 写熟之后** 再写：

```text
Supervisor → Researcher / Coder / Reviewer
```

避免过早「Agent 套 Agent」导致看不清 Loop。

---

## 11. 再回头看 LangGraph / CrewAI / AutoGen `[未开始 — 提纲]`

对照 checklist：

- [ ] 手写 Loop 的哪一段被框架替换成「节点」？  
- [ ] 持久化、人机中断、并行 Tool 框架提供了什么？  
- [ ] 什么场景仍值得保持零框架依赖  

---

## 附录 A：仓库结构（随开发更新）

```text
myAgent/
├── config.py
├── main.py
├── agent/
│   ├── llm.py      # Ollama 客户端
│   └── tools/      # 每 Tool 一模块 + 注册表
│   ├── loop.py     # Agent Loop
│   └── state.py    # 显式状态（待接入 Loop）
└── docs/
    └── 从零手写Agent学习笔记.md   # 本文
```

## 附录 B：本地运行

```bash
cd myAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen2.5:7b   # 若尚未拉取

python main.py -v "123 * 456 + 789 是多少？"
python main.py -i
python main.py --trace "你的问题"
```

## 附录 C：发表前 Checklist

- [ ] 通读全文，删掉过于私人的踩坑（或泛化表述）  
- [ ] 每章至少一张示意图或一条真实 trace  
- [ ] 代码片段与仓库同步  
- [ ] 摘要 + 结论收束「为什么要先手写 Loop」  
- [ ] 选定发布平台（博客园 / 知乎 / 个人站）并调整排版  

---

## 修订记录

| 日期 | 变更 |
|------|------|
| 2026-10-22 | 初稿：路线表 + §1–§4 写实 + §5–§11 提纲；记录 Ollama/代理/Python3.9 踩坑 |
| 2026-10-22 | 系列第一篇博文：`01-理解Agent里的Tool.md`（Tool 原理与常见疑惑） |
| 2026-10-22 | 博文 §7 多 Tool Q&A；`agent/tools/` 包结构 |
| 2026-10-22 | 博文 Q6 + §8 Agent 调优；`loop.build_system_prompt` 注入时间 |
| 2026-10-22 | 博文附录 D：本地 `-v` / `--trace` 实测日志 |
| 2026-10-22 | 第一篇博文重写：学习脉络 + 困惑 + 精简日志，文末仓库链接 |
| 2026-10-22 | 第二篇博文草稿；AgentState、prompt 模块、交互多轮 |
| 2026-10-22 | 第二篇改题：上下文窗口与多轮对话（替换 Loop/State 主线） |
| 2026-10-22 | 第三篇草稿 + `agent/context.py` + `compare_context_trim.py` |
| 2026-10-22 | 第四篇：多源 search 串行实现 + §3.3–3.6 并发/Adapter/业内实践 |
| 2026-10-22 | 第四篇 §7 调研 Agent 总结；第五篇草稿（报告 / 引用 / 落盘） |
| 2026-10-22 | `save_markdown` Tool；第五篇 §2.1 Python 3.13 踩坑实录 |
| 2026-10-22 | 默认 Ollama `qwen2.5:7b`；第六篇商用差距地图草稿 |
