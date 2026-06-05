"""
╔══════════════════════════════════════════════════════════════════╗
║    🛡️ بوت إدارة المجموعات المتكامل v6.0 - الإصدار الخارق 🛡️    ║
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
import random
import asyncio
from datetime import datetime, timedelta
from flask import Flask, jsonify
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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
TOKEN = os.environ.get("TOKEN", "")
OWNER_ID = 8947599931
WARN_LIMIT = 3
DEFAULT_WELCOME = "مرحباً بك يا {user} في مجموعتنا! 🎉\nيرجى قراءة القوانين"
DB_PATH = "bot_database.db"

SUDO_USERS = {OWNER_ID}

# ═════════════════════════════════════════════════════════════════
# خادم Flask للحفاظ على البوت نشطاً
# ═════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return jsonify({
        "status": "running",
        "bot": "Group Manager v6.0",
        "uptime": True
    }), 200

@web_app.route('/health')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port, use_reloader=False)

# ═════════════════════════════════════════════════════════════════
# نظام قاعدة البيانات SQLite
# ═════════════════════════════════════════════════════════════════
class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
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
                anti_phone INTEGER DEFAULT 0,
                anti_longmsg INTEGER DEFAULT 0,
                anti_edit INTEGER DEFAULT 0,
                report_enabled INTEGER DEFAULT 1,
                captcha_enabled INTEGER DEFAULT 0,
                max_flood_msgs INTEGER DEFAULT 5,
                flood_interval INTEGER DEFAULT 5,
                raid_threshold INTEGER DEFAULT 5,
                raid_action TEXT DEFAULT 'kick',
                link_action TEXT DEFAULT 'delete',
                warn_action TEXT DEFAULT 'mute',
                auto_delete INTEGER DEFAULT 0,
                slow_mode INTEGER DEFAULT 0,
                max_msg_length INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, user_id INTEGER, reason TEXT DEFAULT '',
                warned_by INTEGER, warned_at TEXT DEFAULT CURRENT_TIMESTAMP
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
                total_deleted INTEGER DEFAULT 0, total_kicks INTEGER DEFAULT 0,
                total_raids_blocked INTEGER DEFAULT 0, total_links_blocked INTEGER DEFAULT 0,
                total_spam_blocked INTEGER DEFAULT 0, total_flood_blocked INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
            c.execute('''CREATE TABLE IF NOT EXISTS whitelist (
                chat_id INTEGER, user_id INTEGER, added_by INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(chat_id, user_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS captcha_pending (
                chat_id INTEGER, user_id INTEGER, message_id INTEGER,
                correct_answer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS user_reputation (
                chat_id INTEGER, user_id INTEGER, rep INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS msg_count (
                chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )''')
            c.execute('''CREATE TABLE IF NOT EXISTS admins_cache (
                chat_id INTEGER, user_id INTEGER, role TEXT DEFAULT 'admin',
                cached_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN auto_delete INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN slow_mode INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN max_msg_length INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN anti_phone INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN anti_longmsg INTEGER DEFAULT 0")
            except:
                pass
            try:
                c.execute("ALTER TABLE group_settings ADD COLUMN anti_edit INTEGER DEFAULT 0")
            except:
                pass
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
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM group_settings WHERE chat_id = ?", (chat_id,))
            row = c.fetchone()
            conn.close()
            return dict(row) if row else {}

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

    def remove_captcha(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            conn.commit()
            conn.close()

    def get_all_group_ids(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT chat_id FROM group_settings")
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    def add_rep(self, chat_id, user_id, amount=1):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO user_reputation (chat_id, user_id, rep) VALUES (?, ?, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET rep = rep + ?",
                     (chat_id, user_id, amount, amount))
            c.execute("SELECT rep FROM user_reputation WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            rep = c.fetchone()[0]
            conn.commit()
            conn.close()
            return rep

    def get_rep(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT rep FROM user_reputation WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row[0] if row else 0

    def get_top_rep(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, rep FROM user_reputation WHERE chat_id = ? ORDER BY rep DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [(row[0], row[1]) for row in rows]

    def increment_msg_count(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO msg_count (chat_id, user_id, count) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1",
                     (chat_id, user_id))
            conn.commit()
            conn.close()

    def get_msg_count(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT count FROM msg_count WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row[0] if row else 0

    def get_top_msg(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, count FROM msg_count WHERE chat_id = ? ORDER BY count DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [(row[0], row[1]) for row in rows]


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
}

MUTE_TIMES = [
    ("1 دقيقة", "1m"), ("5 دقائق", "5m"), ("10 دقائق", "10m"),
    ("30 دقيقة", "30m"), ("1 ساعة", "1h"), ("6 ساعات", "6h"),
    ("12 ساعة", "12h"), ("1 يوم", "1d"), ("3 أيام", "3d"), ("7 أيام", "7d"),
]

RAID_ACTIONS = {"kick": "طرد 👢", "ban": "حظر 🚫", "mute": "كتم 🔇"}
LINK_ACTIONS = {"delete": "حذف الرسالة 🗑️", "mute": "كتم 🔇", "ban": "حظر 🚫", "warn": "تحذير ⚠️"}
WARN_ACTIONS = {"mute": "كتم 🔇", "kick": "طرد 👢", "ban": "حظر 🚫"}

# ═════════════════════════════════════════════════════════════════
# أنظمة الحماية
# ═════════════════════════════════════════════════════════════════
flood_data = {}
raid_data = {}
slow_mode_data = {}

def check_flood(chat_id, user_id, max_msgs=5, interval=5):
    now = time.time()
    if chat_id not in flood_data:
        flood_data[chat_id] = {}
    if user_id not in flood_data[chat_id]:
        flood_data[chat_id][user_id] = []
    flood_data[chat_id][user_id].append(now)
    flood_data[chat_id][user_id] = [t for t in flood_data[chat_id][user_id] if now - t <= interval]
    return len(flood_data[chat_id][user_id]) > max_msgs

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

def check_slow_mode(chat_id, user_id, seconds):
    if seconds <= 0:
        return False
    now = time.time()
    key = (chat_id, user_id)
    if key in slow_mode_data:
        if now - slow_mode_data[key] < seconds:
            return True
    slow_mode_data[key] = now
    return False

URL_PATTERN = re.compile(r'(https?://[^\s]+)|(t\.me/[^\s]+)', re.IGNORECASE)
PHONE_PATTERN = re.compile(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
USERNAME_PATTERN = re.compile(r'@[\w]{5,}')

def has_link(text):
    if not text:
        return False
    return bool(URL_PATTERN.search(text))

def has_phone(text):
    if not text:
        return False
    return bool(PHONE_PATTERN.search(text))

def has_username(text):
    if not text:
        return False
    return bool(USERNAME_PATTERN.search(text))

def is_spam(text):
    if not text:
        return False
    if re.search(r'(.)\1{8,}', text):
        return True
    if re.search(r'(.{3,})\1{4,}', text):
        return True
    return False

# ═════════════════════════════════════════════════════════════════
# دوال مساعدة
# ═════════════════════════════════════════════════════════════════

async def check_is_admin(chat, user_id: int) -> bool:
    try:
        if user_id == OWNER_ID or user_id in SUDO_USERS:
            return True
        if chat is None:
            return False
        member = await chat.get_member(user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"check_is_admin error: {e}")
        return user_id == OWNER_ID

async def check_bot_admin(chat, bot_id: int) -> bool:
    try:
        if chat is None:
            return False
        member = await chat.get_member(bot_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception as e:
        logger.error(f"check_bot_admin error: {e}")
        return False

def mention(user_id, name):
    safe_name = name if name else "مستخدم"
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

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
        return f"{seconds // 3600} ساعة"
    elif seconds >= 60:
        return f"{seconds // 60} دقيقة"
    else:
        return f"{seconds} ثانية"

async def send_log(chat_id, text, context):
    try:
        settings = db.get_settings(chat_id)
        log_channel = settings.get('log_channel_id', 0)
        if log_channel and log_channel != 0:
            await context.bot.send_message(chat_id=log_channel, text=text, parse_mode="HTML")
    except:
        pass

async def safe_edit(query, text, reply_markup=None, parse_mode="HTML"):
    try:
        await query.message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        if "Message is not modified" not in str(e):
            try:
                await query.message.delete()
                await query.message.chat.send_message(text, parse_mode=parse_mode, reply_markup=reply_markup)
            except:
                pass

async def safe_answer(query, text="", show_alert=False):
    try:
        await query.answer(text, show_alert=show_alert)
    except:
        pass

# ═════════════════════════════════════════════════════════════════
# نظام اللوحات (Keyboards)
# ═════════════════════════════════════════════════════════════════

def kb_main(is_adm=False):
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
         InlineKeyboardButton("⭐ السمعة", callback_data="menu_reputation")],
        [InlineKeyboardButton("🚨 أخرى", callback_data="menu_other"),
         InlineKeyboardButton("🧹 التنظيف", callback_data="menu_cleanup")],
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
        [InlineKeyboardButton("📈 ترقية مشرف", callback_data="act_promote"),
         InlineKeyboardButton("📉 تخفيض مشرف", callback_data="act_demote")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_protection(chat_id):
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
        [InlineKeyboardButton(f"{'✅' if s.get('anti_phone',0) else '❌'} منع أرقام الهاتف", callback_data="tog_antiphone"),
         InlineKeyboardButton(f"{'✅' if s.get('anti_longmsg',0) else '❌'} منع الرسائل الطويلة", callback_data="tog_antilongmsg")],
        [InlineKeyboardButton(f"{'✅' if s.get('anti_edit',0) else '❌'} منع التعديل", callback_data="tog_antiedit"),
         InlineKeyboardButton(f"{'🐢' if s.get('slow_mode',0) else '🐇'} الوضع البطيء", callback_data="tog_slowmode")],
        [InlineKeyboardButton("⚡ إعدادات الغارة", callback_data="raid_settings"),
         InlineKeyboardButton("🔗 إعدادات الروابط", callback_data="link_settings")],
        [InlineKeyboardButton("⚠️ إعدادات التحذير", callback_data="warn_settings"),
         InlineKeyboardButton("🛡️ القائمة البيضاء", callback_data="menu_whitelist")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ]
    return InlineKeyboardMarkup(buttons)

def kb_mute_time(target_id):
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
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 تثبيت رسالة", callback_data="act_pin"),
         InlineKeyboardButton("📌 إلغاء التثبيت", callback_data="act_unpin")],
        [InlineKeyboardButton("📋 تعيين القوانين", callback_data="act_setrules"),
         InlineKeyboardButton("📋 عرض القوانين", callback_data="act_rules")],
        [InlineKeyboardButton("📋 حذف القوانين", callback_data="act_clearrules"),
         InlineKeyboardButton("📝 وصف المجموعة", callback_data="act_setdesc")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_notes():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💾 حفظ ملاحظة", callback_data="act_savenote"),
         InlineKeyboardButton("📖 استرجاع ملاحظة", callback_data="act_getnote")],
        [InlineKeyboardButton("📋 عرض الكل", callback_data="act_allnotes"),
         InlineKeyboardButton("🗑️ حذف ملاحظة", callback_data="act_delnote")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_notes_list(chat_id):
    notes = db.get_all_notes(chat_id)
    if not notes:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_notes")]])
    buttons = []
    for name in notes[:20]:
        buttons.append([InlineKeyboardButton(f"📝 {name}", callback_data=f"note_{name}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_notes")])
    return InlineKeyboardMarkup(buttons)

def kb_filters():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة فلتر", callback_data="act_addfilter"),
         InlineKeyboardButton("➖ حذف فلتر", callback_data="act_delfilter")],
        [InlineKeyboardButton("📋 عرض الفلاتر", callback_data="act_allfilters")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_lock_types(chat_id):
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
    buttons.append([InlineKeyboardButton("🔒 قفل الكل", callback_data="act_lockall"),
                     InlineKeyboardButton("🔓 فتح الكل", callback_data="act_unlockall")])
    buttons.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")])
    return InlineKeyboardMarkup(buttons)

def kb_badwords():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data="act_addbadword"),
         InlineKeyboardButton("➖ حذف كلمة", callback_data="act_delbadword")],
        [InlineKeyboardButton("📋 عرض الكلمات", callback_data="act_showbadwords")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_settings(chat_id):
    s = db.get_settings(chat_id)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'✅' if s.get('maintenance_mode',0) else '❌'} وضع الصيانة", callback_data="tog_maintenance"),
         InlineKeyboardButton(f"{'✅' if s.get('report_enabled',1) else '❌'} البلاغات", callback_data="tog_report")],
        [InlineKeyboardButton("💬 تعيين الترحيب", callback_data="act_setwelcome"),
         InlineKeyboardButton("🔄 ترحيب افتراضي", callback_data="act_resetwelcome")],
        [InlineKeyboardButton("📝 قناة السجلات", callback_data="act_setlog"),
         InlineKeyboardButton("⏱️ حذف تلقائي", callback_data="act_autodelete")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_info():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 معلومات مستخدم", callback_data="act_userinfo"),
         InlineKeyboardButton("📊 إحصائيات المجموعة", callback_data="act_groupstats")],
        [InlineKeyboardButton("👥 المشرفين", callback_data="act_admins"),
         InlineKeyboardButton("📋 سجل الإجراءات", callback_data="act_log")],
        [InlineKeyboardButton("🛡️ حالة الحماية", callback_data="act_protect_status"),
         InlineKeyboardButton("📈 الأنشط", callback_data="act_topactive")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_reputation():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ إعطاء نقطة", callback_data="act_giverep"),
         InlineKeyboardButton("📊 ترتيب السمعة", callback_data="act_reprank")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_other():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان", callback_data="act_announce"),
         InlineKeyboardButton("🚨 بلاغ", callback_data="act_report")],
        [InlineKeyboardButton("🎰 حظ", callback_data="act_dice"),
         InlineKeyboardButton("🎯 عملة", callback_data="act_coin")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_cleanup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ حذف رسائل بوت", callback_data="clean_bot"),
         InlineKeyboardButton("🗑️ حذف كتم مؤقت", callback_data="clean_tempmutes")],
        [InlineKeyboardButton("🗑️ حذف تحذيرات", callback_data="clean_warns"),
         InlineKeyboardButton("🗑️ حذف إحصائيات", callback_data="clean_stats")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_owner():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان لكل المجموعات", callback_data="owner_broadcast"),
         InlineKeyboardButton("📊 إحصائيات عامة", callback_data="owner_stats")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_raid_settings(chat_id):
    s = db.get_settings(chat_id)
    current_action = s.get('raid_action', 'kick')
    threshold = s.get('raid_threshold', 5)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📊 حد الغارة: {threshold}", callback_data="set_raid_threshold")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='kick' else '⚪'} طرد", callback_data="set_raid_kick"),
         InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_raid_ban"),
         InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_raid_mute")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_link_settings(chat_id):
    s = db.get_settings(chat_id)
    current_action = s.get('link_action', 'delete')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔵' if current_action=='delete' else '⚪'} حذف الرسالة", callback_data="set_link_delete"),
         InlineKeyboardButton(f"{'🔵' if current_action=='warn' else '⚪'} تحذير", callback_data="set_link_warn")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_link_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_link_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_warn_settings(chat_id):
    s = db.get_settings(chat_id)
    current_action = s.get('warn_action', 'mute')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم عند الحد", callback_data="set_warn_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='kick' else '⚪'} طرد عند الحد", callback_data="set_warn_kick")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر عند الحد", callback_data="set_warn_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_whitelist():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة للقائمة البيضاء", callback_data="wl_add"),
         InlineKeyboardButton("➖ إزالة من القائمة", callback_data="wl_remove")],
        [InlineKeyboardButton("📋 عرض القائمة البيضاء", callback_data="wl_show")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])


# ═════════════════════════════════════════════════════════════════
# أوامر /start و /panel و /help
# ═════════════════════════════════════════════════════════════════

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    is_adm = False

    if chat and chat.type != "private":
        is_adm = await check_is_admin(chat, user.id)

    if user.id == OWNER_ID:
        is_adm = True

    text = (
        "🛡️ <b>بوت إدارة المجموعات المتكامل v6.0</b>\n\n"
        "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
        "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
        "📊 <b>إحصائيات شاملة</b> لكل ما يحدث في مجموعتك\n"
        "⭐ <b>نظام سمعة</b> لتقييم أعضاء المجموعة\n"
        "🧹 <b>أدوات تنظيف</b> للحفاظ على نظافة المجموعة\n\n"
        "👇 اختر أي قسم من الأزرار أدناه:"
    )
    try:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb_main(is_adm))
    except Exception as e:
        logger.error(f"start_cmd error: {e}")

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_cmd(update, context)


# ═════════════════════════════════════════════════════════════════
# معالجة الأزرار التفاعلية
# ═════════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await safe_answer(query)
    data = query.data
    chat = update.effective_chat
    user_id = query.from_user.id

    is_adm = await check_is_admin(chat, user_id) if chat else (user_id == OWNER_ID)
    is_owner = user_id == OWNER_ID
    bot_adm = await check_bot_admin(chat, context.bot.id) if chat else False

    try:

    # ═══ القائمة الرئيسية ═══
        if data == "back":
            await safe_edit(query,
                "🛡️ <b>بوت إدارة المجموعات المتكامل v6.0</b>\n\n"
                "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
                "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
                "📊 <b>إحصائيات شاملة</b> لكل ما يحدث في مجموعتك\n"
                "⭐ <b>نظام سمعة</b> لتقييم أعضاء المجموعة\n"
                "🧹 <b>أدوات تنظيف</b> للحفاظ على نظافة المجموعة\n\n"
                "👇 اختر أي قسم من الأزرار أدناه:",
                reply_markup=kb_main(is_adm or is_owner)
            )

        elif data == "cancel":
            context.user_data.pop("waiting", None)
            context.user_data.pop("target_id", None)
            context.user_data.pop("note_name", None)
            context.user_data.pop("filter_kw", None)
            await safe_edit(query, "❌ تم الإلغاء.\n\n👇 اختر من القائمة:",
                reply_markup=kb_main(is_adm or is_owner))

    # ═══ فتح القوائم ═══
        elif data == "menu_admin":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query,
                "🛡️ <b>أوامر الإشراف</b>\n\n"
                "📌 لحظر/كتم/طرد/تحذير: رد على رسالة المستخدم ثم اضغط الزر\n"
                "📌 لحذف رسالة: رد على الرسالة ثم اضغط حذف\n"
                "📌 لترقية/تخفيض: رد على رسالة المستخدم",
                reply_markup=kb_admin())

        elif data == "menu_protection":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query,
                "🔐 <b>نظام الحماية المتقدم</b>\n\nاضغط على أي حماية لتفعيلها/تعطيلها:",
                reply_markup=kb_protection(chat.id))

        elif data == "menu_content":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📌 <b>إدارة المحتوى</b>\n\nاختر الإجراء:", reply_markup=kb_content())

        elif data == "menu_notes":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📝 <b>نظام الملاحظات</b>\n\nاحفظ واسترجع ملاحظات:", reply_markup=kb_notes())

        elif data == "menu_filters":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔍 <b>نظام الفلاتر</b>\n\nأنشئ ردود تلقائية:", reply_markup=kb_filters())

        elif data == "menu_locks":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔒 <b>نظام الأقفال</b>\n\nاختر نوع الرسالة لقفله:", reply_markup=kb_lock_types(chat.id))

        elif data == "menu_badwords":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔤 <b>فلتر الكلمات المسيئة</b>:", reply_markup=kb_badwords())

        elif data == "menu_settings":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "⚙️ <b>إعدادات المجموعة</b>:", reply_markup=kb_settings(chat.id))

        elif data == "menu_info":
            await safe_edit(query, "📊 <b>المعلومات</b>:", reply_markup=kb_info())

        elif data == "menu_reputation":
            await safe_edit(query, "⭐ <b>نظام السمعة</b>\n\nقيّم أعضاء المجموعة!", reply_markup=kb_reputation())

        elif data == "menu_other":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🚨 <b>أوامر أخرى</b>:", reply_markup=kb_other())

        elif data == "menu_cleanup":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🧹 <b>أدوات التنظيف</b>\n\nاحذف البيانات غير الضرورية:", reply_markup=kb_cleanup())

        elif data == "menu_owner":
            if not is_owner:
                await safe_answer(query, "👑 للمالك فقط!", show_alert=True); return
            await safe_edit(query, "👑 <b>أدوات المالك</b>:", reply_markup=kb_owner())

    # ═══ تبديل الحماية ═══
        elif data.startswith("tog_"):
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
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
                "tog_antiphone": ("anti_phone", "منع أرقام الهاتف"),
                "tog_antilongmsg": ("anti_longmsg", "منع الرسائل الطويلة"),
                "tog_antiedit": ("anti_edit", "منع التعديل"),
                "tog_slowmode": ("slow_mode", "الوضع البطيء"),
                "tog_maintenance": ("maintenance_mode", "وضع الصيانة"),
                "tog_report": ("report_enabled", "البلاغات"),
            }
            if data in toggle_map:
                key, name = toggle_map[data]
                s = db.get_settings(chat.id)
                new_val = 0 if s.get(key, 0) else 1
                db.update_setting(chat.id, key, new_val)
                status = "مفعّل ✅" if new_val else "معطّل ❌"
                await safe_edit(query,
                    f"🔐 <b>نظام الحماية</b>\n\nتم {'تفعيل' if new_val else 'تعطيل'} <b>{name}</b> {status}\n\nاضغط على أي حماية:",
                    reply_markup=kb_protection(chat.id))

    # ═══ إعدادات الغارة ═══
        elif data == "raid_settings":
            if not is_adm: return
            await safe_edit(query, "⚡ <b>إعدادات حماية الغارات</b>:", reply_markup=kb_raid_settings(chat.id))
        elif data == "set_raid_threshold":
            if not is_adm: return
            context.user_data["waiting"] = "set_raid_threshold"
            await safe_edit(query, "📊 <b>تعيين حد الغارة</b>\n\nاكتب عدد الأعضاء (2-50):\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data.startswith("set_raid_"):
            if not is_adm: return
            action = data.replace("set_raid_", "")
            if action in RAID_ACTIONS:
                db.update_setting(chat.id, "raid_action", action)
                await safe_edit(query,
                    f"⚡ <b>إعدادات الغارات</b>\n\nالإجراء: {RAID_ACTIONS[action]}",
                    reply_markup=kb_raid_settings(chat.id))

    # ═══ إعدادات الروابط ═══
        elif data == "link_settings":
            if not is_adm: return
            await safe_edit(query, "🔗 <b>إعدادات منع الروابط</b>:", reply_markup=kb_link_settings(chat.id))
        elif data.startswith("set_link_"):
            if not is_adm: return
            action = data.replace("set_link_", "")
            if action in LINK_ACTIONS:
                db.update_setting(chat.id, "link_action", action)
                await safe_edit(query,
                    f"🔗 <b>إعدادات الروابط</b>\n\nالإجراء: {LINK_ACTIONS[action]}",
                    reply_markup=kb_link_settings(chat.id))

    # ═══ إعدادات التحذير ═══
        elif data == "warn_settings":
            if not is_adm: return
            await safe_edit(query,
                f"⚠️ <b>إعدادات التحذيرات</b>\n\nالحد: {WARN_LIMIT}:",
                reply_markup=kb_warn_settings(chat.id))
        elif data.startswith("set_warn_"):
            if not is_adm: return
            action = data.replace("set_warn_", "")
            if action in WARN_ACTIONS:
                db.update_setting(chat.id, "warn_action", action)
                await safe_edit(query,
                    f"⚠️ <b>إعدادات التحذير</b>\n\nالإجراء: {WARN_ACTIONS[action]}",
                    reply_markup=kb_warn_settings(chat.id))

    # ═══ القائمة البيضاء ═══
        elif data == "menu_whitelist":
            if not is_adm: return
            await safe_edit(query, "🛡️ <b>القائمة البيضاء</b>:", reply_markup=kb_whitelist())
        elif data == "wl_add":
            if not is_adm: return
            context.user_data["waiting"] = "wl_add"
            await safe_edit(query, "➕ <b>إضافة للقائمة البيضاء</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "wl_remove":
            if not is_adm: return
            context.user_data["waiting"] = "wl_remove"
            await safe_edit(query, "➖ <b>إزالة من القائمة البيضاء</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "wl_show":
            wl = db.get_whitelist(chat.id)
            if wl:
                text = "🛡️ <b>القائمة البيضاء:</b>\n\n"
                for uid in wl:
                    text += f"• <code>{uid}</code>\n"
            else:
                text = "🛡️ القائمة البيضاء فارغة."
            await safe_edit(query, text, reply_markup=kb_whitelist())

    # ═══ إجراءات الإشراف ═══
        elif data == "act_ban":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "ban"
            await safe_edit(query, "🚫 <b>حظر مستخدم</b>\n\nرد على رسالة المستخدم + اكتب السبب\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_unban":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "unban"
            await safe_edit(query, "✅ <b>إلغاء حظر</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_mute":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "mute"
            await safe_edit(query, "🔇 <b>كتم مستخدم</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_unmute":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "unmute"
            await safe_edit(query, "🔊 <b>إلغاء كتم</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_tmute":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "tmute_select"
            await safe_edit(query, "⏱️ <b>كتم مؤقت</b>\n\nرد على رسالة المستخدم أولاً ثم اختر المدة\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data.startswith("tmute_"):
            parts = data.split("_")
            if len(parts) >= 3:
                target_id = int(parts[1])
                time_val = parts[2]
                seconds = parse_time(time_val)
                if seconds <= 0:
                    await safe_answer(query, "❌ صيغة وقت خاطئة!", show_alert=True); return
                try:
                    until = datetime.now() + timedelta(seconds=seconds)
                    perms = ChatPermissions(can_send_messages=False)
                    await chat.restrict_member(target_id, perms, until_date=until)
                    time_str = format_time(seconds)
                    await safe_edit(query, f"⏱️ تم كتم المستخدم لمدة <b>{time_str}</b> ✅", reply_markup=kb_admin())
                    db.add_temp_mute(chat.id, target_id, user_id, until.strftime("%Y-%m-%d %H:%M:%S"))
                    db.increment_stat(chat.id, "total_mutes")
                    db.log_action(chat.id, user_id, f"tmute_{time_str}", target_id)
                except Exception as e:
                    await safe_edit(query, f"❌ خطأ: {str(e)}", reply_markup=kb_admin())
            context.user_data.pop("waiting", None)
            context.user_data.pop("target_id", None)

        elif data == "act_kick":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "kick"
            await safe_edit(query, "👢 <b>طرد مستخدم</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_warn":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "warn"
            await safe_edit(query, "⚠️ <b>تحذير مستخدم</b>\n\nرد على رسالة المستخدم + اكتب السبب\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_unwarn":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "unwarn"
            await safe_edit(query, "✅ <b>إزالة تحذيرات</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_del":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "del"
            await safe_edit(query, "🗑️ <b>حذف رسالة</b>\n\nرد على الرسالة\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_purge":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "purge"
            await safe_edit(query, "🗑️ <b>حذف متعدد</b>\n\nرد على رسالة واكتب العدد\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_promote":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "promote"
            await safe_edit(query, "📈 <b>ترقية لمشرف</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_demote":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "demote"
            await safe_edit(query, "📉 <b>تخفيض مشرف</b>\n\nرد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())

    # ═══ المحتوى ═══
        elif data == "act_pin":
            if not is_adm: return
            context.user_data["waiting"] = "pin"
            await safe_edit(query, "📌 رد على الرسالة لتثبيتها\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_unpin":
            if not is_adm: return
            try:
                await chat.unpin_all_messages()
                await safe_edit(query, "📌 تم إلغاء التثبيت ✅", reply_markup=kb_content())
            except:
                await safe_answer(query, "❌ لا يمكن الإلغاء!", show_alert=True)
        elif data == "act_setrules":
            if not is_adm: return
            context.user_data["waiting"] = "setrules"
            await safe_edit(query, "📋 اكتب القوانين الجديدة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_rules":
            settings = db.get_settings(chat.id)
            rules = settings.get("rules", "")
            if rules:
                await safe_edit(query, f"📋 <b>القوانين:</b>\n\n{rules}", reply_markup=kb_back())
            else:
                await safe_edit(query, "📋 لم يتم تعيين قوانين.", reply_markup=kb_content())
        elif data == "act_clearrules":
            if not is_adm: return
            db.update_setting(chat.id, "rules", "")
            await safe_edit(query, "📋 تم حذف القوانين ✅", reply_markup=kb_content())
        elif data == "act_setdesc":
            if not is_adm: return
            context.user_data["waiting"] = "setdesc"
            await safe_edit(query, "📝 اكتب وصف المجموعة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())

    # ═══ الملاحظات ═══
        elif data == "act_savenote":
            if not is_adm: return
            context.user_data["waiting"] = "savenote_name"
            await safe_edit(query, "💾 اكتب اسم الملاحظة (كلمة واحدة):\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_getnote":
            notes = db.get_all_notes(chat.id)
            if not notes:
                await safe_edit(query, "📝 لا توجد ملاحظات.", reply_markup=kb_notes())
            else:
                await safe_edit(query, "📖 اختر ملاحظة:", reply_markup=kb_notes_list(chat.id))
        elif data.startswith("note_"):
            note_name = data[5:]
            content = db.get_note(chat.id, note_name)
            if content:
                await safe_edit(query, f"📝 <b>{note_name}:</b>\n\n{content}", reply_markup=kb_back())
            else:
                await safe_edit(query, "❌ غير موجودة.", reply_markup=kb_notes())
        elif data == "act_allnotes":
            notes = db.get_all_notes(chat.id)
            if notes:
                text = "📋 <b>الملاحظات:</b>\n\n" + "\n".join([f"• 📝 {n}" for n in notes])
            else:
                text = "📋 لا توجد ملاحظات."
            await safe_edit(query, text, reply_markup=kb_notes())
        elif data == "act_delnote":
            if not is_adm: return
            context.user_data["waiting"] = "delnote"
            await safe_edit(query, "🗑️ اكتب اسم الملاحظة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())

    # ═══ الفلاتر ═══
        elif data == "act_addfilter":
            if not is_adm: return
            context.user_data["waiting"] = "addfilter_kw"
            await safe_edit(query, "➕ اكتب الكلمة المفتاحية:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_delfilter":
            if not is_adm: return
            context.user_data["waiting"] = "delfilter"
            await safe_edit(query, "➖ اكتب الكلمة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_allfilters":
            fl = db.get_all_filters(chat.id)
            if fl:
                text = "📋 <b>الفلاتر:</b>\n\n" + "\n".join([f"• 🔍 {kw}" for kw in fl])
            else:
                text = "📋 لا توجد فلاتر."
            await safe_edit(query, text, reply_markup=kb_filters())

    # ═══ الأقفال ═══
        elif data.startswith("lock_"):
            if not is_adm: return
            lock_type = data[5:]
            locked = db.get_all_locks(chat.id)
            if lock_type in locked:
                db.unlock_type(chat.id, lock_type)
                action = "فتح"
            else:
                db.lock_type(chat.id, lock_type, user_id)
                action = "قفل"
            await safe_edit(query,
                f"🔒 تم {action} {LOCK_TYPES.get(lock_type, lock_type)}\n\nاختر نوع آخر:",
                reply_markup=kb_lock_types(chat.id))
        elif data == "act_lockall":
            if not is_adm: return
            for key in LOCK_TYPES:
                db.lock_type(chat.id, key, user_id)
            await safe_edit(query, "🔒 تم قفل الكل ✅", reply_markup=kb_lock_types(chat.id))
        elif data == "act_unlockall":
            if not is_adm: return
            db.unlock_all(chat.id)
            await safe_edit(query, "🔓 تم فتح الكل ✅", reply_markup=kb_lock_types(chat.id))

    # ═══ الكلمات المسيئة ═══
        elif data == "act_addbadword":
            if not is_adm: return
            context.user_data["waiting"] = "addbadword"
            await safe_edit(query, "➕ اكتب الكلمة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_delbadword":
            if not is_adm: return
            context.user_data["waiting"] = "delbadword"
            await safe_edit(query, "➖ اكتب الكلمة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_showbadwords":
            words = db.get_badwords(chat.id)
            if words:
                text = "📋 <b>الكلمات المحظورة:</b>\n\n" + "\n".join([f"• 🚫 {w}" for w in words])
            else:
                text = "📋 لا توجد كلمات."
            await safe_edit(query, text, reply_markup=kb_badwords())

    # ═══ الإعدادات ═══
        elif data == "act_setwelcome":
            if not is_adm: return
            context.user_data["waiting"] = "setwelcome"
            await safe_edit(query, "💬 اكتب رسالة الترحيب (استخدم {user} لاسم العضو):\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_resetwelcome":
            if not is_adm: return
            db.update_setting(chat.id, "welcome_msg", "")
            await safe_edit(query, "🔄 تم إعادة الترحيب ✅", reply_markup=kb_settings(chat.id))
        elif data == "act_setlog":
            if not is_adm: return
            context.user_data["waiting"] = "setlog"
            await safe_edit(query, "📝 أرسل معرف القناة (مثال: -1001234567890):\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_autodelete":
            if not is_adm: return
            context.user_data["waiting"] = "autodelete"
            s = db.get_settings(chat.id)
            current = s.get('auto_delete', 0)
            await safe_edit(query,
                f"⏱️ <b>حذف تلقائي</b>\n\nالحالي: {current} ثانية (0 = معطل)\n\nاكتب الثواني (0 للتعطيل):\n\n⏳ بانتظار كتابتك...",
                reply_markup=kb_back_cancel())

    # ═══ المعلومات ═══
        elif data == "act_userinfo":
            context.user_data["waiting"] = "userinfo"
            await safe_edit(query, "👤 رد على رسالة المستخدم\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_groupstats":
            stats = db.get_stats(chat.id)
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
                )
            else:
                text = "📊 لا توجد إحصائيات بعد."
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_admins":
            try:
                admins = await chat.get_administrators()
                text = "👥 <b>المشرفين:</b>\n\n"
                for a in admins:
                    status = "👑" if a.status == ChatMemberStatus.OWNER else "🛡️"
                    text += f"{status} {mention(a.user.id, a.user.first_name)}\n"
            except:
                text = "❌ لا يمكن جلب المشرفين."
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_log":
            logs = db.get_action_log(chat.id, 10)
            if logs:
                text = "📋 <b>آخر 10 إجراءات:</b>\n\n"
                for log_entry in logs:
                    text += f"• {log_entry['action']} - <code>{log_entry['created_at']}</code>\n"
            else:
                text = "📋 لا توجد إجراءات."
            await safe_edit(query, text, reply_markup=kb_back())
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
                ("كابتشا الدخول", s.get('captcha_enabled', 0)),
                ("منع الهاتف", s.get('anti_phone', 0)),
                ("منع الرسائل الطويلة", s.get('anti_longmsg', 0)),
                ("منع التعديل", s.get('anti_edit', 0)),
                ("الوضع البطيء", s.get('slow_mode', 0)),
            ]
            text = "🛡️ <b>حالة الحماية:</b>\n\n"
            for name, status in protections:
                text += f"{'✅' if status else '❌'} {name}\n"
            active = sum(1 for _, s_val in protections if s_val)
            text += f"\n📊 {active}/{len(protections)} مفعّلة"
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_topactive":
            top = db.get_top_msg(chat.id, 10)
            if top:
                text = "📈 <b>الأكثر نشاطاً:</b>\n\n"
                for i, (uid, cnt) in enumerate(top, 1):
                    text += f"{i}. <code>{uid}</code> - {cnt} رسالة\n"
            else:
                text = "📈 لا توجد بيانات."
            await safe_edit(query, text, reply_markup=kb_back())

    # ═══ السمعة ═══
        elif data == "act_giverep":
            context.user_data["waiting"] = "giverep"
            await safe_edit(query, "⭐ رد على رسالة العضو لإعطائه نقطة سمعة\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_reprank":
            top = db.get_top_rep(chat.id, 10)
            if top:
                text = "⭐ <b>ترتيب السمعة:</b>\n\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, (uid, rep) in enumerate(top, 1):
                    medal = medals[i-1] if i <= 3 else f"{i}."
                    text += f"{medal} <code>{uid}</code> - {rep} نقطة\n"
            else:
                text = "⭐ لا توجد بيانات سمعة."
            await safe_edit(query, text, reply_markup=kb_back())

    # ═══ أخرى ═══
        elif data == "act_announce":
            if not is_adm: return
            context.user_data["waiting"] = "announce"
            await safe_edit(query, "📢 اكتب نص الإعلان:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "act_report":
            context.user_data["waiting"] = "report"
            await safe_edit(query, "🚨 رد على رسالة المستخدم + اكتب السبب\n\n⏳ بانتظار ردك...", reply_markup=kb_back_cancel())
        elif data == "act_dice":
            result = random.randint(1, 6)
            await safe_edit(query, f"🎰 <b>رمية النرد:</b> {result} 🎲", reply_markup=kb_other())
        elif data == "act_coin":
            result = random.choice(["👑 رأس", "🦅 كتاب"])
            await safe_edit(query, f"🎯 <b>رمية العملة:</b> {result}", reply_markup=kb_other())

    # ═══ التنظيف ═══
        elif data == "clean_bot":
            if not is_adm: return
            await safe_edit(query, "🗑️ <b>حذف رسائل البوت</b>\n\nسيتم حذف آخر 50 رسالة من البوت...\nهذه الميزة تعمل تلقائياً عند الطلب فقط.", reply_markup=kb_cleanup())
        elif data == "clean_tempmutes":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM temp_mutes WHERE chat_id = ?", (chat.id,))
                deleted = c.rowcount
                conn.commit()
                conn.close()
            await safe_edit(query, f"🗑️ تم حذف {deleted} كتم مؤقت ✅", reply_markup=kb_cleanup())
        elif data == "clean_warns":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM warnings WHERE chat_id = ?", (chat.id,))
                c.execute("DELETE FROM warning_counts WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف جميع التحذيرات ✅", reply_markup=kb_cleanup())
        elif data == "clean_stats":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM group_stats WHERE chat_id = ?", (chat.id,))
                c.execute("DELETE FROM msg_count WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف الإحصائيات ✅", reply_markup=kb_cleanup())

    # ═══ أدوات المالك ═══
        elif data == "owner_broadcast":
            if not is_owner: return
            context.user_data["waiting"] = "owner_broadcast"
            await safe_edit(query, "📢 اكتب الإعلان لكل المجموعات:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
        elif data == "owner_stats":
            if not is_owner: return
            group_ids = db.get_all_group_ids()
            await safe_edit(query,
                f"📊 <b>إحصائيات البوت</b>\n\n👥 المجموعات: {len(group_ids)}",
                reply_markup=kb_owner())

    except Exception as e:
        logger.error(f"callback_handler error: {e}")
        try:
            await safe_answer(query, f"❌ خطأ: {str(e)[:50]}", show_alert=True)
        except:
            pass


# ═════════════════════════════════════════════════════════════════
# معالجة الرسائل النصية
# ═════════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.effective_chat:
        return

    chat = update.effective_chat
    user = update.effective_user
    msg = update.message
    text = msg.text or ""
    waiting = context.user_data.get("waiting")

    # ═══ معالجة الإجراءات المعلقة ═══
    if waiting:
        is_adm = await check_is_admin(chat, user.id) or user.id == OWNER_ID
        target = msg.reply_to_message.from_user if msg.reply_to_message else None
        target_id = target.id if target else None

        if waiting == "ban" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            reason = text if text and text != "." else "بدون سبب"
            try:
                await chat.ban_member(target_id)
                await msg.reply_text(f"🚫 تم حظر {mention(target_id, target.first_name)}\n📋 السبب: {reason}", parse_mode="HTML")
                db.increment_stat(chat.id, "total_bans")
                db.log_action(chat.id, user.id, "ban", target_id, reason)
                await send_log(chat.id, f"🚫 حظر: {mention(user.id, user.first_name)} حظر {mention(target_id, target.first_name)}", context)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "unban" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                await chat.unban_member(target_id)
                await msg.reply_text(f"✅ تم إلغاء حظر {mention(target_id, target.first_name)}", parse_mode="HTML")
                db.log_action(chat.id, user.id, "unban", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "mute" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                perms = ChatPermissions(can_send_messages=False)
                await chat.restrict_member(target_id, perms)
                await msg.reply_text(f"🔇 تم كتم {mention(target_id, target.first_name)}", parse_mode="HTML")
                db.increment_stat(chat.id, "total_mutes")
                db.log_action(chat.id, user.id, "mute", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "unmute" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                perms = ChatPermissions(
                    can_send_messages=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_video_notes=True,
                    can_send_voice_notes=True,
                    can_send_polls=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True,
                )
                await chat.restrict_member(target_id, perms)
                await msg.reply_text(f"🔊 تم إلغاء كتم {mention(target_id, target.first_name)}", parse_mode="HTML")
                db.log_action(chat.id, user.id, "unmute", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "tmute_select" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            context.user_data["target_id"] = target_id
            context.user_data["waiting"] = None
            await msg.reply_text(
                f"⏱️ اختر مدة كتم {mention(target_id, target.first_name)}:",
                parse_mode="HTML", reply_markup=kb_mute_time(target_id))
            return

        elif waiting == "kick" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                await chat.ban_member(target_id)
                await chat.unban_member(target_id)
                await msg.reply_text(f"👢 تم طرد {mention(target_id, target.first_name)}", parse_mode="HTML")
                db.increment_stat(chat.id, "total_kicks")
                db.log_action(chat.id, user.id, "kick", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "warn" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            reason = text if text and text != "." else "بدون سبب"
            count = db.add_warning(chat.id, target_id, reason, user.id)
            db.increment_stat(chat.id, "total_warns")
            db.log_action(chat.id, user.id, "warn", target_id, reason)
            if count >= WARN_LIMIT:
                settings = db.get_settings(chat.id)
                warn_action = settings.get('warn_action', 'mute')
                try:
                    if warn_action == 'ban':
                        await chat.ban_member(target_id)
                        action_text = "حظر 🚫"
                        db.increment_stat(chat.id, "total_bans")
                    elif warn_action == 'kick':
                        await chat.ban_member(target_id)
                        await chat.unban_member(target_id)
                        action_text = "طرد 👢"
                        db.increment_stat(chat.id, "total_kicks")
                    else:
                        perms = ChatPermissions(can_send_messages=False)
                        await chat.restrict_member(target_id, perms)
                        action_text = "كتم 🔇"
                        db.increment_stat(chat.id, "total_mutes")
                    db.reset_warnings(chat.id, target_id)
                    await msg.reply_text(
                        f"⚠️ تحذير {count}/{WARN_LIMIT}\n\n{mention(target_id, target.first_name)} وصل الحد!\n📋 الإجراء: {action_text}",
                        parse_mode="HTML")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ في الإجراء: {str(e)}")
            else:
                await msg.reply_text(
                    f"⚠️ تحذير {count}/{WARN_LIMIT}\n\n👤 {mention(target_id, target.first_name)}\n📋 السبب: {reason}",
                    parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "unwarn" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            db.reset_warnings(chat.id, target_id)
            await msg.reply_text(f"✅ تم إزالة تحذيرات {mention(target_id, target.first_name)}", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "del":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            if msg.reply_to_message:
                try:
                    await msg.reply_to_message.delete()
                    db.increment_stat(chat.id, "total_deleted")
                    await msg.delete()
                except:
                    await msg.reply_text("❌ لا يمكن حذف الرسالة")
            context.user_data.pop("waiting", None); return

        elif waiting == "purge":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            if msg.reply_to_message:
                try:
                    count_val = int(text) if text.isdigit() else 5
                    count_val = min(count_val, 100)
                    deleted = 0
                    msg_id = msg.reply_to_message.message_id
                    for i in range(count_val):
                        try:
                            await chat.delete_message(msg_id + i)
                            deleted += 1
                        except:
                            pass
                    try:
                        await msg.delete()
                    except:
                        pass
                    db.increment_stat(chat.id, "total_deleted")
                    await chat.send_message(f"🗑️ تم حذف {deleted} رسالة ✅")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "promote" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                await chat.promote_member(target_id, can_manage_chat=True, can_delete_messages=True, can_restrict_members=True)
                await msg.reply_text(f"📈 تم ترقية {mention(target_id, target.first_name)} لمشرف ✅", parse_mode="HTML")
                db.log_action(chat.id, user.id, "promote", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "demote" and target_id:
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                await chat.promote_member(target_id, can_manage_chat=False, can_delete_messages=False, can_restrict_members=False)
                await msg.reply_text(f"📉 تم تخفيض {mention(target_id, target.first_name)} ✅", parse_mode="HTML")
                db.log_action(chat.id, user.id, "demote", target_id)
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "pin":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            if msg.reply_to_message:
                try:
                    await msg.reply_to_message.pin()
                    await msg.reply_text("📌 تم التثبيت ✅")
                except:
                    await msg.reply_text("❌ لا يمكن التثبيت")
            context.user_data.pop("waiting", None); return

        elif waiting == "setrules":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            db.update_setting(chat.id, "rules", text)
            await msg.reply_text("📋 تم تعيين القوانين ✅")
            context.user_data.pop("waiting", None); return

        elif waiting == "setdesc":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                await chat.set_description(text)
                await msg.reply_text("📝 تم تعيين وصف المجموعة ✅")
            except Exception as e:
                await msg.reply_text(f"❌ خطأ: {str(e)}")
            context.user_data.pop("waiting", None); return

        elif waiting == "setwelcome":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            db.update_setting(chat.id, "welcome_msg", text)
            await msg.reply_text("💬 تم تعيين الترحيب ✅")
            context.user_data.pop("waiting", None); return

        elif waiting == "setlog":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                log_id = int(text)
                db.update_setting(chat.id, "log_channel_id", log_id)
                await msg.reply_text("📝 تم تعيين قناة السجلات ✅")
            except:
                await msg.reply_text("❌ معرف خاطئ. أرسل الرقم فقط (مثال: -1001234567890)")
            context.user_data.pop("waiting", None); return

        elif waiting == "autodelete":
            if not is_adm:
                await msg.reply_text("⛔ للمشرفين فقط!")
                context.user_data.pop("waiting", None); return
            try:
                secs = int(text)
                db.update_setting(chat.id, "auto_delete", secs)
                if secs > 0:
                    await msg.reply_text(f"⏱️ تم تفعيل الحذف التلقائي: {secs} ثانية ✅")
                else:
                    await msg.reply_text("⏱️ تم تعطيل الحذف التلقائي ✅")
            except:
                await msg.reply_text("❌ اكتب رقماً فقط")
            context.user_data.pop("waiting", None); return

        elif waiting == "savenote_name":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            context.user_data["note_name"] = text
            context.user_data["waiting"] = "savenote_content"
            await msg.reply_text("📝 اكتب محتوى الملاحظة:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
            return

        elif waiting == "savenote_content":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            note_name = context.user_data.pop("note_name", "untitled")
            db.save_note(chat.id, note_name, text, user.id)
            await msg.reply_text(f"💾 تم حفظ الملاحظة <b>{note_name}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "delnote":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.delete_note(chat.id, text):
                await msg.reply_text(f"🗑️ تم حذف الملاحظة <b>{text}</b> ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ الملاحظة غير موجودة")
            context.user_data.pop("waiting", None); return

        elif waiting == "addfilter_kw":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            context.user_data["filter_kw"] = text
            context.user_data["waiting"] = "addfilter_reply"
            await msg.reply_text("📝 اكتب الرد التلقائي:\n\n⏳ بانتظار كتابتك...", reply_markup=kb_back_cancel())
            return

        elif waiting == "addfilter_reply":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            kw = context.user_data.pop("filter_kw", "")
            db.save_filter(chat.id, kw, text, user.id)
            await msg.reply_text(f"🔍 تم حفظ الفلتر <b>{kw}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "delfilter":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.delete_filter(chat.id, text):
                await msg.reply_text(f"🗑️ تم حذف الفلتر <b>{text}</b> ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ الفلتر غير موجود")
            context.user_data.pop("waiting", None); return

        elif waiting == "addbadword":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            db.add_badword(chat.id, text.lower(), user.id)
            await msg.reply_text(f"🚫 تم إضافة الكلمة <b>{text}</b> ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "delbadword":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.remove_badword(chat.id, text.lower()):
                await msg.reply_text(f"✅ تم حذف الكلمة <b>{text}</b>", parse_mode="HTML")
            else:
                await msg.reply_text("❌ الكلمة غير موجودة")
            context.user_data.pop("waiting", None); return

        elif waiting == "set_raid_threshold":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            try:
                val = int(text)
                if 2 <= val <= 50:
                    db.update_setting(chat.id, "raid_threshold", val)
                    await msg.reply_text(f"⚡ تم تعيين حد الغارة: {val} ✅")
                else:
                    await msg.reply_text("❌ القيمة يجب أن تكون بين 2 و 50")
            except:
                await msg.reply_text("❌ اكتب رقماً فقط")
            context.user_data.pop("waiting", None); return

        elif waiting == "wl_add":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                db.add_whitelist(chat.id, target_id, user.id)
                await msg.reply_text(f"➕ تم إضافة {mention(target_id, target.first_name)} للقائمة البيضاء ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        elif waiting == "wl_remove":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                if db.remove_whitelist(chat.id, target_id):
                    await msg.reply_text(f"➖ تم إزالة المستخدم من القائمة البيضاء ✅")
                else:
                    await msg.reply_text("❌ المستخدم غير موجود في القائمة")
            context.user_data.pop("waiting", None); return

        elif waiting == "userinfo":
            if target_id:
                rep = db.get_rep(chat.id, target_id)
                msg_cnt = db.get_msg_count(chat.id, target_id)
                warn_cnt = db.get_warning_count(chat.id, target_id)
                try:
                    member = await chat.get_member(target_id)
                    status = str(member.status).split('.')[-1]
                    text_info = (
                        f"👤 <b>معلومات المستخدم</b>\n\n"
                        f"🆔 المعرف: <code>{target_id}</code>\n"
                        f"📝 الاسم: {mention(target_id, target.first_name)}\n"
                        f"🏷️ الحالة: {status}\n"
                        f"⭐ السمعة: {rep}\n"
                        f"💬 الرسائل: {msg_cnt}\n"
                        f"⚠️ التحذيرات: {warn_cnt}/{WARN_LIMIT}\n"
                    )
                except:
                    text_info = f"👤 المعرف: <code>{target_id}</code>\n⭐ السمعة: {rep}\n💬 الرسائل: {msg_cnt}"
                await msg.reply_text(text_info, parse_mode="HTML")
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        elif waiting == "giverep":
            if target_id and target_id != user.id:
                rep = db.add_rep(chat.id, target_id)
                await msg.reply_text(f"⭐ تم إعطاء نقطة سمعة لـ {mention(target_id, target.first_name)} ({rep} نقطة)", parse_mode="HTML")
            elif target_id == user.id:
                await msg.reply_text("❌ لا يمكنك إعطاء سمعة لنفسك!")
            else:
                await msg.reply_text("❌ رد على رسالة العضو")
            context.user_data.pop("waiting", None); return

        elif waiting == "announce":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            await msg.reply_text(f"📢 <b>إعلان:</b>\n\n{text}", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "report":
            settings = db.get_settings(chat.id)
            if settings.get('report_enabled', 1):
                if target_id:
                    reason = text if text else "بدون سبب"
                    admins = await chat.get_administrators()
                    admin_text = " ".join([f"<a href=\"tg://user?id={a.user.id}\">‌</a>" for a in admins[:5]])
                    await msg.reply_text(
                        f"🚨 <b>بلاغ</b>\n\n👤 المبلغ: {mention(user.id, user.first_name)}\n🎯 المبلغ عنه: {mention(target_id, target.first_name)}\n📋 السبب: {reason}\n{admin_text}",
                        parse_mode="HTML")
                else:
                    await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        elif waiting == "owner_broadcast":
            if user.id != OWNER_ID:
                context.user_data.pop("waiting", None); return
            group_ids = db.get_all_group_ids()
            sent = 0
            for gid in group_ids:
                try:
                    await context.bot.send_message(chat_id=gid, text=f"📢 <b>إعلان من المالك</b>\n\n{text}", parse_mode="HTML")
                    sent += 1
                except:
                    pass
            await msg.reply_text(f"📢 تم إرسال الإعلان إلى {sent}/{len(group_ids)} مجموعة ✅")
            context.user_data.pop("waiting", None); return

        else:
            context.user_data.pop("waiting", None)

    # ═══ أنظمة الحماية التلقائية ═══
    if chat.type == "private":
        return

    # تجاهل المشرفين والمالك
    if user.id == OWNER_ID or user.id in SUDO_USERS:
        return
    is_user_adm = await check_is_admin(chat, user.id)
    if is_user_adm:
        return

    settings = db.get_settings(chat.id)

    # وضع الصيانة
    if settings.get('maintenance_mode', 0):
        try:
            await msg.delete()
            await chat.ban_member(user.id)
            await chat.unban_member(user.id)
        except:
            pass
        return

    # الوضع البطيء
    slow = settings.get('slow_mode', 0)
    if slow > 0 and check_slow_mode(chat.id, user.id, slow):
        try:
            await msg.delete()
        except:
            pass
        return

    # منع الإيموجي
    if settings.get('anti_emoji', 0):
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF]', text))
        if emoji_count > 5:
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return

    # منع العربية
    if settings.get('anti_arabic', 0) and re.search(r'[\u0600-\u06FF]', text):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # الأقفال
    locked = db.get_all_locks(chat.id)
    if locked:
        if "text" in locked and text:
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return
        if "links" in locked and has_link(text):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return
        if "forward" in locked and msg.forward_date:
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except:
                pass
            return
        if msg.photo and "photos" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.video and "videos" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.sticker and "stickers" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.animation and "animations" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.voice and "voice" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.audio and "audio" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.document and "documents" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.poll and "polls" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if msg.contact and "contacts" in locked:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if (msg.location or msg.venue) and ("location" in locked or "venue" in locked):
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return

    # منع الروابط
    if settings.get('anti_link', 1) and has_link(text):
        db.increment_stat(chat.id, "total_links_blocked")
        link_action = settings.get('link_action', 'delete')
        try:
            await msg.delete()
            if link_action == 'warn':
                count = db.add_warning(chat.id, user.id, "إرسال رابط", 0)
                await chat.send_message(f"⚠️ تحذير {count}/{WARN_LIMIT} - روابط محظورة!", parse_mode="HTML")
            elif link_action == 'mute':
                await chat.restrict_member(user.id, ChatPermissions(can_send_messages=False))
                await chat.send_message(f"🔇 تم كتم {mention(user.id, user.first_name)} - روابط محظورة!", parse_mode="HTML")
            elif link_action == 'ban':
                await chat.ban_member(user.id)
                await chat.send_message(f"🚫 تم حظر {mention(user.id, user.first_name)} - روابط محظورة!", parse_mode="HTML")
        except:
            pass
        return

    # منع أرقام الهاتف
    if settings.get('anti_phone', 0) and has_phone(text):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # منع المعرفات
    if settings.get('anti_username', 0) and has_username(text):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # منع الرسائل الطويلة
    max_len = settings.get('max_msg_length', 0)
    if settings.get('anti_longmsg', 0) and max_len > 0 and len(text) > max_len:
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # حماية السبام
    if settings.get('anti_spam', 1) and is_spam(text):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_spam_blocked")
        except:
            pass
        return

    # حماية الفلود
    if settings.get('anti_flood', 1):
        max_msgs = settings.get('max_flood_msgs', 5)
        interval = settings.get('flood_interval', 5)
        if check_flood(chat.id, user.id, max_msgs, interval):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_flood_blocked")
                perms = ChatPermissions(can_send_messages=False)
                await chat.restrict_member(user.id, perms)
                until = datetime.now() + timedelta(minutes=5)
                await chat.send_message(f"🔇 تم كتم {mention(user.id, user.first_name)} - فلود! (5 دقائق)", parse_mode="HTML")
            except:
                pass
            return

    # منع التوجيه
    if settings.get('anti_forward', 0) and msg.forward_date:
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # منع القنوات
    if settings.get('anti_channel', 1) and msg.sender_chat and msg.sender_chat.id != chat.id:
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass
        return

    # فلتر الكلمات المسيئة
    if settings.get('anti_badword', 1):
        badwords = db.get_badwords(chat.id)
        text_lower = text.lower()
        for bw in badwords:
            if bw in text_lower:
                try:
                    await msg.delete()
                    db.increment_stat(chat.id, "total_deleted")
                    count = db.add_warning(chat.id, user.id, "كلمة مسيئة", 0)
                    await chat.send_message(f"⚠️ تحذير {count}/{WARN_LIMIT} - كلمات مسيئة!", parse_mode="HTML")
                except:
                    pass
                return

    # الفلاتر
    filters_list = db.get_all_filters(chat.id)
    text_lower = text.lower()
    for kw in filters_list:
        if kw.lower() in text_lower:
            reply_text = db.get_filter(chat.id, kw)
            if reply_text:
                await msg.reply_text(reply_text)
            break

    # عداد الرسائل
    db.increment_msg_count(chat.id, user.id)
    db.increment_stat(chat.id, "total_messages")

    # حذف تلقائي
    auto_del = settings.get('auto_delete', 0)
    if auto_del > 0:
        async def auto_delete_msg():
            await asyncio.sleep(auto_del)
            try:
                await msg.delete()
            except:
                pass
        asyncio.ensure_future(auto_delete_msg())


# ═════════════════════════════════════════════════════════════════
# معالجة الرسائل المعدّلة
# ═════════════════════════════════════════════════════════════════

async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.edited_message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    msg = update.edited_message

    if user.id == OWNER_ID or user.id in SUDO_USERS:
        return
    is_adm = await check_is_admin(chat, user.id)
    if is_adm:
        return

    settings = db.get_settings(chat.id)
    if settings.get('anti_edit', 0):
        try:
            await msg.delete()
            db.increment_stat(chat.id, "total_deleted")
        except:
            pass


# ═════════════════════════════════════════════════════════════════
# معالجة الأعضاء الجدد
# ═════════════════════════════════════════════════════════════════

async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    settings = db.get_settings(chat.id)
    new_members = update.message.new_chat_members

    for member in new_members:
        if member.is_bot:
            if member.id != context.bot.id and settings.get('anti_bot', 0):
                try:
                    await chat.ban_member(member.id)
                    await chat.send_message(f"🤖 حظر بوت: {mention(member.id, member.first_name)}", parse_mode="HTML")
                except:
                    pass
            continue

        if member.id == OWNER_ID:
            continue

        if db.is_whitelisted(chat.id, member.id):
            continue

        db.increment_stat(chat.id, "total_joins")
        record_join(chat.id)

        # حماية الغارات
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
                    else:
                        await chat.ban_member(member.id)
                        await chat.unban_member(member.id)
                        action_text = "طرد"
                    db.increment_stat(chat.id, "total_raids_blocked")
                    await chat.send_message(f"🛡️ <b>غارة!</b> تم {action_text} {mention(member.id, member.first_name)}", parse_mode="HTML")
                except:
                    pass
                continue

        # كابتشا
        if settings.get('captcha_enabled', 0):
            try:
                num1 = random.randint(1, 10)
                num2 = random.randint(1, 10)
                answer = str(num1 + num2)
                captcha_msg = await chat.send_message(
                    f"🔐 <b>تحقق!</b>\n\n👤 {mention(member.id, member.first_name)}\n📝 كم يساوي {num1} + {num2} ؟\n⏰ لديك 60 ثانية",
                    parse_mode="HTML"
                )
                await chat.restrict_member(member.id, ChatPermissions(can_send_messages=False))
                with db.lock:
                    conn = db._get_conn()
                    c = conn.cursor()
                    c.execute("INSERT OR REPLACE INTO captcha_pending (chat_id, user_id, message_id, correct_answer) VALUES (?, ?, ?, ?)",
                             (chat.id, member.id, captcha_msg.message_id, answer))
                    conn.commit()
                    conn.close()
            except:
                pass
            continue

        # ترحيب
        welcome_msg = settings.get('welcome_msg', '')
        if not welcome_msg:
            welcome_msg = DEFAULT_WELCOME
        formatted = welcome_msg.replace('{user}', mention(member.id, member.first_name))
        try:
            await chat.send_message(formatted, parse_mode="HTML")
        except:
            pass


async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    db.increment_stat(chat.id, "total_leaves")


# ═════════════════════════════════════════════════════════════════
# فحص الكتم المؤقت
# ═════════════════════════════════════════════════════════════════

async def check_temp_mutes(context: ContextTypes.DEFAULT_TYPE):
    expired = db.get_expired_mutes()
    for mute in expired:
        try:
            perms = ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
            await context.bot.restrict_chat_member(mute['chat_id'], mute['user_id'], perms)
        except:
            pass


# ═════════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═════════════════════════════════════════════════════════════════

def main():
    if not TOKEN:
        logger.error("❌ لم يتم تعيين TOKEN! قم بتعيين متغير البيئة TOKEN")
        return

    # بدء خادم Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ خادم Flask بدأ")

    # بناء التطبيق
    app = Application.builder().token(TOKEN).build()

    # تسجيل معالجات الأوامر
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # تسجيل معالج الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(callback_handler))

    # معالجة الرسائل النصية (في المجموعات والخاصة)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        message_handler
    ))

    # معالجة الرسائل المعدّلة
    app.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE & ~filters.COMMAND,
        edited_message_handler
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

    # جدولة فحص الكتم المؤقت
    try:
        if app.job_queue:
            app.job_queue.run_repeating(check_temp_mutes, interval=60, first=10)
            logger.info("✅ تم تسجيل جدولة الكتم المؤقت")
        else:
            logger.warning("⚠️ JobQueue غير متاح - استخدام خيط بديل")
            def temp_mute_checker():
                while True:
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(check_temp_mutes(app))
                        loop.close()
                    except Exception as e:
                        logger.error(f"temp_mute_checker error: {e}")
                    time.sleep(60)
            checker_thread = threading.Thread(target=temp_mute_checker, daemon=True)
            checker_thread.start()
    except Exception as e:
        logger.warning(f"⚠️ خطأ في الجدولة: {e}")

    logger.info("🛡️ بوت إدارة المجموعات v6.0 يعمل الآن!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
