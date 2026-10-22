---
title: 理解 Agent 里的 Tool：原理、疑惑与写法
series: 从零手写 Agent
part: 1
status: ready-for-review
date: 2026-10-22
tags: [Agent, Tool-Calling, LLM, ReAct]
repo: https://github.com/you/myAgent
---

# 理解 Agent 里的 Tool：原理、疑惑与写法

> 系列第一篇。配套实验仓库：本地 `myAgent`（Python + Ollama + 最小 Agent Loop，无 LangChain/LangGraph）。

---

## 开篇：我真正搞懂 Agent 之前，先搞懂 Tool

很多人第一次接触 Agent，会以为关键是「更聪明的 Prompt」或者某个框架里的 `Agent` 类。  
动手写了一个 **Calculator Agent** 之后，我才意识到：**Tool 才是 Chat 和 Agent 的分水岭**。

普通对话：

```text
User → LLM → Answer
```

带 Tool 的 Agent：

```text
User → LLM →（可能）Tool → Observation → LLM → … → Answer
```

Loop 可以后面再抽象成 LangGraph；但 **「模型提议 → 你执行 → 结果塞回对话」** 这条线，从第一个 Tool 开始就存在了。

这篇把我在学习 Tool 时最常见的疑惑一次说清：**Tool 是什么、模型怎么决定调不调、什么时候该调、怎么写才规范、为什么换模型行为差很多**。

---

## 1. Tool 到底是什么？

### 1.1 一句话

**Tool = 给模型看的说明书（Schema）+ 你在程序里真正执行的函数（Implementation）。**

- **模型**：读对话，推理，**决定**要不要调用、调用哪个、参数填什么（通常是 JSON）。
- **你的代码**：**执行**函数，把返回值作为 **Observation** 写回 `messages`。

模型**不能**直接替你算准大数、查实时网页、改磁盘上的文件——除非你把这些能力包成 Tool，并在 Loop 里执行。

> 执行权在你手里，这是 Agent 安全与可控的第一课。

### 1.2 和 ReAct 里的 Action 是什么关系？

经典 ReAct 文本长这样：

```text
Thought → Action → Observation → Thought → … → Final Answer
```

现代 API（OpenAI 兼容的 **Tool / Function Calling**）里，**Action 往往就是一次 `tool_call`**，**Observation 就是 `role: tool` 那条 message 的 `content`**。  
不必强迫模型输出 `<thought>` 标签；理解 **「交替推理与行动」** 即可，实现上 **Tool call → Tool result → 再 call LLM** 就是在做 ReAct。

### 1.3 两个世界，两套代码

以仓库 `agent/tools/` 为例，同一个 Tool 要维护两面：

| 层面 | 作用 | 在本仓库里 |
|------|------|------------|
| **声明（Schema）** | 告诉模型：叫什么、干什么、要什么参数 | `Tool.schema` → `TOOL_DEFINITIONS` |
| **实现（Implementation）** | 真正跑逻辑 | `Tool.fn`（如 `calculator()`） |

Loop 里只做通用分发：`execute_tool(name, arguments)`，**新增 Tool 通常不必改 Loop**。

---

## 2. 一次 Tool 调用在协议里长什么样？

请求（每轮都可能带上）：

- `messages`：system / user / assistant / tool 历史
- `tools`：函数列表（name、description、parameters 的 JSON Schema）
- 可选 `tool_choice`：`auto` / `none` / 指定某个函数

模型若在 assistant 里返回 **`tool_calls`**，每一项大致包含：

- `id`：你回传结果时必须带上（`tool_call_id`）
- `function.name`
- `function.arguments`：**JSON 字符串**（要 `json.loads`）

你追加一条：

```text
role: tool
tool_call_id: ...
name: calculator
content: "56877"    ← Observation，给模型看的结果
```

然后再请求 LLM，直到某轮 **没有 `tool_calls`**，只有普通文本 → 当作 Final Answer。

伪代码就是系列里反复出现的那段：

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

**`has_tool_call` 不是模型内部的 if-else 开关**，只是 SDK 在告诉你：这一轮生成的是「结构化 tool 输出」还是「纯文本」。

---

## 3. 常见疑惑一：模型怎么知道要不要调 Tool？

### 3.1 没有隐藏的「命中检测器」

