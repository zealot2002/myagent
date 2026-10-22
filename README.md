# myagent

从零手写 Agent 实验仓库：Ollama + Tool Calling + 最小 Loop（无 LangChain/LangGraph）。

文档见 [`docs/`](docs/)。

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ollama pull qwen2.5:7b
python main.py -i
```
