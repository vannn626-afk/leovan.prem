import os, re, json, aiohttp, threading, asyncio, random
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
FORCE_JOIN_CHANNEL = os.getenv("FORCE_JOIN_CHANNEL", "")
TESTIMONI_CHANNEL = os.getenv("TESTIMONI_CHANNEL", "")
LOG_FILE = "log.json"
VOUCHER_FILE = "vouchers.json"
LIMIT_PER_DAY = 3
HARGA_PREMIUM = 10000


# ============== STORAGE ==============
def load_log():
    if not os.path.exists(LOG_FILE):
        return {"users": {}, "daily": {}, "logs": [], "premium": {}, "pending": {}, "riwayat": {}}
    try:
        with open(LOG_FILE, "r") as f:
            data = json.load(f)
            for k in ["premium", "pending", "riwayat"]:
                if k not in data: data[k] = {}
            return data
    except:
        return {"users": {}, "daily": {}, "logs": [], "premium": {}, "pending": {}, "riwayat": {}}


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


def add_riwayat(user_id, email):
    data = load_log()
    uid = str(user_id)
    if uid not in data["riwayat"]:
        data["riwayat"][uid] = []
    data["riwayat"][uid].append({
        "email": email,
        "time": datetime.now().isoformat()
    })
    data["riwayat"][uid] = data["riwayat"][uid][-20:]
    save_log(data)


