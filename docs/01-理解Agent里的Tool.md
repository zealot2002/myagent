---
title: 从零手写 Agent（一）：Tool 把我从 Chat 拽进了 Loop
series: 从零手写 Agent
part: 1
date: 2026-10-22
tags: [Agent, Tool-Calling, Ollama]
---

# 从零手写 Agent（一）：Tool 把我从 Chat 拽进了 Loop

我学 Agent 时刻意没先上 LangGraph，而是在本地用 Ollama 写了一个最小的 **Calculator Agent**：一个 `calculator`、一个 `while`、OpenAI 兼容的 Tool Calling。  
写完、跑通、又测几轮之后，我发现：**搞懂 Tool，比搞懂某个框架的类名重要得多**——Chat 和 Agent 的分水岭就在这里。

这篇只记录这一路 **学到了什么、困惑过什么、日志里暴露了什么问题**。代码在文末仓库。

---

## 1. 动手之前，我以为 Agent 是「更长的 Prompt」

普通 Chat 是 `User → LLM → Answer`。  
我原来以为 Agent 无非是 Prompt 里多写几句「你可以使用工具……」

真正跑起来以后，轨迹变成：

```text
User → LLM →（可能）Tool → Observation → LLM → … → Answer
```

**Agent ≈ LLM + Tools + Loop + State**——这句话在写 Calculator 之前像口号；看到 `tool_calls` 和 `role: tool` 在 messages 里来回之后，才变成直觉。

Loop 的核心伪代码可以极短（仓库 `agent/loop.py` 与之一一对应）：

```python
while step < MAX_STEPS:
    response = llm(messages, tools=tools)
    if response.has_tool_call:
        assistant_turn = ...   # 本轮 assistant dict，含 tool_calls
        result = execute_tool(response.tool_call)
        messages.append(assistant_turn)
        messages.append(tool_result_turn)  # role=tool，即 Observation
    else:
        return response.text
```

- **`assistant_turn`**：写入 `messages` 的 **assistant 角色** 那一项；有 Tool 时通常 `content` 为空，参数在 `tool_calls` 里。实现里是 `_build_assistant_turn()`。
- **`tool_result_turn`**：工具执行结果，`role: tool`，对应 ReAct 的 Observation。
- **`has_tool_call`**：不是模型内部的 if-else，只是 SDK 表示本轮选了 **结构化 Tool 输出** 还是 **纯文本**。  
ReAct 论文里的 Action / Observation，在现代 API 里大体就是 **tool_call / tool message**——不必再逼模型打印 `<thought>`。

---

## 2. Tool 到底是什么？和 Function Call 什么关系？

我现在的理解可以压成一句：

**Tool = 给模型看的说明书（Schema）+ 我在代码里执行的函数。**

- 模型：决定 **要不要调、调哪个、参数 JSON 长什么样**。
- 我：`execute_tool` **真正执行**，把字符串结果塞回对话。

所以 **Tool 和 Function Call 基本是同一条链**：注册的是 function schema，模型发起的那一下叫 tool call / function call，**执行永远在我这边**——不是模型在权重里「算完」了。

和自己在 Python 里写 `calculator("1+1")` 不同：LLM 的 call 只是 **提议**，参数还可能错，Loop 必须接住。

---

## 3. 第一个能用的 Agent：计算题教会我的

我问：`123 * 456 + 789 是多少？`

日志（`python main.py -v`，模型 `qwen2.5:3b`）：

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] tool call: calculator({'expression': '123 * 456 + 789'})
INFO [joyjoy] tool result: 56877
INFO [joyjoy] agent step 2/10

