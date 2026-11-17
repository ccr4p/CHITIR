"""الحظر والكتم والإنذارات والتثبيت وإدارة الرتب."""
from __future__ import annotations

from telegram import ChatPermissions
from telegram.error import TelegramError

from .. import ranks
from ..parsing import normalize
from ..registry import command
from .common import NEED_TARGET, Ctx, check_target, esc, mention, resolve_target

MUTED = ChatPermissions(can_send_messages=False)
FALLBACK_UNMUTED = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True,
    can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
    can_send_other_messages=True, can_add_web_page_previews=True, can_invite_users=True,
)


async def _punish_target(ctx: Ctx):
    target = resolve_target(ctx)
    if not target:
        await ctx.reply(NEED_TARGET)
        return None
    uid, name = target
    if err := await check_target(ctx, uid):
        await ctx.reply(err)
        return None
    return uid, name


@command("حظر", "ban", rank=ranks.ADMIN, group_only=True)
async def ban(ctx: Ctx) -> None:
    if t := await _punish_target(ctx):
        await ctx.context.bot.ban_chat_member(ctx.chat.id, t[0])
        await ctx.reply(f"🚫 تم حظر {mention(*t)}")


@command("الغاء الحظر", "unban", rank=ranks.ADMIN, group_only=True)
async def unban(ctx: Ctx) -> None:
    if t := resolve_target(ctx):
        await ctx.context.bot.unban_chat_member(ctx.chat.id, t[0], only_if_banned=True)
        await ctx.reply(f"✅ تم إلغاء حظر {mention(*t)}")
    else:
        await ctx.reply(NEED_TARGET)


@command("طرد", "kick", rank=ranks.ADMIN, group_only=True)
async def kick(ctx: Ctx) -> None:
    if t := await _punish_target(ctx):
        await ctx.context.bot.ban_chat_member(ctx.chat.id, t[0])
        await ctx.context.bot.unban_chat_member(ctx.chat.id, t[0], only_if_banned=True)
        await ctx.reply(f"👢 تم طرد {mention(*t)}")


@command("كتم", "mute", rank=ranks.ADMIN, group_only=True)
async def mute(ctx: Ctx) -> None:
    if t := await _punish_target(ctx):
        await ctx.context.bot.restrict_chat_member(ctx.chat.id, t[0], permissions=MUTED)
        await ctx.reply(f"🔇 تم كتم {mention(*t)}")


@command("الغاء الكتم", "unmute", rank=ranks.ADMIN, group_only=True)
async def unmute(ctx: Ctx) -> None:
    t = resolve_target(ctx)
    if not t:
        await ctx.reply(NEED_TARGET)
        return
    perms = FALLBACK_UNMUTED
    try:
        full = await ctx.context.bot.get_chat(ctx.chat.id)
        perms = full.permissions or perms
    except TelegramError:
        pass
    await ctx.context.bot.restrict_chat_member(ctx.chat.id, t[0], permissions=perms)
    await ctx.reply(f"🔊 تم إلغاء كتم {mention(*t)}")


@command("انذار", "تحذير", "warn", rank=ranks.ADMIN, group_only=True)
async def warn(ctx: Ctx) -> None:
    t = await _punish_target(ctx)
    if not t:
        return
    uid, name = t
    count = ctx.db.add_warn(ctx.chat.id, uid)
    limit = int(ctx.db.get_setting(ctx.chat.id, "max_warns", "3"))
    if count >= limit:
        await ctx.context.bot.ban_chat_member(ctx.chat.id, uid)
        ctx.db.clear_warns(ctx.chat.id, uid)
        await ctx.reply(f"🚫 {mention(uid, name)} بلغ {limit} إنذارات وتم حظره.")
    else:
        await ctx.reply(f"⚠️ إنذار لـ {mention(uid, name)} ({count}/{limit})")


@command("الانذارات", "انذاراتي", group_only=True)
async def show_warns(ctx: Ctx) -> None:
    t = resolve_target(ctx) if ctx.rank >= ranks.ADMIN else None
    uid, name = t if t else (ctx.user.id, ctx.user.full_name)
    limit = ctx.db.get_setting(ctx.chat.id, "max_warns", "3")
    await ctx.reply(f"إنذارات {mention(uid, name)}: {ctx.db.get_warns(ctx.chat.id, uid)}/{limit}")


@command("مسح الانذارات", "حذف الانذارات", rank=ranks.ADMIN, group_only=True)
async def clear_warns(ctx: Ctx) -> None:
    if t := resolve_target(ctx):
        ctx.db.clear_warns(ctx.chat.id, t[0])
        await ctx.reply(f"🧹 تم مسح إنذارات {mention(*t)}")
    else:
        await ctx.reply(NEED_TARGET)