模型**不会**先对用户输入做关键词匹配，再返回「调 / 不调」。  
每一轮它看到的是 **整段上下文**：用户问题、历史、system prompt、以及你传的 **每个 Tool 的 description**。

然后在生成 assistant 内容时，在两种输出形式之间做 **概率意义上的选择**：

- 继续写自然语言（`content`）
- 或走训练过的 **tool call 结构**（`tool_calls` + 参数 JSON）

支持 Tool Calling 的模型，在对齐阶段见过大量「该查就查、该算就算」的样本，所以 **「会不会用这种格式」** 也是模型能力的一部分。

### 3.2 什么在推它做选择？

| 因素 | 影响 |
|------|------|
| Tool 的 **`description`** | 模型主要靠它理解「什么时候该用这个工具」 |
| 各参数的 **`description`** | 决定参数怎么填 |
| **System prompt** | 例如「精确计算必须用 calculator，不要心算」 |
| **用户怎么说** | 「123×456+789」vs「什么是 Agent」 |
| **对话历史** | 刚拿到 tool 结果，可能不再重复调用 |
| **`tool_choice`** | 强制自动 / 禁止 / 指定某一函数 |

### 3.3 「和 Tool 说明对不上 → 多半自己答」对吗？

**大体对，别当成硬规则。**

若用户只是在聊天、问概念，而注册的工具写的是「计算数学表达式」，模型 **通常** 会直接文字回答，因为生成纯文本更自然。  
但仍是 **倾向**，不是 guarantee：description 太宽会 **误调**，该调时模型弱会 **漏调**，多个 Tool 还可能 **调错**。

---

## 4. 常见疑惑二：模型本身能答，为什么还要 Tool？

「看起来能答」≠「应该让它答」。

| 场景 | 仍建议 Tool 的原因 |
|------|-------------------|
| **精确计算** | 大数、多步运算易错；计算器可验证 |
| **事实 / 时效** | 训练截止后的世界、今日数据——不能靠权重「记忆」 |
| **真实环境** | 读文件、跑测试、调 API——没有 Tool 就没有真实副作用 |
| **审计与合规** | 需要记录「调了谁、参数是什么」 |
| **安全** | 危险操作只放在你审查过的实现里 |

Calculator 的典型价值：**LLM 负责理解题意和组织语言，确定性程序负责对错。**  
即使用户题小模型心算可能对，工程上仍可能 **策略性地** 走 Tool——那是 **输出形式的选择**，不是「检测它会不会算」。

### 什么时候调？什么时候不？

实用规则：

> **答案依赖「权重里没有、或不能稳定复现」的信息 / 运算 / 副作用 → 应该 Tool。**

- 精确数字、外部事实、改代码、跑命令 → **Tool**
- 解释概念、润色文字、基于**已在上下文里**的材料总结 → **多半不用**
- 没有合适 Tool → **只能**直接答（或承认做不到）

产品上还可通过 `tool_choice: "none"` 强制纯 Chat 模式。

---

## 5. 常见疑惑三：模型、描述、泛化——为什么同一套代码表现差很多？

Tool Calling 是 **三件事叠在一起**：

```text
  ① 模型会不会、稳不稳地选 Tool、填对 JSON
           ×
  ② Tool 描述是否让「何时用 / 何时不用」一目了然
           ×
  ③ 任务是否真的需要外部动作或精确结果
           ↓
      你看到的 trace（调不调、调哪个、参数对不对、最后对不对）
```

同一套 `loop.py`，换 `qwen2.5:3b` 和更大模型，或只改一段 `description`，`--trace` 经常完全不同——**这正常**。

| 现象 | 常见原因 |
|------|----------|
| 从不调 | 描述太窄、模型弱、prompt 未引导 |
| 乱调 | 描述太宽、多个 Tool 职责重叠 |
| 调了参数错 | 参数说明不清、用户表述含糊 |
| 调对了答案仍错 | **实现层** bug，与「会不会调」无关 |

调优 Agent，Often **不是多写几个 function 就结束**，而是：**改 Tool 合约 + 选模型 + 看轨迹迭代**。

---

## 6. 如何编写 Tool？规范与实践

### 6.1 实现层（Python 函数）

- **单一职责**：一个 Tool 一件事。
- **参数简单**：优先 string / number / boolean；复杂再 nested object。
- **返回字符串**：Observation 给模型读，一般是文本（或 JSON 字符串）。
- **错误变文本**：在 `execute_tool` 里捕获，返回 `Error: ...`，让模型有机会补救，别炸 Loop。
- **安全**：禁裸 `eval`、限制路径、命令白名单等。

