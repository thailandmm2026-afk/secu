import subprocess
import sys
import os
# အပေါ်ဆုံး ထည့်ပါ
if os.getenv("RENDER"):
    os.environ["BOT_PORT"] = os.getenv("PORT", "5000")
import sqlite3
import threading
import time
import re
import html as html_module
import atexit
import random
import string
import logging
import shutil
from datetime import datetime, timedelta
from threading import Thread

import psutil
import telebot
from telebot import types
import requests
from flask import Flask

# ========== AUTO INSTALL MISSING MODULES ==========
required_modules = [
    'psutil', 'pyTelegramBotAPI', 'flask', 'requests'
]

for module in required_modules:
    try:
        __import__(module)
    except ImportError:
        print(f"📦 Installing {module}...")
        if module == 'psutil':
    # PC အတွက် code
    pass
            subprocess.check_call(['pkg', 'install', 'python-psutil', '-y'])
        else:
            subprocess.check_call([sys.executable, "-m", "pip", "install", module, "--break-system-packages"])

# ========== FLASK KEEP-ALIVE ==========
app = Flask('')

@app.route('/')
def home():
    return """⚡
╔════════════════════════════════════════════════════╗
║              ⚡ KIKI CORE ⚡                    ║
║     Universal Python & JavaScript Cloud Hosting   ║
║            🚀 System Ready • Online               ║
╚════════════════════════════════════════════════════╝"""

def run_flask():
    port = int(os.environ.get("PORT", os.environ.get("BOT_PORT", 5000)))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run_flask)
    t.daemon = True
    t.start()
    print("🟣 Flask Keep-Alive started.")

# ========== BOT CONFIGURATION ==========
TOKEN = os.environ.get("BOT_TOKEN", '8850525377:AAEUrDW_1buI4JzmHmN-tcwJM_ZWVK38IZ0')
OWNER_ID = int(os.environ.get("OWNER_ID", 7308292609))
ADMIN_ID = int(os.environ.get("ADMIN_ID", 7308292609))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", '@kiki20251')

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'dev_bot.db')

DEFAULT_FORCE_CHANNEL_IDS = [-1002236605624,-1003068786628,-1002409342922]
DEFAULT_FORCE_GROUP_ID = -1002409342922
DEFAULT_CHANNEL_LINKS = {
    -1002236605624: "https://t.me/KMM_MOD1",
    -1003068786628: "https://t.me/Sketchware_Beginner_Developer",
    -1002409342922: "https://t.me/taka1251"
}
DEFAULT_GROUP_LINK = "https://t.me/taka1251"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, 'upload_bots')
os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)

PREMIUM_USER_LIMIT = 999
ADMIN_LIMIT = 999
OWNER_LIMIT = float('inf')

bot = telebot.TeleBot(TOKEN, threaded=True, num_threads=10)

# Global in-memory cache
bot_scripts = {}
bot_scripts_lock = threading.Lock()
user_subscriptions = {}   # user_id -> {'expiry': datetime, 'file_limit': int}
user_files = {}           # user_id -> list of (file_name, file_type, file_path)
active_users = set()
admin_ids = {ADMIN_ID, OWNER_ID}
banned_users = set()      # set of banned user_ids
bot_locked = False
broadcast_messages = {}
force_join_enabled = False
FREE_USER_LIMIT = 1
force_channel_ids = list(DEFAULT_FORCE_CHANNEL_IDS)
force_group_id = DEFAULT_FORCE_GROUP_ID

SUPPORTED_EXTENSIONS = {
    '.py': '🐍 Python',
    '.js': '🟨 JavaScript (Node.js)'
}

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

invite_links = {}
conn = None  # SQLite connection

# ========== DATABASE INIT ==========
def init_db():
    global conn
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        c = conn.cursor()

        c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                verified INTEGER DEFAULT 0,
                banned INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id INTEGER PRIMARY KEY,
                expiry TEXT,
                file_limit INTEGER DEFAULT 999
            );
            CREATE TABLE IF NOT EXISTS user_files (
                user_id INTEGER,
                file_name TEXT,
                file_type TEXT,
                file_path TEXT,
                UNIQUE(user_id, file_name)
            );
            CREATE TABLE IF NOT EXISTS active_users (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS subscription_keys (
                key_value TEXT PRIMARY KEY,
                days_valid INTEGER,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                file_limit INTEGER DEFAULT 999
            );
            CREATE TABLE IF NOT EXISTS key_usage (
                key_value TEXT,
                user_id INTEGER,
                UNIQUE(key_value, user_id)
            );
            CREATE TABLE IF NOT EXISTS bot_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            );
            CREATE TABLE IF NOT EXISTS premium_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                days INTEGER,
                price INTEGER,
                file_limit INTEGER
            );
        """)

        # Default settings
        default_settings = {
            "free_user_limit": str(FREE_USER_LIMIT),
            "force_join_enabled": "1",
            "force_channel_ids": ",".join(map(str, DEFAULT_FORCE_CHANNEL_IDS)),
            "force_group_id": str(DEFAULT_FORCE_GROUP_ID)
        }
        for key, val in default_settings.items():
            c.execute("INSERT OR IGNORE INTO bot_settings (setting_key, setting_value) VALUES (?,?)", (key, val))

        # Default premium plans
        c.execute("SELECT COUNT(*) FROM premium_plans")
        if c.fetchone()[0] == 0:
            plans = [
                ("📅 Weekly", 7, 2000, 2),
                ("📆 Monthly", 30, 15000, 5),
                ("📆 Quarterly", 90, 50000, 0),
                ("💼 Admin", -1, 200000, 0),
                ("📂 Bot File", -1, 50000, 0)
            ]
            c.executemany("INSERT INTO premium_plans (name, days, price, file_limit) VALUES (?,?,?,?)", plans)

        # Ensure owner and admin in admins table
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))

        conn.commit()
        logger.info("✅ SQLite database connected and initialized.")
    except Exception as e:
        logger.error(f"❌ SQLite error: {e}", exc_info=True)
        sys.exit(1)

def load_data():
    global user_subscriptions, user_files, active_users, admin_ids, banned_users
    global FREE_USER_LIMIT, force_join_enabled, force_channel_ids, force_group_id
    try:
        c = conn.cursor()

        # Subscriptions
        user_subscriptions.clear()
        for row in c.execute("SELECT user_id, expiry, file_limit FROM subscriptions"):
            try:
                expiry_str = row[1]
                if expiry_str == '9999-12-31T23:59:59':
                    expiry = datetime(9999, 12, 31, 23, 59, 59)
                else:
                    expiry = datetime.fromisoformat(expiry_str)
                user_subscriptions[row[0]] = {"expiry": expiry, "file_limit": row[2]}
            except:
                pass

        # User files
        user_files.clear()
        for row in c.execute("SELECT user_id, file_name, file_type, file_path FROM user_files"):
            uid = row[0]
            if uid not in user_files:
                user_files[uid] = []
            user_files[uid].append((row[1], row[2], row[3]))

        # Active users
        active_users.clear()
        for row in c.execute("SELECT user_id FROM active_users"):
            active_users.add(row[0])

        # Admins
        admin_ids = {OWNER_ID}
        for row in c.execute("SELECT user_id FROM admins"):
            admin_ids.add(row[0])
        admin_ids.add(OWNER_ID)  # ensure

        # Banned users
        banned_users.clear()
        for row in c.execute("SELECT user_id FROM users WHERE banned=1"):
            banned_users.add(row[0])

        # Bot settings
        for row in c.execute("SELECT setting_key, setting_value FROM bot_settings"):
            key = row[0]; val = row[1]
            if key == "free_user_limit":
                FREE_USER_LIMIT = int(val) if val.isdigit() else 1
            elif key == "force_join_enabled":
                force_join_enabled = val == "1"
            elif key == "force_channel_ids":
                if val.strip():
                    force_channel_ids = [int(x) for x in val.split(',') if x.strip().lstrip('-').isdigit()]
                else:
                    force_channel_ids = list(DEFAULT_FORCE_CHANNEL_IDS)
            elif key == "force_group_id":
                force_group_id = int(val) if val.strip().lstrip('-').isdigit() else DEFAULT_FORCE_GROUP_ID

        logger.info(f"📊 Data loaded: {len(active_users)} users, {len(user_subscriptions)} subscriptions")
    except Exception as e:
        logger.error(f"❌ Error loading data: {e}", exc_info=True)

init_db()
load_data()

# ========== AUTO INSTALL NODE.JS ==========
def install_nodejs():
    if shutil.which("node") and shutil.which("npm"):
        return True
    print("🔧 Node.js / npm not found. Installing...")
    try:
        if os.path.exists('/data/data/com.termux'):
            subprocess.check_call(['pkg', 'install', 'nodejs', '-y'])
        else:
            try:
                subprocess.check_call(['sudo', 'apt-get', 'update'])
                subprocess.check_call(['sudo', 'apt-get', 'install', '-y', 'nodejs', 'npm'])
            except:
                subprocess.check_call(['apt-get', 'update'])
                subprocess.check_call(['apt-get', 'install', '-y', 'nodejs', 'npm'])
        if shutil.which("node") and shutil.which("npm"):
            return True
        if shutil.which("node") and not shutil.which("npm"):
            try:
                if os.path.exists('/data/data/com.termux'):
                    subprocess.check_call(['pkg', 'install', 'npm', '-y'])
                else:
                    try:
                        subprocess.check_call(['sudo', 'apt-get', 'install', '-y', 'npm'])
                    except:
                        subprocess.check_call(['apt-get', 'install', '-y', 'npm'])
            except: pass
        return shutil.which("node") and shutil.which("npm")
    except Exception as e:
        print(f"❌ Node.js install failed: {e}")
    return False

# ========== SYSTEM STATS ==========
def get_system_stats():
    try:
        cpu = psutil.cpu_percent(interval=0.5)
    except:
        cpu = 0.0
    try:
        mem = psutil.virtual_memory()
        ram_percent = mem.percent
        ram_used = mem.used >> 20
        ram_total = mem.total >> 20
    except:
        ram_percent = 0; ram_used = 0; ram_total = 0
    return {'cpu': cpu, 'ram_percent': ram_percent, 'ram_used': ram_used, 'ram_total': ram_total}

# ========== BAN SYSTEM ==========
def is_user_banned(user_id):
    return user_id in banned_users

def ban_user(user_id):
    if user_id in admin_ids:
        return False, "❌ Admin/မပိုင်ရှင်ကို ban မလုပ်နိုင်ပါ။"
    conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))
    conn.commit()
    banned_users.add(user_id)
    # Stop all running bots of this user
    stop_user_bots(user_id)
    # Remove from active users (optional)
    if user_id in active_users:
        active_users.discard(user_id)
        conn.execute("DELETE FROM active_users WHERE user_id=?", (user_id,))
        conn.commit()
    return True, f"✅ User <code>{user_id}</code> ban လိုက်ပါပြီ။"

def unban_user(user_id):
    if user_id not in banned_users:
        return False, "⚠️ ဤ user ban မခံထားရပါ။"
    conn.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))
    conn.commit()
    banned_users.discard(user_id)
    return True, f"✅ User <code>{user_id}</code> unban ပြီးပါပြီ။"

def stop_user_bots(user_id):
    with bot_scripts_lock:
        scripts_to_kill = [key for key in bot_scripts if key.startswith(f"{user_id}_")]
        for key in scripts_to_kill:
            kill_process_tree(bot_scripts[key])
            del bot_scripts[key]

# ========== PREMIUM PLANS ==========
def get_all_premium_plans():
    c = conn.cursor()
    c.execute("SELECT id, name, days, price, file_limit FROM premium_plans ORDER BY id")
    return [{"id": row[0], "name": row[1], "days": row[2], "price": row[3], "file_limit": row[4]} for row in c.fetchall()]

def add_premium_plan(name, days, price, file_limit):
    conn.execute("INSERT INTO premium_plans (name, days, price, file_limit) VALUES (?,?,?,?)",
                 (name, days, price, file_limit))
    conn.commit()

def delete_premium_plan(plan_id):
    conn.execute("DELETE FROM premium_plans WHERE id=?", (int(plan_id),))
    conn.commit()

def get_premium_plan_by_id(plan_id):
    c = conn.cursor()
    c.execute("SELECT id, name, days, price, file_limit FROM premium_plans WHERE id=?", (int(plan_id),))
    row = c.fetchone()
    if row:
        return {"id": row[0], "name": row[1], "days": row[2], "price": row[3], "file_limit": row[4]}
    return None

# ========== USER VERIFICATION ==========
def is_premium_user(user_id):
    if user_id in user_subscriptions:
        expiry = user_subscriptions[user_id]['expiry']
        return expiry > datetime.now()
    return False

def get_user_status(user_id):
    if user_id == OWNER_ID: return "👑 ပိုင်ရှင်"
    if user_id in admin_ids: return "🛡️ အယ်မင်း"
    if is_premium_user(user_id): return "✨ ပရိုမ်း"
    return "🎯 အခြေခံ"

def is_user_verified(user_id):
    if user_id in admin_ids:
        return True
    c = conn.cursor()
    c.execute("SELECT verified FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row and row[0] == 1

def set_user_verified(user_id):
    conn.execute("UPDATE users SET verified=1 WHERE user_id=?", (user_id,))
    conn.commit()

def check_force_join_and_access(user_id):
    return True
    if user_id in admin_ids:
        return True
    if is_user_verified(user_id):
        return True
    return False

def verify_membership(user_id):
    return True
    try:
        for ch_id in force_channel_ids:
            member = bot.get_chat_member(ch_id, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        group_member = bot.get_chat_member(force_group_id, user_id)
        if group_member.status not in ['member', 'administrator', 'creator']:
            return False
        if not is_user_verified(user_id):
            set_user_verified(user_id)
        return True
    except Exception as e:
        logger.error(f"Membership check error for {user_id}: {e}")
    return False

def create_force_join_message():
    ch0 = get_channel_name(force_channel_ids[0]) if force_channel_ids else '❌'
    ch1 = get_channel_name(force_channel_ids[1]) if len(force_channel_ids) > 1 else '❌'
    ch2 = get_channel_name(force_channel_ids[2]) if len(force_channel_ids) > 2 else '❌'
    return f"""
