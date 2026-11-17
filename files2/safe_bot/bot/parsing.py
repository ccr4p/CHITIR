"""تطبيع النص العربي وتحليل الأوامر. لا يعتمد على مكتبة تيليجرام."""
from __future__ import annotations

import re
from typing import Container

_STRIP = re.compile("[\u064B-\u065F\u0670\u0640]")  # التشكيل والتطويل
_MAP = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", _STRIP.sub("", text).translate(_MAP)).strip().lower()


def to_ascii_digits(text: str) -> str:
    return text.translate(_DIGITS)


def parse_command(text: str, known: Container[str], max_words: int = 3) -> tuple[str, str] | None:
    """يرجع (اسم_الأمر_المطبّع, النص_المتبقي) أو None. يفضّل الأمر الأطول."""
    text = text.strip()
    if not text:
        return None
    if text.startswith("/"):
        head, *tail = text[1:].split(None, 1)
        head = head.split("@", 1)[0]
        text = head + (" " + tail[0] if tail else "")
    words = text.split()
    for n in range(min(max_words, len(words)), 0, -1):
        name = normalize(" ".join(words[:n]))
        if name in known:
            pieces = text.split(None, n)
            return name, (pieces[n].strip() if len(pieces) > n else "")
    return None
