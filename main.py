import os, re, json, aiohttp, threading, asyncio
from datetime import datetime, date, timedelta
from flask import Flask
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

TOKEN = os.getenv("BOT_TOKEN")
BASE = "https://am.neonode.my.id/api"
HEADERS = {"Content-Type": "application/json"}

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
BANNER_URL = "https://raw.githubusercontent.com/vannn626-afk/leovan.prem/main/banner.jpg"
QRIS_URL = "https://raw.githubusercontent.com/vannn626-afk/leovan.prem/main/qris.jpg"
NOMOR_DANA = os.getenv("NOMOR_DANA", "08xxxxxxxxxx")
LOG_FILE = "log.json"
LIMIT_PER_DAY = 3
HARGA_PREMIUM = "Rp 10.000"


# ============== STORAGE ==============
def load_log():
    if not os.path.exists(LOG_FILE):
        return {"users": {}, "daily": {}, "logs": [], "premium": {}, "pending": {}}
    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
            if "premium" not in data: data["premium"] = {}
            if "pending" not in data: data["pending"] = {}
            return data
    except:
        return {"users": {}, "daily": {}, "logs": [], "premium": {}, "pending": {}}


def save_log(data):
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=2)


def add_log(user_id, username, event):
    data = load_log()
    data["logs"].append({
        "time": datetime.now().isoformat(),
        "user_id": user_id,
        "username": username,
        "event": event
    })
    data["logs"] = data["logs"][-500:]
    save_log(data)


def register_user(user_id, username):
    data = load_log()
    uid = str(user_id)
    if uid not in data["users"]:
        data["users"][uid] = {
            "username": username,
            "first_seen": datetime.now().isoformat()
        }
        save_log(data)
        return True
    return False


# ============== PREMIUM ==============
def is_premium_user(user_id):
    data = load_log()
    uid = str(user_id)
    prem = data["premium"].get(uid)
    if not prem: return False
    if datetime.fromisoformat(prem["expired"]) < datetime.now():
        return False
    return True


def set_premium_user(user_id, days=30):
    data = load_log()
    uid = str(user_id)
    data["premium"][uid] = {
        "expired": (datetime.now() + timedelta(days=days)).isoformat(),
        "since": datetime.now().isoformat()
    }
    save_log(data)


def remove_premium_user(user_id):
    data = load_log()
    data["premium"].pop(str(user_id), None)
    save_log(data)


def get_premium_info(user_id):
    data = load_log()
    uid = str(user_id)
    prem = data["premium"].get(uid)
    if not prem: return None
    expired = datetime.fromisoformat(prem["expired"])
    return {
        "expired": expired.strftime("%d %B %Y"),
        "sisa_hari": max(0, (expired - datetime.now()).days)
    }


# ============== LIMIT ==============
def get_limit(user_id):
    if is_premium_user(user_id): return 999
    data = load_log()
    uid = str(user_id)
    today = str(date.today())
    daily = data["daily"].get(uid, {})
    if daily.get("date") != today: return LIMIT_PER_DAY
    used = daily.get("used", 0)
    return max(0, LIMIT_PER_DAY - used)


def use_limit(user_id):
    if is_premium_user(user_id): return
    data = load_log()
    uid = str(user_id)
    today = str(date.today())
    daily = data["daily"].get(uid, {})
    if daily.get("date") != today:
        daily = {"date": today, "used": 0}
    daily["used"] = daily.get("used", 0) + 1
    data["daily"][uid] = daily
    save_log(data)


def reset_limit(user_id):
    data = load_log()
    data["daily"].pop(str(user_id), None)
    save_log(data)


def get_reset_countdown():
    now = datetime.now()
    besok = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    delta = besok - now
    jam = delta.seconds // 3600
    menit = (delta.seconds % 3600) // 60
    return f"{jam} jam {menit} menit"


def is_admin(user_id): return user_id == ADMIN_ID


