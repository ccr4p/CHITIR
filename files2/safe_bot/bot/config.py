"""تحميل الإعدادات من متغيرات البيئة / ملف .env (بدون أي مكتبات خارجية)."""
from __future__ import annotations

import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

TOKEN_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")


@dataclass(frozen=True)
class Config:
    token: str
    dev_ids: frozenset[int]
    db_path: str
    log_level: str
    enable_media: bool = True


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    try:
        mode = path.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            print(f"تحذير: صلاحيات {path} مفتوحة للآخرين. نفّذ: chmod 600 {path}", file=sys.stderr)
    except OSError:
        pass
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config(env_file: str = ".env") -> Config:
    _load_dotenv(Path(env_file))
    token = os.environ.pop("BOT_TOKEN", "").strip()  # يُزال من البيئة كي لا يرثه أي برنامج فرعي
    if not TOKEN_RE.fullmatch(token):
        raise SystemExit("BOT_TOKEN مفقود أو شكله غير صحيح. ضعه في ملف .env (انظر .env.example).")
    devs = frozenset(int(x) for x in re.split(r"[,\s]+", os.environ.get("DEV_IDS", "")) if x.isdigit())
    if not devs:
        raise SystemExit("DEV_IDS مفقود. ضع آيدي حسابك الرقمي (مثلاً من @userinfobot).")
    return Config(
        token=token,
        dev_ids=devs,
        db_path=os.environ.get("DB_PATH", "data/bot.db"),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        enable_media=os.environ.get("ENABLE_MEDIA", "1") == "1",
    )
