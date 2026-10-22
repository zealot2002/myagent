const messagesEl = document.getElementById("messages");
const timelineEl = document.getElementById("timeline");
const sourcesEl = document.getElementById("sources");
const sourcesCountEl = document.getElementById("sources-count");
const form = document.getElementById("form");
const input = document.getElementById("input");
const btnSend = document.getElementById("btn-send");
const btnReset = document.getElementById("btn-reset");
const multiCheck = document.getElementById("multi");
const llmLabel = document.getElementById("llm-label");

let sessionId = null;

function addBubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  messagesEl.appendChild(div);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function addTimeline(tag, body, kind = "") {
  const div = document.createElement("div");
  div.className = `ev ${kind}`;
  div.innerHTML = `<span class="tag">${tag}</span>${body}`;
  timelineEl.appendChild(div);
  timelineEl.scrollTop = timelineEl.scrollHeight;
}

function renderSources(sources) {
  sourcesEl.innerHTML = "";
  sourcesCountEl.textContent = String(sources.length);
  for (const s of sources) {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = s.url || "#";
    a.target = "_blank";
    a.rel = "noopener";
    a.textContent = `[${s.id}] ${s.title || s.url}`;
    li.appendChild(a);
    sourcesEl.appendChild(li);
  }
}

async function ensureSession() {
  if (sessionId) return sessionId;
  const res = await fetch("/api/session", { method: "POST" });
  const data = await res.json();
  sessionId = data.session_id;
  return sessionId;
}

async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    const data = await res.json();
    llmLabel.textContent = data.llm || "—";
  } catch {
    llmLabel.textContent = "无法读取配置";
  }
}

async function sendMessage(text) {
  await ensureSession();
  btnSend.disabled = true;
  addBubble("user", text);

  const reset = !multiCheck.checked;
  if (reset) {
    timelineEl.innerHTML = "";
    renderSources([]);
  }

  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message: text,
      reset,
    }),
  });

  const newSid = res.headers.get("X-Session-Id");
  if (newSid) sessionId = newSid;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalAnswer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";

    for (const chunk of parts) {
      const line = chunk.trim();
      if (!line.startsWith("data:")) continue;
      const json = line.slice(5).trim();
      let ev;
      try {
        ev = JSON.parse(json);
      } catch {
        continue;
      }
      handleEvent(ev, (ans) => {
        finalAnswer = ans;
      });
    }
  }

  if (finalAnswer) {
    addBubble("assistant", finalAnswer);
  }
  btnSend.disabled = false;
}

function handleEvent(ev, setAnswer) {
  const type = ev.event;
  if (type === "step") {
    addTimeline(
      "Step",
      `LLM 第 ${ev.loop}/${ev.max_loops} 轮（累计 call ${ev.llm_calls}）`,
      "step"
    );
  } else if (type === "assistant_tools") {
    const names = (ev.tool_calls || []).map((t) => t.name).join(", ");
    addTimeline("Tool 计划", names, "tool");
  } else if (type === "tool_start") {
    addTimeline(
      "调用",
      `${ev.name}<pre>${JSON.stringify(ev.arguments, null, 0)}</pre>`,
      "tool"
    );
  } else if (type === "tool_end") {
    addTimeline(
      "结果",
      `${ev.name} · sources=${ev.sources_count}<pre>${escapeHtml(ev.preview || "")}</pre>`,
      "tool"
    );
  } else if (type === "done") {
    if (ev.sources) renderSources(ev.sources);
    setAnswer(ev.answer || "");
    addTimeline("完成", "已返回最终答案", "done");
  } else if (type === "finished") {
    setAnswer(ev.answer || "");
  } else if (type === "error") {
    addBubble("system", ev.message || "未知错误");
    addTimeline("错误", escapeHtml(ev.message || ""), "done");
  }
}

function escapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  sendMessage(text).catch((err) => {
    btnSend.disabled = false;
    addBubble("system", String(err));
  });
});

btnReset.addEventListener("click", async () => {
  sessionId = null;
  messagesEl.innerHTML = "";
  timelineEl.innerHTML = "";
  renderSources([]);
  await ensureSession();
  addBubble("system", "已开启新会话");
});

loadConfig();
ensureSession();
