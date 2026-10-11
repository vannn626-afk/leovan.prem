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

def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 GET AM PREMIUM", callback_data="am_start")]
    ])

def kb_step3():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 GASS TERAPIN PREMIUM", callback_data="am_apply")]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_WELCOME, parse_mode="Markdown", reply_markup=kb_main())

async def cb_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    context.user_data["step"] = "email"
    await q.edit_message_text(
        "📧 *STEP 1*\nKirim email Alight Motion kamu:\nContoh: `user@gmail.com`",
        parse_mode="Markdown"
    )

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
            await msg.edit_text(
                f"📬 *STEP 2*\nMagic link dikirim ke:\n`{email}`\n\nBuka email → copy link → paste di sini 👇",
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
            await msg.edit_text(
                f"🚀 *STEP 3*\nEmail: `{email}`\nStatus: ✅ OK\n\nTekan tombol 👇",
                parse_mode="Markdown", reply_markup=kb_step3()
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
            await q.edit_message_text(
                f"🎉 *PREMIUM AKTIF!*\nEmail: `{email}`\nPaket: 1 Tahun\nStatus: ✅ BERHASIL\n\nSelamat 🗿🤗",
                parse_mode="Markdown"
            )
        else:
            reason = res.get("message") or res.get("error") or str(res)
            await q.edit_message_text(f"❌ Gagal: `{reason}`\n\nUlang /start", parse_mode="Markdown")
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
    print("Bot jalan...")
    app.run_polling()

if __name__ == "__main__":
    main()