# ============== TEKS ==============
TXT_WELCOME = (
    "🎬 *GET AM PREMIUM*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Aktifkan Alight Motion Premium\n"
    "gratis, cepat, 2 langkah.\n\n"
    "✨ No Watermark\n✨ Unlimited Export\n✨ Premium Effects & Fonts\n\n"
    "Tekan tombol di bawah 👇"
)

TXT_STEP1 = (
    "📧 *STEP 1 — MASUKKAN EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Kirim email Alight Motion kamu.\nContoh:\n`user@gmail.com`\n\n"
    "📊 Status limit:\n{status_limit}"
)

TXT_STEP2 = (
    "📬 *STEP 2 — CEK EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Magic link dikirim ke:\n`{email}`\n\n"
    "Buka email → copy link → paste di sini 👇"
)

TXT_PROSES = "⏳ Verifikasi & aktivasi premium..."

TXT_SUCCESS = (
    "🎉 *PREMIUM AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\nPaket: *1 Tahun AM Premium*\nStatus: ✅ BERHASIL\n\n"
    "{status_limit}\n\nSelamat berkarya 🗿🤗"
)

TXT_SUCCESS_PREMIUM_USER = (
    "🎉 *PREMIUM AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\nPaket: *1 Tahun AM Premium*\nStatus: ✅ BERHASIL\n\n"
    "👑 Kamu user *PREMIUM*\nUnlimited tanpa limit!\n\nSelamat berkarya 🗿🤗"
)

TXT_FAIL = (
    "❌ *GAGAL*\nEmail: `{email}`\nAlasan: `{reason}`\n\n"
    "Limit gak kepotong, ulang /start"
)

TXT_LIMIT_HABIS = (
    "⚠️ *LIMIT HABIS*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Kamu sudah pakai *{max}x* hari ini.\n\n"
    "⏰ Reset dalam: *{countdown}*\n\n"
    "Mau unlimited? Klik tombol 👇"
)

TXT_HELP = (
    "📖 *PANDUAN BOT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "*Cara pakai:*\n1. Ketik /start\n2. Klik GET AM PREMIUM\n"
    "3. Kirim email Alight Motion\n4. Buka email, copy magic link\n"
    "5. Paste ke bot, tunggu proses\n\n"
    "*Command:*\n/start — mulai\n/help — panduan\n/status — status bot\n"
    "/limit — cek sisa limit\n/buy — beli akses no limit\n/mypremium — cek premium\n\n"
    "*Limit user biasa:* max {max}x per hari\n*Premium:* unlimited, {harga}"
)

TXT_STATUS = (
    "📊 *STATUS BOT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Status: ✅ Online\nTotal user: *{users}*\n"
    "User premium: *{premium}*\nLimit harian: *{max}x*"
)

TXT_BUY = (
    "💎 *BELI AKSES NO LIMIT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Bebas limit! Aktivasi sepuasnya.\n\n"
    "💰 *Harga:* {harga}/bulan\n\n"
    "📱 *Cara bayar:*\n"
    "1️⃣ Scan QRIS di gambar\n"
    "2️⃣ Atau transfer DANA ke:\n`{dana}`\n\n"
    "3️⃣ Screenshot bukti transfer\n"
    "4️⃣ Kirim screenshot ke bot ini\n\n"
    "⚡ Admin akan verifikasi & aktifkan premium kamu"
)

TXT_KIRIM_BUKTI = (
    "📸 *KIRIM BUKTI TRANSFER*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Upload screenshot bukti transfer kamu.\n\n"
    "Admin akan verifikasi dan aktifkan premium dalam 1x24 jam."
)

TXT_BUKTI_DITERIMA = (
    "✅ *BUKTI DITERIMA*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Screenshot kamu udah dikirim ke admin.\n"
    "Tunggu verifikasi, nanti kamu dapet notif ya 🗿"
)

TXT_PREMIUM_AKTIF_NOTIF = (
    "🎉 *PREMIUM KAMU AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Status: 👑 ACTIVE\nPaket: Unlimited 30 hari\n\n"
    "Sekarang kamu bisa pakai bot tanpa limit!\n"
    "Makasih udah support 🗿🤗"
)