╔══════════════════════════╗
║   🔐 <b>အဖွဲ့ဝင်ဖြစ်ရန် လိုအပ်</b>   ║
╚══════════════════════════╝

✨ <b>အောက်ပါချန်နယ်များနှင့် အုပ်စုသို့ ဝင်ပါ</b>

📣 <b>ချန်နယ်များ</b>
├─ {ch0}
├─ {ch1}
└─ {ch2}
👥 <b>အုပ်စု</b>
└─ {get_group_name(force_group_id)}

📋 <b>လမ်းညွှန်:</b>
1️⃣ အောက်ပါခလုတ်များကို နှိပ်ပါ
2️⃣ စက္ကန့် 50 စောင့်ပါ
3️⃣ "✅ အဖွဲ့ဝင်စစ်ဆေးပါ" ကိုနှိပ်ပါ
4️⃣ <b>အခမဲ့ အမြဲတမ်း အသုံးပြုခွင့်</b> ရမည်

🎁 <b>အကျိုးကျေးဇူး:</b> Python/JS scripts 24/7 run နိုင်သည်
    """

def get_channel_name(chat_id):
    try:
        chat = bot.get_chat(chat_id)
        return f"<b>{chat.title}</b>"
    except:
        return f"ID: {chat_id}"

def get_group_name(chat_id):
    try:
        chat = bot.get_chat(chat_id)
        return f"<b>{chat.title}</b>"
    except:
        return f"ID: {chat_id}"

def create_force_join_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for ch_id in force_channel_ids:
        link = get_or_create_invite_link(ch_id)
        if link:
            markup.add(types.InlineKeyboardButton(f"📣 {get_channel_name(ch_id)}", url=link))
        else:
            markup.add(types.InlineKeyboardButton(f"📣 Channel {ch_id}", callback_data='no_link'))
    group_link = get_or_create_invite_link(force_group_id)
    if group_link:
        markup.add(types.InlineKeyboardButton("👥 အုပ်စုသို့ဝင်ရန်", url=group_link))
    else:
        markup.add(types.InlineKeyboardButton("👥 အုပ်စုသို့ဝင်ရန်", callback_data='no_link'))
    markup.add(types.InlineKeyboardButton("✅ အဖွဲ့ဝင်စစ်ဆေးပါ", callback_data='check_membership'))
    return markup

def get_or_create_invite_link(chat_id):
    if chat_id in invite_links:
        return invite_links[chat_id]
    try:
        link = bot.export_chat_invite_link(chat_id)
        invite_links[chat_id] = link
        return link
    except:
        if chat_id in DEFAULT_CHANNEL_LINKS:
            return DEFAULT_CHANNEL_LINKS[chat_id]
        if chat_id == DEFAULT_FORCE_GROUP_ID:
            return DEFAULT_GROUP_LINK
        return None

# ========== STORAGE HELPERS ==========
def get_user_folder(user_id):
    user_folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(user_folder, exist_ok=True)
    return user_folder

def get_user_file_count(user_id):
    return len(user_files.get(user_id, []))

def get_user_file_limit(user_id):
    if user_id == OWNER_ID or user_id in admin_ids:
        return float('inf')
    if is_premium_user(user_id):
        sub = user_subscriptions.get(user_id)
        if sub and 'file_limit' in sub:
            limit = sub['file_limit']
            return float('inf') if limit == 0 else limit
        return PREMIUM_USER_LIMIT
    return FREE_USER_LIMIT

# ========== KEY MANAGEMENT ==========
def generate_subscription_key(days, file_limit):
    random_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    key = f"KIKI-{random_code}"
    conn.execute("INSERT INTO subscription_keys (key_value, days_valid, max_uses, used_count, file_limit) VALUES (?,?,1,0,?)",
                 (key, days, file_limit))
    conn.commit()
    return key

def redeem_subscription_key(key_value, user_id):
    c = conn.cursor()
    c.execute("SELECT days_valid, max_uses, used_count, file_limit FROM subscription_keys WHERE key_value=?", (key_value,))
    row = c.fetchone()
    if not row:
        return False, "❌ Key မမှန်ပါ"
    days_valid, max_uses, used_count, file_limit = row
    if used_count >= max_uses:
        return False, "❌ Key ကို အခြားသူအသုံးပြုပြီးပါပြီ"
    c.execute("SELECT COUNT(*) FROM key_usage WHERE key_value=? AND user_id=?", (key_value, user_id))
    if c.fetchone()[0] > 0:
        return False, "❌ Key ကို အသုံးပြုပြီးသားဖြစ်သည်"

    current_expiry = user_subscriptions.get(user_id, {}).get('expiry', datetime.now())
    if current_expiry < datetime.now():
        current_expiry = datetime.now()
    if days_valid == -1:
        new_expiry = datetime(9999, 12, 31, 23, 59, 59)
    else:
        new_expiry = current_expiry + timedelta(days=days_valid)

    save_subscription(user_id, new_expiry, file_limit)

    conn.execute("UPDATE subscription_keys SET used_count = used_count + 1 WHERE key_value=?", (key_value,))
    conn.execute("INSERT INTO key_usage (key_value, user_id) VALUES (?,?)", (key_value, user_id))
    conn.commit()

    limit_display = "အကန့်အသတ်မဲ့" if file_limit == 0 else str(file_limit)
    days_display = "တစ်သက်တာ" if days_valid == -1 else f"{days_valid} ရက်"
    expiry_display = "တစ်သက်တာ" if days_valid == -1 else new_expiry.strftime('%Y-%m-%d %H:%M:%S')
    return True, f"""
