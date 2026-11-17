import asyncio
import json
import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot import media
from bot.media import MediaError, build_args, parse_target, parse_tts

FAKE = [sys.executable, str(Path(__file__).with_name("fake_ytdlp.py"))]


class TargetTests(unittest.TestCase):
    def test_valid_urls(self):
        for u in ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ",
                  "http://m.youtube.com/watch?v=abc", "www.youtube.com/watch?v=abc",
                  "https://music.youtube.com/watch?v=abc"]:
            self.assertTrue(parse_target(u).startswith("https://"), u)

    def test_url_with_trailing_text_uses_first_token(self):
        self.assertEqual(parse_target("https://youtu.be/abc يا بوت"), "https://youtu.be/abc")

    def test_rejects_bad_urls(self):
        bad = ["https://evil.com/youtube.com", "https://youtube.com.evil.com/x", "http://localhost:8080/x",
               "http://127.0.0.1/x", "file:///etc/passwd", "ftp://youtube.com/x", "javascript://youtube.com",
               "https://user:pw@youtube.com/x", "https://youtube.com:444/x", "https://youtube.com\\@evil.com",
               "https://evil.com@youtube.com.attacker.io/", "https://youtu.be/" + "a" * 300,
               "https://169.254.169.254/latest/meta-data", "https://[::1]/x"]
        for u in bad:
            with self.assertRaises(MediaError, msg=u):
                parse_target(u)

    def test_search_query(self):
        self.assertEqual(parse_target("اغنية جميلة"), "ytsearch1:اغنية جميلة")
        self.assertEqual(parse_target("  a \n b\x00c "), "ytsearch1:a b c")
        for bad in ["", "   ", "x" * 101]:
            with self.assertRaises(MediaError):
                parse_target(bad)

    def test_option_injection_neutralised(self):
        for evil in ["--exec id", "-o /etc/cron.d/x", "--config-location /tmp/x"]:
            args = build_args(parse_target(evil), "/tmp/o", "audio")
            self.assertEqual(args[-2], "--")
            self.assertTrue(args[-1].startswith("ytsearch1:"))
            self.assertEqual(args.count("--"), 1)

    def test_args_hardening(self):
        args = build_args("ytsearch1:x", "/tmp/o", "video")
        for flag in ("--ignore-config", "--no-playlist", "--max-filesize", "--match-filter", "--restrict-filenames"):
            self.assertIn(flag, args)
        self.assertNotIn("--exec", args)
        self.assertIn("duration<=600 & !is_live", args)


class TtsTests(unittest.TestCase):
    def test_lang_detection(self):
        self.assertEqual(parse_tts("مرحبا بكم"), ("ar", "مرحبا بكم"))
        self.assertEqual(parse_tts("hello there"), ("en", "hello there"))
        self.assertEqual(parse_tts("fr bonjour"), ("fr", "bonjour"))
        self.assertEqual(parse_tts("en"), ("en", "en"))  # رمز لغة وحده يُعامل كنص

    def test_limits(self):
        for bad in ["", "   ", "x" * 301]:
            with self.assertRaises(MediaError):
                parse_tts(bad)

    def test_unsupported_language_not_prefix(self):
        self.assertEqual(parse_tts("xx hello")[1], "xx hello")


class DownloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_success_clean_env_and_cleanup(self):
        os.environ["BOT_TOKEN"] = "123456789:SECRET_SHOULD_NOT_LEAK_abcdefghijklmnop"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "leak"
        try:
            item = await media.download("ytsearch1:ok", "audio", prefix=FAKE)
            self.assertEqual(item.title, "عنوان تجريبي")
            self.assertEqual(item.path.name, "abc.mp3")
            info = json.loads(Path(item.tmpdir, "env.json").read_text())
            self.assertNotIn("BOT_TOKEN", info["env"])
            self.assertNotIn("AWS_SECRET_ACCESS_KEY", info["env"])
            self.assertEqual(set(info["env"]) - {"PATH", "HOME", "LANG", "PYTHONIOENCODING", "LC_CTYPE"}, set())
            self.assertEqual(info["cwd"], os.path.realpath(item.tmpdir))
            self.assertEqual(oct(os.stat(item.tmpdir).st_mode & 0o777), "0o700")
            self.assertEqual(info["argv"][-2:], ["--", "ytsearch1:ok"])
            item.cleanup()
            self.assertFalse(os.path.exists(item.tmpdir))
        finally:
            os.environ.pop("BOT_TOKEN", None)
            os.environ.pop("AWS_SECRET_ACCESS_KEY", None)

    async def test_failure_cleans_tmp(self):
        before = set(os.listdir("/tmp"))
        with self.assertRaises(MediaError):
            await media.download("ytsearch1:fail", "audio", prefix=FAKE)
        with self.assertRaises(MediaError):
            await media.download("ytsearch1:nofile", "audio", prefix=FAKE)
        self.assertEqual({n for n in os.listdir("/tmp") if n.startswith("ytdl-")} - before, set())

    async def test_timeout_kills_process(self):
        start = time.monotonic()
        with self.assertRaises(MediaError) as cm:
            await media.download("ytsearch1:slow", "audio", prefix=FAKE, timeout=1)
        self.assertLess(time.monotonic() - start, 5)
        self.assertIn("وقتًا", str(cm.exception))

    async def test_oversize_rejected(self):
        old = media.MAX_FILE_BYTES
        media.MAX_FILE_BYTES = 100
        try:
            with self.assertRaises(MediaError):
                await media.download("ytsearch1:ok", "audio", prefix=FAKE)
        finally:
            media.MAX_FILE_BYTES = old

    async def test_cancel_cleans_tmp(self):
        before = set(os.listdir("/tmp"))
        task = asyncio.create_task(media.download("ytsearch1:slow", "audio", prefix=FAKE, timeout=20))
        await asyncio.sleep(0.7)
        new_dirs = [n for n in os.listdir("/tmp") if n.startswith("ytdl-") and n not in before]
        pid = int(Path("/tmp", new_dirs[0], "pid").read_text())
        os.kill(pid, 0)  # العملية تعمل الآن
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)  # قُتلت وجُمعت: لا عملية يتيمة
        self.assertEqual({n for n in os.listdir("/tmp") if n.startswith("ytdl-")} - before, set())

    async def test_tts_missing_lib_is_graceful(self):
        if media.tts_available():
            self.skipTest("gTTS installed")
        with self.assertRaises(MediaError):
            await media.synthesize("hello", "en")
        with self.assertRaises(MediaError):
            await media.synthesize("hello", "zz")


if __name__ == "__main__":
    unittest.main()
