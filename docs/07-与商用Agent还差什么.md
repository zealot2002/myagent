---
title: 从零手写 Agent（七）：和商用 Agent 还差什么——个人调研 Agent 的边界
series: 从零手写 Agent
part: 7
date: 2026-10-22
tags: [Agent, Research, Ollama, Python]
status: ready
---

# 从零手写 Agent（七）：和商用 Agent 还差什么——个人调研 Agent 的边界

前六篇把一条线走完了：**Tool → 窗口 → trim → 联网 → 报告落盘 → 云模型 / 网页台**。  
仓库里还有 **Hacker News / RSS**、**`sources` 注入 system**；推理可 **本地 Ollama** 或 **OpenAI 兼容云端 API**（第六篇），并有一个 **本机网页调研台** 把 Step / Tool / 来源可视化。

能搜、能抓、能写进 `reports/*.md`，CLI trace 与网页时间线都能复盘——但我心里清楚：**这和 Perplexity、各类「深度研究」产品，还不是同一类东西**。

第七篇不写新代码，只做 **对照**：对个人用途、尽量 **零持续成本** 的调研 Agent 来说，**天花板在哪、商用多出来的又是什么、哪些差距值得补、哪些可以刻意不做**。  
这不是待办清单，而是一张 **能力地图**，方便和第五篇的「交付层」衔接：save 解决有没有文件，sources 解决引用从哪来，**商用还差的是工程与预期管理**。

---

## 1. 商用 Agent 在卖什么

付费产品或企业采购，买的通常不是「模型会调 function」，而是下面几件事叠在一起：

**可预期的交付。** 同类问题（简报、对比、政策摘要），在可接受的时间内，多大比例真的交出 **文件、链接、可核对引用**，而不是聊天里一段看起来对的散文。

**可信度与可审计。** 失败能说清是检索超时还是源不可用；关键步骤能查日志；引用尽量绑在真实 URL 上，而不是模型记忆里的链接。

**成本与 SLA。** 延迟、并发、配额、降级有设计，而不是「本机 Ollama 有时 90 秒、search 有时全超时」。

**安全与合规。** 谁能用、能抓哪些 URL、日志留多久——对个人 CLI 可以放松，对公网服务则是硬门槛。

我手写的 `_agent_loop` 已经具备 **ReAct 骨架**（prepare → llm → tool → append）。和商用的差距，主要在 **Loop 外的运维**、**完成条件是否可测**，以及 **数据从哪来**，而不是「会不会写 `while`」。

---

## 2. 现在的 myAgent 是什么定位

一句话：**本机、单 Agent、短会话、手写 Tool 的个人 Web 调研原型 + 简易报告落盘。**

推理仍是同一个 Loop；能力靠 Tool 列表扩展。当前大致包括：

- **算与搜：** `calculator`、`search_web`（无 Key 多源 failover）、`search_hn`、`fetch_rss`、`fetch_url`
- **交付：** `save_markdown`（`reports/` 沙箱），以及 Loop 里的 save nudge / 必要时强制 `tool_choice=save_markdown`
- **上下文：** `prepare_messages` trim；**引用：** Tool 结果解析进 `AgentState.sources`，每轮 LLM 前写入 system
- **运行：** CLI + **本机网页台**（`python -m web.server`）；LLM 默认本地 **7B**，可切 **LLM_API_KEY** 云端（第六篇）

第四篇 §4.2、第五篇 §2 的实测已经说明：**Tool 返回成功 ≠ 用户任务成功**（门户首页、只聊天不 save、改写标题等）。商用会把这类问题收成 **固定用例 + 通过率**；我这边仍主要靠 `--trace` 和 `-v` 里的 `joyjoy` 肉眼验收——这是差距，也是个人项目的取舍。

若定一个 **「免费、个人、调研 Agent」** 的务实目标，不是对齐 SaaS，而是：

> 在不出网 Key、本地 7B 的前提下，**Tech 资讯 + 专题简报 + 带引用的 md 报告** 多数时候能走完 search/fetch → sources → save，且失败可解释。

这已经比「只会 Chat」高出一层；再往上每步都要 **工程或付费数据**。

---

## 3. 和商用「调研 / 研究型」Agent 差在哪

不绑定具体产品名，按维度看（Coding Agent 另见 §4）。

**数据与检索。** 商用常用付费搜索 API、PDF/表格、私有索引（RAG）。我这里是无 Key 的 `search_web`、HN 官方 Firebase/Algolia、任意 RSS，加上 HTML 简抽的 `fetch_url`——**无 JS 渲染、无 PDF、无内网库**。差距是 **覆盖率与稳定性**，不是再注册一个同名 Tool 能解决的。