TXT_PREMIUM_DITOLAK = (
    "❌ *PEMBAYARAN DITOLAK*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Bukti transfer kamu ditolak admin.\n"
    "Alasan: `{reason}`\n\n"
    "Coba hubungi admin @{admin}"
)

TXT_MYPREMIUM = (
    "👑 *STATUS PREMIUM KAMU*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Status: {status}\nExpired: *{expired}*\nSisa: *{sisa} hari*\n\n{footer}"
)


# ============== KEYBOARD ==============
def kb_reply_bottom():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎬 GET PREMIUM"), KeyboardButton("📖 Bantuan")],
            [KeyboardButton("💎 BELI AKSES NO LIMIT"), KeyboardButton("📈 Cek Limit")],
            [KeyboardButton("👑 My Premium"), KeyboardButton("📊 Status")]
        ],
        resize_keyboard=True, is_persistent=True
    )


def kb_reply_admin():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Stats"), KeyboardButton("📝 Log")],
            [KeyboardButton("👥 User List"), KeyboardButton("💰 Pending")],
            [KeyboardButton("🎬 GET PREMIUM"), KeyboardButton("💎 BELI AKSES")],
            [KeyboardButton("👑 My Premium"), KeyboardButton("📖 Bantuan")]
        ],
        resize_keyboard=True, is_persistent=True
    )


def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 GET AM PREMIUM", callback_data="am_start")],
        [InlineKeyboardButton("💎 BELI AKSES NO LIMIT — Rp 10.000", callback_data="am_buy")]
    ])


def kb_limit_habis():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 BELI AKSES NO LIMIT", callback_data="am_buy")]
    ])


def kb_buy():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data="am_kirim_bukti")]
    ])


def kb_admin_aksi(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aktifkan", callback_data=f"adm_ok_{user_id}"),
            InlineKeyboardButton("❌ Tolak", callback_data=f"adm_no_{user_id}")
        ]
    ])


# ============== HELPER ==============
def status_limit_text(uid):
    if is_premium_user(uid):
        info = get_premium_info(uid)
        return f"👑 *User PREMIUM*\nUnlimited! Expired: {info['expired']}"
    return f"Sisa limit: *{get_limit(uid)}/{LIMIT_PER_DAY}*\n⏰ Reset dalam: *{get_reset_countdown()}*"


# ============== COMMAND HANDLER ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name
    is_new = register_user(uid, uname)
    if is_new and ADMIN_ID:
        try:
            await context.bot.send_message(ADMIN_ID,
                f"👤 *User baru!*\nID: `{uid}`\nUsername: @{uname}", parse_mode="Markdown")
        except: pass
    add_log(uid, uname, "start")
    await update.message.reply_photo(photo=BANNER_URL, caption=TXT_WELCOME,
        parse_mode="Markdown", reply_markup=kb_main())
    if is_admin(uid):
        await update.message.reply_text("👑 Menu admin:", reply_markup=kb_reply_admin())
    else:
        await update.message.reply_text("👇 Menu cepat:", reply_markup=kb_reply_bottom())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(TXT_HELP.format(max=LIMIT_PER_DAY, harga=HARGA_PREMIUM), parse_mode="Markdown")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_log()
    await update.message.reply_text(TXT_STATUS.format(
        users=len(data["users"]), premium=len(data.get("premium", {})), max=LIMIT_PER_DAY), parse_mode="Markdown")


async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = "📊 *LIMIT KAMU*\n━━━━━━━━━━━━━━━━━━\n" + status_limit_text(uid)
    if is_premium_user(uid):
        await update.message.reply_text(txt, parse_mode="Markdown")
    else:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb_limit_habis())


async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(photo=QRIS_URL,
        caption=TXT_BUY.format(harga=HARGA_PREMIUM, dana=NOMOR_DANA),
        parse_mode="Markdown", reply_markup=kb_buy())


async def mypremium_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    info = get_premium_info(uid)
    if not info:
        await update.message.reply_text("❌ Kamu belum premium.\nKetik /buy buat beli akses unlimited.", reply_markup=kb_limit_habis())
        return
    await update.message.reply_text(TXT_MYPREMIUM.format(
        status="👑 ACTIVE", expired=info["expired"], sisa=info["sisa_hari"],
        footer="Unlimited akses aktif!"), parse_mode="Markdown")


