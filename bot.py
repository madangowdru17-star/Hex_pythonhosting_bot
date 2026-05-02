import logging
import asyncio
import aiohttp
import socket
import json
import random
import string
import subprocess
import re
import os
import sys
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.constants import ParseMode, ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- ⚙️ CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "8687617595:AAEOeTwFDWquCAH3t497srDtrSRXM9Kaq4g")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7898928200"))
CHANNEL_1_ID = int(os.getenv("CHANNEL_1_ID", "-1003240507339"))
CHANNEL_2_ID = int(os.getenv("CHANNEL_2_ID", "-1003806004135"))
LINK_1 = os.getenv("LINK_1", "https://t.me/+dP7xLb3AoE1jNmRl")
LINK_2 = os.getenv("LINK_2", "https://t.me/+9vuPcr9LJ8piODdl")

FOOTER = "\n\n<b>⚡ ᴘᴏᴡᴇʀᴇᴅ ʙʏ @Hexh4ckerOFC</b>"
SEP = "━━━━━━━━━━━━━━━━━━━"

# APIs
LOOKUP_API = "https://tgchatid.vercel.app/api/lookup?number="
IFSC_API = "https://ifsc.razorpay.com/"
SHORTLINK_API = "https://link-btpass.onrender.com/bypass?key=9c44ad66b95cef8aecd7a99cfb362ce0&link="

# Local verify script (included in repo)
VERIFY_SCRIPT = "verify_india.py"

# Files
USERS_FILE = "users.json"
REDEEM_FILE = "redeem_codes.json"
SETTINGS_FILE = "settings.json"

# Settings
DAILY_FREE_CREDITS = 5
INVITE_CREDITS = 3
AUTO_DELETE_TIME = 60

BOT_NAME = "Hex Terminal"
BOT_USERNAME = "Hex_Terminal_bot"

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

MAIN_MENU_MESSAGE_IDS = set()
ADMIN_STATE = {}

# --- 🔧 VERIFY SCRIPT ---

def run_verify_script(choice, value):
    """Run local verify script"""
    if not os.path.exists(VERIFY_SCRIPT):
        logger.error("verify_india.py not found!")
        return None
    
    try:
        result = subprocess.run(
            [sys.executable, VERIFY_SCRIPT],
            input=f"{choice}\n{value}\n0\n",
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout.strip() if result.stdout else ""
        if len(output) > 20:
            return output
        return None
    except Exception as e:
        logger.error(f"Script error: {e}")
        return None

def clean_text(text):
    if not text: return ""
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', text)

def get_settings():
    try:
        with open(SETTINGS_FILE, 'r') as f: return json.load(f)
    except:
        d = {"bypass_maintenance":False,"bypass_msg":"","tgid_enabled":True,"ifsc_enabled":True,"bypass_enabled":True,"mobile_enabled":True,"aadhaar_enabled":True,"rc_enabled":True}
        save_settings(d); return d

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f: json.dump(data, f, indent=2)

# --- 💾 DATA ---

def load_json(filename):
    try:
        with open(filename, 'r') as f: return json.load(f)
    except: return {}

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=2)

def get_user(user_id):
    users = load_json(USERS_FILE)
    uid = str(user_id)
    today = datetime.now().strftime("%Y-%m-%d")
    if uid not in users:
        users[uid] = {"credits":DAILY_FREE_CREDITS,"total_queries":0,"daily_queries":0,"last_reset":today,"invite_code":f"HEX-{''.join(random.choices(string.ascii_uppercase+string.digits, k=8))}","invites":0,"verified":False}
        save_json(USERS_FILE, users)
    elif users[uid].get("last_reset") != today:
        users[uid]["credits"] = users[uid].get("credits",0) + DAILY_FREE_CREDITS
        users[uid]["daily_queries"] = 0
        users[uid]["last_reset"] = today
        save_json(USERS_FILE, users)
    return users[uid]

def save_user(uid, data):
    users = load_json(USERS_FILE); users[str(uid)] = data; save_json(USERS_FILE, users)

def add_credits(uid, amount):
    users = load_json(USERS_FILE); uid = str(uid)
    if uid in users: users[uid]["credits"] = users[uid].get("credits",0) + amount; save_json(USERS_FILE, users); return users[uid]["credits"]
    return 0

