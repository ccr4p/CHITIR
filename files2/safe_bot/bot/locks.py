"""أنواع القفل، كشف المخالفات، وحماية التكرار. لا يعتمد على مكتبة تيليجرام."""
from __future__ import annotations

import re
import time
from collections import deque
from typing import Hashable

from .parsing import normalize

LABELS = {
    "links": "الروابط", "usernames": "المعرفات", "photos": "الصور", "videos": "الفيديو",
    "stickers": "الملصقات", "gifs": "المتحركه", "forwards": "التوجيه", "documents": "الملفات",
    "voice": "الصوتيات", "contacts": "الجهات", "flood": "التكرار", "chat": "الدردشه", "bots": "البوتات",
}
_ALIASES = {"الفيديوهات": "videos", "الرابط": "links", "المتحركات": "gifs", "الصوت": "voice", "الملصق": "stickers"}
BY_NAME = {normalize(v): k for k, v in LABELS.items()} | {normalize(k): v for k, v in _ALIASES.items()}

_LINK_RE = re.compile(r"(?:https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/)\S+", re.I)
_USER_RE = re.compile(r"(?<!\w)@\w{4,32}")


def violated_locks(msg) -> set[str]:
    """أنواع المحتوى الموجودة في الرسالة (للمقارنة مع الأقفال المفعّلة)."""
    found: set[str] = set()
    ents = list(getattr(msg, "entities", None) or []) + list(getattr(msg, "caption_entities", None) or [])
    text = getattr(msg, "text", None) or getattr(msg, "caption", None) or ""
    if any(e.type in ("url", "text_link") for e in ents) or _LINK_RE.search(text):
        found.add("links")
    if any(e.type == "mention" for e in ents) or _USER_RE.search(text):
        found.add("usernames")
    if getattr(msg, "photo", None):
        found.add("photos")
    if getattr(msg, "video", None) or getattr(msg, "video_note", None):
        found.add("videos")
    if getattr(msg, "sticker", None):
        found.add("stickers")
    if getattr(msg, "animation", None):
        found.add("gifs")
    elif getattr(msg, "document", None):  # تيليجرام يضع document مع animation أيضًا
        found.add("documents")
    if getattr(msg, "forward_origin", None):
        found.add("forwards")
    if getattr(msg, "voice", None) or getattr(msg, "audio", None):
        found.add("voice")
    if getattr(msg, "contact", None):
        found.add("contacts")
    return found


class FloodGuard:
    def __init__(self, limit: int = 6, window: float = 4.0):
        self.limit, self.window = limit, window
        self._hits: dict[tuple[int, int], deque[float]] = {}

    def hit(self, chat_id: int, user_id: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits.setdefault((chat_id, user_id), deque())
        q.append(now)
        while q and now - q[0] > self.window:
            q.popleft()
        if len(self._hits) > 5000:
            for k in [k for k, v in self._hits.items() if not v or now - v[-1] > self.window]:
                del self._hits[k]
        return len(q) > self.limit


class Cooldown:
    """حدّ أدنى بين أمرين من نفس المستخدم."""

    def __init__(self, interval: float = 0.8):
        self.interval = interval
        self._last: dict[Hashable, float] = {}

    def allow(self, key: Hashable, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        last = self._last.get(key)
        if last is not None and now - last < self.interval:
            return False
        self._last[key] = now
        if len(self._last) > 10000:
            self._last = {k: t for k, t in self._last.items() if now - t < self.interval}
        return True