# ============== VOUCHER ==============
def load_vouchers():
    if not os.path.exists(VOUCHER_FILE):
        return {}
    try:
        with open(VOUCHER_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_vouchers(data):
    with open(VOUCHER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def buat_voucher(kode, diskon, max_use):
    data = load_vouchers()
    kode = kode.upper().strip()
    if kode in data:
        return False, "Kode udah ada"
    data[kode] = {
        "diskon": int(diskon),
        "max_use": int(max_use),
        "used": 0,
        "created": datetime.now().isoformat(),
        "aktif": True
    }
    save_vouchers(data)
    return True, f"✅ Kode `{kode}` dibuat (diskon {diskon}%, max {max_use}x)"


def cek_voucher(kode):
    data = load_vouchers()
    kode = kode.upper().strip()
    if kode not in data:
        return False, 0, "❌ Kode gak ditemukan"
    v = data[kode]
    if not v.get("aktif", True):
        return False, 0, "❌ Kode udah dinonaktifkan"
    if v["used"] >= v["max_use"]:
        return False, 0, "❌ Kode udah habis"
    return True, v["diskon"], f"✅ Kode valid! Diskon {v['diskon']}%"


def pakai_voucher(kode):
    data = load_vouchers()
    kode = kode.upper().strip()
    if kode in data:
        data[kode]["used"] += 1
        save_vouchers(data)


def list_voucher():
    data = load_vouchers()
    if not data:
        return "Belum ada voucher."
    txt = "🎫 *DAFTAR VOUCHER*\n━━━━━━━━━━━━━━━━━━\n"
    for kode, v in data.items():
        status = "✅" if v.get("aktif") and v["used"] < v["max_use"] else "❌"
        txt += f"{status} `{kode}` — {v['diskon']}% ({v['used']}/{v['max_use']})\n"
    return txt


def hapus_voucher(kode):
    data = load_vouchers()
    kode = kode.upper().strip()
    if kode in data:
        del data[kode]
        save_vouchers(data)
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
        "since": datetime.now().isoformat(),
        "days": days
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
    if is_admin(user_id): return 999
    if is_premium_user(user_id): return 999
    data = load_log()
    uid = str(user_id)
    today = str(date.today())
    daily = data["daily"].get(uid, {})
    if daily.get("date") != today: return LIMIT_PER_DAY
    used = daily.get("used", 0)
    return max(0, LIMIT_PER_DAY - used)


def use_limit(user_id):
    if is_admin(user_id): return
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


def tambah_limit_bonus(user_id, jumlah=1):
    """Kurangi pemakaian limit (bonus dari mini games)"""
    data = load_log()
    uid = str(user_id)
    today = str(date.today())
    daily = data["daily"].get(uid, {})
    if daily.get("date") == today:
        daily["used"] = max(0, daily.get("used", 0) - jumlah)
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


def is_admin(user_id):
    return user_id == ADMIN_ID


# ============== FORCE JOIN ==============
async def cek_join_channel(bot, user_id):
    """Return True kalo user udah join channel"""
    if not FORCE_JOIN_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=f"@{FORCE_JOIN_CHANNEL}", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

    # ============== TEKS ==============
TXT_WELCOME = (
    "🎬 *GET AM PREMIUM*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Aktifkan Alight Motion Premium\n"
    "gratis, cepat, 2 langkah.\n\n"
    "✨ No Watermark\n"
    "✨ Unlimited Export\n"
    "✨ Premium Effects & Fonts\n\n"
    "Tekan tombol di bawah 👇"
)

TXT_FORCE_JOIN = (
    "⚠️ *WAJIB JOIN CHANNEL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Buat pake bot ini, kamu wajib\n"
    "join channel kami dulu.\n\n"
    "Klik tombol di bawah, terus\n"
    "klik *✅ Udah Join* ya 👇"
)

TXT_STEP1 = (
    "📧 *STEP 1 — MASUKKAN EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Kirim email Alight Motion kamu.\n"
    "Contoh:\n`user@gmail.com`\n\n"
    "📊 Status limit:\n"
    "{status_limit}"
)

TXT_STEP2 = (
    "📬 *STEP 2 — CEK EMAIL*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Magic link dikirim ke:\n"
    "`{email}`\n\n"
    "Buka email → copy link → paste di sini 👇"
)

TXT_PROSES = "⏳ Verifikasi & aktivasi premium..."

TXT_SUCCESS = (
    "🎉 *PREMIUM AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\n"
    "Paket: *1 Tahun AM Premium*\n"
    "Status: ✅ BERHASIL\n\n"
    "{status_limit}\n\n"
    "Selamat berkarya 🗿🤗"
)

TXT_SUCCESS_PREMIUM_USER = (
    "🎉 *PREMIUM AKTIF!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Email: `{email}`\n"
    "Paket: *1 Tahun AM Premium*\n"
    "Status: ✅ BERHASIL\n\n"
    "👑 Kamu user *PREMIUM*\n"
    "Unlimited tanpa limit!\n\n"
    "Selamat berkarya 🗿🤗"
)

TXT_FAIL = (
    "❌ *GAGAL*\n"
    "Email: `{email}`\n"
    "Alasan: `{reason}`\n\n"
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
    "*Cara pakai:*\n"
    "1. Ketik /start\n"
    "2. Klik GET AM PREMIUM\n"
    "3. Kirim email Alight Motion\n"
    "4. Buka email, copy magic link\n"
    "5. Paste ke bot, tunggu proses\n\n"
    "*Command User:*\n"
    "/start — mulai\n"
    "/help — panduan\n"
    "/riwayat — riwayat aktivasi\n"
    "/limit — cek sisa limit\n"
    "/buy — beli akses no limit\n"
    "/mypremium — cek premium\n"
    "/game — main mini game\n\n"
    "*Limit user biasa:* max {max}x per hari\n"
    "*Premium:* unlimited, mulai {harga}"
)

TXT_STATUS = (
    "📊 *STATUS BOT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Status: ✅ Online\n"
    "Total user: *{users}*\n"
    "User premium: *{premium}*\n"
    "Limit harian: *{max}x*"
)

TXT_BUY = (
    "💎 *BELI AKSES NO LIMIT*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Bebas limit! Aktivasi sepuasnya.\n\n"
    "📦 *Paket tersedia:*\n"
    "• 1 Bulan — Rp 10.000\n"
    "• 3 Bulan — Rp 25.000 _(hemat Rp 5.000)_\n"
    "• Lifetime — Rp 50.000\n\n"
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
    "Status: 👑 ACTIVE\n"
    "Paket: Unlimited\n\n"
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
    "Status: {status}\n"
    "Expired: *{expired}*\n"
    "Sisa: *{sisa} hari*\n\n{footer}"
)

TXT_TESTI_PROMPT = (
    "📸 *KIRIM TESTIMONI?*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Boleh minta testimoni?\n"
    "Kirim foto screenshot Alight Motion kamu yang udah premium.\n\n"
    "Kamu dapet *1x limit bonus* 🎁"
)

TXT_TESTI_DITERIMA = (
    "✅ *TESTIMONI TERKIRIM!*\n"
    "━━━━━━━━━━━━━━━━━━\n"
    "Makasih udah kirim testimoni 🗿\n"
    "Kamu dapet *1x limit bonus* 🎁"
)


# ============== KEYBOARD ==============
def kb_reply_bottom():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎬 GET PREMIUM"), KeyboardButton("📖 Bantuan")],
            [KeyboardButton("💎 BELI AKSES NO LIMIT"), KeyboardButton("📈 Cek Limit")],
            [KeyboardButton("👑 My Premium"), KeyboardButton("📊 Status")],
            [KeyboardButton("🎮 Mini Games"), KeyboardButton("📜 Riwayat")]
        ],
        resize_keyboard=True, is_persistent=True
    )


