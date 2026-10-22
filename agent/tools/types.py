from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Tool:
    """name + OpenAI function schema + 实际执行的 Python 可调用对象。"""

    name: str
    schema: dict
    fn: Callable[..., str]
