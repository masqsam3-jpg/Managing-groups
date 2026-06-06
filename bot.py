"""
╔══════════════════════════════════════════════════════════════════╗
║    🛡️ بوت إدارة المجموعات المتكامل v7.0 - الإصدار الخارق 🛡️    ║
║                                                                  ║
║  بوت احترافي لإدارة وحماية مجموعات التيليجرام                   ║
║  واجهة أزرار كاملة | حماية متقدمة | إدارة ذكية | ذكاء اصطناعي  ║
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
    return jsonify({"status": "running", "bot": "Group Manager v7.0", "uptime": True}), 200

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
                ai_reply INTEGER DEFAULT 0,
                absence_mode INTEGER DEFAULT 0,
                auto_welcome INTEGER DEFAULT 1,
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
            # القائمة السوداء
            c.execute('''CREATE TABLE IF NOT EXISTS blacklist (
                chat_id INTEGER, user_id INTEGER, reason TEXT DEFAULT '',
                added_by INTEGER, added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            # الكابتشا
            c.execute('''CREATE TABLE IF NOT EXISTS captcha_pending (
                chat_id INTEGER, user_id INTEGER, message_id INTEGER,
                correct_answer TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            # السمعة
            c.execute('''CREATE TABLE IF NOT EXISTS user_reputation (
                chat_id INTEGER, user_id INTEGER, rep INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )''')
            # عداد الرسائل
            c.execute('''CREATE TABLE IF NOT EXISTS msg_count (
                chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            # الرسائل المجدولة
            c.execute('''CREATE TABLE IF NOT EXISTS scheduled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, text TEXT, send_at TEXT,
                created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                sent INTEGER DEFAULT 0
            )''')
            # ردود ذكية
            c.execute('''CREATE TABLE IF NOT EXISTS auto_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, trigger_text TEXT, reply_text TEXT,
                created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, trigger_text)
            )''')
            # الرسائل المثبتة
            c.execute('''CREATE TABLE IF NOT EXISTS pinned_messages (
                chat_id INTEGER, message_id INTEGER, pinned_by INTEGER,
                pinned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, message_id)
            )''')
            # الأدوار المخصصة
            c.execute('''CREATE TABLE IF NOT EXISTS custom_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, user_id INTEGER, role_name TEXT,
                assigned_by INTEGER, assigned_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, user_id)
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

    # ═══ التحذيرات ═══
    def add_warning(self, chat_id, user_id, reason, warned_by):
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

    def get_warning_count(self, chat_id, user_id):
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

    def get_warnings(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM warnings WHERE chat_id = ? AND user_id = ? ORDER BY id DESC", (chat_id, user_id))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def reset_warnings(self, chat_id, user_id):
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

    # ═══ الملاحظات ═══
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

    # ═══ الفلاتر ═══
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

    # ═══ الأقفال ═══
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

    # ═══ الكلمات المسيئة ═══
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

    # ═══ الإحصائيات ═══
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

    # ═══ الكتم المؤقت ═══
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

    # ═══ سجل الإجراءات ═══
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

    # ═══ القائمة البيضاء ═══
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

    # ═══ القائمة السوداء ═══
    def add_blacklist(self, chat_id, user_id, reason, added_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO blacklist (chat_id, user_id, reason, added_by) VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, reason, added_by))
            conn.commit()
            conn.close()

    def remove_blacklist(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM blacklist WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def is_blacklisted(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM blacklist WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row is not None

    def get_blacklist(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM blacklist WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    # ═══ الكابتشا ═══
    def remove_captcha(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            conn.commit()
            conn.close()

    # ═══ السمعة ═══
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

    # ═══ عداد الرسائل ═══
    def increment_msg_count(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO msg_count (chat_id, user_id, count, last_active) VALUES (?, ?, 1, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1, last_active = ?",
                     (chat_id, user_id, now, now))
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

    def get_inactive_users(self, chat_id, days=7):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("SELECT user_id, last_active FROM msg_count WHERE chat_id = ? AND last_active < ?", (chat_id, cutoff))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def get_all_group_ids(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT chat_id FROM group_settings")
            rows = c.fetchall()
            conn.close()
            return [row[0] for row in rows]

    # ═══ الرسائل المجدولة ═══
    def add_scheduled(self, chat_id, text, send_at, created_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO scheduled_messages (chat_id, text, send_at, created_by) VALUES (?, ?, ?, ?)",
                     (chat_id, text, send_at, created_by))
            conn.commit()
            conn.close()

    def get_pending_scheduled(self):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("SELECT * FROM scheduled_messages WHERE send_at <= ? AND sent = 0", (now,))
            rows = c.fetchall()
            for r in rows:
                c.execute("UPDATE scheduled_messages SET sent = 1 WHERE id = ?", (r['id'],))
            conn.commit()
            conn.close()
            return [dict(r) for r in rows]

    # ═══ الردود الذكية ═══
    def add_auto_reply(self, chat_id, trigger, reply, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO auto_replies (chat_id, trigger_text, reply_text, created_by) VALUES (?, ?, ?, ?)",
                     (chat_id, trigger, reply, user_id))
            conn.commit()
            conn.close()

    def get_auto_replies(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT trigger_text, reply_text FROM auto_replies WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows]

    def delete_auto_reply(self, chat_id, trigger):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM auto_replies WHERE chat_id = ? AND trigger_text = ?", (chat_id, trigger))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    # ═══ الأدوار المخصصة ═══
    def assign_role(self, chat_id, user_id, role_name, assigned_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO custom_roles (chat_id, user_id, role_name, assigned_by) VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, role_name, assigned_by))
            conn.commit()
            conn.close()

    def remove_role(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM custom_roles WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def get_user_role(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT role_name FROM custom_roles WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row[0] if row else None

    def get_all_roles(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, role_name FROM custom_roles WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows]


db = Database(DB_PATH)

# ═════════════════════════════════════════════════════════════════
# ثوابت
# ═════════════════════════════════════════════════════════════════
LOCK_TYPES = {
    "photos": "الصور", "videos": "الفيديو", "stickers": "الملصقات",
    "animations": "ال GIF", "voice": "الصوتية", "audio": "الصوت",
    "documents": "الملفات", "links": "الروابط", "forward": "إعادة التوجيه",
    "inline": "الإنلاين", "polls": "الاستفتاءات", "contacts": "جهات الاتصال",
    "location": "الموقع", "venue": "الأماكن", "text": "النصوص", "bots": "البوتات",
}

MUTE_TIMES = [
    ("1 دقيقة", "1m"), ("5 دقائق", "5m"), ("10 دقائق", "10m"),
    ("30 دقيقة", "30m"), ("1 ساعة", "1h"), ("6 ساعات", "6h"),
    ("12 ساعة", "12h"), ("1 يوم", "1d"), ("3 أيام", "3d"), ("7 أيام", "7d"),
]

RAID_ACTIONS = {"kick": "طرد", "ban": "حظر", "mute": "كتم"}
LINK_ACTIONS = {"delete": "حذف الرسالة", "mute": "كتم", "ban": "حظر", "warn": "تحذير"}
WARN_ACTIONS = {"mute": "كتم", "kick": "طرد", "ban": "حظر"}

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
    return bool(URL_PATTERN.search(text)) if text else False

def has_phone(text):
    return bool(PHONE_PATTERN.search(text)) if text else False

def has_username(text):
    return bool(USERNAME_PATTERN.search(text)) if text else False

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
    except:
        return False

def mention(user_id, name):
    safe_name = name if name else "مستخدم"
    return f'<a href="tg://user?id={user_id}">{safe_name}</a>'

def parse_time(time_str):
    """تحويل نص الوقت إلى ثوان - تم إصلاح الخطأ الحرج"""
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
# نظام اللوحات (Keyboards) - واجهة أزرار شاملة
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
        [InlineKeyboardButton("🤖 الذكاء الاصطناعي", callback_data="menu_ai"),
         InlineKeyboardButton("📋 الأدوار", callback_data="menu_roles")],
        [InlineKeyboardButton("⏰ الجدولة", callback_data="menu_schedule"),
         InlineKeyboardButton("🚨 أخرى", callback_data="menu_other")],
        [InlineKeyboardButton("🧹 التنظيف", callback_data="menu_cleanup"),
         InlineKeyboardButton("📨 الرسائل", callback_data="menu_messages")],
        [InlineKeyboardButton("👤 معلوماتي", callback_data="act_me"),
         InlineKeyboardButton("📋 القوانين", callback_data="act_rules")],
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
        [InlineKeyboardButton("📋 عرض التحذيرات", callback_data="act_warns"),
         InlineKeyboardButton("🗑️ حذف التحذيرات", callback_data="act_delwarn")],
        [InlineKeyboardButton("🗑️ حذف رسالة", callback_data="act_del"),
         InlineKeyboardButton("🗑️ حذف متعدد", callback_data="act_purge")],
        [InlineKeyboardButton("📈 ترقية مشرف", callback_data="act_promote"),
         InlineKeyboardButton("📉 تخفيض مشرف", callback_data="act_demote")],
        [InlineKeyboardButton("🖤 إضافة للقائمة السوداء", callback_data="act_badd"),
         InlineKeyboardButton("💚 إزالة من السوداء", callback_data="act_bdel")],
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
        [InlineKeyboardButton(f"{'🌙' if s.get('absence_mode',0) else '☀️'} وضع الغياب", callback_data="tog_absence"),
         InlineKeyboardButton("🖤 القائمة السوداء", callback_data="menu_blacklist")],
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
        [InlineKeyboardButton("📝 تعديل المثبتة", callback_data="act_editpin"),
         InlineKeyboardButton("📌 إعادة تثبيت", callback_data="act_repin")],
        [InlineKeyboardButton("📋 الرسائل المثبتة", callback_data="act_pinned"),
         InlineKeyboardButton("🔗 رابط المجموعة", callback_data="act_geturl")],
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
        [InlineKeyboardButton("👻 غير النشطين", callback_data="act_inactives"),
         InlineKeyboardButton("📊 رسم بياني", callback_data="act_graphic")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_reputation():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ إعطاء نقطة", callback_data="act_giverep"),
         InlineKeyboardButton("📊 ترتيب السمعة", callback_data="act_reprank")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_ai():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🤖 تفعيل الرد الذكي", callback_data="tog_aireply"),
         InlineKeyboardButton("➕ إضافة رد تلقائي", callback_data="act_addautoreply")],
        [InlineKeyboardButton("📋 عرض الردود", callback_data="act_autoreplies"),
         InlineKeyboardButton("➖ حذف رد تلقائي", callback_data="act_delautoreply")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_roles():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎖️ تعيين دور", callback_data="act_assignrole"),
         InlineKeyboardButton("🗑️ إزالة دور", callback_data="act_removerole")],
        [InlineKeyboardButton("📋 عرض الأدوار", callback_data="act_listroles")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_schedule():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏰ إرسال مجدول", callback_data="act_schedule"),
         InlineKeyboardButton("📋 عرض المجدولة", callback_data="act_scheduledlist")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_other():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 إعلان", callback_data="act_announce"),
         InlineKeyboardButton("🚨 بلاغ", callback_data="act_report")],
        [InlineKeyboardButton("🎰 حظ", callback_data="act_dice"),
         InlineKeyboardButton("🎯 عملة", callback_data="act_coin")],
        [InlineKeyboardButton("📨 إرسال رسالة", callback_data="act_send"),
         InlineKeyboardButton("📋 قائمة الأعضاء", callback_data="act_list")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_messages():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📨 إرسال لعضو", callback_data="act_send"),
         InlineKeyboardButton("📩 إرسال بالخاص", callback_data="act_infopvt")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_cleanup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ حذف رسائل بوت", callback_data="clean_bot"),
         InlineKeyboardButton("🗑️ حذف كتم مؤقت", callback_data="clean_tempmutes")],
        [InlineKeyboardButton("🗑️ حذف تحذيرات", callback_data="clean_warns"),
         InlineKeyboardButton("🗑️ حذف إحصائيات", callback_data="clean_stats")],
        [InlineKeyboardButton("🗑️ حذف سجل", callback_data="clean_log")],
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
        [InlineKeyboardButton(f"{'🔵' if current_action=='delete' else '⚪'} حذف", callback_data="set_link_delete"),
         InlineKeyboardButton(f"{'🔵' if current_action=='warn' else '⚪'} تحذير", callback_data="set_link_warn")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_link_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_link_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_warn_settings(chat_id):
    s = db.get_settings(chat_id)
    current_action = s.get('warn_action', 'mute')
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"{'🔵' if current_action=='mute' else '⚪'} كتم", callback_data="set_warn_mute"),
         InlineKeyboardButton(f"{'🔵' if current_action=='kick' else '⚪'} طرد", callback_data="set_warn_kick")],
        [InlineKeyboardButton(f"{'🔵' if current_action=='ban' else '⚪'} حظر", callback_data="set_warn_ban")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_whitelist():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة", callback_data="wl_add"),
         InlineKeyboardButton("➖ إزالة", callback_data="wl_remove")],
        [InlineKeyboardButton("📋 عرض القائمة", callback_data="wl_show")],
        [InlineKeyboardButton("🔙 حماية", callback_data="menu_protection")]
    ])

def kb_blacklist():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة", callback_data="bl_add"),
         InlineKeyboardButton("➖ إزالة", callback_data="bl_remove")],
        [InlineKeyboardButton("📋 عرض القائمة", callback_data="bl_show")],
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
        "🛡️ <b>بوت إدارة المجموعات المتكامل v7.0</b>\n\n"
        "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
        "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
        "🤖 <b>ذكاء اصطناعي</b> ردود ذكية تلقائية في المجموعة\n"
        "📊 <b>إحصائيات شاملة</b> مع رسومات بيانية\n"
        "⭐ <b>نظام سمعة وأدوار</b> لتقييم أعضاء المجموعة\n"
        "⏰ <b>جدولة رسائل</b> إرسال تلقائي في أوقات محددة\n"
        "🖤 <b>قائمة سوداء</b> حظر تلقائي دائم\n"
        "🌙 <b>وضع الغياب</b> إدارة تلقائية عند غياب المشرفين\n\n"
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
                "🛡️ <b>بوت إدارة المجموعات المتكامل v7.0</b>\n\n"
                "🔐 حماية متقدمة | ⚡ إدارة ذكية | 🤖 ذكاء اصطناعي\n\n"
                "👇 اختر أي قسم:",
                reply_markup=kb_main(is_adm or is_owner))

        elif data == "cancel":
            context.user_data.pop("waiting", None)
            context.user_data.pop("target_id", None)
            context.user_data.pop("note_name", None)
            context.user_data.pop("filter_kw", None)
            await safe_edit(query, "❌ تم الإلغاء.", reply_markup=kb_main(is_adm or is_owner))

        # ═══ فتح القوائم ═══
        elif data == "menu_admin":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🛡️ <b>أوامر الإشراف</b>\n\n📌 لحظر/كتم/طرد: رد على رسالة المستخدم ثم اضغط الزر", reply_markup=kb_admin())

        elif data == "menu_protection":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔐 <b>نظام الحماية المتقدم</b>\n\nاضغط لأي حماية لتفعيلها/تعطيلها:", reply_markup=kb_protection(chat.id))

        elif data == "menu_content":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📌 <b>إدارة المحتوى</b>:", reply_markup=kb_content())

        elif data == "menu_notes":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📝 <b>نظام الملاحظات</b>:", reply_markup=kb_notes())

        elif data == "menu_filters":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔍 <b>نظام الفلاتر</b>:", reply_markup=kb_filters())

        elif data == "menu_locks":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🔒 <b>نظام الأقفال</b>:", reply_markup=kb_lock_types(chat.id))

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
            await safe_edit(query, "⭐ <b>نظام السمعة</b>:", reply_markup=kb_reputation())

        elif data == "menu_ai":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🤖 <b>الذكاء الاصطناعي والردود الذكية</b>:", reply_markup=kb_ai())

        elif data == "menu_roles":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🎖️ <b>نظام الأدوار المخصصة</b>:", reply_markup=kb_roles())

        elif data == "menu_schedule":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "⏰ <b>نظام الجدولة</b>:", reply_markup=kb_schedule())

        elif data == "menu_other":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🚨 <b>أوامر أخرى</b>:", reply_markup=kb_other())

        elif data == "menu_messages":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📨 <b>الرسائل</b>:", reply_markup=kb_messages())

        elif data == "menu_cleanup":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "🧹 <b>أدوات التنظيف</b>:", reply_markup=kb_cleanup())

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
                "tog_absence": ("absence_mode", "وضع الغياب"),
                "tog_aireply": ("ai_reply", "الرد الذكي بالذكاء الاصطناعي"),
            }
            if data in toggle_map:
                key, name = toggle_map[data]
                s = db.get_settings(chat.id)
                new_val = 0 if s.get(key, 0) else 1
                db.update_setting(chat.id, key, new_val)
                status = "مفعّل ✅" if new_val else "معطّل ❌"
                if data in ("tog_absence", "tog_aireply"):
                    await safe_edit(query, f"🔐 <b>الإعدادات</b>\n\nتم {'تفعيل' if new_val else 'تعطيل'} <b>{name}</b> {status}", reply_markup=kb_protection(chat.id) if data == "tog_absence" else kb_ai())
                else:
                    await safe_edit(query, f"🔐 <b>الحماية</b>\n\nتم {'تفعيل' if new_val else 'تعطيل'} <b>{name}</b> {status}", reply_markup=kb_protection(chat.id))

        # ═══ إعدادات الغارة ═══
        elif data == "raid_settings":
            if not is_adm: return
            await safe_edit(query, "⚡ <b>إعدادات الغارات</b>:", reply_markup=kb_raid_settings(chat.id))
        elif data == "set_raid_threshold":
            if not is_adm: return
            context.user_data["waiting"] = "set_raid_threshold"
            await safe_edit(query, "📊 <b>تعيين حد الغارة</b>\n\nاكتب عدد الأعضاء (2-50):", reply_markup=kb_back_cancel())
        elif data.startswith("set_raid_"):
            if not is_adm: return
            action = data.replace("set_raid_", "")
            if action in RAID_ACTIONS:
                db.update_setting(chat.id, "raid_action", action)
                await safe_edit(query, f"⚡ <b>إعدادات الغارات</b>\n\nالإجراء: {RAID_ACTIONS[action]}", reply_markup=kb_raid_settings(chat.id))

        # ═══ إعدادات الروابط ═══
        elif data == "link_settings":
            if not is_adm: return
            await safe_edit(query, "🔗 <b>إعدادات الروابط</b>:", reply_markup=kb_link_settings(chat.id))
        elif data.startswith("set_link_"):
            if not is_adm: return
            action = data.replace("set_link_", "")
            if action in LINK_ACTIONS:
                db.update_setting(chat.id, "link_action", action)
                await safe_edit(query, f"🔗 <b>إعدادات الروابط</b>\n\nالإجراء: {LINK_ACTIONS[action]}", reply_markup=kb_link_settings(chat.id))

        # ═══ إعدادات التحذير ═══
        elif data == "warn_settings":
            if not is_adm: return
            await safe_edit(query, f"⚠️ <b>إعدادات التحذيرات</b>\n\nالحد: {WARN_LIMIT}:", reply_markup=kb_warn_settings(chat.id))
        elif data.startswith("set_warn_"):
            if not is_adm: return
            action = data.replace("set_warn_", "")
            if action in WARN_ACTIONS:
                db.update_setting(chat.id, "warn_action", action)
                await safe_edit(query, f"⚠️ <b>إعدادات التحذير</b>\n\nالإجراء: {WARN_ACTIONS[action]}", reply_markup=kb_warn_settings(chat.id))

        # ═══ القائمة البيضاء ═══
        elif data == "menu_whitelist":
            if not is_adm: return
            await safe_edit(query, "🛡️ <b>القائمة البيضاء</b>:", reply_markup=kb_whitelist())
        elif data == "wl_add":
            if not is_adm: return
            context.user_data["waiting"] = "wl_add"
            await safe_edit(query, "➕ <b>إضافة للقائمة البيضاء</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "wl_remove":
            if not is_adm: return
            context.user_data["waiting"] = "wl_remove"
            await safe_edit(query, "➖ <b>إزالة من القائمة البيضاء</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "wl_show":
            wl = db.get_whitelist(chat.id)
            if wl:
                text = "🛡️ <b>القائمة البيضاء:</b>\n\n"
                for uid in wl:
                    text += f"• <code>{uid}</code>\n"
            else:
                text = "🛡️ القائمة البيضاء فارغة."
            await safe_edit(query, text, reply_markup=kb_whitelist())

        # ═══ القائمة السوداء ═══
        elif data == "menu_blacklist":
            if not is_adm: return
            await safe_edit(query, "🖤 <b>القائمة السوداء</b>:", reply_markup=kb_blacklist())
        elif data == "bl_add":
            if not is_adm: return
            context.user_data["waiting"] = "bl_add"
            await safe_edit(query, "🖤 <b>إضافة للقائمة السوداء</b>\n\nرد على رسالة المستخدم + اكتب السبب:", reply_markup=kb_back_cancel())
        elif data == "bl_remove":
            if not is_adm: return
            context.user_data["waiting"] = "bl_remove"
            await safe_edit(query, "💚 <b>إزالة من القائمة السوداء</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "bl_show":
            bl = db.get_blacklist(chat.id)
            if bl:
                text = "🖤 <b>القائمة السوداء:</b>\n\n"
                for item in bl:
                    text += f"• <code>{item['user_id']}</code> - {item['reason'] or 'بدون سبب'}\n"
            else:
                text = "🖤 القائمة السوداء فارغة."
            await safe_edit(query, text, reply_markup=kb_blacklist())

        # ═══ إجراءات الإشراف ═══
        elif data == "act_ban":
            if not is_adm or not bot_adm:
                await safe_answer(query, "⛔ البوت يحتاج صلاحيات مشرف!", show_alert=True); return
            context.user_data["waiting"] = "ban"
            await safe_edit(query, "🚫 <b>حظر مستخدم</b>\n\nرد على رسالة المستخدم + اكتب السبب:", reply_markup=kb_back_cancel())
        elif data == "act_unban":
            if not is_adm: return
            context.user_data["waiting"] = "unban"
            await safe_edit(query, "✅ <b>إلغاء حظر</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_mute":
            if not is_adm or not bot_adm: return
            context.user_data["waiting"] = "mute"
            await safe_edit(query, "🔇 <b>كتم مستخدم</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_unmute":
            if not is_adm: return
            context.user_data["waiting"] = "unmute"
            await safe_edit(query, "🔊 <b>إلغاء كتم</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_tmute":
            if not is_adm or not bot_adm: return
            context.user_data["waiting"] = "tmute_select"
            await safe_edit(query, "⏱️ <b>كتم مؤقت</b>\n\nرد على رسالة المستخدم أولاً:", reply_markup=kb_back_cancel())
        elif data == "act_kick":
            if not is_adm or not bot_adm: return
            context.user_data["waiting"] = "kick"
            await safe_edit(query, "👢 <b>طرد مستخدم</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_warn":
            if not is_adm: return
            context.user_data["waiting"] = "warn"
            await safe_edit(query, "⚠️ <b>تحذير</b>\n\nرد على رسالة المستخدم + اكتب السبب:", reply_markup=kb_back_cancel())
        elif data == "act_unwarn":
            if not is_adm: return
            context.user_data["waiting"] = "unwarn"
            await safe_edit(query, "✅ <b>إزالة تحذير</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_warns":
            if not is_adm: return
            context.user_data["waiting"] = "warns"
            await safe_edit(query, "📋 <b>عرض التحذيرات</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_delwarn":
            if not is_adm: return
            context.user_data["waiting"] = "delwarn"
            await safe_edit(query, "🗑️ <b>حذف التحذيرات</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_del":
            if not is_adm: return
            context.user_data["waiting"] = "del"
            await safe_edit(query, "🗑️ <b>حذف رسالة</b>\n\nرد على الرسالة:", reply_markup=kb_back_cancel())
        elif data == "act_purge":
            if not is_adm: return
            context.user_data["waiting"] = "purge"
            await safe_edit(query, "🗑️ <b>حذف متعدد</b>\n\nرد على الرسالة (يحذف منها حتى الرسالة الحالية):", reply_markup=kb_back_cancel())
        elif data == "act_promote":
            if not is_adm or not bot_adm: return
            context.user_data["waiting"] = "promote"
            await safe_edit(query, "📈 <b>ترقية مشرف</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_demote":
            if not is_adm: return
            context.user_data["waiting"] = "demote"
            await safe_edit(query, "📉 <b>تخفيض مشرف</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_badd":
            if not is_adm: return
            context.user_data["waiting"] = "badd"
            await safe_edit(query, "🖤 <b>إضافة للقائمة السوداء</b>\n\nرد على رسالة المستخدم + السبب:", reply_markup=kb_back_cancel())
        elif data == "act_bdel":
            if not is_adm: return
            context.user_data["waiting"] = "bdel"
            await safe_edit(query, "💚 <b>إزالة من القائمة السوداء</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())

        # ═══ كتم مؤقت - اختيار الوقت ═══
        elif data.startswith("tmute_"):
            if not is_adm: return
            parts = data.split("_")
            if len(parts) >= 3:
                target_id = int(parts[1])
                time_str = parts[2]
                seconds = parse_time(time_str)
                if seconds > 0:
                    until = datetime.now() + timedelta(seconds=seconds)
                    until_str = until.strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        await chat.restrict_member(target_id, ChatPermissions(can_send_messages=False))
                        db.add_temp_mute(chat.id, target_id, user_id, until_str)
                        target = await chat.get_member(target_id)
                        name = target.user.first_name if target and target.user else "مستخدم"
                        await chat.send_message(f"⏱️ تم كتم {mention(target_id, name)} لمدة {format_time(seconds)}", parse_mode="HTML")
                        db.log_action(chat.id, user_id, "tmute", target_id, format_time(seconds))
                        db.increment_stat(chat.id, "total_mutes")
                    except Exception as e:
                        await chat.send_message(f"❌ خطأ: {e}")
                context.user_data.pop("waiting", None)
                context.user_data.pop("target_id", None)

        # ═══ المحتوى ═══
        elif data == "act_pin":
            if not is_adm: return
            context.user_data["waiting"] = "pin"
            await safe_edit(query, "📌 <b>تثبيت رسالة</b>\n\nرد على الرسالة:", reply_markup=kb_back_cancel())
        elif data == "act_unpin":
            if not is_adm: return
            try:
                await chat.unpin_all_chat_messages()
                await chat.send_message("📌 تم إلغاء تثبيت جميع الرسائل ✅")
            except: pass
        elif data == "act_setrules":
            if not is_adm: return
            context.user_data["waiting"] = "setrules"
            await safe_edit(query, "📋 <b>تعيين القوانين</b>\n\nاكتب القوانين:", reply_markup=kb_back_cancel())
        elif data == "act_rules":
            settings = db.get_settings(chat.id)
            rules = settings.get('rules', '')
            if rules:
                await safe_edit(query, f"📋 <b>قوانين المجموعة:</b>\n\n{rules}", reply_markup=kb_back())
            else:
                await safe_edit(query, "📋 لم يتم تعيين قوانين بعد.", reply_markup=kb_back())
        elif data == "act_clearrules":
            if not is_adm: return
            db.update_setting(chat.id, "rules", "")
            await safe_edit(query, "📋 تم حذف القوانين ✅", reply_markup=kb_back())
        elif data == "act_setdesc":
            if not is_adm: return
            context.user_data["waiting"] = "setdesc"
            await safe_edit(query, "📝 <b>وصف المجموعة</b>\n\nاكتب الوصف:", reply_markup=kb_back_cancel())
        elif data == "act_editpin":
            if not is_adm: return
            context.user_data["waiting"] = "editpin"
            await safe_edit(query, "📝 <b>تعديل الرسالة المثبتة</b>\n\nرد على الرسالة المثبتة + اكتب النص الجديد:", reply_markup=kb_back_cancel())
        elif data == "act_repin":
            if not is_adm: return
            try:
                pinned = await chat.get_pinned_messages()
                if pinned:
                    await pinned[0].unpin()
                    await pinned[0].pin()
                    await chat.send_message("📌 تم إعادة تثبيت الرسالة ✅")
                else:
                    await chat.send_message("❌ لا توجد رسائل مثبتة")
            except: pass
        elif data == "act_pinned":
            try:
                pinned = await chat.get_pinned_messages()
                if pinned:
                    text = "📌 <b>الرسائل المثبتة:</b>\n\n"
                    for i, msg in enumerate(pinned[:5], 1):
                        preview = msg.text[:50] if msg.text else "(وسائط)"
                        text += f"{i}. {preview}...\n"
                else:
                    text = "📌 لا توجد رسائل مثبتة."
                await safe_edit(query, text, reply_markup=kb_back())
            except: pass
        elif data == "act_geturl":
            try:
                link = await chat.export_invite_link()
                await safe_edit(query, f"🔗 <b>رابط المجموعة:</b>\n\n<code>{link}</code>", reply_markup=kb_back())
            except:
                await safe_edit(query, "❌ لا يمكن إنشاء رابط. تأكد من صلاحيات البوت.", reply_markup=kb_back())

        # ═══ الملاحظات ═══
        elif data == "act_savenote":
            if not is_adm: return
            context.user_data["waiting"] = "savenote_name"
            await safe_edit(query, "💾 <b>حفظ ملاحظة</b>\n\nاكتب اسم الملاحظة:", reply_markup=kb_back_cancel())
        elif data == "act_getnote":
            if not is_adm: return
            context.user_data["waiting"] = "getnote"
            await safe_edit(query, "📖 <b>استرجاع ملاحظة</b>\n\nاكتب اسم الملاحظة:", reply_markup=kb_back_cancel())
        elif data == "act_allnotes":
            notes = db.get_all_notes(chat.id)
            if notes:
                text = "📋 <b>الملاحظات:</b>\n\n"
                for n in notes:
                    text += f"• 📝 {n}\n"
            else:
                text = "📋 لا توجد ملاحظات."
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_delnote":
            if not is_adm: return
            context.user_data["waiting"] = "delnote"
            await safe_edit(query, "🗑️ <b>حذف ملاحظة</b>\n\nاكتب اسم الملاحظة:", reply_markup=kb_back_cancel())

        # ═══ الفلاتر ═══
        elif data == "act_addfilter":
            if not is_adm: return
            context.user_data["waiting"] = "addfilter_kw"
            await safe_edit(query, "➕ <b>إضافة فلتر</b>\n\nاكتب الكلمة المفتاحية:", reply_markup=kb_back_cancel())
        elif data == "act_delfilter":
            if not is_adm: return
            context.user_data["waiting"] = "delfilter"
            await safe_edit(query, "➖ <b>حذف فلتر</b>\n\nاكتب الكلمة المفتاحية:", reply_markup=kb_back_cancel())
        elif data == "act_allfilters":
            filters_list = db.get_all_filters(chat.id)
            if filters_list:
                text = "📋 <b>الفلاتر:</b>\n\n"
                for f in filters_list:
                    text += f"• 🔍 {f}\n"
            else:
                text = "📋 لا توجد فلاتر."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ الأقفال ═══
        elif data.startswith("lock_"):
            if not is_adm: return
            lock_type = data.replace("lock_", "")
            locked = db.get_all_locks(chat.id)
            if lock_type in locked:
                db.unlock_type(chat.id, lock_type)
                status = "فتح 🔓"
            else:
                db.lock_type(chat.id, lock_type, user_id)
                status = "قفل 🔒"
            await safe_edit(query, f"🔒 <b>الأقفال</b>\n\nتم {status} {LOCK_TYPES.get(lock_type, lock_type)}:", reply_markup=kb_lock_types(chat.id))
        elif data == "act_lockall":
            if not is_adm: return
            for key in LOCK_TYPES:
                db.lock_type(chat.id, key, user_id)
            await safe_edit(query, "🔒 تم قفل الكل!", reply_markup=kb_lock_types(chat.id))
        elif data == "act_unlockall":
            if not is_adm: return
            db.unlock_all(chat.id)
            await safe_edit(query, "🔓 تم فتح الكل!", reply_markup=kb_lock_types(chat.id))

        # ═══ الكلمات المسيئة ═══
        elif data == "act_addbadword":
            if not is_adm: return
            context.user_data["waiting"] = "addbadword"
            await safe_edit(query, "➕ <b>إضافة كلمة مسيئة</b>\n\nاكتب الكلمة:", reply_markup=kb_back_cancel())
        elif data == "act_delbadword":
            if not is_adm: return
            context.user_data["waiting"] = "delbadword"
            await safe_edit(query, "➖ <b>حذف كلمة</b>\n\nاكتب الكلمة:", reply_markup=kb_back_cancel())
        elif data == "act_showbadwords":
            words = db.get_badwords(chat.id)
            if words:
                text = "📋 <b>الكلمات المسيئة:</b>\n\n" + "\n".join([f"• 🚫 {w}" for w in words])
            else:
                text = "📋 لا توجد كلمات مسيئة."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ الإعدادات ═══
        elif data == "act_setwelcome":
            if not is_adm: return
            context.user_data["waiting"] = "setwelcome"
            await safe_edit(query, "💬 <b>تعيين رسالة الترحيب</b>\n\nاكتب الرسالة (استخدم {user} لاسم العضو):", reply_markup=kb_back_cancel())
        elif data == "act_resetwelcome":
            if not is_adm: return
            db.update_setting(chat.id, "welcome_msg", "")
            await safe_edit(query, "🔄 تم إعادة الترحيب للافتراضي ✅", reply_markup=kb_back())
        elif data == "act_setlog":
            if not is_adm: return
            context.user_data["waiting"] = "setlog"
            await safe_edit(query, "📝 <b>قناة السجلات</b>\n\nأرسل معرف القناة أو حول البوت لها:", reply_markup=kb_back_cancel())
        elif data == "act_autodelete":
            if not is_adm: return
            context.user_data["waiting"] = "autodelete"
            await safe_edit(query, "⏱️ <b>حذف تلقائي</b>\n\nاكتب الثواني (0 للتعطيل):", reply_markup=kb_back_cancel())

        # ═══ المعلومات ═══
        elif data == "act_me":
            if not chat: return
            user = query.from_user
            rep = db.get_rep(chat.id, user.id)
            msg_cnt = db.get_msg_count(chat.id, user.id)
            warn_cnt = db.get_warning_count(chat.id, user.id)
            role = db.get_user_role(chat.id, user.id)
            is_admin = await check_is_admin(chat, user.id)
            status_text = "مشرف" if is_admin else ("مالك" if user.id == OWNER_ID else "عضو")
            text = (
                f"👤 <b>معلوماتي الشخصية</b>\n\n"
                f"📝 الاسم: {mention(user.id, user.first_name)}\n"
                f"🆔 المعرف: <code>{user.id}</code>\n"
                f"🏷️ الحالة: {status_text}\n"
                f"⭐ السمعة: {rep}\n"
                f"💬 الرسائل: {msg_cnt}\n"
                f"⚠️ التحذيرات: {warn_cnt}/{WARN_LIMIT}\n"
            )
            if role:
                text += f"🎖️ الدور: {role}\n"
            await safe_edit(query, text, reply_markup=kb_back())

        elif data == "act_userinfo":
            context.user_data["waiting"] = "userinfo"
            await safe_edit(query, "👤 <b>معلومات مستخدم</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())

        elif data == "act_groupstats":
            stats = db.get_stats(chat.id)
            if stats:
                text = (
                    f"📊 <b>إحصائيات المجموعة</b>\n\n"
                    f"💬 الرسائل: {stats.get('total_messages', 0)}\n"
                    f"➕ الانضمامات: {stats.get('total_joins', 0)}\n"
                    f"➖ المغادرات: {stats.get('total_leaves', 0)}\n"
                    f"🚫 الحظر: {stats.get('total_bans', 0)}\n"
                    f"🔇 الكتم: {stats.get('total_mutes', 0)}\n"
                    f"⚠️ التحذيرات: {stats.get('total_warns', 0)}\n"
                    f"🗑️ المحذوفات: {stats.get('total_deleted', 0)}\n"
                    f"🛡️ غارات محظورة: {stats.get('total_raids_blocked', 0)}\n"
                    f"🔗 روابط محظورة: {stats.get('total_links_blocked', 0)}\n"
                    f"📨 سبام محظور: {stats.get('total_spam_blocked', 0)}\n"
                    f"🌊 فلود محظور: {stats.get('total_flood_blocked', 0)}\n"
                )
            else:
                text = "📊 لا توجد إحصائيات بعد."
            await safe_edit(query, text, reply_markup=kb_back())

        elif data == "act_admins":
            try:
                admins = await chat.get_administrators()
                text = "👥 <b>المشرفين:</b>\n\n"
                for a in admins:
                    status = "مالك" if a.status == ChatMemberStatus.OWNER else "مشرف"
                    text += f"• {mention(a.user.id, a.user.first_name)} - {status}\n"
                await safe_edit(query, text, reply_markup=kb_back())
            except: pass

        elif data == "act_log":
            logs = db.get_action_log(chat.id, 15)
            if logs:
                text = "📋 <b>سجل الإجراءات:</b>\n\n"
                for l in logs:
                    text += f"• {l['action']} → <code>{l['target_id']}</code> {l['reason']}\n"
            else:
                text = "📋 لا توجد إجراءات مسجلة."
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
                ("وضع الغياب", s.get('absence_mode', 0)),
            ]
            text = "🛡️ <b>حالة الحماية:</b>\n\n"
            for name, val in protections:
                text += f"{'✅' if val else '❌'} {name}\n"
            await safe_edit(query, text, reply_markup=kb_back())

        elif data == "act_topactive":
            top = db.get_top_msg(chat.id, 10)
            if top:
                text = "📈 <b>الأعضاء الأنشط:</b>\n\n"
                for i, (uid, cnt) in enumerate(top, 1):
                    text += f"{i}. {mention(uid, str(uid))} - {cnt} رسالة\n"
            else:
                text = "📈 لا توجد بيانات."
            await safe_edit(query, text, reply_markup=kb_back())

        elif data == "act_inactives":
            inactive = db.get_inactive_users(chat.id, 7)
            if inactive:
                text = f"👻 <b>الأعضاء غير النشطين</b> (7 أيام):\n\n"
                for u in inactive[:20]:
                    text += f"• <code>{u['user_id']}</code> - آخر نشاط: {u['last_active']}\n"
            else:
                text = "👻 جميع الأعضاء نشطين!"
            await safe_edit(query, text, reply_markup=kb_back())

        elif data == "act_graphic":
            stats = db.get_stats(chat.id)
            if stats:
                labels = ["الرسائل", "الحظر", "الكتم", "التحذيرات", "المحذوفات", "الغارات", "الروابط", "السبام"]
                values = [
                    stats.get('total_messages', 0), stats.get('total_bans', 0),
                    stats.get('total_mutes', 0), stats.get('total_warns', 0),
                    stats.get('total_deleted', 0), stats.get('total_raids_blocked', 0),
                    stats.get('total_links_blocked', 0), stats.get('total_spam_blocked', 0)
                ]
                max_val = max(values) if max(values) > 0 else 1
                text = "📊 <b>رسم بياني للمجموعة</b>\n\n"
                for label, val in zip(labels, values):
                    bar_len = int((val / max_val) * 20)
                    bar = "█" * bar_len + "░" * (20 - bar_len)
                    text += f"{label}: {bar} {val}\n"
            else:
                text = "📊 لا توجد إحصائيات."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ السمعة ═══
        elif data == "act_giverep":
            context.user_data["waiting"] = "giverep"
            await safe_edit(query, "⭐ <b>إعطاء نقطة سمعة</b>\n\nرد على رسالة العضو:", reply_markup=kb_back_cancel())
        elif data == "act_reprank":
            top = db.get_top_rep(chat.id, 10)
            if top:
                text = "📊 <b>ترتيب السمعة:</b>\n\n"
                medals = ["🥇", "🥈", "🥉"]
                for i, (uid, rep) in enumerate(top):
                    medal = medals[i] if i < 3 else f"{i+1}."
                    text += f"{medal} {mention(uid, str(uid))} - {rep} ⭐\n"
            else:
                text = "📊 لا توجد بيانات سمعة."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ الذكاء الاصطناعي ═══
        elif data == "act_addautoreply":
            if not is_adm: return
            context.user_data["waiting"] = "addautoreply_trigger"
            await safe_edit(query, "🤖 <b>إضافة رد تلقائي</b>\n\nاكتب النص الذي سيتم الرد عليه:", reply_markup=kb_back_cancel())
        elif data == "act_autoreplies":
            replies = db.get_auto_replies(chat.id)
            if replies:
                text = "📋 <b>الردود التلقائية:</b>\n\n"
                for trigger, reply_text in replies:
                    text += f"• <b>{trigger}</b> → {reply_text}\n"
            else:
                text = "📋 لا توجد ردود تلقائية."
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_delautoreply":
            if not is_adm: return
            context.user_data["waiting"] = "delautoreply"
            await safe_edit(query, "➖ <b>حذف رد تلقائي</b>\n\nاكتب النص:", reply_markup=kb_back_cancel())

        # ═══ الأدوار ═══
        elif data == "act_assignrole":
            if not is_adm: return
            context.user_data["waiting"] = "assignrole"
            await safe_edit(query, "🎖️ <b>تعيين دور</b>\n\nرد على رسالة المستخدم + اكتب اسم الدور:", reply_markup=kb_back_cancel())
        elif data == "act_removerole":
            if not is_adm: return
            context.user_data["waiting"] = "removerole"
            await safe_edit(query, "🗑️ <b>إزالة دور</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())
        elif data == "act_listroles":
            roles = db.get_all_roles(chat.id)
            if roles:
                text = "📋 <b>الأدوار:</b>\n\n"
                for uid, role_name in roles:
                    text += f"• {mention(uid, str(uid))} - 🎖️ {role_name}\n"
            else:
                text = "📋 لا توجد أدوار مخصصة."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ الجدولة ═══
        elif data == "act_schedule":
            if not is_adm: return
            context.user_data["waiting"] = "schedule"
            await safe_edit(query, "⏰ <b>إرسال مجدول</b>\n\nاكتب: الدقائق | الرسالة\nمثال: 30 | حان وقت الصلاة", reply_markup=kb_back_cancel())
        elif data == "act_scheduledlist":
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("SELECT * FROM scheduled_messages WHERE chat_id = ? AND sent = 0", (chat.id,))
                rows = c.fetchall()
                conn.close()
            if rows:
                text = "📋 <b>الرسائل المجدولة:</b>\n\n"
                for r in rows:
                    text += f"• {r['text'][:30]}... - {r['send_at']}\n"
            else:
                text = "📋 لا توجد رسائل مجدولة."
            await safe_edit(query, text, reply_markup=kb_back())

        # ═══ أخرى ═══
        elif data == "act_announce":
            if not is_adm: return
            context.user_data["waiting"] = "announce"
            await safe_edit(query, "📢 <b>إعلان</b>\n\nاكتب نص الإعلان:", reply_markup=kb_back_cancel())
        elif data == "act_report":
            context.user_data["waiting"] = "report"
            await safe_edit(query, "🚨 <b>بلاغ</b>\n\nرد على رسالة المستخدم + السبب:", reply_markup=kb_back_cancel())
        elif data == "act_dice":
            result = random.randint(1, 6)
            await safe_edit(query, f"🎲 النتيجة: <b>{result}</b>", reply_markup=kb_back())
        elif data == "act_coin":
            result = random.choice(["رأس", "كتابة"])
            await safe_edit(query, f"🪙 النتيجة: <b>{result}</b>", reply_markup=kb_back())
        elif data == "act_send":
            if not is_adm: return
            context.user_data["waiting"] = "send"
            await safe_edit(query, "📨 <b>إرسال رسالة</b>\n\nرد على رسالة المستخدم + اكتب الرسالة:", reply_markup=kb_back_cancel())
        elif data == "act_list":
            if not is_adm: return
            try:
                count = await chat.get_member_count()
                await safe_edit(query, f"👥 <b>عدد الأعضاء:</b> {count}", reply_markup=kb_back())
            except: pass
        elif data == "act_infopvt":
            if not is_adm: return
            context.user_data["waiting"] = "infopvt"
            await safe_edit(query, "📩 <b>إرسال معلومات بالخاص</b>\n\nرد على رسالة المستخدم:", reply_markup=kb_back_cancel())

        # ═══ التنظيف ═══
        elif data == "clean_bot":
            if not is_adm: return
            await safe_edit(query, "🗑️ سيتم حذف رسائل البوت...", reply_markup=kb_back())
        elif data == "clean_tempmutes":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM temp_mutes WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف جميع الكتم المؤقت ✅", reply_markup=kb_back())
        elif data == "clean_warns":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM warnings WHERE chat_id = ?", (chat.id,))
                c.execute("DELETE FROM warning_counts WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف جميع التحذيرات ✅", reply_markup=kb_back())
        elif data == "clean_stats":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM group_stats WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف الإحصائيات ✅", reply_markup=kb_back())
        elif data == "clean_log":
            if not is_adm: return
            with db.lock:
                conn = db._get_conn()
                c = conn.cursor()
                c.execute("DELETE FROM action_log WHERE chat_id = ?", (chat.id,))
                conn.commit()
                conn.close()
            await safe_edit(query, "🗑️ تم حذف سجل الإجراءات ✅", reply_markup=kb_back())

        # ═══ أدوات المالك ═══
        elif data == "owner_broadcast":
            if not is_owner: return
            context.user_data["waiting"] = "owner_broadcast"
            await safe_edit(query, "📢 <b>إعلان لكل المجموعات</b>\n\nاكتب نص الإعلان:", reply_markup=kb_back_cancel())
        elif data == "owner_stats":
            group_ids = db.get_all_group_ids()
            text = f"📊 <b>إحصائيات عامة</b>\n\n📁 عدد المجموعات: {len(group_ids)}\n"
            await safe_edit(query, text, reply_markup=kb_back())

    except Exception as e:
        logger.error(f"callback_handler error: {e}")


# ═════════════════════════════════════════════════════════════════
# معالجة الرسائل النصية
# ═════════════════════════════════════════════════════════════════

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
    chat = update.effective_chat
    user = update.effective_user
    if not user or not chat:
        return
    text = msg.text or ""
    user_id = user.id
    target = msg.reply_to_message
    target_id = target.from_user.id if target and target.from_user else None
    target_name = target.from_user.first_name if target and target.from_user else None

    is_adm = await check_is_admin(chat, user_id)
    is_owner = user_id == OWNER_ID

    # ═══ معالجة وضع الانتظار ═══
    waiting = context.user_data.get("waiting")

    if waiting:
        # حظر
        if waiting == "ban":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                reason = text if text else "بدون سبب"
                try:
                    await chat.ban_member(target_id)
                    await msg.reply_text(f"🚫 تم حظر {mention(target_id, target_name)}\n📋 السبب: {reason}", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "ban", target_id, reason)
                    db.increment_stat(chat.id, "total_bans")
                    await send_log(chat.id, f"🚫 حظر: {mention(target_id, target_name)} بواسطة {mention(user_id, user.first_name)}\nالسبب: {reason}", context)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        # إلغاء حظر
        elif waiting == "unban":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    await chat.unban_member(target_id)
                    await msg.reply_text(f"✅ تم إلغاء حظر {mention(target_id, target_name)}", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "unban", target_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # كتم
        elif waiting == "mute":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    await chat.restrict_member(target_id, ChatPermissions(can_send_messages=False))
                    await msg.reply_text(f"🔇 تم كتم {mention(target_id, target_name)}", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "mute", target_id)
                    db.increment_stat(chat.id, "total_mutes")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # إلغاء كتم
        elif waiting == "unmute":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    perms = ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True,
                                          can_send_audios=True, can_send_documents=True, can_send_video_notes=True,
                                          can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                                          can_add_web_page_previews=True)
                    await chat.restrict_member(target_id, perms)
                    await msg.reply_text(f"🔊 تم إلغاء كتم {mention(target_id, target_name)}", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "unmute", target_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # كتم مؤقت - اختيار المستخدم
        elif waiting == "tmute_select":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                context.user_data["target_id"] = target_id
                context.user_data["waiting"] = None
                await msg.reply_text("⏱️ اختر مدة الكتم:", reply_markup=kb_mute_time(target_id))
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم أولاً")
                context.user_data.pop("waiting", None)
            return

        # طرد
        elif waiting == "kick":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    await chat.ban_member(target_id)
                    await chat.unban_member(target_id)
                    await msg.reply_text(f"👢 تم طرد {mention(target_id, target_name)}", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "kick", target_id)
                    db.increment_stat(chat.id, "total_kicks")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # تحذير
        elif waiting == "warn":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                reason = text if text else "بدون سبب"
                count = db.add_warning(chat.id, target_id, reason, user_id)
                await msg.reply_text(f"⚠️ تحذير {count}/{WARN_LIMIT} لـ {mention(target_id, target_name)}\n📋 السبب: {reason}", parse_mode="HTML")
                db.increment_stat(chat.id, "total_warns")
                if count >= WARN_LIMIT:
                    settings = db.get_settings(chat.id)
                    action = settings.get('warn_action', 'mute')
                    try:
                        if action == 'mute':
                            await chat.restrict_member(target_id, ChatPermissions(can_send_messages=False))
                            await msg.reply_text(f"🔇 تم كتم {mention(target_id, target_name)} - تجاوز حد التحذير!", parse_mode="HTML")
                        elif action == 'kick':
                            await chat.ban_member(target_id)
                            await chat.unban_member(target_id)
                            await msg.reply_text(f"👢 تم طرد {mention(target_id, target_name)} - تجاوز حد التحذير!", parse_mode="HTML")
                        elif action == 'ban':
                            await chat.ban_member(target_id)
                            await msg.reply_text(f"🚫 تم حظر {mention(target_id, target_name)} - تجاوز حد التحذير!", parse_mode="HTML")
                        db.reset_warnings(chat.id, target_id)
                    except: pass
            context.user_data.pop("waiting", None); return

        # إزالة تحذير
        elif waiting == "unwarn":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                count = db.get_warning_count(chat.id, target_id)
                if count > 0:
                    db.reset_warnings(chat.id, target_id)
                    await msg.reply_text(f"✅ تم إزالة تحذيرات {mention(target_id, target_name)}", parse_mode="HTML")
                else:
                    await msg.reply_text("❌ لا توجد تحذيرات")
            context.user_data.pop("waiting", None); return

        # عرض التحذيرات
        elif waiting == "warns":
            if target_id:
                count = db.get_warning_count(chat.id, target_id)
                warns = db.get_warnings(chat.id, target_id)
                text_out = f"📋 <b>تحذيرات {mention(target_id, target_name)}</b> ({count}/{WARN_LIMIT}):\n\n"
                for i, w in enumerate(warns[:10], 1):
                    text_out += f"{i}. {w['reason']} - {w['warned_at'][:10]}\n"
                await msg.reply_text(text_out, parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        # حذف التحذيرات
        elif waiting == "delwarn":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                db.reset_warnings(chat.id, target_id)
                await msg.reply_text(f"🗑️ تم حذف تحذيرات {mention(target_id, target_name)} ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        # حذف رسالة
        elif waiting == "del":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target:
                try:
                    await target.delete()
                    await msg.delete()
                    db.increment_stat(chat.id, "total_deleted")
                except: pass
            context.user_data.pop("waiting", None); return

        # حذف متعدد
        elif waiting == "purge":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target:
                try:
                    deleted = 0
                    msg_id = target.message_id
                    current_id = msg.message_id
                    for mid in range(msg_id, current_id + 1):
                        try:
                            await chat.delete_message(mid)
                            deleted += 1
                        except: pass
                    await msg.reply_text(f"🗑️ تم حذف {deleted} رسالة ✅")
                    db.increment_stat(chat.id, "total_deleted")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # ترقية مشرف
        elif waiting == "promote":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    await chat.promote_member(target_id, can_manage_chat=True, can_delete_messages=True,
                                            can_restrict_members=True, can_invite_users=True, can_pin_messages=True)
                    await msg.reply_text(f"📈 تم ترقية {mention(target_id, target_name)} إلى مشرف ✅", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "promote", target_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # تخفيض مشرف
        elif waiting == "demote":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                try:
                    await chat.promote_member(target_id, can_manage_chat=False, can_delete_messages=False,
                                            can_restrict_members=False, can_invite_users=False, can_pin_messages=False)
                    await msg.reply_text(f"📉 تم تخفيض {mention(target_id, target_name)} ✅", parse_mode="HTML")
                    db.log_action(chat.id, user_id, "demote", target_id)
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ: {e}")
            context.user_data.pop("waiting", None); return

        # إضافة للقائمة السوداء
        elif waiting == "badd":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                reason = text if text else "بدون سبب"
                db.add_blacklist(chat.id, target_id, reason, user_id)
                await msg.reply_text(f"🖤 تم إضافة {mention(target_id, target_name)} للقائمة السوداء ✅", parse_mode="HTML")
                try:
                    await chat.ban_member(target_id)
                    await msg.reply_text("🚫 تم حظره تلقائياً!", parse_mode="HTML")
                except: pass
            context.user_data.pop("waiting", None); return

        # إزالة من القائمة السوداء
        elif waiting == "bdel":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                if db.remove_blacklist(chat.id, target_id):
                    try:
                        await chat.unban_member(target_id)
                        await msg.reply_text(f"💚 تم إزالة {mention(target_id, target_name)} من القائمة السوداء وإلغاء حظره ✅", parse_mode="HTML")
                    except:
                        await msg.reply_text(f"💚 تم إزالته من القائمة السوداء ✅", parse_mode="HTML")
                else:
                    await msg.reply_text("❌ المستخدم غير موجود في القائمة السوداء")
            context.user_data.pop("waiting", None); return

        # تثبيت
        elif waiting == "pin":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target:
                try:
                    await target.pin()
                    await msg.reply_text("📌 تم تثبيت الرسالة ✅")
                except: pass
            context.user_data.pop("waiting", None); return

        # تعيين القوانين
        elif waiting == "setrules":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if text:
                db.update_setting(chat.id, "rules", text)
                await msg.reply_text("📋 تم تعيين القوانين ✅")
            context.user_data.pop("waiting", None); return

        # تعيين الوصف
        elif waiting == "setdesc":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if text:
                try:
                    await chat.set_description(text)
                    await msg.reply_text("📝 تم تعيين وصف المجموعة ✅")
                except: pass
            context.user_data.pop("waiting", None); return

        # تعديل الرسالة المثبتة
        elif waiting == "editpin":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target and text:
                try:
                    await target.edit_text(text)
                    await msg.reply_text("📝 تم تعديل الرسالة المثبتة ✅")
                except: pass
            context.user_data.pop("waiting", None); return

        # حفظ ملاحظة - الاسم
        elif waiting == "savenote_name":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            context.user_data["note_name"] = text
            context.user_data["waiting"] = "savenote_content"
            await msg.reply_text("📝 الآن اكتب محتوى الملاحظة:")
            return

        # حفظ ملاحظة - المحتوى
        elif waiting == "savenote_content":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            note_name = context.user_data.get("note_name", "بدون اسم")
            db.save_note(chat.id, note_name, text, user_id)
            await msg.reply_text(f"💾 تم حفظ الملاحظة: {note_name} ✅")
            context.user_data.pop("waiting", None)
            context.user_data.pop("note_name", None)
            return

        # استرجاع ملاحظة
        elif waiting == "getnote":
            content = db.get_note(chat.id, text)
            if content:
                await msg.reply_text(f"📝 {content}")
            else:
                await msg.reply_text("❌ الملاحظة غير موجودة")
            context.user_data.pop("waiting", None); return

        # حذف ملاحظة
        elif waiting == "delnote":
            if db.delete_note(chat.id, text):
                await msg.reply_text("🗑️ تم حذف الملاحظة ✅")
            else:
                await msg.reply_text("❌ الملاحظة غير موجودة")
            context.user_data.pop("waiting", None); return

        # إضافة فلتر - الكلمة
        elif waiting == "addfilter_kw":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            context.user_data["filter_kw"] = text
            context.user_data["waiting"] = "addfilter_reply"
            await msg.reply_text("📝 الآن اكتب الرد:")
            return

        # إضافة فلتر - الرد
        elif waiting == "addfilter_reply":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            kw = context.user_data.get("filter_kw", "")
            db.save_filter(chat.id, kw, text, user_id)
            await msg.reply_text(f"✅ تم إضافة فلتر: {kw} → {text}")
            context.user_data.pop("waiting", None)
            context.user_data.pop("filter_kw", None)
            return

        # حذف فلتر
        elif waiting == "delfilter":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.delete_filter(chat.id, text):
                await msg.reply_text("🗑️ تم حذف الفلتر ✅")
            else:
                await msg.reply_text("❌ الفلتر غير موجود")
            context.user_data.pop("waiting", None); return

        # كلمة مسيئة
        elif waiting == "addbadword":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            db.add_badword(chat.id, text, user_id)
            await msg.reply_text(f"🚫 تم إضافة الكلمة: {text} ✅")
            context.user_data.pop("waiting", None); return

        elif waiting == "delbadword":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.remove_badword(chat.id, text):
                await msg.reply_text("🗑️ تم حذف الكلمة ✅")
            else:
                await msg.reply_text("❌ الكلمة غير موجودة")
            context.user_data.pop("waiting", None); return

        # الترحيب
        elif waiting == "setwelcome":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            db.update_setting(chat.id, "welcome_msg", text)
            await msg.reply_text("💬 تم تعيين الترحيب ✅")
            context.user_data.pop("waiting", None); return

        # قناة السجلات
        elif waiting == "setlog":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            try:
                log_id = int(text)
                db.update_setting(chat.id, "log_channel_id", log_id)
                await msg.reply_text(f"📝 تم تعيين قناة السجلات: {log_id} ✅")
            except:
                await msg.reply_text("❌ أرسل معرف القناة (رقم)")
            context.user_data.pop("waiting", None); return

        # حذف تلقائي
        elif waiting == "autodelete":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            try:
                val = int(text)
                db.update_setting(chat.id, "auto_delete", val)
                await msg.reply_text(f"⏱️ تم تعيين الحذف التلقائي: {val} ثانية ✅" if val > 0 else "⏱️ تم تعطيل الحذف التلقائي ✅")
            except:
                await msg.reply_text("❌ اكتب رقماً")
            context.user_data.pop("waiting", None); return

        # حد الغارة
        elif waiting == "set_raid_threshold":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            try:
                val = int(text)
                if 2 <= val <= 50:
                    db.update_setting(chat.id, "raid_threshold", val)
                    await msg.reply_text(f"⚡ تم تعيين حد الغارة: {val} ✅")
                else:
                    await msg.reply_text("❌ القيمة بين 2 و 50")
            except:
                await msg.reply_text("❌ اكتب رقماً")
            context.user_data.pop("waiting", None); return

        # القائمة البيضاء
        elif waiting == "wl_add":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                db.add_whitelist(chat.id, target_id, user_id)
                await msg.reply_text(f"➕ تم إضافة {mention(target_id, target_name)} للقائمة البيضاء ✅", parse_mode="HTML")
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        elif waiting == "wl_remove":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                if db.remove_whitelist(chat.id, target_id):
                    await msg.reply_text("➖ تم الإزالة من القائمة البيضاء ✅")
                else:
                    await msg.reply_text("❌ غير موجود في القائمة")
            context.user_data.pop("waiting", None); return

        # القائمة السوداء
        elif waiting == "bl_add":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                reason = text if text else "بدون سبب"
                db.add_blacklist(chat.id, target_id, reason, user_id)
                await msg.reply_text(f"🖤 تم إضافة {mention(target_id, target_name)} للقائمة السوداء ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "bl_remove":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                if db.remove_blacklist(chat.id, target_id):
                    await msg.reply_text("💚 تم الإزالة من القائمة السوداء ✅")
                else:
                    await msg.reply_text("❌ غير موجود في القائمة")
            context.user_data.pop("waiting", None); return

        # معلومات مستخدم
        elif waiting == "userinfo":
            if target_id:
                rep = db.get_rep(chat.id, target_id)
                msg_cnt = db.get_msg_count(chat.id, target_id)
                warn_cnt = db.get_warning_count(chat.id, target_id)
                role = db.get_user_role(chat.id, target_id)
                is_bl = db.is_blacklisted(chat.id, target_id)
                try:
                    member = await chat.get_member(target_id)
                    status = str(member.status).split('.')[-1]
                    text_info = (
                        f"👤 <b>معلومات المستخدم</b>\n\n"
                        f"🆔 المعرف: <code>{target_id}</code>\n"
                        f"📝 الاسم: {mention(target_id, target_name)}\n"
                        f"🏷️ الحالة: {status}\n"
                        f"⭐ السمعة: {rep}\n"
                        f"💬 الرسائل: {msg_cnt}\n"
                        f"⚠️ التحذيرات: {warn_cnt}/{WARN_LIMIT}\n"
                    )
                    if role:
                        text_info += f"🎖️ الدور: {role}\n"
                    if is_bl:
                        text_info += "🖤 في القائمة السوداء!\n"
                except:
                    text_info = f"👤 المعرف: <code>{target_id}</code>\n⭐ السمعة: {rep}\n💬 الرسائل: {msg_cnt}"
                await msg.reply_text(text_info, parse_mode="HTML")
            else:
                await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        # سمعة
        elif waiting == "giverep":
            if target_id and target_id != user_id:
                rep = db.add_rep(chat.id, target_id)
                await msg.reply_text(f"⭐ تم إعطاء نقطة سمعة لـ {mention(target_id, target_name)} ({rep} نقطة)", parse_mode="HTML")
            elif target_id == user_id:
                await msg.reply_text("❌ لا يمكنك إعطاء سمعة لنفسك!")
            else:
                await msg.reply_text("❌ رد على رسالة العضو")
            context.user_data.pop("waiting", None); return

        # إعلان
        elif waiting == "announce":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            await msg.reply_text(f"📢 <b>إعلان:</b>\n\n{text}", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        # بلاغ
        elif waiting == "report":
            settings = db.get_settings(chat.id)
            if settings.get('report_enabled', 1):
                if target_id:
                    reason = text if text else "بدون سبب"
                    admins = await chat.get_administrators()
                    admin_text = " ".join([f"<a href=\"tg://user?id={a.user.id}\">‌</a>" for a in admins[:5]])
                    await msg.reply_text(
                        f"🚨 <b>بلاغ</b>\n\n👤 المبلغ: {mention(user_id, user.first_name)}\n🎯 المبلغ عنه: {mention(target_id, target_name)}\n📋 السبب: {reason}\n{admin_text}",
                        parse_mode="HTML")
                else:
                    await msg.reply_text("❌ رد على رسالة المستخدم")
            context.user_data.pop("waiting", None); return

        # إعلان المالك
        elif waiting == "owner_broadcast":
            if user_id != OWNER_ID:
                context.user_data.pop("waiting", None); return
            group_ids = db.get_all_group_ids()
            sent = 0
            for gid in group_ids:
                try:
                    await context.bot.send_message(chat_id=gid, text=f"📢 <b>إعلان من المالك</b>\n\n{text}", parse_mode="HTML")
                    sent += 1
                except: pass
            await msg.reply_text(f"📢 تم إرسال الإعلان إلى {sent}/{len(group_ids)} مجموعة ✅")
            context.user_data.pop("waiting", None); return

        # إرسال رسالة لعضو
        elif waiting == "send":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id and text:
                try:
                    await context.bot.send_message(chat_id=target_id, text=f"📨 <b>رسالة من إدارة المجموعة</b>\n\n{text}", parse_mode="HTML")
                    await msg.reply_text("📨 تم إرسال الرسالة ✅")
                except:
                    await msg.reply_text("❌ لا يمكن إرسال الرسالة. المستخدم قد يكون حظر البوت.")
            context.user_data.pop("waiting", None); return

        # إرسال معلومات بالخاص
        elif waiting == "infopvt":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                rep = db.get_rep(chat.id, target_id)
                msg_cnt = db.get_msg_count(chat.id, target_id)
                warn_cnt = db.get_warning_count(chat.id, target_id)
                try:
                    await context.bot.send_message(chat_id=target_id,
                        text=f"📩 <b>معلوماتك في المجموعة</b>\n\n⭐ السمعة: {rep}\n💬 الرسائل: {msg_cnt}\n⚠️ التحذيرات: {warn_cnt}/{WARN_LIMIT}",
                        parse_mode="HTML")
                    await msg.reply_text("📩 تم إرسال المعلومات بالخاص ✅")
                except:
                    await msg.reply_text("❌ لا يمكن الإرسال بالخاص")
            context.user_data.pop("waiting", None); return

        # رد ذكي - الكلمة
        elif waiting == "addautoreply_trigger":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            context.user_data["autoreply_trigger"] = text
            context.user_data["waiting"] = "addautoreply_response"
            await msg.reply_text("📝 الآن اكتب الرد التلقائي:")
            return

        # رد ذكي - الرد
        elif waiting == "addautoreply_response":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            trigger = context.user_data.get("autoreply_trigger", "")
            db.add_auto_reply(chat.id, trigger, text, user_id)
            await msg.reply_text(f"🤖 تم إضافة رد ذكي: {trigger} → {text} ✅")
            context.user_data.pop("waiting", None)
            context.user_data.pop("autoreply_trigger", None)
            return

        # حذف رد ذكي
        elif waiting == "delautoreply":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if db.delete_auto_reply(chat.id, text):
                await msg.reply_text("🗑️ تم حذف الرد الذكي ✅")
            else:
                await msg.reply_text("❌ الرد غير موجود")
            context.user_data.pop("waiting", None); return

        # تعيين دور
        elif waiting == "assignrole":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id and text:
                db.assign_role(chat.id, target_id, text, user_id)
                await msg.reply_text(f"🎖️ تم تعيين دور '{text}' لـ {mention(target_id, target_name)} ✅", parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        # إزالة دور
        elif waiting == "removerole":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if target_id:
                if db.remove_role(chat.id, target_id):
                    await msg.reply_text("🗑️ تم إزالة الدور ✅")
                else:
                    await msg.reply_text("❌ لا يوجد دور لهذا المستخدم")
            context.user_data.pop("waiting", None); return

        # جدولة
        elif waiting == "schedule":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|", 1)
                try:
                    minutes = int(parts[0].strip())
                    msg_text = parts[1].strip()
                    send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                    db.add_scheduled(chat.id, msg_text, send_at, user_id)
                    await msg.reply_text(f"⏰ تم جدولة الرسالة بعد {minutes} دقيقة ✅")
                except:
                    await msg.reply_text("❌ الصيغة: الدقائق | الرسالة")
            else:
                await msg.reply_text("❌ استخدم: الدقائق | الرسالة\nمثال: 30 | حان وقت الصلاة")
            context.user_data.pop("waiting", None); return

        else:
            context.user_data.pop("waiting", None)

    # ═══ أنظمة الحماية التلقائية ═══
    if chat.type == "private":
        return

    # تجاهل المشرفين والمالك
    if user_id == OWNER_ID or user_id in SUDO_USERS:
        return
    is_user_adm = await check_is_admin(chat, user_id)
    if is_user_adm:
        return

    # القائمة السوداء
    if db.is_blacklisted(chat.id, user_id):
        try:
            await msg.delete()
            await chat.ban_member(user_id)
            db.increment_stat(chat.id, "total_bans")
        except: pass
        return

    settings = db.get_settings(chat.id)

    # وضع الصيانة
    if settings.get('maintenance_mode', 0):
        try:
            await msg.delete()
            await chat.ban_member(user_id)
            await chat.unban_member(user_id)
        except: pass
        return

    # وضع الغياب - رد تلقائي
    if settings.get('absence_mode', 0):
        try:
            await msg.reply_text("🌙 المشرفون غائبون حالياً. سيتم الرد عليكم لاحقاً.")
        except: pass

    # الوضع البطيء
    slow = settings.get('slow_mode', 0)
    if slow > 0 and check_slow_mode(chat.id, user_id, slow):
        try: await msg.delete()
        except: pass
        return

    # منع الإيموجي
    if settings.get('anti_emoji', 0):
        emoji_count = len(re.findall(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U0001F900-\U0001F9FF]', text))
        if emoji_count > 5:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass
            return

    # منع العربية
    if settings.get('anti_arabic', 0) and re.search(r'[\u0600-\u06FF]', text):
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass
        return

    # الأقفال
    locked = db.get_all_locks(chat.id)
    if locked:
        if "text" in locked and text:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if "links" in locked and has_link(text):
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
        if "forward" in locked and msg.forward_date:
            try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
            except: pass; return
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
                count = db.add_warning(chat.id, user_id, "إرسال رابط", 0)
                await chat.send_message(f"⚠️ تحذير {count}/{WARN_LIMIT} - روابط محظورة!", parse_mode="HTML")
            elif link_action == 'mute':
                await chat.restrict_member(user_id, ChatPermissions(can_send_messages=False))
                await chat.send_message(f"🔇 تم كتم {mention(user_id, user.first_name)} - روابط!", parse_mode="HTML")
            elif link_action == 'ban':
                await chat.ban_member(user_id)
                await chat.send_message(f"🚫 تم حظر {mention(user_id, user.first_name)} - روابط!", parse_mode="HTML")
        except: pass
        return

    # منع أرقام الهاتف
    if settings.get('anti_phone', 0) and has_phone(text):
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass; return

    # منع المعرفات
    if settings.get('anti_username', 0) and has_username(text):
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass; return

    # منع الرسائل الطويلة
    max_len = settings.get('max_msg_length', 0)
    if settings.get('anti_longmsg', 0) and max_len > 0 and len(text) > max_len:
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass; return

    # حماية السبام
    if settings.get('anti_spam', 1) and is_spam(text):
        try: await msg.delete(); db.increment_stat(chat.id, "total_spam_blocked")
        except: pass; return

    # حماية الفلود
    if settings.get('anti_flood', 1):
        max_msgs = settings.get('max_flood_msgs', 5)
        interval = settings.get('flood_interval', 5)
        if check_flood(chat.id, user_id, max_msgs, interval):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_flood_blocked")
                await chat.restrict_member(user_id, ChatPermissions(can_send_messages=False))
                await chat.send_message(f"🔇 تم كتم {mention(user_id, user.first_name)} - فلود! (5 دقائق)", parse_mode="HTML")
            except: pass
            return

    # منع التوجيه
    if settings.get('anti_forward', 0) and msg.forward_date:
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass; return

    # منع القنوات
    if settings.get('anti_channel', 1) and msg.sender_chat and msg.sender_chat.id != chat.id:
        try: await msg.delete(); db.increment_stat(chat.id, "total_deleted")
        except: pass; return

    # فلتر الكلمات المسيئة
    if settings.get('anti_badword', 1):
        badwords = db.get_badwords(chat.id)
        text_lower = text.lower()
        for bw in badwords:
            if bw in text_lower:
                try:
                    await msg.delete()
                    db.increment_stat(chat.id, "total_deleted")
                    count = db.add_warning(chat.id, user_id, "كلمة مسيئة", 0)
                    await chat.send_message(f"⚠️ تحذير {count}/{WARN_LIMIT} - كلمات مسيئة!", parse_mode="HTML")
                except: pass
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

    # الردود الذكية التلقائية
    auto_replies = db.get_auto_replies(chat.id)
    for trigger, reply_t in auto_replies:
        if trigger.lower() in text.lower():
            await msg.reply_text(reply_t)
            break

    # عداد الرسائل
    db.increment_msg_count(chat.id, user_id)
    db.increment_stat(chat.id, "total_messages")

    # حذف تلقائي
    auto_del = settings.get('auto_delete', 0)
    if auto_del > 0:
        async def auto_delete_msg():
            await asyncio.sleep(auto_del)
            try: await msg.delete()
            except: pass
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
        except: pass


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
                except: pass
            continue

        if member.id == OWNER_ID:
            continue

        if db.is_whitelisted(chat.id, member.id):
            continue

        # القائمة السوداء - حظر تلقائي
        if db.is_blacklisted(chat.id, member.id):
            try:
                await chat.ban_member(member.id)
                await chat.send_message(f"🖤 حظر تلقائي - القائمة السوداء: {mention(member.id, member.first_name)}", parse_mode="HTML")
            except: pass
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
                except: pass
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
            except: pass
            continue

        # ترحيب
        if settings.get('auto_welcome', 1):
            welcome_msg = settings.get('welcome_msg', '')
            if not welcome_msg:
                welcome_msg = DEFAULT_WELCOME
            formatted = welcome_msg.replace('{user}', mention(member.id, member.first_name))
            try:
                await chat.send_message(formatted, parse_mode="HTML")
            except: pass


async def left_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    db.increment_stat(chat.id, "total_leaves")


# ═════════════════════════════════════════════════════════════════
# فحص الكتم المؤقت والرسائل المجدولة
# ═════════════════════════════════════════════════════════════════

async def check_temp_mutes(context: ContextTypes.DEFAULT_TYPE):
    expired = db.get_expired_mutes()
    for mute in expired:
        try:
            perms = ChatPermissions(
                can_send_messages=True, can_send_photos=True, can_send_videos=True,
                can_send_audios=True, can_send_documents=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True,
            )
            await context.bot.restrict_chat_member(mute['chat_id'], mute['user_id'], perms)
        except: pass


async def check_scheduled_messages(context: ContextTypes.DEFAULT_TYPE):
    pending = db.get_pending_scheduled()
    for item in pending:
        try:
            await context.bot.send_message(chat_id=item['chat_id'], text=item['text'], parse_mode="HTML")
        except: pass


# ═════════════════════════════════════════════════════════════════
# الدالة الرئيسية - مع إصلاح مشكلة Conflict
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

    # ═══ إصلاح مشكلة Conflict: حذف أي webhook أو getUpdates سابق ═══
    async def post_init(application):
        """يتم تنفيذه بعد بناء التطبيق وقبل بدء polling - يمنع خطأ Conflict"""
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ تم حذف أي webhook سابق")
        except Exception as e:
            logger.warning(f"⚠️ لم يتم حذف webhook: {e}")

    app.post_init = post_init

    # تسجيل معالجات الأوامر
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    # أوامر إضافية من الصورة
    app.add_handler(CommandHandler("ban", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("unban", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("mute", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("unmute", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("kick", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("warn", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("rules", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("info", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("staff", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("me", lambda u, c: start_cmd(u, c)))
    app.add_handler(CommandHandler("pin", lambda u, c: start_cmd(u, c)))

    # تسجيل معالج الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(callback_handler))

    # معالجة الرسائل النصية
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

    # جدولة المهام
    try:
        if app.job_queue:
            app.job_queue.run_repeating(check_temp_mutes, interval=60, first=10)
            app.job_queue.run_repeating(check_scheduled_messages, interval=30, first=15)
            logger.info("✅ تم تسجيل جدولة المهام")
        else:
            logger.warning("⚠️ JobQueue غير متاح - استخدام خيط بديل")
            def background_checker():
                while True:
                    try:
                        loop = asyncio.new_event_loop()
                        loop.run_until_complete(_background_tasks(app))
                        loop.close()
                    except Exception as e:
                        logger.error(f"background_checker error: {e}")
                    time.sleep(30)
            checker_thread = threading.Thread(target=background_checker, daemon=True)
            checker_thread.start()
    except Exception as e:
        logger.warning(f"⚠️ خطأ في الجدولة: {e}")

    logger.info("🛡️ بوت إدارة المجموعات v7.0 يعمل الآن!")
    app.run_polling(drop_pending_updates=True)


async def _background_tasks(app):
    """تنفيذ المهام الخلفية عندما لا يتوفر JobQueue"""
    # فحص الكتم المؤقت
    try:
        expired = db.get_expired_mutes()
        for mute in expired:
            try:
                perms = ChatPermissions(
                    can_send_messages=True, can_send_photos=True, can_send_videos=True,
                    can_send_audios=True, can_send_documents=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                    can_add_web_page_previews=True,
                )
                await app.bot.restrict_chat_member(mute['chat_id'], mute['user_id'], perms)
            except: pass
    except: pass

    # فحص الرسائل المجدولة
    try:
        pending = db.get_pending_scheduled()
        for item in pending:
            try:
                await app.bot.send_message(chat_id=item['chat_id'], text=item['text'], parse_mode="HTML")
            except: pass
    except: pass


if __name__ == "__main__":
    main()