def use_credit(uid):
    users = load_json(USERS_FILE); uid = str(uid)
    if uid in users and users[uid].get("credits",0) > 0:
        users[uid]["credits"] -= 1; users[uid]["total_queries"] = users[uid].get("total_queries",0) + 1
        users[uid]["daily_queries"] = users[uid].get("daily_queries",0) + 1; save_json(USERS_FILE, users); return True
    return False

def process_invite(inviter_id, new_id):
    users = load_json(USERS_FILE); inviter = str(inviter_id); new = str(new_id)
    if inviter in users: users[inviter]["credits"] = users[inviter].get("credits",0) + INVITE_CREDITS; users[inviter]["invites"] = users[inviter].get("invites",0) + 1
    if new in users: users[new]["credits"] = users[new].get("credits",0) + INVITE_CREDITS; users[new]["invited_by"] = inviter
    save_json(USERS_FILE, users); return INVITE_CREDITS

def generate_redeem_code(credits):
    code = f"HEX-{''.join(random.choices(string.ascii_uppercase+string.digits, k=10))}"
    codes = load_json(REDEEM_FILE); codes[code] = {"credits":credits,"used":False,"created":datetime.now().isoformat()}
    save_json(REDEEM_FILE, codes); return code

def redeem_code(uid, code):
    codes = load_json(REDEEM_FILE); code = code.upper().strip()
    if code not in codes: return False, "❌ Invalid code"
    if codes[code].get("used"): return False, "❌ Already used"
    cr = codes[code]["credits"]; codes[code]["used"] = True; codes[code]["used_by"] = str(uid)
    save_json(REDEEM_FILE, codes); bal = add_credits(uid, cr)
    return True, f"✅ +{cr} credits!\n💰 Balance: {bal}"

# --- 🔍 VERIFY ---

async def check_channels(uid, context):
    try:
        m1 = await context.bot.get_chat_member(CHANNEL_1_ID, uid)
        m2 = await context.bot.get_chat_member(CHANNEL_2_ID, uid)
        return m1.status in ['member','administrator','creator'] and m2.status in ['member','administrator','creator']
    except: return False

# --- 🛠️ UTILS ---

async def net_ok():
    try: socket.create_connection(("8.8.8.8", 53), timeout=3); return True
    except: return False

async def auto_del(msg, delay=AUTO_DELETE_TIME):
    await asyncio.sleep(delay)
    try:
        if msg.message_id not in MAIN_MENU_MESSAGE_IDS: await msg.delete()
    except: pass

async def loading_animation(msg, name):
    bars = ["🟩⬛⬛⬛⬛⬛⬛⬛⬛⬛","🟩🟩⬛⬛⬛⬛⬛⬛⬛⬛","🟩🟩🟩⬛⬛⬛⬛⬛⬛⬛","🟩🟩🟩🟩⬛⬛⬛⬛⬛⬛","🟩🟩🟩🟩🟩⬛⬛⬛⬛⬛","🟩🟩🟩🟩🟩🟩⬛⬛⬛⬛","🟩🟩🟩🟩🟩🟩🟩⬛⬛⬛","🟩🟩🟩🟩🟩🟩🟩🟩⬛⬛","🟩🟩🟩🟩🟩🟩🟩🟩🟩⬛","🟩🟩🟩🟩🟩🟩🟩🟩🟩🟩"]
    for i, bar in enumerate(bars):
        try: await msg.edit_text(f"<blockquote>⚡ {name}</blockquote>\n<code>{bar} {i*10}%</code>", parse_mode=ParseMode.HTML); await asyncio.sleep(0.25)
        except: break