本仓库的 `calculator` 用 `ast` 限制表达式，是 **学习项目里该有的底线**，不是教程里的 `eval(expression)`。

### 6.2 声明层（Schema）

OpenAI 兼容格式核心字段：

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "何时使用、何时不要用（写清楚）",
    "parameters": {
      "type": "object",
      "properties": {
        "expression": {
          "type": "string",
          "description": "含义 + 示例，如 123 * 456 + 789"
        }
      },
      "required": ["expression"]
    }
  }
}
```

**命名与文案：**

- `name`：`snake_case`，与 `TOOL_REGISTRY` 的键 **完全一致**。
- `description`：写 **何时用 / 何时不用 / 边界**；比参数名更重要。
- 参数 `description`：格式、单位、示例。

### 6.3 工程结构：`agent/tools/` 包（不是一个越写越长的 `tools.py`）

Tool 少时单文件 `tools.py` 足够；**多个 Tool 并存后更推荐目录**：

```text
agent/tools/
├── __init__.py      # ALL_TOOLS 列表 → 导出 TOOL_DEFINITIONS / execute_tool
├── schema.py        # 统一的 tool_schema()  helper
├── types.py         # Tool dataclass（schema + fn）
├── registry.py      # 去重、execute_tool
└── calculator.py    # 一个文件 = 一个 Tool 的实现 + 声明
```

新增 Tool 的步骤：

1. 新建 `agent/tools/my_tool.py`，定义函数 + `MY_TOOL = Tool(name=..., schema=..., fn=...)`
2. 在 `__init__.py` 的 `ALL_TOOLS` 里 append
3. Loop **不用改**

`registry.build_registry()` 会在启动时发现 **重名 Tool** 并抛错——比手动维护两个 dict 更不容易漏。

必要时在 system prompt 里补一句「何时优先用哪个 Tool」，与 description **保持一致**，避免模型犹豫。

### 6.4 写 Tool 前自检

1. 这件事模型**单独做**是否不可靠或不真实？  
2. 多个 Tool 并存时，**description 能否让模型选对**？  
3. 参数是否少而准？`required` 是否完整？  
4. 实现是否可单测、错误是否可读？  
5. 返回内容是否过长？（fetch 网页、读大文件要截断）

---

## 7. Q&A：多 Tool 并存、数量与组织

### Q1：多个 Tool 并存时，模型怎么「选对」？选不对怎么办？

**A：** 选型没有硬规则，靠的是 **description 互斥 + 模型能力 + prompt 一致**。可以按下面层次处理：

**（1）写 description：像写 API 文档，而不是起名**

- 每个 Tool 的 `description` 必须包含：**负责什么 / 不负责什么 / 一个典型反例**。
- 本仓库 `calculator` 已改成这种写法（「不要用于：单位换算、符号推导…」），目的是和将来的 `search`、`fetch` **划边界**。

**（2）互斥表（给自己看的设计稿，可进 system prompt 摘要）**

| 用户意图 | 应选 Tool |
|----------|-----------|
| 精确数值表达式 | `calculator` |
| 不知道答案、要查资料 | `search`（后续 Project） |
| 已有 URL、要正文 | `fetch_url` |
| 概念解释、写作 | **不调 Tool** |

**（3）实现层兜底**

- **重名禁止**：注册表构建时检查（见 `registry.build_registry`）。
- **未知 name**：返回 `Error: unknown tool`，让模型下一轮改选。
- **参数错误**：返回可读 `Error: ...`，不要抛 uncaught exception。
- **仍选错**：用 `--trace` 看轨迹，改 description；或 **合并** 两个过像的 Tool；或 **减少** 同轮暴露的 Tool 数量（见 Q3）。

**（4）强手段（产品化再用）**

- `tool_choice` 指定某一函数（流水线步骤）。
- **两阶段**：先让模型输出「计划用哪个 tool」（纯 JSON），再带缩小后的 `tools` 列表调第二次——本质是 **Routing**。
- 换更强、tool 对齐更好的模型。

---

### Q2：`tools.py` 应该是一个文件还是文件夹？

**A：** **学习阶段**一个文件即可；**Project 2 起（search + fetch + calculator）** 建议 **`agent/tools/` 包**，一个 Tool 一个模块。

原因：

- Schema 与实现贴在一起，review 时不会「改函数忘改 TOOL_DEFINITIONS」。
- `ALL_TOOLS` 一处汇总，Loop 永远 `from agent.tools import TOOL_DEFINITIONS, execute_tool`。
- 单测可以对 `calculator.py` 单独测，不加载全网 Tool。

不是「文件夹才专业」——**Tool 数量 & 协作人数**到了再拆，避免 premature abstraction。

---

### Q3：一个 Agent 应该挂多少个 Tool？有没有上限？

**A：** 协议层 Often 可以挂很多个，**有效上限在模型上下文与选型能力**，不是 Python 字典大小。

经验区间（随模型而异，仅作规划参考）：

| 规模 | 数量（约） | 说明 |
|------|------------|------|
| 教程 / 单域 Agent | 1–5 | 如 Calculator、Research、Coding 各一套 |
| 通用助手 | 5–15 | 要开始严格写互斥 description、分组 |
| 大而全 | 15+ | 强烈建议 **分组 / 路由 / 多 Agent**，不要一次全塞给同一轮 LLM |

「上限」更指：**再增加 Tool，误选率上升、延迟上升、description 维护成本爆炸** 的那个拐点——用 trace 和简单 benchmark 自己量，比背数字有用。

本仓库 Calculator Agent **故意只挂 1 个 Tool**，先把 Loop 跑通；加 Search Agent 时再扩 `ALL_TOOLS`。

---

### Q4：是否禁止「高相似」的 Tool 同时挂在同一个 Agent 下？

**A：** **强烈不建议并存，优先合并或拆分 Agent**，而不是写两行几乎一样的 description。

典型坏味道：

```text
search_web     —「搜索互联网」
web_search     —「在网上查找信息」
google_search  —「用搜索引擎查」
```

模型会在三者间 **随机游走**；你也难以维护。

**怎么处理：**

1. **合并**：一个 `search(query, source?)`，细节放参数，不要三个入口。
2. **分层**：`search` 返回链接列表，`fetch_url` 读单页——能力不同，description 好写互斥。
3. **拆分 Agent**：Research Agent（search + fetch）与 Coding Agent（read_file + run_command）**不同进程 / 不同 `ALL_TOOLS`**，由 Supervisor 或用户场景决定调谁。
4. **若必须保留近似能力**：只在 description 里写 **硬边界**（例如「仅查已配置的内网 Wiki API，不查公网」 vs 「公网 DuckDuckGo」），并接受更强模型才扛得住。

原则：**同轮暴露给 LLM 的 Tool 集合，应两两可区分；区分不了就并成一个或分到两个 Agent。**

---

### Q5：Tool 多了以后，和「一个 Agent」的边界怎么划？

**A：** 一个 Agent = **同一 Loop + 同一套（或同一阶段）Tool 白名单 + 同一状态**。  
Tool 爆炸时，常见演进：

```text
单 Agent + 很多 Tool        → 误选多、prompt 长
单 Agent + 少量 Tool        → 单域好用（当前仓库）
Router / Supervisor + 多 Agent → 每个子 Agent 5 个以内 Tool
```

你现在的学习路线（Calculator → Research → Coding）**天然是换 Tool 集，而不是一个 Agent 挂 30 个函数**——这和工业界做法一致。

---

### Q6：没有合适 Tool 时，模型「拒绝回答」——算 Bug 吗？属于 Agent 调优吗？

**A：** **Loop 多半没问题**；这是典型的 **Agent 调优** 场景，且 Often 先动 **System / Tool 合约**，而不是改 `while`。

真实现象（本仓库 Calculator Agent，仅挂 `calculator`）：

```bash
python main.py -v "今天是几号？"
```

日志里 **只有 step 1、没有 tool call**，但模型仍可能说：「请提供能获取当前日期的服务…」——  
说明它 **已经用文字结束了本轮**，只是 **策略上选择拒答**，不是「Agent 不会走无 Tool 分支」。

| 你看到的 | 实际含义 |
|----------|----------|
| 没有 `tool call` | Loop 正常：`if not tool_calls → return content` |
| 内容像在要 Tool | 模型认为「日期 = 实时数据」，手头又没有时间类 Tool |
| 只有 `calculator` | 不应调 Tool；模型若乱调 `calculator`，属于 **误选 Tool**（另一类调优） |

**调优分层（建议顺序）：**

```text
1. 用 --trace 确认：是没调 Tool 的拒答，还是误调 / 漏调？
2. System / 环境：能否由宿主程序提供事实（当前时间、用户 id、工作区路径）？
3. Tool 集：是否缺一块能力（get_current_datetime、search）？
4. description + system：互斥是否写清（日期不要走 calculator）？
5. 模型：小模型误选、拒答多 → 换更大或 tool 对齐更好的模型
```

**本仓库已做的调优（`agent/loop.py` → `build_system_prompt()`）：**

- 注入 **本地当前时间**，让「今天几号」不必靠模型权重猜，也 **不必** 为此造 Tool。
- 规则写死：**系统环境能答的 → 直接文字答**；**无合适 Tool → 尽量答或说明局限**，不要只让用户「去配工具」。

调优后仍可能出现 **误调 calculator**（例如瞎填 `today().day`）→ tool 返回 `Error` → 第二轮才答对日期。  
这说明：**调优是迭代的**；trace 里「一次错误 Tool + 一次修正」同样 valuable。

**本仓库实测日志（调优前 / 后、计算题）见 [附录 D](#附录-d本地实测日志qwen25-3b--ollama)。**

**结论：**  
「没 Tool 却不好好答」**属于 Agent 调优**，核心是 **Tool 集 + System 环境 + 文案 + 模型** 与任务不匹配；**不等于** Loop 写错。  
专门 Tool（如 `get_current_datetime`）与 system 注入二选一或组合：前者更「Agent 原教旨」，后者更轻，学习阶段两者都值得试。

---

## 8. Agent 调优：在 Tool 视角下它是什么？

**Agent 调优** = 在 **Loop 不变** 的前提下，让轨迹更稳、更少误选、更少拒答。  
第一篇只挂 Tool 相关；后续还会加 State、Planning，但调优思路相同：**先看 trace，再改最便宜的层**。

### 8.1 哪些算调优，哪些不算？

| 类别 | 例子 | 通常不算「调优」 |
|------|------|------------------|
| **Loop / 执行** | `MAX_STEPS`、tool 结果格式、异常变 `Error` 字符串 | 改错了是 **Bug** |
| **Tool 合约** | description、参数说明、合并相似 Tool | — |
| **System / 环境** | 注入当前时间、用户语言、允许访问的目录 | — |
| **模型** | 换 `qwen2.5:3b` → 更大、换 API | — |
| **产品策略** | `tool_choice: none`、强制某步必调某 Tool | — |

你写的 `while` 对了之后，线上体验 **大部分** 来自上表后四行——所以「今天是几号」这种 case **就是调优课**，不是挫败 Loop。

### 8.2 调优工作流（建议固定成习惯）

```text
用户反馈 / 奇怪回答
        ↓
