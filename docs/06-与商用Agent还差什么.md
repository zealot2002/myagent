---
title: 从零手写 Agent（六）：和商用 Agent 还差什么——一张能力地图
series: 从零手写 Agent
part: 6
date: 2026-10-22
tags: [Agent, Roadmap, Production]
status: draft
---

# 从零手写 Agent（六）：和商用 Agent 还差什么——一张能力地图

前五篇把一条线走完了：**Tool → 多轮与窗口 → trim → 联网检索 → 报告落盘**。  
默认模型也从小档换到了 **`qwen2.5:7b`**——多步 Tool、`save_markdown` 会稳一些，但 **换模型不会自动变成商用产品**。

第六篇不引入新框架，只做 **对照**：我现在的 `myAgent` 在商用 Agent（调研助手、Coding Agent、平台型 Copilot）面前，**还缺哪些层、哪些是刻意不做、接下来写代码该先碰哪块**。  
方便和第五篇结尾「sources 下一块拼图」衔接——**差距地图 ≠ 待办清单**，而是 **设计边界**。

---

## 1. 先对齐：商用 Agent 在卖什么

用户付费或企业采购时，买的通常不是「能调 function」，而是 **可预期的结果 + 可运维的系统**：

**任务完成率。** 给定一类问题（写报告、改 bug、查政策），多大比例在时延预算内 **真正交付**（文件、PR、可点击引用），而不是聊天里说说。  
**可信度。** 引用可核对、失败可解释、关键步骤可审计。  
**成本与 SLA。** 延迟、并发、配额、降级；不是「我本机 Ollama 有时 90 秒有时超时」。  
**安全与合规。** 谁能用、能访问哪些 URL/文件、日志留多久。

我的学习版 Loop 已经具备 **ReAct 骨架**；商用差距主要在 **Loop 外面的工程层** 和 **Loop 里面的完成条件/状态**，而不是「会不会写 `while`」。

---

## 2. 本仓库已经有什么（前五篇收束）

用一句话：**本地、单 Agent、短会话、手写 Tool 的 Web 调研原型 + 简易报告落盘。**

| 层 | 已有 |
|----|------|
| 推理环 | `_agent_loop`、tool_calls / tool messages |
| Tool | calculator、search_web、fetch_url、save_markdown |
| 短期记忆 | `messages`、`-i` 多轮 |
| 上下文 | `prepare_messages` trim |
| 交付 | `reports/*.md`（save Tool + nudge / 强制 tool_choice） |
| 运行 | Ollama OpenAI 兼容 API，默认 7B |

**注意：** 第四篇 §4.2、第五篇 §2 的实测说明：**Tool 成功 ≠ 用户任务成功**——这条在商用里会写成 **评测集 + 指标**，我们目前主要靠 `--trace` 肉眼验收。

---

## 3. 和商用调研 / 研究型 Agent 的差距

不绑定某一产品 UI，按 **能力维度** 对照（调研向；与 Coding Agent 有重叠部分放在 §4）。

### 3.1 数据与检索

**商用常见：** 付费搜索 API（Bing/Google/Tavily 等）、新闻/RSS、PDF/表格解析、有时 **客户私有索引**（RAG、向量库、权限过滤）。  
**本仓库：** 无 Key 多源 `search_web` 串行 failover；`fetch_url` 只做 HTML 简抽，**无 JS 渲染**；无 PDF、无企业内网文档。

差距 = **覆盖率、稳定性、垂直深度**，不是「再写一个 search Tool 名字不同」。

### 3.2 规划与执行

**商用常见：** 显式 **Plan**（子问题、源类型、停止条件）→ Execute → 失败 **Re-plan**；长任务 **分钟级** 异步，带进度。  
**本仓库：** 模型在 `tool_choice=auto` 下 **即兴** 多步；`AGENT_MAX_STEPS` 上限内一次性跑完；save nudge 是 **补丁式完成条件**，不是通用规划器。

### 3.3 引用、报告与验收

**商用常见：** 正文 `[n]` 与来源库绑定；冲突标注；模板 enforced；**无 Saved / 无 citation 不算完成**。  
**本仓库：** Markdown 契约在 prompt 里；**`AgentState.sources` 尚未实现**；落盘靠 save Tool + nudge，**内容仍可能 hallucinate**（如 python-313 报告里的张冠李戴）。

### 3.4 模型与推理