✨ <b>Key အသက်ဝင်ပါပြီ</b> ✨
🔑 <b>Key:</b> <code>{key_value}</code>
📅 <b>ကာလ:</b> {days_display}
📁 <b>ဖိုင်အကန့်အသတ်:</b> {limit_display}
⏳ <b>ကုန်ဆုံး:</b> {expiry_display}
✨ <b>ရရှိသောအခွင့်အရေးများ:</b>
├─ ⚡ {limit_display} ဖိုင်များ
├─ 📦 အဆင့်မြှင့်သိုလှောင်မှု
└─ 🛡️ ဦးစားပေးအကူအညီ
    """

def save_subscription(user_id, expiry, file_limit):
    if expiry >= datetime(9999, 12, 31, 23, 59, 59):
        expiry_str = '9999-12-31T23:59:59'
    else:
        expiry_str = expiry.isoformat()
    conn.execute("INSERT OR REPLACE INTO subscriptions (user_id, expiry, file_limit) VALUES (?,?,?)",
                 (user_id, expiry_str, file_limit))
    conn.commit()
    user_subscriptions[user_id] = {'expiry': expiry, 'file_limit': file_limit}

def delete_subscription_key(key_value):
    # Get all users who used this key and remove their subscriptions
    c = conn.cursor()
    c.execute("SELECT user_id FROM key_usage WHERE key_value=?", (key_value,))
    users = [row[0] for row in c.fetchall()]
    for uid in users:
        conn.execute("DELETE FROM subscriptions WHERE user_id=?", (uid,))
        if uid in user_subscriptions:
            del user_subscriptions[uid]
    conn.execute("DELETE FROM subscription_keys WHERE key_value=?", (key_value,))
    conn.execute("DELETE FROM key_usage WHERE key_value=?", (key_value,))
    conn.commit()

def get_all_subscription_keys():
    c = conn.cursor()
    c.execute("SELECT key_value, days_valid, max_uses, used_count, file_limit FROM subscription_keys")
    return [{"key_value": row[0], "days_valid": row[1], "max_uses": row[2], "used_count": row[3], "file_limit": row[4]} for row in c.fetchall()]

# ========== PROCESS MANAGEMENT ==========
def is_bot_running(script_owner_id, file_name):
    script_key = f"{script_owner_id}_{file_name}"
    with bot_scripts_lock:
        script_info = bot_scripts.get(script_key)
    if script_info and script_info.get('process'):
        try:
            proc = psutil.Process(script_info['process'].pid)
            return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        except psutil.NoSuchProcess:
            return False
    return False

def kill_process_tree(process_info):
    try:
        process = process_info.get('process')
        if process and hasattr(process, 'pid'):
            pid = process.pid
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try: child.kill()
                except: pass
            try:
                parent.kill()
                parent.wait(timeout=5)
            except: pass
            if process_info.get('log_file'):
                try: process_info['log_file'].close()
                except: pass
    except Exception as e:
        logger.error(f"❌ Error killing process: {e}")

def attempt_install_pip(module_name, message_obj):
    try:
        bot.reply_to(message_obj, f"🔧 <code>{module_name}</code> တပ်ဆင်နေသည်...", parse_mode='HTML')
        cmd = [sys.executable, '-m', 'pip', 'install', module_name, '--timeout', '60', '--retries', '3', '--break-system-packages']
        result = subprocess.run(cmd, capture_output=True, text=True, check=False, encoding='utf-8', errors='ignore', timeout=120)
        if result.returncode == 0:
            bot.reply_to(message_obj, f"✅ <code>{module_name}</code> တပ်ဆင်ပြီးပါပြီ", parse_mode='HTML')
            return True
        else:
            raw_err = html_module.escape(result.stderr or result.stdout or '')
            bot.reply_to(message_obj, f"❌ တပ်ဆင်မှုအမှား\n<pre>{raw_err[:3000]}</pre>", parse_mode='HTML')
            return False
    except Exception as e:
        bot.reply_to(message_obj, f"❌ အမှား: {str(e)}")
        return False

def patch_script_for_replit(script_path, user_folder):
    try:
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        patched = []
        for line in lines:
            if ('pip' in line and 'install' in line and '--break-system-packages' not in line
                    and ('subprocess' in line or 'check_call' in line or 'check_output' in line)):
                stripped = line.rstrip('\n')
                bracket_pos = stripped.rfind(']')
                if bracket_pos != -1:
                    line = stripped[:bracket_pos] + ", '--break-system-packages'" + stripped[bracket_pos:] + '\n'
            patched.append(line)
        base = os.path.splitext(os.path.basename(script_path))[0]
        patched_path = os.path.join(user_folder, f"{base}_patched.py")
        with open(patched_path, 'w', encoding='utf-8', errors='ignore') as f:
            f.writelines(patched)
        return patched_path
    except:
        return script_path

def run_python_script(script_path, script_owner_id, user_folder, file_name, message_obj, attempt=1):
    max_attempts = 3
    if attempt > max_attempts:
        bot.reply_to(message_obj, f"❌ <code>{file_name}</code> စတင်ရာတွင်အမှား", parse_mode='HTML')
        return
    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"Attempt {attempt} to run: {script_path}")
    log_file = None
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj, f"❌ ဖိုင်မတွေ့ပါ")
            return
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        run_env = os.environ.copy()
        run_env['PIP_BREAK_SYSTEM_PACKAGES'] = '1'
        patched_path = patch_script_for_replit(script_path, user_folder)
        process = subprocess.Popen(
            [sys.executable, patched_path],
            cwd=user_folder, stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, encoding='utf-8', errors='ignore', bufsize=1, env=run_env
        )
        with bot_scripts_lock:
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'py', 'script_key': script_key
            }
        time.sleep(3)
        if process.poll() is not None:
            log_file.flush()
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                    log_content = lf.read()
            except:
                log_content = ''
            PACKAGE_MAP = {
                'telegram': 'python-telegram-bot', 'cv2': 'opencv-python',
                'sklearn': 'scikit-learn', 'PIL': 'Pillow', 'bs4': 'beautifulsoup4',
                'dotenv': 'python-dotenv', 'yaml': 'pyyaml', 'Crypto': 'pycryptodome', 'gi': 'PyGObject'
            }
            install_pkg = None; uninstall_pkg = None
            m1 = re.search(r"ModuleNotFoundError: No module named '([^']+)'", log_content)
            if m1: install_pkg = PACKAGE_MAP.get(m1.group(1).split('.')[0], m1.group(1).split('.')[0])
            if not install_pkg:
                m2 = re.search(r"ImportError: cannot import name '.+?' from '([^']+)'", log_content)
                if m2:
                    wrong_pkg = m2.group(1).split('.')[0]
                    if wrong_pkg in PACKAGE_MAP:
                        install_pkg = PACKAGE_MAP[wrong_pkg]; uninstall_pkg = wrong_pkg
            if not install_pkg:
                m3 = re.search(r"ImportError: No module named '([^']+)'", log_content)
                if m3: install_pkg = PACKAGE_MAP.get(m3.group(1).split('.')[0], m3.group(1).split('.')[0])
            if install_pkg and attempt < max_attempts:
                with bot_scripts_lock:
                    if script_key in bot_scripts: del bot_scripts[script_key]
                if uninstall_pkg:
                    subprocess.run([sys.executable, '-m', 'pip', 'uninstall', uninstall_pkg, '-y', '--break-system-packages'], capture_output=True, timeout=60)
                if attempt_install_pip(install_pkg, message_obj):
                    threading.Thread(target=run_python_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj, attempt+1)).start()
                return
            with bot_scripts_lock:
                if script_key in bot_scripts: del bot_scripts[script_key]
            err_preview = log_content[-800:] if log_content else ''
            safe_preview = html_module.escape(err_preview)
            bot.reply_to(message_obj, f"❌ <code>{html_module.escape(file_name)}</code> ပျက်သွားသည်:\n<pre>{safe_preview}</pre>", parse_mode='HTML')
            return
        bot.reply_to(message_obj, f"✅ <code>{file_name}</code> (Python) စတင်ပြီ (PID: {process.pid})", parse_mode='HTML')
    except Exception as e:
        if log_file and not log_file.closed:
            log_file.close()
        bot.reply_to(message_obj, f"❌ <code>{file_name}</code> အမှား: {str(e)}", parse_mode='HTML')
        with bot_scripts_lock:
            if script_key in bot_scripts: del bot_scripts[script_key]

# ========== JS RUNNER (same but with npm install) ==========
COMMONJS_FALLBACK = {'node-telegram-bot-api': '0.66.0'}

def run_js_script(script_path, script_owner_id, user_folder, file_name, message_obj, attempt=1):
    max_attempts = 3
    if attempt > max_attempts:
        bot.reply_to(message_obj, f"❌ <code>{file_name}</code> စတင်ရာတွင်အမှား", parse_mode='HTML')
        return
    script_key = f"{script_owner_id}_{file_name}"
    logger.info(f"JS Attempt {attempt} to run: {script_path}")
    if not shutil.which("node"):
        bot.reply_to(message_obj, "❌ Node.js မရှိပါ။"); return
    if not shutil.which("npm"):
        bot.reply_to(message_obj, "❌ npm မရှိပါ။"); return
    log_file = None
    try:
        if not os.path.exists(script_path):
            bot.reply_to(message_obj, "❌ ဖိုင်မတွေ့ပါ"); return
        with open(script_path, 'r', encoding='utf-8', errors='ignore') as f:
            script_content = f.read()
        required_modules = set()
        for match in re.finditer(r"require\(['\"]([^'\"]+)['\"]\)", script_content):
            mod = match.group(1)
            if not mod.startswith('./') and not mod.startswith('/'):
                required_modules.add(mod)
        missing = []
        for mod in required_modules:
            mod_path = os.path.join(user_folder, 'node_modules', mod)
            if not os.path.exists(mod_path):
                missing.append(mod)
        if missing:
            bot.reply_to(message_obj, f"📦 Missing modules: <code>{', '.join(missing)}</code>. Installing via npm...", parse_mode='HTML')
            try:
                subprocess.run(["npm", "install", "--save"] + missing, cwd=user_folder, check=False, timeout=120)
                bot.reply_to(message_obj, "✅ Modules installed. Starting script...", parse_mode='HTML')
                time.sleep(1)
            except Exception as e:
                bot.reply_to(message_obj, f"❌ npm install အမှား: {str(e)}", parse_mode='HTML')
                return
        log_file_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        log_file = open(log_file_path, 'w', encoding='utf-8', errors='ignore')
        process = subprocess.Popen(
            ["node", script_path], cwd=user_folder, stdout=log_file, stderr=log_file,
            stdin=subprocess.PIPE, encoding='utf-8', errors='ignore', bufsize=1
        )
        with bot_scripts_lock:
            bot_scripts[script_key] = {
                'process': process, 'log_file': log_file, 'file_name': file_name,
                'chat_id': message_obj.chat.id, 'script_owner_id': script_owner_id,
                'start_time': datetime.now(), 'user_folder': user_folder, 'type': 'js', 'script_key': script_key
            }
        time.sleep(2)
        if process.poll() is not None:
            log_file.flush()
            try:
                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as lf:
                    log_content = lf.read()
            except:
                log_content = ''
            if 'ERR_PACKAGE_PATH_NOT_EXPORTED' in log_content:
                for pkg, fallback_ver in COMMONJS_FALLBACK.items():
                    if pkg in log_content:
                        with bot_scripts_lock:
                            if script_key in bot_scripts: del bot_scripts[script_key]
                        try:
                            bot.reply_to(message_obj, f"🔄 {pkg} CommonJS compatible version ({fallback_ver}) တပ်ဆင်နေသည်...", parse_mode='HTML')
                            subprocess.run(["npm", "install", f"{pkg}@{fallback_ver}", "--save"], cwd=user_folder, check=False, timeout=120)
                            bot.reply_to(message_obj, "✅ တပ်ဆင်ပြီး။ ပြန်စတင်နေသည်...", parse_mode='HTML')
                            time.sleep(1)
                            threading.Thread(target=run_js_script, args=(script_path, script_owner_id, user_folder, file_name, message_obj, attempt+1)).start()
                            return
                        except Exception as e:
                            bot.reply_to(message_obj, f"❌ npm install အမှား: {str(e)}", parse_mode='HTML')
                            return
            with bot_scripts_lock:
                if script_key in bot_scripts: del bot_scripts[script_key]
            err_preview = log_content[-800:] if log_content else ''
            safe_preview = html_module.escape(err_preview)
            bot.reply_to(message_obj, f"❌ <code>{html_module.escape(file_name)}</code> JS error:\n<pre>{safe_preview}</pre>", parse_mode='HTML')
            return
        bot.reply_to(message_obj, f"✅ <code>{file_name}</code> (Node.js) စတင်ပြီ (PID: {process.pid})", parse_mode='HTML')
    except Exception as e:
        if log_file and not log_file.closed:
            log_file.close()
        bot.reply_to(message_obj, f"❌ <code>{file_name}</code> အမှား: {str(e)}", parse_mode='HTML')
        with bot_scripts_lock:
            if script_key in bot_scripts: del bot_scripts[script_key]

def send_log_file(user_id, file_name, chat_id):
    user_folder = get_user_folder(user_id)
    log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
    if os.path.exists(log_path):
        with open(log_path, 'rb') as f:
            bot.send_document(chat_id, f, caption=f"📋 {file_name} - Log ဖိုင်")
        return True
    else:
        bot.send_message(chat_id, f"📭 <code>{file_name}</code> အတွက် Log မရှိပါ", parse_mode='HTML')
        return False

# ========== UI KEYBOARDS ==========
def create_main_menu_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = ['📤 ဖိုင်တင်ရန်', '📁 ကျွန်ုပ်၏ဖိုင်များ', '🔑 Key ဖြည့်ရန်', '✨ အဆင့်မြှင့်ရန်',
               '👤 ကိုယ်ရေးအချက်အလက်', '📊 အခြေအနေ']
    if user_id in admin_ids:
        buttons.append('⚙️ အယ်မင်းအကန့်')
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons): markup.row(buttons[i], buttons[i+1])
        else: markup.row(buttons[i])
    return markup

def create_manage_files_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_files_list = user_files.get(user_id, [])
    if not user_files_list:
        markup.add(types.InlineKeyboardButton("📭 ဖိုင်မရှိပါ", callback_data='no_files'))
    else:
        for file_name, file_type, file_path in user_files_list:
            is_running = is_bot_running(user_id, file_name)
            status_emoji = "🟢" if is_running else "🔴"
            markup.add(types.InlineKeyboardButton(f"{status_emoji} {file_name}", callback_data=f'file_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("⬅️ နောက်သို့", callback_data='back_to_main'))
    return markup

def create_file_management_buttons(user_id, file_name, is_running=True):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if is_running:
        markup.row(types.InlineKeyboardButton("⏸️ ခေတ္တရပ်ရန်", callback_data=f'stop_{user_id}_{file_name}'),
                   types.InlineKeyboardButton("🔄 ပြန်စတင်ရန်", callback_data=f'restart_{user_id}_{file_name}'))
    else:
        markup.row(types.InlineKeyboardButton("▶️ စတင်ရန်", callback_data=f'start_{user_id}_{file_name}'))
    markup.row(types.InlineKeyboardButton("🗑️ ဖျက်ရန်", callback_data=f'delete_{user_id}_{file_name}'),
               types.InlineKeyboardButton("📋 Log ဖိုင်ရယူရန်", callback_data=f'logs_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("📥 ဖိုင်ဒေါင်းလုပ်ရန်", callback_data=f'download_{user_id}_{file_name}'))
    markup.add(types.InlineKeyboardButton("⬅️ နောက်သို့", callback_data='manage_files'))
    return markup

def create_admin_panel_keyboard(user_id=None):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = ['📊 စာရင်းအင်းများ', '👥 အသုံးပြုသူများ', '✨ Pro အသုံးပြုသူများ', '🔄 လည်ပတ်နေသည့်များ',
               '📢 အသိပေးစာ', '🔑 Key ထုတ်ရန်', '🗑️ Key ဖျက်ရန်', '🔢 Key များ',
               '📈 အကန့်အသတ်', '💎 Premium စီမံရန်', '⚙️ ဆက်တင်များ', '🔗 Force Join စီမံရန်',
               '🚫 Ban User', '✅ Unban User']
    if user_id == OWNER_ID:
        buttons = ['➕ အယ်မင်းထည့်ရန်', '➖ အယ်မင်းဖယ်ရှားရန်'] + buttons
    for i in range(0, len(buttons), 2):
        if i+1 < len(buttons): markup.row(buttons[i], buttons[i+1])
        else: markup.row(buttons[i])
    markup.row('⬅️ နောက်သို့')
    return markup

# ========== HELPER ==========
def safe_answer_callback(call, text, show_alert=False):
    try:
        bot.answer_callback_query(call.id, text, show_alert=show_alert)
    except Exception as e:
        logger.warning(f"Callback answer ignored: {e}")

# ========== DATABASE UTILS ==========
def save_user(user_id, username, first_name, last_name):
    conn.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, last_name) VALUES (?,?,?,?)",
                 (user_id, username, first_name, last_name))
    conn.commit()

def save_user_file(user_id, file_name, file_type, file_path):
    conn.execute("INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, file_path) VALUES (?,?,?,?)",
                 (user_id, file_name, file_type, file_path))
    conn.commit()
    if user_id not in user_files:
        user_files[user_id] = []
    user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
    user_files[user_id].append((file_name, file_type, file_path))

def remove_user_file_db(user_id, file_name):
    conn.execute("DELETE FROM user_files WHERE user_id=? AND file_name=?", (user_id, file_name))
    conn.commit()
    if user_id in user_files:
        user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]

def add_active_user(user_id):
    active_users.add(user_id)
    conn.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def update_file_limit(new_limit):
    global FREE_USER_LIMIT
    FREE_USER_LIMIT = new_limit
    conn.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES ('free_user_limit',?)", (str(new_limit),))
    conn.commit()

def update_force_join_status(enabled):
    global force_join_enabled
    force_join_enabled = enabled
    conn.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES ('force_join_enabled',?)", ('1' if enabled else '0',))
    conn.commit()

# ========== BOT HANDLERS ==========
@bot.message_handler(commands=['start', 'help'])
def command_send_welcome(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.send_message(message.chat.id, "🚫 သင်သည် Ban ခံထားရသော အသုံးပြုသူဖြစ်ပါသည်။")
        return
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "🔒 ပြုပြင်ထိန်းသိမ်းချိန်ဖြစ်ပါသည်။")
        return
    save_user(user_id, message.from_user.username, message.from_user.first_name, message.from_user.last_name)
    add_active_user(user_id)
    if is_user_verified(user_id):
        show_main_menu(message, user_id)
        return
    force_message = create_force_join_message()
    force_markup = create_force_join_keyboard()
    bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='HTML')

def show_main_menu(message, user_id):
    sys_stats = get_system_stats()
    status = get_user_status(user_id)
    file_count = get_user_file_count(user_id)
    file_limit = get_user_file_limit(user_id)
    limit_disp = "∞" if file_limit == float('inf') else str(file_limit)
    running = sum(1 for fn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))
    welcome_text = f"""
