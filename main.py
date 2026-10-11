import os, re, aiohttp, threading
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

TOKEN = os.getenv("BOT_TOKEN")
BASE = "https://am.rafaelxd.my.id/api/v1"
HEADERS = {
    "Content-Type": "application/json",
    "x-api-key": os.getenv("AM_API_KEY")
}

BANNER_URL = "https://raw.githubusercontent.com/vannn626-afk/leovan.prem/main/banner.jpg"

TXT_WELCOME = (
    "🎬 *GET AM PREMIUM*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Aktifkan Alight Motion Premium\n"
    "gratis, cepat, 3 langkah.\n\n"
    "✨ No Watermark\n"
    "✨ Unlimited Export\n"
    "✨ Premium Effects & Fonts\n\n"
    "Tekan tombol di bawah 👇"
)

TXT_STEP1 = (
    "📧 *STEP 1 — MASUKKAN EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Kirim email Alight Motion kamu.\n"
    "Contoh:\n`user@gmail.com`"
)

TXT_STEP2 = (
    "📬 *STEP 2 — CEK EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Magic link sudah dikirim ke:\n"
    "`{email}`\n\n"
    "Buka email → copy link → paste di sini 👇"
)

TXT_STEP3 = (
    "🚀 *STEP 3 — GASS TERAPIN PREMIUM*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\n"
    "Status: ✅ OK\n\n"
    "Tekan *GASS PREMIUM* 👇"
)

TXT_SUCCESS = (
    "🎉 *PREMIUM AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\n"
    "Paket: *1 Tahun AM Premium*\n"
    "Status: ✅ BERHASIL\n\n"
    "Selamat berkarya 🗿🤗"
)

TXT_FAIL = (
    "❌ *GAGAL*\n"
    "Email: `{email}`\n"
    "Alasan: `{reason}`\n\n"
    "Ulang /start"
)

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 GET AM PREMIUM", callback_data="am_start")]
    ])

def kb_step3():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 GASS TERAPIN PREMIUM", callback_data="am_apply")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(
        photo=BANNER_URL,
        caption=TXT_WELCOME,
        parse_mode="Markdown",
        reply_markup=kb_main()
    )

async def cb_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    context.user_data["step"] = "email"
    try:
        await q.message.reply_photo(
            photo=BANNER_URL,
            caption=TXT_STEP1,
            parse_mode="Markdown"
        )
        await q.message.delete()
    except Exception:
        await q.edit_message_text(TXT_STEP1, parse_mode="Markdown")

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    step = context.user_data.get("step")
    if step == "email":
        email = update.message.text.strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await update.message.reply_text("❌ Email tidak valid.")
            return
        context.user_data["email"] = email
        context.user_data["step"] = "wait_link"
        msg = await update.message.reply_text("⏳ Mengirim magic link...")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{BASE}/send-magiclink", json={"email": email}, headers=HEADERS) as r:
                    await r.json()
            await msg.delete()
            await update.message.reply_photo(
                photo=BANNER_URL,
                caption=TXT_STEP2.format(email=email),
                parse_mode="Markdown"
            )
        except Exception as e:
            await msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")
    elif step == "wait_link":
        link = update.message.text.strip()
        if "alightcreative.com" not in link:
            await update.message.reply_text("❌ Link tidak valid.")
            return
        email = context.user_data["email"]
        context.user_data["step"] = "ready"
        msg = await update.message.reply_text("⏳ Verifikasi...")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{BASE}/verify-account", json={"email": email, "rawLink": link}, headers=HEADERS) as r:
                    res = await r.json()
            token = res.get("idToken") or res.get("id_token")
            if not token:
                await msg.edit_text(f"❌ Gagal verify:\n`{res}`", parse_mode="Markdown")
                context.user_data.clear()
                return
            context.user_data["id_token"] = token
            await msg.delete()
            await update.message.reply_photo(
                photo=BANNER_URL,
                caption=TXT_STEP3.format(email=email),
                parse_mode="Markdown",
                reply_markup=kb_step3()
            )
        except Exception as e:
            await msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("Ketik /start buat mulai.")

async def cb_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    email = context.user_data.get("email")
    token = context.user_data.get("id_token")
    if not email or not token:
        await q.edit_message_text("❌ Sesi hilang. /start")
        return
    await q.edit_message_text("⏳ Menerapkan premium 1 tahun...")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{BASE}/apply-premium", json={"email": email, "idToken": token}, headers=HEADERS) as r:
                res = await r.json()
        if res.get("success") or res.get("status") == "ok":
            await q.message.reply_photo(
                photo=BANNER_URL,
                caption=TXT_SUCCESS.format(email=email),
                parse_mode="Markdown"
            )
        else:
            reason = res.get("message") or res.get("error") or str(res)
            await q.message.reply_photo(
                photo=BANNER_URL,
                caption=TXT_FAIL.format(email=email, reason=reason),
                parse_mode="Markdown"
            )
    except Exception as e:
        await q.edit_message_text(f"❌ Error: `{e}`", parse_mode="Markdown")
    context.user_data.clear()

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Bot aktif ✅"

def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(cb_start, pattern="^am_start$"))
    app.add_handler(CallbackQueryHandler(cb_apply, pattern="^am_apply$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    print("✅ Bot jalan!")
    app.run_polling()

if __name__ == "__main__":
    main()
