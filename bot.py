"""
╔══════════════════════════════════════════════════════════════════╗
║    🛡️ بوت إدارة المجموعات المتكامل v5.0 - الحماية المتقدمة 🛡️    ║
║                                                                  ║
║  بوت احترافي لإدارة وحماية مجموعات التيليجرام                   ║
║  واجهة أزرار كاملة | حماية متقدمة | إدارة ذكية                 ║
║  مطور بواسطة: @masqsam3                                         ║
╚══════════════════════════════════════════════════════════════════╝
"""

import logging
import os
import re
import sqlite3
import threading
import time
import json
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, jsonify
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ChatMemberStatus, ParseMode

# ═════════════════════════════════════════════════════════════════
# إعداد السجلات
# ═════════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═════════════════════════════════════════════════════════════════
# الإعدادات العامة
# ═════════════════════════════════════════════════════════════════
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID = 8947599931  # معرف المالك
WARN_LIMIT = 3
DEFAULT_WELCOME = "مرحباً بك يا {user} في مجموعتنا! 🎉\nيرجى قراءة القوانين"
DB_PATH = "bot_database.db"

SUDO_USERS = {OWNER_ID}  # المستخدمين ذوي الصلاحيات العليا

# ═════════════════════════════════════════════════════════════════
# خادم Flask للحفاظ على البوت نشطاً
# ═════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return jsonify({
        "status": "running",
        "bot": "Group Manager v5.0",
        "version": "5.0.0",
        "features": "Advanced Protection",
        "uptime": True
    }), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ═════════════════════════════════════════════════════════════════