╔══════════════════════════╗
║   ⚡ <b>KIKI CORE</b> ⚡   ║
║  Universal Cloud Hosting  ║
╚══════════════════════════╝

✨ <b>မင်္ဂလာပါ</b>, {message.from_user.first_name}!

┌──────────────────────────┐
│ 📊 <b>သင့်အခြေအနေ</b>          │
├──────────────────────────┤
│ 👤 အဆင့်: {status}
│ 📁 ဖိုင်များ: {file_count}/{limit_disp}
│ 🟢 အလုပ်လုပ်နေသည်: {running}
│ 🔴 ရပ်နားထား: {file_count - running}
└──────────────────────────┘

🖥 <b>System</b>
├─ CPU: {sys_stats['cpu']}%
├─ RAM: {sys_stats['ram_percent']}% ({sys_stats['ram_used']}/{sys_stats['ram_total']} MB)
└─ ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

🎯 <b>အင်္ဂါရပ်များ:</b>
├─ 🐍 Python 24/7 Run
├─ 🟨 Node.js 24/7 Run
├─ 📦 Auto Module Install (pip/npm)
├─ 📋 Real-time Logging
└─ 👥 Force Join Verification

👇 <b>အောက်ပါခလုတ်များဖြင့် စတင်ပါ</b>
    """
    markup = create_main_menu_keyboard(user_id)
    bot.send_message(message.chat.id, welcome_text, reply_markup=markup, parse_mode='HTML')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.reply_to(message, "🚫 သင်သည် Ban ခံထားရသော အသုံးပြုသူဖြစ်ပါသည်။")
        return
    if bot_locked and user_id not in admin_ids:
        bot.reply_to(message, "🔒 ပြုပြင်ထိန်းသိမ်းချိန်"); return
    if not check_force_join_and_access(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='HTML')
        return
    file_limit = get_user_file_limit(user_id)
    current_files = get_user_file_count(user_id)
    if file_limit != float('inf') and current_files >= file_limit:
        bot.reply_to(message, f"❌ သင့်အတွက် ဖိုင်အကန့်အသတ်မှာ {int(file_limit)} ဖြစ်ပါသည်။"); return
    doc = message.document
    file_name = doc.file_name
    file_ext = os.path.splitext(file_name)[1].lower()
    if file_ext not in SUPPORTED_EXTENSIONS:
        supported_list = ", ".join([f"<code>{ext}</code>" for ext in SUPPORTED_EXTENSIONS.keys()])
        bot.reply_to(message, f"❌ မှားယွင်းသောအမျိုးအစား\nခွင့်ပြုချက်: {supported_list}", parse_mode='HTML'); return
    try:
        file_info = bot.get_file(doc.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        user_folder = get_user_folder(user_id)
        file_path = os.path.join(user_folder, file_name)
        with open(file_path, 'wb') as new_file: new_file.write(downloaded_file)
        file_type = SUPPORTED_EXTENSIONS.get(file_ext, 'အမည်မသိ')
        save_user_file(user_id, file_name, file_type, file_path)
        try:
            bot.forward_message(OWNER_ID, message.chat.id, message.message_id)
            bot.send_message(OWNER_ID, f"📤 ဖိုင်အသစ်\n👤 {message.from_user.first_name}\n📄 <code>{file_name}</code>", parse_mode='HTML')
        except: pass
        success_text = f"✅ <code>{file_name}</code> တင်ပြီးပါပြီ\n📦 {file_type}\n🚀 ဖိုင်ကိုနှိပ်၍ စတင်ရန် ခလုတ်ကိုနှိပ်ပါ"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📁 ဖိုင်များသို့သွားရန်", callback_data='manage_files'))
        bot.reply_to(message, success_text, reply_markup=markup, parse_mode='HTML')
    except Exception as e:
        logger.error(f"File upload error: {e}")
        bot.reply_to(message, f"❌ အမှား: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_text_messages(message):
    user_id = message.from_user.id
    if is_user_banned(user_id):
        bot.send_message(message.chat.id, "🚫 သင်သည် Ban ခံထားရသော အသုံးပြုသူဖြစ်ပါသည်။")
        return
    if bot_locked and user_id not in admin_ids:
        bot.send_message(message.chat.id, "🔒 ပြုပြင်ထိန်းသိမ်းချိန်"); return
    if not check_force_join_and_access(user_id):
        force_message = create_force_join_message()
        force_markup = create_force_join_keyboard()
        bot.send_message(message.chat.id, force_message, reply_markup=force_markup, parse_mode='HTML')
        return
    text = message.text
    if text == '📤 ဖိုင်တင်ရန်':
        bot.send_message(message.chat.id, "📤 သင့် <code>.py</code> သို့မဟုတ် <code>.js</code> ဖိုင်ကိုတင်ပါ", parse_mode='HTML')
    elif text == '📁 ကျွန်ုပ်၏ဖိုင်များ': handle_manage_files(message)
    elif text == '🔑 Key ဖြည့်ရန်':
        msg = bot.send_message(message.chat.id, "🔑 Key ထည့်ပါ (KIKI-XXXXX):")
        bot.register_next_step_handler(msg, process_redeem_key)
    elif text == '✨ အဆင့်မြှင့်ရန်': handle_upgrade(message)
    elif text == '👤 ကိုယ်ရေးအချက်အလက်': handle_my_info(message)
    elif text == '📊 အခြေအနေ': handle_status(message)
    elif text == '⚙️ အယ်မင်းအကန့်' and user_id in admin_ids: handle_admin_panel(message)
    elif text == '📊 စာရင်းအင်းများ' and user_id in admin_ids: handle_stats(message)
    elif text == '👥 အသုံးပြုသူများ' and user_id in admin_ids: handle_all_users(message)
    elif text == '✨ Pro အသုံးပြုသူများ' and user_id in admin_ids: handle_premium_users(message)
    elif text == '🔄 လည်ပတ်နေသည့်များ' and user_id in admin_ids: handle_running_scripts(message)
    elif text == '📢 အသိပေးစာ' and user_id in admin_ids:
        msg = bot.send_message(message.chat.id, "📢 အသိပေးစာထည့်ပါ:")
        bot.register_next_step_handler(msg, process_broadcast)
    elif text == '🔑 Key ထုတ်ရန်' and user_id in admin_ids: handle_generate_key(message)
    elif text == '🗑️ Key ဖျက်ရန်' and user_id in admin_ids: handle_delete_key(message)
    elif text == '🔢 Key များ' and user_id in admin_ids: handle_list_keys(message)
    elif text == '📈 အကန့်အသတ်' and user_id in admin_ids: handle_set_limit(message)
    elif text == '💎 Premium စီမံရန်' and user_id in admin_ids: handle_premium_plan_management(message)
    elif text == '⚙️ ဆက်တင်များ' and user_id in admin_ids: handle_settings(message)
    elif text == '🔗 Force Join စီမံရန်' and user_id in admin_ids: handle_force_join_management(message)
    elif text == '➕ အယ်မင်းထည့်ရန်' and user_id == OWNER_ID:
        msg = bot.send_message(message.chat.id, "👤 အယ်မင်းထည့်ရန် User ID ထည့်ပါ:")
        bot.register_next_step_handler(msg, process_add_admin)
    elif text == '➖ အယ်မင်းဖယ်ရှားရန်' and user_id == OWNER_ID:
        msg = bot.send_message(message.chat.id, "👤 အယ်မင်းဖယ်ရှားရန် User ID ထည့်ပါ:")
        bot.register_next_step_handler(msg, process_remove_admin)
    elif text == '🚫 Ban User' and user_id in admin_ids:
        msg = bot.send_message(message.chat.id, "🚫 Ban လုပ်ရန် User ID ထည့်ပါ:")
        bot.register_next_step_handler(msg, process_ban_user)
    elif text == '✅ Unban User' and user_id in admin_ids:
        msg = bot.send_message(message.chat.id, "✅ Unban လုပ်ရန် User ID ထည့်ပါ:")
        bot.register_next_step_handler(msg, process_unban_user)
    elif text == '⬅️ နောက်သို့':
        markup = create_main_menu_keyboard(user_id)
        bot.send_message(message.chat.id, "🏠 ပင်မစာမျက်နှာ", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "❌ မှားယွင်းသောအကြောင်းအရာ")

def handle_admin_panel(message):
    if message.from_user.id not in admin_ids: return
    admin_text = "⚙️ <b>အယ်မင်းထိန်းချုပ်မှုအကန့်</b>"
    markup = create_admin_panel_keyboard(message.from_user.id)
    bot.send_message(message.chat.id, admin_text, reply_markup=markup, parse_mode='HTML')

# ========== ADMIN HANDLERS ==========
def process_add_admin(message):
    try:
        new_admin_id = int(message.text.strip())
        if new_admin_id in admin_ids:
            bot.send_message(message.chat.id, "⚠️ ထို user သည် အယ်မင်းဖြစ်ပြီးသားပါ။"); return
        admin_ids.add(new_admin_id)
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ အယ်မင်း <code>{new_admin_id}</code> ထည့်ပြီးပါပြီ။", parse_mode='HTML')
    except: bot.send_message(message.chat.id, "❌ မှန်ကန်သော User ID ထည့်ပါ။")

def process_remove_admin(message):
    try:
        admin_id_remove = int(message.text.strip())
        if admin_id_remove == OWNER_ID:
            bot.send_message(message.chat.id, "❌ ပိုင်ရှင်ကို ဖယ်ရှား၍မရပါ။"); return
        if admin_id_remove not in admin_ids:
            bot.send_message(message.chat.id, "⚠️ ထို user သည် အယ်မင်းမဟုတ်ပါ။"); return
        admin_ids.discard(admin_id_remove)
        conn.execute("DELETE FROM admins WHERE user_id=?", (admin_id_remove,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ အယ်မင်း <code>{admin_id_remove}</code> ဖယ်ရှားပြီးပါပြီ။", parse_mode='HTML')
    except: bot.send_message(message.chat.id, "❌ မှန်ကန်သော User ID ထည့်ပါ။")

def process_ban_user(message):
    try:
        target_id = int(message.text.strip())
        success, msg = ban_user(target_id)
        bot.send_message(message.chat.id, msg, parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ မှန်ကန်သော User ID ထည့်ပါ။")

def process_unban_user(message):
    try:
        target_id = int(message.text.strip())
        success, msg = unban_user(target_id)
        bot.send_message(message.chat.id, msg, parse_mode='HTML')
    except:
        bot.send_message(message.chat.id, "❌ မှန်ကန်သော User ID ထည့်ပါ။")

def handle_generate_key(message):
    msg = bot.send_message(message.chat.id, "📅 ရက်အရေအတွက် (-1=တစ်သက်တာ, 1-365):")
    bot.register_next_step_handler(msg, process_key_days)

def process_key_days(message):
    try:
        days = int(message.text.strip())
        if days < -1 or days > 365:
            bot.send_message(message.chat.id, "❌ -1 (တစ်သက်တာ) သို့မဟုတ် 1-365 ကြားထည့်ပါ"); return
        msg = bot.send_message(message.chat.id, "📁 ဖိုင်အကန့်အသတ် (0=အကန့်အသတ်မဲ့):")
        bot.register_next_step_handler(msg, process_key_file_limit, days)
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ")

def process_key_file_limit(message, days):
    try:
        file_limit_text = message.text.strip()
        if file_limit_text.lower() in ['unlimited', '∞', '0']: file_limit = 0
        else: file_limit = int(file_limit_text)
        if file_limit < 0:
            bot.send_message(message.chat.id, "❌ 0 (အကန့်အသတ်မဲ့) သို့မဟုတ် အပေါင်းဂဏန်းထည့်ပါ"); return
        key = generate_subscription_key(days, file_limit)
        limit_display = "အကန့်အသတ်မဲ့" if file_limit == 0 else str(file_limit)
        days_display = "တစ်သက်တာ" if days == -1 else f"{days} ရက်"
        bot.send_message(message.chat.id, f"✅ <b>Key ထုတ်လုပ်ပြီး</b>\n\n🔑 <code>{key}</code>\n📅 {days_display}\n📁 {limit_display} ဖိုင်\n🔢 တစ်ကြိမ်သုံးနိုင်သည်", parse_mode='HTML')
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ (သို့) 0 ထည့်ပါ")

def handle_delete_key(message):
    keys = get_all_subscription_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 Key မရှိပါ"); return
    keys_text = "🗑️ <b>ရှိသော key များ:</b>\n\n"
    for k in keys:
        limit_disp = "∞" if k['file_limit'] == 0 else str(k['file_limit'])
        days_disp = "တစ်သက်တာ" if k['days_valid'] == -1 else f"{k['days_valid']}ရက်"
        keys_text += f"• <code>{k['key_value']}</code> - {days_disp}, သုံးပြီး {k['used_count']}/{k['max_uses']} (file limit: {limit_disp})\n"
    keys_text += "\nဖျက်လိုသော key ထည့်ပါ:"
    bot.send_message(message.chat.id, keys_text, parse_mode='HTML')
    msg = bot.send_message(message.chat.id, "🔑 Key:")
    bot.register_next_step_handler(msg, process_delete_key)

def process_delete_key(message):
    key = message.text.strip().upper()
    delete_subscription_key(key)
    bot.send_message(message.chat.id, f"✅ <code>{key}</code> ဖျက်ပြီး (အသုံးပြုသူများ premium မှ ဖယ်ရှားပြီး)", parse_mode='HTML')

def handle_list_keys(message):
    keys = get_all_subscription_keys()
    if not keys:
        bot.send_message(message.chat.id, "📭 Key မရှိပါ"); return
    text = "🔢 <b>Key များ:</b>\n\n"
    for k in keys:
        limit_disp = "∞" if k['file_limit'] == 0 else str(k['file_limit'])
        days_disp = "တစ်သက်တာ" if k['days_valid'] == -1 else f"{k['days_valid']}ရက်"
        text += f"• <code>{k['key_value']}</code> - {days_disp}, သုံးပြီး {k['used_count']}/{k['max_uses']} (file limit: {limit_disp})\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

def handle_set_limit(message):
    current = FREE_USER_LIMIT
    msg = bot.send_message(message.chat.id, f"📈 လက်ရှိအကန့်အသတ်: {current}\n\nအကန့်အသတ်အသစ် (1-100):")
    bot.register_next_step_handler(msg, process_set_limit)

def process_set_limit(message):
    try:
        new_limit = int(message.text.strip())
        if 1 <= new_limit <= 100:
            update_file_limit(new_limit)
            bot.send_message(message.chat.id, f"✅ အခြေခံအသုံးပြုသူ ဖိုင်အကန့်အသတ်: {new_limit}")
        else: bot.send_message(message.chat.id, "❌ 1-100 ကြားထည့်ပါ")
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ")

def handle_settings(message):
    sys_stats = get_system_stats()
    settings_text = f"""