python main.py --trace "复现句"
        ↓
分类：
  A. 该调没调   → 加强 description / system
  B. 不该调乱调 → 互斥文案、收窄 Tool 集、换模型
  C. 没调 Tool 但答不好 → 环境注入 or 新增 Tool or 拒答策略
  D. 调了但实现错 → 修 Python 实现，不是骂模型
        ↓
改一项 → 再 trace → 记录进博文/笔记
```

### 8.3 案例对照：两种「日期」解法

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| **环境注入** | `build_system_prompt()` 里写 `datetime.now()` | 零新 Tool、适合宿主已知信息 | 模型未必信 system；和「Tool 获取世界」范式不同 |
| **专用 Tool** | `get_current_datetime()` | 语义清晰，和 search 同类 | 多一步调用；要问是否值得 |

Calculator Agent 阶段 **先用注入** 理解「不是所有事实都要 Tool」；Project 2 加 search 后，再对比 **「时间走 system、事实走 search」** 的分工。

### 8.4 与 §7 多 Tool Q&A 的关系

- **Q1–Q5**：Tool **多了** 怎么选型、怎么组织。  
- **Q6 + §8**：Tool **少了或不对** 时，模型 **拒答 / 误选** 怎么修。  

合在一起就是 Tool 维度上的调优全景：**该有几个、分别写什么、缺了怎么办**。

---

## 9. 走一遍：Calculator 的轨迹

用户：**「123 * 456 + 789 是多少？」**

```text
[1] user: 123 * 456 + 789 是多少？

