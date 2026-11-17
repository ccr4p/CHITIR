#!/bin/sh
# تشغيل مع إعادة التشغيل التلقائي عند الأعطال. بدون sudo.
cd "$(dirname "$0")" || exit 1
[ -d .venv ] && . .venv/bin/activate
while true; do
  python3 main.py
  echo "توقف البوت، إعادة التشغيل بعد 5 ثوانٍ..." >&2
  sleep 5
done
