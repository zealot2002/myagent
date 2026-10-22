---
title: 从零手写 Agent（一）：Tool 把我从 Chat 拽进了 Loop
series: 从零手写 Agent
part: 1
date: 2026-10-22
tags: [Agent, Ollama, ToolCalling, Python]
status: ready
---

# 从零手写 Agent（一）：Tool 把我从 Chat 拽进了 Loop

最近开始自己折腾 Agent。

一开始我也没急着上 LangGraph 之类的框架，而是在本地用 Ollama 写了一个最小版本：一个 `calculator`，一个 `while` 循环，再加上 OpenAI 兼容的 Tool Calling。

代码其实没多少，但跑通以后，我反而觉得这件事比看框架源码有意思。

因为真正把 Calculator Agent 跑起来之后，我才发现：

**Agent 和普通 Chat 的区别，并不是 Prompt 写得更长，而是模型开始参与“决定下一步做什么”。**

而 Tool，就是这个变化真正发生的地方。

这篇不讲框架，也不打算把 Agent 的概念从头到尾讲一遍。主要记录写这个最小 Agent 时遇到的几个问题，以及跑日志以后对 Tool、Loop、State 的一些理解。

系列目录：[系列导读](./00-系列导读.md) · 代码见文末仓库链接。

---

## 1. 一开始，我以为 Agent 就是 Prompt 写得更复杂

普通 Chat 很简单：

```text
User → LLM → Answer
```

所以我最开始对 Agent 的理解也很朴素：

> 不就是在 Prompt 里告诉模型：“你可以使用这些工具”吗？

真自己跑起来以后，发现完全不是这么回事。

一个最简单的 Agent，实际执行过程更像这样：

```text
User
  ↓
LLM
  ↓
需要工具？
  ├─ 否 → Answer
  │
  └─ 是
       ↓
    Tool Call
       ↓
    执行 Tool
       ↓
    Observation
       ↓
    LLM
       ↓
    Answer / 再调 Tool
```

换成代码，其实就是一个非常普通的循环：

```python
while step < MAX_STEPS:
    response = llm(messages, tools=tools)

    if response.has_tool_call:
        assistant_turn = ...
        result = execute_tool(response.tool_call)

        messages.append(assistant_turn)
        messages.append(tool_result_turn)
    else:
        return response.text
```

到这里，我才真正理解了之前经常看到的那句话：

> **Agent ≈ LLM + Tools + Loop + State**

以前看这句话的时候，感觉多少有点像概念总结。

自己写一遍以后就不一样了。

所谓 Loop，本质就是：

**模型说下一步想干什么 → 程序真的去干 → 把结果塞回来 → 再让模型决定下一步。**

这才是 Agent 开始“动起来”的地方。

---

## 2. 那 Tool 到底是什么？

这个问题我一开始也容易和 Function Call 混在一起。

后来我觉得可以用一句比较简单的话理解：

> **Tool = 给模型看的说明书 + 程序里真正执行的函数。**

这里其实有两个角色。

模型负责：

- 要不要调用 Tool
- 调哪个 Tool
- 参数应该怎么填

程序负责：

- 接收模型给出的参数
- 真正执行函数
- 把执行结果返回给模型

比如我们有一个：

```python
calculator(expression)
```

模型可能会输出：

```json
{
  "expression": "123 * 456 + 789"
}
```

注意，这时候**计算还没有发生**。

模型只是说：

> “我想调用 calculator，而且参数是这个。”

真正执行：

```python
calculator("123 * 456 + 789")
```

的是我的 Python 程序。

所以 Tool Calling 这件事，可以简单理解成：

```text
LLM
 ↓
“我要调用 calculator，参数是 xxx”
 ↓
你的程序
 ↓
真的执行 calculator
 ↓
返回结果
 ↓
LLM
```

这点很重要。

因为模型发出来的 Tool Call，本质上只是一个**请求或者提议**，不是程序真的执行了什么。

参数也不一定永远正确。

所以 Agent Loop 不能把模型输出当成绝对可靠的函数调用，必须有一层真正的执行逻辑接住它。

---

## 3. 第一个 Calculator Agent 跑起来以后，我才知道 Loop 在干什么