def kb_reply_admin():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📊 Stats"), KeyboardButton("📝 Log")],
            [KeyboardButton("👥 User List"), KeyboardButton("💰 Pending")],
            [KeyboardButton("🎬 GET PREMIUM"), KeyboardButton("💎 BELI AKSES")],
            [KeyboardButton("👑 My Premium"), KeyboardButton("📖 Bantuan")],
            [KeyboardButton("🎮 Mini Games"), KeyboardButton("📜 Riwayat")]
        ],
        resize_keyboard=True, is_persistent=True
    )


def kb_main():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 GET AM PREMIUM", callback_data="am_start")],
        [InlineKeyboardButton("💎 BELI AKSES NO LIMIT", callback_data="am_buy")]
    ])


def kb_limit_habis():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 BELI AKSES NO LIMIT", callback_data="am_buy")]
    ])


def kb_buy():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Kirim Bukti Transfer", callback_data="am_kirim_bukti")],
        [InlineKeyboardButton("🎫 Punya Kode Voucher?", callback_data="am_voucher")]
    ])


def kb_admin_aksi(user_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Aktifkan 30hr", callback_data=f"adm_ok30_{user_id}"),
            InlineKeyboardButton("✅ Aktifkan 90hr", callback_data=f"adm_ok90_{user_id}")
        ],
        [
            InlineKeyboardButton("✅ Aktifkan Lifetime", callback_data=f"adm_oklife_{user_id}"),
            InlineKeyboardButton("❌ Tolak", callback_data=f"adm_no_{user_id}")
        ]
    ])


def kb_back():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Kembali", callback_data="am_back"),
         InlineKeyboardButton("❌ Batal", callback_data="am_cancel")]
    ])


def kb_force_join():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")],
        [InlineKeyboardButton("✅ Udah Join", callback_data="am_check_join")]
    ])


def kb_testi():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Kirim Testimoni", callback_data="am_testi"),
         InlineKeyboardButton("❌ Skip", callback_data="am_testi_skip")]
    ])

# ============== HELPER ==============
def status_limit_text(uid):
    if is_admin(uid):
        return "👑 *Admin* — Unlimited!"
    if is_premium_user(uid):
        info = get_premium_info(uid)
        return f"👑 *User PREMIUM*\nUnlimited! Expired: {info['expired']}"
    return f"Sisa limit: *{get_limit(uid)}/{LIMIT_PER_DAY}*\n⏰ Reset dalam: *{get_reset_countdown()}*"


