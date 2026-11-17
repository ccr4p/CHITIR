"""بديل وهمي لـ yt-dlp للاختبار: السلوك يُحدَّد بآخر وسيط (الهدف)."""
import json, os, pathlib, sys, time
a = sys.argv[1:]
target = a[-1]
out = pathlib.Path(a[a.index("-P") + 1])
if target.endswith("slow"):
    (out / "pid").write_text(str(os.getpid()))
    time.sleep(30)
if target.endswith("fail"):
    sys.stderr.write("boom")
    sys.exit(1)
if target.endswith("nofile"):
    sys.exit(0)
(out / "abc.mp3").write_bytes(b"x" * 5000)
(out / "env.json").write_text(json.dumps({"env": dict(os.environ), "argv": a, "cwd": os.getcwd()}))
print("عنوان تجريبي")
