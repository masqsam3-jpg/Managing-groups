"""
╔══════════════════════════════════════════════════════════════╗
║       🤖 بوت إدارة المجموعات المتكامل v3.0 - أزرار 🤖       ║
║                                                              ║
║  بوت احترافي لإدارة مجموعات التيليجرام بواجهة أزرار كاملة    ║
║  مطور بواسطة: @masqsam3                                      ║
╚══════════════════════════════════════════════════════════════╝
"""

import logging
import os
import re
import sqlite3
import threading
import time
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ChatMemberStatus

# ═══════════════════════════════════════════════════════════════
# إعداد السجلات
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# الإعدادات العامة
# ═══════════════════════════════════════════════════════════════
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = 894759993  # معرف المالك
WARN_LIMIT = 3
DEFAULT_WELCOME = "مرحباً بك يا {user} في مجموعتنا! 🎉\nيرجى قراءة القوانين"
DB_PATH = "bot_database.db"

# ═══════════════════════════════════════════════════════════════
# خادم Flask
# ═══════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return jsonify({"status": "running", "bot": "Group Manager v3.0", "uptime": True}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ═══════════════════════════════════════════════════════════════
# نظام قاعدة البيانات SQLite
# ═══════════════════════════════════════════════════════════════
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_msg TEXT DEFAULT '{}',
            rules TEXT DEFAULT '',
            maintenance_mode INTEGER DEFAULT 0,
            log_channel_id INTEGER DEFAULT 0,
            anti_spam INTEGER DEFAULT 1,
            anti_flood INTEGER DEFAULT 1,
            anti_link INTEGER DEFAULT 0,
            anti_badword INTEGER DEFAULT 1,
            report_enabled INTEGER DEFAULT 1,
            max_flood_msgs INTEGER DEFAULT 5,
            flood_interval INTEGER DEFAULT 5,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, user_id INTEGER, reason TEXT DEFAULT '',
            warned_by INTEGER, warned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, user_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS warning_counts (
            chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
            PRIMARY KEY(chat_id, user_id)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, name TEXT, content TEXT, created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, name)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, keyword TEXT, reply TEXT, created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, keyword)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS locks (
            chat_id INTEGER, lock_type TEXT, locked_by INTEGER,
            locked_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (chat_id, lock_type)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS badwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, word TEXT, added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, word)
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER PRIMARY KEY,
            total_messages INTEGER DEFAULT 0, total_joins INTEGER DEFAULT 0,
            total_leaves INTEGER DEFAULT 0, total_bans INTEGER DEFAULT 0,
            total_mutes INTEGER DEFAULT 0, total_warns INTEGER DEFAULT 0,
            total_deleted INTEGER DEFAULT 0, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS temp_mutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, user_id INTEGER, muted_by INTEGER,
            mute_until TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER, user_id INTEGER, action TEXT,
            target_id INTEGER DEFAULT 0, reason TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.commit()
        conn.close()

    def get_settings(self, chat_id: int) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM group_settings WHERE chat_id = ?", (chat_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        self._create_settings(chat_id)
        return self.get_settings(chat_id)

    def _create_settings(self, chat_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
        conn.commit()
        conn.close()

    def update_setting(self, chat_id: int, key: str, value):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute(f"UPDATE group_settings SET {key} = ? WHERE chat_id = ?", (value, chat_id))
        conn.commit()
        conn.close()

    def add_warning(self, chat_id: int, user_id: int, reason: str, warned_by: int) -> int:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO warnings (chat_id, user_id, reason, warned_by) VALUES (?, ?, ?, ?)",
                 (chat_id, user_id, reason, warned_by))
        c.execute("INSERT INTO warning_counts (chat_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1",
                 (chat_id, user_id))
        c.execute("SELECT count FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        count = c.fetchone()[0]
        conn.commit()
        conn.close()
        return count

    def get_warning_count(self, chat_id: int, user_id: int) -> int:
        conn = self._get_conn()
        c = conn.cursor()
        try:
            c.execute("SELECT count FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row[0] if row else 0
        except:
            conn.close()
            return 0

    def reset_warnings(self, chat_id: int, user_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        try: c.execute("DELETE FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        except: pass
        conn.commit()
        conn.close()

    def save_note(self, chat_id, name, content, user_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO notes (chat_id, name, content, created_by) VALUES (?, ?, ?, ?)", (chat_id, name, content, user_id))
        conn.commit(); conn.close()

    def get_note(self, chat_id, name):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT content FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
        row = c.fetchone(); conn.close()
        return row[0] if row else None

    def get_all_notes(self, chat_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT name FROM notes WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall(); conn.close()
        return [row[0] for row in rows]

    def delete_note(self, chat_id, name):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("DELETE FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
        d = c.rowcount > 0; conn.commit(); conn.close(); return d

    def save_filter(self, chat_id, keyword, reply, user_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO filters (chat_id, keyword, reply, created_by) VALUES (?, ?, ?, ?)", (chat_id, keyword, reply, user_id))
        conn.commit(); conn.close()

    def get_filter(self, chat_id, keyword):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT reply FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
        row = c.fetchone(); conn.close()
        return row[0] if row else None

    def get_all_filters(self, chat_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT keyword FROM filters WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall(); conn.close()
        return [row[0] for row in rows]

    def delete_filter(self, chat_id, keyword):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("DELETE FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
        d = c.rowcount > 0; conn.commit(); conn.close(); return d

    def lock_type(self, chat_id, lock_type, user_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO locks (chat_id, lock_type, locked_by) VALUES (?, ?, ?)", (chat_id, lock_type, user_id))
        conn.commit(); conn.close()

    def unlock_type(self, chat_id, lock_type):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("DELETE FROM locks WHERE chat_id = ? AND lock_type = ?", (chat_id, lock_type))
        d = c.rowcount > 0; conn.commit(); conn.close(); return d

    def get_all_locks(self, chat_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT lock_type FROM locks WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall(); conn.close()
        return [row[0] for row in rows]

    def add_badword(self, chat_id, word, user_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO badwords (chat_id, word, added_by) VALUES (?, ?, ?)", (chat_id, word, user_id))
        conn.commit(); conn.close()

    def remove_badword(self, chat_id, word):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("DELETE FROM badwords WHERE chat_id = ? AND word = ?", (chat_id, word))
        d = c.rowcount > 0; conn.commit(); conn.close(); return d

    def get_badwords(self, chat_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT word FROM badwords WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall(); conn.close()
        return [row[0] for row in rows]

    def increment_stat(self, chat_id, stat):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO group_stats (chat_id) VALUES (?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
        c.execute(f"UPDATE group_stats SET {stat} = {stat} + 1, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?", (chat_id,))
        conn.commit(); conn.close()

    def get_stats(self, chat_id):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM group_stats WHERE chat_id = ?", (chat_id,))
        row = c.fetchone(); conn.close()
        return dict(row) if row else {}

    def add_temp_mute(self, chat_id, user_id, muted_by, mute_until):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO temp_mutes (chat_id, user_id, muted_by, mute_until) VALUES (?, ?, ?, ?)", (chat_id, user_id, muted_by, mute_until))
        conn.commit(); conn.close()

    def get_expired_mutes(self):
        conn = self._get_conn(); c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT * FROM temp_mutes WHERE mute_until <= ?", (now,))
        rows = c.fetchall()
        c.execute("DELETE FROM temp_mutes WHERE mute_until <= ?", (now,))
        conn.commit(); conn.close()
        return [dict(row) for row in rows]

    def log_action(self, chat_id, user_id, action, target_id=0, reason=""):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("INSERT INTO action_log (chat_id, user_id, action, target_id, reason) VALUES (?, ?, ?, ?, ?)", (chat_id, user_id, action, target_id, reason))
        conn.commit(); conn.close()

    def get_action_log(self, chat_id, limit=10):
        conn = self._get_conn(); c = conn.cursor()
        c.execute("SELECT * FROM action_log WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))
        rows = c.fetchall(); conn.close()
        return [dict(row) for row in rows]


db = Database(DB_PATH)

# ═══════════════════════════════════════════════════════════════
# ثوابت
# ═══════════════════════════════════════════════════════════════
LOCK_TYPES = {
    "photos": "الصور 📷", "videos": "الفيديو 🎬", "stickers": "الملصقات 🎭",
    "animations": "ال GIF 🎞️", "voice": "الصوتية 🎤", "audio": "الصوت 🎵",
    "documents": "الملفات 📄", "links": "الروابط 🔗", "forward": "إعادة التوجيه ↗️",
    "inline": "الإنلاين ⚡", "polls": "الاستفتاءات 📊", "contacts": "جهات الاتصال 📱",
    "location": "الموقع 📍", "venue": "الأماكن 🏢", "text": "النصوص ✏️", "bots": "البوتات 🤖",
}

MUTE_TIMES = [
    ("1 دقيقة", "1m"), ("5 دقائق", "5m"), ("10 دقائق", "10m"),
    ("30 دقيقة", "30m"), ("1 ساعة", "1h"), ("6 ساعات", "6h"),
    ("12 ساعة", "12h"), ("1 يوم", "1d"), ("3 أيام", "3d"), ("7 أيام", "7d"),
]

# ═══════════════════════════════════════════════════════════════
# نظام الفلود
# ═══════════════════════════════════════════════════════════════
flood_data = {}

def check_flood(chat_id, user_id, max_msgs=5, interval=5):
    now = time.time()
    if chat_id not in flood_data: flood_data[chat_id] = {}
    if user_id not in flood_data[chat_id]: flood_data[chat_id][user_id] = []
    flood_data[chat_id][user_id].append(now)
    flood_data[chat_id][user_id] = [t for t in flood_data[chat_id][user_id] if now - t <= interval]
    return len(flood_data[chat_id][user_id]) > max_msgs

# ═══════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════
async def is_admin(update: Update, user_id: int = None) -> bool:
    try:
        if user_id is None: user_id = update.effective_user.id
        if user_id == OWNER_ID: return True
        admins = await update.effective_chat.get_administrators()
        return user_id in [a.user.id for a in admins]
    except: return False

async def is_bot_admin(update: Update) -> bool:
    try:
        m = await update.effective_chat.get_member(update.message.bot.id)
        return m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except: return False

def mention(user_id, name):
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def parse_time(time_str):
    if not time_str: return 0
    time_str = time_str.lower().strip()
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    match = re.match(r'^(\d+)([smhd])$', time_str)
    if match: return int(match.group(1)) * units[match.group(2)]
    try: return int(time_str) * 60
    except: return 0

def format_time(seconds):
    if seconds >= 86400: return f"{seconds // 86400} يوم"
    elif seconds >= 3600: return f"{seconds // 3600} ساعة"
    elif seconds >= 60: return f"{seconds // 60} دقيقة"
    else: return f"{seconds} ثانية"

async def send_log(chat_id, text, context):
    settings = db.get_settings(chat_id)
    log_channel = settings.get('log_channel_id', 0)
    if log_channel and log_channel != 0:
        try: await context.bot.send_message(chat_id=log_channel, text=text, parse_mode="HTML")
        except: pass

# ═══════════════════════════════════════════════════════════════
# نظام اللوحات (Keyboards) - كل شيء أزرار
# ═══════════════════════════════════════════════════════════════

def kb_main():
    """القائمة الرئيسية"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡️ الإشراف", callback_data="menu_admin"),
         InlineKeyboardButton("📌 المحتوى", callback_data="menu_content")],
        [InlineKeyboardButton("📝 الملاحظات", callback_data="menu_notes"),
         InlineKeyboardButton("🔍 الفلاتر", callback_data="menu_filters")],
        [InlineKeyboardButton("🔒 الأقفال", callback_data="menu_locks"),
         InlineKeyboardButton("🔤 الكلمات", callback_data="menu_badwords")],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings"),
         InlineKeyboardButton("📊 المعلومات", callback_data="menu_info")],
        [InlineKeyboardButton("🚨 أخرى", callback_data="menu_other"),
         InlineKeyboardButton("👤 المالك", url="https://t.me/masqsam3")]
    ])

def kb_back():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]])

def kb_back_cancel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back"),
         InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]
    ])

def kb_admin():
    """أزرار الإشراف"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 حظر", callback_data="act_ban"),
         InlineKeyboardButton("✅ إلغاء حظر", callback_data="act_unban")],
        [InlineKeyboardButton("🔇 كتم", callback_data="act_mute"),
         InlineKeyboardButton("🔊 إلغاء كتم", callback_data="act_unmute")],
        [InlineKeyboardButton("⏱️ كتم مؤقت", callback_data="act_tmute"),
         InlineKeyboardButton("👢 طرد", callback_data="act_kick")],
        [InlineKeyboardButton("⚠️ تحذير", callback_data="act_warn"),
         InlineKeyboardButton("✅ إزالة تحذير", callback_data="act_unwarn")],
        [InlineKeyboardButton("🗑️ حذف رسالة", callback_data="act_del"),
         InlineKeyboardButton("🗑️ حذف متعدد", callback_data="act_purge")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_mute_time(target_id):
    """أزرار اختيار مدة الكتم"""
    buttons = []
    row = []
    for label, val in MUTE_TIMES:
        row.append(InlineKeyboardButton(label, callback_data=f"tmute_{target_id}_{val}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_admin")])
    return InlineKeyboardMarkup(buttons)

def kb_content():
    """أزرار المحتوى"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 تثبيت رسالة", callback_data="act_pin"),
         InlineKeyboardButton("📌 إلغاء التثبيت", callback_data="act_unpin")],
        [InlineKeyboardButton("📋 تعيين القوانين", callback_data="act_setrules"),
         InlineKeyboardButton("📋 عرض القوانين", callback_data="act_rules")],
        [InlineKeyboardButton("📋 حذف القوانين", callback_data="act_clearrules")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_notes():
    """أزرار الملاحظات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 حفظ ملاحظة", callback_data="act_savenote"),
         InlineKeyboardButton("📖 استرجاع ملاحظة", callback_data="act_getnote")],
        [InlineKeyboardButton("📋 عرض الكل", callback_data="act_allnotes"),
         InlineKeyboardButton("🗑️ حذف ملاحظة", callback_data="act_delnote")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_notes_list(chat_id):
    """أزرار قائمة الملاحظات"""
    notes = db.get_all_notes(chat_id)
    if not notes:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_notes")]])
    buttons = []
    for name in notes:
        buttons.append([InlineKeyboardButton(f"📝 {name}", callback_data=f"note_{name}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_notes")])
    return InlineKeyboardMarkup(buttons)

def kb_filters():
    """أزرار الفلاتر"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة فلتر", callback_data="act_addfilter"),
         InlineKeyboardButton("➖ حذف فلتر", callback_data="act_delfilter")],
        [InlineKeyboardButton("📋 عرض الفلاتر", callback_data="act_allfilters")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_locks():
    """أزرار الأقفال"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔒 قفل الكل", callback_data="act_lockall"),
         InlineKeyboardButton("🔓 فتح الكل", callback_data="act_unlockall")],
        [InlineKeyboardButton("📋 عرض الأقفال", callback_data="act_showlocks")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_lock_types(chat_id):
    """أزرار أنواع الأقفال"""
    locked = db.get_all_locks(chat_id)
    buttons = []
    row = []
    for key, name in LOCK_TYPES.items():
        icon = "🔒" if key in locked else "🔓"
        row.append(InlineKeyboardButton(f"{icon} {name}", callback_data=f"lock_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_locks")])
    return InlineKeyboardMarkup(buttons)

def kb_badwords():
    """أزرار الكلمات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data="act_addbadword"),
         InlineKeyboardButton("➖ حذف كلمة", callback_data="act_delbadword")],
        [InlineKeyboardButton("📋 عرض الكلمات", callback_data="act_showbadwords")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_settings(chat_id):
    """أزرار الإعدادات مع حالة كل واحد"""
    s = db.get_settings(chat_id)
    buttons = [
        [InlineKeyboardButton(f"{'✅' if s.get('anti_flood',1) else '❌'} حماية الفلود", callback_data="tog_flood"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_spam',1) else '❌'} حماية السبام", callback_data="tog_spam")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_link',0) else '❌'} منع الروابط", callback_data="tog_link"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_badword',1) else '❌'} فلتر الكلمات", callback_data="tog_badword")],
        [InlineKeyboardButton(f"{'✅' if s.get('maintenance_mode',0) else '❌'} وضع الصيانة", callback_data="tog_maintenance"),
         InlineKeyboardButton(f"{'✅' if s.get('report_enabled',1) else '❌'} البلاغات", callback_data="tog_report")],
        [InlineKeyboardButton("💬 تعيين الترحيب", callback_data="act_setwelcome"),
         InlineKeyboardButton("🔄 ترحيب افتراضي", callback_data="act_resetwelcome")],
        [InlineKeyboardButton("📝 قناة السجلات", callback_data="act_setlog")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_info():
    """أزرار المعلومات"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 معلومات مستخدم", callback_data="act_userinfo"),
         InlineKeyboardButton("📊 إحصائيات المجموعة", callback_data="act_groupstats")],
        [InlineKeyboardButton("👥 المشرفين", callback_data="act_admins"),
         InlineKeyboardButton("📋 سجل الإجراءات", callback_data="act_log")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_other():
    """أزرار أخرى"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان", callback_data="act_announce"),
         InlineKeyboardButton("🚨 بلاغ", callback_data="act_report")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

# ═══════════════════════════════════════════════════════════════
# أوامر البوت (فقط /start و /panel)
# ═══════════════════════════════════════════════════════════════

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة التحكم الرئيسية"""
    await update.message.reply_text(
        "🤖 <b>بوت إدارة المجموعات المتكامل v3.0</b>\n\n"
        "🛡️ أحمي مجموعتك وأديرها باحترافية!\n\n"
        "👇 اختر أي قسم من الأزرار أدناه:",
        parse_mode="HTML",
        reply_markup=kb_main()
    )

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة التحكم"""
    await start_cmd(update, context)

# ═══════════════════════════════════════════════════════════════
# معالجة الأزرار التفاعلية الرئيسية
# ═══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat = update.effective_chat
    user_id = query.from_user.id

    # التحقق من الصلاحيات
    admin = await is_admin(update, user_id)
    bot_adm = await is_bot_admin(update)

    # ═══ القائمة الرئيسية ═══
    if data == "back":
        await query.message.edit_text(
            "🤖 <b>بوت إدارة المجموعات المتكامل v3.0</b>\n\n"
            "🛡️ أحمي مجموعتك وأديرها باحترافية!\n\n"
            "👇 اختر أي قسم من الأزرار أدناه:",
            parse_mode="HTML", reply_markup=kb_main()
        )

    elif data == "cancel":
        context.user_data.pop("waiting", None)
        context.user_data.pop("target_id", None)
        await query.message.edit_text("❌ تم الإلغاء.\n\n👇 اختر من القائمة:", parse_mode="HTML", reply_markup=kb_main())

    # ═══ فتح القوائم ═══
    elif data == "menu_admin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("🛡️ <b>أوامر الإشراف</b>\n\nاختر الإجراء المطلوب:\n⚠️ لأوامر الحظر/الكتم/الطرد: <b>رد على رسالة المستخدم</b> ثم اضغط الزر", parse_mode="HTML", reply_markup=kb_admin())

    elif data == "menu_content":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("📌 <b>إدارة المحتوى</b>\n\nاختر الإجراء المطلوب:", parse_mode="HTML", reply_markup=kb_content())

    elif data == "menu_notes":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("📝 <b>نظام الملاحظات</b>\n\nاحفظ واسترجع ملاحظات لمجموعتك:", parse_mode="HTML", reply_markup=kb_notes())

    elif data == "menu_filters":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("🔍 <b>نظام الفلاتر</b>\n\nأنشئ ردود تلقائية على كلمات مفتاحية:", parse_mode="HTML", reply_markup=kb_filters())

    elif data == "menu_locks":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("🔒 <b>نظام الأقفال</b>\n\nاختر نوع الرسالة لقفله:", parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    elif data == "menu_badwords":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("🔤 <b>فلتر الكلمات المسيئة</b>\n\nأضف كلمات محظورة تُحذف تلقائياً:", parse_mode="HTML", reply_markup=kb_badwords())

    elif data == "menu_settings":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "menu_info":
        await query.message.edit_text("📊 <b>المعلومات</b>\n\nاختر المعلومات المطلوبة:", parse_mode="HTML", reply_markup=kb_info())

    elif data == "menu_other":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        await query.message.edit_text("🚨 <b>أوامر أخرى</b>\n\nاختر الإجراء:", parse_mode="HTML", reply_markup=kb_other())

    # ═══ إجراءات الإشراف ═══
    elif data == "act_ban":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "ban"
        await query.message.edit_text(
            "🚫 <b>حظر مستخدم</b>\n\n"
            "📌 <b>الخطوات:</b>\n"
            "1️⃣ رد على رسالة المستخدم المراد حظره\n"
            "2️⃣ اكتب السبب (أو أرسل نقطه . بدون سبب)\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unban":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "unban"
        await query.message.edit_text(
            "✅ <b>إلغاء حظر</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إلغاء حظره\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_mute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "mute"
        await query.message.edit_text(
            "🔇 <b>كتم مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد كتمه\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unmute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "unmute"
        await query.message.edit_text(
            "🔊 <b>إلغاء كتم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إلغاء كتمه\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_tmute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "tmute_select"
        await query.message.edit_text(
            "⏱️ <b>كتم مؤقت</b>\n\n"
            "📌 رد على رسالة المستخدم أولاً\n"
            "ثم اختر المدة من الأزرار\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data.startswith("tmute_"):
        # تنفيذ الكتم المؤقت بعد اختيار المدة
        parts = data.split("_")
        if len(parts) >= 3:
            target_id = int(parts[1])
            time_val = parts[2]
            seconds = parse_time(time_val)
            if seconds <= 0:
                await query.answer("❌ صيغة وقت خاطئة!", show_alert=True); return
            try:
                until = datetime.now() + timedelta(seconds=seconds)
                perms = ChatPermissions(can_send_messages=False)
                await chat.restrict_member(target_id, perms, until_date=until)
                time_str = format_time(seconds)
                await query.message.edit_text(
                    f"⏱️ تم كتم المستخدم لمدة <b>{time_str}</b> ✅",
                    parse_mode="HTML", reply_markup=kb_admin()
                )
                db.add_temp_mute(chat.id, target_id, user_id, until.strftime("%Y-%m-%d %H:%M:%S"))
                db.increment_stat(chat.id, "total_mutes")
                db.log_action(chat.id, user_id, f"tmute_{time_str}", target_id)
            except Exception as e:
                await query.message.edit_text(f"❌ خطأ: {str(e)}", parse_mode="HTML", reply_markup=kb_admin())
        context.user_data.pop("waiting", None)
        context.user_data.pop("target_id", None)

    elif data == "act_kick":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "kick"
        await query.message.edit_text(
            "👢 <b>طرد مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد طرده\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_warn":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "warn"
        await query.message.edit_text(
            "⚠️ <b>تحذير مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم واكتب السبب (أو . بدون سبب)\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unwarn":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "unwarn"
        await query.message.edit_text(
            "✅ <b>إزالة تحذيرات</b>\n\n"
            "📌 رد على رسالة المستخدم\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_del":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "del"
        await query.message.edit_text(
            "🗑️ <b>حذف رسالة</b>\n\n"
            "📌 رد على الرسالة المراد حذفها\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_purge":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
        context.user_data["waiting"] = "purge"
        await query.message.edit_text(
            "🗑️ <b>حذف متعدد</b>\n\n"
            "📌 رد على رسالة واكتب عدد الرسائل للحذف\n"
            "مثال: <code>10</code>\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══ إجراءات المحتوى ═══
    elif data == "act_pin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "pin"
        await query.message.edit_text(
            "📌 <b>تثبيت رسالة</b>\n\n"
            "📌 رد على الرسالة المراد تثبيتها\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unpin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        try:
            await chat.unpin_all_messages()
            await query.message.edit_text("📌 تم إلغاء تثبيت جميع الرسائل ✅", parse_mode="HTML", reply_markup=kb_content())
            db.log_action(chat.id, user_id, "unpin")
        except:
            await query.answer("❌ لا يمكن الإلغاء!", show_alert=True)

    elif data == "act_setrules":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "setrules"
        await query.message.edit_text(
            "📋 <b>تعيين القوانين</b>\n\n"
            "📝 اكتب القوانين الجديدة:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_rules":
        settings = db.get_settings(chat.id)
        rules = settings.get("rules", "")
        if rules:
            await query.message.edit_text(f"📋 <b>قوانين المجموعة:</b>\n\n{rules}", parse_mode="HTML", reply_markup=kb_back())
        else:
            await query.message.edit_text("📋 لم يتم تعيين قوانين بعد!", parse_mode="HTML", reply_markup=kb_content())

    elif data == "act_clearrules":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        db.update_setting(chat.id, "rules", "")
        await query.message.edit_text("📋 تم حذف القوانين ✅", parse_mode="HTML", reply_markup=kb_content())

    # ═══ الملاحظات ═══
    elif data == "act_savenote":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "savenote"
        await query.message.edit_text(
            "💾 <b>حفظ ملاحظة</b>\n\n"
            "📝 اكتب اسم الملاحظة ثم المحتوى:\n"
            "<code>الاسم المحتوى</code>\n\n"
            "مثال: <code>discord رابط الديسكورد: xxx</code>\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_getnote":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        notes = db.get_all_notes(chat.id)
        if notes:
            await query.message.edit_text("📖 <b>اختر ملاحظة:</b>", parse_mode="HTML", reply_markup=kb_notes_list(chat.id))
        else:
            await query.message.edit_text("📝 لا توجد ملاحظات محفوظة!", parse_mode="HTML", reply_markup=kb_notes())

    elif data.startswith("note_"):
        name = data[5:]
        content = db.get_note(chat.id, name)
        if content:
            await query.message.edit_text(f"📝 <b>{name}:</b>\n\n{content}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑️ حذف", callback_data=f"delnote_{name}"),
                 InlineKeyboardButton("🔙 رجوع", callback_data="act_getnote")]
            ]))
        else:
            await query.message.edit_text("❌ الملاحظة غير موجودة!", parse_mode="HTML", reply_markup=kb_notes_list(chat.id))

    elif data.startswith("delnote_"):
        name = data[8:]
        db.delete_note(chat.id, name)
        await query.message.edit_text(f"🗑️ تم حذف الملاحظة <b>{name}</b> ✅", parse_mode="HTML", reply_markup=kb_notes_list(chat.id))

    elif data == "act_allnotes":
        notes = db.get_all_notes(chat.id)
        if notes:
            text = "📋 <b>الملاحظات المحفوظة:</b>\n\n"
            for n in notes:
                text += f"• <b>{n}</b>\n"
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_notes_list(chat.id))
        else:
            await query.message.edit_text("📝 لا توجد ملاحظات!", parse_mode="HTML", reply_markup=kb_notes())

    elif data == "act_delnote":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "delnote"
        await query.message.edit_text(
            "🗑️ <b>حذف ملاحظة</b>\n\n"
            "📝 اكتب اسم الملاحظة المراد حذفها:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══ الفلاتر ═══
    elif data == "act_addfilter":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "addfilter"
        await query.message.edit_text(
            "➕ <b>إضافة فلتر</b>\n\n"
            "📝 اكتب الكلمة ثم الرد:\n"
            "<code>الكلمة الرد</code>\n\n"
            "مثال: <code>مرحبا أهلاً وسهلاً!</code>\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_delfilter":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "delfilter"
        await query.message.edit_text(
            "➖ <b>حذف فلتر</b>\n\n"
            "📝 اكتب الكلمة المراد حذف فلترها:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_allfilters":
        filters_list = db.get_all_filters(chat.id)
        if filters_list:
            text = "🔍 <b>الفلاتر النشطة:</b>\n\n"
            for f in filters_list:
                text += f"• <code>{f}</code>\n"
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_filters())
        else:
            await query.message.edit_text("🔍 لا توجد فلاتر!", parse_mode="HTML", reply_markup=kb_filters())

    # ═══ الأقفال ═══
    elif data.startswith("lock_"):
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        lock_type = data[5:]
        locked = db.get_all_locks(chat.id)
        if lock_type in locked:
            db.unlock_type(chat.id, lock_type)
            await query.answer(f"🔓 تم فتح {LOCK_TYPES.get(lock_type, lock_type)}!", show_alert=False)
        else:
            db.lock_type(chat.id, lock_type, user_id)
            await query.answer(f"🔒 تم قفل {LOCK_TYPES.get(lock_type, lock_type)}!", show_alert=False)
        await query.message.edit_text("🔒 <b>نظام الأقفال</b>\n\nاضغط للقفل/الفتح:", parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    elif data == "act_lockall":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        for lt in LOCK_TYPES:
            db.lock_type(chat.id, lt, user_id)
        await query.message.edit_text("🔒 تم قفل كل أنواع الرسائل ✅", parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    elif data == "act_unlockall":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        for lt in LOCK_TYPES:
            db.unlock_type(chat.id, lt)
        await query.message.edit_text("🔓 تم فتح كل أنواع الرسائل ✅", parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    elif data == "act_showlocks":
        locked = db.get_all_locks(chat.id)
        if locked:
            text = "🔒 <b>الأقفال النشطة:</b>\n\n"
            for l in locked:
                text += f"• {LOCK_TYPES.get(l, l)}\n"
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_lock_types(chat.id))
        else:
            await query.message.edit_text("🔓 لا توجد أقفال نشطة!", parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    # ═══ الكلمات ═══
    elif data == "act_addbadword":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "addbadword"
        await query.message.edit_text(
            "➕ <b>إضافة كلمة محظورة</b>\n\n"
            "📝 اكتب الكلمة:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_delbadword":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "delbadword"
        await query.message.edit_text(
            "➖ <b>حذف كلمة محظورة</b>\n\n"
            "📝 اكتب الكلمة:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_showbadwords":
        words = db.get_badwords(chat.id)
        if words:
            text = "🔤 <b>الكلمات المحظورة:</b>\n\n"
            for w in words:
                text += f"• <code>{w}</code>\n"
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_badwords())
        else:
            await query.message.edit_text("🔤 لا توجد كلمات محظورة!", parse_mode="HTML", reply_markup=kb_badwords())

    # ═══ تبديل الإعدادات ═══
    elif data == "tog_flood":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('anti_flood', 1) else 1
        db.update_setting(chat.id, 'anti_flood', nv)
        await query.answer(f"{'✅ تم التشغيل' if nv else '❌ تم الإيقاف'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "tog_spam":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('anti_spam', 1) else 1
        db.update_setting(chat.id, 'anti_spam', nv)
        await query.answer(f"{'✅ تم التشغيل' if nv else '❌ تم الإيقاف'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "tog_link":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('anti_link', 0) else 1
        db.update_setting(chat.id, 'anti_link', nv)
        await query.answer(f"{'✅ تم التشغيل' if nv else '❌ تم الإيقاف'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "tog_badword":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('anti_badword', 1) else 1
        db.update_setting(chat.id, 'anti_badword', nv)
        await query.answer(f"{'✅ تم التشغيل' if nv else '❌ تم الإيقاف'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "tog_maintenance":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('maintenance_mode', 0) else 1
        db.update_setting(chat.id, 'maintenance_mode', nv)
        await query.answer(f"{'🔧 تم تفعيل الصيانة' if nv else '✅ تم إلغاء الصيانة'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "tog_report":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        s = db.get_settings(chat.id)
        nv = 0 if s.get('report_enabled', 1) else 1
        db.update_setting(chat.id, 'report_enabled', nv)
        await query.answer(f"{'✅ تم التشغيل' if nv else '❌ تم الإيقاف'}", show_alert=True)
        await query.message.edit_text("⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "act_setwelcome":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "setwelcome"
        await query.message.edit_text(
            "💬 <b>تعيين رسالة الترحيب</b>\n\n"
            "📝 اكتب رسالة الترحيب:\n\n"
            "المتغيرات: <code>{user}</code> <code>{chat}</code> <code>{count}</code>\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_resetwelcome":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        db.update_setting(chat.id, "welcome_msg", json.dumps({"text": DEFAULT_WELCOME}))
        await query.message.edit_text("🔄 تم إعادة الترحيب الافتراضي ✅", parse_mode="HTML", reply_markup=kb_settings(chat.id))

    elif data == "act_setlog":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "setlog"
        await query.message.edit_text(
            "📝 <b>قناة السجلات</b>\n\n"
            "أرسل معرف القناة:\n"
            "مثال: <code>-1001234567890</code>\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══ المعلومات ═══
    elif data == "act_userinfo":
        context.user_data["waiting"] = "userinfo"
        await query.message.edit_text(
            "👤 <b>معلومات مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم (أو أرسل بدون رد لمعلوماتك)\n\n"
            "⏳ بانتظار ردك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_groupstats":
        stats = db.get_stats(chat.id)
        mc = await chat.get_member_count()
        text = f"""📊 <b>إحصائيات المجموعة</b>

👥 الأعضاء: {mc}
💬 الرسائل: {stats.get('total_messages', 0)}
✅ الانضمامات: {stats.get('total_joins', 0)}
❌ المغادرات: {stats.get('total_leaves', 0)}
🚫 الحظر: {stats.get('total_bans', 0)}
🔇 الكتم: {stats.get('total_mutes', 0)}
⚠️ التحذيرات: {stats.get('total_warns', 0)}
🗑️ المحذوفة: {stats.get('total_deleted', 0)}"""
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_info())

    elif data == "act_admins":
        admins_list = await chat.get_administrators()
        text = "👥 <b>المشرفين:</b>\n\n"
        for i, a in enumerate(admins_list, 1):
            u = a.user
            st = "👑" if a.status == ChatMemberStatus.OWNER else "⭐"
            text += f"{i}. {st} {u.full_name}"
            if u.username: text += f" (@{u.username})"
            text += "\n"
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_info())

    elif data == "act_log":
        logs = db.get_action_log(chat.id, 10)
        if logs:
            text = "📋 <b>سجل الإجراءات:</b>\n\n"
            for l in logs:
                date = l.get('created_at', '')[:16]
                action = l.get('action', '')
                reason = l.get('reason', '')
                text += f"• [{date}] {action}"
                if reason: text += f" - {reason}"
                text += "\n"
            await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_info())
        else:
            await query.message.edit_text("📋 لا توجد إجراءات مسجلة!", parse_mode="HTML", reply_markup=kb_info())

    # ═══ أخرى ═══
    elif data == "act_announce":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True); return
        context.user_data["waiting"] = "announce"
        await query.message.edit_text(
            "📢 <b>إعلان</b>\n\n"
            "📝 اكتب نص الإعلان:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_report":
        settings = db.get_settings(chat.id)
        if not settings.get('report_enabled', 1):
            await query.answer("❌ البلاغات معطلة!", show_alert=True); return
        context.user_data["waiting"] = "report"
        await query.message.edit_text(
            "🚨 <b>بلاغ</b>\n\n"
            "📌 رد على رسالة المستخدم المراد الإبلاغ عنه\n\n"
            "⏳ بانتظار ردك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

# ═══════════════════════════════════════════════════════════════
# معالجة الرسائل النصية (للإدخال بعد الضغط على زر)
# ═══════════════════════════════════════════════════════════════

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية - إدخال البيانات أو الحماية"""
    if not update.message or not update.effective_user:
        return

    chat = update.effective_chat
    user = update.effective_user
    text = update.message.text or ""

    # التحقق من حالة الانتظار (إدخال بيانات)
    waiting = context.user_data.get("waiting")
    if waiting and await is_admin(update, user.id):
        await handle_waiting_input(update, context, waiting, text, chat, user)
        return

    # حماية للأعضاء العاديين
    if await is_admin(update):
        return
    if user.is_bot:
        return
    if user.id == OWNER_ID:
        return

    settings = db.get_settings(chat.id)
    db.increment_stat(chat.id, "total_messages")

    # وضع الصيانة
    if settings.get("maintenance_mode", 0):
        try: await update.message.delete()
        except: pass
        return

    # حماية الفلود
    if settings.get("anti_flood", 1):
        if check_flood(chat.id, user.id, settings.get("max_flood_msgs", 5), settings.get("flood_interval", 5)):
            try:
                await update.message.delete()
                perms = ChatPermissions(can_send_messages=False)
                until = datetime.now() + timedelta(minutes=5)
                await chat.restrict_member(user.id, perms, until_date=until)
                m = mention(user.id, user.full_name)
                await chat.send_message(f"🛡️ تم كتم {m} لمدة 5 دقائق بسبب الفلود!", parse_mode="HTML")
                db.increment_stat(chat.id, "total_mutes")
                return
            except: pass

    # منع الروابط
    if settings.get("anti_link", 0):
        if re.search(r'(https?://|t\.me/|@)', text, re.IGNORECASE):
            try:
                await update.message.delete()
                await chat.send_message(f"🚫 الروابط ممنوعة يا {mention(user.id, user.full_name)}!", parse_mode="HTML")
                return
            except: pass

    # فلتر الكلمات
    if settings.get("anti_badword", 1):
        badwords = db.get_badwords(chat.id)
        for word in badwords:
            if word in text.lower():
                try:
                    await update.message.delete()
                    await chat.send_message(f"🚫 كلمة محظورة! {mention(user.id, user.full_name)}", parse_mode="HTML")
                    return
                except: pass

    # الأقفال
    locks = db.get_all_locks(chat.id)
    if locks:
        msg = update.message
        checks = {
            "photos": msg.photo, "videos": msg.video, "stickers": msg.sticker,
            "animations": msg.animation, "voice": msg.voice, "audio": msg.audio,
            "documents": msg.document, "links": bool(msg.text and re.search(r'https?://', msg.text)),
            "forward": msg.forward_date is not None, "polls": msg.poll,
            "contacts": msg.contact, "location": msg.location, "venue": msg.venue,
            "text": msg.text and not msg.entities, "inline": bool(msg.via_bot),
        }
        for lt in locks:
            if lt in checks and checks[lt]:
                try: await update.message.delete()
                except: pass
                return

    # فلاتر رد تلقائي
    if text:
        for word in text.lower().split():
            reply = db.get_filter(chat.id, word)
            if reply:
                await update.message.reply_text(reply)
                break

    # نظام البلاغات @admin
    if settings.get("report_enabled", 1) and text and "@admin" in text.lower():
        admins_list = await chat.get_administrators()
        admin_mentions = [mention(a.user.id, a.user.first_name) for a in admins_list if not a.user.is_bot][:5]
        m = mention(user.id, user.full_name)
        rtext = f"🚨 بلاغ من {m}!\n\n👥 {' '.join(admin_mentions)}"
        await chat.send_message(rtext, parse_mode="HTML")
        db.log_action(chat.id, user.id, "report")


async def handle_waiting_input(update, context, waiting, text, chat, user):
    """معالجة إدخال البيانات بعد الضغط على زر"""
    reply_msg = update.message.reply_to_message
    target = reply_msg.from_user if reply_msg else None

    # ═══ إجراءات الإشراف ═══
    if waiting == "ban" and target:
        if await is_admin(update, target.id):
            await update.message.reply_text("⛔ لا يمكن حظر مشرف!", reply_markup=kb_admin()); return
        try:
            reason = text if text != "." else "بدون سبب"
            await chat.ban_member(target.id)
            m = mention(target.id, target.full_name)
            am = mention(user.id, user.full_name)
            await update.message.reply_text(f"🚫 تم حظر {m}\n👤 بواسطة: {am}\n📝 السبب: {reason}", parse_mode="HTML", reply_markup=kb_admin())
            db.increment_stat(chat.id, "total_bans")
            db.log_action(chat.id, user.id, "ban", target.id, reason)
            await send_log(chat.id, f"🚫 حظر: {m} بواسطة {am} - {reason}", context)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    elif waiting == "unban" and target:
        try:
            await chat.unban_member(target.id)
            await update.message.reply_text(f"✅ تم إلغاء حظر {mention(target.id, target.full_name)}", parse_mode="HTML", reply_markup=kb_admin())
            db.log_action(chat.id, user.id, "unban", target.id)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    elif waiting == "mute" and target:
        if await is_admin(update, target.id):
            await update.message.reply_text("⛔ لا يمكن كتم مشرف!", reply_markup=kb_admin()); return
        try:
            perms = ChatPermissions(can_send_messages=False)
            await chat.restrict_member(target.id, perms)
            m = mention(target.id, target.full_name)
            am = mention(user.id, user.full_name)
            await update.message.reply_text(f"🔇 تم كتم {m}\n👤 بواسطة: {am}", parse_mode="HTML", reply_markup=kb_admin())
            db.increment_stat(chat.id, "total_mutes")
            db.log_action(chat.id, user.id, "mute", target.id)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    elif waiting == "unmute" and target:
        try:
            perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await chat.restrict_member(target.id, perms)
            await update.message.reply_text(f"🔊 تم إلغاء كتم {mention(target.id, target.full_name)}", parse_mode="HTML", reply_markup=kb_admin())
            db.log_action(chat.id, user.id, "unmute", target.id)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    elif waiting == "tmute_select" and target:
        if await is_admin(update, target.id):
            await update.message.reply_text("⛔ لا يمكن كتم مشرف!", reply_markup=kb_admin()); return
        context.user_data["target_id"] = target.id
        await update.message.reply_text(
            f"⏱️ <b>اختر مدة الكتم لـ {mention(target.id, target.full_name)}</b>",
            parse_mode="HTML", reply_markup=kb_mute_time(target.id)
        )
        context.user_data["waiting"] = None
        return  # لا نزيل waiting حتى يختار المدة

    elif waiting == "kick" and target:
        if await is_admin(update, target.id):
            await update.message.reply_text("⛔ لا يمكن طرد مشرف!", reply_markup=kb_admin()); return
        reason = text if text != "." else "بدون سبب"
        try:
            await chat.ban_member(target.id)
            await chat.unban_member(target.id)
            m = mention(target.id, target.full_name)
            am = mention(user.id, user.full_name)
            await update.message.reply_text(f"👢 تم طرد {m}\n👤 بواسطة: {am}\n📝 السبب: {reason}", parse_mode="HTML", reply_markup=kb_admin())
            db.log_action(chat.id, user.id, "kick", target.id, reason)
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    elif waiting == "warn" and target:
        if await is_admin(update, target.id):
            await update.message.reply_text("⛔ لا يمكن تحذير مشرف!", reply_markup=kb_admin()); return
        reason = text if text != "." else "بدون سبب"
        count = db.add_warning(chat.id, target.id, reason, user.id)
        m = mention(target.id, target.full_name)
        am = mention(user.id, user.full_name)
        db.increment_stat(chat.id, "total_warns")
        if count >= WARN_LIMIT:
            try:
                await chat.ban_member(target.id)
                await update.message.reply_text(f"🚫 تم حظر {m} بعد {WARN_LIMIT} تحذيرات!", parse_mode="HTML", reply_markup=kb_admin())
                db.reset_warnings(chat.id, target.id)
                db.increment_stat(chat.id, "total_bans")
            except: pass
        else:
            await update.message.reply_text(f"⚠️ تحذير {count}/{WARN_LIMIT} لـ {m}\n👤 بواسطة: {am}\n📝 السبب: {reason}", parse_mode="HTML", reply_markup=kb_admin())
        db.log_action(chat.id, user.id, "warn", target.id, reason)

    elif waiting == "unwarn" and target:
        db.reset_warnings(chat.id, target.id)
        await update.message.reply_text(f"✅ تم إزالة تحذيرات {mention(target.id, target.full_name)}", parse_mode="HTML", reply_markup=kb_admin())

    elif waiting == "del":
        if reply_msg:
            try:
                await reply_msg.delete()
                await update.message.delete()
                db.increment_stat(chat.id, "total_deleted")
            except: pass
        context.user_data.pop("waiting", None)
        return

    elif waiting == "purge" and reply_msg:
        try:
            count = int(text) if text.isdigit() else 5
            start_id = reply_msg.message_id
            end_id = update.message.message_id
            deleted = 0
            for msg_id in range(start_id, min(start_id + count, end_id + 1)):
                try:
                    await context.bot.delete_message(chat.id, msg_id)
                    deleted += 1
                except: continue
            await chat.send_message(f"🗑️ تم حذف {deleted} رسالة ✅", reply_markup=kb_admin())
            db.increment_stat(chat.id, "total_deleted")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}", reply_markup=kb_admin())

    # ═══ المحتوى ═══
    elif waiting == "pin":
        if reply_msg:
            try:
                await reply_msg.pin()
                await update.message.reply_text("📌 تم تثبيت الرسالة ✅", reply_markup=kb_content())
                db.log_action(chat.id, user.id, "pin")
            except: pass

    elif waiting == "setrules":
        db.update_setting(chat.id, "rules", text)
        await update.message.reply_text("📋 تم تعيين القوانين ✅", reply_markup=kb_content())
        db.log_action(chat.id, user.id, "set_rules")

    # ═══ الملاحظات ═══
    elif waiting == "savenote":
        parts = text.split(None, 1)
        if len(parts) >= 2:
            db.save_note(chat.id, parts[0].lower(), parts[1], user.id)
            await update.message.reply_text(f"📝 تم حفظ الملاحظة <b>{parts[0]}</b> ✅", parse_mode="HTML", reply_markup=kb_notes())
        else:
            await update.message.reply_text("❌ اكتب الاسم ثم المحتوى!", reply_markup=kb_notes())

    elif waiting == "delnote":
        if db.delete_note(chat.id, text.lower()):
            await update.message.reply_text(f"🗑️ تم حذف الملاحظة <b>{text}</b> ✅", parse_mode="HTML", reply_markup=kb_notes())
        else:
            await update.message.reply_text("❌ الملاحظة غير موجودة!", reply_markup=kb_notes())

    # ═══ الفلاتر ═══
    elif waiting == "addfilter":
        parts = text.split(None, 1)
        if len(parts) >= 2:
            db.save_filter(chat.id, parts[0].lower(), parts[1], user.id)
            await update.message.reply_text(f"🔍 تم إضافة فلتر لـ <code>{parts[0]}</code> ✅", parse_mode="HTML", reply_markup=kb_filters())
        else:
            await update.message.reply_text("❌ اكتب الكلمة ثم الرد!", reply_markup=kb_filters())

    elif waiting == "delfilter":
        if db.delete_filter(chat.id, text.lower()):
            await update.message.reply_text(f"✅ تم حذف فلتر <code>{text}</code>", parse_mode="HTML", reply_markup=kb_filters())
        else:
            await update.message.reply_text("❌ الفلتر غير موجود!", reply_markup=kb_filters())

    # ═══ الكلمات ═══
    elif waiting == "addbadword":
        db.add_badword(chat.id, text.lower(), user.id)
        await update.message.reply_text(f"🔤 تم إضافة <code>{text}</code> للكلمات المحظورة ✅", parse_mode="HTML", reply_markup=kb_badwords())

    elif waiting == "delbadword":
        if db.remove_badword(chat.id, text.lower()):
            await update.message.reply_text(f"✅ تم حذف <code>{text}</code>", parse_mode="HTML", reply_markup=kb_badwords())
        else:
            await update.message.reply_text("❌ الكلمة غير موجودة!", reply_markup=kb_badwords())

    # ═══ الإعدادات ═══
    elif waiting == "setwelcome":
        db.update_setting(chat.id, "welcome_msg", json.dumps({"text": text}))
        await update.message.reply_text(f"💬 تم تعيين الترحيب ✅\n\nمعاينة:\n{text}", reply_markup=kb_settings(chat.id))

    elif waiting == "setlog":
        try:
            channel_id = int(text)
            db.update_setting(chat.id, "log_channel_id", channel_id)
            await update.message.reply_text(f"📝 تم تعيين قناة السجلات ✅", reply_markup=kb_settings(chat.id))
        except ValueError:
            await update.message.reply_text("❌ معرف القناة غير صحيح!", reply_markup=kb_settings(chat.id))

    # ═══ أخرى ═══
    elif waiting == "announce":
        am = mention(user.id, user.full_name)
        await update.message.reply_text(f"📢 <b>إعلان من الإدارة</b>\n\n{text}\n\n👤 بواسطة: {am}", parse_mode="HTML", reply_markup=kb_other())
        db.log_action(chat.id, user.id, "announce", reason=text)

    elif waiting == "report" and target:
        admins_list = await chat.get_administrators()
        admin_mentions = [mention(a.user.id, a.user.first_name) for a in admins_list if not a.user.is_bot][:5]
        m = mention(user.id, user.full_name)
        await chat.send_message(f"🚨 بلاغ من {m} ضد {mention(target.id, target.full_name)}!\n\n👥 {' '.join(admin_mentions)}", parse_mode="HTML")
        db.log_action(chat.id, user.id, "report", target.id)

    elif waiting == "userinfo":
        if target:
            target_user = target
        else:
            target_user = user
        member = await chat.get_member(target_user.id)
        status_map = {
            ChatMemberStatus.OWNER: "👑 مالك", ChatMemberStatus.ADMINISTRATOR: "⭐ مشرف",
            ChatMemberStatus.MEMBER: "👤 عضو", ChatMemberStatus.RESTRICTED: "🔇 مقيد",
            ChatMemberStatus.LEFT: "🚪 غادر", ChatMemberStatus.BANNED: "🚫 محظور"
        }
        wc = db.get_warning_count(chat.id, target_user.id)
        info_text = f"""👤 <b>معلومات المستخدم</b>

🆔 المعرف: <code>{target_user.id}</code>
📝 الاسم: {target_user.full_name}
🔤 اليوزر: @{target_user.username if target_user.username else 'غير متوفر'}
📌 الحالة: {status_map.get(member.status, '❓')}
⚠️ التحذيرات: {wc}/{WARN_LIMIT}"""
        if target_user.is_bot:
            info_text += "\n🤖 بوت: نعم"
        await update.message.reply_text(info_text, parse_mode="HTML", reply_markup=kb_info())

    # تنظيف الحالة
    context.user_data.pop("waiting", None)
    context.user_data.pop("target_id", None)


# ═══════════════════════════════════════════════════════════════
# الترحيب والمغادرة
# ═══════════════════════════════════════════════════════════════

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            await update.effective_chat.send_message(
                "🤖 شكراً لإضافتي!\n\n📌 يرجى رفعي كمشرف.\n👇 اضغط لفتح لوحة التحكم:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎮 لوحة التحكم", callback_data="back")]])
            )
            continue
        settings = db.get_settings(update.effective_chat.id)
        wd = settings.get("welcome_msg", "{}")
        try: wt = json.loads(wd).get("text", DEFAULT_WELCOME)
        except: wt = DEFAULT_WELCOME
        cn = update.effective_chat.title or "المجموعة"
        mc = await update.effective_chat.get_member_count()
        m = mention(member.id, member.full_name)
        wt = wt.replace("{user}", m).replace("{user_mention}", m).replace("{chat}", cn).replace("{count}", str(mc))
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("📋 القوانين", callback_data="act_rules")]])
        await update.effective_chat.send_message(wt, parse_mode="HTML", reply_markup=kb)
        db.increment_stat(update.effective_chat.id, "total_joins")

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db.increment_stat(update.effective_chat.id, "total_leaves")

# ═══════════════════════════════════════════════════════════════
# فحص الكتم المؤقت
# ═══════════════════════════════════════════════════════════════

async def check_temp_mutes(context: ContextTypes.DEFAULT_TYPE):
    expired = db.get_expired_mutes()
    for mute in expired:
        try:
            perms = ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
            await context.bot.restrict_member(mute['chat_id'], mute['user_id'], perms)
            logger.info(f"Unmuted user {mute['user_id']} in chat {mute['chat_id']}")
        except Exception as e:
            logger.error(f"Error unmuting: {e}")

# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════

def main():
    threading.Thread(target=run_flask, daemon=True).start()

    app = Application.builder().token(TOKEN).build()

    # أوامر أساسية فقط
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))

    # معالجة الأزرار
    app.add_handler(CallbackQueryHandler(callback_handler))

    # معالجة الرسائل
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_text))

    # فحص الكتم المؤقت
    if app.job_queue is not None:
        app.job_queue.run_repeating(check_temp_mutes, interval=60, first=10)
    else:
        def temp_mute_checker():
            while True:
                try:
                    expired = db.get_expired_mutes()
                    for mute in expired:
                        logger.info(f"Auto-unmute: user {mute['user_id']} in chat {mute['chat_id']}")
                except Exception as e:
                    logger.error(f"Error in temp_mute_checker: {e}")
                time.sleep(60)
        threading.Thread(target=temp_mute_checker, daemon=True).start()

    logger.info("🤖 بوت إدارة المجموعات المتكامل v3.0 - أزرار بدأ العمل!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
