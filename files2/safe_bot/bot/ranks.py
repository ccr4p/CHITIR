"""الرتب وقواعد من يستطيع فعل ماذا."""
from __future__ import annotations

from .parsing import normalize

NONE, VIP, ADMIN, MANAGER, CREATOR, OWNER, DEV = 0, 1, 2, 3, 4, 5, 9

LABELS = {NONE: "عضو", VIP: "مميز", ADMIN: "ادمن", MANAGER: "مدير", CREATOR: "منشئ", OWNER: "مالك", DEV: "مطور"}
_BY_WORD = {normalize(LABELS[r]): r for r in (VIP, ADMIN, MANAGER, CREATOR, OWNER)}


def label(rank: int) -> str:
    return LABELS.get(rank, "عضو")


def parse_rank(word: str) -> int | None:
    return _BY_WORD.get(normalize(word))


def can_grant(actor_rank: int, give: int) -> bool:
    """تستطيع منح رتبة أدنى من رتبتك فقط (المالك يستطيع منح مالك، والمطور كل شيء)."""
    if actor_rank >= DEV:
        return True
    return actor_rank > give or (actor_rank == OWNER and give == OWNER)


def can_act_on(actor_rank: int, target_rank: int) -> bool:
    """حظر/كتم/إنذار/خفض رتبة: فقط لمن رتبته أقل من رتبتك."""
    return actor_rank >= DEV or actor_rank > target_rank
