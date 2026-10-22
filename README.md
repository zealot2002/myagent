# myagent

从零手写 Agent 实验仓库：OpenAI 兼容 LLM（默认 Ollama）+ Tool Calling + 最小 Loop（无 LangChain/LangGraph）。

文档见 [`docs/`](docs/)（[系列导读](docs/00-系列导读.md)）。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 本地 Ollama 或填写 LLM_API_KEY
ollama pull qwen2.5:7b # 若用本地模型

python main.py -i -v --trace
python -m web.server   # http://127.0.0.1:8765 调研台
```