我先问一个最简单的问题：

```text
123 * 456 + 789 是多少？
```

模型用的是 `qwen2.5:3b`。

实际日志：

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] tool call: calculator({'expression': '123 * 456 + 789'})
INFO [joyjoy] tool result: 56877
INFO [joyjoy] agent step 2/10

计算结果是 56877。
```

第一次看到这个日志，我觉得挺有意思。

因为它其实把 Agent 的工作过程完整暴露出来了。

第一步：

```text
User
↓
LLM
↓
calculator("123 * 456 + 789")
```

第二步：

```text
calculator
↓
56877
↓
LLM
↓
“计算结果是 56877”
```

所以这里出现两个容易误解的地方。

### 第一，为什么要跑两步？

因为第一轮模型的任务不是“说人话”，而是决定：

> 这个问题需要调用 calculator。

于是第一轮主要产生的是：

```text
tool_call
```

工具执行以后，模型拿到 `56877`，第二轮才负责组织最终回答。

所以：

**两步不是多余的，而是 Tool Calling 的正常流程。**

### 第二，真正完成计算的是谁？

不是 LLM。

是：

```text
calculator
```

LLM 做的是理解问题，然后决定：

```text
calculator("123 * 456 + 789")
```

程序负责真正计算。

这也是我觉得 Tool 很有价值的地方：

> **让模型负责“理解”，让程序负责“确定性”。**

计算器只是一个很简单的例子。

如果换成搜索、数据库、文件系统、API，逻辑其实还是一样。

---

## 4. 模型到底怎么知道“现在应该调 Tool”？

这个问题我刚开始也想得比较简单。

我以为背后是不是有一个东西：

```text
用户问题
↓
关键词检测
↓
出现“计算”
↓
调用 calculator
```

实际上不是。

模型看到的是：

- system prompt
- 用户问题
- 历史 messages
- Tool 的 description/schema

然后自己决定这一轮应该输出普通文本，还是 `tool_calls`。

比如：

```text
123 * 456 + 789 是多少？
```

它可能选择：

```text
tool_calls → calculator
```

而：

```text
Agent 是什么？
```

大概率直接：

```text
assistant → 普通文本
```

这里有一个很容易低估的东西：

**Tool description。**

我现在越来越觉得，Tool description 有点像给模型看的 API 文档。

如果你有几个功能非常相似的 Tool，description 写得含糊，模型很容易选错。

所以 Tool 的名字固然重要，但真正影响模型选择的，往往是：

```text
Tool 是干什么的
什么时候应该用
什么时候不要用
参数是什么
返回什么
```

尤其是小模型。

我用的只是本地 `qwen2.5:3b`，它并不是每次都能做出最合理的选择。

所以实际调 Agent 的时候，我现在比较习惯先看 trace，而不是先怀疑 Loop。

---

## 5. 模型明明会算，为什么还要 Calculator？

这个问题也挺有意思。

比如：

```text
123 * 456 + 789
```

模型自己其实很可能也能算出来。

那为什么还要 Tool？

我的理解是：

**很多时候我们要的不是“模型觉得答案是多少”，而是一个可以验证、可以记录、可以复现的结果。**

计算尤其明显。

让 LLM 负责：

```text
理解题目
```

让程序负责：

```text
计算
```

最后得到的结果就比较容易验证。

同样的思路放到其他场景里也成立：

```text
查数据库 → 数据库负责事实
搜索网页 → 搜索服务负责事实
调用 API → API 返回真实状态
执行操作 → 程序负责副作用
```

所以 Tool 的意义并不是：

> “模型不会做，所以给它一个工具。”

更准确一点应该是：

> **模型适合做判断和规划，但某些事情交给确定性的程序更靠谱。**

---

## 6. 一个很有意思的坑：没有 Tool，Agent 就不会回答了吗？

然后我遇到了一个挺有意思的问题。

当时 Agent 里只有一个：

```text
calculator
```

我突然问：

```text
今天是几号？
```

结果模型没调 Tool，而是直接说：

```text
请提供当前日期或使用可以获取当前日期的服务或工具。
我目前无法直接获取当前日期。
```

当时第一反应是：

> Agent 是不是坏了？

后来仔细看了一下，Loop 根本没问题。

这一轮发生的是：

```text
LLM
↓
没有 tool_call
↓
返回普通文本
↓
Loop 结束
```

问题其实在另外一个地方：

**Agent 根本没有获得“当前时间”这个能力。**

这让我意识到一个很容易混淆的问题：

> **Agent 能不能完成任务，和 Loop 写得对不对，是两件事。**

Loop 只负责：

```text
模型 → Tool → 模型 → Tool → ...
```

至于模型有没有能力完成当前任务，取决于你给它什么。

---

## 7. “今天”到底从哪里来？

这个问题我后来又专门拆了一下。

如果没有：

- 当前时间
- 时间 Tool
- 其他环境信息

那就不能指望模型凭空知道“今天”。

模型没有一块隐藏的硬件时钟。

我现在这个最小 Agent 里，采用的是另一种简单办法：

**直接把当前时间写进 system prompt。**

比如：

```text
【系统环境】当前本地时间：
2026-10-22 10:54:36 +0800
（日期以 YYYY-MM-DD 为准）
```

所以进入 Loop 时，messages 大概是：

```python
messages = [
    {
        "role": "system",
        "content": "【系统环境】当前本地时间：2026-10-22 ..."
    },
    {
        "role": "user",
        "content": "今天是几号？"
    }
]
```

然后模型只是读取上下文里的这段文字。

它并没有真的跑到我的电脑上读取系统时间。

这一点和 Tool 有一个很直观的区别：

| | System 注入 | Tool |
|---|---|---|
| 信息在哪里 | `system.content` | `role: tool` |
| 是否需要额外 Loop | 不需要 | 通常需要 |
| 谁提供 | 宿主程序 | Tool 执行结果 |
| 例子 | 当前时间 | 查询数据库 |

这个区分对我来说挺重要。

因为以前容易产生一种误解：

> “只要 Agent 有 Tool，所有外部信息都应该通过 Tool 获取。”

其实没必要。

一些稳定、基础的环境信息，直接注入 system 就够了。

而需要动态查询、执行或者验证的东西，再考虑 Tool。

---

## 8. 同一个问题，为什么有时候结果还不一样？

把当前时间注入 system 以后，再问：

```text
今天几号？
```

情况就开始变得有意思了。

理想情况下：

```text
INFO [joyjoy] agent step 1/10

