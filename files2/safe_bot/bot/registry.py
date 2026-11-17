"""سجل الأوامر: كل أمر يُسجَّل بمزخرف @command مع الحد الأدنى للرتبة."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .parsing import normalize


@dataclass(frozen=True)
class Command:
    name: str
    handler: Callable
    rank: int
    group_only: bool


COMMANDS: dict[str, Command] = {}


def command(*names: str, rank: int = 0, group_only: bool = False):
    def deco(fn):
        for n in names:
            key = normalize(n)
            if key in COMMANDS:
                raise RuntimeError(f"أمر مكرر: {n}")
            COMMANDS[key] = Command(names[0], fn, rank, group_only)
        return fn
    return deco
