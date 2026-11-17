import os
import sys
import tempfile
import unittest
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bot import ranks
from bot.calc import CalcError, calculate
from bot.db import Database
from bot.locks import BY_NAME, Cooldown, FloodGuard, violated_locks
from bot.parsing import normalize, parse_command


class CalcTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(calculate("5*(3+2)"), "25")
        self.assertEqual(calculate("٣ + ٤"), "7")
        self.assertEqual(calculate("10/4"), "2.5")
        self.assertEqual(calculate("2^10"), "1024")

    def test_rejects_malicious(self):
        for bad in ["__import__('os').system('id')", "open('/etc/passwd')", "9**9**9", "(-8)**0.5",
                    "1/0", "1" * 200, "().__class__", "lambda:1", "2**1000", "a+1", ""]:
            with self.assertRaises(CalcError, msg=bad):
                calculate(bad)


class ParsingTests(unittest.TestCase):
    known = {normalize(x) for x in ["حظر", "الغاء الحظر", "رفع", "الغاء تثبيت", "الغاء تثبيت الكل", "id"]}

    def test_longest_match(self):
        self.assertEqual(parse_command("الغاء تثبيت الكل", self.known), ("الغاء تثبيت الكل", ""))
        self.assertEqual(parse_command("الغاء تثبيت", self.known), ("الغاء تثبيت", ""))

    def test_args_preserved(self):
        self.assertEqual(parse_command("رفع  مميز   @user", self.known), ("رفع", "مميز   @user"))

    def test_hamza_and_slash(self):
        self.assertEqual(parse_command("إلغاء الحظر".replace("إلغاء", "الغاء"), self.known)[0], "الغاء الحظر")
        self.assertEqual(parse_command("/id@MyBot 123", self.known), ("id", "123"))

    def test_not_command(self):
        self.assertIsNone(parse_command("مرحبا بالجميع", self.known))


class RankTests(unittest.TestCase):
    def test_grant_rules(self):
        self.assertTrue(ranks.can_grant(ranks.ADMIN, ranks.VIP))
        self.assertFalse(ranks.can_grant(ranks.ADMIN, ranks.ADMIN))
        self.assertFalse(ranks.can_grant(ranks.MANAGER, ranks.OWNER))
        self.assertTrue(ranks.can_grant(ranks.OWNER, ranks.OWNER))
        self.assertTrue(ranks.can_grant(ranks.DEV, ranks.OWNER))

    def test_act_on(self):
        self.assertFalse(ranks.can_act_on(ranks.ADMIN, ranks.ADMIN))
        self.assertFalse(ranks.can_act_on(ranks.ADMIN, ranks.OWNER))
        self.assertTrue(ranks.can_act_on(ranks.MANAGER, ranks.ADMIN))
        self.assertTrue(ranks.can_act_on(ranks.DEV, ranks.OWNER))

    def test_parse_rank(self):
        self.assertEqual(ranks.parse_rank("مميز"), ranks.VIP)
        self.assertEqual(ranks.parse_rank("أدمن".replace("أ", "ا")), ranks.ADMIN)
        self.assertIsNone(ranks.parse_rank("ملك"))


class LockTests(unittest.TestCase):
    def test_detect(self):
        url = NS(type="url")
        self.assertIn("links", violated_locks(NS(text="https://x.com", entities=[url])))
        self.assertIn("links", violated_locks(NS(text="زوروا t.me/abc", entities=[])))
        self.assertIn("usernames", violated_locks(NS(text="كلم @someone", entities=[])))
        self.assertEqual(violated_locks(NS(text="مرحبا", entities=[])), set())
        self.assertIn("photos", violated_locks(NS(photo=[1], caption="x", caption_entities=[])))
        self.assertIn("gifs", violated_locks(NS(animation=1, document=1)))
        self.assertNotIn("documents", violated_locks(NS(animation=1, document=1)))
        self.assertIn("documents", violated_locks(NS(document=1)))
        self.assertIn("forwards", violated_locks(NS(forward_origin=object(), text="x", entities=[])))

    def test_names(self):
        self.assertEqual(BY_NAME[normalize("الروابط")], "links")
        self.assertEqual(BY_NAME[normalize("الدردشة")], "chat")

    def test_flood(self):
        g = FloodGuard(limit=3, window=2)
        results = [g.hit(1, 1, now=t) for t in (0, 0.1, 0.2, 0.3, 0.4)]
        self.assertEqual(results, [False, False, False, True, True])
        self.assertFalse(g.hit(1, 1, now=10))
        self.assertFalse(g.hit(1, 2, now=0.4))

    def test_cooldown(self):
        c = Cooldown(1.0)
        self.assertTrue(c.allow("a", now=0))
        self.assertFalse(c.allow("a", now=0.5))
        self.assertTrue(c.allow("a", now=1.2))


class DbTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_sql_injection_is_inert(self):
        evil = "x'); DROP TABLE ranks;--"
        self.db.set_reply(1, evil, evil)
        self.assertEqual(self.db.get_reply(1, evil), evil)
        self.db.set_rank(1, 5, ranks.VIP)
        self.assertEqual(self.db.get_rank(1, 5), ranks.VIP)

    def test_ranks_and_users(self):
        self.db.set_rank(1, 5, ranks.ADMIN)
        self.db.set_rank(1, 5, ranks.NONE)
        self.assertEqual(self.db.get_rank(1, 5), 0)
        self.db.upsert_user(7, "Alice", "A")
        self.assertEqual(self.db.find_user_id("@alice"), 7)

    def test_locks_warns(self):
        self.db.lock(1, "links"); self.db.lock(1, "links")
        self.assertEqual(self.db.locked(1), {"links"})
        self.db.unlock(1, "links")
        self.assertEqual(self.db.locked(1), set())
        self.assertEqual([self.db.add_warn(1, 9) for _ in range(3)], [1, 2, 3])
        self.db.clear_warns(1, 9)
        self.assertEqual(self.db.get_warns(1, 9), 0)

    def test_bank(self):
        self.assertTrue(self.db.open_account(1)); self.assertFalse(self.db.open_account(1))
        self.db.open_account(2)
        self.assertEqual(self.db.transfer(1, 2, 400), "ok")
        self.assertEqual((self.db.balance(1), self.db.balance(2)), (600, 1400))
        self.assertEqual(self.db.transfer(1, 2, 10**6), "no_funds")
        self.assertEqual(self.db.transfer(1, 3, 5), "no_account")
        self.assertEqual(self.db.transfer(1, 1, 5), "bad_amount")
        self.assertEqual(self.db.transfer(1, 2, -5), "bad_amount")
        self.assertEqual((self.db.balance(1), self.db.balance(2)), (600, 1400))
        self.assertEqual(self.db.claim_bonus(1, 10_000, 3600, 100), ("ok", 700))
        self.assertEqual(self.db.claim_bonus(1, 10_100, 3600, 100)[0], "wait")


if __name__ == "__main__":
    unittest.main()
