"""نقطة التشغيل. التوكن يُقرأ من البيئة فقط ولا يُطبع ولا يُسجَّل أبدًا."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import Update
from telegram.ext import Application, MessageHandler, filters

from bot.config import TOKEN_RE, load_config
from bot.db import Database
from bot.handlers.events import enforce, on_new_members, track
from bot.handlers.router import on_text
from bot.locks import Cooldown, FloodGuard

log = logging.getLogger("bot")


class RedactingFormatter(logging.Formatter):
    """يحجب أي نص يشبه توكن بوت من كل سطر سجل (بما فيه تتبّع الأخطاء)."""

    def format(self, record: logging.LogRecord) -> str:
        return TOKEN_RE.sub("<token>", super().format(record))


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=getattr(logging, level, logging.INFO), handlers=[handler], force=True)
    # httpx يطبع روابط الطلبات وفيها التوكن عند مستوى INFO
    for noisy in ("httpx", "httpcore", "telegram.ext.ExtBot"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def on_error(update: object, context) -> None:
    log.error("خطأ غير معالج", exc_info=context.error)


def main() -> None:
    cfg = load_config()
    setup_logging(cfg.log_level)
    Path(cfg.db_path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = Database(cfg.db_path)

    app = Application.builder().token(cfg.token).build()
    app.bot_data.update(cfg=cfg, db=db, flood=FloodGuard(), cooldown=Cooldown(0.8),
                        status_cache={}, seen_cache={},
                        media_sem=asyncio.Semaphore(2), media_cooldown=Cooldown(30.0))

    app.add_handler(MessageHandler(filters.ALL, track), group=-1)
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & (filters.UpdateType.MESSAGE | filters.UpdateType.EDITED_MESSAGE), enforce), group=0)
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members), group=1)
    app.add_handler(MessageHandler(filters.TEXT & filters.UpdateType.MESSAGE, on_text), group=2)
    app.add_error_handler(on_error)

    log.info("البوت يعمل. المطورون: %d", len(cfg.dev_ids))
    app.run_polling(allowed_updates=["message", "edited_message"], drop_pending_updates=True)


if __name__ == "__main__":
    main()