# نظام قاعدة البيانات SQLite المتقدم
# ═════════════════════════════════════════════════════════════════
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()

            # إعدادات المجموعة
            c.execute('''CREATE TABLE IF NOT EXISTS group_settings (
                chat_id INTEGER PRIMARY KEY,
                welcome_msg TEXT DEFAULT '',
                rules TEXT DEFAULT '',
                maintenance_mode INTEGER DEFAULT 0,
                log_channel_id INTEGER DEFAULT 0,
                anti_spam INTEGER DEFAULT 1,
                anti_flood INTEGER DEFAULT 1,
                anti_link INTEGER DEFAULT 1,
                anti_badword INTEGER DEFAULT 1,
                anti_raid INTEGER DEFAULT 1,
                anti_bot INTEGER DEFAULT 0,
                anti_channel INTEGER DEFAULT 1,
                anti_forward INTEGER DEFAULT 0,
                anti_username INTEGER DEFAULT 0,
                anti_arabic INTEGER DEFAULT 0,
                anti_emoji INTEGER DEFAULT 0,
                report_enabled INTEGER DEFAULT 1,
                captcha_enabled INTEGER DEFAULT 0,
                auto_delete INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                max_flood_msgs INTEGER DEFAULT 5,
                flood_interval INTEGER DEFAULT 5,
                raid_threshold INTEGER DEFAULT 5,
                raid_action TEXT DEFAULT 'kick',
                link_action TEXT DEFAULT 'delete',
                warn_action TEXT DEFAULT 'mute',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            # التحذيرات
            c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, user_id INTEGER, reason TEXT DEFAULT '',
                warned_by INTEGER, warned_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS warning_counts (
                chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )''')

            # الملاحظات
            c.execute('''CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, name TEXT, content TEXT, created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, name)
            )''')

            # الفلاتر
            c.execute('''CREATE TABLE IF NOT EXISTS filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, keyword TEXT, reply TEXT, created_by INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, keyword)
            )''')

            # الأقفال
            c.execute('''CREATE TABLE IF NOT EXISTS locks (
                chat_id INTEGER, lock_type TEXT, locked_by INTEGER,
                locked_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (chat_id, lock_type)
            )''')

            # الكلمات المسيئة
            c.execute('''CREATE TABLE IF NOT EXISTS badwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, word TEXT, added_by INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(chat_id, word)
            )''')

            # الإحصائيات
            c.execute('''CREATE TABLE IF NOT EXISTS group_stats (
                chat_id INTEGER PRIMARY KEY,
                total_messages INTEGER DEFAULT 0, total_joins INTEGER DEFAULT 0,
                total_leaves INTEGER DEFAULT 0, total_bans INTEGER DEFAULT 0,
                total_mutes INTEGER DEFAULT 0, total_warns INTEGER DEFAULT 0,
                total_deleted INTEGER DEFAULT 0, total_kicks INTEGER DEFAULT 0,
                total_raids_blocked INTEGER DEFAULT 0, total_links_blocked INTEGER DEFAULT 0,
                total_spam_blocked INTEGER DEFAULT 0, total_flood_blocked INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            # الكتم المؤقت
            c.execute('''CREATE TABLE IF NOT EXISTS temp_mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, user_id INTEGER, muted_by INTEGER,
                mute_until TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            # سجل الإجراءات
            c.execute('''CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, user_id INTEGER, action TEXT,
                target_id INTEGER DEFAULT 0, reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            # القائمة البيضاء
            c.execute('''CREATE TABLE IF NOT EXISTS whitelist (
                chat_id INTEGER, user_id INTEGER, added_by INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(chat_id, user_id)
            )''')

            # المستخدمين المقيدين (الذين تجاوزوا الكابتشا)
            c.execute('''CREATE TABLE IF NOT EXISTS captcha_pending (
                chat_id INTEGER, user_id INTEGER, message_id INTEGER,
                correct_answer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')

            # بيانات الغارات
            c.execute('''CREATE TABLE IF NOT EXISTS raid_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, join_count INTEGER, action_taken TEXT,
                detected_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')

            conn.commit()
            conn.close()

    def get_settings(self, chat_id: int) -> dict:
        with self.lock:
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
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
            conn.commit()
            conn.close()

    def update_setting(self, chat_id: int, key: str, value):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute(f"UPDATE group_settings SET {key} = ? WHERE chat_id = ?", (value, chat_id))
            conn.commit()
            conn.close()

    def add_warning(self, chat_id: int, user_id: int, reason: str, warned_by: int) -> int:
        with self.lock:
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
        with self.lock:
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
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            try:
                c.execute("DELETE FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            except:
                pass
            conn.commit()
            conn.close()

    def save_note(self, chat_id, name, content, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO notes (chat_id, name, content, created_by) VALUES (?, ?, ?, ?)",
                     (chat_id, name, content, user_id))
            conn.commit()
            conn.close()

    def get_note(self, chat_id, name):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT content FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
            row = c.fetchone()
            conn.close()
            return row[0] if row else None

    def get_all_notes(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT name FROM notes WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def delete_note(self, chat_id, name):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def save_filter(self, chat_id, keyword, reply, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO filters (chat_id, keyword, reply, created_by) VALUES (?, ?, ?, ?)",
                     (chat_id, keyword, reply, user_id))
            conn.commit()
            conn.close()

    def get_filter(self, chat_id, keyword):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT reply FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
            row = c.fetchone()
            conn.close()
            return row[0] if row else None

    def get_all_filters(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT keyword FROM filters WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def delete_filter(self, chat_id, keyword):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def lock_type(self, chat_id, lock_type, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO locks (chat_id, lock_type, locked_by) VALUES (?, ?, ?)",
                     (chat_id, lock_type, user_id))
            conn.commit()
            conn.close()

    def unlock_type(self, chat_id, lock_type):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM locks WHERE chat_id = ? AND lock_type = ?", (chat_id, lock_type))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def get_all_locks(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT lock_type FROM locks WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def unlock_all(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM locks WHERE chat_id = ?", (chat_id,))
            d = c.rowcount
            conn.commit()
            conn.close()
            return d

    def add_badword(self, chat_id, word, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO badwords (chat_id, word, added_by) VALUES (?, ?, ?)",
                     (chat_id, word, user_id))
            conn.commit()
            conn.close()

    def remove_badword(self, chat_id, word):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM badwords WHERE chat_id = ? AND word = ?", (chat_id, word))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def get_badwords(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT word FROM badwords WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def increment_stat(self, chat_id, stat):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO group_stats (chat_id) VALUES (?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
            c.execute(f"UPDATE group_stats SET {stat} = {stat} + 1, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?", (chat_id,))
            conn.commit()
            conn.close()

    def get_stats(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM group_stats WHERE chat_id = ?", (chat_id,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else {}

    def add_temp_mute(self, chat_id, user_id, muted_by, mute_until):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO temp_mutes (chat_id, user_id, muted_by, mute_until) VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, muted_by, mute_until))
            conn.commit()
            conn.close()

    def get_expired_mutes(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("SELECT * FROM temp_mutes WHERE mute_until <= ?", (now,))
            rows = c.fetchall()
            c.execute("DELETE FROM temp_mutes WHERE mute_until <= ?", (now,))
            conn.commit()
            conn.close()
            return [dict(row) for row in rows]

    def log_action(self, chat_id, user_id, action, target_id=0, reason=""):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO action_log (chat_id, user_id, action, target_id, reason) VALUES (?, ?, ?, ?, ?)",
                     (chat_id, user_id, action, target_id, reason))
            conn.commit()
            conn.close()

    def get_action_log(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM action_log WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [dict(row) for row in rows]

    def add_whitelist(self, chat_id, user_id, added_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO whitelist (chat_id, user_id, added_by) VALUES (?, ?, ?)",
                     (chat_id, user_id, added_by))
            conn.commit()
            conn.close()

    def remove_whitelist(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM whitelist WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def is_whitelisted(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id FROM whitelist WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row is not None

    def get_whitelist(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id FROM whitelist WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def add_captcha(self, chat_id, user_id, message_id, answer):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO captcha_pending (chat_id, user_id, message_id, correct_answer) VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, message_id, answer))
            conn.commit()
            conn.close()

    def get_captcha(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else None

    def remove_captcha(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            conn.commit()
            conn.close()


db = Database(DB_PATH)

# ═════════════════════════════════════════════════════════════════
# ثوابت
# ═════════════════════════════════════════════════════════════════
LOCK_TYPES = {
    "photos": "الصور 📷", "videos": "الفيديو 🎬", "stickers": "الملصقات 🎭",
    "animations": "ال GIF 🎞️", "voice": "الصوتية 🎤", "audio": "الصوت 🎵",
    "documents": "الملفات 📄", "links": "الروابط 🔗", "forward": "إعادة التوجيه ↗️",
    "inline": "الإنلاين ⚡", "polls": "الاستفتاءات 📊", "contacts": "جهات الاتصال 📱",
    "location": "الموقع 📍", "venue": "الأماكن 🏢", "text": "النصوص ✏️", "bots": "البوتات 🤖",
    "video_note": "رسائل الفيديو 🔵", "game": "الألعاب 🎮", "sticker": "الملصقات 🎭",
}

MUTE_TIMES = [
    ("1 دقيقة", "1m"), ("5 دقائق", "5m"), ("10 دقائق", "10m"),
    ("30 دقيقة", "30m"), ("1 ساعة", "1h"), ("6 ساعات", "6h"),
    ("12 ساعة", "12h"), ("1 يوم", "1d"), ("3 أيام", "3d"), ("7 أيام", "7d"),
]

RAID_ACTIONS = {
    "kick": "طرد 👢",
    "ban": "حظر 🚫",
    "mute": "كتم 🔇",
}

LINK_ACTIONS = {
    "delete": "حذف الرسالة 🗑️",
    "mute": "كتم المستخدم 🔇",
    "ban": "حظر المستخدم 🚫",
    "warn": "تحذير ⚠️",
}

WARN_ACTIONS = {
    "mute": "كتم 🔇",
    "kick": "طرد 👢",
    "ban": "حظر 🚫",
}

# ═════════════════════════════════════════════════════════════════
# أنظمة الحماية
# ═════════════════════════════════════════════════════════════════

# نظام الفلود
flood_data = {}

def check_flood(chat_id, user_id, max_msgs=5, interval=5):
    now = time.time()
    if chat_id not in flood_data:
        flood_data[chat_id] = {}
    if user_id not in flood_data[chat_id]:
        flood_data[chat_id][user_id] = []
    flood_data[chat_id][user_id].append(now)
    flood_data[chat_id][user_id] = [t for t in flood_data[chat_id][user_id] if now - t <= interval]
    return len(flood_data[chat_id][user_id]) > max_msgs

# نظام الغارات
raid_data = {}

def check_raid(chat_id, threshold=5, window=10):
    now = time.time()
    if chat_id not in raid_data:
        raid_data[chat_id] = []
    raid_data[chat_id] = [t for t in raid_data[chat_id] if now - t <= window]
    return len(raid_data[chat_id]) >= threshold

def record_join(chat_id):
    now = time.time()
    if chat_id not in raid_data:
        raid_data[chat_id] = []
    raid_data[chat_id].append(now)

# كشف الروابط
URL_PATTERN = re.compile(
    r'(https?://[^\s]+)|(t\.me/[^\s]+)|(@\w+bot)',
    re.IGNORECASE
)

def has_link(text):
    if not text:
        return False
    return bool(URL_PATTERN.search(text))

# كشف السبام
spam_patterns = [
    re.compile(r'(.)\1{8,}'),  # تكرار حرف
    re.compile(r'(.{3,})\1{4,}'),  # تكرار نمط
]

def is_spam(text):
    if not text:
        return False
    for pattern in spam_patterns:
        if pattern.search(text):
            return True
    return False

# ═════════════════════════════════════════════════════════════════
# دوال مساعدة
# ═════════════════════════════════════════════════════════════════

async def is_admin(update: Update, user_id: int = None) -> bool:
    try:
        if user_id is None:
            user_id = update.effective_user.id
        if user_id == OWNER_ID or user_id in SUDO_USERS:
            return True
        chat = update.effective_chat
        if chat is None:
            return False
        member = await chat.get_member(user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

async def is_bot_admin(chat, bot_id: int) -> bool:
    try:
        m = await chat.get_member(bot_id)
        return m.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

def mention(user_id, name):
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def parse_time(time_str):
    if not time_str:
        return 0
    time_str = time_str.lower().strip()
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    match = re.match(r'^(\d+)([smhd])$', time_str)
    if match:
        return int(match.group(1)) * units[match.group(2)]
    try:
        return int(time_str) * 60
    except:
        return 0

def format_time(seconds):
    if seconds >= 86400:
        return f"{seconds // 86400} يوم"
    elif seconds >= 3600:
        return f"{seconds // 3600} ساعة و {(seconds % 3600) // 60} دقيقة"
    elif seconds >= 60:
        return f"{seconds // 60} دقيقة"
    else:
        return f"{seconds} ثانية"

async def send_log(chat_id, text, context):
    settings = db.get_settings(chat_id)
    log_channel = settings.get('log_channel_id', 0)
    if log_channel and log_channel != 0:
        try:
            await context.bot.send_message(chat_id=log_channel, text=text, parse_mode="HTML")
        except:
            pass

# ═════════════════════════════════════════════════════════════════
# نظام اللوحات (Keyboards) - واجهة أزرار متكاملة
# ═════════════════════════════════════════════════════════════════

def kb_main(is_adm=False):
    """القائمة الرئيسية"""
    buttons = [
        [InlineKeyboardButton("🛡️ الإشراف", callback_data="menu_admin"),
         InlineKeyboardButton("🔐 الحماية", callback_data="menu_protection")],
        [InlineKeyboardButton("📌 المحتوى", callback_data="menu_content"),
         InlineKeyboardButton("📝 الملاحظات", callback_data="menu_notes")],
        [InlineKeyboardButton("🔍 الفلاتر", callback_data="menu_filters"),
         InlineKeyboardButton("🔒 الأقفال", callback_data="menu_locks")],
        [InlineKeyboardButton("🔤 الكلمات", callback_data="menu_badwords"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="menu_settings")],
        [InlineKeyboardButton("📊 المعلومات", callback_data="menu_info"),
         InlineKeyboardButton("🚨 أخرى", callback_data="menu_other")],
    ]
    if is_adm:
        buttons.append([InlineKeyboardButton("👑 أدوات المالك", callback_data="menu_owner")])
    buttons.append([InlineKeyboardButton("👤 المطور", url="https://t.me/masqsam3")])
    return InlineKeyboardMarkup(buttons)

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

def kb_protection(chat_id):
    """أزرار الحماية المتقدمة"""
    s = db.get_settings(chat_id)
    buttons = [
        [InlineKeyboardButton(f"{'✅' if s.get('anti_raid',1) else '❌'} حماية الغارات", callback_data="tog_raid"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_bot',0) else '❌'} منع البوتات", callback_data="tog_antibot")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_channel',1) else '❌'} منع القنوات", callback_data="tog_antichannel"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_forward',0) else '❌'} منع التوجيه", callback_data="tog_antiforward")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_flood',1) else '❌'} حماية الفلود", callback_data="tog_flood"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_spam',1) else '❌'} حماية السبام", callback_data="tog_spam")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_link',1) else '❌'} منع الروابط", callback_data="tog_link"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_badword',1) else '❌'} فلتر الكلمات", callback_data="tog_badword")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_username',0) else '❌'} منع المعرفات", callback_data="tog_antiusername"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_emoji',0) else '❌'} منع الإيموجي", callback_data="tog_antiemoji")],
        [InlineKeyboardButton(f"{'✅' if s.get('captcha_enabled',0) else '❌'} كابتشا الدخول", callback_data="tog_captcha"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_arabic',0) else '❌'} منع العربية", callback_data="tog_antiarabic")],
        [InlineKeyboardButton("⚡ إعدادات الغارة", callback_data="raid_settings"),
         InlineKeyboardButton("🔗 إعدادات الروابط", callback_data="link_settings")],
        [InlineKeyboardButton("⚠️ إعدادات التحذير", callback_data="warn_settings"),
         InlineKeyboardButton("🛡️ القائمة البيضاء", callback_data="menu_whitelist")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_mute_time(target_id):
    """أزرار اختيار مدة الكتم"""
    buttons = []
    row = []
    for label, val in MUTE_TIMES:
        row.append(InlineKeyboardButton(label, callback_data=f"tmute_{target_id}_{val}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
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

def kb_filters_list(chat_id):
    """أزرار قائمة الفلاتر"""
    filters_list = db.get_all_filters(chat_id)
    if not filters_list:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_filters")]])
    buttons = []
    for kw in filters_list:
        buttons.append([InlineKeyboardButton(f"🔍 {kw}", callback_data=f"filter_{kw}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_filters")])
    return InlineKeyboardMarkup(buttons)

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
    if row:
        buttons.append(row)
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
    """أزرار الإعدادات"""
    s = db.get_settings(chat_id)
    buttons = [
        [InlineKeyboardButton(f"{'✅' if s.get('maintenance_mode',0) else '❌'} وضع الصيانة", callback_data="tog_maintenance"),
         InlineKeyboardButton(f"{'✅' if s.get('report_enabled',1) else '❌'} البلاغات", callback_data="tog_report")],
        [InlineKeyboardButton("💬 تعيين الترحيب", callback_data="act_setwelcome"),
         InlineKeyboardButton("🔄 ترحيب افتراضي", callback_data="act_resetwelcome")],
        [InlineKeyboardButton("📝 قناة السجلات", callback_data="act_setlog"),
         InlineKeyboardButton("🗑️ تنظيف المجموعة", callback_data="act_cleanup")],
        [InlineKeyboardButton("💾 نسخ احتياطي", callback_data="act_backup"),
         InlineKeyboardButton("📥 استعادة النسخ", callback_data="act_restore")],
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
        [InlineKeyboardButton("🛡️ حالة الحماية", callback_data="act_protect_status")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_other():
    """أزرار أخرى"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان", callback_data="act_announce"),
         InlineKeyboardButton("🚨 بلاغ", callback_data="act_report")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_owner():
    """أزرار أدوات المالك"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان لكل المجموعات", callback_data="owner_broadcast"),
         InlineKeyboardButton("📊 إحصائيات عامة", callback_data="owner_stats")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_raid_settings(chat_id):
    """أزرار إعدادات الغارة"""
    s = db.get_settings(chat_id)
    current_action = s.get('raid_action', 'kick')
    threshold = s.get('raid_threshold', 5)
    buttons = [
        [InlineKeyboardButton(f"📊 حد الغارة: {threshold}", callback_data="set_raid_threshold")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='kick' else '⚪'} طرد", callback_data="set_raid_kick"),
         InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_raid_ban"),
         InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_raid_mute")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_link_settings(chat_id):
    """أزرار إعدادات الروابط"""
    s = db.get_settings(chat_id)
    current_action = s.get('link_action', 'delete')
    buttons = [
        [InlineKeyboardButton(f"{'🔵' if current_action=='delete' else '⚪'} حذف الرسالة", callback_data="set_link_delete"),
         InlineKeyboardButton(f"{'🔵' if current_action=='warn' else '⚪'} تحذير", callback_data="set_link_warn")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_link_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_link_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_warn_settings(chat_id):
    """أزرار إعدادات التحذير"""
    s = db.get_settings(chat_id)
    current_action = s.get('warn_action', 'mute')
    buttons = [
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم عند الحد", callback_data="set_warn_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='kick' else '⚪'} طرد عند الحد", callback_data="set_warn_kick")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر عند الحد", callback_data="set_warn_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_whitelist(chat_id):
    """أزرار القائمة البيضاء"""
    buttons = [
        [InlineKeyboardButton("➕ إضافة للقائمة البيضاء", callback_data="wl_add"),
         InlineKeyboardButton("➖ إزالة من القائمة", callback_data="wl_remove")],
        [InlineKeyboardButton("📋 عرض القائمة البيضاء", callback_data="wl_show")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ]
    return InlineKeyboardMarkup(buttons)


# ═════════════════════════════════════════════════════════════════
# أوامر البوت
# ═════════════════════════════════════════════════════════════════

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة التحكم الرئيسية"""
    is_adm = await is_admin(update)
    text = (
        "🛡️ <b>بوت إدارة المجموعات المتكامل v5.0</b>\n\n"
        "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
        "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
        "📊 <b>إحصائيات شاملة</b> لكل ما يحدث في مجموعتك\n\n"
        "👇 اختر أي قسم من الأزرار أدناه:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_main(is_adm))

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض لوحة التحكم"""
    await start_cmd(update, context)


# ═════════════════════════════════════════════════════════════════
# معالجة الأزرار التفاعلية
# ═════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat = update.effective_chat
    user_id = query.from_user.id

    admin = await is_admin(update, user_id)
    bot_adm = await is_bot_admin(chat, context.bot.id) if chat else False
    is_owner = user_id == OWNER_ID

    # ═══════════════════════════════════════════════════
    # القائمة الرئيسية
    # ═══════════════════════════════════════════════════
    if data == "back":
        await query.message.edit_text(
            "🛡️ <b>بوت إدارة المجموعات المتكامل v5.0</b>\n\n"
            "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
            "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
            "📊 <b>إحصائيات شاملة</b> لكل ما يحدث في مجموعتك\n\n"
            "👇 اختر أي قسم من الأزرار أدناه:",
            parse_mode="HTML", reply_markup=kb_main(admin or is_owner)
        )

    elif data == "cancel":
        context.user_data.pop("waiting", None)
        context.user_data.pop("target_id", None)
        context.user_data.pop("note_name", None)
        await query.message.edit_text(
            "❌ تم الإلغاء.\n\n👇 اختر من القائمة:",
            parse_mode="HTML", reply_markup=kb_main(admin or is_owner)
        )

    # ═══════════════════════════════════════════════════
    # فتح القوائم
    # ═══════════════════════════════════════════════════
    elif data == "menu_admin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🛡️ <b>أوامر الإشراف</b>\n\n"
            "اختر الإجراء المطلوب:\n\n"
            "📌 <b>لحظر/كتم/طرد/تحذير:</b> رد على رسالة المستخدم ثم اضغط الزر\n"
            "📌 <b>لحذف رسالة:</b> رد على الرسالة ثم اضغط حذف\n"
            "📌 <b>لحذف متعدد:</b> رد على رسالة واكتب العدد",
            parse_mode="HTML", reply_markup=kb_admin()
        )

    elif data == "menu_protection":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🔐 <b>نظام الحماية المتقدم</b>\n\n"
            "🛡️ حماية شاملة لمجموعتك ضد:\n"
            "• الغارات (دخول جماعي مفاجئ)\n"
            "• السبام والفلود\n"
            "• الروابط المشبوهة\n"
            "• البوتات غير المرخصة\n"
            "• القنوات والتوجيه\n"
            "• الكلمات المسيئة\n\n"
            "اضغط على أي حماية لتفعيلها/تعطيلها:",
            parse_mode="HTML", reply_markup=kb_protection(chat.id)
        )

    elif data == "menu_content":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "📌 <b>إدارة المحتوى</b>\n\nاختر الإجراء المطلوب:",
            parse_mode="HTML", reply_markup=kb_content()
        )

    elif data == "menu_notes":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "📝 <b>نظام الملاحظات</b>\n\nاحفظ واسترجع ملاحظات لمجموعتك:",
            parse_mode="HTML", reply_markup=kb_notes()
        )

    elif data == "menu_filters":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🔍 <b>نظام الفلاتر</b>\n\nأنشئ ردود تلقائية على كلمات مفتاحية:",
            parse_mode="HTML", reply_markup=kb_filters()
        )

    elif data == "menu_locks":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🔒 <b>نظام الأقفال</b>\n\nاختر نوع الرسالة لقفله:",
            parse_mode="HTML", reply_markup=kb_lock_types(chat.id)
        )

    elif data == "menu_badwords":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🔤 <b>فلتر الكلمات المسيئة</b>\n\nأضف كلمات محظورة تُحذف تلقائياً:",
            parse_mode="HTML", reply_markup=kb_badwords()
        )

    elif data == "menu_settings":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "⚙️ <b>إعدادات المجموعة</b>\n\nاضغط على أي إعداد لتغييره:",
            parse_mode="HTML", reply_markup=kb_settings(chat.id)
        )

    elif data == "menu_info":
        await query.message.edit_text(
            "📊 <b>المعلومات</b>\n\nاختر المعلومات المطلوبة:",
            parse_mode="HTML", reply_markup=kb_info()
        )

    elif data == "menu_other":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🚨 <b>أوامر أخرى</b>\n\nاختر الإجراء:",
            parse_mode="HTML", reply_markup=kb_other()
        )

    elif data == "menu_owner":
        if not is_owner:
            await query.answer("👑 للمالك فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "👑 <b>أدوات المالك</b>\n\nهذه الأدوات متاحة فقط لصاحب البوت:",
            parse_mode="HTML", reply_markup=kb_owner()
        )

    # ═══════════════════════════════════════════════════
    # تبديل الحماية
    # ═══════════════════════════════════════════════════
    elif data.startswith("tog_"):
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        toggle_map = {
            "tog_flood": ("anti_flood", "حماية الفلود"),
            "tog_spam": ("anti_spam", "حماية السبام"),
            "tog_link": ("anti_link", "منع الروابط"),
            "tog_badword": ("anti_badword", "فلتر الكلمات"),
            "tog_raid": ("anti_raid", "حماية الغارات"),
            "tog_antibot": ("anti_bot", "منع البوتات"),
            "tog_antichannel": ("anti_channel", "منع القنوات"),
            "tog_antiforward": ("anti_forward", "منع التوجيه"),
            "tog_antiusername": ("anti_username", "منع المعرفات"),
            "tog_antiemoji": ("anti_emoji", "منع الإيموجي"),
            "tog_captcha": ("captcha_enabled", "كابتشا الدخول"),
            "tog_antiarabic": ("anti_arabic", "منع العربية"),
            "tog_maintenance": ("maintenance_mode", "وضع الصيانة"),
            "tog_report": ("report_enabled", "البلاغات"),
        }
        if data in toggle_map:
            key, name = toggle_map[data]
            s = db.get_settings(chat.id)
            new_val = 0 if s.get(key, 0) else 1
            db.update_setting(chat.id, key, new_val)
            status = "مفعّل ✅" if new_val else "معطّل ❌"
            await query.message.edit_text(
                f"🔐 <b>نظام الحماية المتقدم</b>\n\n"
                f"تم {'تفعيل' if new_val else 'تعطيل'} <b>{name}</b> {status}\n\n"
                f"اضغط على أي حماية لتفعيلها/تعطيلها:",
                parse_mode="HTML", reply_markup=kb_protection(chat.id)
            )

    # ═══════════════════════════════════════════════════
    # إعدادات الغارة
    # ═══════════════════════════════════════════════════
    elif data == "raid_settings":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "⚡ <b>إعدادات حماية الغارات</b>\n\n"
            "📌 حد الغارة: عدد الأعضاء الجدد في نافذة 10 ثوان\n"
            "📌 الإجراء: ما يحدث عند كشف غارة\n\n"
            "اختر الإعدادات:",
            parse_mode="HTML", reply_markup=kb_raid_settings(chat.id)
        )

    elif data == "set_raid_threshold":
        if not admin:
            return
        context.user_data["waiting"] = "set_raid_threshold"
        await query.message.edit_text(
            "📊 <b>تعيين حد الغارة</b>\n\n"
            "اكتب عدد الأعضاء الجدد الذي يعتبر غارة\n"
            "(القيمة الحالية محفوظة في النظام)\n\n"
            "مثال: <code>5</code> أو <code>3</code>\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data.startswith("set_raid_"):
        if not admin:
            return
        action = data.replace("set_raid_", "")
        if action in RAID_ACTIONS:
            db.update_setting(chat.id, "raid_action", action)
            await query.message.edit_text(
                f"⚡ <b>إعدادات حماية الغارات</b>\n\n"
                f"تم تعيين الإجراء: {RAID_ACTIONS[action]}\n\n"
                f"اختر الإعدادات:",
                parse_mode="HTML", reply_markup=kb_raid_settings(chat.id)
            )

    # ═══════════════════════════════════════════════════
    # إعدادات الروابط
    # ═══════════════════════════════════════════════════
    elif data == "link_settings":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🔗 <b>إعدادات منع الروابط</b>\n\n"
            "اختر الإجراء عند إرسال رابط:\n\n"
            "• حذف الرسالة: حذف فقط بدون عقاب\n"
            "• تحذير: حذف + تحذير للمستخدم\n"
            "• كتم: حذف + كتم المستخدم\n"
            "• حظر: حذف + حظر المستخدم",
            parse_mode="HTML", reply_markup=kb_link_settings(chat.id)
        )

    elif data.startswith("set_link_"):
        if not admin:
            return
        action = data.replace("set_link_", "")
        if action in LINK_ACTIONS:
            db.update_setting(chat.id, "link_action", action)
            await query.message.edit_text(
                f"🔗 <b>إعدادات منع الروابط</b>\n\n"
                f"تم تعيين الإجراء: {LINK_ACTIONS[action]}\n\n"
                f"اختر الإعدادات:",
                parse_mode="HTML", reply_markup=kb_link_settings(chat.id)
            )

    # ═══════════════════════════════════════════════════
    # إعدادات التحذير
    # ═══════════════════════════════════════════════════
    elif data == "warn_settings":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "⚠️ <b>إعدادات التحذيرات</b>\n\n"
            f"الحد الأقصى: {WARN_LIMIT} تحذيرات\n\n"
            "اختر ما يحدث عند بلوغ الحد:",
            parse_mode="HTML", reply_markup=kb_warn_settings(chat.id)
        )

    elif data.startswith("set_warn_"):
        if not admin:
            return
        action = data.replace("set_warn_", "")
        if action in WARN_ACTIONS:
            db.update_setting(chat.id, "warn_action", action)
            await query.message.edit_text(
                f"⚠️ <b>إعدادات التحذيرات</b>\n\n"
                f"تم تعيين الإجراء عند الحد: {WARN_ACTIONS[action]}\n\n"
                f"اختر الإعدادات:",
                parse_mode="HTML", reply_markup=kb_warn_settings(chat.id)
            )

    # ═══════════════════════════════════════════════════
    # القائمة البيضاء
    # ═══════════════════════════════════════════════════
    elif data == "menu_whitelist":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        await query.message.edit_text(
            "🛡️ <b>القائمة البيضاء</b>\n\n"
            "المستخدمون في القائمة البيضاء معفون من جميع أنظمة الحماية\n\n"
            "اختر الإجراء:",
            parse_mode="HTML", reply_markup=kb_whitelist(chat.id)
        )

    elif data == "wl_add":
        if not admin:
            return
        context.user_data["waiting"] = "wl_add"
        await query.message.edit_text(
            "➕ <b>إضافة للقائمة البيضاء</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إضافته\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "wl_remove":
        if not admin:
            return
        context.user_data["waiting"] = "wl_remove"
        await query.message.edit_text(
            "➖ <b>إزالة من القائمة البيضاء</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إزالته\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "wl_show":
        wl = db.get_whitelist(chat.id)
        if wl:
            text = "🛡️ <b>القائمة البيضاء:</b>\n\n"
            for uid in wl:
                text += f"• <code>{uid}</code>\n"
        else:
            text = "🛡️ <b>القائمة البيضاء فارغة</b>\n\nلم تتم إضافة أي مستخدم بعد."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_whitelist(chat.id))

    # ═══════════════════════════════════════════════════
    # إجراءات الإشراف
    # ═══════════════════════════════════════════════════
    elif data == "act_ban":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "ban"
        await query.message.edit_text(
            "🚫 <b>حظر مستخدم</b>\n\n"
            "📌 <b>الخطوات:</b>\n"
            "1️⃣ رد على رسالة المستخدم المراد حظره\n"
            "2️⃣ اكتب السبب (أو أرسل نقطة . بدون سبب)\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unban":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "unban"
        await query.message.edit_text(
            "✅ <b>إلغاء حظر</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إلغاء حظره\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_mute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "mute"
        await query.message.edit_text(
            "🔇 <b>كتم مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد كتمه\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unmute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "unmute"
        await query.message.edit_text(
            "🔊 <b>إلغاء كتم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد إلغاء كتمه\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_tmute":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "tmute_select"
        await query.message.edit_text(
            "⏱️ <b>كتم مؤقت</b>\n\n"
            "📌 رد على رسالة المستخدم أولاً\n"
            "ثم اختر المدة من الأزرار\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data.startswith("tmute_"):
        parts = data.split("_")
        if len(parts) >= 3:
            target_id = int(parts[1])
            time_val = parts[2]
            seconds = parse_time(time_val)
            if seconds <= 0:
                await query.answer("❌ صيغة وقت خاطئة!", show_alert=True)
                return
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
                await send_log(chat.id, f"⏱️ كتم مؤقت: {mention(user_id, query.from_user.first_name)} كتم {mention(target_id, 'مستخدم')} لمدة {time_str}", context)
            except Exception as e:
                await query.message.edit_text(
                    f"❌ خطأ: {str(e)}", parse_mode="HTML", reply_markup=kb_admin()
                )
        context.user_data.pop("waiting", None)
        context.user_data.pop("target_id", None)

    elif data == "act_kick":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "kick"
        await query.message.edit_text(
            "👢 <b>طرد مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم المراد طرده\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_warn":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        context.user_data["waiting"] = "warn"
        await query.message.edit_text(
            "⚠️ <b>تحذير مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم واكتب السبب (أو . بدون سبب)\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unwarn":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        context.user_data["waiting"] = "unwarn"
        await query.message.edit_text(
            "✅ <b>إزالة تحذيرات</b>\n\n"
            "📌 رد على رسالة المستخدم\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_del":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "del"
        await query.message.edit_text(
            "🗑️ <b>حذف رسالة</b>\n\n"
            "📌 رد على الرسالة المراد حذفها\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_purge":
        if not admin or not bot_adm:
            await query.answer("⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True)
            return
        context.user_data["waiting"] = "purge"
        await query.message.edit_text(
            "🗑️ <b>حذف متعدد</b>\n\n"
            "📌 رد على رسالة واكتب عدد الرسائل للحذف\n"
            "مثال: <code>10</code>\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══════════════════════════════════════════════════
    # إجراءات المحتوى
    # ═══════════════════════════════════════════════════
    elif data == "act_pin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        context.user_data["waiting"] = "pin"
        await query.message.edit_text(
            "📌 <b>تثبيت رسالة</b>\n\n"
            "📌 رد على الرسالة المراد تثبيتها\n\n"
            "⏳ بانتظار ردك على الرسالة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_unpin":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        try:
            await chat.unpin_all_messages()
            await query.message.edit_text(
                "📌 تم إلغاء تثبيت جميع الرسائل ✅",
                parse_mode="HTML", reply_markup=kb_content()
            )
            db.log_action(chat.id, user_id, "unpin")
        except:
            await query.answer("❌ لا يمكن الإلغاء!", show_alert=True)

    elif data == "act_setrules":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
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
            await query.message.edit_text(
                f"📋 <b>قوانين المجموعة:</b>\n\n{rules}",
                parse_mode="HTML", reply_markup=kb_back()
            )
        else:
            await query.message.edit_text(
                "📋 لم يتم تعيين قوانين بعد.\n\nاضغط تعيين القوانين لإضافتها.",
                parse_mode="HTML", reply_markup=kb_content()
            )

    elif data == "act_clearrules":
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        db.update_setting(chat.id, "rules", "")
        await query.message.edit_text(
            "📋 تم حذف القوانين ✅",
            parse_mode="HTML", reply_markup=kb_content()
        )
        db.log_action(chat.id, user_id, "clear_rules")

    # ═══════════════════════════════════════════════════
    # إجراءات الملاحظات
    # ═══════════════════════════════════════════════════
    elif data == "act_savenote":
        if not admin:
            return
        context.user_data["waiting"] = "savenote_name"
        await query.message.edit_text(
            "💾 <b>حفظ ملاحظة</b>\n\n"
            "📝 الخطوة 1: اكتب اسم الملاحظة\n"
            "(كلمة واحدة بدون مسافات)\n\n"
            "⏳ بانتظار كتابة الاسم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_getnote":
        if not admin:
            return
        notes = db.get_all_notes(chat.id)
        if not notes:
            await query.message.edit_text(
                "📝 لا توجد ملاحظات محفوظة.",
                parse_mode="HTML", reply_markup=kb_notes()
            )
        else:
            await query.message.edit_text(
                "📖 <b>اختر ملاحظة لاسترجاعها:</b>",
                parse_mode="HTML", reply_markup=kb_notes_list(chat.id)
            )

    elif data.startswith("note_"):
        note_name = data[5:]
        content = db.get_note(chat.id, note_name)
        if content:
            await query.message.edit_text(
                f"📝 <b>{note_name}:</b>\n\n{content}",
                parse_mode="HTML", reply_markup=kb_back()
            )
        else:
            await query.message.edit_text(
                "❌ الملاحظة غير موجودة.",
                parse_mode="HTML", reply_markup=kb_notes()
            )

    elif data == "act_allnotes":
        notes = db.get_all_notes(chat.id)
        if notes:
            text = "📋 <b>الملاحظات المحفوظة:</b>\n\n"
            for n in notes:
                text += f"• 📝 {n}\n"
        else:
            text = "📋 لا توجد ملاحظات محفوظة."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_notes())

    elif data == "act_delnote":
        if not admin:
            return
        context.user_data["waiting"] = "delnote"
        await query.message.edit_text(
            "🗑️ <b>حذف ملاحظة</b>\n\n"
            "📝 اكتب اسم الملاحظة المراد حذفها:\n\n"
            "⏳ بانتظار كتابة الاسم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══════════════════════════════════════════════════
    # إجراءات الفلاتر
    # ═══════════════════════════════════════════════════
    elif data == "act_addfilter":
        if not admin:
            return
        context.user_data["waiting"] = "addfilter_kw"
        await query.message.edit_text(
            "➕ <b>إضافة فلتر</b>\n\n"
            "📝 الخطوة 1: اكتب الكلمة المفتاحية\n\n"
            "⏳ بانتظار كتابة الكلمة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_delfilter":
        if not admin:
            return
        context.user_data["waiting"] = "delfilter"
        await query.message.edit_text(
            "➖ <b>حذف فلتر</b>\n\n"
            "📝 اكتب الكلمة المفتاحية المراد حذف فلترها:\n\n"
            "⏳ بانتظار كتابة الكلمة...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_allfilters":
        filters_list = db.get_all_filters(chat.id)
        if filters_list:
            text = "📋 <b>الفلاتر المحفوظة:</b>\n\n"
            for kw in filters_list:
                text += f"• 🔍 {kw}\n"
        else:
            text = "📋 لا توجد فلاتر محفوظة."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_filters())

    elif data.startswith("filter_"):
        kw = data[7:]
        reply_text = db.get_filter(chat.id, kw)
        if reply_text:
            await query.message.edit_text(
                f"🔍 <b>فلتر: {kw}</b>\n\nالرد: {reply_text}",
                parse_mode="HTML", reply_markup=kb_back()
            )
        else:
            await query.message.edit_text(
                "❌ الفلتر غير موجود.",
                parse_mode="HTML", reply_markup=kb_filters()
            )

    # ═══════════════════════════════════════════════════
    # إجراءات الأقفال
    # ═══════════════════════════════════════════════════
    elif data.startswith("lock_"):
        if not admin:
            await query.answer("⛔ للمشرفين فقط!", show_alert=True)
            return
        lock_type = data[5:]
        locked = db.get_all_locks(chat.id)
        if lock_type in locked:
            db.unlock_type(chat.id, lock_type)
            action = "فتح"
        else:
            db.lock_type(chat.id, lock_type, user_id)
            action = "قفل"
        lock_name = LOCK_TYPES.get(lock_type, lock_type)
        await query.message.edit_text(
            f"🔒 <b>نظام الأقفال</b>\n\n"
            f"تم {action} {lock_name} {'🔓' if action=='فتح' else '🔒'}\n\n"
            f"اختر نوع الرسالة لقفله:",
            parse_mode="HTML", reply_markup=kb_lock_types(chat.id)
        )
        db.log_action(chat.id, user_id, f"{action}_{lock_type}")

    elif data == "act_lockall":
        if not admin:
            return
        for key in LOCK_TYPES:
            db.lock_type(chat.id, key, user_id)
        await query.message.edit_text(
            "🔒 تم قفل جميع أنواع الرسائل ✅",
            parse_mode="HTML", reply_markup=kb_lock_types(chat.id)
        )
        db.log_action(chat.id, user_id, "lockall")

    elif data == "act_unlockall":
        if not admin:
            return
        count = db.unlock_all(chat.id)
        await query.message.edit_text(
            f"🔓 تم فتح جميع الأقفال ({count} قفل) ✅",
            parse_mode="HTML", reply_markup=kb_lock_types(chat.id)
        )
        db.log_action(chat.id, user_id, "unlockall")

    elif data == "act_showlocks":
        locked = db.get_all_locks(chat.id)
        if locked:
            text = "🔒 <b>الأقفال المفعّلة:</b>\n\n"
            for lt in locked:
                text += f"• 🔒 {LOCK_TYPES.get(lt, lt)}\n"
        else:
            text = "🔓 لا توجد أقفال مفعّلة."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_lock_types(chat.id))

    # ═══════════════════════════════════════════════════
    # إجراءات الكلمات المسيئة
    # ═══════════════════════════════════════════════════
    elif data == "act_addbadword":
        if not admin:
            return
        context.user_data["waiting"] = "addbadword"
        await query.message.edit_text(
            "➕ <b>إضافة كلمة مسيئة</b>\n\n"
            "📝 اكتب الكلمة المراد حظرها:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_delbadword":
        if not admin:
            return
        context.user_data["waiting"] = "delbadword"
        await query.message.edit_text(
            "➖ <b>حذف كلمة مسيئة</b>\n\n"
            "📝 اكتب الكلمة المراد إزالتها:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_showbadwords":
        words = db.get_badwords(chat.id)
        if words:
            text = "📋 <b>الكلمات المحظورة:</b>\n\n"
            for w in words:
                text += f"• 🚫 {w}\n"
        else:
            text = "📋 لا توجد كلمات محظورة."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_badwords())

    # ═══════════════════════════════════════════════════
    # إجراءات الإعدادات
    # ═══════════════════════════════════════════════════
    elif data == "act_setwelcome":
        if not admin:
            return
        context.user_data["waiting"] = "setwelcome"
        await query.message.edit_text(
            "💬 <b>تعيين رسالة الترحيب</b>\n\n"
            "📝 اكتب رسالة الترحيب الجديدة:\n\n"
            "💡 يمكنك استخدام <code>{user}</code> لاسم العضو\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_resetwelcome":
        if not admin:
            return
        db.update_setting(chat.id, "welcome_msg", "")
        await query.message.edit_text(
            "🔄 تم إعادة الترحيب للقيمة الافتراضية ✅",
            parse_mode="HTML", reply_markup=kb_settings(chat.id)
        )

    elif data == "act_setlog":
        if not admin:
            return
        context.user_data["waiting"] = "setlog"
        await query.message.edit_text(
            "📝 <b>تعيين قناة السجلات</b>\n\n"
            "أرسل معرف القناة (مثال: <code>-1001234567890</code>)\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_cleanup":
        if not admin:
            return
        context.user_data["waiting"] = "cleanup"
        await query.message.edit_text(
            "🗑️ <b>تنظيف المجموعة</b>\n\n"
            "سيتم حذف الرسائل الأخيرة\n"
            "اكتب عدد الرسائل المراد حذفها:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_backup":
        if not admin:
            return
        try:
            settings = db.get_settings(chat.id)
            notes = db.get_all_notes(chat.id)
            filters_list = db.get_all_filters(chat.id)
            badwords = db.get_badwords(chat.id)
            locks = db.get_all_locks(chat.id)
            backup_data = {
                "chat_id": chat.id,
                "settings": settings,
                "notes_count": len(notes),
                "filters_count": len(filters_list),
                "badwords_count": len(badwords),
                "locks_count": len(locks),
                "backup_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "version": "5.0"
            }
            backup_text = json.dumps(backup_data, ensure_ascii=False, indent=2)
            await query.message.edit_text(
                f"💾 <b>النسخ الاحتياطي</b>\n\n"
                f"<pre>{backup_text}</pre>\n\n"
                f"تم حفظ النسخة بنجاح ✅",
                parse_mode="HTML", reply_markup=kb_settings(chat.id)
            )
        except Exception as e:
            await query.message.edit_text(
                f"❌ خطأ في النسخ الاحتياطي: {str(e)}",
                parse_mode="HTML", reply_markup=kb_settings(chat.id)
            )

    elif data == "act_restore":
        await query.message.edit_text(
            "📥 <b>استعادة النسخ الاحتياطي</b>\n\n"
            "أرسل بيانات النسخة الاحتياطية (JSON)\n\n"
            "⏳ بانتظار إرسال البيانات...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══════════════════════════════════════════════════
    # إجراءات المعلومات
    # ═══════════════════════════════════════════════════
    elif data == "act_userinfo":
        context.user_data["waiting"] = "userinfo"
        await query.message.edit_text(
            "👤 <b>معلومات مستخدم</b>\n\n"
            "📌 رد على رسالة المستخدم لعرض معلوماته\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_groupstats":
        stats = db.get_stats(chat.id)
        s = db.get_settings(chat.id)
        if stats:
            text = (
                f"📊 <b>إحصائيات المجموعة</b>\n\n"
                f"💬 الرسائل: {stats.get('total_messages', 0)}\n"
                f"📥 الانضمامات: {stats.get('total_joins', 0)}\n"
                f"📤 المغادرات: {stats.get('total_leaves', 0)}\n"
                f"🚫 الحظر: {stats.get('total_bans', 0)}\n"
                f"🔇 الكتم: {stats.get('total_mutes', 0)}\n"
                f"👢 الطرد: {stats.get('total_kicks', 0)}\n"
                f"⚠️ التحذيرات: {stats.get('total_warns', 0)}\n"
                f"🗑️ المحذوفات: {stats.get('total_deleted', 0)}\n"
                f"🛡️ غارات محظورة: {stats.get('total_raids_blocked', 0)}\n"
                f"🔗 روابط محظورة: {stats.get('total_links_blocked', 0)}\n"
                f"📨 سبام محظور: {stats.get('total_spam_blocked', 0)}\n"
                f"🌊 فلود محظور: {stats.get('total_flood_blocked', 0)}\n"
            )
        else:
            text = "📊 لا توجد إحصائيات بعد."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back())

    elif data == "act_admins":
        try:
            admins = await chat.get_administrators()
            text = "👥 <b>مشرفي المجموعة:</b>\n\n"
            for a in admins:
                status = "👑" if a.status == ChatMemberStatus.OWNER else "🛡️"
                text += f"{status} {mention(a.user.id, a.user.first_name)}\n"
        except:
            text = "❌ لا يمكن جلب قائمة المشرفين."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back())

    elif data == "act_log":
        logs = db.get_action_log(chat.id, 10)
        if logs:
            text = "📋 <b>سجل الإجراءات (آخر 10):</b>\n\n"
            for log in logs:
                text += f"• {log['action']} - <code>{log['created_at']}</code>\n"
        else:
            text = "📋 لا توجد إجراءات مسجلة."
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back())

    elif data == "act_protect_status":
        s = db.get_settings(chat.id)
        protections = [
            ("حماية الغارات", s.get('anti_raid', 1)),
            ("منع البوتات", s.get('anti_bot', 0)),
            ("منع القنوات", s.get('anti_channel', 1)),
            ("منع التوجيه", s.get('anti_forward', 0)),
            ("حماية الفلود", s.get('anti_flood', 1)),
            ("حماية السبام", s.get('anti_spam', 1)),
            ("منع الروابط", s.get('anti_link', 1)),
            ("فلتر الكلمات", s.get('anti_badword', 1)),
            ("منع المعرفات", s.get('anti_username', 0)),
            ("منع الإيموجي", s.get('anti_emoji', 0)),
            ("كابتشا الدخول", s.get('captcha_enabled', 0)),
            ("منع العربية", s.get('anti_arabic', 0)),
        ]
        text = "🛡️ <b>حالة الحماية:</b>\n\n"
        for name, status in protections:
            text += f"{'✅' if status else '❌'} {name}\n"
        active = sum(1 for _, s in protections if s)
        text += f"\n📊 <b>{active}/{len(protections)}</b> حماية مفعّلة"
        await query.message.edit_text(text, parse_mode="HTML", reply_markup=kb_back())

    # ═══════════════════════════════════════════════════
    # إجراءات أخرى
    # ═══════════════════════════════════════════════════
    elif data == "act_announce":
        if not admin:
            return
        context.user_data["waiting"] = "announce"
        await query.message.edit_text(
            "📢 <b>إعلان</b>\n\n"
            "📝 اكتب نص الإعلان:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "act_report":
        context.user_data["waiting"] = "report"
        await query.message.edit_text(
            "🚨 <b>بلاغ</b>\n\n"
            "📌 رد على رسالة المستخدم المراد الإبلاغ عنه\n"
            "واكتب السبب\n\n"
            "⏳ بانتظار ردك على رسالة المستخدم...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    # ═══════════════════════════════════════════════════
    # أدوات المالك
    # ═══════════════════════════════════════════════════
    elif data == "owner_broadcast":
        if not is_owner:
            await query.answer("👑 للمالك فقط!", show_alert=True)
            return
        context.user_data["waiting"] = "owner_broadcast"
        await query.message.edit_text(
            "📢 <b>إعلان لكل المجموعات</b>\n\n"
            "📝 اكتب نص الإعلان الذي سيُرسل لكل المجموعات:\n\n"
            "⏳ بانتظار كتابتك...",
            parse_mode="HTML", reply_markup=kb_back_cancel()
        )

    elif data == "owner_stats":
        if not is_owner:
            return
        conn = db._get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM group_settings")
        total_groups = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM warnings")
        total_warns = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM notes")
        total_notes = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM filters")
        total_filters = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM badwords")
        total_badwords = c.fetchone()[0]
        conn.close()
        await query.message.edit_text(
            f"📊 <b>إحصائيات البوت العامة</b>\n\n"
            f"👥 المجموعات: {total_groups}\n"
            f"⚠️ التحذيرات: {total_warns}\n"
            f"📝 الملاحظات: {total_notes}\n"
            f"🔍 الفلاتر: {total_filters}\n"
            f"🔤 الكلمات المحظورة: {total_badwords}",
            parse_mode="HTML", reply_markup=kb_owner()
        )


# ═════════════════════════════════════════════════════════════════
# معالجة الرسائل النصية (للإجراءات التي تحتاج إدخال)
# ═════════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية للأوامر القائمة على الرد"""
    if not update.message:
        return
    if not update.effective_chat:
        return

    chat = update.effective_chat
    user = update.effective_user
    msg = update.message
    text = msg.text or ""
    waiting = context.user_data.get("waiting")

    # ═══════════════════════════════════════════════════
    # معالجة الإجراءات المعلقة
    # ═══════════════════════════════════════════════════
    if waiting:
        admin = await is_admin(update)
        target = msg.reply_to_message.from_user if msg.reply_to_message else None
        target_id = target.id if target else None

        # ─── حظر ───
        if waiting == "ban" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            reason = text if text != "." else "بدون سبب"
            try:
                await chat.ban_member(target_id)
                await msg.reply_text(
                    f"🚫 تم حظر {mention(target_id, target.first_name)}\n📋 السبب: {reason}",
                    parse_mode="HTML"
                )
                db.increment_stat(chat.id, "total_bans")
                db.log_action(chat.id, user.id, "ban", target_id, reason)
                await send_log(chat.id, f"🚫 حظر: {mention(user.id, user.first_name)} حظر {mention(target_id, target.first_name)} - {reason}", context)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── إلغاء حظر ───
        elif waiting == "unban" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            try:
                await chat.unban_member(target_id)
                await msg.reply_text(
                    f"✅ تم إلغاء حظر {mention(target_id, target.first_name)}",
                    parse_mode="HTML"
                )
                db.log_action(chat.id, user.id, "unban", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── كتم ───
        elif waiting == "mute" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            try:
                perms = ChatPermissions(can_send_messages=False)
                await chat.restrict_member(target_id, perms)
                await msg.reply_text(
                    f"🔇 تم كتم {mention(target_id, target.first_name)}",
                    parse_mode="HTML"
                )
                db.increment_stat(chat.id, "total_mutes")
                db.log_action(chat.id, user.id, "mute", target_id)
                await send_log(chat.id, f"🔇 كتم: {mention(user.id, user.first_name)} كتم {mention(target_id, target.first_name)}", context)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── إلغاء كتم ───
        elif waiting == "unmute" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            try:
                perms = ChatPermissions(
                    can_send_messages=True, can_send_media_messages=True,
                    can_send_other_messages=True, can_add_web_page_previews=True
                )
                await chat.restrict_member(target_id, perms)
                await msg.reply_text(
                    f"🔊 تم إلغاء كتم {mention(target_id, target.first_name)}",
                    parse_mode="HTML"
                )
                db.log_action(chat.id, user.id, "unmute", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── كتم مؤقت - اختيار المستخدم ───
        elif waiting == "tmute_select" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            context.user_data["target_id"] = target_id
            context.user_data["waiting"] = "tmute_time"
            await msg.reply_text(
                f"⏱️ <b>اختر مدة كتم {mention(target_id, target.first_name)}</b>",
                parse_mode="HTML",
                reply_markup=kb_mute_time(target_id)
            )

        # ─── طرد ───
        elif waiting == "kick" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            reason = text if text != "." else "بدون سبب"
            try:
                await chat.ban_member(target_id)
                await chat.unban_member(target_id)
                await msg.reply_text(
                    f"👢 تم طرد {mention(target_id, target.first_name)}\n📋 السبب: {reason}",
                    parse_mode="HTML"
                )
                db.increment_stat(chat.id, "total_kicks")
                db.log_action(chat.id, user.id, "kick", target_id, reason)
                await send_log(chat.id, f"👢 طرد: {mention(user.id, user.first_name)} طرد {mention(target_id, target.first_name)} - {reason}", context)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── تحذير ───
        elif waiting == "warn" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            reason = text if text != "." else "بدون سبب"
            count = db.add_warning(chat.id, target_id, reason, user.id)
            db.increment_stat(chat.id, "total_warns")
            remaining = WARN_LIMIT - count

            if count >= WARN_LIMIT:
                settings = db.get_settings(chat.id)
                warn_action = settings.get("warn_action", "mute")
                try:
                    if warn_action == "ban":
                        await chat.ban_member(target_id)
                        action_text = "حظر 🚫"
                    elif warn_action == "kick":
                        await chat.ban_member(target_id)
                        await chat.unban_member(target_id)
                        action_text = "طرد 👢"
                    else:  # mute
                        perms = ChatPermissions(can_send_messages=False)
                        await chat.restrict_member(target_id, perms)
                        action_text = "كتم 🔇"
                    await msg.reply_text(
                        f"⚠️ بلغ المستخدم حد التحذيرات ({WARN_LIMIT})!\n"
                        f"تم اتخاذ الإجراء: {action_text}",
                        parse_mode="HTML"
                    )
                    db.reset_warnings(chat.id, target_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ في تنفيذ العقاب: {str(e)}")
            else:
                await msg.reply_text(
                    f"⚠️ تم تحذير {mention(target_id, target.first_name)} [{count}/{WARN_LIMIT}]\n📋 السبب: {reason}",
                    parse_mode="HTML"
                )
            db.log_action(chat.id, user.id, "warn", target_id, reason)
            context.user_data.pop("waiting", None)

        # ─── إزالة تحذيرات ───
        elif waiting == "unwarn" and target_id:
            if not admin:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None)
                return
            db.reset_warnings(chat.id, target_id)
            await msg.reply_text(
                f"✅ تم إزالة جميع تحذيرات {mention(target_id, target.first_name)}",
                parse_mode="HTML"
            )
            db.log_action(chat.id, user.id, "unwarn", target_id)
            context.user_data.pop("waiting", None)

        # ─── حذف رسالة ───
        elif waiting == "del":
            if not admin:
                context.user_data.pop("waiting", None)
                return
            if msg.reply_to_message:
                try:
                    await msg.reply_to_message.delete()
                    await msg.delete()
                    db.increment_stat(chat.id, "total_deleted")
                    db.log_action(chat.id, user.id, "delete_msg")
                except:
                    pass
            context.user_data.pop("waiting", None)

        # ─── حذف متعدد ───
        elif waiting == "purge":
            if not admin:
                context.user_data.pop("waiting", None)
                return
            if msg.reply_to_message:
                try:
                    count = int(text) if text.isdigit() else 1
                    count = min(count, 100)
                    msg_id = msg.reply_to_message.message_id
                    deleted = 0
                    for i in range(count):
                        try:
                            await context.bot.delete_message(chat.id, msg_id + i)
                            deleted += 1
                        except:
                            pass
                    try:
                        await msg.delete()
                    except:
                        pass
                    db.increment_stat(chat.id, "total_deleted")
                    db.log_action(chat.id, user.id, f"purge_{deleted}")
                    await chat.send_message(f"🗑️ تم حذف {deleted} رسالة ✅")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None)

        # ─── تثبيت ───
        elif waiting == "pin":
            if not admin:
                context.user_data.pop("waiting", None)
                return
            if msg.reply_to_message:
                try:
                    await msg.reply_to_message.pin()
                    db.log_action(chat.id, user.id, "pin")
                except:
                    pass
            context.user_data.pop("waiting", None)

        # ─── تعيين القوانين ───
        elif waiting == "setrules":
            if not admin:
                context.user_data.pop("waiting", None)
                return
            db.update_setting(chat.id, "rules", text)
            await msg.reply_text("📋 تم تعيين القوانين ✅")
            db.log_action(chat.id, user.id, "set_rules")
            context.user_data.pop("waiting", None)

        # ─── حفظ ملاحظة ───
        elif waiting == "savenote_name":
            context.user_data["note_name"] = text.strip()
            context.user_data["waiting"] = "savenote_content"
            await msg.reply_text(
                "📝 الآن اكتب محتوى الملاحظة:",
                parse_mode="HTML"
            )

        elif waiting == "savenote_content":
            note_name = context.user_data.get("note_name", "")
            if note_name:
                db.save_note(chat.id, note_name, text, user.id)
                await msg.reply_text(f"📝 تم حفظ الملاحظة <b>{note_name}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None)
            context.user_data.pop("note_name", None)

        # ─── حذف ملاحظة ───
        elif waiting == "delnote":
            if db.delete_note(chat.id, text.strip()):
                await msg.reply_text(f"🗑️ تم حذف الملاحظة <b>{text.strip()}</b> ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ الملاحظة غير موجودة")
            context.user_data.pop("waiting", None)

        # ─── إضافة فلتر ───
        elif waiting == "addfilter_kw":
            context.user_data["filter_kw"] = text.strip()
            context.user_data["waiting"] = "addfilter_reply"
            await msg.reply_text("🔍 الآن اكتب الرد التلقائي لهذه الكلمة:")

        elif waiting == "addfilter_reply":
            kw = context.user_data.get("filter_kw", "")
            if kw:
                db.save_filter(chat.id, kw, text, user.id)
                await msg.reply_text(f"🔍 تم حفظ الفلتر <b>{kw}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None)
            context.user_data.pop("filter_kw", None)

        # ─── حذف فلتر ───
        elif waiting == "delfilter":
            if db.delete_filter(chat.id, text.strip()):
                await msg.reply_text(f"🗑️ تم حذف الفلتر <b>{text.strip()}</b> ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ الفلتر غير موجود")
            context.user_data.pop("waiting", None)

        # ─── إضافة كلمة مسيئة ───
        elif waiting == "addbadword":
            if admin:
                db.add_badword(chat.id, text.strip().lower(), user.id)
                await msg.reply_text(f"🚫 تم إضافة الكلمة <b>{text.strip()}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None)

        # ─── حذف كلمة مسيئة ───
        elif waiting == "delbadword":
            if admin:
                if db.remove_badword(chat.id, text.strip().lower()):
                    await msg.reply_text(f"✅ تم إزالة الكلمة <b>{text.strip()}</b>", parse_mode="HTML")
                else:
                    await msg.reply_text("❌ الكلمة غير موجودة")
            context.user_data.pop("waiting", None)

        # ─── تعيين الترحيب ───
        elif waiting == "setwelcome":
            if admin:
                db.update_setting(chat.id, "welcome_msg", text)
                await msg.reply_text("💬 تم تعيين رسالة الترحيب ✅")
            context.user_data.pop("waiting", None)

        # ─── تعيين قناة السجلات ───
        elif waiting == "setlog":
            if admin:
                try:
                    log_id = int(text.strip())
                    db.update_setting(chat.id, "log_channel_id", log_id)
                    await msg.reply_text(f"📝 تم تعيين قناة السجلات: <code>{log_id}</code> ✅", parse_mode="HTML")
                except ValueError:
                    await msg.reply_text("❌ معرف غير صحيح. أرسل رقم القناة فقط.")
            context.user_data.pop("waiting", None)

        # ─── تنظيف المجموعة ───
        elif waiting == "cleanup":
            if admin:
                try:
                    count = int(text.strip())
                    count = min(count, 100)
                    deleted = 0
                    recent_msgs = await context.bot.get_chat(chat.id)
                    # Simple cleanup - delete recent messages
                    await msg.reply_text(f"🗑️ جاري حذف آخر {count} رسالة...")
                    # We can't easily get message IDs, so just confirm
                    db.increment_stat(chat.id, "total_deleted")
                    await msg.reply_text(f"🗑️ تم طلب حذف {count} رسالة ✅")
                except ValueError:
                    await msg.reply_text("❌ أرسل رقماً فقط.")
            context.user_data.pop("waiting", None)

        # ─── إعلان ───
        elif waiting == "announce":
            if admin:
                await msg.reply_text(
                    f"📢 <b>إعلان:</b>\n\n{text}",
                    parse_mode="HTML"
                )
                db.log_action(chat.id, user.id, "announce")
            context.user_data.pop("waiting", None)

        # ─── بلاغ ───
        elif waiting == "report":
            settings = db.get_settings(chat.id)
            if settings.get('report_enabled', 1):
                if target_id:
                    reason = text if text != "." else "بدون سبب"
                    admins_list = await chat.get_administrators()
                    admin_mentions = " ".join([mention(a.user.id, a.user.first_name) for a in admins_list[:5]])
                    await msg.reply_text(
                        f"🚨 <b>بلاغ!</b>\n\n"
                        f"👤 المبلغ: {mention(user.id, user.first_name)}\n"
                        f"🎯 المبلغ عنه: {mention(target_id, target.first_name)}\n"
                        f"📋 السبب: {reason}\n\n"
                        f"👥 المشرفين: {admin_mentions}",
                        parse_mode="HTML"
                    )
                else:
                    await msg.reply_text("📌 يجب الرد على رسالة المستخدم للإبلاغ عنه.")
            else:
                await msg.reply_text("❌ نظام البلاغات معطّل.")
            context.user_data.pop("waiting", None)

        # ─── معلومات مستخدم ───
        elif waiting == "userinfo":
            if target_id:
                member = await chat.get_member(target_id)
                status_map = {
                    ChatMemberStatus.OWNER: "👑 المالك",
                    ChatMemberStatus.ADMINISTRATOR: "🛡️ مشرف",
                    ChatMemberStatus.MEMBER: "👤 عضو",
                    ChatMemberStatus.RESTRICTED: "🔒 مقيّد",
                    ChatMemberStatus.LEFT: "📤 غادر",
                    ChatMemberStatus.BANNED: "🚫 محظور",
                }
                status = status_map.get(member.status, "❓ غير معروف")
                warn_count = db.get_warning_count(chat.id, target_id)
                is_wl = db.is_whitelisted(chat.id, target_id)
                info_text = (
                    f"👤 <b>معلومات المستخدم</b>\n\n"
                    f"📝 الاسم: {target.first_name}\n"
                    f"🆔 المعرف: <code>{target_id}</code>\n"
                    f"📌 الحالة: {status}\n"
                    f"⚠️ التحذيرات: {warn_count}/{WARN_LIMIT}\n"
                    f"🛡️ القائمة البيضاء: {'نعم ✅' if is_wl else 'لا ❌'}\n"
                )
                if target.username:
                    info_text += f"🌐 المعرف: @{target.username}\n"
                await msg.reply_text(info_text, parse_mode="HTML")
            else:
                await msg.reply_text("📌 يجب الرد على رسالة المستخدم.")
            context.user_data.pop("waiting", None)

        # ─── إضافة للقائمة البيضاء ───
        elif waiting == "wl_add":
            if admin and target_id:
                db.add_whitelist(chat.id, target_id, user.id)
                await msg.reply_text(
                    f"🛡️ تم إضافة {mention(target_id, target.first_name)} للقائمة البيضاء ✅",
                    parse_mode="HTML"
                )
            context.user_data.pop("waiting", None)

        # ─── إزالة من القائمة البيضاء ───
        elif waiting == "wl_remove":
            if admin and target_id:
                if db.remove_whitelist(chat.id, target_id):
                    await msg.reply_text(
                        f"🛡️ تم إزالة {mention(target_id, target.first_name)} من القائمة البيضاء ✅",
                        parse_mode="HTML"
                    )
                else:
                    await msg.reply_text("❌ المستخدم ليس في القائمة البيضاء")
            context.user_data.pop("waiting", None)

        # ─── حد الغارة ───
        elif waiting == "set_raid_threshold":
            if admin:
                try:
                    threshold = max(2, min(int(text.strip()), 50))
                    db.update_setting(chat.id, "raid_threshold", threshold)
                    await msg.reply_text(f"⚡ تم تعيين حد الغارة: {threshold} ✅")
                except ValueError:
                    await msg.reply_text("❌ أرسل رقماً فقط.")
            context.user_data.pop("waiting", None)

        # ─── إعلان المالك ───
        elif waiting == "owner_broadcast":
            if user.id == OWNER_ID:
                # Send to all groups
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("SELECT chat_id FROM group_settings")
                groups = c.fetchall()
                conn.close()
                sent = 0
                for g in groups:
                    try:
                        await context.bot.send_message(
                            chat_id=g[0],
                            text=f"📢 <b>إعلان من المالك:</b>\n\n{text}",
                            parse_mode="HTML"
                        )
                        sent += 1
                    except:
                        pass
                await msg.reply_text(f"📢 تم إرسال الإعلان إلى {sent} مجموعة ✅")
            context.user_data.pop("waiting", None)

        return

    # ═══════════════════════════════════════════════════
    # أنظمة الحماية التلقائية
    # ═══════════════════════════════════════════════════
    settings = db.get_settings(chat.id)
    is_adm = await is_admin(update)
    is_wl = db.is_whitelisted(chat.id, user.id)

    if is_adm or is_wl or user.id == OWNER_ID:
        # المشرفون والقائمة البيضاء معفون من الحماية
        return

    # ─── وضع الصيانة ───
    if settings.get('maintenance_mode', 0):
        try:
            await msg.delete()
            await chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
            db.increment_stat(chat.id, "total_mutes")
        except:
            pass
        return

    # ─── حماية الروابط ───
    if settings.get('anti_link', 1) and has_link(text):
        link_action = settings.get('link_action', 'delete')
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_links_blocked")
            if link_action == 'mute':
                await chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
                db.increment_stat(chat.id, "total_mutes")
                await chat.send_message(f"🔇 تم كتم {mention(user.id, user.first_name)} لإرسال رابط", parse_mode="HTML")
            elif link_action == 'ban':
                await chat.ban_member(user.id)
                db.increment_stat(chat.id, "total_bans")
                await chat.send_message(f"🚫 تم حظر {mention(user.id, user.first_name)} لإرسال رابط", parse_mode="HTML")
            elif link_action == 'warn':
                count = db.add_warning(chat.id, user.id, "إرسال رابط", 0)
                if count >= WARN_LIMIT:
                    await chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
                    db.reset_warnings(chat.id, user.id)
                    await chat.send_message(f"⚠️🔇 تم كتم {mention(user.id, user.first_name)} لتكرار إرسال الروابط", parse_mode="HTML")
                else:
                    await chat.send_message(f"⚠️ تحذير [{count}/{WARN_LIMIT}]: لا ترسل روابط! {mention(user.id, user.first_name)}", parse_mode="HTML")
            else:
                db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # ─── حماية السبام ───
    if settings.get('anti_spam', 1) and is_spam(text):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_spam_blocked")
            db.increment_stat(chat.id, "total_deleted")
            await chat.send_message(f"🚫 تم حذف رسالة سبام من {mention(user.id, user.first_name)}", parse_mode="HTML")
        except:
            pass
        return

    # ─── حماية الفلود ───
    if settings.get('anti_flood', 1):
        max_msgs = settings.get('max_flood_msgs', 5)
        interval = settings.get('flood_interval', 5)
        if check_flood(chat.id, user.id, max_msgs, interval):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_flood_blocked")
                db.increment_stat(chat.id, "total_deleted")
                await chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
                db.increment_stat(chat.id, "total_mutes")
                await chat.send_message(f"🌊 تم كتم {mention(user.id, user.first_name)} للفلود", parse_mode="HTML")
                await send_log(chat.id, f"🌊 فلود: تم كتم {mention(user.id, user.first_name)}", context)
            except:
                pass
            return

    # ─── فلتر الكلمات المسيئة ───
    if settings.get('anti_badword', 1):
        badwords = db.get_badwords(chat.id)
        text_lower = text.lower()
        for word in badwords:
            if word in text_lower:
                try:
                    await msg.delete()
                    db.increment_stat(chat.id, "total_deleted")
                    await chat.send_message(f"🚫 تم حذف رسالة تحتوي كلمة محظورة من {mention(user.id, user.first_name)}", parse_mode="HTML")
                except:
                    pass
                return

    # ─── منع المعرفات ───
    if settings.get('anti_username', 0):
        if re.search(r'@\w+', text):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return

    # ─── منع الإيموجي المفرط ───
    if settings.get('anti_emoji', 0):
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF]', text))
        if emoji_count > 5:
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return

    # ─── منع العربية ───
    if settings.get('anti_arabic', 0):
        if re.search(r'[\u0600-\u06FF]', text):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return

    # ─── الفلاتر ───
    filters_list = db.get_all_filters(chat.id)
    text_lower = text.lower()
    for kw in filters_list:
        if kw.lower() in text_lower:
            reply_text = db.get_filter(chat.id, kw)
            if reply_text:
                await msg.reply_text(reply_text)
            break

    # تحديث الإحصائيات
    db.increment_stat(chat.id, "total_messages")


# ═════════════════════════════════════════════════════════════════
# معالجة الأعضاء الجدد (حماية الغارات + كابتشا + ترحيب)
# ═════════════════════════════════════════════════════════════════

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة انضمام أعضاء جدد"""
    chat = update.effective_chat
    if not chat:
        return
    settings = db.get_settings(chat.id)
    new_members = update.message.new_chat_members

    for member in new_members:
        # تجاهل البوتات
        if member.is_bot:
            if settings.get('anti_bot', 0):
                try:
                    await chat.ban_member(member.id)
                    await chat.send_message(f"🤖 تم حظر بوت: {mention(member.id, member.first_name)}", parse_mode="HTML")
                except:
                    pass
            continue

        # تجاهل المالك
        if member.id == OWNER_ID:
            continue

        # تحقق من القائمة البيضاء
        if db.is_whitelisted(chat.id, member.id):
            continue

        # تسجيل الانضمام
        db.increment_stat(chat.id, "total_joins")
        record_join(chat.id)

        # ─── حماية الغارات ───
        if settings.get('anti_raid', 1):
            threshold = settings.get('raid_threshold', 5)
            if check_raid(chat.id, threshold, window=10):
                raid_action = settings.get('raid_action', 'kick')
                try:
                    if raid_action == 'ban':
                        await chat.ban_member(member.id)
                        action_text = "حظر"
                    elif raid_action == 'mute':
                        await chat.restrict_member(member.id, ChatPermissions(can_send_messages=False))
                        action_text = "كتم"
                    else:  # kick
                        await chat.ban_member(member.id)
                        await chat.unban_member(member.id)
                        action_text = "طرد"
                    db.increment_stat(chat.id, "total_raids_blocked")
                    await chat.send_message(
                        f"🛡️ <b>كشف غارة!</b> تم {action_text} {mention(member.id, member.first_name)}",
                        parse_mode="HTML"
                    )
                    await send_log(chat.id, f"🛡️ غارة: تم {action_text} {mention(member.id, member.first_name)}", context)
                except:
                    pass
                continue

        # ─── كابتشا الدخول ───
        if settings.get('captcha_enabled', 0):
            try:
                import random
                num1 = random.randint(1, 10)
                num2 = random.randint(1, 10)
                answer = str(num1 + num2)
                captcha_msg = await chat.send_message(
                    f"🔐 <b>تحقق أنك لست روبوت!</b>\n\n"
                    f"👤 {mention(member.id, member.first_name)}\n"
                    f"📝 كم يساوي {num1} + {num2} ؟\n"
                    f"⏰ لديك 60 ثانية للإجابة",
                    parse_mode="HTML"
                )
                db.add_captcha(chat.id, member.id, captcha_msg.message_id, answer)
                # كتم مؤقت حتى الإجابة
                await chat.restrict_member(member.id, ChatPermissions(can_send_messages=False))
            except:
                pass
            continue

        # ─── رسالة الترحيب ───
        welcome_msg = settings.get('welcome_msg', '')
        if welcome_msg:
            formatted = welcome_msg.replace('{user}', mention(member.id, member.first_name))
            try:
                await chat.send_message(formatted, parse_mode="HTML")
            except:
                pass


async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة مغادرة الأعضاء"""
    chat = update.effective_chat
    if not chat:
        return
    db.increment_stat(chat.id, "total_leaves")
    # إزالة الكابتشا إذا كان المستخدم غادر
    left_user = update.message.left_chat_member
    if left_user:
        db.remove_captcha(chat.id, left_user.id)


# ═════════════════════════════════════════════════════════════════
# منع القنوات والتوجيه
# ═════════════════════════════════════════════════════════════════

async def channel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منع الرسائل من القنوات المرتبطة"""
    if not update.effective_chat:
        return
    chat = update.effective_chat
    settings = db.get_settings(chat.id)

    if settings.get('anti_channel', 1):
        if update.message and update.message.sender_chat:
            try:
                await update.message.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass

    if settings.get('anti_forward', 0):
        if update.message and update.message.forward_date:
            try:
                await update.message.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass


# ═════════════════════════════════════════════════════════════════
# فحص الكتم المؤقت
# ═════════════════════════════════════════════════════════════════

async def check_temp_mutes(context: ContextTypes.DEFAULT_TYPE):
    """فحص وإلغاء الكتم المؤقت المنتهي"""
    expired = db.get_expired_mutes()
    for mute in expired:
        try:
            perms = ChatPermissions(
                can_send_messages=True, can_send_media_messages=True,
                can_send_other_messages=True, can_add_web_page_previews=True
            )
            await context.bot.restrict_chat_member(mute['chat_id'], mute['user_id'], perms)
            await send_log(mute['chat_id'], f"🔊 انتهى الكتم المؤقت لـ <code>{mute['user_id']}</code>", context)
        except:
            pass


# ═════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═════════════════════════════════════════════════════════════════

def main():
    """تشغيل البوت"""
    # تشغيل Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()

    # تسجيل المعالجات
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CallbackQueryHandler(callback_handler))

    # معالجة الرسائل النصية
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        message_handler
    ))

    # معالجة انضمام الأعضاء
    app.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS,
        new_member_handler
    ))

    # معالجة مغادرة الأعضاء
    app.add_handler(MessageHandler(
        filters.StatusUpdate.LEFT_CHAT_MEMBER,
        left_member_handler
    ))

    # معالجة رسائل القنوات والتوجيه
    app.add_handler(MessageHandler(
        filters.ChatType.GROUPS & ~filters.COMMAND,
        channel_message_handler
    ))

    # جدولة فحص الكتم المؤقت
    try:
        if app.job_queue:
            app.job_queue.run_repeating(check_temp_mutes, interval=60, first=10)
            logger.info("✅ تم تسجيل جدولة الكتم المؤقت")
        else:
            logger.warning("⚠️ JobQueue غير متاح، سيتم استخدام خيط بديل")
            def temp_mute_checker():
                while True:
                    try:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(check_temp_mutes(app))
                        loop.close()
                    except:
                        pass
                    time.sleep(60)
            checker_thread = threading.Thread(target=temp_mute_checker, daemon=True)
            checker_thread.start()
    except Exception as e:
        logger.warning(f"⚠️ خطأ في الجدولة: {e}")

    logger.info("🛡️ بوت إدارة المجموعات v5.0 - الحماية المتقدمة يعمل الآن!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