计算结果是 56877。
```

**注意：**

1. 第一轮只有 tool call，没有人话；第二轮没有 tool call，才组织答案——**两步是正常形态**。
2. 到 `tool result: 56877` 为止，**已经完成一次 Agent 行为**；后面一句「计算结果是…」是体验层。
3. 计算器不必 `eval` 用户字符串；用 `ast` 限制表达式是底线。

用 `--trace` 看 messages 更直观：assistant 的 `content` 常为空，参数在 `tool_calls` 里；下一条 `role: tool` 就是 Observation。

---

## 4. 困惑一：模型怎么知道要不要调 Tool？

我一开始以为有个「命中检测器」：用户话里没出现「计算」就不调。**没有。**

每一轮模型看到的是：用户问题、历史、system、以及每个 Tool 的 **description**。它在生成时 **更倾向** 输出纯文本，还是输出 `tool_calls`，是训练和对齐的结果，**不是 keyword 表**。

所以：

- 和 calculator 无关的问题（例如聊概念），**多半**直接文字答——但小模型仍可能 **误调** 或 **该调不调**。
- **description、system prompt、模型能力** 一起决定轨迹；换模型或改两句说明，trace 可以完全不同。

我还问过自己：**模型心算可能对，为什么还要 Tool？**  
现在我的答案是：精确计算、外部事实、真实副作用、审计——这些场景要的是 **可验证、可记录**，不是「看起来像对」。Calculator 的价值是 **LLM 理解题意，程序负责对错**。

---

## 5. 困惑二：「没有 Tool 可用」= Agent 不会回答吗？

我问：`今天是几号？`  
当时只有一个 `calculator`，system 里也 **没有** 注入当前时间。

日志：

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] HTTP Request: POST ... "HTTP/1.1 200 OK"

请提供当前日期或使用可以获取当前日期的服务或工具。我目前无法直接获取当前日期。
```

这里 **没有 tool call**，Loop 已经正常结束——**不是**「没 Tool 就不走分支」，而是模型 **选择了拒答式措辞**。

我当时的误判是：以为 Agent 坏了。其实是 **Tool 集 + 环境信息** 和任务不匹配——这后来我才愿意叫它 **Agent 调优**，而不是改 `while`。

**另一个困惑：模型知不知道「今天」？**  
不带 system 注入、也不给查时间的 Tool 时，**不能认为它知道**。模型没有内置时钟；「今天」必须锚定到宿主注入或 Tool 返回。ChatGPT 类产品常在看不见的 system 里写当前时间，所以像「自带日历」。

**补充：system 注入 —— 时间是不是放在 prompt 里？**  
是的。在我现在的实现里，**时间就是写在 system prompt 里的**：也就是 `messages` 里第一条 `role: "system"` 的 `content`，不是 user 那句，也 **不是 Tool**。

宿主在 Python 里用 `datetime.now()` 拼进模板（仓库里 `build_system_prompt()`），例如：

```text
【系统环境】当前本地时间：2026-10-22 10:54:36 +0800（日期以 YYYY-MM-DD 为准）
```

进入 Loop 时先构造：

```text
messages = [ system（含上面这段）, user（你的问题） ]
```

每一轮 `llm(messages, tools=...)` 都会把 **整段 messages** 发给模型。模型并没有来我机器上「读时钟」——它只是像读 user 话一样，在上下文里 **读到这段文字**，再决定怎么答。所以「取到时间」= **读 prompt 里你写好的字**，不是 Tool 的 Observation。

和 Tool 的对比可以记一张表：

| | System 注入（我现在用的） | Tool（例如 `get_current_datetime`） |
|--|---------------------------|-------------------------------------|
| 时间出现在哪 | `role: system` 的 content | 某次 `role: tool` 的 content |
| 要不要多一轮 Loop | 否，开局就有 | 通常要 tool_call → 执行 → 再 call |
| 谁写入 | `build_system_prompt()` | `execute_tool` 返回字符串 |

同一次提问里，若 Loop 跑多步，我 **目前只在进入 Loop 前建一次 system**（step 2 不会自动刷新时间）；长跑或跨午夜若要准，可以在每轮 `chat` 前重算 `build_system_prompt()` 并更新 `messages[0]`。

调优后我在 system 里注入了本地时间，并写明：日期类问题 **不要** 用 calculator，无合适 Tool 也要尽量回答。同一句「今天几号？」会出现多种轨迹——小模型 **非确定性**，这很正常：

**情况 A — 一步直答（理想）：**

```text
INFO [joyjoy] agent step 1/10
2026-10-22
```

**情况 B — 误调 calculator，再修正：**

```text
INFO [joyjoy] tool call: calculator({'expression': 'today().day'})
WARNING [joyjoy] tool calculator failed: unsupported expression: Attribute
INFO [joyjoy] tool result: Error: unsupported expression: Attribute
INFO [joyjoy] agent step 2/10
今天是2026-10-22，……
```

