"""قاعدة بيانات SQLite. كل الاستعلامات مُعامَلة (parameterized) فلا حقن SQL."""
from __future__ import annotations

import os
import sqlite3
import threading
import time

SCHEMA = (
    "CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY, username TEXT COLLATE NOCASE,"
    " first_name TEXT, last_seen INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
    "CREATE TABLE IF NOT EXISTS chats(chat_id INTEGER PRIMARY KEY, title TEXT, added INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS ranks(chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
    " rank INTEGER NOT NULL, PRIMARY KEY(chat_id, user_id))",
    "CREATE TABLE IF NOT EXISTS locks(chat_id INTEGER NOT NULL, name TEXT NOT NULL, PRIMARY KEY(chat_id, name))",
    "CREATE TABLE IF NOT EXISTS warns(chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL,"
    " count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(chat_id, user_id))",
    "CREATE TABLE IF NOT EXISTS replies(chat_id INTEGER NOT NULL, word TEXT NOT NULL, response TEXT NOT NULL,"
    " PRIMARY KEY(chat_id, word))",
    "CREATE TABLE IF NOT EXISTS settings(chat_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,"
    " PRIMARY KEY(chat_id, key))",
    "CREATE TABLE IF NOT EXISTS bank(user_id INTEGER PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0"
    " CHECK(balance >= 0), last_bonus INTEGER NOT NULL DEFAULT 0)",
)