# ============== COMMAND HANDLER ==============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name

    # Cek force join
    if FORCE_JOIN_CHANNEL:
        joined = await cek_join_channel(context.bot, uid)
        if not joined:
            await update.message.reply_text(
                TXT_FORCE_JOIN,
                parse_mode="Markdown",
                reply_markup=kb_force_join()
            )
            return

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
    await update.message.reply_text(
        TXT_HELP.format(max=LIMIT_PER_DAY, harga=f"Rp {HARGA_PREMIUM:,}".replace(",", ".")),
        parse_mode="Markdown"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_log()
    await update.message.reply_text(TXT_STATUS.format(
        users=len(data["users"]), premium=len(data.get("premium", {})), max=LIMIT_PER_DAY),
        parse_mode="Markdown")


async def limit_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    txt = "📊 *LIMIT KAMU*\n━━━━━━━━━━━━━━━━━━\n" + status_limit_text(uid)
    if is_premium_user(uid) or is_admin(uid):
        await update.message.reply_text(txt, parse_mode="Markdown")
    else:
        await update.message.reply_text(txt, parse_mode="Markdown", reply_markup=kb_limit_habis())


async def riwayat_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = load_log()
    rw = data.get("riwayat", {}).get(str(uid), [])
    if not rw:
        await update.message.reply_text("📜 Belum ada riwayat aktivasi.")
        return
    txt = "📜 *RIWAYAT AKTIVASI KAMU*\n━━━━━━━━━━━━━━━━━━\n"
    for i, item in enumerate(reversed(rw[-10:]), 1):
        tgl = item["time"][:10]
        txt += f"{i}. `{item['email']}`\n   📅 {tgl}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


async def buy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_photo(photo=QRIS_URL,
        caption=TXT_BUY.format(dana=NOMOR_DANA),
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


# ============== ADMIN COMMAND ==============
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


async def createvoucher_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Khusus admin."); return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Format: `/createvoucher KODE DISKON MAX_USE`\n"
            "Contoh: `/createvoucher PROMO50 50 10`",
            parse_mode="Markdown")
        return
    ok, msg = buat_voucher(context.args[0], int(context.args[1]), int(context.args[2]))
    await update.message.reply_text(msg, parse_mode="Markdown")


async def listvoucher_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Khusus admin."); return
    await update.message.reply_text(list_voucher(), parse_mode="Markdown")


async def delvoucher_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Khusus admin."); return
    if not context.args:
        await update.message.reply_text("Format: `/delvoucher KODE`", parse_mode="Markdown"); return
    if hapus_voucher(context.args[0]):
        await update.message.reply_text(f"✅ Voucher `{context.args[0].upper()}` dihapus.", parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Kode gak ditemukan.", parse_mode="Markdown")

# ============== CALLBACK HANDLER ==============
async def cb_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    if get_limit(uid) <= 0 and not is_premium_user(uid):
        await q.message.reply_text(
            TXT_LIMIT_HABIS.format(max=LIMIT_PER_DAY, countdown=get_reset_countdown()),
            parse_mode="Markdown", reply_markup=kb_limit_habis())
        return
    context.user_data.clear()
    context.user_data["step"] = "email"
    await q.message.reply_photo(photo=BANNER_URL,
        caption=TXT_STEP1.format(status_limit=status_limit_text(uid)),
        parse_mode="Markdown", reply_markup=kb_back())


async def cb_buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_photo(photo=QRIS_URL,
        caption=TXT_BUY.format(dana=NOMOR_DANA),
        parse_mode="Markdown", reply_markup=kb_buy())


async def cb_kirim_bukti(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["kirim_bukti"] = True
    await q.message.reply_text(TXT_KIRIM_BUKTI, parse_mode="Markdown")


async def cb_voucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["input_voucher"] = True
    await q.message.reply_text(
        "🎫 *MASUKIN KODE VOUCHER*\n━━━━━━━━━━━━━━━━━━\nKetik kode voucher kamu:",
        parse_mode="Markdown")


async def cb_testi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["kirim_testi"] = True
    await q.message.reply_text("📸 Kirim foto screenshotnya sekarang:")


async def cb_testi_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("Oke, gapapa. Makasih udah pakai bot 🗿")
    context.user_data.pop("kirim_testi", None)


async def cb_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    await q.message.reply_photo(photo=BANNER_URL, caption=TXT_WELCOME,
        parse_mode="Markdown", reply_markup=kb_main())


async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data.clear()
    await q.message.reply_text("❌ Dibatalkan. Ketik /start buat mulai lagi.")


async def cb_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_user.id
    joined = await cek_join_channel(context.bot, uid)
    if not joined:
        await q.answer("❌ Kamu belum join channel!", show_alert=True)
        return
    uname = update.effective_user.username or update.effective_user.first_name
    register_user(uid, uname)
    add_log(uid, uname, "start")
    await q.message.reply_photo(photo=BANNER_URL, caption=TXT_WELCOME,
        parse_mode="Markdown", reply_markup=kb_main())
    if is_admin(uid):
        await q.message.reply_text("👑 Menu admin:", reply_markup=kb_reply_admin())
    else:
        await q.message.reply_text("👇 Menu cepat:", reply_markup=kb_reply_bottom())


async def cb_admin_aksi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(update.effective_user.id): return
    parts = q.data.split("_")
    aksi = parts[1]
    target = int(parts[2])

    if aksi == "ok30":
        set_premium_user(target, 30)
        days_txt = "30 hari"
    elif aksi == "ok90":
        set_premium_user(target, 90)
        days_txt = "90 hari"
    elif aksi == "oklife":
        set_premium_user(target, 36500)
        days_txt = "Lifetime"
    elif aksi == "no":
        context.user_data["reject_target"] = target
        try:
            await q.edit_message_caption(
                caption=q.message.caption + "\n\n❌ *DITOLAK*\n\nKetik alasan penolakan:*",
                parse_mode="Markdown")
        except:
            await q.edit_message_text("❌ Ditolak. Ketik alasan:")
        return
    else:
        return

    add_log(target, "user", f"premium_manual_{aksi}")
    data = load_log()
    data.get("pending", {}).pop(str(target), None)
    save_log(data)
    try:
        await q.edit_message_caption(
            caption=q.message.caption + f"\n\n✅ *DIAKTIFKAN ({days_txt})*",
            parse_mode="Markdown")
    except:
        await q.edit_message_text(f"✅ Diaktifkan ({days_txt}).")
    try:
        await context.bot.send_message(target,
            f"🎉 *PREMIUM KAMU AKTIF!*\nPaket: {days_txt}\n\nSelamat 🗿🤗",
            parse_mode="Markdown")
    except: pass


# ============== ROUTER ==============
async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name

    # ===== Handle foto =====
    if update.message.photo:
        photo = update.message.photo[-1]

        # Foto testimoni
        if context.user_data.get("kirim_testi"):
            caption_channel = (
                f"📸 TESTIMONI BARU\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Nama: {update.effective_user.first_name}\n"
                f"📛 Username: @{uname}\n"
                f"📅 Tanggal: {datetime.now().strftime('%d %B %Y')}\n"
                f"✅ Verified by @Kelvanra_bot"
            )
            try:
                if TESTIMONI_CHANNEL:
                    await context.bot.send_photo(
                        f"@{TESTIMONI_CHANNEL}",
                        photo=photo.file_id,
                        caption=caption_channel,
                        parse_mode=None)
                    tambah_limit_bonus(uid, 1)
                    add_log(uid, uname, "kirim_testimoni")
                    await update.message.reply_text(TXT_TESTI_DITERIMA, parse_mode="Markdown")
                else:
                    await update.message.reply_text("❌ Channel testimoni belum di-set.")
            except Exception as e:
                await update.message.reply_text(f"❌ Gagal kirim: {e}")
            context.user_data.pop("kirim_testi", None)
            return

        # Foto bukti transfer
        if context.user_data.get("kirim_bukti"):
            nominal = context.user_data.get("harga_final", HARGA_PREMIUM)
            voucher_used = context.user_data.get("voucher_aktif", "-")
            caption_admin = (
                f"💰 *PEMBELIAN PREMIUM BARU*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👤 Nama: {update.effective_user.first_name}\n"
                f"📛 Username: @{uname}\n"
                f"🆔 User ID: `{uid}`\n"
                f"💵 Nominal: Rp {nominal:,}\n"
                f"🎫 Voucher: {voucher_used}\n\n"
                f"Cek bukti transfer di bawah 👇".replace(",", ".")
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

    # ===== Admin reply alasan tolak =====
    if is_admin(uid) and context.user_data.get("reject_target") and text:
        target = context.user_data.pop("reject_target")
        try:
            await context.bot.send_message(target,
                TXT_PREMIUM_DITOLAK.format(reason=text, admin=ADMIN_USERNAME),
                parse_mode="Markdown")
        except: pass
        await update.message.reply_text(f"✅ Alasan dikirim ke `{target}`.", parse_mode="Markdown")
        return

    # ===== Input voucher =====
    if context.user_data.get("input_voucher"):
        kode = text.upper().strip()
        valid, diskon, pesan = cek_voucher(kode)
        if not valid:
            await update.message.reply_text(pesan)
            context.user_data.pop("input_voucher", None)
            return
        harga_diskon = int(HARGA_PREMIUM * (100 - diskon) / 100)
        context.user_data["voucher_aktif"] = kode
        context.user_data["harga_final"] = harga_diskon
        context.user_data.pop("input_voucher", None)
        await update.message.reply_text(
            f"{pesan}\n\n💰 Harga asli: *Rp 10.000*\n🎉 Harga diskon: *Rp {harga_diskon:,}*\n\n"
            f"Transfer sesuai nominal diskon, kirim bukti ke bot.".replace(",", "."),
            parse_mode="Markdown")
        return

    # ===== TOMBOL ADMIN =====
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
            parse_mode="Markdown")
        return

    if text == "📝 Log" and is_admin(uid):
        data = load_log()
        logs = data["logs"][-20:]
        if not logs:
            await update.message.reply_text("Belum ada log."); return
        txt = "📝 *20 LOG TERAKHIR*\n━━━━━━━━━━━━━━━━━━\n"
        for l in logs:
            txt += f"`{l['time'][11:19]}` @{l['username']} — {l['event']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    if text == "👥 User List" and is_admin(uid):
        data = load_log()
        users = list(data["users"].items())[-30:]
        if not users:
            await update.message.reply_text("Belum ada user."); return
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
            await update.message.reply_text("✅ Gak ada pending."); return
        txt = "💰 *PENDING PEMBAYARAN*\n━━━━━━━━━━━━━━━━━━\n"
        for user_id, info in pending.items():
            txt += f"🆔 `{user_id}` — @{info['username']}\n"
        await update.message.reply_text(txt, parse_mode="Markdown")
        return

    # ===== TOMBOL USER =====
    if text == "🎬 GET PREMIUM":
        context.user_data.clear()
        context.user_data["step"] = "email"
        if get_limit(uid) <= 0 and not is_premium_user(uid):
            await update.message.reply_text(
                TXT_LIMIT_HABIS.format(max=LIMIT_PER_DAY, countdown=get_reset_countdown()),
                parse_mode="Markdown", reply_markup=kb_limit_habis())
            return
        await update.message.reply_photo(photo=BANNER_URL,
            caption=TXT_STEP1.format(status_limit=status_limit_text(uid)),
            parse_mode="Markdown", reply_markup=kb_back())
        return

    if text == "📖 Bantuan":
        await update.message.reply_text(
            TXT_HELP.format(max=LIMIT_PER_DAY, harga=f"Rp {HARGA_PREMIUM:,}".replace(",", ".")),
            parse_mode="Markdown")
        return

    if text in ["💎 BELI AKSES NO LIMIT", "💎 BELI AKSES"]:
        await update.message.reply_photo(photo=QRIS_URL, caption=TXT_BUY.format(dana=NOMOR_DANA),
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
            users=len(data["users"]), premium=len(data.get("premium", {})),
            max=LIMIT_PER_DAY), parse_mode="Markdown")
        return

    if text == "📈 Cek Limit":
        await update.message.reply_text(
            "📊 *LIMIT KAMU*\n━━━━━━━━━━━━━━━━━━\n" + status_limit_text(uid),
            parse_mode="Markdown")
        return

    if text == "📜 Riwayat":
        await riwayat_cmd(update, context)
        return

    if text == "🎮 Mini Games":
        await mini_game(update, context)
        return

    # ===== FLOW AKTIVASI =====
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
                caption=TXT_STEP2.format(email=email), parse_mode="Markdown",
                reply_markup=kb_back())
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
            add_riwayat(uid, email)
            await msg.delete()
            caption = TXT_SUCCESS_PREMIUM_USER.format(email=email) if is_premium_user(uid) \
                else TXT_SUCCESS.format(email=email, status_limit=status_limit_text(uid))
            await update.message.reply_photo(photo=BANNER_URL, caption=caption, parse_mode="Markdown")
            # Prompt testimoni
            await update.message.reply_text(TXT_TESTI_PROMPT, parse_mode="Markdown", reply_markup=kb_testi())
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

# ============== MINI GAMES ==============
SOAL_GAME = [
    {"q": "Ibu kota Indonesia?", "a": ["jakarta", "dki jakarta"]},
    {"q": "2 + 2 x 2 = ?", "a": ["6"]},
    {"q": "Planet terdekat matahari?", "a": ["merkurius", "mercury"]},
    {"q": "Hewan tercepat di darat?", "a": ["cheetah", "citah"]},
    {"q": "Warna langit cerah?", "a": ["biru", "blue"]},
    {"q": "Berapa jumlah warna pelangi?", "a": ["7", "tujuh"]},
    {"q": "Ibu kota Jepang?", "a": ["tokyo"]},
    {"q": "Alight Motion itu aplikasi apa?", "a": ["editor video", "edit video", "video editing"]},
    {"q": "1 tahun = berapa hari (biasa)?", "a": ["365"]},
    {"q": "Presiden pertama Indonesia?", "a": ["soekarno", "sukarno"]},
]


async def mini_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if context.user_data.get("game_aktif"):
        await update.message.reply_text("⚠️ Selesaikan game sebelumnya dulu.")
        return
    soal = random.choice(SOAL_GAME)
    context.user_data["game_aktif"] = True
    context.user_data["game_jawaban"] = soal["a"]
    await update.message.reply_text(
        f"🎮 *MINI GAMES*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"❓ {soal['q']}\n\n"
        f"💡 Jawab di chat ini.\n"
        f"🎁 Menang dapet *1x limit bonus*!\n"
        f"❌ Kalo salah, gak dapet apa-apa.\n\n"
        f"Ketik jawaban:",
        parse_mode="Markdown"
    )


async def cek_jawaban_game(update: Update, context: ContextTypes.DEFAULT_TYPE, jawaban: str):
    """Dipanggil dari router kalo ada game aktif"""
    uid = update.effective_user.id
    uname = update.effective_user.username or update.effective_user.first_name
    benar = context.user_data.get("game_jawaban", [])
    context.user_data.pop("game_aktif", None)
    context.user_data.pop("game_jawaban", None)

    jawaban_lower = jawaban.lower().strip()
    if jawaban_lower in [x.lower() for x in benar]:
        tambah_limit_bonus(uid, 1)
        add_log(uid, uname, "menang_game")
        await update.message.reply_text(
            "🎉 *BENAR!*\n\n"
            "Kamu dapet *1x limit bonus* 🎁\n"
            "Ketik /limit buat cek sisa limit.",
            parse_mode="Markdown"
        )
    else:
        jawaban_benar = benar[0] if benar else "-"
        await update.message.reply_text(
            f"❌ *SALAH!*\n\n"
            f"Jawaban bener: *{jawaban_benar.capitalize()}*\n"
            f"Coba lagi kapan aja 🗿",
            parse_mode="Markdown"
        )
    return True


# ============== BACKUP SCHEDULER ==============
async def daily_stats_loop(bot, admin_id):
    """Kirim stats ke admin tiap jam 12 malam"""
    while True:
        now = datetime.now()
        besok = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        delta = (besok - now).total_seconds()
        await asyncio.sleep(delta)
        try:
            data = load_log()
            today = str(date.today())
            today_users = sum(1 for u in data["users"].values() if u["first_seen"].startswith(today))
            total_prem = len(data.get("premium", {}))
            logs_today = [l for l in data["logs"] if l["time"].startswith(today)]
            sukses_today = sum(1 for l in logs_today if l["event"] == "premium_sukses")
            txt = (
                f"📊 *STATISTIK HARIAN*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📅 Tanggal: {today}\n"
                f"👥 User baru: *{today_users}*\n"
                f"✅ Sukses premium: *{sukses_today}*\n"
                f"👑 Total premium aktif: *{total_prem}*\n"
                f"⏳ Pending pembayaran: *{len(data.get('pending', {}))}*\n\n"
                f"_Selamat pagi admin! 🌅_"
            )
            await bot.send_message(admin_id, txt, parse_mode="Markdown")
        except Exception as e:
            print(f"[DAILY STATS ERROR] {e}")


# ============== WEB ==============
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Bot aktif ✅"


def run_web():
    flask_app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))


