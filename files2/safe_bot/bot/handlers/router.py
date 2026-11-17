"""موزّع الأوامر النصية العربية/الإنجليزية + الردود المخصصة."""
from __future__ import annotations

import logging

from telegram.error import BadRequest, Forbidden, TelegramError

from ..parsing import normalize, parse_command
from ..registry import COMMANDS
from . import content, media, moderation, protection, tools  # noqa: F401  (استيرادها يسجّل الأوامر)
from .common import GROUP_TYPES, NO_PREVIEW, Ctx, get_rank

log = logging.getLogger(__name__)
PERMISSION_HINT = "تعذّر التنفيذ. تأكد أنني مشرف في المجموعة وأملك الصلاحية المطلوبة (حذف/حظر/تثبيت)."


async def on_text(update, context) -> None:
    msg, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if msg is None or user is None or chat is None or not msg.text or user.is_bot:
        return
    in_group = chat.type in GROUP_TYPES
    parsed = parse_command(msg.text, COMMANDS)

    if parsed is None:
        if in_group and context.bot_data["cooldown"].allow(("reply", chat.id)):
            key = normalize(msg.text)
            if 0 < len(key) <= 60:
                response = context.bot_data["db"].get_reply(chat.id, key)
                if response:
                    await msg.reply_text(response, link_preview_options=NO_PREVIEW)  # نص عادي بدون HTML
        return

    name, arg = parsed
    cmd = COMMANDS[name]
    if not context.bot_data["cooldown"].allow(("cmd", user.id)):
        return
    if cmd.group_only and not in_group:
        await msg.reply_text("هذا الأمر يعمل داخل المجموعات فقط.")
        return
    rank = await get_rank(context, chat, user.id)
    if rank < cmd.rank:
        return  # تجاهل صامت: لا نردّ على من لا يملك الصلاحية
    ctx = Ctx(update, context, msg, chat, user, rank, arg)
    try:
        await cmd.handler(ctx)
    except (BadRequest, Forbidden) as e:
        log.warning("فشل الأمر %s في %s: %s", cmd.name, chat.id, e)
        await _safe_reply(msg, PERMISSION_HINT)
    except TelegramError as e:
        log.warning("خطأ تيليجرام في الأمر %s: %s", cmd.name, e)


async def _safe_reply(msg, text: str) -> None:
    try:
        await msg.reply_text(text)
    except TelegramError:
        pass
