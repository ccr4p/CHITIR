"""الوسائط: تحميل يوتيوب عبر yt-dlp وتحويل النص لصوت عبر gTTS.

مبادئ الأمان:
- لا صدفة أبدًا: الأوامر تُمرَّر كقائمة وسائط (exec) فلا حقن أوامر.
- الرابط يُقبل فقط من نطاقات يوتيوب (https) وبدون مستخدم/منفذ، والنص الحر يتحول إلى بحث ytsearch1.
- الفاصل `--` قبل الهدف يمنع تحويل أي نص إلى خيار لـ yt-dlp.
- العملية الفرعية تُشغَّل ببيئة نظيفة (بدون BOT_TOKEN) ومجلد مؤقت خاص يُحذف دائمًا.
- حدود: 10 دقائق، 48MB، مهلة 150 ثانية مع قتل العملية، ولا بثوث مباشرة ولا قوائم تشغيل.
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

ALLOWED_HOSTS = frozenset({"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
                           "youtu.be", "www.youtu.be"})
MAX_URL_LEN, MAX_QUERY_LEN, MAX_TTS_CHARS = 200, 100, 300
MAX_SECONDS = 600
MAX_FILE_BYTES = 48 * 1024 * 1024
DL_TIMEOUT = 150
TTS_TIMEOUT = 30
TTS_LANGS = frozenset({"ar", "en", "fr", "tr", "es", "de", "fa", "ur", "ru", "it"})
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ARABIC = re.compile(r"[\u0600-\u06FF]")


class MediaError(Exception):
    """رسالة آمنة تُعرض للمستخدم كما هي."""


def ytdlp_available() -> bool:
    return importlib.util.find_spec("yt_dlp") is not None


def tts_available() -> bool:
    return importlib.util.find_spec("gtts") is not None


# ---------------- التحقق من المدخلات ----------------
def _looks_like_url(token: str) -> bool:
    return "://" in token or token.lower().startswith("www.")


def _validate_url(url: str) -> str:
    if len(url) > MAX_URL_LEN or _CONTROL.search(url) or "\\" in url:
        raise MediaError("الرابط غير صالح.")
    if url.lower().startswith("www."):
        url = "https://" + url
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise MediaError("الرابط غير صالح.") from None
    host = (parts.hostname or "").lower()
    if parts.scheme.lower() not in ("http", "https") or parts.username or parts.password or port is not None:
        raise MediaError("يُسمح فقط بروابط يوتيوب العادية.")
    if host not in ALLOWED_HOSTS:
        raise MediaError("يُسمح فقط بروابط يوتيوب (youtube.com / youtu.be).")
    return parts._replace(scheme="https").geturl()


def parse_target(text: str) -> str:
    """رابط يوتيوب مُتحقَّق منه، أو بحث نصي مُحصَّن بالبادئة ytsearch1:"""
    text = text.strip()
    if not text:
        raise MediaError("اكتب رابط يوتيوب أو اسم المقطع.")
    first = text.split()[0]
    if _looks_like_url(first):
        return _validate_url(first)
    query = re.sub(r"\s+", " ", _CONTROL.sub(" ", text)).strip()
    if not query or len(query) > MAX_QUERY_LEN:
        raise MediaError(f"نص البحث يجب أن يكون بين 1 و{MAX_QUERY_LEN} حرفًا.")
    return "ytsearch1:" + query


def parse_tts(arg: str) -> tuple[str, str]:
    """(اللغة, النص). يمكن بدء النص برمز لغة مثل: en hello"""
    arg = _CONTROL.sub(" ", arg).strip()
    first, _, rest = arg.partition(" ")
    lang = None
    if first.lower() in TTS_LANGS and rest.strip():
        lang, arg = first.lower(), rest.strip()
    if not arg:
        raise MediaError("اكتب النص المراد نطقه. مثال: انطق مرحبا بكم")
    if len(arg) > MAX_TTS_CHARS:
        raise MediaError(f"النص طويل (الحد {MAX_TTS_CHARS} حرف).")
    return lang or ("ar" if _ARABIC.search(arg) else "en"), arg


# ---------------- yt-dlp ----------------
def build_args(target: str, outdir: str, kind: str) -> list[str]:
    args = [
        "--ignore-config", "--no-cache-dir", "--no-playlist", "--no-warnings", "--quiet", "--no-progress",
        "--socket-timeout", "15", "--retries", "2",
        "--max-filesize", "48M",
        "--match-filter", f"duration<={MAX_SECONDS} & !is_live",
        "--restrict-filenames", "-P", outdir, "-o", "%(id)s.%(ext)s",
        "--print", "%(title).100s", "--no-simulate",
    ]
    if kind == "audio":
        args += ["-f", "bestaudio/best", "-x", "--audio-format", "mp3", "--audio-quality", "5"]
    else:
        args += ["-f", "best[ext=mp4][height<=480]/best[height<=480]/best", "--merge-output-format", "mp4"]
    return args + ["--", target]


@dataclass
class MediaFile:
    path: Path
    title: str
    tmpdir: str

    def cleanup(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)


async def download(target: str, kind: str, *, prefix: list[str] | None = None,
                   timeout: float = DL_TIMEOUT) -> MediaFile:
    if kind not in ("audio", "video"):
        raise ValueError(kind)
    tmp = tempfile.mkdtemp(prefix="ytdl-")  # صلاحيات 0700
    try:
        cmd = (prefix or [sys.executable, "-m", "yt_dlp"]) + build_args(target, tmp, kind)
        env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": tmp,
               "LANG": "C.UTF-8", "PYTHONIOENCODING": "utf-8"}  # لا نمرّر BOT_TOKEN ولا أي أسرار
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=tmp, env=env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise MediaError("استغرق التحميل وقتًا طويلًا، أُلغي.") from None
        except BaseException:  # ومنها الإلغاء (CancelledError) عند إيقاف البوت: لا نترك عملية يتيمة
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        if proc.returncode != 0:
            log.warning("yt-dlp رمز=%s: %s", proc.returncode, err.decode("utf-8", "replace")[-300:])
            raise MediaError("تعذّر التحميل (الرابط غير مدعوم أو المقطع محجوب).")
        files = [p for p in Path(tmp).iterdir()
                 if p.is_file() and not p.is_symlink() and not p.name.endswith((".part", ".ytdl", ".temp"))]
        if not files:
            raise MediaError(f"لم أحصل على ملف. الحد المسموح: {MAX_SECONDS // 60} دقائق و48MB، ولا بثوث مباشرة.")
        best = max(files, key=lambda p: p.stat().st_size)
        if best.stat().st_size > MAX_FILE_BYTES:
            raise MediaError("الملف أكبر من حد تيليجرام للبوتات (50MB).")
        lines = out.decode("utf-8", "replace").strip().splitlines()
        return MediaFile(best, _CONTROL.sub("", lines[0])[:100] if lines else "", tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


# ---------------- تحويل النص لصوت ----------------
def _gtts_save(text: str, lang: str, path: str) -> None:
    from gtts import gTTS  # استيراد متأخر: الميزة اختيارية
    gTTS(text=text, lang=lang, timeout=15).save(path)


async def synthesize(text: str, lang: str) -> MediaFile:
    if lang not in TTS_LANGS:
        raise MediaError("لغة غير مدعومة.")
    if not tts_available():
        raise MediaError("ميزة النطق غير مثبّتة على هذا السيرفر.")
    tmp = tempfile.mkdtemp(prefix="tts-")
    try:
        path = Path(tmp) / "tts.mp3"
        try:
            await asyncio.wait_for(asyncio.to_thread(_gtts_save, text, lang, str(path)), TTS_TIMEOUT)
        except asyncio.TimeoutError:
            raise MediaError("انتهت مهلة خدمة النطق.") from None
        except Exception as e:  # أخطاء الشبكة/الخدمة
            log.warning("فشل gTTS: %s", type(e).__name__)
            raise MediaError("تعذّر تحويل النص إلى صوت الآن.") from None
        if not path.is_file() or path.stat().st_size == 0:
            raise MediaError("تعذّر تحويل النص إلى صوت.")
        return MediaFile(path, "", tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