async def addprem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Khusus admin."); return
    if not context.args:
        await update.message.reply_text("Format: /addprem <user_id> [hari]"); return
    target = int(context.args[0])
    days = int(context.args[1]) if len(context.args) > 1 else 30
    set_premium_user(target, days)
    await update.message.reply_text(f"✅ User `{target}` jadi PREMIUM {days} hari.", parse_mode="Markdown")
    try:
        await context.bot.send_message(target, TXT_PREMIUM_AKTIF_NOTIF, parse_mode="Markdown")
    except: pass


async def delprem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Khusus admin."); return
    if not context.args:
        await update.message.reply_text("Format: /delprem <user_id>"); return
    remove_premium_user(int(context.args[0]))
    await update.message.reply_text(f"✅ Premium `{context.args[0]}` dihapus.", parse_mode="Markdown")


# ============== CALLBACK ==============
async def cb_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    if get_limit(uid) <= 0:
        await q.message.reply_text(
            TXT_LIMIT_HABIS.format(max=LIMIT_PER_DAY, countdown=get_reset_countdown()),
            parse_mode="Markdown", reply_markup=kb_limit_habis())
        return
    context.user_data.clear()
    context.user_data["step"] = "email"
    await q.message.reply_photo(photo=BANNER_URL,
        caption=TXT_STEP1.format(status_limit=status_limit_text(uid)), parse_mode="Markdown")


async def cb_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_photo(photo=QRIS_URL,
        caption=TXT_BUY.format(harga=HARGA_PREMIUM, dana=NOMOR_DANA),
        parse_mode="Markdown", reply_markup=kb_buy())


async def cb_kirim_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["kirim_bukti"] = True
    await q.message.reply_text(TXT_KIRIM_BUKTI, parse_mode="Markdown")


async def cb_admin_aksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id): return
    parts = q.data.split("_")
    aksi = parts[1]
    target = int(parts[2])

    if aksi == "ok":
        set_premium_user(target, 30)
        add_log(target, "user", "premium_manual_aktif")
        data = load_log()
        data.get("pending", {}).pop(str(target), None)
        save_log(data)
        try:
            await q.edit_message_caption(
                caption=q.message.caption + "\n\n✅ *SUDAH DIAKTIFKAN*",
                parse_mode="Markdown")
        except:
            await q.edit_message_text("✅ Sudah diaktifkan.")
        try:
            await context.bot.send_message(target, TXT_PREMIUM_AKTIF_NOTIF, parse_mode="Markdown")
        except: pass

    elif aksi == "no":
        context.user_data["reject_target"] = target
        try:
            await q.edit_message_caption(
                caption=q.message.caption + "\n\n❌ *DITOLAK*\n\nKetik alasan penolakan:*",
                parse_mode="Markdown")
        except:
            await q.edit_message_text("❌ Ditolak. Ketik alasan:")


