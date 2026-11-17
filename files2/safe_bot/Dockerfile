FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DB_PATH=/data/bot.db
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-media.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-media.txt
COPY main.py ./
COPY bot ./bot
# مستخدم عادي بلا صلاحيات، والبيانات في مجلد منفصل
RUN useradd --system --no-create-home bot && mkdir /data && chown bot /data
USER bot
VOLUME /data
CMD ["python", "main.py"]
