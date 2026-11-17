"""أدوات مشتركة: سياق الأمر، الرتب، وتحديد الهدف."""
from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass

from telegram import LinkPreviewOptions, Message, Update, User, Chat
from telegram.constants import ChatMemberStatus, ChatType
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from .. import ranks

GROUP_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP)
NO_PREVIEW = LinkPreviewOptions(is_disabled=True)
STATUS_TTL = 60.0
NEED_TARGET = "رد على رسالة الشخص، أو اكتب آيدي رقمي، أو معرّفًا سبق أن تكلّم فيه."


def esc(value) -> str:
    return html.escape(str(value), quote=False)


def mention(user_id: int, name: str | None = None) -> str:
    return f'<a href="tg://user?id={int(user_id)}">{esc(name or user_id)}</a>'


@dataclass
class Ctx:
    update: Update
    context: ContextTypes.DEFAULT_TYPE
    msg: Message
    chat: Chat
    user: User
    rank: int
    arg: str

    @property
    def db(self):
        return self.context.bot_data["db"]

    @property
    def cfg(self):
        return self.context.bot_data["cfg"]

    @property
    def is_group(self) -> bool:
        return self.chat.type in GROUP_TYPES

    async def reply(self, text: str) -> Message:
        return await self.msg.reply_html(text, link_preview_options=NO_PREVIEW)


async def _telegram_rank(context, chat_id: int, user_id: int) -> int:
    cache = context.bot_data["status_cache"]
    now = time.monotonic()
    hit = cache.get((chat_id, user_id))
    if hit and now - hit[0] < STATUS_TTL:
        return hit[1]
    level = ranks.NONE
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status == ChatMemberStatus.OWNER:
            level = ranks.OWNER
        elif member.status == ChatMemberStatus.ADMINISTRATOR:
            level = ranks.ADMIN
    except TelegramError:
        pass
    if len(cache) > 5000:
        cache.clear()
    cache[(chat_id, user_id)] = (now, level)
    return level


async def get_rank(context, chat: Chat, user_id: int) -> int:
    """الرتبة الفعلية = الأعلى بين: مطور (من .env)، رتبة البوت المخزنة، وحالة تيليجرام (مالك/مشرف)."""
    if user_id in context.bot_data["cfg"].dev_ids:
        return ranks.DEV
    if chat.type not in GROUP_TYPES:
        return ranks.NONE
    stored = context.bot_data["db"].get_rank(chat.id, user_id)
    return max(stored, await _telegram_rank(context, chat.id, user_id))


def resolve_target(ctx: Ctx, text: str | None = None) -> tuple[int, str | None] | None:
    """الهدف من الرد على رسالة، أو آيدي رقمي، أو @معرّف معروف في قاعدة البيانات."""
    replied = ctx.msg.reply_to_message
    if replied and replied.from_user:
        return replied.from_user.id, replied.from_user.full_name
    src = ctx.arg if text is None else text
    tokens = src.split()
    if not tokens:
        return None
    token = tokens[0]
    if re.fullmatch(r"[0-9]{1,15}", token):
        uid = int(token)
        return uid, ctx.db.user_name(uid)
    if token.startswith("@") and len(token) > 1:
        uid = ctx.db.find_user_id(token)
        return (uid, ctx.db.user_name(uid)) if uid else None
    return None


async def check_target(ctx: Ctx, uid: int) -> str | None:
    """رسالة خطأ إن لم يجز تنفيذ إجراء عقابي على الهدف، وإلا None."""
    if uid == ctx.context.bot.id:
        return "لا أستطيع تنفيذ ذلك على نفسي."
    if uid == ctx.user.id:
        return "لا يمكنك تنفيذ ذلك على نفسك."
    target_rank = await get_rank(ctx.context, ctx.chat, uid)
    if not ranks.can_act_on(ctx.rank, target_rank):
        return "لا تستطيع تنفيذ ذلك على من رتبته مساوية لرتبتك أو أعلى."
    return None