⚙️ <b>ဆက်တင်များ</b>

🔒 Bot: {'🔒 သော့ခတ်' if bot_locked else '🔓 ဖွင့်'}
🔰 Force Join: {'✅ ဖွင့်' if force_join_enabled else '❌ ပိတ်'}
📁 Free Limit: {FREE_USER_LIMIT}
🖥 CPU: {sys_stats['cpu']}%
💾 RAM: {sys_stats['ram_percent']}%
    """
    markup = types.InlineKeyboardMarkup()
    if message.from_user.id == OWNER_ID:
        if bot_locked: markup.add(types.InlineKeyboardButton("🔓 ဖွင့်ရန်", callback_data='unlock_bot'))
        else: markup.add(types.InlineKeyboardButton("🔒 သော့ခတ်ရန်", callback_data='lock_bot'))
        if force_join_enabled: markup.add(types.InlineKeyboardButton("❌ Force Join ပိတ်ရန်", callback_data='disable_force_join'))
        else: markup.add(types.InlineKeyboardButton("✅ Force Join ဖွင့်ရန်", callback_data='enable_force_join'))
    bot.send_message(message.chat.id, settings_text, reply_markup=markup, parse_mode='HTML')

def handle_force_join_management(message):
    if message.from_user.id not in admin_ids: return
    current_channels = ", ".join(map(str, force_channel_ids)) if force_channel_ids else "မရှိ"
    info = f"""