async def show_verification_page(update, context):
    caption = (
        f"<b>╭━━━━━━━━━━━━━━━━━━╮</b>\n"
        f"<b>┃  🤖 {BOT_NAME}  ┃</b>\n"
        f"<b>┃  @{BOT_USERNAME}    ┃</b>\n"
        f"<b>╰━━━━━━━━━━━━━━━━━━╯</b>\n\n"
        f"<b>🔒 ᴊᴏɪɴ ʙᴏᴛʜ ᴄʜᴀɴɴᴇʟꜱ</b>\n"
        f"<b>🎁 +{DAILY_FREE_CREDITS} ᴅᴀɪʟʏ | 👥 +{INVITE_CREDITS} ɪɴᴠɪᴛᴇ</b>\n\n"
        f"<b>📱 ᴛɢ ɪᴅ → ɴᴜᴍʙᴇʀ</b>\n"
        f"<b>🏦 ɪꜰꜱᴄ ʙᴀɴᴋ ɪɴꜰᴏ</b>\n"
        f"<b>🔗 ʟɪɴᴋ ʙʏᴘᴀꜱꜱ</b>\n"
        f"<b>📞 ᴍᴏʙɪʟᴇ ᴏꜱɪɴᴛ</b>\n"
        f"<b>🆔 ᴀᴀᴅʜᴀᴀʀ ꜰᴀᴍɪʟʏ</b>\n"
        f"<b>🚘 ʀᴄ ᴅᴇᴛᴀɪʟꜱ</b>\n\n"
        f"<b>👑 @Hexh4ckerOFC</b>"
    )
    try:
        bot = await context.bot.get_me()
        photos = await context.bot.get_user_profile_photos(bot.id, limit=1)
        if photos and photos.photos:
            await update.message.reply_photo(photo=photos.photos[0][-1].file_id, caption=caption, parse_mode=ParseMode.HTML)
            return
    except: pass
    await update.message.reply_text(caption, parse_mode=ParseMode.HTML)
    
    buttons = [
        [InlineKeyboardButton("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ 𝟷", url=LINK_1)],
        [InlineKeyboardButton("📢 ᴊᴏɪɴ ᴄʜᴀɴɴᴇʟ 𝟸", url=LINK_2)],
        [InlineKeyboardButton("✅ ᴠᴇʀɪꜰʏ", callback_data="verify")]
    ]
    await update.message.reply_text(
        "<blockquote>🔒 ᴊᴏɪɴ ʙᴏᴛʜ ᴄʜᴀɴɴᴇʟꜱ</blockquote>\n<blockquote>ᴛʜᴇɴ ᴄʟɪᴄᴋ ᴠᴇʀɪꜰʏ</blockquote>",
        reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.HTML
    )

async def main_menu(update, context):
    is_admin = update.effective_user.id == ADMIN_ID
    user = get_user(update.effective_user.id); s = get_settings()
    kb = []; row = []
    if s.get("tgid_enabled",True): row.append(KeyboardButton("📱 ᴛɢ ɪᴅ ᴛᴏ ɴᴜᴍʙ"))
    if s.get("ifsc_enabled",True): row.append(KeyboardButton("🏦 ɪꜰꜱᴄ ɪɴꜰᴏ"))
    if row: kb.append(row)
    if s.get("bypass_enabled",True): kb.append([KeyboardButton("🔗 ʟɪɴᴋ ʙʏᴘᴀꜱꜱ")])
    row2 = []
    if s.get("mobile_enabled",True): row2.append(KeyboardButton("📞 ɪɴᴅ ɴᴜᴍʙᴇʀ"))
    if s.get("aadhaar_enabled",True): row2.append(KeyboardButton("🆔 ᴀᴀᴅʜᴀᴀʀ"))
    if row2: kb.append(row2)
    if s.get("rc_enabled",True): kb.append([KeyboardButton("🚘 ʀᴄ ᴅᴇᴛᴀɪʟꜱ")])
    kb.append([KeyboardButton("👥 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ"), KeyboardButton("💎 ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ")])
    if is_admin: kb.append([KeyboardButton("👑 ᴀᴅᴍɪɴ")])
    markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    
    cr = user.get("credits",0); total = user.get("total_queries",0); invites = user.get("invites",0)
    txt = (
        f"<blockquote>💎 ᴘʀᴇᴍɪᴜᴍ ʜᴜʙ</blockquote>\n"
        f"<blockquote>ᴡᴇʟᴄᴏᴍᴇ <code>{update.effective_user.first_name}</code></blockquote>\n"
        f"<blockquote>💰 ᴄʀ: {cr} | 📊 ǫ: {total} | 👥 ɪɴᴠ: {invites}</blockquote>\n"
        f"<blockquote>🔄 +{DAILY_FREE_CREDITS} ᴅᴀɪʟʏ | ⏱ {AUTO_DELETE_TIME}ꜱ</blockquote>\n"
        f"<blockquote>ꜱᴇʟᴇᴄᴛ ᴀ ꜱᴇʀᴠɪᴄᴇ</blockquote>"
    )
    msg = await update.message.reply_text(txt, reply_markup=markup, parse_mode=ParseMode.HTML)
    MAIN_MENU_MESSAGE_IDS.add(msg.message_id)