2026-10-22
```

一步结束。

但小模型偶尔也会犯迷糊。

比如出现：

```text
INFO [joyjoy] tool call:
calculator({'expression': 'today().day'})

WARNING [joyjoy] tool calculator failed:
unsupported expression: Attribute

INFO [joyjoy] tool result:
Error: unsupported expression: Attribute

INFO [joyjoy] agent step 2/10

今天是2026-10-22……
```

也就是说，它先误用了 calculator，发现不行以后，再根据 system 里的时间把答案答出来。

甚至还有更极端的情况：

模型在 `content` 里自己输出了一段看起来像 JSON 的东西，但协议层面并没有真正产生 `tool_calls`。

这种情况下，Loop 只能把它当普通文本处理。

这也让我对一个问题有了比较现实的认识：

**Agent 不是写完 Loop 就万事大吉。**

实际效果还和下面几个东西强相关：

```text
模型
Tool description
System prompt
输出协议
上下文
```

所以调 Agent 的时候，我现在更愿意看真实 trace。

不要光盯着最终答案。

---

## 9. Tool 一多，问题就来了

目前我的 Calculator Agent 只有一个 Tool，所以事情还很简单。

但如果继续加：

```text
calculator
search_web
read_file
query_database
get_current_datetime
...
```

模型就需要从一堆 Tool 里做选择。

这时候我目前比较认可几个原则。

### Tool 的职责要尽量清楚

比如：

```text
search_web
```

负责搜索网页。

那就别再搞一个：

```text
web_search
```

两者干一样的事情。

对模型来说，这相当于：

> “这里有两个看起来差不多的按钮，你自己猜按哪个。”

### description 比名字更重要

Tool 的 description 最好直接说清楚：

```text
负责什么
什么时候用
什么时候不要用
参数怎么传
```

把它当 API 文档写就行。

### Tool 不是越多越好

协议层面可以注册很多 Tool。

但真正的问题是：

**模型到底能不能稳定选对？**

如果一个 Agent 同时挂几十个功能，模型选择本身就开始变成问题。

到了这个阶段，通常应该考虑 Router、多 Agent 或者 Tool 分组，而不是继续往一个 Agent 里塞。

---

## 10. 我现在调 Agent，基本就按这个顺序排查

这一点是我写完 Calculator 之后最大的一个变化。

以前遇到：

```text
Agent 答错了
```

第一反应可能是：

> Loop 有 bug？

现在我会先看 trace，然后把问题分成几类：

```text
1. 漏调 Tool
2. 误调 Tool
3. 没有合适 Tool
4. Tool 自己执行失败
5. 模型输出协议有问题
6. 上下文/Prompt 有问题
7. 真正的代码 bug
```

然后一次只改一个地方，再重新跑。

比如模型不调 calculator：

```text
先看 Tool description
```

模型乱调 calculator：

```text
看 description + system + 模型能力
```

Tool 调对了，但执行失败：

```text
查 execute_tool
```

模型明明应该知道时间却不知道：

```text
查 system 环境信息
```

这样排查起来，比一上来修改 while 循环有效得多。

---

## 11. 还有一个和 Agent 完全无关的坑：代理

最后记录一个比较无聊，但确实浪费我时间的问题。

接 Ollama 的时候，OpenAI SDK 报：

```text
502 Bad Gateway
```

但我直接：

```bash
curl localhost:11434
```

却是正常的。

最后发现不是 Agent，也不是 Tool，更不是 Ollama 挂了。

是 macOS 的 HTTP 代理把 localhost 也转发出去了。

把客户端的：

```text
trust_env
```

处理好之后才恢复正常。

所以有时候 Agent 看起来“挂了”，真的不一定是 Agent 的问题。

特别是本地模型这种环境，网络代理、endpoint、环境变量这些东西也得一起查。

---

## 12. 收束

**注意：**

- **Tool = Schema + 你的实现**；执行永远在进程里，不在模型权重里。
- **Agent ≈ Loop**：LLM → 是否 `tool_calls` → 执行 → 结果进 `messages` → 再调 LLM。
- **何时调 Tool** 由问题、历史、system、Tool description 和模型能力共同决定 — description 要写准。
- **缺能力**（如当前日期）应加 Tool/上下文，而不是改 Loop 逻辑糊弄过去。
- **`--trace`** 比架构图直观：看清 `assistant(tool_calls)` → `tool` → `assistant` 最终答。

建议路径：先手写几十行 Loop + 一个 Calculator，故意跑坏几次，再去看框架。

---

## 下一篇

《[从零手写 Agent（二）：上下文窗口与多轮对话](./02-上下文窗口与多轮对话.md)》——`messages` 就是短期记忆；`-i` 与同进程 State；Context Window 与 Ollama 静默截断。

系列目录：[系列导读](./00-系列导读.md)

---

## 附录：几个关键日志

### 计算题

```text
INFO [joyjoy] agent step 1/10
INFO [joyjoy] tool call: calculator({'expression': '123 * 456 + 789'})
INFO [joyjoy] tool result: 56877
INFO [joyjoy] agent step 2/10

计算结果是 56877。
```

### `--trace`

```text
[1] user: 123 * 456 + 789 是多少？
[2] assistant: tool_calls → calculator({"expression":"123 * 456 + 789"})
[3] tool: 56877
[4] assistant: 计算结果是 123 乘以 456 再加 789 等于 56877。
```

### 没有时间信息时

```text
INFO [joyjoy] agent step 1/10

请提供当前日期或使用可以获取当前日期的服务或工具。
我目前无法直接获取当前日期。
```

### 调优后误调 Calculator

```text
INFO [joyjoy] tool call:
calculator({'expression': 'today().day'})

INFO [joyjoy] tool result:
Error: unsupported expression: Attribute

INFO [joyjoy] agent step 2/10

今天是2026-10-22，……
```

代码：

https://github.com/zealot2002/myagent