🔗 <b>Force Join စီမံမှု</b>
📣 လက်ရှိ Channel IDs: <code>{current_channels}</code>
👥 Group ID: <code>{force_group_id}</code>
ပြောင်းလဲရန် Channel IDs များကို comma ခြား၍ ထည့်ပါ (ဥပမာ: -100123,-100456)
    """
    msg = bot.send_message(message.chat.id, info, parse_mode='HTML')
    bot.send_message(message.chat.id, "📣 Channel IDs (comma):")
    bot.register_next_step_handler(msg, process_force_join_channels)

def process_force_join_channels(message):
    try:
        ids = [int(x.strip()) for x in message.text.split(',') if x.strip().lstrip('-').isdigit()]
        if not ids: bot.send_message(message.chat.id, "❌ မှန်ကန်သော ID ထည့်ပါ"); return
        msg = bot.send_message(message.chat.id, "👥 Group ID ထည့်ပါ:")
        bot.register_next_step_handler(msg, process_force_join_group, ids)
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းများသာထည့်ပါ")

def process_force_join_group(message, channel_ids):
    try:
        group_id = int(message.text.strip())
        global force_channel_ids, force_group_id
        force_channel_ids = channel_ids; force_group_id = group_id
        conn.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES ('force_channel_ids',?)", (','.join(map(str, force_channel_ids)),))
        conn.execute("INSERT OR REPLACE INTO bot_settings (setting_key, setting_value) VALUES ('force_group_id',?)", (str(force_group_id),))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Force Join အပ်ဒိတ်လုပ်ပြီး\nChannels: {force_channel_ids}\nGroup: {force_group_id}")
    except: bot.send_message(message.chat.id, "❌ မှန်ကန်သော Group ID ထည့်ပါ")

def handle_running_scripts(message):
    if message.from_user.id not in admin_ids: return
    with bot_scripts_lock:
        scripts_copy = dict(bot_scripts)
    if not scripts_copy:
        bot.send_message(message.chat.id, "🔄 လည်ပတ်နေသော script မရှိပါ"); return
    text = "<b>လည်ပတ်နေသော Scripts:</b>\n\n"
    for key, info in scripts_copy.items():
        uid = info['script_owner_id']; fname = info['file_name']; pid = info['process'].pid if info['process'] else '?'
        lang = '🐍' if info['type'] == 'py' else '🟨'
        try: uname = bot.get_chat(uid).first_name
        except: uname = str(uid)
        text += f"• {lang} <code>{fname}</code> (User: {uname}, PID: {pid})\n"
    bot.send_message(message.chat.id, text, parse_mode='HTML')

def handle_premium_plan_management(message):
    plans = get_all_premium_plans()
    text = "💎 <b>Premium အစီအစဉ်များ</b>\n\n"
    if not plans: text += "အစီအစဉ်မရှိပါ\n"
    else:
        for p in plans:
            plan_id = p['id']; name = p['name']; days = p['days']; price = p['price']; file_limit = p['file_limit']
            days_disp = "တစ်သက်တာ" if days == -1 else f"{days} ရက်"
            file_disp = "∞" if file_limit == 0 else file_limit
            text += f"• ID: {plan_id} - {name} | {days_disp} | {price} Ks | {file_disp} files\n"
    text += "\n<b>Action:</b>"
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("➕ ထည့်ရန်", callback_data='add_premium_plan'),
               types.InlineKeyboardButton("➖ ဖျက်ရန်", callback_data='delete_premium_plan'))
    markup.add(types.InlineKeyboardButton("⬅️ နောက်သို့", callback_data='admin_back'))
    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: call.data == 'add_premium_plan')
def callback_add_premium_plan(call):
    msg = bot.send_message(call.message.chat.id, "💎 Plan အမည် ထည့်ပါ:")
    bot.register_next_step_handler(msg, process_plan_name)

def process_plan_name(message):
    name = message.text.strip()
    msg = bot.send_message(message.chat.id, "📅 ရက်အရေအတွက် (-1=တစ်သက်တာ, 7,30,90,365...):")
    bot.register_next_step_handler(msg, process_plan_days, name)

def process_plan_days(message, name):
    try:
        days = int(message.text.strip())
        msg = bot.send_message(message.chat.id, "💰 စျေးနှုန်း (ကျပ်):")
        bot.register_next_step_handler(msg, process_plan_price, name, days)
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ")

def process_plan_price(message, name, days):
    try:
        price = int(message.text.strip())
        msg = bot.send_message(message.chat.id, "📁 File အကန့်အသတ် (0=အကန့်အသတ်မဲ့):")
        bot.register_next_step_handler(msg, process_plan_filelimit, name, days, price)
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ")

def process_plan_filelimit(message, name, days, price):
    try:
        file_limit = int(message.text.strip())
        if file_limit < 0: bot.send_message(message.chat.id, "❌ 0 သို့မဟုတ် အပေါင်းကိန်း"); return
        add_premium_plan(name, days, price, file_limit)
        bot.send_message(message.chat.id, f"✅ Plan '{name}' ထည့်ပြီး\n{days}ရက်, {price}Ks, File limit: {'∞' if file_limit==0 else file_limit}")
    except: bot.send_message(message.chat.id, "❌ ဂဏန်းထည့်ပါ")

@bot.callback_query_handler(func=lambda call: call.data == 'delete_premium_plan')
def callback_delete_premium_plan(call):
    plans = get_all_premium_plans()
    if not plans:
        safe_answer_callback(call, "ဖျက်ရန် plan မရှိပါ", show_alert=True); return
    plan_list = "💎 <b>Plan ID ထည့်ပါ:</b>\n\n"
    for p in plans:
        plan_list += f"ID: {p['id']} - {p['name']}\n"
    msg = bot.send_message(call.message.chat.id, plan_list, parse_mode='HTML')
    bot.send_message(call.message.chat.id, "Plan ID ထည့်ပါ:")
    bot.register_next_step_handler(msg, process_delete_plan_id)

def process_delete_plan_id(message):
    try:
        plan_id = message.text.strip()
        delete_premium_plan(plan_id)
        bot.send_message(message.chat.id, f"✅ Plan ID {plan_id} ဖျက်ပြီး")
    except: bot.send_message(message.chat.id, "❌ မှန်ကန်သော Plan ID ထည့်ပါ")

# ========== COMMON HANDLERS ==========
def handle_stats(message):
    stats = get_bot_statistics()
    sys_stats = get_system_stats()
    stats_text = f"""