**商用常见：** 云端强模型 + 专用「research」流程；有时 **多模型**（小模型规划、大模型写作）。  
**本仓库：** 单本地 **7B**；上下文与 tool 能力受 Ollama 模型与 `num_ctx` 约束（第二篇）。

### 3.5 工程与安全

**商用常见：** 鉴权、限速、审计、SSRF/域名策略、密钥托管、多租户。  
**本仓库：** CLI 本机跑；`fetch_url` **仅 scheme 校验**；`trust_env=False` 的代理策略适合调试 Ollama，不适合生产出网策略。

---

## 4. 和商用 Coding Agent 的差距（系列下一方向）

Cursor、Claude Code、Devin 一类产品的 **Loop 形状往往相同**，Tool 换成 **读文件、改文件、跑命令、测测试**。

| 维度 | 调研 Agent（当前） | Coding Agent（商用） |
|------|-------------------|----------------------|
| 核心 Tool | search / fetch / save | read / write / shell / test |
| 沙箱 | reports/ 路径限制 | 工作区根、命令白名单、容器 |
| 验收 | 文件存在 + 人工读 | 测试绿、diff 可审 |
| 风险 | SSRF、垃圾报告 | 任意代码执行、泄密 |

笔记里 **Coding Agent** 章节仍是提纲——**Loop 不变，换 Tool 包** 与第四篇 calculus 同一套路；商用差距同样在 **沙箱 + 评测 + 长链路可靠性**。

---

## 5. 和「平台型 Agent 框架」的差距

LangGraph、CrewAI、AutoGen 等卖的是 **编排、持久化、人机中断、并行 Tool、可视化**——不是替代「懂 Tool Calling」。

| 能力 | 手写 myAgent | 框架常提供 |
|------|-------------|------------|
| 单 Loop | 清晰、可逐行读 | 抽象成 graph / node |
|  checkpoint / 恢复 | 无 | 有 |
| 并行 Tool | 无（search 内可多源） | 常内置 |
| 子 Agent / 角色 | 无 | Supervisor 模式 |
| 生产运维 | 自备 | 生态集成 |

**注意：** 系列 deliberately **先手写 Loop**（笔记 §11），框架是 **对照学习**，不是「用了就商用」。

---

## 6. 若继续手写，合理的下一层（与差距的对应）

按 **投入 / 收益** 排序，和前五篇风格一致——每项都是 **Loop 外或 state 上增量**，不必推翻重写：

1. **`sources` 足迹 + 报告引用注入**（第五篇 §4）→ 缩小 **可信度** 差距。  
2. **固定评测 query + 脚本**（是否 save、是否调 fetch、URL 是否在 tool 里）→ 缩小 **验收** 差距。  
3. **fetch 安全与可选代理配置**（SSRF、allowlist）→ 缩小 **安全** 差距。  
4. **轻量 Plan**（一轮 JSON 大纲再 Loop）→ 缩小 **规划** 差距。  
5. **Coding Tool 包 + 工作区沙箱** → 换赛道到 Coding Agent，Loop 仍同构。  
6. **MCP 把 search/fetch 外置** → 架构实验，Loop 仍是 client（第四篇 Q）。

换 **云端 API + 付费检索** 是 **能力上限** 的捷径，但会离开「零 Key、本地 Ollama」系列主线——可以写成 **番外**，不必塞进最小仓库。

---

## 7. 本地现状自检（写博文时用）

```bash
python main.py -v --trace '…'   # 看 tool 链与 Saved:
ollama list                     # 确认 qwen2.5:7b
ls reports/                     # 落盘产物（gitignore）
```

商用产品还会看：**同一 prompt 跑 100 次的成功率、p95 延迟、引用准确率**——我们尚未建表，这是 **商用差距** 里最该补的「工程习惯」之一。

---

## 8. 收束

**myAgent 现在是什么：** 教学向、可 trace 的 **单 Agent 调研 + 简易交付**，Loop 与 Tool 模式与商用 **同构**，能力与运维 **不同量级**。  
**和商用差最多的：** 检索与数据、规划与长任务、引用与评测、安全与多租户——**不是** 再多注册两个 Tool 就能对齐。  
**和第五篇的关系：** save 解决「有没有文件」；**sources + 评测** 解决「文件是否可信、任务是否可重复验收」——第六篇是 **地图**，具体实现仍按篇拆、Loop 一行不改。

---

**系列阅读顺序：** 一 Tool · 二 窗口 · 三 trim · 四 联网 · 五 报告 · **六 商用对照（本文）**

**代码：** https://github.com/zealot2002/myagent