**规划与长任务。** 商用常见 Plan → Execute → Re-plan，分钟级异步加进度。这里是 **即兴多步**，靠 prompt、save nudge 和模型自觉；**轻量 JSON Plan** 我评估过，对复杂报告有用，但对「HN 列五条」不值得多一轮 LLM——**先不做硬 Plan**，不算短板。

**引用与验收。** 商用往往 `[n]` 与来源库绑定，无引用不算完成。现在有 **sources 注入 + prompt 约束**；尚无成稿 URL 白名单脚本、也无「跑 100 次」的评测表。内容仍可能 **简评瞎编**，但 URL 应逐渐向 sources 列表收敛。

**模型。** 商用多用云端强模型或大小模型分工。这里默认 **本地 7B**，也可通过 **LLM_*** 切云端；差距主要在 **稳定性与成本管控**，不是会不会配 Key。

**工程与安全。** 鉴权、限速、审计、SSRF 策略、多租户——个人 CLI / **默认只绑 127.0.0.1 的网页台** 仅 **reports 路径限制 + fetch scheme 校验**；**勿把网页台裸奔公网**（Key 在服务端 `.env`）。`trust_env=False` 是为 Ollama 避 macOS 代理坑，不是生产出网方案。

---

## 4. 和 Coding Agent、和框架：同构不同题

**Coding Agent**（Cursor、Claude Code 一类）Loop 形状往往相同，换的是 **read / write / shell / test** 和 **工作区沙箱**；验收是测试与 diff，风险是任意执行。系列笔记里 Coding 仍是下一赛道——**Loop 不变，换 Tool 包**，商用差距同样在沙箱与评测。

**LangGraph、CrewAI 等** 卖的是编排、checkpoint、并行 Tool、多 Agent 角色——不是替代表层 Tool Calling。我 **刻意先手写 Loop** 再对照框架：框架省 boilerplate，**不会自动变成商用**；个人调研 Agent 不必为了「像产品」先上图。

---

## 5. 刻意不做与以后可能补的（个人范围）

**近期不优先的（与「免费个人」一致）：**

- **长期 memory / 向量库**——调研任务以单次 run 的 messages + sources 为主，跨天记忆对个人简报价值有限。
- **硬编码 Plan 一轮 JSON**——报告类若 7B + sources + save nudge 仍不够，再考虑；简单资讯不付多一轮延迟。
- **自动化评测脚本 / CI**——有用，但属于工程习惯；需要时再补，不阻塞功能学习。
- **付费检索**——仍是无 Key 的 web/HN/RSS 主线；云端 LLM 已在第六篇作为 **可选**，不默认假设人人有 Key。

**若继续手写、仍不推翻 Loop，性价比较高的方向：**

- **fetch 侧 SSRF 基础**（禁内网 IP、可选域名 allowlist）——公网暴露前必备。
- **成稿引用校验**——Markdown 里 URL 是否 ⊆ `sources`（脚本层，不依赖模型）。
- **search 并发合并 / 缓存**——仍放在单个 `search_web` 内，不增加模型可见 Tool 数量。
- **DEV.to 等垂直源 Tool**（有 Key 时）——Tech 向摘要，不是通用新闻。
- **Coding Tool 包**——换题，Loop 同构。

云端大模型 + 付费搜索是 **捷径**，不是系列必答题；个人天花板更现实的路径是：**7B + 多免费源（web/HN/RSS）+ sources + save + 少量安全与校验**。

---

## 6. 读者自检（本机）

```bash
ollama list                              # 确认 qwen2.5:7b
python main.py -v --trace '…'            # tool 链、sources、Saved:
ls reports/                              # 落盘产物（*.md 通常 gitignore）
```

trace 里可关注：`[0] system` 是否出现 **【本轮已收集来源】**；`tool_results` 是否含 `Saved:`；第四篇式宽 query 与窄 query 的差异是否仍符合预期。

商用还会盯 **同一批问题的通过率、p95 延迟**——个人项目用「改代码前后各跑两次同一命令」即可，不必上监控平台。

---

## 7. 收束

**myAgent 现在：** 可 trace、可落盘、可约束引用的 **个人调研 Agent 原型**；与商用 **协议同构**（Tool + Loop + Observation），**能力与运维不同量级**。

**差最多的：** 稳定数据源、可测完成率、规划与长任务、生产安全——**不是** 再多挂两个 Tool 就对齐。

**与系列前文：** 一 Tool · 二 窗口 · 三 trim · 四 联网 · 五 报告与 save · 六 云模型与网页 · **七 边界（本文）**。代码仓库：

https://github.com/zealot2002/myagent

若你也在手写 Agent：先求 **一条 trace 跑通且能 Saved**，再对照本地图决定值不值得为 **评测、Plan、付费源** 付复杂度——比一开始就追商用功能列表，更不容易迷失在框架里。

系列目录：[系列导读](./00-系列导读.md)
