import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
LOG_TAG = "joyjoy"

# 上下文治理：每次 call LLM 前对 state.messages 就地 trim
CONTEXT_TRIM_ENABLED = os.getenv("CONTEXT_TRIM_ENABLED", "true").lower() in ("1", "true", "yes")
CONTEXT_MAX_TOKENS = int(os.getenv("CONTEXT_MAX_TOKENS", "8000"))
CONTEXT_TOOL_MAX_CHARS = int(os.getenv("CONTEXT_TOOL_MAX_CHARS", "2000"))
