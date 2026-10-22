import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
LOG_TAG = "joyjoy"

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