[2] assistant: tool_calls → calculator({ "expression": "123 * 456 + 789" })

[3] tool: "56877"

[4] assistant: 计算结果是 56877。
```

第 2 步是 **模型选的输出形式**；第 3 步是 **你的代码**；第 4 步是 **模型根据 Observation 组织人话**。  
**到第 3 步已经完成一次 Agent 行为**；第 4 步是用户体验。

与 **附录 D.1 / D.2** 的 `-v`、`--trace` 输出一致（含 `joyjoy` 步进与 messages 列表）。

本地验证（仓库根目录）：

```bash
python main.py -v "123 * 456 + 789 是多少？"
python main.py --trace "123 * 456 + 789 是多少？"
```

---

## 10. 小结：Tool 在 Agent 里的位置

```text
Agent ≈ LLM + Tools + Loop + State
              ↑
         本篇重点
```

记住这几条就够用：

1. **Tool 是 Schema + 实现**；模型提议，你执行。  
2. **调不调是生成时的选择**，受 description、prompt、模型能力共同影响，不是 keyword 命中表。  
3. **能答仍要 Tool** Often 是为了精确、真实、安全、可审计。  
4. **Loop 写对只是底座**；Tool 文案与模型选型决定线上轨迹。  
5. **多 Tool**：互斥 description、控制数量、避免相似 Tool 并存；工程上用 `agent/tools/` 包组织。  
6. **Agent 调优**（Tool 维）：trace → 分类（漏调/误调/无 Tool 拒答/实现错）→ 改 system、Tool 集或模型；「今天是几号」即典型课例。  
7. 现代 API 里，**Tool call 就是 ReAct 的 Action**；不必神话 Agent，也不必神话 Tool。

下一篇计划：**最小 Agent Loop**——为什么 `while` 是所有框架的祖先，以及 `messages` 如何自然长成 State。

---

## 附录：与本仓库文件的对应关系

| 概念 | 文件 |
|------|------|
| Tool 包与注册 | `agent/tools/`（`__init__.py`、`registry.py`、各 Tool 模块） |
| Loop、system 调优 | `agent/loop.py`（`build_system_prompt()`） |
| LLM 请求 | `agent/llm.py` |
| CLI / trace | `main.py` |

更长的学习路线与后续 Project 提纲见同目录 `从零手写Agent学习笔记.md`。

---

## 附录 D：本地实测日志（qwen2.5:3b @ Ollama）

**环境：** `myAgent` 根目录、`.venv` 已安装依赖、`ollama pull qwen2.5:3b` 已就绪。  
**命令：** `python main.py -v "..."` 或 `--trace`（stderr 为 `INFO [joyjoy]` 日志，stdout 为模型面向用户的输出）。

> **说明：** 同一 prompt 小模型 **非确定性**，「今天几号」可能出现 1 步直答、2 步误调 calculator、甚至偶发乱码；调优看 **多数 trace** 与 **可复现的坏模式**，不要追求单次完美。

### D.1 计算题：`-v`（2 步，正确调 Tool）

**输入：** `123 * 456 + 789 是多少？`

```text
$ python main.py -v "123 * 456 + 789 是多少？"
LLM: qwen2.5:3b @ http://localhost:11434/v1

INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
INFO [joyjoy] tool call: calculator({'expression': '123 * 456 + 789'})
INFO [joyjoy] tool result: 56877
INFO [joyjoy] agent step 2/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"

计算结果是 56877。
```

**读日志：** step 1 只有 tool call、无最终人话；step 2 无 tool call，输出自然语言。这是 **标准 Agent 轨迹**。

---

### D.2 计算题：`--trace`（messages 全貌）

**输入：** 同上。节选（system 里已含 `build_system_prompt()` 注入的本地时间）：

```text
--- trace ---
[0] {'role': 'system', 'content': '你是一个有帮助的助手。\n\n【系统环境】当前本地时间：2026-10-22 10:54:36 +0800（日期以 YYYY-MM-DD 为准）。\n\n规则：\n- 需要精确数学表达式求值时，使用 calculator 工具...'}
[1] {'role': 'user', 'content': '123 * 456 + 789 是多少？'}
[2] {'role': 'assistant', 'content': '', 'tool_calls': [{'id': 'call_0o5ruw9b', 'type': 'function', 'function': {'name': 'calculator', 'arguments': '{"expression":"123 * 456 + 789"}'}}]}
[3] {'role': 'tool', 'tool_call_id': 'call_0o5ruw9b', 'name': 'calculator', 'content': '56877'}
[4] {'role': 'assistant', 'content': '计算结果是 123 乘以 456 再加 789 等于 56877。'}
```

**读 trace：** `[2]` 的 `content` 为空、工具参数在 `tool_calls`；`[3]` 即 Observation；`[4]` 为 Final Answer。

---

### D.3 调优前：「今天是几号？」——无 tool call，但 **拒答**（2026-10-22 实测）

**背景：** 当时 `system` 尚未注入当前时间，仅强调计算用 `calculator`；Tool 列表只有 `calculator`。

**输入：** `今天是几号？`

```text
$ python main.py -v "今天是几号？"
LLM: qwen2.5:3b @ http://localhost:11434/v1

INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"

请提供当前日期或使用可以获取当前日期的服务或工具。我目前无法直接获取当前日期。
```

**读日志：** 仅 **step 1**、**无** `tool call` → Loop 已走「无 Tool → 直接返回 content」分支。  
问题在 **content 内容**（拒答），属于 **§8 Agent 调优**，不是 Loop 未执行。

---

### D.4 调优后：注入时间 + 规则 —— **1 步直答**（同日复测）

**背景：** `agent/loop.py` 使用 `build_system_prompt()`（见 D.2 system 片段）。

**输入：** `今天是几号？`

```text
$ python main.py -v "今天是几号？"
LLM: qwen2.5:3b @ http://localhost:11434/v1

INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"

2026-10-22
```

**读日志：** 仍无 tool call；模型从 system 里的 **【系统环境】当前本地时间** 直接作答。这是 **环境注入** 调优生效的理想情况。

---

### D.5 调优后：**误调 calculator** → Error → 第 2 步才答（同日复测）

**输入：** 仍是 `今天是几号？`（与 D.4 同命令，不同采样）

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"
INFO [joyjoy] tool call: calculator({'expression': 'today().day'})
WARNING [joyjoy] tool calculator failed: unsupported expression: Attribute
INFO [joyjoy] tool result: Error: unsupported expression: Attribute
INFO [joyjoy] agent step 2/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"

今天是2026-10-22，你可以根据这个信息来回答你的问题。今天的日期是10月22日，请问你需要了解关于这个日期的哪些信息或进行哪些计算？如果有任何其他问题，尽管告诉我！
```

**读日志：** 属 **Q1 误选 Tool**；`calculator` 实现拒绝非法表达式 → `Error` 字符串回到 messages → 第二轮结合 system 时间组织答案。  
可继续调优：加强 calculator 的「不要用于日期」、或加 `get_current_datetime` Tool 分流。

---

### D.6 调优后：误把 JSON 当正文输出（偶发，同日复测）

同一问题第三次运行，模型 **未走 tool_calls 协议**，而在 `content` 里输出类 JSON 文本（**无效轨迹**）：

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST http://localhost:11434/v1/chat/completions "HTTP/1.1 200 OK"

{"name": "calculator", "arguments": {"expression": "today().format('YY-MM-DD')"}}
```

**读日志：** Loop 仍视为「无 tool_calls」并原样返回给用户 → 说明 **调优还包括模型选型 / 输出格式约束**；必要时对 assistant 内容做校验或重试。此条作 **小模型 tail case** 记录在案。

---

### D.7 环境踩坑（与 Tool 无关，但会表现为「Agent 挂了」）

**现象：** OpenAI SDK 请求 Ollama 报 `502 Bad Gateway`，curl 直连却 200。  
**原因：** macOS 系统 HTTP 代理把 `localhost:11434` 也转发出去。  
**修复：** `agent/llm.py` 中 `httpx.Client(trust_env=False)`（详见学习笔记 §2）。

---

*修订：2026-10-22，首稿；同日增补 §7 多 Tool Q&A，仓库改为 `agent/tools/` 包结构。*  
*修订：2026-10-22，增补 Q6 + §8 Agent 调优（「无合适 Tool 却拒答」案例与 `build_system_prompt`）。*  
*修订：2026-10-22，附录 D：补充本地 `-v` / `--trace` 实测日志（含调优前后「今天几号」）。*
