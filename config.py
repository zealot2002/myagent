import os
from dotenv import load_dotenv

load_dotenv()

# LLM：OpenAI 兼容端点。Key 优先 LLM_API_KEY，否则可读 shell 里的 GLM_API_KEY
_llm_key = (os.getenv("LLM_API_KEY") or os.getenv("GLM_API_KEY") or "").strip()
_use_cloud = bool(_llm_key)

if os.getenv("LLM_BASE_URL"):
    LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
elif _use_cloud and (os.getenv("LLM_PROVIDER") or "").lower() == "glm":
    LLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4/"
else:
    LLM_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

if os.getenv("LLM_MODEL"):
    LLM_MODEL = os.getenv("LLM_MODEL", "")
elif _use_cloud and (os.getenv("LLM_PROVIDER") or "").lower() == "glm":
    LLM_MODEL = os.getenv("GLM_MODEL", "glm-4-flash")
else:
    LLM_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

LLM_API_KEY = _llm_key if _llm_key else "ollama"

# 本地 Ollama 配置（与当前 LLM 端点无关，便于切回）
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
LOG_TAG = "joyjoy"

WEB_HOST = os.getenv("WEB_HOST", "127.0.0.1")
WEB_PORT = int(os.getenv("WEB_PORT", "8765"))

# 上下文治理：每次 call LLM 前对 state.messages 就地 trim
CONTEXT_TRIM_ENABLED = os.getenv("CONTEXT_TRIM_ENABLED", "true").lower() in ("1", "true", "yes")
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "8000"))
CONTEXT_TOOL_MAX_CHARS = int(os.getenv("CONTEXT_TOOL_MAX_CHARS", "2000"))

FETCH_MAX_BYTES = int(os.getenv("FETCH_MAX_BYTES", "512000"))
FETCH_TIMEOUT_SEC = float(os.getenv("FETCH_TIMEOUT_SEC", "20"))

# search_web：无 API Key 多源串行；单源超时 + 整次调用总预算
SEARCH_TIMEOUT_SEC = float(os.getenv("SEARCH_TIMEOUT_SEC", "12"))
SEARCH_BUDGET_SEC = float(os.getenv("SEARCH_BUDGET_SEC", "28"))

REPORTS_DIR = os.getenv("REPORTS_DIR", "reports")
SAVE_MARKDOWN_MAX_BYTES = int(os.getenv("SAVE_MARKDOWN_MAX_BYTES", "512000"))

HN_MAX_RESULTS = int(os.getenv("HN_MAX_RESULTS", "15"))
RSS_MAX_ENTRIES = int(os.getenv("RSS_MAX_ENTRIES", "15"))
RSS_MAX_BYTES = int(os.getenv("RSS_MAX_BYTES", "512000"))

SOURCES_MAX_IN_PROMPT = int(os.getenv("SOURCES_MAX_IN_PROMPT", "25"))


def llm_endpoint_label() -> str:
    """CLI / 网页展示用，不含 API Key。"""
    if LLM_API_KEY == "ollama":
        key_hint = "（本地 Ollama 占位 Key）"
    elif os.getenv("LLM_API_KEY"):
        key_hint = "（LLM_API_KEY）"
    elif os.getenv("GLM_API_KEY"):
        key_hint = "（GLM_API_KEY）"
    else:
        key_hint = "（API Key 已配置）"
    return f"{LLM_MODEL} @ {LLM_BASE_URL} {key_hint}"