# ============== ROUTER ==============
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name

    if update.message.photo:
        if context.user_data.get("kirim_bukti"):
            photo = update.message.photo[-1]
            caption_admin = (
                f"💰 *PEMBELIAN PREMIUM BARU*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Nama: {update.effective_user.first_name}\n"
                f"📛 Username: @{uname}\n"
                f"🆔 User ID: `{uid}`\n"
                f"💵 Nominal: {HARGA_PREMIUM}\n\n"
                f"Cek bukti transfer di bawah 👇"
            )
            try:
                await context.bot.send_photo(
                    ADMIN_ID,
                    photo=photo.file_id,
                    caption=caption_admin,
                    parse_mode="Markdown",
                    reply_markup=kb_admin_aksi(uid))
                data = load_log()
                data["pending"][str(uid)] = {
                    "time": datetime.now().isoformat(),
                    "username": uname,
                    "name": update.effective_user.first_name
                }
                save_log(data)
                await update.message.reply_text(TXT_BUKTI_DITERIMA, parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ Gagal kirim ke admin: {e}")
            context.user_data.pop("kirim_bukti", None)
            return

    text = update.message.text.strip() if update.message.text else ""

    if is_admin(uid) and context.user_data.get("reject_target") and text:
        target = context.user_data.pop("reject_target")
        try:
            await context.bot.send_message(
                target,
                TXT_PREMIUM_DITOLAK.format(reason=text, admin=ADMIN_USERNAME),
                parse_mode="Markdown")
        except: pass
        await update.message.reply_text(f"✅ Alasan penolakan dikirim ke `{target}`.", parse_mode="Markdown")
        return

    if text == "📊 Stats" and is_admin(uid):
        data = load_log()
        logs = data["logs"]
        sukses = sum(1 for l in logs if l["event"] == "premium_sukses")
        gagal = sum(1 for l in logs if l["event"] == "premium_gagal")
        today = str(date.today())
        today_users = sum(1 for u in data["users"].values() if u["first_seen"].startswith(today))
        await update.message.reply_text(
            f"📊 *STATISTIK BOT*\n━━━━━━━━━━━━━━━━━━\n"
            f"👥 Total user: *{len(data['users'])}*\n"
            f"📅 User hari ini: *{today_users}*\n"
            f"👑 User premium: *{len(data.get('premium', {}))}*\n"
            f"✅ Sukses: *{sukses}*\n"
            f"❌ Gagal: *{gagal}*\n"
            f"⏳ Pending: *{len(data.get('pending', {}))}*",
            parse_mode="Markdown"
        )
        return

    if text == "📝 Log" and is_admin(uid):
        data = load_log()
        logs = data["logs"][-20:]
        if not logs:
            await update.message.reply_text("Belum ada log.")
            return
        txt = "📝 *20 LOG TERAKHIR*\n━━━━━━━━━━━━━━━━━━\n"
        for l in logs:
            txt += f"`{l['time'][11:19]}` @{l['username']} — {l['event']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    if text == "👥 User List" and is_admin(uid):
        data = load_log()
        users = list(data["users"].items())[-30:]
        if not users:
            await update.message.reply_text("Belum ada user.")
            return
        txt = "👥 *30 USER TERAKHIR*\n━━━━━━━━━━━━━━━━━━\n"
        for user_id, info in users:
            prem = "👑" if is_premium_user(int(user_id)) else "👤"
            txt += f"{prem} `{user_id}` @{info['username']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    if text == "💰 Pending" and is_admin(uid):
        data = load_log()
        pending = data.get("pending", {})
        if not pending:
            await update.message.reply_text("✅ Gak ada pending pembayaran.")
            return
        txt = "💰 *PENDING PEMBAYARAN*\n━━━━━━━━━━━━━━━━━━\n"
        for user_id, info in pending.items():
            txt += f"🆔 `{user_id}` — @{info['username']}\n"
        txt += "\n_Ketik /addprem <id> buat aktifin_"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    if text == "🎬 GET PREMIUM":
        context.user_data.clear()
        context.user_data["step"] = "email"
        if get_limit(uid) <= 0:
            await update.message.reply_text(
                TXT_LIMIT_HABIS.format(max=LIMIT_PER_DAY, countdown=get_reset_countdown()),
                parse_mode="Markdown", reply_markup=kb_limit_habis())
            return
        await update.message.reply_photo(photo=BANNER_URL,
            caption=TXT_STEP1.format(status_limit=status_limit_text(uid)), parse_mode="Markdown")
        return

    if text == "📖 Bantuan":
        await update.message.reply_text(TXT_HELP.format(max=LIMIT_PER_DAY, harga=HARGA_PREMIUM), parse_mode="Markdown")
        return

    if text in ["💎 BELI AKSES NO LIMIT", "💎 BELI AKSES"]:
        await update.message.reply_photo(photo=QRIS_URL,
            caption=TXT_BUY.format(harga=HARGA_PREMIUM, dana=NOMOR_DANA),
            parse_mode="Markdown", reply_markup=kb_buy())
        return

    if text == "👑 My Premium":
        info = get_premium_info(uid)
        if not info:
            await update.message.reply_text("❌ Belum premium.\nKetik /buy.", reply_markup=kb_limit_habis())
            return
        await update.message.reply_text(TXT_MYPREMIUM.format(
            status="👑 ACTIVE", expired=info["expired"], sisa=info["sisa_hari"],
            footer="Unlimited akses aktif!"), parse_mode="Markdown")
        return

    if text == "📊 Status":
        data = load_log()
        await update.message.reply_text(TXT_STATUS.format(
            users=len(data["users"]), premium=len(data.get("premium", {})), max=LIMIT_PER_DAY), parse_mode="Markdown")
        return

    if text == "📈 Cek Limit":
        await update.message.reply_text(
            "📊 *LIMIT KAMU*\n━━━━━━━━━━━━━━━━━━\n" + status_limit_text(uid), parse_mode="Markdown")
        return

    step = context.user_data.get("step")

    if step == "email":
        email = text
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            await update.message.reply_text("❌ Email tidak valid."); return
        context.user_data["email"] = email
        context.user_data["step"] = "wait_link"
        msg = await update.message.reply_text("⏳ Mengirim magic link...")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{BASE}/send-link", json={"email": email}) as r:
                    res = await r.json()
            if not res.get("success"):
                await msg.edit_text(f"❌ Gagal: {res.get('message')}")
                context.user_data.clear(); return
            await msg.delete()
            await update.message.reply_photo(photo=BANNER_URL,
                caption=TXT_STEP2.format(email=email), parse_mode="Markdown")
        except Exception as e:
            await msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")

    elif step == "wait_link":
        link = text
        if "http" not in link and "oobCode" not in link:
            await update.message.reply_text("❌ Link tidak valid."); return
        email = context.user_data["email"]
        context.user_data["step"] = "proses"
        msg = await update.message.reply_text(TXT_PROSES)
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(f"{BASE}/verify-link", json={"email": email, "magicLink": link}) as r:
                    res = await r.json()
            if not res.get("success"):
                reason = res.get("message", "Unknown")
                add_log(uid, uname, "premium_gagal")
                await msg.delete()
                await update.message.reply_photo(photo=BANNER_URL,
                    caption=TXT_FAIL.format(email=email, reason=reason), parse_mode="Markdown")
                context.user_data.clear(); return
            use_limit(uid)
            add_log(uid, uname, "premium_sukses")
            await msg.delete()
            caption = TXT_SUCCESS_PREMIUM_USER.format(email=email) if is_premium_user(uid) \
                else TXT_SUCCESS.format(email=email, status_limit=status_limit_text(uid))
            await update.message.reply_photo(photo=BANNER_URL, caption=caption, parse_mode="Markdown")
            if ADMIN_ID:
                try:
                    await context.bot.send_message(ADMIN_ID,
                        f"✅ *Premium berhasil!*\nUser: @{uname} (`{uid}`)\nEmail: `{email}`",
                        parse_mode="Markdown")
                except: pass
        except Exception as e:
            await msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")
        context.user_data.clear()

    else:
        await update.message.reply_text("Ketik /start buat mulai.")


# ============== WEB ==============
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Bot aktif ✅"


def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))


# ============== MAIN ==============
def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(CommandHandler("buy", buy_cmd))
    app.add_handler(CommandHandler("mypremium", mypremium_cmd))
    app.add_handler(CommandHandler("addprem", addprem_cmd))
    app.add_handler(CommandHandler("delprem", delprem_cmd))
    app.add_handler(CallbackQueryHandler(cb_start, pattern="^am_start$"))
    app.add_handler(CallbackQueryHandler(cb_buy, pattern="^am_buy$"))
    app.add_handler(CallbackQueryHandler(cb_kirim_bukti, pattern="^am_kirim_bukti$"))
    app.add_handler(CallbackQueryHandler(cb_admin_aksi, pattern="^adm_(ok|no)_"))
    app.add_handler(MessageHandler(filters.PHOTO, router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))
    print("✅ Bot jalan!")
    app.run_polling()


if __name__ == "__main__":
    main()
