from __future__ import annotations


def tool_schema(
    name: str,
    description: str,
    properties: dict[str, dict],
    required: list[str],
) -> dict:
    """组装 OpenAI 兼容的 tools[] 单项（type=function + JSON Schema 参数）。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