class Database:
    def __init__(self, path: str):
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            for stmt in SCHEMA:
                self._conn.execute(stmt)
        if path != ":memory:":
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass

    # ---- أدوات داخلية ----
    def _exec(self, sql: str, params: tuple = ()) -> int:
        with self._lock:
            return self._conn.execute(sql, params).rowcount

    def _one(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _all(self, sql: str, params: tuple = ()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- المستخدمون والمجموعات ----
    def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        self._exec(
            "INSERT INTO users(user_id, username, first_name, last_seen) VALUES(?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, "
            "first_name=excluded.first_name, last_seen=excluded.last_seen",
            (user_id, username, first_name, int(time.time())),
        )

    def find_user_id(self, username: str) -> int | None:
        row = self._one(
            "SELECT user_id FROM users WHERE username=? ORDER BY last_seen DESC LIMIT 1",
            (username.lstrip("@"),),
        )
        return row["user_id"] if row else None

    def user_name(self, user_id: int) -> str | None:
        row = self._one("SELECT first_name FROM users WHERE user_id=?", (user_id,))
        return row["first_name"] if row else None

    def add_chat(self, chat_id: int, title: str) -> None:
        self._exec("INSERT OR IGNORE INTO chats(chat_id, title, added) VALUES(?,?,?)",
                   (chat_id, title, int(time.time())))

    def stats(self) -> tuple[int, int]:
        c = self._one("SELECT COUNT(*) AS n FROM chats")["n"]
        u = self._one("SELECT COUNT(*) AS n FROM users")["n"]
        return c, u

    # ---- الرتب ----
    def set_rank(self, chat_id: int, user_id: int, rank: int) -> None:
        if rank <= 0:
            self._exec("DELETE FROM ranks WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        else:
            self._exec(
                "INSERT INTO ranks(chat_id, user_id, rank) VALUES(?,?,?) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET rank=excluded.rank",
                (chat_id, user_id, rank),
            )

    def get_rank(self, chat_id: int, user_id: int) -> int:
        row = self._one("SELECT rank FROM ranks WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return row["rank"] if row else 0

    def list_rank(self, chat_id: int, rank: int, limit: int = 50) -> list[int]:
        rows = self._all("SELECT user_id FROM ranks WHERE chat_id=? AND rank=? LIMIT ?", (chat_id, rank, limit))
        return [r["user_id"] for r in rows]

    # ---- الأقفال ----
    def lock(self, chat_id: int, name: str) -> None:
        self._exec("INSERT OR IGNORE INTO locks(chat_id, name) VALUES(?,?)", (chat_id, name))

    def unlock(self, chat_id: int, name: str) -> None:
        self._exec("DELETE FROM locks WHERE chat_id=? AND name=?", (chat_id, name))

    def locked(self, chat_id: int) -> set[str]:
        return {r["name"] for r in self._all("SELECT name FROM locks WHERE chat_id=?", (chat_id,))}

    # ---- الإنذارات ----
    def add_warn(self, chat_id: int, user_id: int) -> int:
        with self._lock:
            self._exec(
                "INSERT INTO warns(chat_id, user_id, count) VALUES(?,?,1) "
                "ON CONFLICT(chat_id, user_id) DO UPDATE SET count=count+1",
                (chat_id, user_id),
            )
            return self.get_warns(chat_id, user_id)

    def get_warns(self, chat_id: int, user_id: int) -> int:
        row = self._one("SELECT count FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        return row["count"] if row else 0

    def clear_warns(self, chat_id: int, user_id: int) -> None:
        self._exec("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))

    # ---- الردود ----
    def set_reply(self, chat_id: int, word: str, response: str) -> None:
        self._exec(
            "INSERT INTO replies(chat_id, word, response) VALUES(?,?,?) "
            "ON CONFLICT(chat_id, word) DO UPDATE SET response=excluded.response",
            (chat_id, word, response),
        )

    def del_reply(self, chat_id: int, word: str) -> bool:
        return self._exec("DELETE FROM replies WHERE chat_id=? AND word=?", (chat_id, word)) > 0

    def get_reply(self, chat_id: int, word: str) -> str | None:
        row = self._one("SELECT response FROM replies WHERE chat_id=? AND word=?", (chat_id, word))
        return row["response"] if row else None

    def list_replies(self, chat_id: int, limit: int = 100) -> list[str]:
        return [r["word"] for r in self._all("SELECT word FROM replies WHERE chat_id=? ORDER BY word LIMIT ?",
                                             (chat_id, limit))]

    def count_replies(self, chat_id: int) -> int:
        return self._one("SELECT COUNT(*) AS n FROM replies WHERE chat_id=?", (chat_id,))["n"]

    def clear_replies(self, chat_id: int) -> None:
        self._exec("DELETE FROM replies WHERE chat_id=?", (chat_id,))

    # ---- الإعدادات ----
    def get_setting(self, chat_id: int, key: str, default: str | None = None) -> str | None:
        row = self._one("SELECT value FROM settings WHERE chat_id=? AND key=?", (chat_id, key))
        return row["value"] if row else default

    def set_setting(self, chat_id: int, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO settings(chat_id, key, value) VALUES(?,?,?) "
            "ON CONFLICT(chat_id, key) DO UPDATE SET value=excluded.value",
            (chat_id, key, value),
        )

    # ---- البنك ----
    def open_account(self, user_id: int, initial: int = 1000) -> bool:
        return self._exec("INSERT OR IGNORE INTO bank(user_id, balance) VALUES(?,?)", (user_id, initial)) > 0

    def balance(self, user_id: int) -> int | None:
        row = self._one("SELECT balance FROM bank WHERE user_id=?", (user_id,))
        return row["balance"] if row else None

    def claim_bonus(self, user_id: int, now: int, cooldown: int, amount: int) -> tuple[str, int]:
        with self._lock:
            row = self._one("SELECT last_bonus FROM bank WHERE user_id=?", (user_id,))
            if row is None:
                return "no_account", 0
            wait = row["last_bonus"] + cooldown - now
            if wait > 0:
                return "wait", wait
            self._exec("UPDATE bank SET balance=balance+?, last_bonus=? WHERE user_id=?", (amount, now, user_id))
            return "ok", self.balance(user_id) or 0

    def transfer(self, sender: int, receiver: int, amount: int) -> str:
        """تحويل ذرّي داخل معاملة واحدة. يرجع: ok / no_account / no_funds / bad_amount."""
        if amount <= 0 or sender == receiver:
            return "bad_amount"
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                s = self._conn.execute("SELECT balance FROM bank WHERE user_id=?", (sender,)).fetchone()
                r = self._conn.execute("SELECT 1 FROM bank WHERE user_id=?", (receiver,)).fetchone()
                if s is None or r is None:
                    result = "no_account"
                elif s["balance"] < amount:
                    result = "no_funds"
                else:
                    self._conn.execute("UPDATE bank SET balance=balance-? WHERE user_id=?", (amount, sender))
                    self._conn.execute("UPDATE bank SET balance=balance+? WHERE user_id=?", (amount, receiver))
                    result = "ok"
            except Exception:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT" if result == "ok" else "ROLLBACK")
            return result
