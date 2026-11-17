"""معالجات الأحداث: تتبّع المستخدمين، تطبيق الأقفال، الترحيب."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from telegram import ChatPermissions
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop

from .. import ranks
from ..locks import violated_locks
from .common import GROUP_TYPES, NO_PREVIEW, get_rank, mention
from .content import DEFAULT_WELCOME, render_template

log = logging.getLogger(__name__)
MAX_WELCOMES_PER_EVENT = 3


async def track(update, context) -> None:
    """يحفظ (آيدي، معرّف، اسم) ليتمكن البوت من تحويل @معرّف إلى آيدي. الكتابة محدودة بمرة كل 10 دقائق."""
    user, chat = update.effective_user, update.effective_chat
    if user is None or user.is_bot:
        return
    cache, now = context.bot_data["seen_cache"], time.monotonic()
    prev = cache.get(user.id)
    if prev and prev[0] == user.username and now - prev[1] < 600:
        return
    db = context.bot_data["db"]
    db.upsert_user(user.id, user.username, user.first_name)
    if chat is not None and chat.type in GROUP_TYPES:
        db.add_chat(chat.id, chat.title or "")
    if len(cache) > 20000:
        cache.clear()
    cache[user.id] = (user.username, now)


async def enforce(update, context) -> None:
    """يحذف الرسائل المخالفة للأقفال المفعّلة (ما لم يكن المرسل مميزًا فأعلى)."""
    msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
    if msg is None or chat is None or chat.type not in GROUP_TYPES or user is None or user.is_bot:
        return
    locked = context.bot_data["db"].locked(chat.id)
    if not locked:
        return
    if await get_rank(context, chat, user.id) >= ranks.VIP:
        return
    hit = locked & violated_locks(msg)
    if "chat" in locked:
        hit.add("chat")
    if "flood" in locked and context.bot_data["flood"].hit(chat.id, user.id):
        hit.add("flood")
    if not hit:
        return
    try:
        await msg.delete()
    except TelegramError as e:
        log.warning("تعذّر حذف رسالة مخالفة في %s: %s", chat.id, e)
        return
    if "flood" in hit:
        until = datetime.now(timezone.utc) + timedelta(minutes=10)
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions(can_send_messages=False), until_date=until)
        except TelegramError as e:
            log.warning("تعذّر كتم مُكرِّر في %s: %s", chat.id, e)
    raise ApplicationHandlerStop


async def on_new_members(update, context) -> None:
    msg, chat = update.effective_message, update.effective_chat
    if msg is None or chat is None or chat.type not in GROUP_TYPES:
        return
    db = context.bot_data["db"]
    db.add_chat(chat.id, chat.title or "")
    locked = db.locked(chat.id)
    adder = update.effective_user
    adder_rank = await get_rank(context, chat, adder.id) if adder else ranks.NONE
    humans = []
    for member in msg.new_chat_members or []:
        if member.id == context.bot.id:
            continue
        if member.is_bot:
            if "bots" in locked and adder_rank < ranks.ADMIN:
                try:
                    await context.bot.ban_chat_member(chat.id, member.id)
                except TelegramError as e:
                    log.warning("تعذّر طرد بوت في %s: %s", chat.id, e)
            continue
        db.upsert_user(member.id, member.username, member.first_name)
        humans.append(member)
    if humans and db.get_setting(chat.id, "welcome_on", "1") == "1":
        template = db.get_setting(chat.id, "welcome_text", DEFAULT_WELCOME)
        for member in humans[:MAX_WELCOMES_PER_EVENT]:
            text = render_template(template, mention(member.id, member.full_name), chat.title or "")
            await context.bot.send_message(chat.id, text, parse_mode=ParseMode.HTML,
                                           link_preview_options=NO_PREVIEW)
