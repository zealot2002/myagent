from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Tool:
    """单个 Tool：OpenAI schema + 可执行函数。"""

    name: str
    schema: dict
    fn: Callable[..., str]