📊 <b>စနစ်စာရင်းအင်းများ</b>
👥 အသုံးပြုသူ: <code>{stats['total_users']}</code>
✨ Pro: <code>{stats['premium_users']}</code>
📁 ဖိုင်များ: <code>{stats['total_files']}</code>
🟢 လည်ပတ်နေသည်: <code>{stats['active_files']}</code>
🖥 <b>Server</b>
├ CPU: {sys_stats['cpu']}%
├ RAM: {sys_stats['ram_percent']}% ({sys_stats['ram_used']}/{sys_stats['ram_total']} MB)
└ ⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    """
    bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

def get_bot_statistics():
    total_users = len(active_users)
    total_files = sum(len(files) for files in user_files.values())
    with bot_scripts_lock:
        active_files = len(bot_scripts)
    premium_users = sum(1 for uid in active_users if is_premium_user(uid))
    return {'total_users': total_users, 'total_files': total_files, 'active_files': active_files, 'premium_users': premium_users}

def handle_all_users(message):
    users = get_all_users_details()
    if not users: bot.send_message(message.chat.id, "📭 အသုံးပြုသူမရှိပါ"); return
    users_text = "👥 <b>အသုံးပြုသူများ:</b>\n\n"
    for user in users[:50]:
        status = "✨" if user['is_premium'] else "🎯"
        username = f"@{user['username']}" if user['username'] else "-"
        ban_info = " [🚫 BANNED]" if user['banned'] else ""
        users_text += f"• {status} {user['first_name']} ({username}){ban_info}\n"
    if len(users) > 50: users_text += f"\n... {len(users) - 50} ဦးကျန်သည်"
    bot.send_message(message.chat.id, users_text, parse_mode='HTML')

def get_all_users_details():
    users_list = []
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, banned FROM users")
    for row in c:
        uid, username, first_name, banned = row
        users_list.append({'user_id': uid, 'first_name': first_name or 'Unknown', 'username': username or 'Unknown',
                           'is_premium': is_premium_user(uid), 'banned': bool(banned)})
    return users_list

def handle_premium_users(message):
    premium_list = []
    for uid in active_users:
        if is_premium_user(uid):
            try: chat = bot.get_chat(uid); premium_list.append(f"• {chat.first_name} (@{chat.username or '-'})")
            except: premium_list.append(f"• User {uid}")
    if not premium_list: bot.send_message(message.chat.id, "📭 Pro အသုံးပြုသူမရှိပါ")
    else: bot.send_message(message.chat.id, "✨ <b>Pro အသုံးပြုသူများ:</b>\n\n" + "\n".join(premium_list), parse_mode='HTML')

def process_broadcast(message):
    broadcast_msg = message.text
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ ပို့ရန်", callback_data=f'confirm_broadcast_{message.message_id}'),
               types.InlineKeyboardButton("❌ ပယ်ဖျက်ရန်", callback_data='cancel_broadcast'))
    broadcast_messages[message.message_id] = broadcast_msg
    bot.send_message(message.chat.id, f"📢 <b>အကြိုကြည့်ရှုခြင်း:</b>\n\n{broadcast_msg}\n\nအသုံးပြုသူအားလုံးသို့ပို့မည်?", reply_markup=markup, parse_mode='HTML')

def handle_upgrade(message):
    plans = get_all_premium_plans()
    if not plans: bot.send_message(message.chat.id, "💎 လောလောဆယ် premium plan မရှိသေးပါ။ admin ထံဆက်သွယ်ပါ။"); return
    plans_text = "💎 <b>Premium အစီအစဉ်များ</b>\n\n"
    for p in plans:
        name = p['name']; days = p['days']; price = p['price']; file_limit = p['file_limit']
        days_disp = "တစ်သက်တာ" if days == -1 else f"{days} ရက်"
        file_disp = "∞" if file_limit == 0 else file_limit
        plans_text += f"• <b>{name}</b>: {price} Ks | {days_disp} | File: {file_disp}\n"
    plans_text += f"\n💳 ငွေပေးချေမှု: KPAY, WAVE\n📲 ဆက်သွယ်ရန်: {ADMIN_USERNAME}"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 ဆက်သွယ်ရန်", url=f"https://t.me/{ADMIN_USERNAME.lstrip('@')}"))
    markup.add(types.InlineKeyboardButton("🔑 Key ရှိပြီးသား", callback_data='redeem_key'))
    bot.send_message(message.chat.id, plans_text, reply_markup=markup, parse_mode='HTML')

def handle_my_info(message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    file_count = get_user_file_count(user_id)
    file_limit = get_user_file_limit(user_id)
    limit_str = "∞" if file_limit == float('inf') else str(int(file_limit))
    running = sum(1 for fn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))
    sys_stats = get_system_stats()
    info_text = f"""
👤 <b>ကိုယ်ရေးအချက်အလက်</b>
🆔 ID: <code>{user_id}</code>
👤 အမည်: {message.from_user.first_name}
📊 အဆင့်: {status}
📁 <b>ဖိုင်အချက်အလက်</b>
├─ စုစုပေါင်း: {file_count}/{limit_str}
├─ 🟢 လည်ပတ်နေသည်: {running}
└─ 🔴 ရပ်ထား: {file_count - running}
🖥 System: CPU {sys_stats['cpu']}% | RAM {sys_stats['ram_percent']}%
    """
    markup = types.InlineKeyboardMarkup(); markup.add(types.InlineKeyboardButton("📁 ဖိုင်များ", callback_data='manage_files'))
    bot.send_message(message.chat.id, info_text, reply_markup=markup, parse_mode='HTML')

def handle_status(message):
    user_id = message.from_user.id
    status = get_user_status(user_id)
    file_count = get_user_file_count(user_id)
    file_limit = get_user_file_limit(user_id)
    limit_str = "∞" if file_limit == float('inf') else str(int(file_limit))
    running = sum(1 for fn, _, _ in user_files.get(user_id, []) if is_bot_running(user_id, fn))
    sys_stats = get_system_stats()
    stats_text = f"""
