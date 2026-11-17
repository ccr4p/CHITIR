"""أوامر عامة: المساعدة، الآيدي، الرتبة، الحاسبة، البنك، الإحصائيات."""
from __future__ import annotations

import random
import re
import time

from .. import ranks
from ..calc import CalcError, calculate
from ..parsing import to_ascii_digits
from ..registry import command
from .common import Ctx, esc, mention, resolve_target

HELP = """<b>📖 الأوامر</b>

<b>للجميع:</b> ايدي، رتبتي، القوانين، الانذارات، حاسبه 5*3، انشاء حساب بنكي، فلوسي، بخشيش، تحويل (بالرد + المبلغ)
<b>الوسائط:</b> يوتيوب <رابط|اسم> (صوت)، تحميل فيديو <رابط|اسم>، انطق <نص> (أو: انطق en hello)

<b>الادمن:</b> حظر، الغاء الحظر، طرد، كتم، الغاء الكتم، انذار، مسح الانذارات، تثبيت، الغاء التثبيت، مسح، رفع مميز، تنزيل، المميزين، الحمايه، الردود

<b>المدير:</b> قفل/فتح (الروابط، المعرفات، الصور، الفيديو، الملصقات، المتحركه، التوجيه، الملفات، الصوتيات، الجهات، التكرار، الدردشه، البوتات)، ضع ترحيب، تفعيل/تعطيل الترحيب، ضع القوانين، اضف رد كلمة = رد، حذف رد، ضع الانذارات، تفعيل/تعطيل التحميل، رفع ادمن|مدير

<b>المنشئ/المالك:</b> رفع مدير|منشئ|مالك بحسب رتبتك"""

START = "أهلاً 👋 أنا بوت إدارة مجموعات. أضفني لمجموعتك كمشرف، ثم اكتب <b>الاوامر</b> لعرض ما أستطيعه."


@command("start", "ابدأ")
async def start(ctx: Ctx) -> None:
    await ctx.reply(START)


@command("الاوامر", "help", "اوامر", "مساعدة")
async def help_(ctx: Ctx) -> None:
    await ctx.reply(HELP)


@command("ايدي", "id")
async def whoami(ctx: Ctx) -> None:
    t = resolve_target(ctx)
    uid, name = t if t else (ctx.user.id, ctx.user.full_name)
    lines = [f"👤 {mention(uid, name)}", f"🆔 <code>{uid}</code>"]
    if ctx.is_group:
        lines.append(f"💬 آيدي المجموعة: <code>{ctx.chat.id}</code>")
    await ctx.reply("\n".join(lines))


@command("رتبتي")
async def my_rank(ctx: Ctx) -> None:
    await ctx.reply(f"رتبتك: <b>{ranks.label(ctx.rank)}</b>")


@command("حاسبه", "احسب", "calc")
async def calc(ctx: Ctx) -> None:
    try:
        result = calculate(ctx.arg)
    except CalcError as e:
        await ctx.reply(esc(e))
        return
    await ctx.reply(f"<code>{esc(ctx.arg)} = {esc(result)}</code>")


# ---------------- البنك ----------------
BONUS_COOLDOWN = 3600
MAX_TRANSFER = 1_000_000_000


@command("انشاء حساب بنكي", "فتح حساب بنكي")
async def open_account(ctx: Ctx) -> None:
    if ctx.db.open_account(ctx.user.id):
        await ctx.reply("🏦 تم إنشاء حسابك البنكي برصيد 1000 💰")
    else:
        await ctx.reply("لديك حساب بنكي بالفعل.")


@command("فلوسي", "رصيدي")
async def balance(ctx: Ctx) -> None:
    bal = ctx.db.balance(ctx.user.id)
    await ctx.reply("ليس لديك حساب. اكتب: انشاء حساب بنكي" if bal is None else f"💰 رصيدك: <b>{bal}</b>")


@command("بخشيش", "بقشيش")
async def bonus(ctx: Ctx) -> None:
    status, value = ctx.db.claim_bonus(ctx.user.id, int(time.time()), BONUS_COOLDOWN, random.randint(50, 500))
    if status == "no_account":
        await ctx.reply("ليس لديك حساب. اكتب: انشاء حساب بنكي")
    elif status == "wait":
        await ctx.reply(f"⏳ حاول بعد {value // 60 + 1} دقيقة.")
    else:
        await ctx.reply(f"🎁 حصلت على بخشيش! رصيدك الآن: <b>{value}</b>")


@command("تحويل", group_only=True)
async def transfer(ctx: Ctx) -> None:
    replied = ctx.msg.reply_to_message
    amount_txt = to_ascii_digits(ctx.arg.strip())
    if not replied or not replied.from_user or not re.fullmatch(r"[0-9]{1,10}", amount_txt):
        await ctx.reply("بالرد على الشخص اكتب: تحويل <المبلغ>")
        return
    amount, target = int(amount_txt), replied.from_user
    if target.is_bot or not 1 <= amount <= MAX_TRANSFER:
        await ctx.reply("مبلغ أو مستلم غير صالح.")
        return
    result = ctx.db.transfer(ctx.user.id, target.id, amount)
    messages = {
        "ok": f"✅ حوّلت <b>{amount}</b> إلى {mention(target.id, target.full_name)}",
        "no_funds": "رصيدك لا يكفي.",
        "no_account": "يلزم أن يكون لكليكما حساب بنكي.",
        "bad_amount": "لا يمكن التحويل لنفسك.",
    }
    await ctx.reply(messages[result])


@command("الاحصائيات", rank=ranks.DEV)
async def stats(ctx: Ctx) -> None:
    chats, users = ctx.db.stats()
    await ctx.reply(f"📊 المجموعات: <b>{chats}</b>\nالمستخدمون: <b>{users}</b>")