# --- 🔗 API ---

async def api_fetch(session, url, timeout=15):
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as r:
            text = await r.text()
            if not text or text.startswith('<!'): return None
            return json.loads(text)
    except: return None

async def chatid_lookup(session, query):
    data = await api_fetch(session, f"{LOOKUP_API}{query}")
    if not data: return "<blockquote>❌ Service unavailable</blockquote>"
    if isinstance(data, dict) and data.get("success"):
        d = data.get("data", {})
        return f"<blockquote expandable>✨ 📱 ᴛɢ ɪᴅ ᴛᴏ ɴᴜᴍʙᴇʀ</blockquote>\n<blockquote>🆔: <code>{d.get('chat_id','N/A')}</code></blockquote>\n<blockquote>📞: <code>{d.get('number','N/A')}</code></blockquote>\n<blockquote>🌍: <code>{d.get('country','N/A')}</code></blockquote>"
    return "<blockquote>❌ Not found</blockquote>"

async def ifsc_lookup(session, code):
    data = await api_fetch(session, f"{IFSC_API}{code.upper()}")
    if not data: return "<blockquote>❌ Service unavailable</blockquote>"
    if isinstance(data, dict):
        return f"<blockquote expandable>✨ 🏦 ɪꜰꜱᴄ</blockquote>\n<blockquote>🏛: <code>{data.get('BANK','N/A')}</code></blockquote>\n<blockquote>📍: <code>{data.get('BRANCH','N/A')}</code></blockquote>\n<blockquote>🔑: <code>{data.get('IFSC',code.upper())}</code></blockquote>\n<blockquote>📫: <code>{data.get('ADDRESS','N/A')}</code></blockquote>"
    return "<blockquote>❌ Invalid</blockquote>"

async def bypass_lookup(session, link):
    s = get_settings()
    if s.get("bypass_maintenance",False): return f"<blockquote>🛠️ ᴍᴀɪɴᴛᴇɴᴀɴᴄᴇ</blockquote>"
    data = await api_fetch(session, f"{SHORTLINK_API}{link}", timeout=20)
    if not data: return "<blockquote>❌ Service unavailable</blockquote>"
    if isinstance(data, dict):
        r = data.get('bypassed_url') or data.get('url') or str(data)
        return f"<blockquote expandable>✨ 🔗 ʙʏᴘᴀꜱꜱᴇᴅ</blockquote>\n<blockquote>🔗 <code>{str(r)}</code></blockquote>"
    return f"<blockquote>🔗 <code>{str(data)}</code></blockquote>"

# --- 📊 PARSING ---

def parse_single_record(rt):
    d = {}
    for f, l in {'Name':'👤 Name',"Father's Name":'👨 Father','Mobile':'📱 Mobile','Alternative Number':'📞 Alternative','Address':'📍 Address','Email':'📧 Email','Circle':'📡 Circle'}.items():
        m = re.search(rf'{re.escape(f)}:\s*([^\n]+)', rt, re.IGNORECASE)
        if m and m.group(1).strip() not in ['None','','N/A','null']: d[l] = m.group(1).strip()
    return d if d else None

def parse_all_records(raw):
    raw = clean_text(raw) if raw else ""
    if not raw: return []
    recs = []
    for sec in re.split(r'={5,}|-{5,}|Record\s*\d+[:\s-]*', raw):
        sec = sec.strip()
        if len(sec) < 10: continue
        rd = parse_single_record(sec)
        if rd:
            seen = set(); ud = {}
            for k, v in rd.items():
                if v not in seen: seen.add(v); ud[k] = v
            if ud: recs.append(ud)
    if not recs:
        s = parse_single_record(raw)
        if s: recs.append(s)
    return recs

def format_aadhaar_result(raw):
    recs = parse_all_records(raw)
    if not recs: return None
    r = f"<blockquote expandable>✨ 🆔 ᴀᴀᴅʜᴀᴀʀ</blockquote>\n<blockquote>📊 Records: {len(recs)}</blockquote>\n"
    for i, rec in enumerate(recs, 1):
        if len(recs) > 1: r += f"\n<blockquote>━━ ʀᴇᴄᴏʀᴅ {i} ━━</blockquote>\n"
        for k in ['👤 Name','👨 Father','📱 Mobile','📞 Alternative','📍 Address','📧 Email','📡 Circle']:
            if k in rec: r += f"<blockquote>{k}: <code>{rec[k]}</code></blockquote>\n"
    return r

