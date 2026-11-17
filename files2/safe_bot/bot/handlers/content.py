"""الترحيب والقوانين والردود المخصصة."""
from __future__ import annotations

from .. import ranks
from ..parsing import normalize
from ..registry import COMMANDS, command
from .common import Ctx, esc

MAX_WELCOME, MAX_RULES = 500, 1500
MAX_WORD, MAX_RESPONSE, MAX_REPLIES = 40, 500, 100
DEFAULT_WELCOME = "أهلاً بك {name} في {title} 🌹"


def render_template(template: str, name_html: str, title: str) -> str:
    """نص المستخدم يُهرَّب أولًا ثم تُستبدل المتغيرات، فلا يمكن حقن HTML."""
    return esc(template).replace("{name}", name_html).replace("{title}", esc(title))


@command("ضع ترحيب", "وضع ترحيب", rank=ranks.MANAGER, group_only=True)
async def set_welcome(ctx: Ctx) -> None:
    if not ctx.arg or len(ctx.arg) > MAX_WELCOME:
        await ctx.reply(f"اكتب نص الترحيب (حتى {MAX_WELCOME} حرف). يمكنك استخدام {{name}} و{{title}}.")
        return
    ctx.db.set_setting(ctx.chat.id, "welcome_text", ctx.arg)
    await ctx.reply("✅ تم حفظ الترحيب.")


@command("الترحيب", group_only=True)
async def show_welcome(ctx: Ctx) -> None:
    text = ctx.db.get_setting(ctx.chat.id, "welcome_text", DEFAULT_WELCOME)
    await ctx.reply(render_template(text, esc(ctx.user.full_name), ctx.chat.title or ""))


@command("تفعيل الترحيب", rank=ranks.MANAGER, group_only=True)
async def welcome_on(ctx: Ctx) -> None:
    ctx.db.set_setting(ctx.chat.id, "welcome_on", "1")
    await ctx.reply("✅ تم تفعيل الترحيب.")


@command("تعطيل الترحيب", rank=ranks.MANAGER, group_only=True)
async def welcome_off(ctx: Ctx) -> None:
    ctx.db.set_setting(ctx.chat.id, "welcome_on", "0")
    await ctx.reply("✅ تم تعطيل الترحيب.")


@command("ضع القوانين", "وضع القوانين", rank=ranks.MANAGER, group_only=True)
async def set_rules(ctx: Ctx) -> None:
    if not ctx.arg or len(ctx.arg) > MAX_RULES:
        await ctx.reply(f"اكتب نص القوانين (حتى {MAX_RULES} حرف).")
        return
    ctx.db.set_setting(ctx.chat.id, "rules", ctx.arg)
    await ctx.reply("✅ تم حفظ القوانين.")


@command("القوانين", group_only=True)
async def show_rules(ctx: Ctx) -> None:
    text = ctx.db.get_setting(ctx.chat.id, "rules")
    await ctx.reply(f"<b>قوانين المجموعة:</b>\n{esc(text)}" if text else "لم تُحدَّد قوانين بعد.")


# ---------------- الردود ----------------
@command("اضف رد", rank=ranks.MANAGER, group_only=True)
async def add_reply(ctx: Ctx) -> None:
    word, sep, response = ctx.arg.partition("=")
    key, response = normalize(word), response.strip()
    if not sep or not key or not response:
        await ctx.reply("الصيغة: اضف رد الكلمة = نص الرد")
        return
    if len(key) > MAX_WORD or len(response) > MAX_RESPONSE:
        await ctx.reply(f"الكلمة حتى {MAX_WORD} حرف والرد حتى {MAX_RESPONSE} حرف.")
        return
    if key in COMMANDS:
        await ctx.reply("هذه الكلمة محجوزة لأمر في البوت.")
        return
    if ctx.db.get_reply(ctx.chat.id, key) is None and ctx.db.count_replies(ctx.chat.id) >= MAX_REPLIES:
        await ctx.reply(f"وصلت للحد الأقصى ({MAX_REPLIES} ردًا).")
        return
    ctx.db.set_reply(ctx.chat.id, key, response)
    await ctx.reply("✅ تمت إضافة الرد.")


@command("حذف رد", "مسح رد", rank=ranks.MANAGER, group_only=True)
async def delete_reply(ctx: Ctx) -> None:
    ok = ctx.db.del_reply(ctx.chat.id, normalize(ctx.arg))
    await ctx.reply("🗑 تم حذف الرد." if ok else "لا يوجد رد بهذه الكلمة.")


@command("الردود", rank=ranks.ADMIN, group_only=True)
async def list_replies(ctx: Ctx) -> None:
    words = ctx.db.list_replies(ctx.chat.id)
    await ctx.reply("<b>الردود:</b>\n" + "\n".join(f"• {esc(w)}" for w in words) if words else "لا توجد ردود.")


@command("مسح الردود", rank=ranks.MANAGER, group_only=True)
async def clear_replies(ctx: Ctx) -> None:
    ctx.db.clear_replies(ctx.chat.id)
    await ctx.reply("🧹 تم مسح كل الردود.")