**情况 C — 偶发乱输出（tail case）：** content 里出现假 JSON，但协议上没有 `tool_calls`，Loop 会原样返回给用户——说明还要靠 **模型选型或输出校验**。

关于「正规」做法：**产品里当前时间多为 system 注入**；**Agent 叙事里**也可以做成 `get_current_datetime` Tool。我现阶段先用注入，把「不是所有事实都要多一轮 Tool」想清楚；以后加 search 时再对比 **时间走 system、事实走 Tool**。

---

## 6. 困惑三：多个 Tool 以后怎么办？

目前 deliberately 只挂一个 Tool，先把 Loop 跑通。但多 Tool 的问题我已经在笔记里想过了，收几句结论：

- **选型靠 description 互斥**，像写 API 文档：写清 **负责什么 / 不负责什么**，比起名重要。
- **相似 Tool 不要并存**（`search_web` / `web_search` / `google_search` 这种），要么合并，要么拆成不同 Agent 的 Tool 白名单。
- **数量**：协议上可以很多，**有效上限在模型的选型能力**；单域 Agent 个位数常见，再大就要 Router / 多 Agent，而不是一次塞三十个函数。
- Tool 多了以后，代码会从单文件拆成 **每个 Tool 一个模块 + 统一注册**——这是组织问题，不改变 Loop。

调优时我给自己固定流程：**复现 → `--trace` → 分类（漏调 / 误调 / 无 Tool 拒答 / 实现 bug）→ 改一项再测**。Loop 写对之后，体验多半来自 **Tool 文案、system 环境、模型**，不是 mystery。

---

## 7. 环境坑：Agent 像挂了，其实是代理

接 Ollama 时 OpenAI SDK 报 `502 Bad Gateway`，curl 直连 `localhost:11434` 却正常。  
原因是 macOS 系统 HTTP 代理把 localhost 也转发出去了。对本地 LLM 客户端关掉 `trust_env` 后才稳定。  
这类问题和 Tool、Loop 逻辑无关，多半是客户端/网络配置。

---

## 8. 小节

1. **Tool 是 Schema + 实现**；**Tool call ≈ Function call**；执行权在我。
2. **调不调 Tool** 是模型在上下文里的生成选择，不是命中表；**description 和模型** 同样重要。
3. **没合适 Tool** 时仍可能返回文字——可能是好答案，也可能是拒答；要看 **缺的是能力还是环境信息**。
4. **「今天几号」** 让我分清：Loop 正常 ≠ 答得好；**system 注入与 Tool 分工** 是调优，不是失败。
5. **日志和 trace** 比再读十篇教程有用；Calculator 的两步日志、日期的三种轨迹，比任何结构图都真实。

下一篇我打算写 **短期记忆与上下文窗口**——`messages` 每轮整包进 prompt，多轮对话里我踩过的「刚才」坑。

---

## 附录：关键实测日志（qwen2.5:3b · Ollama）

便于发表时对照；同一 prompt 多次运行可能略有差异。

<details>
<summary>计算题完整 -v 日志</summary>

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] tool call: calculator({'expression': '123 * 456 + 789'})
INFO [joyjoy] tool result: 56877
INFO [joyjoy] agent step 2/10
计算结果是 56877。
```

</details>

<details>
<summary>计算题 --trace（节选）</summary>

```text
[1] user: 123 * 456 + 789 是多少？
[2] assistant: tool_calls → calculator({"expression":"123 * 456 + 789"})
[3] tool: 56877
[4] assistant: 计算结果是 123 乘以 456 再加 789 等于 56877。
```

</details>

<details>
<summary>「今天几号」调优前（拒答，无 tool call）</summary>

```text
INFO [joyjoy] agent step 1/10
请提供当前日期或使用可以获取当前日期的服务或工具。我目前无法直接获取当前日期。
```

</details>

<details>
<summary>「今天几号」调优后（误调 calculator → Error → 再答）</summary>

```text
INFO [joyjoy] tool call: calculator({'expression': 'today().day'})
INFO [joyjoy] tool result: Error: unsupported expression: Attribute
INFO [joyjoy] agent step 2/10
今天是2026-10-22，……
```

</details>

---

**代码与后续笔记：** https://github.com/zealot2002/myagent