def format_mobile_result(raw):
    recs = parse_all_records(raw)
    if not recs: return None
    r = f"<blockquote expandable>✨ 📞 ɪɴᴅ ɴᴜᴍʙᴇʀ</blockquote>\n"
    if len(recs) > 1: r += f"<blockquote>📊 Records: {len(recs)}</blockquote>\n"
    for i, rec in enumerate(recs, 1):
        if len(recs) > 1: r += f"\n<blockquote>━━ ʀᴇᴄᴏʀᴅ {i} ━━</blockquote>\n"
        for k in ['👤 Name','👨 Father','📱 Mobile','📞 Alternative','📍 Address','📡 Circle']:
            if k in rec: r += f"<blockquote>{k}: <code>{rec[k]}</code></blockquote>\n"
    return r

def parse_rc_details(raw):
    raw = clean_text(raw) if raw else ""
    if not raw: return None
    d = {}
    for f, l in {'RC Number':'🔖 RC','Owner Name':'👤 Owner',"Father's Name":'👨 Father','Address':'📍 Address','Registered RTO':'🏢 RTO','Registration Date':'📅 Reg','Vehicle Class':'🚗 Class','Maker Model':'🏭 Maker','Model Name':'🚙 Model','Fuel Type':'⛽ Fuel','Insurance Company':'🛡️ Insurance','Insurance Expiry':'📅 Ins Exp','Fitness Upto':'✅ Fitness','Tax Upto':'💰 Tax','Financier Name':'🏦 Financier','Phone':'📞 Phone'}.items():
        m = re.search(rf'{re.escape(f)}:\s*([^\n]+)', raw, re.IGNORECASE)
        if m and m.group(1).strip() not in ['None','','N/A']: d[l] = m.group(1).strip()
    return d if d else None

def format_rc_result(data):
    if not data: return None
    r = "<blockquote expandable>✨ 🚘 ʀᴄ</blockquote>\n"
    for k in ['🔖 RC','👤 Owner','👨 Father','🚗 Class','🚙 Model','🏭 Maker','⛽ Fuel','📅 Reg','🏢 RTO','🛡️ Insurance','📅 Ins Exp','✅ Fitness','💰 Tax','🏦 Financier','📞 Phone','📍 Address']:
        if k in data: r += f"<blockquote>{k}: <code>{data[k]}</code></blockquote>\n"
    return r

# --- 👑 ADMIN ---

async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID: return
    s = get_settings()
    kb = [
        [InlineKeyboardButton("🎫 Generate Code", callback_data="ad_gen")],
        [InlineKeyboardButton("📋 Codes", callback_data="ad_codes")],
        [InlineKeyboardButton("🎁 Add Credits", callback_data="ad_credit")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="ad_bcast")],
        [InlineKeyboardButton(f"{'🟢' if s.get('tgid_enabled',True) else '🔴'} TG ID", callback_data="ad_tgid")],
        [InlineKeyboardButton(f"{'🟢' if s.get('ifsc_enabled',True) else '🔴'} IFSC", callback_data="ad_ifsc")],
        [InlineKeyboardButton(f"{'🟢' if s.get('bypass_enabled',True) else '🔴'} Bypass", callback_data="ad_bypass")],
        [InlineKeyboardButton(f"{'🟢' if s.get('mobile_enabled',True) else '🔴'} Mobile", callback_data="ad_mobile")],
        [InlineKeyboardButton(f"{'🟢' if s.get('aadhaar_enabled',True) else '🔴'} Aadhaar", callback_data="ad_aadhaar")],
        [InlineKeyboardButton(f"{'🟢' if s.get('rc_enabled',True) else '🔴'} RC", callback_data="ad_rc")],
        [InlineKeyboardButton("❌ Close", callback_data="ad_close")]
    ]
    txt = f"<blockquote>👑 Admin</blockquote>\n<blockquote>👥 {len(load_json(USERS_FILE))} | 🎫 {len(load_json(REDEEM_FILE))}</blockquote>"
    if update.callback_query: await update.callback_query.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)
    else: await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.HTML)