@command("ضع الانذارات", rank=ranks.MANAGER, group_only=True)
async def set_max_warns(ctx: Ctx) -> None:
    try:
        n = int(ctx.arg)
    except ValueError:
        n = 0
    if not 2 <= n <= 10:
        await ctx.reply("اكتب رقمًا بين 2 و10، مثال: ضع الانذارات 3")
        return
    ctx.db.set_setting(ctx.chat.id, "max_warns", str(n))
    await ctx.reply(f"✅ الحد الأقصى للإنذارات الآن {n}")


@command("تثبيت", "pin", rank=ranks.ADMIN, group_only=True)
async def pin(ctx: Ctx) -> None:
    if not ctx.msg.reply_to_message:
        await ctx.reply("رد على الرسالة المراد تثبيتها.")
        return
    await ctx.context.bot.pin_chat_message(ctx.chat.id, ctx.msg.reply_to_message.message_id,
                                           disable_notification=True)


@command("الغاء التثبيت", "الغاء تثبيت", "unpin", rank=ranks.ADMIN, group_only=True)
async def unpin(ctx: Ctx) -> None:
    replied = ctx.msg.reply_to_message
    await ctx.context.bot.unpin_chat_message(ctx.chat.id, replied.message_id if replied else None)


@command("الغاء تثبيت الكل", rank=ranks.MANAGER, group_only=True)
async def unpin_all(ctx: Ctx) -> None:
    await ctx.context.bot.unpin_all_chat_messages(ctx.chat.id)
    await ctx.reply("📌 تم إلغاء تثبيت كل الرسائل.")


@command("مسح", "حذف", rank=ranks.ADMIN, group_only=True)
async def delete_replied(ctx: Ctx) -> None:
    replied = ctx.msg.reply_to_message
    if not replied:
        await ctx.reply("رد على الرسالة المراد حذفها.")
        return
    await ctx.context.bot.delete_message(ctx.chat.id, replied.message_id)
    try:
        await ctx.msg.delete()
    except TelegramError:
        pass


# ---------------- الرتب ----------------
RANK_USAGE = "الصيغة: رفع مميز|ادمن|مدير|منشئ|مالك — بالرد على الشخص أو بآيديه."


@command("رفع", rank=ranks.ADMIN, group_only=True)
async def promote(ctx: Ctx) -> None:
    parts = ctx.arg.split(None, 1)
    give = ranks.parse_rank(parts[0]) if parts else None
    if give is None:
        await ctx.reply(RANK_USAGE)
        return
    if not ranks.can_grant(ctx.rank, give):
        await ctx.reply("لا تستطيع منح رتبة مساوية لرتبتك أو أعلى منها.")
        return
    t = resolve_target(ctx, parts[1] if len(parts) > 1 else "")
    if not t:
        await ctx.reply(NEED_TARGET)
        return
    if t[0] == ctx.context.bot.id:
        await ctx.reply("لا يمكن رفع البوت.")
        return
    ctx.db.set_rank(ctx.chat.id, t[0], give)
    await ctx.reply(f"⬆️ تم رفع {mention(*t)} إلى رتبة <b>{ranks.label(give)}</b>")


@command("تنزيل", rank=ranks.ADMIN, group_only=True)
async def demote(ctx: Ctx) -> None:
    parts = ctx.arg.split(None, 1)
    only = ranks.parse_rank(parts[0]) if parts else None
    rest = parts[1] if (only is not None and len(parts) > 1) else (ctx.arg if only is None else "")
    t = resolve_target(ctx, rest)
    if not t:
        await ctx.reply(NEED_TARGET)
        return
    current = ctx.db.get_rank(ctx.chat.id, t[0])
    if current == ranks.NONE:
        await ctx.reply("هذا الشخص لا يملك رتبة في البوت.")
        return
    if only is not None and only != current:
        await ctx.reply(f"رتبته الحالية <b>{ranks.label(current)}</b> وليست {ranks.label(only)}.")
        return
    if not ranks.can_act_on(ctx.rank, current):
        await ctx.reply("لا تستطيع تنزيل من رتبته مساوية لرتبتك أو أعلى.")
        return
    ctx.db.set_rank(ctx.chat.id, t[0], ranks.NONE)
    await ctx.reply(f"⬇️ تم تنزيل {mention(*t)} من رتبة <b>{ranks.label(current)}</b>")


def _make_list(rank_value: int):
    async def _list(ctx: Ctx) -> None:
        ids = ctx.db.list_rank(ctx.chat.id, rank_value)
        if not ids:
            await ctx.reply(f"لا يوجد أحد برتبة {ranks.label(rank_value)}.")
            return
        lines = [f"{i}. {mention(uid, ctx.db.user_name(uid))}" for i, uid in enumerate(ids, 1)]
        await ctx.reply(f"<b>قائمة {ranks.label(rank_value)}:</b>\n" + "\n".join(lines))
    return _list


for _words, _value in ((("المميزين",), ranks.VIP), (("الادمنيه",), ranks.ADMIN),
                       (("المدراء",), ranks.MANAGER), (("المنشئين",), ranks.CREATOR),
                       (("المالكين",), ranks.OWNER)):
    command(*_words, rank=ranks.ADMIN, group_only=True)(_make_list(_value))
