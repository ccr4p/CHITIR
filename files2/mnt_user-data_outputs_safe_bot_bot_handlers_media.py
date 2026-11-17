"""أوامر يوتيوب والنطق. كل المنطق الأمني في bot/media.py."""
from __future__ import annotations

import logging
import shutil

from telegram.error import TelegramError

from .. import media, ranks
from ..registry import command
from .common import Ctx, esc

log = logging.getLogger(__name__)
MEDIA_USAGE = "الصيغة: يوتيوب <رابط أو اسم المقطع> (صوت) — تحميل فيديو <رابط أو اسم> — انطق <نص>"


def _enabled(ctx: Ctx) -> bool:
    return ctx.cfg.enable_media and ctx.db.get_setting(ctx.chat.id, "media", "1") == "1"


async def _download(ctx: Ctx, kind: str) -> None:
    if not _enabled(ctx):
        await ctx.reply("التحميل معطّل هنا.")
        return
    if not media.ytdlp_available():
        await ctx.reply("ميزة التحميل غير مثبّتة على هذا السيرفر (requirements-media.txt).")
        return
    if kind == "audio" and not shutil.which("ffmpeg"):
        await ctx.reply("تحويل الصوت يحتاج ffmpeg على السيرفر.")
        return
    try:
        target = media.parse_target(ctx.arg)
    except media.MediaError as e:
        await ctx.reply(f"{esc(e)}\n{MEDIA_USAGE}")
        return
    bd = ctx.context.bot_data
    if not bd["media_cooldown"].allow(("dl", ctx.user.id)):
        await ctx.reply("⏳ انتظر قليلًا، يُسمح بتحميل واحد كل 30 ثانية.")
        return
    sem = bd["media_sem"]
    if sem.locked():
        await ctx.reply("البوت مشغول بتحميلات أخرى، حاول بعد قليل.")
        return
    status = await ctx.reply("⏳ جارٍ التحميل...")
    item = None
    try:
        async with sem:
            item = await media.download(target, kind)
        with open(item.path, "rb") as f:
            if kind == "audio":
                await ctx.msg.reply_audio(f, title=item.title or None, caption=item.title or None,
                                          read_timeout=120, write_timeout=120)
            elif item.path.suffix.lower() == ".mp4":
                await ctx.msg.reply_video(f, caption=item.title or None, supports_streaming=True,
                                          read_timeout=120, write_timeout=120)
            else:
                await ctx.msg.reply_document(f, caption=item.title or None, read_timeout=120, write_timeout=120)
    except media.MediaError as e:
        await ctx.reply(f"❌ {esc(e)}")
    except TelegramError as e:
        log.warning("فشل إرسال الوسائط: %s", e)
        await ctx.reply("❌ تعذّر إرسال الملف.")
    finally:
        if item:
            item.cleanup()
        try:
            await status.delete()
        except TelegramError:
            pass


@command("يوتيوب", "yt", "تحميل صوت")
async def yt_audio(ctx: Ctx) -> None:
    await _download(ctx, "audio")


@command("تحميل فيديو", "فيديو يوتيوب")
async def yt_video(ctx: Ctx) -> None:
    await _download(ctx, "video")


@command("انطق", "نطق", "tts", "تحويل لصوت")
async def speak(ctx: Ctx) -> None:
    if not _enabled(ctx):
        await ctx.reply("هذه الميزة معطّلة هنا.")
        return
    try:
        lang, text = media.parse_tts(ctx.arg)
    except media.MediaError as e:
        await ctx.reply(esc(e))
        return
    if not ctx.context.bot_data["media_cooldown"].allow(("tts", ctx.user.id)):
        await ctx.reply("⏳ انتظر قليلًا قبل الطلب التالي.")
        return
    item = None
    try:
        item = await media.synthesize(text, lang)
        with open(item.path, "rb") as f:
            await ctx.msg.reply_audio(f, title="نطق", read_timeout=60, write_timeout=60)
    except media.MediaError as e:
        await ctx.reply(f"❌ {esc(e)}")
    except TelegramError as e:
        log.warning("فشل إرسال الصوت: %s", e)
        await ctx.reply("❌ تعذّر إرسال الملف.")
    finally:
        if item:
            item.cleanup()


@command("تفعيل التحميل", rank=ranks.MANAGER, group_only=True)
async def media_on(ctx: Ctx) -> None:
    ctx.db.set_setting(ctx.chat.id, "media", "1")
    await ctx.reply("✅ تم تفعيل التحميل والنطق.")


@command("تعطيل التحميل", rank=ranks.MANAGER, group_only=True)
async def media_off(ctx: Ctx) -> None:
    ctx.db.set_setting(ctx.chat.id, "media", "0")
    await ctx.reply("✅ تم تعطيل التحميل والنطق.")
