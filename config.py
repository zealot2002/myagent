import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "10"))
LOG_TAG = "joyjoy"
