from __future__ import annotations

import ast
import operator

from agent.tools.schema import tool_schema
from agent.tools.types import Tool

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_ast(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported operator: {type(node.op).__name__}")
        return op(_eval_ast(node.left), _eval_ast(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError(f"unsupported unary: {type(node.op).__name__}")
        return op(_eval_ast(node.operand))
    raise ValueError(f"unsupported expression: {type(node).__name__}")


def calculator(expression: str) -> str:
    tree = ast.parse(expression.strip(), mode="eval")
    result = _eval_ast(tree)
    if result == int(result):
        return str(int(result))
    return str(result)


CALCULATOR = Tool(
    name="calculator",
    schema=tool_schema(
        "calculator",
        (
            "对数学表达式求精确数值。"
            "用于：四则运算、括号、幂运算等需要准确结果的问题。"
            "不要用于：单位换算、符号推导、解释公式含义（应直接回答）。"
        ),
        {
            "expression": {
                "type": "string",
                "description": "仅含数字与运算符的表达式，例如 123 * 456 + 789",
            }
        },
        ["expression"],
    ),
    fn=calculator,
)