# ============== MAIN ==============
async def post_init(app):
    """Jalanin scheduler pas bot start"""
    if ADMIN_ID:
        asyncio.create_task(daily_stats_loop(app.bot, ADMIN_ID))
        print("✅ Daily stats scheduler jalan")


def main():
    threading.Thread(target=run_web, daemon=True).start()

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("limit", limit_cmd))
    app.add_handler(CommandHandler("riwayat", riwayat_cmd))
    app.add_handler(CommandHandler("buy", buy_cmd))
    app.add_handler(CommandHandler("mypremium", mypremium_cmd))
    app.add_handler(CommandHandler("game", mini_game))

    # Admin commands
    app.add_handler(CommandHandler("addprem", addprem_cmd))
    app.add_handler(CommandHandler("delprem", delprem_cmd))
    app.add_handler(CommandHandler("createvoucher", createvoucher_cmd))
    app.add_handler(CommandHandler("listvoucher", listvoucher_cmd))
    app.add_handler(CommandHandler("delvoucher", delvoucher_cmd))

    # Callback handlers
    app.add_handler(CallbackQueryHandler(cb_start, pattern="^am_start$"))
    app.add_handler(CallbackQueryHandler(cb_buy, pattern="^am_buy$"))
    app.add_handler(CallbackQueryHandler(cb_kirim_bukti, pattern="^am_kirim_bukti$"))
    app.add_handler(CallbackQueryHandler(cb_voucher, pattern="^am_voucher$"))
    app.add_handler(CallbackQueryHandler(cb_testi, pattern="^am_testi$"))
    app.add_handler(CallbackQueryHandler(cb_testi_skip, pattern="^am_testi_skip$"))
    app.add_handler(CallbackQueryHandler(cb_back, pattern="^am_back$"))
    app.add_handler(CallbackQueryHandler(cb_cancel, pattern="^am_cancel$"))
    app.add_handler(CallbackQueryHandler(cb_check_join, pattern="^am_check_join$"))
    app.add_handler(CallbackQueryHandler(cb_admin_aksi, pattern="^adm_(ok30|ok90|oklife|no)_"))

    # Message handlers
    app.add_handler(MessageHandler(filters.PHOTO, router))

    async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # Cek game aktif dulu
        if context.user_data.get("game_aktif"):
            await cek_jawaban_game(update, context, update.message.text.strip())
            return
        await router(update, context)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

    print("✅ Bot jalan!")
    app.run_polling()


if __name__ == "__main__":
    main()
