"""قفل وفتح أنواع المحتوى وعرض إعدادات الحماية."""
from __future__ import annotations

from .. import locks, ranks
from ..parsing import normalize
from ..registry import command
from .common import Ctx

USAGE = "اكتب: قفل <النوع> — الأنواع: " + "، ".join(locks.LABELS.values())


@command("قفل", rank=ranks.MANAGER, group_only=True)
async def lock(ctx: Ctx) -> None:
    key = locks.BY_NAME.get(normalize(ctx.arg))
    if not key:
        await ctx.reply(USAGE)
        return
    ctx.db.lock(ctx.chat.id, key)
    extra = "\nتنبيه: يلزم أن أكون مشرفًا بصلاحية حذف الرسائل." if key != "bots" else ""
    await ctx.reply(f"🔒 تم قفل <b>{locks.LABELS[key]}</b>{extra}")


@command("فتح", rank=ranks.MANAGER, group_only=True)
async def unlock(ctx: Ctx) -> None:
    key = locks.BY_NAME.get(normalize(ctx.arg))
    if not key:
        await ctx.reply(USAGE.replace("قفل", "فتح", 1))
        return
    ctx.db.unlock(ctx.chat.id, key)
    await ctx.reply(f"🔓 تم فتح <b>{locks.LABELS[key]}</b>")


@command("الحمايه", "اعدادات الحمايه", "الاعدادات", rank=ranks.ADMIN, group_only=True)
async def show_locks(ctx: Ctx) -> None:
    active = ctx.db.locked(ctx.chat.id)
    lines = [f"{'🔒' if k in active else '🔓'} {v}" for k, v in locks.LABELS.items()]
    await ctx.reply("<b>إعدادات الحماية:</b>\n" + "\n".join(lines))