📊 <b>သင့်အခြေအနေ</b>
👤 အဆင့်: {status}
📁 ဖိုင်များ: {file_count}/{limit_str}
🟢 လည်ပတ်နေသည်: {running}
🔴 ရပ်ထား: {file_count - running}
🖥 CPU: {sys_stats['cpu']}% | RAM: {sys_stats['ram_percent']}%
    """
    bot.send_message(message.chat.id, stats_text, parse_mode='HTML')

def handle_manage_files(message):
    user_id = message.from_user.id
    user_files_list = user_files.get(user_id, [])
    if not user_files_list: bot.send_message(message.chat.id, "📭 ဖိုင်မရှိပါ"); return
    files_text = "📁 <b>သင့်ဖိုင်များ:</b>\n\n"
    for file_name, file_type, file_path in user_files_list:
        status = "🟢" if is_bot_running(user_id, file_name) else "🔴"
        files_text += f"{status} <code>{file_name}</code>\n"
    files_text += "\nစီမံရန်ဖိုင်ကိုနှိပ်ပါ"
    markup = create_manage_files_keyboard(user_id)
    bot.send_message(message.chat.id, files_text, reply_markup=markup, parse_mode='HTML')

def process_redeem_key(message):
    user_id = message.from_user.id
    key = message.text.strip().upper()
    if not key.startswith('KIKI-'):
        bot.reply_to(message, "❌ ပုံစံ: <code>KIKI-XXXXX</code>", parse_mode='HTML'); return
    success, msg = redeem_subscription_key(key, user_id)
    bot.reply_to(message, msg, parse_mode='HTML')

# ========== CALLBACK HELPERS ==========
def parse_callback_data(data, prefix):
    try:
        without_prefix = data[len(prefix):]
        underscore_pos = without_prefix.index('_')
        user_id_str = without_prefix[:underscore_pos]
        file_name = without_prefix[underscore_pos+1:]
        return int(user_id_str), file_name
    except:
        return None, None

# ========== MAIN CALLBACK HANDLER ==========
@bot.callback_query_handler(func=lambda call: call.data not in ('add_premium_plan', 'delete_premium_plan'))
def handle_callbacks(call):
    user_id = call.from_user.id
    if is_user_banned(user_id):
        safe_answer_callback(call, "🚫 Ban ခံထားရသည်", show_alert=True)
        return
    data = call.data

    if data == 'check_membership':
        if user_id in admin_ids:
            safe_answer_callback(call, "✅ အယ်မင်းအခွင့်အရေး"); show_main_menu(call.message, user_id); return
        if verify_membership(user_id):
            safe_answer_callback(call, "✅ အတည်ပြုပြီး"); show_main_menu(call.message, user_id)
        else: safe_answer_callback(call, "❌ အုပ်စုနှင့် ချန်နယ်အားလုံးဝင်ပါ", show_alert=True)

    elif data == 'manage_files': handle_manage_files_callback(call)
    elif data == 'back_to_main': show_main_menu(call.message, user_id)
    elif data.startswith('file_'): handle_file_click(call)
    elif data.startswith('start_'): handle_start_file(call)
    elif data.startswith('stop_'): handle_stop_file(call)
    elif data.startswith('restart_'): handle_restart_file(call)
    elif data.startswith('delete_') and not data == 'delete_premium_plan': handle_delete_file_callback(call)
    elif data.startswith('logs_'): handle_logs_callback(call)
    elif data.startswith('download_'): handle_download_callback(call)
    elif data == 'redeem_key':
        msg = bot.send_message(call.message.chat.id, "🔑 Key ထည့်ပါ (KIKI-XXXXX):")
        bot.register_next_step_handler(msg, process_redeem_key)
    elif data.startswith('confirm_broadcast_'): handle_confirm_broadcast(call)
    elif data == 'cancel_broadcast':
        try: bot.delete_message(call.message.chat.id, call.message.message_id)
        except: pass
        safe_answer_callback(call, "ပယ်ဖျက်ပြီး")
    elif data == 'lock_bot':
        if user_id == OWNER_ID:
            global bot_locked
            bot_locked = True
            safe_answer_callback(call, "🔒 သော့ခတ်ထား"); handle_settings(call.message)
    elif data == 'unlock_bot':
        if user_id == OWNER_ID:
            bot_locked = False
            safe_answer_callback(call, "🔓 ဖွင့်ထား"); handle_settings(call.message)
    elif data == 'enable_force_join':
        if user_id == OWNER_ID: update_force_join_status(True); safe_answer_callback(call, "✅ Force Join ဖွင့်ထား"); handle_settings(call.message)
    elif data == 'disable_force_join':
        if user_id == OWNER_ID: update_force_join_status(False); safe_answer_callback(call, "❌ Force Join ပိတ်ထား"); handle_settings(call.message)
    elif data == 'admin_back': handle_admin_panel(call.message)

def handle_manage_files_callback(call):
    user_id = call.from_user.id
    if not check_force_join_and_access(user_id): safe_answer_callback(call, "⛔ ဝင်ခွင့်မရှိပါ", show_alert=True); return
    user_files_list = user_files.get(user_id, [])
    if not user_files_list: safe_answer_callback(call, "📭 ဖိုင်မရှိပါ", show_alert=True); return
    files_text = "📁 <b>သင့်ဖိုင်များ:</b>\n\n"
    for file_name, file_type, file_path in user_files_list:
        status = "🟢" if is_bot_running(user_id, file_name) else "🔴"
        files_text += f"{status} <code>{file_name}</code>\n"
    files_text += "\nစီမံရန်ဖိုင်ကိုနှိပ်ပါ"
    markup = create_manage_files_keyboard(user_id)
    try: bot.edit_message_text(files_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
    except: bot.send_message(call.message.chat.id, files_text, reply_markup=markup, parse_mode='HTML')

def handle_file_click(call):
    try:
        target_id, file_name = parse_callback_data(call.data, 'file_')
        if target_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        if call.from_user.id != target_id and call.from_user.id not in admin_ids:
            safe_answer_callback(call, "❌ ငြင်းပယ်သည်", show_alert=True); return
        if not check_force_join_and_access(target_id): safe_answer_callback(call, "⛔ ဝင်ခွင့်မရှိပါ", show_alert=True); return
        is_running = is_bot_running(target_id, file_name)
        file_ext = os.path.splitext(file_name)[1].lower()
        lang_icon = "🐍" if file_ext == '.py' else "🟨" if file_ext == '.js' else "📄"
        file_text = f"{lang_icon} <b>{html_module.escape(file_name)}</b>\n\n📊 {'🟢 လည်ပတ်နေသည်' if is_running else '🔴 ရပ်ထားသည်'}"
        markup = create_file_management_buttons(target_id, file_name, is_running)
        try: bot.edit_message_text(file_text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode='HTML')
        except: bot.send_message(call.message.chat.id, file_text, reply_markup=markup, parse_mode='HTML')
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_start_file(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'start_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            safe_answer_callback(call, "❌ ငြင်းပယ်သည်", show_alert=True); return
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name: file_path = fp; break
        if not file_path or not os.path.exists(file_path): safe_answer_callback(call, "❌ မတွေ့ပါ", show_alert=True); return
        user_folder = get_user_folder(user_id)
        file_ext = os.path.splitext(file_name)[1].lower()
        if file_ext == '.py': threading.Thread(target=run_python_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
        elif file_ext == '.js': threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
        else: safe_answer_callback(call, "❌ မသိ ဖိုင်အမျိုးအစား", show_alert=True); return
        safe_answer_callback(call, "🚀 စတင်နေသည်...")
        time.sleep(4)
        call.data = f'file_{user_id}_{file_name}'
        handle_file_click(call)
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_stop_file(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'stop_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        script_key = f"{user_id}_{file_name}"
        with bot_scripts_lock:
            script_info = bot_scripts.get(script_key)
        if script_info: kill_process_tree(script_info)
        with bot_scripts_lock:
            if script_key in bot_scripts: del bot_scripts[script_key]
        safe_answer_callback(call, "⏸️ ရပ်နားထားသည်")
        time.sleep(1)
        call.data = f'file_{user_id}_{file_name}'
        handle_file_click(call)
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_restart_file(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'restart_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        script_key = f"{user_id}_{file_name}"
        with bot_scripts_lock:
            script_info = bot_scripts.get(script_key)
        if script_info: kill_process_tree(script_info)
        with bot_scripts_lock:
            if script_key in bot_scripts: del bot_scripts[script_key]
        time.sleep(1)
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name: file_path = fp; break
        if file_path and os.path.exists(file_path):
            user_folder = get_user_folder(user_id)
            file_ext = os.path.splitext(file_name)[1].lower()
            if file_ext == '.py': threading.Thread(target=run_python_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            elif file_ext == '.js': threading.Thread(target=run_js_script, args=(file_path, user_id, user_folder, file_name, call.message)).start()
            safe_answer_callback(call, "🔄 ပြန်စတင်နေသည်...")
        else: safe_answer_callback(call, "❌ မတွေ့ပါ", show_alert=True)
        time.sleep(4)
        call.data = f'file_{user_id}_{file_name}'
        handle_file_click(call)
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_delete_file_callback(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'delete_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            safe_answer_callback(call, "❌ ငြင်းပယ်သည်", show_alert=True); return
        script_key = f"{user_id}_{file_name}"
        with bot_scripts_lock:
            script_info = bot_scripts.get(script_key)
        if script_info: kill_process_tree(script_info)
        with bot_scripts_lock:
            if script_key in bot_scripts: del bot_scripts[script_key]
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name: file_path = fp; break
        if file_path and os.path.exists(file_path): os.remove(file_path)
        remove_user_file_db(user_id, file_name)
        safe_answer_callback(call, "🗑️ ဖျက်ပြီး")
        handle_manage_files_callback(call)
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_logs_callback(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'logs_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        if send_log_file(user_id, file_name, call.message.chat.id): safe_answer_callback(call, "📋 Log ဖိုင်ပို့ပြီး")
        else: safe_answer_callback(call, "📭 Log မရှိပါ", show_alert=True)
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_download_callback(call):
    try:
        user_id, file_name = parse_callback_data(call.data, 'download_')
        if user_id is None: safe_answer_callback(call, "❌ ဒေတာမှား", show_alert=True); return
        if call.from_user.id != user_id and call.from_user.id not in admin_ids:
            safe_answer_callback(call, "❌ ငြင်းပယ်သည်", show_alert=True); return
        file_path = None
        for fn, ft, fp in user_files.get(user_id, []):
            if fn == file_name: file_path = fp; break
        if not file_path or not os.path.exists(file_path): safe_answer_callback(call, "❌ ဖိုင်မတွေ့ပါ", show_alert=True); return
        with open(file_path, 'rb') as f: bot.send_document(call.message.chat.id, f, caption=f"📥 {file_name}")
        safe_answer_callback(call, "📥 ဖိုင်ပို့ပြီး")
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

def handle_confirm_broadcast(call):
    if call.from_user.id not in admin_ids: safe_answer_callback(call, "❌ အယ်မင်းသာလျှင်", show_alert=True); return
    try:
        msg_id = int(call.data.split('_')[-1])
        broadcast_text = broadcast_messages.get(msg_id, "")
        if not broadcast_text: safe_answer_callback(call, "❌ စာမတွေ့ပါ"); return
        sent = 0; failed = 0
        for uid in list(active_users):
            if is_user_banned(uid):
                continue  # skip banned users
            try: bot.send_message(uid, broadcast_text, parse_mode='HTML'); sent += 1; time.sleep(0.05)
            except: failed += 1
        safe_answer_callback(call, f"✅ ပို့ပြီး: {sent}, မပို့ရ: {failed}")
        try: bot.edit_message_text(f"📢 ပြီးဆုံးပါပြီ\n✅ {sent}\n❌ {failed}", call.message.chat.id, call.message.message_id)
        except: pass
        if msg_id in broadcast_messages: del broadcast_messages[msg_id]
    except Exception as e: safe_answer_callback(call, f"❌ {str(e)}")

# ========== CLEANUP ==========
def cleanup():
    logger.warning("🛑 Shutting down...")
    with bot_scripts_lock:
        scripts_copy = dict(bot_scripts)
    for script_key in list(scripts_copy.keys()):
        kill_process_tree(scripts_copy[script_key])
    if conn:
        conn.close()
atexit.register(cleanup)

# ========== MAIN ==========
if __name__ == '__main__':
    logger.info("""
╔════════════════════════════╗
║   🚀 KiKi X CORE 🚀     ║
║      SYSTEM ONLINE         ║
║   Ready For Requests...    ║
╚════════════════════════════╝
""")
    keep_alive()
    node_installed = install_nodejs()
    if not node_installed: logger.warning("⚠️ Node.js/npm not available.")
    for ch_id in force_channel_ids: get_or_create_invite_link(ch_id)
    get_or_create_invite_link(force_group_id)
    while True:
        try: bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e: logger.error(f"❌ Polling error: {e}"); time.sleep(5)