async def admin_callback(update, context):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID: await q.answer("❌"); return
    d = q.data; s = get_settings()
    if d == "ad_close": await q.message.delete()
    elif d == "ad_codes":
        codes = load_json(REDEEM_FILE)
        txt = f"<blockquote>🎫 Codes ({len(codes)})</blockquote>\n"
        for c, v in list(codes.items())[-15:]: txt += f"<blockquote>{'✅' if not v.get('used') else '❌'} <code>{c}</code> | {v.get('credits')}cr</blockquote>\n"
        await q.message.edit_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="ad_back")]]), parse_mode=ParseMode.HTML)
    elif d == "ad_gen": ADMIN_STATE[q.from_user.id] = "gen"; await q.message.edit_text("<blockquote>🎫 Credits:</blockquote>\n<i>100</i>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="ad_back")]]), parse_mode=ParseMode.HTML)
    elif d == "ad_credit": ADMIN_STATE[q.from_user.id] = "credit"; await q.message.edit_text("<blockquote>🎁 ID AMOUNT:</blockquote>\n<i>123456789 50</i>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="ad_back")]]), parse_mode=ParseMode.HTML)
    elif d == "ad_bcast": ADMIN_STATE[q.from_user.id] = "bcast"; await q.message.edit_text("<blockquote>📢 Message:</blockquote>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="ad_back")]]), parse_mode=ParseMode.HTML)
    elif d in ["ad_tgid","ad_ifsc","ad_bypass","ad_mobile","ad_aadhaar","ad_rc"]:
        key = d.replace("ad_","") + "_enabled"
        s[key] = not s.get(key, True)
        save_settings(s)
        await q.answer(f"{'ON' if s[key] else 'OFF'}", show_alert=True)
        await admin_panel(update, context)
    elif d == "ad_back": await admin_panel(update, context)
    await q.answer()

# --- 🚀 HANDLERS ---

async def start(update, context):
    try:
        uid = update.effective_user.id; args = context.args
        if args and args[0].startswith("HEX-"):
            users = load_json(USERS_FILE)
            for inviter, data in users.items():
                if data.get("invite_code") == args[0] and inviter != str(uid):
                    cr = process_invite(inviter, uid)
                    try: await context.bot.send_message(chat_id=int(inviter), text=f"<blockquote>🎉 +{cr} credits!</blockquote>", parse_mode=ParseMode.HTML)
                    except: pass
                    break
        user = get_user(uid)
        if not user.get("verified"):
            if await check_channels(uid, context):
                user["verified"] = True; save_user(uid, user)
                await main_menu(update, context); return
            await show_verification_page(update, context); return
        await main_menu(update, context)
    except Exception as e: logger.error(f"Start: {e}")

async def verify_cb(update, context):
    q = update.callback_query
    if await check_channels(q.from_user.id, context):
        user = get_user(q.from_user.id); user["verified"] = True; save_user(q.from_user.id, user)
        await q.answer("✅ Verified!"); 
        try: await q.message.delete()
        except: pass
        await main_menu(update, context)
    else: await q.answer("❌ Join both channels!", show_alert=True)

async def msg_handler(update, context):
    try:
        uid = update.effective_user.id; txt = update.message.text.strip()
        
        if uid == ADMIN_ID and uid in ADMIN_STATE:
            state = ADMIN_STATE.pop(uid)
            if state == "gen":
                try: cr = int(txt); code = generate_redeem_code(cr); await update.message.reply_text(f"<blockquote>✅ <code>{code}</code> | 💰 {cr}cr</blockquote>", parse_mode=ParseMode.HTML)
                except: await update.message.reply_text("<blockquote>❌ Number</blockquote>", parse_mode=ParseMode.HTML)
                return
            elif state == "credit":
                p = txt.split()
                if len(p) >= 2: bal = add_credits(p[0], int(p[1])); await update.message.reply_text(f"<blockquote>✅ +{p[1]} | {bal}</blockquote>", parse_mode=ParseMode.HTML)
                return
            elif state == "bcast":
                users = load_json(USERS_FILE); cnt = 0
                for u in users:
                    try: await context.bot.send_message(chat_id=int(u), text=f"📢 {txt}"); cnt += 1
                    except: pass
                await update.message.reply_text(f"<blockquote>✅ {cnt} users</blockquote>", parse_mode=ParseMode.HTML)
                return
        
        user = get_user(uid)
        if not user.get("verified"):
            if await check_channels(uid, context):
                user["verified"] = True; save_user(uid, user)
                await main_menu(update, context)
            else: await show_verification_page(update, context)
            return
        
        s = get_settings()
        
        if txt in ["👑 ᴀᴅᴍɪɴ"]: await admin_panel(update, context)
        elif txt in ["📱 ᴛɢ ɪᴅ ᴛᴏ ɴᴜᴍʙ"]:
            if not s.get("tgid_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'TG'
            btn = [[InlineKeyboardButton("🤖 @ChatIdInfoBot", url="https://t.me/ChatIdInfoBot")]]
            m = await update.message.reply_text("<blockquote>📱 ᴛɢ ɪᴅ ᴛᴏ ɴᴜᴍʙᴇʀ</blockquote>\n<blockquote>1️⃣ @ChatIdInfoBot</blockquote>\n<blockquote>2️⃣ Get Chat ID</blockquote>\n<blockquote>3️⃣ Enter here</blockquote>\n<i>7123181749</i>", reply_markup=InlineKeyboardMarkup(btn), parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt in ["🏦 ɪꜰꜱᴄ ɪɴꜰᴏ"]:
            if not s.get("ifsc_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'IFSC'
            m = await update.message.reply_text("<blockquote>🏦 ɪꜰꜱᴄ ɪɴꜰᴏ</blockquote>\n<blockquote>Enter IFSC code</blockquote>\n<i>SBIN0001234</i>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt in ["🔗 ʟɪɴᴋ ʙʏᴘᴀꜱꜱ"]:
            if not s.get("bypass_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'SHORTLINK'
            m = await update.message.reply_text("<blockquote>🔗 ʟɪɴᴋ ʙʏᴘᴀꜱꜱ</blockquote>\n<blockquote>Enter short link</blockquote>\n<i>https://indianshortner.in/xxx</i>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt == "📞 ɪɴᴅ ɴᴜᴍʙᴇʀ":
            if not s.get("mobile_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'MOBILE'
            m = await update.message.reply_text("<blockquote>📞 ɪɴᴅ ɴᴜᴍʙᴇʀ</blockquote>\n<blockquote>Enter 10-digit mobile</blockquote>\n<i>9876543210</i>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt == "🆔 ᴀᴀᴅʜᴀᴀʀ":
            if not s.get("aadhaar_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'AADHAAR'
            m = await update.message.reply_text("<blockquote>🆔 ᴀᴀᴅʜᴀᴀʀ</blockquote>\n<blockquote>Enter 12-digit Aadhaar</blockquote>\n<i>123456789012</i>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt == "🚘 ʀᴄ ᴅᴇᴛᴀɪʟꜱ":
            if not s.get("rc_enabled",True): await update.message.reply_text("<blockquote>📴 Disabled</blockquote>", parse_mode=ParseMode.HTML); return
            context.user_data['mode'] = 'VEHICLE_INDIA'
            m = await update.message.reply_text("<blockquote>🚘 ʀᴄ ᴅᴇᴛᴀɪʟꜱ</blockquote>\n<blockquote>Enter vehicle number</blockquote>\n<i>KA01AB3256</i>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m))
        elif txt in ["👥 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ"]:
            user = get_user(uid)
            bot_username = context.bot.username or BOT_USERNAME
            link = f"https://t.me/{bot_username}?start={user['invite_code']}"
            m = await update.message.reply_text(f"<blockquote>👥 ɪɴᴠɪᴛᴇ & ᴇᴀʀɴ</blockquote>\n<blockquote>🎁 +{INVITE_CREDITS} credits per invite</blockquote>\n<blockquote>🔗 <code>{link}</code></blockquote>\n<blockquote>👥 {user.get('invites',0)} | 💰 {user.get('credits',0)}</blockquote>", parse_mode=ParseMode.HTML)
            asyncio.create_task(auto_del(m, 120))
        elif txt in ["💎 ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ"]:
            await update.message.reply_text("<blockquote>💎 ʙᴜʏ ᴄʀᴇᴅɪᴛꜱ</blockquote>\n<blockquote>📩 @Hexh4ckerOFC</blockquote>\n<blockquote>💬 DM to buy</blockquote>\n<blockquote>🎫 Get redeem code</blockquote>", parse_mode=ParseMode.HTML)
        else:
            mode = context.user_data.get('mode')
            if mode:
                if txt.upper().startswith("HEX-") and len(txt) > 10:
                    success, msg = redeem_code(uid, txt)
                    await update.message.reply_text(f"<blockquote>{msg}</blockquote>", parse_mode=ParseMode.HTML)
                    context.user_data['mode'] = None; return
                user = get_user(uid)
                if user.get("credits", 0) <= 0:
                    await update.message.reply_text("<blockquote>❌ No credits</blockquote>\n<blockquote>🔄 +5 daily | 👥 +3 invite</blockquote>", parse_mode=ParseMode.HTML)
                    context.user_data['mode'] = None; return
                await run_query(update, context, mode, txt)
                context.user_data['mode'] = None
            else: await main_menu(update, context)
    except Exception as e: logger.error(f"Msg: {e}")

async def run_query(update, context, mode, query):
    if not await net_ok():
        await update.message.reply_text("<blockquote>🔴 No internet</blockquote>", parse_mode=ParseMode.HTML); return
    
    await update.message.reply_chat_action(ChatAction.TYPING)
    names = {'TG':'📱','IFSC':'🏦','SHORTLINK':'🔗','AADHAAR':'🆔','MOBILE':'📞','VEHICLE_INDIA':'🚘'}
    st = await update.message.reply_text("<blockquote>🟩 Searching...</blockquote>", parse_mode=ParseMode.HTML)
    lt = asyncio.create_task(loading_animation(st, names.get(mode, '')))
    
    try:
        if mode in ['AADHAAR','MOBILE','VEHICLE_INDIA']:
            if not os.path.exists(VERIFY_SCRIPT):
                result = "<blockquote>❌ Script missing</blockquote>"
            else:
                cm = {'AADHAAR':'2','MOBILE':'1','VEHICLE_INDIA':'4'}
                raw = run_verify_script(cm[mode], query)
                
                if raw:
                    if mode == 'VEHICLE_INDIA':
                        data = parse_rc_details(raw)
                        result = format_rc_result(data)
                    elif mode == 'MOBILE':
                        result = format_mobile_result(raw)
                    elif mode == 'AADHAAR':
                        result = format_aadhaar_result(raw)
                    
                    if not result:
                        result = "<blockquote>❌ No records found</blockquote>"
                        lt.cancel()
                        try: await lt
                        except asyncio.CancelledError: pass
                        final = f"{result}\n{SEP}\n<blockquote>💰 No credit deducted</blockquote>{FOOTER}"
                        await st.edit_text(final, parse_mode=ParseMode.HTML)
                        asyncio.create_task(auto_del(st)); return
                else:
                    result = "<blockquote>❌ No response</blockquote>"
        else:
            async with aiohttp.ClientSession() as s:
                if mode == 'TG': result = await chatid_lookup(s, query)
                elif mode == 'IFSC': result = await ifsc_lookup(s, query)
                elif mode == 'SHORTLINK': result = await bypass_lookup(s, query)
                else: result = "❌"
        
        use_credit(update.effective_user.id)
        lt.cancel()
        try: await lt
        except asyncio.CancelledError: pass
        
        user = get_user(update.effective_user.id)
        final = f"{result}\n{SEP}\n<blockquote>💰 CR: {user.get('credits',0)} | ⏱ {AUTO_DELETE_TIME}s</blockquote>{FOOTER}"
        await st.edit_text(final, parse_mode=ParseMode.HTML)
        asyncio.create_task(auto_del(st))
    except Exception as e:
        lt.cancel()
        logger.error(f"Query: {e}")
        try: await st.edit_text(f"<blockquote>⚠️ Error</blockquote>{FOOTER}", parse_mode=ParseMode.HTML)
        except: pass

def main():
    print(f"🔄 Starting {BOT_NAME}...")
    
    if os.path.exists(VERIFY_SCRIPT):
        print("✅ Verify script found!")
    else:
        print("⚠️ verify_india.py not found - India lookup disabled")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(verify_cb, pattern="^verify$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^ad_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_handler))
    
    print(f"✅ {BOT_NAME} Ready! 24/7 on Railway!")
    app.run_polling()

if __name__ == '__main__':
    main()