"""
╔══════════════════════════════════════════════════════════════════╗
║  🛡️ بوت إدارة المجموعات المتكامل v12.0 - الإصدار الخارق 🛡️     ║
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
from html import escape as html_escape
from datetime import datetime, timedelta
from flask import Flask, jsonify
from waitress import serve
from telegram import Update, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from telegram.constants import ChatMemberStatus, ParseMode
from telegram.error import Conflict

import signal as signal_module
import sys
import fcntl
import io
import math

try:
    import qrcode as qrcode_lib
    HAS_QRCODE = True
except ImportError:
    HAS_QRCODE = False

try:
    from PIL import Image as PILImage
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

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
OWNER_ID = int(os.environ.get("OWNER_ID", "8947599931"))
WARN_LIMIT = 3
DEFAULT_WELCOME = "مرحباً بك يا {user} في مجموعتنا! 🎉\nيرجى قراءة القوانين"
DB_PATH = "bot_database.db"

SUDO_USERS = {OWNER_ID}

# ═══ نظام القفل الأحادي لمنع تكرار البوت ═══
LOCK_FILE = "/tmp/bot_singleton.lock"
_lock_file = None

def acquire_singleton_lock():
    """الحصول على قفل ملف لمنع تشغيل عدة مثيلات من البوت"""
    global _lock_file
    try:
        _lock_file = open(LOCK_FILE, 'w')
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file.write(str(os.getpid()))
        _lock_file.flush()
        logger.info(f"✅ Singleton lock acquired (PID: {os.getpid()})")
        return True
    except (IOError, OSError):
        logger.error("❌ مثيل آخر من البوت يعمل! جاري الانتظار...")
        if _lock_file:
            _lock_file.close()
        return False

def release_singleton_lock():
    """تحرير قفل الملف"""
    global _lock_file
    try:
        if _lock_file:
            fcntl.flock(_lock_file, fcntl.LOCK_UN)
            _lock_file.close()
            try:
                os.remove(LOCK_FILE)
            except:
                pass
            logger.info("✅ Singleton lock released")
    except:
        pass

# ═══ فحص المتغيرات الحرجة عند البدء ═══
if not TOKEN:
    logger.critical("❌❌❌ متغير البيئة TOKEN غير موجود! البوت لن يعمل!")
    logger.critical("📌 اذهب إلى Render Dashboard → Environment → أضف TOKEN = توكن_البوت_الخاص_بك")
else:
    logger.info(f"✅ TOKEN موجود (الطول: {len(TOKEN)} حرف)")
    logger.info(f"✅ OWNER_ID: {OWNER_ID}")

# ═════════════════════════════════════════════════════════════════
# خادم Flask للحفاظ على البوت نشطاً
# ═════════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return jsonify({
        "status": "running",
        "bot": "Group Manager v12.0",
        "token_set": bool(TOKEN),
        "uptime": True
    }), 200

@web_app.route('/health')
def health():
    return "OK", 200

@web_app.route('/status')
def status():
    """مسار لفحص حالة البوت - يظهر ما إذا كان TOKEN موجوداً أم لا"""
    if TOKEN:
        return jsonify({
            "status": "healthy",
            "token": "موجود ✅",
            "token_length": len(TOKEN),
            "owner_id": OWNER_ID,
            "message": "البوت يعمل بشكل طبيعي"
        }), 200
    else:
        return jsonify({
            "status": "unhealthy",
            "token": "غير موجود ❌",
            "message": "⚠️ متغير البيئة TOKEN غير محدد! اذهب إلى Render Dashboard → Environment → أضف TOKEN"
        }), 500

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌐 Starting production server on port {port}")
    serve(web_app, host='0.0.0.0', port=port)

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
                welcome_back_msg TEXT DEFAULT 'مرحباً بعودتك يا {user}! 🎊',
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
            # شبكة البوتات - تواصل البوتات مع بعضها
            c.execute('''CREATE TABLE IF NOT EXISTS bot_network (
                chat_id INTEGER, bot_id INTEGER, bot_name TEXT DEFAULT '',
                added_by INTEGER, is_active INTEGER DEFAULT 1,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, bot_id)
            )''')
            # نظام المستويات
            c.execute('''CREATE TABLE IF NOT EXISTS user_levels (
                chat_id INTEGER, user_id INTEGER, xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1, last_xp_time TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id)
            )''')
            # الردود المتعلمة من المشرفين
            c.execute('''CREATE TABLE IF NOT EXISTS learned_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER, trigger_pattern TEXT, response TEXT,
                learned_from INTEGER, times_used INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, trigger_pattern)
            )''')
            # سجل الألعاب
            c.execute('''CREATE TABLE IF NOT EXISTS game_scores (
                chat_id INTEGER, user_id INTEGER, game_type TEXT,
                score INTEGER DEFAULT 0, played_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(chat_id, user_id, game_type)
            )''')
            # تفاعلات الرسائل
            c.execute('''CREATE TABLE IF NOT EXISTS reaction_stats (
                chat_id INTEGER, user_id INTEGER, reactions_received INTEGER DEFAULT 0,
                reactions_given INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id)
            )''')

            # إدارة يوتيوب
            c.execute("CREATE TABLE IF NOT EXISTS youtube_channels (chat_id INTEGER, channel_id TEXT, channel_name TEXT DEFAULT '', api_key TEXT DEFAULT '', subscriber_count INTEGER DEFAULT 0, video_count INTEGER DEFAULT 0, view_count INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1, added_by INTEGER, added_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(chat_id, channel_id))")
            c.execute("CREATE TABLE IF NOT EXISTS youtube_videos (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, channel_id TEXT, video_id TEXT, title TEXT DEFAULT '', views INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, tracked_at TEXT DEFAULT CURRENT_TIMESTAMP)")
            c.execute("CREATE TABLE IF NOT EXISTS youtube_ideas (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, channel_id TEXT, idea_type TEXT DEFAULT 'script', content TEXT, generated_at TEXT DEFAULT CURRENT_TIMESTAMP, used INTEGER DEFAULT 0)")
            c.execute("CREATE TABLE IF NOT EXISTS short_videos (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, channel_id TEXT DEFAULT '', topic TEXT, script TEXT DEFAULT '', image_prompts TEXT DEFAULT '', text_overlays TEXT DEFAULT '', status TEXT DEFAULT 'draft', created_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
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
        # حماية من SQL Injection
        if key not in VALID_SETTING_KEYS:
            logger.error(f"Invalid setting key attempted: {key}")
            return
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
        if stat not in VALID_STAT_KEYS:
            logger.error(f"Invalid stat key attempted: {stat}")
            return
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

    def is_captcha_pending(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT 1 FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row is not None

    def get_captcha_answer(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT correct_answer FROM captcha_pending WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            return row[0] if row else None

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

    # ═══ شبكة البوتات ═══
    def add_bot_network(self, chat_id, bot_id, bot_name, added_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO bot_network (chat_id, bot_id, bot_name, added_by, is_active) VALUES (?, ?, ?, ?, 1)",
                     (chat_id, bot_id, bot_name, added_by))
            conn.commit()
            conn.close()

    def remove_bot_network(self, chat_id, bot_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM bot_network WHERE chat_id = ? AND bot_id = ?", (chat_id, bot_id))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def get_bot_network(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT bot_id, bot_name, is_active FROM bot_network WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def is_bot_allowed(self, chat_id, bot_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT is_active FROM bot_network WHERE chat_id = ? AND bot_id = ?", (chat_id, bot_id))
            row = c.fetchone()
            conn.close()
            return row is not None and row[0] == 1

    # ═══ نظام المستويات ═══
    def add_xp(self, chat_id, user_id, amount=1):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO user_levels (chat_id, user_id, xp, level, last_xp_time) VALUES (?, ?, ?, 1, ?) ON CONFLICT(chat_id, user_id) DO UPDATE SET xp = xp + ?, last_xp_time = ?",
                     (chat_id, user_id, amount, now, amount, now))
            c.execute("SELECT xp, level FROM user_levels WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            xp, level = row[0], row[1]
            new_level = min(50, int((xp / LEVEL_XP_BASE) ** 0.5) + 1)
            if new_level > level:
                c.execute("UPDATE user_levels SET level = ? WHERE chat_id = ? AND user_id = ?", (new_level, chat_id, user_id))
                level = new_level
            conn.commit()
            conn.close()
            return xp, level, new_level > (min(50, int(((xp - amount) / LEVEL_XP_BASE) ** 0.5) + 1))

    def get_user_level(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT xp, level FROM user_levels WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            row = c.fetchone()
            conn.close()
            if row:
                return {"xp": row[0], "level": row[1]}
            return {"xp": 0, "level": 1}

    def get_level_leaderboard(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, xp, level FROM user_levels WHERE chat_id = ? ORDER BY xp DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1], r[2]) for r in rows]

    # ═══ الردود المتعلمة ═══
    def add_learned_response(self, chat_id, trigger, response, learned_from):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO learned_responses (chat_id, trigger_pattern, response, learned_from) VALUES (?, ?, ?, ?)",
                     (chat_id, trigger, response, learned_from))
            conn.commit()
            conn.close()

    def get_learned_responses(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT trigger_pattern, response FROM learned_responses WHERE chat_id = ?", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows]

    def delete_learned_response(self, chat_id, trigger):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM learned_responses WHERE chat_id = ? AND trigger_pattern = ?", (chat_id, trigger))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def increment_learned_usage(self, chat_id, trigger):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("UPDATE learned_responses SET times_used = times_used + 1 WHERE chat_id = ? AND trigger_pattern = ?", (chat_id, trigger))
            conn.commit()
            conn.close()

    # ═══ سجل الألعاب ═══
    def update_game_score(self, chat_id, user_id, game_type, points=1):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO game_scores (chat_id, user_id, game_type, score) VALUES (?, ?, ?, ?) ON CONFLICT(chat_id, user_id, game_type) DO UPDATE SET score = score + ?, played_at = CURRENT_TIMESTAMP",
                     (chat_id, user_id, game_type, points, points))
            conn.commit()
            conn.close()

    def get_game_leaderboard(self, chat_id, game_type=None, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            if game_type:
                c.execute("SELECT user_id, score FROM game_scores WHERE chat_id = ? AND game_type = ? ORDER BY score DESC LIMIT ?", (chat_id, game_type, limit))
            else:
                c.execute("SELECT user_id, SUM(score) as total FROM game_scores WHERE chat_id = ? GROUP BY user_id ORDER BY total DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows]

    # ═══ تفاعلات الرسائل ═══
    def add_reaction_received(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO reaction_stats (chat_id, user_id, reactions_received) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET reactions_received = reactions_received + 1",
                     (chat_id, user_id))
            conn.commit()
            conn.close()

    def add_reaction_given(self, chat_id, user_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO reaction_stats (chat_id, user_id, reactions_given) VALUES (?, ?, 1) ON CONFLICT(chat_id, user_id) DO UPDATE SET reactions_given = reactions_given + 1",
                     (chat_id, user_id))
            conn.commit()
            conn.close()

    def get_reaction_leaderboard(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT user_id, reactions_received FROM reaction_stats WHERE chat_id = ? ORDER BY reactions_received DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [(r[0], r[1]) for r in rows]


    # ═══ إدارة يوتيوب ═══
    def add_youtube_channel(self, chat_id, channel_id, channel_name, api_key, added_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO youtube_channels (chat_id, channel_id, channel_name, api_key, added_by) VALUES (?, ?, ?, ?, ?)",
                     (chat_id, channel_id, channel_name, api_key, added_by))
            conn.commit()
            conn.close()

    def remove_youtube_channel(self, chat_id, channel_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("DELETE FROM youtube_channels WHERE chat_id = ? AND channel_id = ?", (chat_id, channel_id))
            d = c.rowcount > 0
            conn.commit()
            conn.close()
            return d

    def get_youtube_channels(self, chat_id):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM youtube_channels WHERE chat_id = ? AND is_active = 1", (chat_id,))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def add_youtube_idea(self, chat_id, channel_id, idea_type, content):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO youtube_ideas (chat_id, channel_id, idea_type, content) VALUES (?, ?, ?, ?)",
                     (chat_id, channel_id, idea_type, content))
            conn.commit()
            conn.close()

    def get_youtube_ideas(self, chat_id, channel_id='', idea_type='', limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            query = "SELECT * FROM youtube_ideas WHERE chat_id = ?"
            params = [chat_id]
            if channel_id:
                query += " AND channel_id = ?"
                params.append(channel_id)
            if idea_type:
                query += " AND idea_type = ?"
                params.append(idea_type)
            query += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            c.execute(query, params)
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

    def add_short_video(self, chat_id, channel_id, topic, script, image_prompts, text_overlays, created_by):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO short_videos (chat_id, channel_id, topic, script, image_prompts, text_overlays, created_by) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     (chat_id, channel_id, topic, script, image_prompts, text_overlays, created_by))
            conn.commit()
            conn.close()

    def get_short_videos(self, chat_id, limit=10):
        with self.lock:
            conn = self._get_conn()
            c = conn.cursor()
            c.execute("SELECT * FROM short_videos WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))
            rows = c.fetchall()
            conn.close()
            return [dict(r) for r in rows]

db = Database(DB_PATH)

# ═════════════════════════════════════════════════════════════════
# ثوابت الأمان - فلترة مفاتيح الإعدادات والإحصائيات
# ═════════════════════════════════════════════════════════════════
VALID_SETTING_KEYS = {
    "welcome_msg", "rules", "maintenance_mode", "log_channel_id",
    "anti_spam", "anti_flood", "anti_link", "anti_badword", "anti_raid",
    "anti_bot", "anti_channel", "anti_forward", "anti_username",
    "anti_arabic", "anti_emoji", "anti_phone", "anti_longmsg", "anti_edit",
    "report_enabled", "captcha_enabled", "max_flood_msgs", "flood_interval",
    "raid_threshold", "raid_action", "link_action", "warn_action",
    "auto_delete", "slow_mode", "max_msg_length", "ai_reply",
    "absence_mode", "auto_welcome", "welcome_back_msg",
    "bot_communication", "anti_spoof", "auto_translate", "level_system",
    "learn_responses", "group_language",
}

VALID_STAT_KEYS = {
    "total_messages", "total_joins", "total_leaves", "total_bans",
    "total_mutes", "total_warns", "total_deleted", "total_kicks",
    "total_raids_blocked", "total_links_blocked", "total_spam_blocked",
    "total_flood_blocked",
}

# ═════════════════════════════════════════════════════════════════
# ثوابت نظام المستويات
# ═════════════════════════════════════════════════════════════════
LEVEL_NAMES = {
    1: "مبتدئ", 2: "قادم جديد", 3: "نشيط", 4: "متقدم", 5: "محترف",
    6: "خبير", 7: "مبدع", 8: "قائد", 9: "أسطورة", 10: "بطل",
    11: "فارس", 12: "بطل محترف", 13: "صانع السلام", 14: "حكيم",
    15: "مرشد", 16: "خبير متقدم", 17: "بطل المجتمع", 18: "فارس الظلام",
    19: "حارس المجموعة", 20: "ملك الحوار", 21: "إمبراطور", 22: "نجم ساطع",
    23: "عملاق", 24: "صانع التاريخ", 25: "أسطورة حية", 26: "حامي العرش",
    27: "سيد الحكمة", 28: "بطل الأبطال", 29: "فخر المجموعة", 30: "القمة",
    31: "سيد السادة", 32: "حاكم", 33: "ملك متوج", 34: "إمبراطور عظيم",
    35: "أسطورة الخالدين", 36: "صانع المعجزات", 37: "حارس الأبدية",
    38: "سيد الكون", 39: "فوق البشر", 40: "نصف إله",
    41: "الأسطورة المطلقة", 42: "المعلم الأكبر", 43: "حكيم الأبدية",
    44: "سيد كل الأزمنة", 45: "المنتهي", 46: "ما وراء الخيال",
    47: "القوة المطلقة", 48: "الأزلي", 49: "المطلق", 50: "المطور 👑",
}
LEVEL_XP_BASE = 100

TRIVIA_QUESTIONS = [
    {"q": "ما هي عاصمة السعودية؟", "a": "الرياض", "opts": ["الرياض", "جدة", "مكة", "المدينة"]},
    {"q": "كم عدد أحرف اللغة العربية؟", "a": "28", "opts": ["28", "26", "30", "29"]},
    {"q": "ما هو أكبر كوكب في المجموعة الشمسية؟", "a": "المشتري", "opts": ["المشتري", "زحل", "الأرض", "المريخ"]},
    {"q": "من اخترع الهاتف؟", "a": "بل", "opts": ["بل", "إديسون", "تسلا", "نيوتن"]},
    {"q": "ما هي أطول نهر في العالم؟", "a": "النيل", "opts": ["النيل", "الأمازون", "المسيسيبي", "اليانغتسي"]},
    {"q": "كم عدد قارات العالم؟", "a": "7", "opts": ["7", "6", "5", "8"]},
    {"q": "ما هو العنصر الكيميائي الأكثر وفرة في الكون؟", "a": "الهيدروجين", "opts": ["الهيدروجين", "الأكسجين", "الكربون", "الهيليوم"]},
    {"q": "في أي سنة هبط الإنسان على القمر؟", "a": "1969", "opts": ["1969", "1972", "1965", "1970"]},
]

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
    safe_name = html_escape(name) if name else "مستخدم"
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
# وظائف يوتيوب API
# ═════════════════════════════════════════════════════════════════
def fetch_youtube_stats(api_key, channel_id):
    """جلب إحصائيات قناة يوتيوب باستخدام YouTube Data API v3"""
    import requests as req
    try:
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {"part": "statistics,snippet", "id": channel_id, "key": api_key}
        resp = req.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            if items:
                ch = items[0]
                stats = ch.get('statistics', {})
                snippet = ch.get('snippet', {})
                return {
                    "name": snippet.get('title', 'غير معروف'),
                    "subscribers": int(stats.get('subscriberCount', 0)),
                    "views": int(stats.get('viewCount', 0)),
                    "videos": int(stats.get('videoCount', 0)),
                    "thumbnail": snippet.get('thumbnails', {}).get('default', {}).get('url', ''),
                }
    except Exception as e:
        logger.error(f"YouTube stats error: {e}")
    return None

def fetch_youtube_trending(api_key, region_code="SA", max_results=5):
    """جلب الفيديوهات الرائجة"""
    import requests as req
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
            "key": api_key
        }
        resp = req.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get('items', []):
                results.append({
                    "title": item['snippet']['title'],
                    "channel": item['snippet']['channelTitle'],
                    "views": item.get('statistics', {}).get('viewCount', '0'),
                    "likes": item.get('statistics', {}).get('likeCount', '0'),
                    "video_id": item['id'],
                    "thumbnail": item['snippet']['thumbnails'].get('default', {}).get('url', ''),
                })
            return results
    except Exception as e:
        logger.error(f"YouTube trending error: {e}")
    return []

def fetch_youtube_search(api_key, query, max_results=5):
    """البحث في يوتيوب عن موضوع"""
    import requests as req
    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "q": query,
            "maxResults": max_results,
            "type": "video",
            "key": api_key
        }
        resp = req.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            results = []
            for item in data.get('items', []):
                results.append({
                    "title": item['snippet']['title'],
                    "channel": item['snippet']['channelTitle'],
                    "video_id": item.get('id', {}).get('videoId', ''),
                    "thumbnail": item['snippet']['thumbnails'].get('default', {}).get('url', ''),
                })
            return results
    except Exception as e:
        logger.error(f"YouTube search error: {e}")
    return []

# ═════════════════════════════════════════════════════════════════
# توليد محتوى بالذكاء الاصطناعي (نظام مدمج)
# ═════════════════════════════════════════════════════════════════
VIDEO_SCRIPT_TEMPLATES = {
    "تقنية": [
        "🎬 سكربت فيديو تقني - الموضوع: {topic}\n\n📝 المقدمة (5 ثواني):\nهل تساءلت يوماً عن {topic}؟ اليوم سأكشف لك الحقيقة!\n\n💡 المحتوى الرئيسي (20 ثانية):\n{topic} أصبح جزءاً أساسياً من حياتنا اليومية. وفقاً لأحدث الإحصائيات، يتزايد الاهتمام بهذا المجال بشكل كبير. إليك أهم 3 نقاط يجب أن تعرفها:\n1. التطور السريع في هذا المجال غير قواعد اللعبة\n2. التطبيقات العملية أصبحت أقرب مما تتصور\n3. المستقبل يحمل مفاجآت مذهلة\n\n🎯 الخاتمة (5 ثواني):\nإذا أعجبك الفيديو اضغط لايك واشترك في القناة! شاركنا رأيك في التعليقات.",
        "🎬 سكربت فيديو تقني متقدم - الموضوع: {topic}\n\n📢 خطاف الانتباه (3 ثواني):\n{topic} - الكلمة التي يبحث عنها الملايين!\n\n📖 الشرح (22 ثانية):\nدعني أشرح لك ببساطة. {topic} هو أحد أكثر المواضيع إثارة في عالم التقنية اليوم. ما يجعله مميزاً هو قدرته على تغيير طريقة عملنا وعيشنا. العديد من الخبراء يتوقعون أنه سيكون المحرك الرئيسي للابتكار في السنوات القادمة.\n\n✨ الدعوة للتفاعل (5 ثواني):\nما رأيك في {topic}؟ أخبرنا في التعليقات ولاتنسى الاشتراك!",
    ],
    "تعليمي": [
        "📚 سكربت فيديو تعليمي - الموضوع: {topic}\n\n🎯 المقدمة (5 ثواني):\nهل تريد تعلم {topic}؟ في هذا الفيديو القصير سأعطيك أهم المعلومات!\n\n📝 المحتوى (20 ثانية):\n{topic} من المهارات المطلوبة بشكل متزايد. إليك الخطوات الأساسية:\n1. ابدأ بفهم الأساسيات والمفاهيم الرئيسية\n2. طبّق ما تعلمته عملياً من خلال مشاريع صغيرة\n3. انضم لمجتمع المتعلمين وتبادل الخبرات\n\n💡 الخاتمة (5 ثواني):\nإذا استفدت من الفيديو اضغط لايك وشاركه مع أصدقائك!",
    ],
    "ترفيهي": [
        "🎮 سكربت فيديو ترفيهي - الموضوع: {topic}\n\n🔥 خطاف الانتباه (3 ثواني):\nلن تصدق ما سنكشفه عن {topic}!\n\n😄 المحتوى (22 ثانية):\n{topic} من أكثر المواضيع إثارة للجدل والإثارة! هل تعلم أن الكثير من الناس لا يعرفون الحقيقة الكاملة عن هذا الموضوع؟ اليوم سنغوص في التفاصيل ونكشف لك المفاجآت.\n\n📌 الخاتمة (5 ثواني):\nاضغط لايك إذا أردت المزيد واشترك في القناة!",
    ],
    "عام": [
        "🎬 سكربت فيديو - الموضوع: {topic}\n\n📢 المقدمة (5 ثواني):\nاليوم سنتحدث عن {topic} - موضوع يهم الكثيرين!\n\n📋 المحتوى (20 ثانية):\n{topic} هو موضوع يستحق الاهتمام. في هذا الفيديو القصير سنتناول أهم النقاط والمعلومات الأساسية التي يجب أن تعرفها. سنستعرض الحقائق والأرقام ونسلط الضوء على الجوانب الأكثر إثارة.\n\n✅ الخاتمة (5 ثواني):\nشاركنا رأيك في التعليقات ولاتنسى الاشتراك في القناة!",
    ],
}

THUMBNAIL_TEMPLATES = [
    "🎨 فكرة صورة مصغرة: نص كبير وواضح '{title}' مع خلفية متدرجة ألوان زاهية + صورة وجه متفاجئ",
    "🎨 فكرة صورة مصغرة: رموز وأيقونات تعبر عن '{title}' مع ألوان صفراء وحمراء لجذب الانتباه",
    "🎨 فكرة صورة مصغرة: مقارنة بين شيئين related to '{title}' مع أسهم وعلامات استفهام",
    "🎨 فكرة صورة مصغرة: رقم ضخم أو إحصائية مذهلة عن '{title}' مع خلفية داكنة ونص مضيء",
]

CONTENT_IDEAS_TEMPLATES = {
    "تقنية": [
        "مراجعة أحدث هاتف/جهاز في السوق",
        "مقارنة بين تطبيقين منافسين",
        "أسرار وميزات مخفية في برنامج شهير",
        "توقعات مستقبل التقنية لعام 2026",
        "دليل شامل لبدء تعلم البرمجة",
    ],
    "تعليمي": [
        "شرح مبسط لمفهوم معقد",
        "نصائح ذهبية للنجاح في الدراسة",
        "أفضل مصادر التعلم المجانية",
        "كيف تبني عادة التعلم اليومي",
        "أخطاء شائعة يجب تجنبها",
    ],
    "ترفيهي": [
        "تحدي ممتع مع أصدقائي",
        "رد فعلي على شيء مذهل",
        "أفضل 10 أماكن/مطاعم/ألعاب",
        "قصة غريبة حدثت معي",
        "مسابقة مع متابعين",
    ],
    "عام": [
        "حقائق مذهلة لم تكن تعرفها",
        "نصائح عملية للحياة اليومية",
        "أفضل التطبيقات والمواقع المفيدة",
        "تجربتي الشخصية مع...",
        "أسئلة وأجوبة مع المتابعين",
    ],
}

def generate_video_script(topic, category="عام", duration=30):
    """توليد سكربت فيديو بالذكاء الاصطناعي"""
    templates = VIDEO_SCRIPT_TEMPLATES.get(category, VIDEO_SCRIPT_TEMPLATES["عام"])
    template = random.choice(templates)
    script = template.format(topic=topic)
    return script

def generate_thumbnail_ideas(topic):
    """توليد أفكار الصور المصغرة"""
    ideas = []
    for tmpl in THUMBNAIL_TEMPLATES:
        ideas.append(tmpl.format(title=topic[:30]))
    return ideas

def generate_content_ideas(niche="عام", count=5):
    """توليد أفكار محتوى"""
    templates = CONTENT_IDEAS_TEMPLATES.get(niche, CONTENT_IDEAS_TEMPLATES["عام"])
    selected = random.sample(templates, min(count, len(templates)))
    return selected

def generate_short_video_package(topic):
    """توليد حزمة فيديو قصير 30 ثانية"""
    script = f"""🎬 سكربت فيديو قصير 30 ثانية - الموضوع: {topic}

📢 خطاف الانتباه (0-3 ثواني):
هل تعلم ما يخص {topic}؟ استمر بالمشاهدة!

📈 المحتوى الرئيسي (3-25 ثانية):
{topic} هو أحد أكثر المواضيع إثارة اليوم!
• النقطة الأولى: أهمية هذا الموضوع في حياتنا
• النقطة الثانية: إحصائيات مذهلة ستدهشك
• النقطة الثالثة: كيف يمكنك الاستفادة عملياً

🎯 الدعوة للعمل (25-30 ثانية):
اضغط لايك واشترك! شاركنا رأيك في التعليقات 👇"""

    image_prompts = f"""🎨 مطالبات الصور للفيديو القصير:

1. صورة افتتاحية: نص عريض "{topic[:20]}؟" مع خلفية متحركة ملونة
2. صورة النقطة الأولى: أيقونة مع رقم 1 + نص مختصر
3. صورة النقطة الثانية: رسم بياني أو إحصائية بصرية
4. صورة النقطة الثالثة: رمز عملي + سهم
5. صورة الختام: شعار القناة + "اشترك الآن" """

    text_overlays = f"""📝 النصوص على الشاشة:

00:00 - "{topic[:25]}؟ 🤔"
00:03 - "النقطة الأولى ⭐"
00:10 - "هل تعلم؟ 📊"
00:18 - "طبّق الآن! 💡"
00:25 - "لايك + اشتراك ❤️"
00:28 - "شاركنا رأيك 👇" """

    return script, image_prompts, text_overlays

def generate_ai_reply(text, user_name="صديقي"):
    """توليد رد ذكي بالذكاء الاصطناعي المدمج"""
    text_lower = text.lower().strip()

    # تحيات
    greetings = ['مرحبا', 'هلا', 'السلام عليكم', 'سلام', 'اهلا', 'أهلا', 'هاي', 'صباح الخير', 'مساء الخير']
    for g in greetings:
        if g in text_lower:
            return random.choice([
                f"أهلاً وسهلاً {user_name}! كيف حالك اليوم؟ 😊",
                f"مرحباً {user_name}! نورت المجموعة 🌟",
                f"وعليكم السلام {user_name}! أخبارك إيه؟ 💫",
                f"هلا والله {user_name}! حياك الله 🎉",
            ])

    # شكر
    thanks = ['شكرا', 'مشكور', 'يعطيك العافية', 'الله يجزاك']
    for t in thanks:
        if t in text_lower:
            return random.choice([
                f"العفو {user_name}! دائماً في الخدمة 😊",
                f"لا شكر على واجب {user_name}! 💙",
                f"الله يعافيك {user_name}! 🌹",
            ])

    # أسئلة
    if '?' in text or '؟' in text:
        return random.choice([
            f"سؤال ممتاز {user_name}! دعني أفكر... أعتقد أن الأفضل أن نسأل المشرفين عن هذا 🤔",
            f"سؤال مهم! أتمنى أن نجد إجابة شافية 💭",
            f"هذا سؤال يستحق النقاش! من عنده إجابة؟ 🙋",
        ])

    # ردود عامة ذكية
    return random.choice([
        f"كلام جميل {user_name}! 👍",
        f"أوافقك الرأي {user_name}! ✨",
        f"نقطة مهمة {user_name}! 💡",
        f"شكراً للمشاركة {user_name}! 🌟",
        f"ممتاز {user_name}! استمر 🚀",
        f"فكرة رائعة {user_name}! 🎯",
        f"صدقت {user_name}! 👏",
    ])

def get_weather(city):
    """جلب حالة الطقس باستخدام wttr.in API"""
    import requests as req
    try:
        resp = req.get(f"https://wttr.in/{city}?format=j1", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            current = data.get('current_condition', [{}])[0]
            area = data.get('nearest_area', [{}])[0]
            return {
                "city": area.get('areaName', [{}])[0].get('value', city),
                "country": area.get('country', [{}])[0].get('value', ''),
                "temp": current.get('temp_C', 'N/A'),
                "feels_like": current.get('FeelsLikeC', 'N/A'),
                "humidity": current.get('humidity', 'N/A'),
                "description": current.get('weatherDesc', [{}])[0].get('value', 'N/A'),
                "wind": current.get('windspeedKmph', 'N/A'),
            }
    except Exception as e:
        logger.error(f"Weather error: {e}")
    return None

def safe_eval_math(expr):
    """تقييم تعبير رياضي بشكل آمن"""
    # إزالة كل شيء خطير
    allowed = set('0123456789+-*/.()^ ')
    expr = expr.replace('^', '**')
    expr = ''.join(c for c in expr if c in allowed)
    if not expr:
        return None
    try:
        result = eval(expr, {"__builtins__": {}}, {"abs": abs, "round": round, "min": min, "max": max, "pow": pow})
        return result
    except:
        return None

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
        [InlineKeyboardButton("🤖 شبكة البوتات", callback_data="menu_botnet"),
         InlineKeyboardButton("🏅 المستوى", callback_data="menu_levels")],
        [InlineKeyboardButton("🎮 الألعاب", callback_data="menu_games"),
         InlineKeyboardButton("🏆 المتصدرين", callback_data="menu_leaderboard")],
        [InlineKeyboardButton("📺 يوتيوب", callback_data="menu_youtube"),
         InlineKeyboardButton("🛠️ أدوات ذكية", callback_data="menu_smart")],
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
        [InlineKeyboardButton("📦 نسخ احتياطي", callback_data="act_backup"),
         InlineKeyboardButton("🆔 معرفات", callback_data="act_id")],
        [InlineKeyboardButton("🔔 تنبيه المشرفين", callback_data="act_alertadmins"),
         InlineKeyboardButton("📝 استطلاع", callback_data="act_poll")],
        [InlineKeyboardButton("🎫 إنشاء تذكرة", callback_data="act_ticket"),
         InlineKeyboardButton("🎲 لعبة السؤال", callback_data="act_quiz")],
        [InlineKeyboardButton("⏱️ مؤقت", callback_data="act_timer"),
         InlineKeyboardButton("💬 اقتباس عشوائي", callback_data="act_quote")],
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

def kb_botnet(chat_id):
    s = db.get_settings(chat_id)
    bots = db.get_bot_network(chat_id)
    bot_list = "\n".join([f"• @{b['bot_name']} ({'✅' if b['is_active'] else '❌'})" for b in bots]) if bots else "لا توجد بوتات متصلة"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة بوت مساعد", callback_data="bn_add"),
         InlineKeyboardButton("➖ إزالة بوت", callback_data="bn_remove")],
        [InlineKeyboardButton(f"{'✅' if s.get('bot_communication',0) else '❌'} تواصل البوتات", callback_data="tog_botcomm")],
        [InlineKeyboardButton("📋 عرض البوتات المتصلة", callback_data="bn_show")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_levels():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏅 بطاقتي", callback_data="lvl_mycard"),
         InlineKeyboardButton("📊 ترتيب المستويات", callback_data="lvl_rank")],
        [InlineKeyboardButton(f"{'✅' if db.get_settings(0).get('level_system',0) else '❌'} نظام المستويات", callback_data="tog_levelsys")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_games():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 مسابقة ثقافية", callback_data="game_trivia"),
         InlineKeyboardButton("🔢 تخمين الرقم", callback_data="game_guess")],
        [InlineKeyboardButton("🔗 لعبة الكلمات", callback_data="game_wordchain"),
         InlineKeyboardButton("🎲 حظ وسعادة", callback_data="game_luck")],
        [InlineKeyboardButton("🏆 نتائج الألعاب", callback_data="game_scores")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_leaderboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏅 ترتيب المستويات", callback_data="lb_levels"),
         InlineKeyboardButton("💬 ترتيب الرسائل", callback_data="lb_messages")],
        [InlineKeyboardButton("⭐ ترتيب السمعة", callback_data="lb_reputation"),
         InlineKeyboardButton("🎯 ترتيب الألعاب", callback_data="lb_games")],
        [InlineKeyboardButton("❤️ ترتيب التفاعلات", callback_data="lb_reactions")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])





def kb_youtube(chat_id):
    channels = db.get_youtube_channels(chat_id)
    ch_count = len(channels)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f"📺 قنواتي ({ch_count})", callback_data="yt_channels"),
         InlineKeyboardButton("➕ ربط قناة", callback_data="yt_add")],
        [InlineKeyboardButton("➖ فصل قناة", callback_data="yt_remove"),
         InlineKeyboardButton("📊 إحصائيات", callback_data="yt_stats")],
        [InlineKeyboardButton("🔥 المواضيع الرائجة", callback_data="yt_trending"),
         InlineKeyboardButton("📝 توليد سكربت", callback_data="yt_script")],
        [InlineKeyboardButton("🎬 فيديو قصير 30ث", callback_data="yt_short"),
         InlineKeyboardButton("🎨 صور مصغرة", callback_data="yt_thumb")],
        [InlineKeyboardButton("📋 تتبع الفيديوهات", callback_data="yt_track"),
         InlineKeyboardButton("💡 أفكار محتوى", callback_data="yt_ideas")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
    ])

def kb_smart():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 رمز QR", callback_data="act_qrcode"),
         InlineKeyboardButton("🔢 حاسبة", callback_data="act_calc")],
        [InlineKeyboardButton("🌤️ الطقس", callback_data="act_weather"),
         InlineKeyboardButton("⏰ تذكير", callback_data="act_reminder")],
        [InlineKeyboardButton("🔗 معلومات رابط", callback_data="act_urlinfo"),
         InlineKeyboardButton("📊 إحصائيات سريعة", callback_data="act_quickstats")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="back")]
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
        "🛡️ <b>بوت إدارة المجموعات المتكامل v12.0</b>\n\n"
        "🔐 <b>نظام حماية متقدم</b> ضد الغارات والسبام والروابط\n"
        "⚡ <b>إدارة ذكية</b> بواجهة أزرار سهلة وبسيطة\n"
        "🤖 <b>ذكاء اصطناعي</b> ردود ذكية تلقائية في المجموعة\n"
        "📊 <b>إحصائيات شاملة</b> مع رسومات بيانية\n"
        "⭐ <b>نظام سمعة وأدوار</b> لتقييم أعضاء المجموعة\n"
        "⏰ <b>جدولة رسائل</b> إرسال تلقائي في أوقات محددة\n"
        "🖤 <b>قائمة سوداء</b> حظر تلقائي دائم\n"
        "🌙 <b>وضع الغياب</b> إدارة تلقائية عند غياب المشرفين\n"
        "🤖 <b>شبكة البوتات</b> تواصل وتنسيق مع البوتات المساعدة\n"
        "🏅 <b>نظام المستويات</b> تقدم واكسب XP بكل رسالة\n"
        "🎮 <b>ألعاب جماعية</b> مسابقات وتحديات ممتعة\n"
        "🏆 <b>لوحة المتصدرين</b> تنافس على المراكز الأولى\n"
        "📝 <b>استطلاعات</b> تصويت جماعي\n"
        "🎫 <b>نظام تذاكر</b> للبلاغات والدعم الفني\n\n"
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
    data = query.data
    chat = update.effective_chat
    user_id = query.from_user.id
    is_adm = await check_is_admin(chat, user_id) if chat else (user_id == OWNER_ID)
    is_owner = user_id == OWNER_ID
    bot_adm = await check_bot_admin(chat, context.bot.id) if chat else False
    await safe_answer(query)  # إزالة مؤشر التحميل

    try:
        # ═══ القائمة الرئيسية ═══
        if data == "back":
            await safe_edit(query,
                "🛡️ <b>بوت إدارة المجموعات المتكامل v12.0</b>\n\n"
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

        # ═══ شبكة البوتات ═══
        elif data == "menu_botnet":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            bots = db.get_bot_network(chat.id)
            bot_list = "\n".join([f"• {b['bot_name']} - {'✅ نشط' if b['is_active'] else '❌ معطل'}" for b in bots]) if bots else "لا توجد بوتات متصلة"
            s = db.get_settings(chat.id)
            comm_status = "✅ مفعّل" if s.get('bot_communication', 0) else "❌ معطل"
            await safe_edit(query,
                f"🤖 <b>شبكة البوتات</b>\n\n"
                f"📡 حالة التواصل: {comm_status}\n"
                f"🤖 البوتات المتصلة:\n{bot_list}\n\n"
                f"يمكنك ربط البوتات المساعدة للتواصل والتنسيق بينها تلقائياً",
                reply_markup=kb_botnet(chat.id))

        elif data == "bn_add":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "add_bot"
            await safe_edit(query,
                "➕ <b>إضافة بوت مساعد</b>\n\nأرسل معرف البوت (مثال: @MyHelperBot) أو أعد توجيه رسالة من البوت:",
                reply_markup=kb_back_cancel())

        elif data == "bn_remove":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "remove_bot"
            await safe_edit(query,
                "➖ <b>إزالة بوت</b>\n\nأرسل معرف البوت الذي تريد إزالته:",
                reply_markup=kb_back_cancel())

        elif data == "bn_show":
            bots = db.get_bot_network(chat.id)
            if not bots:
                await safe_answer(query, "📋 لا توجد بوتات متصلة", show_alert=True); return
            bot_text = "🤖 <b>البوتات المتصلة:</b>\n\n"
            for i, b in enumerate(bots, 1):
                status = "✅ نشط" if b['is_active'] else "❌ معطل"
                bot_text += f"{i}. {b['bot_name']} - {status}\n"
            await safe_edit(query, bot_text, reply_markup=kb_botnet(chat.id))

        elif data == "tog_botcomm":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            s = db.get_settings(chat.id)
            new_val = 0 if s.get('bot_communication', 0) else 1
            db.update_setting(chat.id, 'bot_communication', new_val)
            status = "✅ مفعّل" if new_val else "❌ معطل"
            await safe_edit(query,
                f"🤖 <b>شبكة البوتات</b>\n\n📡 تواصل البوتات: {status}",
                reply_markup=kb_botnet(chat.id))

        # ═══ نظام المستويات ═══
        elif data == "menu_levels":
            await safe_edit(query,
                "🏅 <b>نظام المستويات</b>\n\nاكسب نقاط خبرة (XP) بكل رسالة ترسلها وتقدم في المستويات!",
                reply_markup=kb_levels())

        elif data == "lvl_mycard":
            lvl_data = db.get_user_level(chat.id, user_id)
            level = lvl_data['level']
            xp = lvl_data['xp']
            next_xp = LEVEL_XP_BASE * (level ** 2)
            level_name = LEVEL_NAMES.get(level, f"مستوى {level}")
            user = query.from_user
            msg_count = db.get_msg_count(chat.id, user_id)
            progress = min(100, int((xp / next_xp) * 100)) if next_xp > 0 else 100
            bar_filled = int(progress / 10)
            bar = "▓" * bar_filled + "░" * (10 - bar_filled)
            card_text = (
                f"🏅 <b>بطاقة المستوى</b>\n\n"
                f"👤 الاسم: {html_escape(user.first_name)}\n"
                f"🏅 المستوى: {level} - {level_name}\n"
                f"⭐ XP: {xp}/{next_xp}\n"
                f"📊 التقدم: [{bar}] {progress}%\n"
                f"💬 الرسائل: {msg_count}\n"
            )
            await safe_edit(query, card_text, reply_markup=kb_levels())

        elif data == "lvl_rank":
            top = db.get_level_leaderboard(chat.id, 10)
            if not top:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            rank_text = "🏅 <b>ترتيب المستويات</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, xp, level) in enumerate(top, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                level_name = LEVEL_NAMES.get(level, f"مستوى {level}")
                rank_text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - Lv.{level} {level_name} ({xp} XP)\n"
            await safe_edit(query, rank_text, reply_markup=kb_levels())

        elif data == "tog_levelsys":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            s = db.get_settings(chat.id)
            new_val = 0 if s.get('level_system', 0) else 1
            db.update_setting(chat.id, 'level_system', new_val)
            status = "✅ مفعّل" if new_val else "❌ معطل"
            await safe_edit(query,
                f"🏅 <b>نظام المستويات: {status}</b>",
                reply_markup=kb_levels())

        # ═══ الألعاب ═══
        elif data == "menu_games":
            await safe_edit(query,
                "🎮 <b>الألعاب الجماعية</b>\n\nالعب مع أعضاء المجموعة واكسب نقاط!",
                reply_markup=kb_games())

        elif data == "game_trivia":
            q = random.choice(TRIVIA_QUESTIONS)
            buttons = []
            row = []
            for opt in q['opts']:
                row.append(InlineKeyboardButton(opt, callback_data=f"trivia_{opt}_{q['a']}"))
                if len(row) == 2:
                    buttons.append(row)
                    row = []
            if row:
                buttons.append(row)
            buttons.append([InlineKeyboardButton("🔙 الألعاب", callback_data="menu_games")])
            await safe_edit(query, f"🧠 <b>مسابقة ثقافية</b>\n\n❓ {q['q']}", reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("trivia_"):
            parts = data[7:].rsplit("_", 1)
            if len(parts) == 2:
                chosen, answer = parts
                if chosen == answer:
                    db.update_game_score(chat.id, user_id, "trivia", 3)
                    await safe_answer(query, "✅ إجابة صحيحة! +3 نقاط", show_alert=True)
                else:
                    await safe_answer(query, f"❌ إجابة خاطئة! الإجابة الصحيحة: {answer}", show_alert=True)

        elif data == "game_guess":
            target = random.randint(1, 100)
            context.chat_data["guess_number"] = target
            context.chat_data["guess_active"] = True
            context.chat_data["guess_attempts"] = {}
            await safe_edit(query,
                "🔢 <b>لعبة تخمين الرقم</b>\n\nخمنت رقم بين 1 و 100\nاكتب رقمك في الشات!",
                reply_markup=kb_games())

        elif data == "game_wordchain":
            context.chat_data["word_chain"] = []
            context.chat_data["chain_active"] = True
            await safe_edit(query,
                "🔗 <b>لعبة سلسلة الكلمات</b>\n\nاكتب كلمة وسيأتي الشخص التالي بكلمة تبدأ بآخر حرف من كلمتك!",
                reply_markup=kb_games())

        elif data == "game_luck":
            luck_score = random.randint(1, 100)
            if luck_score >= 90:
                result = "🌟 حظ استثنائي! أنت محظوظ جداً!"
                points = 5
            elif luck_score >= 70:
                result = "✨ حظ جيد! أنت محظوظ!"
                points = 3
            elif luck_score >= 40:
                result = "😐 حظ عادي... يمكن أفضل المرة القادمة"
                points = 1
            else:
                result = "😢 حظ سيء... حاول مرة أخرى!"
                points = 0
            db.update_game_score(chat.id, user_id, "luck", points)
            await safe_edit(query,
                f"🎲 <b>لعبة الحظ والسعادة</b>\n\n📊 نتيجتك: {luck_score}/100\n{result}\nنقاط: +{points}",
                reply_markup=kb_games())

        elif data == "game_scores":
            scores = db.get_game_leaderboard(chat.id)
            if not scores:
                await safe_answer(query, "📋 لا توجد نتائج بعد", show_alert=True); return
            score_text = "🏆 <b>نتائج الألعاب</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, score) in enumerate(scores, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                score_text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - {score} نقطة\n"
            await safe_edit(query, score_text, reply_markup=kb_games())

        # ═══ المتصدرين ═══
        elif data == "menu_leaderboard":
            await safe_edit(query,
                "🏆 <b>لوحة المتصدرين</b>\n\nاختر التصنيف:",
                reply_markup=kb_leaderboard())

        elif data == "lb_levels":
            top = db.get_level_leaderboard(chat.id, 10)
            if not top:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            text = "🏅 <b>ترتيب المستويات</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, xp, level) in enumerate(top, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - Lv.{level} ({xp} XP)\n"
            await safe_edit(query, text, reply_markup=kb_leaderboard())

        elif data == "lb_messages":
            top = db.get_top_msg(chat.id, 10)
            if not top:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            text = "💬 <b>ترتيب الرسائل</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, count) in enumerate(top, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - {count} رسالة\n"
            await safe_edit(query, text, reply_markup=kb_leaderboard())

        elif data == "lb_reputation":
            top = db.get_top_rep(chat.id, 10)
            if not top:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            text = "⭐ <b>ترتيب السمعة</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, rep) in enumerate(top, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - {rep} نقطة\n"
            await safe_edit(query, text, reply_markup=kb_leaderboard())

        elif data == "lb_games":
            scores = db.get_game_leaderboard(chat.id)
            if not scores:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            text = "🎯 <b>ترتيب الألعاب</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, score) in enumerate(scores, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - {score} نقطة\n"
            await safe_edit(query, text, reply_markup=kb_leaderboard())

        elif data == "lb_reactions":
            top = db.get_reaction_leaderboard(chat.id, 10)
            if not top:
                await safe_answer(query, "📋 لا توجد بيانات بعد", show_alert=True); return
            text = "❤️ <b>ترتيب التفاعلات</b>\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (uid, rxn) in enumerate(top, 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                text += f"{medal} <a href='tg://user?id={uid}'>مستخدم</a> - {rxn} تفاعل\n"
            await safe_edit(query, text, reply_markup=kb_leaderboard())


        # ═══ إدارة يوتيوب ═══
        elif data == "menu_youtube":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            await safe_edit(query, "📺 <b>إدارة قناة اليوتيوب</b>\n\nاربط قناتك وأدر محتواك بالذكاء الاصطناعي!\nيمكنك توليد سكربتات فيديو وأفكار محتوى تلقائياً.", reply_markup=kb_youtube(chat.id))

        elif data == "yt_add":
            if not is_adm: return
            context.user_data["waiting"] = "yt_add"
            await safe_edit(query, "➕ <b>ربط قناة يوتيوب</b>\n\nأرسل البيانات بالصيغة التالية:\n<code>API_KEY | CHANNEL_ID | اسم القناة</code>\n\n💡 للحصول على API Key:\n1. اذهب إلى console.cloud.google.com\n2. أنشئ مشروع جديد\n3. فعّل YouTube Data API v3\n4. أنشئ بيانات اعتماد API Key", reply_markup=kb_back_cancel())

        elif data == "yt_remove":
            if not is_adm: return
            channels = db.get_youtube_channels(chat.id)
            if not channels:
                await safe_answer(query, "📺 لا توجد قنوات مربوطة", show_alert=True); return
            ch_list = "\n".join([f"• {c['channel_name']} (ID: <code>{c['channel_id'][:15]}...</code>)" for c in channels])
            context.user_data["waiting"] = "yt_remove"
            await safe_edit(query, f"➖ <b>فصل قناة</b>\n\n{ch_list}\n\nأرسل معرف القناة (Channel ID) التي تريد فصلها:", reply_markup=kb_back_cancel())

        elif data == "yt_channels":
            channels = db.get_youtube_channels(chat.id)
            if not channels:
                await safe_edit(query, "📺 <b>لا توجد قنوات مربوطة</b>\n\nاضغط ➕ ربط قناة لإضافة قناتك!", reply_markup=kb_youtube(chat.id)); return
            text = "📺 <b>القنوات المربوطة:</b>\n\n"
            for ch in channels:
                text += f"• <b>{ch['channel_name']}</b>\n  المشتركين: {ch.get('subscriber_count', 0)} | الفيديوهات: {ch.get('video_count', 0)}\n\n"
            await safe_edit(query, text, reply_markup=kb_youtube(chat.id))

        elif data == "yt_stats":
            channels = db.get_youtube_channels(chat.id)
            if not channels:
                await safe_answer(query, "📺 اربط قناة أولاً!", show_alert=True); return
            ch = channels[0]
            stats = fetch_youtube_stats(ch.get('api_key', ''), ch['channel_id'])
            if stats:
                text = f"📊 <b>إحصائيات قناة {stats['name']}</b>\n\n👥 المشتركين: {stats['subscribers']:,}\n👁️ المشاهدات: {stats['views']:,}\n🎬 الفيديوهات: {stats['videos']:,}"
                # Update DB
                db.add_youtube_channel(chat.id, ch['channel_id'], stats['name'], ch.get('api_key', ''), user_id)
            else:
                text = "❌ لم يتم جلب الإحصائيات. تأكد من صحة API Key و Channel ID"
            await safe_edit(query, text, reply_markup=kb_youtube(chat.id))

        elif data == "yt_trending":
            channels = db.get_youtube_channels(chat.id)
            if not channels:
                await safe_answer(query, "📺 اربط قناة أولاً!", show_alert=True); return
            ch = channels[0]
            trending = fetch_youtube_trending(ch.get('api_key', ''))
            if trending:
                text = "🔥 <b>الفيديوهات الرائجة:</b>\n\n"
                for i, v in enumerate(trending, 1):
                    text += f"{i}. <b>{v['title'][:40]}</b>\n   👁️ {v['views']} | ❤️ {v['likes']}\n\n"
            else:
                text = "❌ لم يتم جلب الرائج. تحقق من API Key"
            await safe_edit(query, text, reply_markup=kb_youtube(chat.id))

        elif data == "yt_script":
            if not is_adm: return
            context.user_data["waiting"] = "yt_script"
            await safe_edit(query, "📝 <b>توليد سكربت فيديو</b>\n\nأرسل الموضوع ونوع المحتوى:\n<code>الموضوع | النوع</code>\n\nالأنواع: تقنية | تعليمي | ترفيهي | عام\nمثال: الذكاء الاصطناعي | تقنية", reply_markup=kb_back_cancel())

        elif data == "yt_short":
            if not is_adm: return
            context.user_data["waiting"] = "yt_short"
            await safe_edit(query, "🎬 <b>إنشاء فيديو قصير 30 ثانية</b>\n\nأرسل موضوع الفيديو القصير:\nسيتم توليد: سكربت + مطالبات صور + نصوص على الشاشة", reply_markup=kb_back_cancel())

        elif data == "yt_thumb":
            if not is_adm: return
            context.user_data["waiting"] = "yt_thumb"
            await safe_edit(query, "🎨 <b>أفكار الصور المصغرة</b>\n\nأرسل عنوان/موضوع الفيديو:", reply_markup=kb_back_cancel())

        elif data == "yt_track":
            await safe_edit(query, "📋 <b>تتبع الفيديوهات</b>\n\n💡 هذه الميزة تتتبع أداء فيديوهات قناتك تلقائياً\nسيتم إضافة بيانات الفيديوهات عند جلب الإحصائيات", reply_markup=kb_youtube(chat.id))

        elif data == "yt_ideas":
            if not is_adm: return
            context.user_data["waiting"] = "yt_ideas"
            await safe_edit(query, "💡 <b>أفكار محتوى بالذكاء الاصطناعي</b>\n\nأرسل مجال قناتك:\nتقنية | تعليمي | ترفيهي | عام", reply_markup=kb_back_cancel())

        # ═══ الأدوات الذكية ═══
        elif data == "menu_smart":
            await safe_edit(query, "🛠️ <b>الأدوات الذكية</b>\n\nأدوات مفيدة تعتمد على الذكاء الاصطناعي!", reply_markup=kb_smart())

        elif data == "act_qrcode":
            context.user_data["waiting"] = "qrcode"
            await safe_edit(query, "📱 <b>إنشاء رمز QR</b>\n\nأرسل النص أو الرابط الذي تريد تحويله إلى رمز QR:", reply_markup=kb_back_cancel())

        elif data == "act_calc":
            context.user_data["waiting"] = "calc"
            await safe_edit(query, "🔢 <b>الحاسبة الذكية</b>\n\nأرسل العملية الحسابية:\nمثال: 25 * 4 + 100\nيدعم: + - * / ^ ()", reply_markup=kb_back_cancel())

        elif data == "act_weather":
            context.user_data["waiting"] = "weather"
            await safe_edit(query, "🌤️ <b>حالة الطقس</b>\n\nأرسل اسم المدينة:\nمثال: الرياض، جدة، القاهرة، دبي", reply_markup=kb_back_cancel())

        elif data == "act_reminder":
            context.user_data["waiting"] = "reminder"
            await safe_edit(query, "⏰ <b>تعيين تذكير</b>\n\nاكتب: الدقائق | الرسالة\nمثال: 30 | حان وقت الاجتماع", reply_markup=kb_back_cancel())

        elif data == "act_urlinfo":
            context.user_data["waiting"] = "urlinfo"
            await safe_edit(query, "🔗 <b>معلومات الرابط</b>\n\nأرسل الرابط:", reply_markup=kb_back_cancel())

        elif data == "act_quickstats":
            stats = db.get_stats(chat.id) if chat else {}
            text = "📊 <b>إحصائيات سريعة</b>\n\n"
            if stats:
                text += f"💬 الرسائل: {stats.get('total_messages', 0)}\n🚫 الحظر: {stats.get('total_bans', 0)}\n🔇 الكتم: {stats.get('total_mutes', 0)}\n🗑️ المحذوفات: {stats.get('total_deleted', 0)}"
            else:
                text += "لا توجد إحصائيات بعد"
            await safe_edit(query, text, reply_markup=kb_smart())

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
                await chat.unpin_all_messages()
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
                chat_info = await chat.get_chat()
                if chat_info.pinned_message:
                    pinned_msg = chat_info.pinned_message
                    await chat.unpin_message(pinned_msg.message_id)
                    await chat.pin_message(pinned_msg.message_id)
                    await chat.send_message("📌 تم إعادة تثبيت الرسالة ✅")
                else:
                    await chat.send_message("❌ لا توجد رسائل مثبتة")
            except Exception as e:
                await chat.send_message(f"❌ خطأ: {e}")
        elif data == "act_pinned":
            try:
                chat_info = await chat.get_chat()
                if chat_info.pinned_message:
                    preview = chat_info.pinned_message.text[:100] if chat_info.pinned_message.text else "(وسائط)"
                    text = f"📌 <b>الرسالة المثبتة:</b>\n\n{preview}"
                else:
                    text = "📌 لا توجد رسائل مثبتة."
                await safe_edit(query, text, reply_markup=kb_back())
            except Exception as e:
                await safe_edit(query, f"❌ خطأ: {e}", reply_markup=kb_back())
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
        elif data == "act_id":
            text = f"🆔 <b>معلومات المعرفات</b>\n\n"
            text += f"👤 اسمك: {mention(user_id, query.from_user.first_name)}\n"
            text += f"📱 معرفك: <code>{user_id}</code>\n"
            if chat and chat.type != "private":
                text += f"👥 المجموعة: <b>{html_escape(chat.title or 'غير معروف')}</b>\n"
                text += f"🆔 معرف المجموعة: <code>{chat.id}</code>\n"
            await safe_edit(query, text, reply_markup=kb_back())
        elif data == "act_backup":
            if not is_adm: return
            settings = db.get_settings(chat.id)
            locks = db.get_all_locks(chat.id)
            badwords = db.get_badwords(chat.id)
            notes = db.get_all_notes(chat.id)
            filters_list = db.get_all_filters(chat.id)
            backup_data = {
                "chat_id": chat.id, "chat_title": chat.title,
                "backup_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "settings": settings, "locks": locks,
                "badwords": badwords, "notes": notes, "filters": filters_list,
            }
            backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
            await safe_edit(query,
                f"📦 <b>نسخة احتياطية</b>\n\n"
                f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"🔒 الأقفال: {len(locks)}\n📝 الملاحظات: {len(notes)}\n"
                f"🔍 الفلاتر: {len(filters_list)}\n🔤 الكلمات: {len(badwords)}\n\n"
                f"<code>{backup_json[:3500]}</code>",
                reply_markup=kb_back())
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

        # ═══ مميزات جديدة v10.0 ═══
        elif data == "act_alertadmins":
            # تنبيه المشرفين - إرسال mention لكل المشرفين
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            try:
                admins = await chat.get_administrators()
                admin_text = "🔔 <b>تنبيه للمشرفين!</b>\n\n"
                for a in admins:
                    admin_text += f"• {mention(a.user.id, a.user.first_name)}\n"
                admin_text += f"\n📍 تم التنبيه بواسطة: {mention(user_id, query.from_user.first_name)}"
                await chat.send_message(admin_text, parse_mode="HTML")
                await safe_edit(query, "🔔 تم تنبيه المشرفين ✅", reply_markup=kb_back())
            except Exception as e:
                await safe_edit(query, f"❌ خطأ: {e}", reply_markup=kb_back())

        elif data == "act_poll":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "poll_question"
            await safe_edit(query, "📝 <b>إنشاء استطلاع</b>\n\nاكتب السؤال ثم الخيارات مفصولة بـ |:\nمثال: ما رأيك؟ | ممتاز | جيد | سيء", reply_markup=kb_back_cancel())

        elif data == "act_ticket":
            context.user_data["waiting"] = "ticket"
            await safe_edit(query, "🎫 <b>إنشاء تذكرة دعم</b>\n\nاكتب مشكلتك أو اقتراحك:", reply_markup=kb_back_cancel())

        elif data == "act_quiz":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "quiz_question"
            await safe_edit(query, "🎲 <b>لعبة السؤال</b>\n\nاكتب السؤال ثم الخيارات مفصولة بـ | (الإجابة الصحيحة أولاً):\nمثال: عاصمة السعودية؟ | الرياض | جدة | مكة", reply_markup=kb_back_cancel())

        elif data == "act_timer":
            if not is_adm:
                await safe_answer(query, "⛔ للمشرفين فقط!", show_alert=True); return
            context.user_data["waiting"] = "timer"
            await safe_edit(query, "⏱️ <b>مؤقت</b>\n\nاكتب عدد الدقائق ثم الرسالة:\nمثال: 5 | انتهى الاجتماع!", reply_markup=kb_back_cancel())

        elif data == "act_quote":
            # اقتباس عشوائي محفوظ
            quotes = [
                "🌟 النجاح ليس نهائياً، والفشل ليس قاتلاً: إنما الشجاعة للاستمرار هي ما يهم. - ونستون تشرشل",
                "💡 الطريقة الوحيدة للقيام بعمل عظيم هي أن تحب ما تفعله. - ستيف جوبز",
                "🚀 لا تنتظر الفرصة، بل اصنعها. - جورج برنارد شو",
                "💪 الصعوبات هي التي تُظهر الرجال. - أبيقور",
                "🎯 إن لم تكن تسير نحو شيء، فأنت تسير نحو لا شيء. - هالي بيري",
                "📚 العلم نور، والجهل ظلام. - مثل عربي",
                "🤝 اليد الواحدة لا تصفق. - مثل عربي",
                "⭐ من جدّ وجد، ومن زرع حصد. - مثل عربي",
                "🌈 بعد كل عسر يسر. - القرآن الكريم",
                "🔥 النار تصقل الحديد، والتجارب تصقل الرجال. - حكمة",
            ]
            quote = random.choice(quotes)
            await safe_edit(query, f"💬 <b>اقتباس عشوائي</b>\n\n{quote}", reply_markup=kb_back())

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

    # ═══ تحقق الكابتشا ═══
    if text and db.is_captcha_pending(chat.id, user_id):
        correct = db.get_captcha_answer(chat.id, user_id)
        if text.strip() == correct:
            db.remove_captcha(chat.id, user_id)
            try:
                await chat.restrict_member(user_id, ChatPermissions(
                    can_send_messages=True, can_send_photos=True, can_send_videos=True,
                    can_send_audios=True, can_send_documents=True, can_send_video_notes=True,
                    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                    can_add_web_page_previews=True,
                ))
                await msg.reply_text("✅ تم التحقق بنجاح! أهلاً بك في المجموعة 🎉")
            except: pass
        else:
            try:
                await msg.delete()
            except: pass
        return

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

        # إضافة بوت للشبكة
        elif waiting == "add_bot":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            bot_username = text.strip().lstrip('@')
            if target and target.from_user and target.from_user.is_bot:
                bot_id = target.from_user.id
                bot_name = target.from_user.username or target.from_user.first_name
                db.add_bot_network(chat.id, bot_id, bot_name, user_id)
                await msg.reply_text(f"🤖 تم إضافة البوت @{bot_name} لشبكة البوتات ✅")
            else:
                await msg.reply_text("❌ أعد توجيه رسالة من البوت الذي تريد إضافته")
            context.user_data.pop("waiting", None); return

        # إزالة بوت من الشبكة
        elif waiting == "remove_bot":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            bots = db.get_bot_network(chat.id)
            removed = False
            for b in bots:
                if b['bot_name'].lower() == text.strip().lstrip('@').lower():
                    db.remove_bot_network(chat.id, b['bot_id'])
                    await msg.reply_text(f"➖ تم إزالة البوت @{b['bot_name']} ✅")
                    removed = True
                    break
            if not removed:
                await msg.reply_text("❌ البوت غير موجود في الشبكة")
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

        # ═══ مميزات جديدة v10.0 ═══

        # استطلاع - السؤال
        elif waiting == "poll_question":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|")
                if len(parts) >= 3:
                    question = parts[0].strip()
                    options = [p.strip() for p in parts[1:] if p.strip()]
                    if 2 <= len(options) <= 10:
                        try:
                            from telegram import Poll
                            await context.bot.send_poll(
                                chat_id=chat.id,
                                question=question,
                                options=options,
                                is_anonymous=False,
                                allows_multiple_answers=False
                            )
                            await msg.reply_text("📝 تم إنشاء الاستطلاع ✅")
                        except Exception as e:
                            await msg.reply_text(f"❌ خطأ: {e}")
                    else:
                        await msg.reply_text("❌ يجب أن يكون بين 2 و 10 خيارات")
                else:
                    await msg.reply_text("❌ الصيغة: السؤال | خيار1 | خيار2 | خيار3")
            else:
                await msg.reply_text("❌ استخدم: السؤال | خيار1 | خيار2 | خيار3")
            context.user_data.pop("waiting", None); return

        # تذكرة دعم
        elif waiting == "ticket":
            ticket_id = random.randint(10000, 99999)
            ticket_text = (
                f"🎫 <b>تذكرة دعم جديدة #{ticket_id}</b>\n\n"
                f"👤 من: {mention(user_id, user.first_name)}\n"
                f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"💬 المشكلة/الاقتراح:\n{text}\n\n"
                f"⏳ الحالة: قيد المراجعة"
            )
            await msg.reply_text(ticket_text, parse_mode="HTML")
            # إرسال للمشرفين
            try:
                admins = await chat.get_administrators()
                admin_mentions = " ".join([f"<a href=\"tg://user?id={a.user.id}\">‌</a>" for a in admins[:5]])
                await chat.send_message(f"🎫 تذكرة جديدة #{ticket_id} {admin_mentions}", parse_mode="HTML")
            except: pass
            context.user_data.pop("waiting", None); return

        # لعبة السؤال
        elif waiting == "quiz_question":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|")
                if len(parts) >= 3:
                    question = parts[0].strip()
                    options = [p.strip() for p in parts[1:] if p.strip()]
                    if 2 <= len(options) <= 10:
                        try:
                            await context.bot.send_poll(
                                chat_id=chat.id,
                                question=f"🎲 {question}",
                                options=options,
                                type="quiz",
                                correct_option_id=0,  # الإجابة الأولى هي الصحيحة
                                is_anonymous=False
                            )
                            await msg.reply_text("🎲 تم إنشاء لعبة السؤال ✅")
                        except Exception as e:
                            await msg.reply_text(f"❌ خطأ: {e}")
                    else:
                        await msg.reply_text("❌ يجب أن يكون بين 2 و 10 خيارات")
                else:
                    await msg.reply_text("❌ الصيغة: السؤال | الإجابة الصحيحة | خيار خاطئ | خيار خاطئ")
            else:
                await msg.reply_text("❌ استخدم: السؤال | إجابة صحيحة | خيارات أخرى")
            context.user_data.pop("waiting", None); return

        # مؤقت
        elif waiting == "timer":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|", 1)
                try:
                    minutes = int(parts[0].strip())
                    timer_msg = parts[1].strip() if len(parts) > 1 else "انتهى المؤقت!"
                    await msg.reply_text(f"⏱️ تم تعيين مؤقت لمدة {minutes} دقيقة ✅")
                    # جدولة الرسالة
                    send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                    db.add_scheduled(chat.id, f"⏱️ {timer_msg}", send_at, user_id)
                except:
                    await msg.reply_text("❌ الصيغة: الدقائق | الرسالة")
            else:
                try:
                    minutes = int(text.strip())
                    await msg.reply_text(f"⏱️ تم تعيين مؤقت لمدة {minutes} دقيقة ✅")
                    send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                    db.add_scheduled(chat.id, "⏱️ انتهى المؤقت!", send_at, user_id)
                except:
                    await msg.reply_text("❌ اكتب عدد الدقائق أو: الدقائق | الرسالة")
            context.user_data.pop("waiting", None); return

        # ═══ معالجات يوتيوب ═══
        elif waiting == "yt_add":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|")
                if len(parts) >= 3:
                    api_key = parts[0].strip()
                    channel_id = parts[1].strip()
                    ch_name = parts[2].strip()
                    # Verify API key by fetching stats
                    stats = fetch_youtube_stats(api_key, channel_id)
                    if stats:
                        db.add_youtube_channel(chat.id, channel_id, stats['name'], api_key, user_id)
                        await msg.reply_text(f"📺 تم ربط القناة: <b>{stats['name']}</b> ✅\n👥 المشتركين: {stats['subscribers']:,} | 🎬 الفيديوهات: {stats['videos']:,}", parse_mode="HTML")
                    else:
                        db.add_youtube_channel(chat.id, channel_id, ch_name, api_key, user_id)
                        await msg.reply_text(f"📺 تم حفظ القناة: {ch_name} ✅\n⚠️ لم يتم التحقق من البيانات - تأكد من صحة API Key")
                else:
                    await msg.reply_text("❌ الصيغة: API_KEY | CHANNEL_ID | اسم القناة")
            else:
                await msg.reply_text("❌ استخدم: API_KEY | CHANNEL_ID | اسم القناة")
            context.user_data.pop("waiting", None); return

        elif waiting == "yt_remove":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            ch_id = text.strip()
            if db.remove_youtube_channel(chat.id, ch_id):
                await msg.reply_text("➖ تم فصل القناة بنجاح ✅")
            else:
                await msg.reply_text("❌ القناة غير موجودة")
            context.user_data.pop("waiting", None); return

        elif waiting == "yt_script":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            if "|" in text:
                parts = text.split("|", 1)
                topic = parts[0].strip()
                category = parts[1].strip() if len(parts) > 1 else "عام"
            else:
                topic = text.strip()
                category = "عام"
            script = generate_video_script(topic, category)
            # Save to ideas
            channels = db.get_youtube_channels(chat.id)
            ch_id = channels[0]['channel_id'] if channels else ''
            db.add_youtube_idea(chat.id, ch_id, 'script', script)
            await msg.reply_text(script, parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "yt_short":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            topic = text.strip()
            script, img_prompts, overlays = generate_short_video_package(topic)
            # Save to DB
            channels = db.get_youtube_channels(chat.id)
            ch_id = channels[0]['channel_id'] if channels else ''
            db.add_short_video(chat.id, ch_id, topic, script, img_prompts, overlays, user_id)
            full_text = f"{script}\n\n{img_prompts}\n\n{overlays}"
            # Split if too long
            if len(full_text) > 4000:
                await msg.reply_text(script, parse_mode="HTML")
                await msg.reply_text(img_prompts, parse_mode="HTML")
                await msg.reply_text(overlays, parse_mode="HTML")
            else:
                await msg.reply_text(full_text, parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "yt_thumb":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            ideas = generate_thumbnail_ideas(text.strip())
            ideas_text = "🎨 <b>أفكار الصور المصغرة:</b>\n\n" + "\n\n".join(ideas)
            await msg.reply_text(ideas_text, parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        elif waiting == "yt_ideas":
            if not is_adm:
                context.user_data.pop("waiting", None); return
            niche = text.strip()
            ideas = generate_content_ideas(niche, 5)
            ideas_text = f"💡 <b>أفكار محتوى - مجال: {niche}</b>\n\n"
            for i, idea in enumerate(ideas, 1):
                ideas_text += f"{i}. {idea}\n"
            await msg.reply_text(ideas_text, parse_mode="HTML")
            context.user_data.pop("waiting", None); return

        # ═══ الأدوات الذكية ═══
        elif waiting == "qrcode":
            if HAS_QRCODE:
                try:
                    qr = qrcode_lib.QRCode(version=1, box_size=10, border=5)
                    qr.add_data(text)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    buf.seek(0)
                    await msg.reply_photo(photo=buf, caption=f"📱 رمز QR لـ: {text[:50]}")
                except Exception as e:
                    await msg.reply_text(f"❌ خطأ في إنشاء QR: {e}")
            else:
                await msg.reply_text("❌ مكتبة QR غير متاحة")
            context.user_data.pop("waiting", None); return

        elif waiting == "calc":
            result = safe_eval_math(text)
            if result is not None:
                await msg.reply_text(f"🔢 <b>النتيجة:</b>\n\n{text} = <b>{result}</b>", parse_mode="HTML")
            else:
                await msg.reply_text("❌ تعبير رياضي غير صالح\nاستخدم: أرقام وعمليات + - * / ^ ()")
            context.user_data.pop("waiting", None); return

        elif waiting == "weather":
            city = text.strip()
            weather = get_weather(city)
            if weather:
                text_out = (
                    f"🌤️ <b>حالة الطقس - {weather['city']}, {weather['country']}</b>\n\n"
                    f"🌡️ الحرارة: {weather['temp']}°C\n"
                    f"🤔 يشبه: {weather['feels_like']}°C\n"
                    f"💧 الرطوبة: {weather['humidity']}%\n"
                    f"🌬️ الرياح: {weather['wind']} كم/س\n"
                    f"☁️ الحالة: {weather['description']}"
                )
                await msg.reply_text(text_out, parse_mode="HTML")
            else:
                await msg.reply_text("❌ لم يتم العثور على المدينة. جرب اسم المدينة بالإنجليزية")
            context.user_data.pop("waiting", None); return

        elif waiting == "reminder":
            if "|" in text:
                parts = text.split("|", 1)
                try:
                    minutes = int(parts[0].strip())
                    reminder_msg = parts[1].strip() if len(parts) > 1 else "تذكير!"
                    send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                    db.add_scheduled(chat.id, f"⏰ تذكير: {reminder_msg}", send_at, user_id)
                    await msg.reply_text(f"⏰ تم تعيين تذكير بعد {minutes} دقيقة ✅")
                except:
                    await msg.reply_text("❌ الصيغة: الدقائق | الرسالة")
            else:
                try:
                    minutes = int(text.strip())
                    send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                    db.add_scheduled(chat.id, "⏰ تذكير!", send_at, user_id)
                    await msg.reply_text(f"⏰ تم تعيين تذكير بعد {minutes} دقيقة ✅")
                except:
                    await msg.reply_text("❌ اكتب عدد الدقائق أو: الدقائق | الرسالة")
            context.user_data.pop("waiting", None); return

        elif waiting == "urlinfo":
            url = text.strip()
            info_text = f"🔗 <b>معلومات الرابط</b>\n\n🌐 الرابط: {url}\n📏 الطول: {len(url)} حرف"
            if 'youtube.com' in url or 'youtu.be' in url:
                info_text += "\n📺 نوع: رابط يوتيوب"
            elif 't.me' in url:
                info_text += "\n📱 نوع: رابط تيليجرام"
            elif 'github.com' in url:
                info_text += "\n💻 نوع: رابط GitHub"
            elif 'twitter.com' in url or 'x.com' in url:
                info_text += "\n🐦 نوع: رابط تويتر"
            else:
                info_text += "\n🌐 نوع: رابط عام"
            await msg.reply_text(info_text, parse_mode="HTML")
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
    replied = False
    for trigger, reply_t in auto_replies:
        if trigger.lower() in text.lower():
            await msg.reply_text(reply_t)
            replied = True
            break

    # رد الذكاء الاصطناعي المدمج
    if not replied and settings.get('ai_reply', 0) and not user.is_bot:
        ai_response = generate_ai_reply(text, user.first_name)
        if ai_response:
            await msg.reply_text(ai_response)

    # عداد الرسائل
    db.increment_msg_count(chat.id, user_id)
    db.increment_stat(chat.id, "total_messages")

    # ═══ نظام المستويات - إضافة XP ═══
    settings = db.get_settings(chat.id)
    if settings.get('level_system', 0) and not user.is_bot:
        xp, level, leveled_up = db.add_xp(chat.id, user_id, random.randint(1, 3))
        if leveled_up:
            level_name = LEVEL_NAMES.get(level, f"مستوى {level}")
            try:
                await chat.send_message(
                    f"🎉 مبروك! {mention(user_id, user.first_name)} وصل المستوى {level} - {level_name}!",
                    parse_mode="HTML"
                )
            except: pass

    # ═══ تواصل البوتات ═══
    if user.is_bot and user.id != context.bot.id:
        if settings.get('bot_communication', 0) and db.is_bot_allowed(chat.id, user.id):
            # البوت مسجل في الشبكة - يمكنه التواصل
            try:
                admins = await chat.get_administrators()
                for admin in admins:
                    if not admin.user.is_bot:
                        try:
                            await context.bot.send_message(
                                chat_id=admin.user.id,
                                text=f"🤖 رسالة من البوت @{user.username or user.first_name} في مجموعة {chat.title}:\n{text[:200]}",
                            )
                        except: pass
            except: pass

    # ═══ تعلّم الردود من المشرفين ═══
    if settings.get('learn_responses', 0) and is_adm and target and target.from_user and not target.from_user.is_bot and text:
        trigger = (target.text or "")[:100]
        if trigger:
            db.add_learned_response(chat.id, trigger, text, user_id)

    # ═══ لعبة تخمين الرقم ═══
    if context.chat_data.get("guess_active") and text:
        try:
            guess = int(text.strip())
            target_num = context.chat_data.get("guess_number", 0)
            if guess == target_num:
                db.update_game_score(chat.id, user_id, "guess", 5)
                await msg.reply_text(f"🎉 أحسنت! الرقم هو {target_num}! +5 نقاط")
                context.chat_data["guess_active"] = False
            elif guess < target_num:
                await msg.reply_text("⬆️ الرقم أكبر!")
            else:
                await msg.reply_text("⬇️ الرقم أصغر!")
        except ValueError:
            pass

    # ═══ لعبة سلسلة الكلمات ═══
    if context.chat_data.get("chain_active") and text and not user.is_bot:
        chain = context.chat_data.get("word_chain", [])
        word = text.strip()
        if len(word) >= 2:
            if chain:
                last_word = chain[-1]
                if word[0] == last_word[-1]:
                    chain.append(word)
                    context.chat_data["word_chain"] = chain[-20:]
                    db.update_game_score(chat.id, user_id, "wordchain", 1)
                else:
                    await msg.reply_text(f"❌ الكلمة يجب أن تبدأ بحرف '{last_word[-1]}'")
            else:
                chain.append(word)
                context.chat_data["word_chain"] = chain

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

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل غير النصية (صور، فيديو، الخ) - لدعم أقفال الوسائط"""
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    user = update.effective_user
    msg = update.message
    if not user:
        return
    if user.id == OWNER_ID or user.id in SUDO_USERS:
        return
    is_adm = await check_is_admin(chat, user.id)
    if is_adm:
        return
    if db.is_whitelisted(chat.id, user.id):
        return
    
    settings = db.get_settings(chat.id)
    locks = db.get_all_locks(chat.id)
    deleted = False
    
    # فحص الأقفال حسب نوع الرسالة
    lock_media_map = {
        "photos": msg.photo, "videos": msg.video, "stickers": msg.sticker,
        "animations": msg.animation, "voice": msg.voice, "audio": msg.audio,
        "documents": msg.document, "polls": msg.poll, "contacts": msg.contact,
        "location": msg.location or msg.venue, "venue": msg.venue,
    }
    for lock_type, has_media in lock_media_map.items():
        if lock_type in locks and has_media:
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
                deleted = True
            except: pass
            break
    
    # فحص الروابط في الـ caption
    if not deleted and msg.caption:
        if "links" in locks and has_link(msg.caption):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
                db.increment_stat(chat.id, "total_links_blocked")
                deleted = True
            except: pass
        elif settings.get('anti_link', 1) and has_link(msg.caption):
            try:
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
                db.increment_stat(chat.id, "total_links_blocked")
            except: pass


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

        # ترحيب - مع تمييز العائدين
        if settings.get('auto_welcome', 1):
            # فحص هل المستخدم كان في المجموعة من قبل (له رسائل مسجلة)
            is_returning = db.get_msg_count(chat.id, member.id) > 0
            if is_returning:
                welcome_back_msg = settings.get('welcome_back_msg', 'مرحباً بعودتك يا {user}! 🎊')
                formatted = welcome_back_msg.replace('{user}', mention(member.id, member.first_name))
            else:
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


async def cleanup_memory(context: ContextTypes.DEFAULT_TYPE):
    """تنظيف ذاكرة الفلود والغارات - يمنع تسرب الذاكرة"""
    global flood_data, raid_data, slow_mode_data
    now = time.time()
    
    # تنظيف بيانات الفلود القديمة
    for chat_id in list(flood_data.keys()):
        for user_id in list(flood_data[chat_id].keys()):
            flood_data[chat_id][user_id] = [t for t in flood_data[chat_id][user_id] if now - t <= 60]
            if not flood_data[chat_id][user_id]:
                del flood_data[chat_id][user_id]
        if not flood_data[chat_id]:
            del flood_data[chat_id]
    
    # تنظيف بيانات الغارات القديمة
    for chat_id in list(raid_data.keys()):
        raid_data[chat_id] = [t for t in raid_data[chat_id] if now - t <= 60]
        if not raid_data[chat_id]:
            del raid_data[chat_id]
    
    # تنظيف بيانات الوضع البطيء القديمة
    for key in list(slow_mode_data.keys()):
        if now - slow_mode_data[key] > 300:  # أكثر من 5 دقائق
            del slow_mode_data[key]
    
    logger.info("🧹 تم تنظيف الذاكرة المؤقتة")


async def check_expired_captchas(context: ContextTypes.DEFAULT_TYPE):
    """فحص الكابتشا المنتهية وطرد المستخدمين الذين لم يحلوها"""
    with db.lock:
        conn = db._get_conn()
        c = conn.cursor()
        # البحث عن كابتشا أقدم من 120 ثانية
        cutoff = (datetime.now() - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT * FROM captcha_pending WHERE created_at <= ?", (cutoff,))
        expired = c.fetchall()
        for cap in expired:
            try:
                # حظر المستخدم مؤقتاً (طرد وإلغاء حظر)
                await context.bot.ban_chat_member(cap['chat_id'], cap['user_id'])
                await context.bot.unban_chat_member(cap['chat_id'], cap['user_id'])
            except: pass
            c.execute("DELETE FROM captcha_pending WHERE chat_id = ? AND user_id = ?",
                     (cap['chat_id'], cap['user_id']))
        conn.commit()
        conn.close()
    if expired:
        logger.info(f"🧹 تم طرد {len(expired)} مستخدم لم يحلوا الكابتشا")


# ═════════════════════════════════════════════════════════════════
# الدالة الرئيسية - مع إصلاح مشكلة Conflict
# ═════════════════════════════════════════════════════════════════

async def kill_existing_instances():
    """قتل أي مثيل سابق من البوت عن طريق حذف الـ webhook وتفريغ التحديثات المعلقة"""
    import requests as req_lib
    if not TOKEN:
        return
    api_url = f"https://api.telegram.org/bot{TOKEN}"
    try:
        # الخطوة 1: حذف أي webhook موجود
        req_lib.post(f"{api_url}/deleteWebhook", json={"drop_pending_updates": True}, timeout=10)
        logger.info("✅ الخطوة 1: تم حذف الـ webhook")
        await asyncio.sleep(2)
        # الخطوة 2: تفريغ أي تحديثات معلقة
        try:
            req_lib.get(f"{api_url}/getUpdates?offset=-1", timeout=10)
            logger.info("✅ الخطوة 2: تم تفريغ التحديثات المعلقة")
        except Exception:
            pass
        # الخطوة 3: حذف الـ webhook مرة أخرى للتأكد
        req_lib.post(f"{api_url}/deleteWebhook", json={"drop_pending_updates": True}, timeout=10)
        logger.info("✅ الخطوة 3: تم حذف الـ webhook مرة أخرى")
        await asyncio.sleep(3)
        logger.info("✅ تم تنظيف المثيلات السابقة بنجاح")
    except Exception as e:
        logger.warning(f"⚠️ خطأ أثناء تنظيف المثيلات السابقة: {e}")


def build_application():
    """بناء التطبيق فقط (بدون تشغيل) - يسمح بالتحكم بشكل أفضل"""

    # ═══ تعريف post_init قبل بناء التطبيق ═══
    async def post_init(application):
        """يتم تنفيذه بعد بناء التطبيق وقبل بدء polling - يمنع خطأ Conflict"""
        # تنظيف أي مثيل سابق أولاً
        await kill_existing_instances()
        try:
            await application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("✅ تم حذف أي webhook سابق (post_init)")
            await asyncio.sleep(3)  # انتظار إضافي لضمان توقف المثيل القديم
        except Exception as e:
            logger.warning(f"⚠️ لم يتم حذف webhook: {e}")
        try:
            await application.bot.set_my_commands([
                BotCommand("start", "🛡️ لوحة التحكم الرئيسية"),
                BotCommand("panel", "📋 فتح لوحة التحكم"),
                BotCommand("help", "❓ المساعدة"),
                BotCommand("id", "🆔 معرف المستخدم والمجموعة"),
                BotCommand("ban", "🚫 حظر مستخدم (رد على رسالته)"),
                BotCommand("unban", "✅ إلغاء حظر (رد على رسالته)"),
                BotCommand("mute", "🔇 كتم مستخدم (رد على رسالته)"),
                BotCommand("unmute", "🔊 إلغاء كتم (رد على رسالته)"),
                BotCommand("kick", "👢 طرد مستخدم (رد على رسالته)"),
                BotCommand("warn", "⚠️ تحذير مستخدم (رد + السبب)"),
                BotCommand("unwarn", "✅ إزالة تحذيرات (رد على رسالته)"),
                BotCommand("warns", "📋 عرض التحذيرات (رد على رسالته)"),
                BotCommand("delwarn", "🗑️ حذف التحذيرات (رد على رسالته)"),
                BotCommand("del", "🗑️ حذف رسالة (رد عليها)"),
                BotCommand("pin", "📌 تثبيت رسالة (رد عليها)"),
                BotCommand("rules", "📋 عرض قوانين المجموعة"),
                BotCommand("me", "👤 معلوماتي الشخصية"),
                BotCommand("info", "📊 معلومات المجموعة"),
                BotCommand("staff", "👥 عرض المشرفين"),
                BotCommand("badd", "🖤 إضافة للقائمة السوداء"),
                BotCommand("bdel", "💚 إزالة من القائمة السوداء"),
                BotCommand("geturl", "🔗 رابط المجموعة"),
                BotCommand("inactives", "👻 الأعضاء غير النشطين"),
                BotCommand("listroles", "🎖️ عرض الأدوار"),
                BotCommand("graphic", "📊 رسم بياني للمجموعة"),
                BotCommand("send", "📨 إرسال رسالة لعضو"),
                BotCommand("poll", "📝 إنشاء استطلاع"),
                BotCommand("quiz", "🎲 لعبة سؤال"),
                BotCommand("timer", "⏱️ تعيين مؤقت"),
                BotCommand("quote", "💬 اقتباس عشوائي"),
                BotCommand("ticket", "🎫 إنشاء تذكرة دعم"),
            ])
            logger.info("✅ تم تعيين قائمة الأوامر في تلييجرام")
        except Exception as e:
            logger.warning(f"⚠️ لم يتم تعيين قائمة الأوامر: {e}")

    # ═══ بناء التطبيق مع تمرير post_init للـ builder (إصلاح C1) ═══
    app = Application.builder().token(TOKEN).post_init(post_init).read_timeout(30).write_timeout(30).connect_timeout(30).pool_timeout(30).build()

    # ═══ تسجيل معالجات الأوامر الرئيسية ═══
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    # ═══ أوامر الإشراف المباشرة (رد على رسالة المستخدم) ═══
    async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حظر مستخدم - رد على رسالته"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private":
            return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!")
            return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم الذي تريد حظره + اكتب السبب")
            return
        target_id = target.from_user.id
        target_name = target.from_user.first_name
        reason = " ".join(context.args) if context.args else "بدون سبب"
        if target_id == user.id:
            await msg.reply_text("❌ لا يمكنك حظر نفسك!"); return
        if target_id == context.bot.id:
            await msg.reply_text("❌ لا يمكنني حظر نفسي!"); return
        try:
            await chat.ban_member(target_id)
            await msg.reply_text(f"🚫 تم حظر {mention(target_id, target_name)}\n📋 السبب: {reason}", parse_mode="HTML")
            db.log_action(chat.id, user.id, "ban", target_id, reason)
            db.increment_stat(chat.id, "total_bans")
            await send_log(chat.id, f"🚫 حظر: {mention(target_id, target_name)} بواسطة {mention(user.id, user.first_name)}\nالسبب: {reason}", context)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء حظر - رد على رسالته"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        try:
            await chat.unban_member(target.from_user.id)
            await msg.reply_text(f"✅ تم إلغاء حظر {mention(target.from_user.id, target.from_user.first_name)}", parse_mode="HTML")
            db.log_action(chat.id, user.id, "unban", target.from_user.id)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """كتم مستخدم"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        try:
            await chat.restrict_member(target.from_user.id, ChatPermissions(can_send_messages=False))
            await msg.reply_text(f"🔇 تم كتم {mention(target.from_user.id, target.from_user.first_name)}", parse_mode="HTML")
            db.log_action(chat.id, user.id, "mute", target.from_user.id)
            db.increment_stat(chat.id, "total_mutes")
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إلغاء كتم"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        try:
            perms = ChatPermissions(can_send_messages=True, can_send_photos=True, can_send_videos=True,
                                   can_send_audios=True, can_send_documents=True, can_send_video_notes=True,
                                   can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                                   can_add_web_page_previews=True)
            await chat.restrict_member(target.from_user.id, perms)
            await msg.reply_text(f"🔊 تم إلغاء كتم {mention(target.from_user.id, target.from_user.first_name)}", parse_mode="HTML")
            db.log_action(chat.id, user.id, "unmute", target.from_user.id)
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_kick(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """طرد مستخدم"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        try:
            await chat.ban_member(target.from_user.id)
            await chat.unban_member(target.from_user.id)
            await msg.reply_text(f"👢 تم طرد {mention(target.from_user.id, target.from_user.first_name)}", parse_mode="HTML")
            db.log_action(chat.id, user.id, "kick", target.from_user.id)
            db.increment_stat(chat.id, "total_kicks")
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تحذير مستخدم"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم + اكتب السبب"); return
        reason = " ".join(context.args) if context.args else "بدون سبب"
        count = db.add_warning(chat.id, target.from_user.id, reason, user.id)
        db.increment_stat(chat.id, "total_warns")
        await msg.reply_text(f"⚠️ تحذير {count}/{WARN_LIMIT} لـ {mention(target.from_user.id, target.from_user.first_name)}\n📋 السبب: {reason}", parse_mode="HTML")
        # تنفيذ الإجراء عند تجاوز الحد
        if count >= WARN_LIMIT:
            settings = db.get_settings(chat.id)
            action = settings.get('warn_action', 'mute')
            try:
                if action == 'mute':
                    await chat.restrict_member(target.from_user.id, ChatPermissions(can_send_messages=False))
                    await msg.reply_text(f"🔇 تم كتم - تجاوز حد التحذير!", parse_mode="HTML")
                elif action == 'kick':
                    await chat.ban_member(target.from_user.id)
                    await chat.unban_member(target.from_user.id)
                    await msg.reply_text(f"👢 تم طرد - تجاوز حد التحذير!", parse_mode="HTML")
                elif action == 'ban':
                    await chat.ban_member(target.from_user.id)
                    await msg.reply_text(f"🚫 تم حظر - تجاوز حد التحذير!", parse_mode="HTML")
                db.reset_warnings(chat.id, target.from_user.id)
            except: pass

    async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إزالة تحذيرات"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        db.reset_warnings(chat.id, target.from_user.id)
        await msg.reply_text(f"✅ تم إزالة تحذيرات {mention(target.from_user.id, target.from_user.first_name)}", parse_mode="HTML")

    async def cmd_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض التحذيرات"""
        chat = update.effective_chat
        msg = update.message
        if not chat or chat.type == "private": return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        count = db.get_warning_count(chat.id, target.from_user.id)
        warns = db.get_warnings(chat.id, target.from_user.id)
        text_out = f"📋 <b>تحذيرات {mention(target.from_user.id, target.from_user.first_name)}</b> ({count}/{WARN_LIMIT}):\n\n"
        for i, w in enumerate(warns[:10], 1):
            text_out += f"{i}. {w['reason']} - {w['warned_at'][:10]}\n"
        await msg.reply_text(text_out, parse_mode="HTML")

    async def cmd_delwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حذف التحذيرات"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        db.reset_warnings(chat.id, target.from_user.id)
        await msg.reply_text(f"🗑️ تم حذف تحذيرات {mention(target.from_user.id, target.from_user.first_name)} ✅", parse_mode="HTML")

    async def cmd_del(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """حذف رسالة بالرد عليها"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if target:
            try:
                await target.delete()
                await msg.delete()
                db.increment_stat(chat.id, "total_deleted")
            except: pass
        else:
            await msg.reply_text("📌 رد على الرسالة لحذفها")

    async def cmd_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تثبيت رسالة"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if target:
            try:
                await target.pin()
                await msg.reply_text("📌 تم تثبيت الرسالة ✅")
            except: pass
        else:
            await msg.reply_text("📌 رد على الرسالة لتثبيتها")

    async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض القوانين"""
        chat = update.effective_chat
        if not chat: return
        settings = db.get_settings(chat.id)
        rules = settings.get('rules', '')
        if rules:
            await update.message.reply_text(f"📋 <b>قوانين المجموعة:</b>\n\n{rules}", parse_mode="HTML")
        else:
            await update.message.reply_text("📋 لم يتم تعيين قوانين بعد.")

    async def cmd_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معلوماتي الشخصية"""
        chat = update.effective_chat
        user = update.effective_user
        if not chat or chat.type == "private": return
        rep = db.get_rep(chat.id, user.id)
        msg_cnt = db.get_msg_count(chat.id, user.id)
        warn_cnt = db.get_warning_count(chat.id, user.id)
        role = db.get_user_role(chat.id, user.id)
        is_admin = await check_is_admin(chat, user.id)
        status_text = "مالك" if user.id == OWNER_ID else ("مشرف" if is_admin else "عضو")
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
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معلومات المجموعة"""
        chat = update.effective_chat
        if not chat: return
        stats = db.get_stats(chat.id)
        try:
            count = await chat.get_member_count()
        except:
            count = 0
        text = (
            f"📊 <b>معلومات المجموعة</b>\n\n"
            f"📝 الاسم: {chat.title}\n"
            f"🆔 المعرف: <code>{chat.id}</code>\n"
            f"👥 الأعضاء: {count}\n"
            f"💬 الرسائل: {stats.get('total_messages', 0)}\n"
            f"➕ الانضمامات: {stats.get('total_joins', 0)}\n"
            f"🚫 الحظر: {stats.get('total_bans', 0)}\n"
            f"🔇 الكتم: {stats.get('total_mutes', 0)}\n"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_staff(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض المشرفين"""
        chat = update.effective_chat
        if not chat: return
        try:
            admins = await chat.get_administrators()
            text = "👥 <b>المشرفين:</b>\n\n"
            for a in admins:
                status = "مالك" if a.status == ChatMemberStatus.OWNER else "مشرف"
                text += f"• {mention(a.user.id, a.user.first_name)} - {status}\n"
            await update.message.reply_text(text, parse_mode="HTML")
        except: pass

    async def cmd_badd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إضافة للقائمة السوداء"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم + السبب"); return
        reason = " ".join(context.args) if context.args else "بدون سبب"
        db.add_blacklist(chat.id, target.from_user.id, reason, user.id)
        try:
            await chat.ban_member(target.from_user.id)
            await msg.reply_text(f"🖤 تم إضافة {mention(target.from_user.id, target.from_user.first_name)} للقائمة السوداء وحظره ✅", parse_mode="HTML")
        except:
            await msg.reply_text(f"🖤 تم إضافته للقائمة السوداء ✅", parse_mode="HTML")

    async def cmd_bdel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إزالة من القائمة السوداء"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم"); return
        if db.remove_blacklist(chat.id, target.from_user.id):
            try:
                await chat.unban_member(target.from_user.id)
                await msg.reply_text(f"💚 تم إزالة {mention(target.from_user.id, target.from_user.first_name)} من القائمة السوداء ✅", parse_mode="HTML")
            except:
                await msg.reply_text("💚 تم الإزالة ✅", parse_mode="HTML")
        else:
            await msg.reply_text("❌ غير موجود في القائمة السوداء")

    async def cmd_geturl(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """رابط المجموعة"""
        chat = update.effective_chat
        if not chat: return
        try:
            link = await chat.export_invite_link()
            await update.message.reply_text(f"🔗 <b>رابط المجموعة:</b>\n\n<code>{link}</code>", parse_mode="HTML")
        except:
            await update.message.reply_text("❌ لا يمكن إنشاء رابط")

    async def cmd_inactives(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """الأعضاء غير النشطين"""
        chat = update.effective_chat
        if not chat: return
        inactive = db.get_inactive_users(chat.id, 7)
        if inactive:
            text = f"👻 <b>غير النشطين (7 أيام):</b>\n\n"
            for u in inactive[:20]:
                text += f"• <code>{u['user_id']}</code>\n"
        else:
            text = "👻 جميع الأعضاء نشطين!"
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_listroles(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """عرض الأدوار"""
        chat = update.effective_chat
        if not chat: return
        roles = db.get_all_roles(chat.id)
        if roles:
            text = "📋 <b>الأدوار:</b>\n\n"
            for uid, role_name in roles:
                text += f"• {mention(uid, str(uid))} - 🎖️ {role_name}\n"
        else:
            text = "📋 لا توجد أدوار مخصصة."
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_graphic(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """رسم بياني"""
        chat = update.effective_chat
        if not chat: return
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
            text = "📊 <b>رسم بياني</b>\n\n"
            for label, val in zip(labels, values):
                bar_len = int((val / max_val) * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                text += f"{label}: {bar} {val}\n"
        else:
            text = "📊 لا توجد إحصائيات."
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إرسال رسالة لعضو"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        target = msg.reply_to_message
        if not target or not target.from_user:
            await msg.reply_text("📌 رد على رسالة المستخدم + اكتب الرسالة"); return
        text_msg = " ".join(context.args) if context.args else ""
        if not text_msg:
            await msg.reply_text("📌 اكتب الرسالة بعد الأمر"); return
        try:
            await context.bot.send_message(chat_id=target.from_user.id, text=f"📨 <b>رسالة من الإدارة</b>\n\n{text_msg}", parse_mode="HTML")
            await msg.reply_text("📨 تم إرسال الرسالة ✅")
        except:
            await msg.reply_text("❌ لا يمكن الإرسال. المستخدم حظر البوت.")

    # ═══ تسجيل جميع الأوامر ═══
    app.add_handler(CommandHandler("ban", cmd_ban))
    app.add_handler(CommandHandler("unban", cmd_unban))
    app.add_handler(CommandHandler("mute", cmd_mute))
    app.add_handler(CommandHandler("unmute", cmd_unmute))
    app.add_handler(CommandHandler("kick", cmd_kick))
    app.add_handler(CommandHandler("warn", cmd_warn))
    app.add_handler(CommandHandler("unwarn", cmd_unwarn))
    app.add_handler(CommandHandler("warns", cmd_warns))
    app.add_handler(CommandHandler("delwarn", cmd_delwarn))
    app.add_handler(CommandHandler("del", cmd_del))
    app.add_handler(CommandHandler("pin", cmd_pin))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("me", cmd_me))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("staff", cmd_staff))
    app.add_handler(CommandHandler("badd", cmd_badd))
    app.add_handler(CommandHandler("bdel", cmd_bdel))
    app.add_handler(CommandHandler("geturl", cmd_geturl))
    app.add_handler(CommandHandler("inactives", cmd_inactives))
    app.add_handler(CommandHandler("listroles", cmd_listroles))
    app.add_handler(CommandHandler("graphic", cmd_graphic))
    app.add_handler(CommandHandler("send", cmd_send))
    app.add_handler(CommandHandler("delban", cmd_unban))      # alias
    app.add_handler(CommandHandler("delmute", cmd_unmute))    # alias

    # ═══ أوامر جديدة v10.0 ═══
    async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /id - عرض معرف المستخدم والمجموعة"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or not user:
            return
        text = f"🆔 <b>معلومات المعرفات</b>\n\n"
        text += f"👤 اسمك: {mention(user.id, user.first_name)}\n"
        text += f"📱 معرفك: <code>{user.id}</code>\n"
        if chat.type != "private":
            text += f"👥 المجموعة: <b>{html_escape(chat.title or 'غير معروف')}</b>\n"
            text += f"🆔 معرف المجموعة: <code>{chat.id}</code>\n"
            if msg.reply_to_message and msg.reply_to_message.from_user:
                target = msg.reply_to_message.from_user
                text += f"\n📌 المستخدم المردود عليه:\n"
                text += f"👤 الاسم: {mention(target.id, target.first_name)}\n"
                text += f"📱 المعرف: <code>{target.id}</code>\n"
        await msg.reply_text(text, parse_mode="HTML")

    async def cmd_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر /backup - تصدير إعدادات المجموعة"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private":
            return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        settings = db.get_settings(chat.id)
        locks = db.get_all_locks(chat.id)
        badwords = db.get_badwords(chat.id)
        notes = db.get_all_notes(chat.id)
        filters_list = db.get_all_filters(chat.id)
        backup_data = {
            "chat_id": chat.id,
            "chat_title": chat.title,
            "backup_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "settings": settings,
            "locks": locks,
            "badwords": badwords,
            "notes": notes,
            "filters": filters_list,
        }
        backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
        await msg.reply_text(
            f"📦 <b>نسخة احتياطية - {html_escape(chat.title or 'المجموعة')}</b>\n\n"
            f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"🔒 الأقفال: {len(locks)}\n"
            f"📝 الملاحظات: {len(notes)}\n"
            f"🔍 الفلاتر: {len(filters_list)}\n"
            f"🔤 الكلمات المسيئة: {len(badwords)}\n\n"
            f"<code>{backup_json[:3500]}</code>",
            parse_mode="HTML"
        )

    async def cmd_welcome_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """أمر لتعيين رسالة الترحيب بالعودة"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private":
            return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        welcome_back_msg = " ".join(context.args) if context.args else ""
        if welcome_back_msg:
            db.update_setting(chat.id, "welcome_back_msg", welcome_back_msg)  # إصلاح: كان يحفظ في welcome_msg بالخطأ
            await msg.reply_text(f"✅ تم تعيين رسالة الترحيب بالعودة!\n\n📦 الرسالة:\n{welcome_back_msg}")
        else:
            await msg.reply_text("📝 اكتب الرسالة بعد الأمر\nمثال: /welcomeback مرحباً بعودتك يا {user}! 🎊")

    app.add_handler(CommandHandler("id", cmd_id))
    app.add_handler(CommandHandler("backup", cmd_backup))
    app.add_handler(CommandHandler("welcomeback", cmd_welcome_back))

    # ═══ أوامر جديدة v10.0 - خدمات إضافية ═══
    async def cmd_poll(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إنشاء استطلاع عبر الأمر"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        text_msg = " ".join(context.args) if context.args else ""
        if "|" not in text_msg:
            await msg.reply_text("📝 الصيغة: /poll السؤال | خيار1 | خيار2 | خيار3")
            return
        parts = text_msg.split("|")
        if len(parts) < 3:
            await msg.reply_text("❌ يجب أن يكون هناك سؤال وخياران على الأقل")
            return
        question = parts[0].strip()
        options = [p.strip() for p in parts[1:] if p.strip()]
        try:
            await context.bot.send_poll(chat_id=chat.id, question=question, options=options, is_anonymous=False)
            await msg.reply_text("📝 تم إنشاء الاستطلاع ✅")
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إنشاء لعبة سؤال"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        text_msg = " ".join(context.args) if context.args else ""
        if "|" not in text_msg:
            await msg.reply_text("🎲 الصيغة: /quiz السؤال | الإجابة الصحيحة | خيار خاطئ")
            return
        parts = text_msg.split("|")
        if len(parts) < 3:
            await msg.reply_text("❌ يجب أن يكون هناك سؤال وخياران على الأقل")
            return
        question = parts[0].strip()
        options = [p.strip() for p in parts[1:] if p.strip()]
        try:
            await context.bot.send_poll(chat_id=chat.id, question=question, options=options,
                                        type="quiz", correct_option_id=0, is_anonymous=False)
            await msg.reply_text("🎲 تم إنشاء لعبة السؤال ✅")
        except Exception as e:
            await msg.reply_text(f"❌ خطأ: {e}")

    async def cmd_timer(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تعيين مؤقت"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        if not await check_is_admin(chat, user.id):
            await msg.reply_text("⛔ للمشرفين فقط!"); return
        text_msg = " ".join(context.args) if context.args else ""
        if not text_msg:
            await msg.reply_text("⏱️ الصيغة: /timer الدقائق أو /timer الدقائق | الرسالة")
            return
        if "|" in text_msg:
            parts = text_msg.split("|", 1)
            try:
                minutes = int(parts[0].strip())
                timer_msg = parts[1].strip()
            except:
                await msg.reply_text("❌ الصيغة خاطئة"); return
        else:
            try:
                minutes = int(text_msg.strip())
                timer_msg = "انتهى المؤقت!"
            except:
                await msg.reply_text("❌ اكتب عدد الدقائق"); return
        if minutes < 1 or minutes > 1440:
            await msg.reply_text("❌ الدقائق بين 1 و 1440"); return
        send_at = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        db.add_scheduled(chat.id, f"⏱️ {timer_msg}", send_at, user.id)
        await msg.reply_text(f"⏱️ تم تعيين مؤقت لمدة {minutes} دقيقة ✅")

    async def cmd_quote(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """اقتباس عشوائي"""
        quotes = [
            "🌟 النجاح ليس نهائياً، والفشل ليس قاتلاً: إنما الشجاعة للاستمرار هي ما يهم. - ونستون تشرشل",
            "💡 الطريقة الوحيدة للقيام بعمل عظيم هي أن تحب ما تفعله. - ستيف جوبز",
            "🚀 لا تنتظر الفرصة، بل اصنعها. - جورج برنارد شو",
            "💪 الصعوبات هي التي تُظهر الرجال. - أبيقور",
            "📚 العلم نور، والجهل ظلام. - مثل عربي",
            "🤝 اليد الواحدة لا تصفق. - مثل عربي",
            "⭐ من جدّ وجد، ومن زرع حصد. - مثل عربي",
            "🌈 بعد كل عسر يسر. - القرآن الكريم",
        ]
        await update.message.reply_text(f"💬 <b>اقتباس عشوائي</b>\n\n{random.choice(quotes)}", parse_mode="HTML")

    async def cmd_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """إنشاء تذكرة دعم"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        text_msg = " ".join(context.args) if context.args else ""
        if not text_msg:
            await msg.reply_text("🎫 الصيغة: /ticket مشكلتك أو اقتراحك")
            return
        ticket_id = random.randint(10000, 99999)
        ticket_text = (
            f"🎫 <b>تذكرة دعم جديدة #{ticket_id}</b>\n\n"
            f"👤 من: {mention(user.id, user.first_name)}\n"
            f"📅 التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"💬 المشكلة/الاقتراح:\n{text_msg}\n\n"
            f"⏳ الحالة: قيد المراجعة"
        )
        await msg.reply_text(ticket_text, parse_mode="HTML")

    async def cmd_alertadmins(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """تنبيه المشرفين"""
        chat = update.effective_chat
        user = update.effective_user
        msg = update.message
        if not chat or chat.type == "private": return
        try:
            admins = await chat.get_administrators()
            admin_text = "🔔 <b>تنبيه للمشرفين!</b>\n\n"
            for a in admins:
                admin_text += f"• {mention(a.user.id, a.user.first_name)}\n"
            admin_text += f"\n📍 تم التنبيه بواسطة: {mention(user.id, user.first_name)}"
            await chat.send_message(admin_text, parse_mode="HTML")
        except: pass

    app.add_handler(CommandHandler("poll", cmd_poll))
    app.add_handler(CommandHandler("quiz", cmd_quiz))
    app.add_handler(CommandHandler("timer", cmd_timer))
    app.add_handler(CommandHandler("quote", cmd_quote))
    app.add_handler(CommandHandler("ticket", cmd_ticket))
    app.add_handler(CommandHandler("alertadmins", cmd_alertadmins))

    # تسجيل معالج الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(callback_handler))

    # معالجة الرسائل النصية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # معالجة الرسائل التي ليست نص (صور، فيديو، الخ) - لدعم أقفال الوسائط
    app.add_handler(MessageHandler(
        ~filters.TEXT & ~filters.COMMAND,
        media_handler
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
            app.job_queue.run_repeating(cleanup_memory, interval=300, first=60)  # تنظيف الذاكرة كل 5 دقائق
            app.job_queue.run_repeating(check_expired_captchas, interval=60, first=30)  # فحص الكابتشا المنتهية
            logger.info("✅ تم تسجيل جدولة المهام (4 مهام)")
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

    logger.info("🛡️ بوت إدارة المجموعات v12.0 يعمل الآن!")
    # ═══ معالج الأخطاء العام ═══
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """معالج الأخطاء العام - يمنع توقف البوت عند حدوث أي خطأ"""
        error_str = str(context.error)
        logger.error(f"⚠️ Exception while handling an update: {error_str}")
        
        # تجاهل أخطاء Conflict - البوت سيعيد التشغيل تلقائياً
        if "Conflict" in error_str or "Terminated by other getUpdates" in error_str:
            logger.warning("⚠️ خطأ Conflict - سيتم تجاهله والتشغيل بشكل طبيعي...")
            return
        
        # تجاهل أخطاء الشبكة المؤقتة
        if "TimedOut" in error_str or "NetworkError" in error_str:
            logger.warning("⚠️ خطأ شبكة مؤقت - تم التجاهل")
            return
        
        # تجاهل أخطاء الرسائل المحذوفة
        if "Message to delete not found" in error_str or "Message is not modified" in error_str:
            return

    app.add_error_handler(error_handler)
    logger.info("✅ Global error handler registered")
    logger.info("✅ Bot started successfully! 🚀")
    return app


def main():
    if not TOKEN:
        logger.error("❌ لم يتم تعيين TOKEN! قم بتعيين متغير البيئة TOKEN")
        return

    # ═══ محاولة الحصول على قفل أحادي ═══
    if not acquire_singleton_lock():
        logger.error("❌ مثيل آخر يعمل! الانتظار 60 ثانية...")
        time.sleep(60)
        if not acquire_singleton_lock():
            logger.error("❌ لا يمكن الحصول على القفل. الخروج.")
            return

    # ═══ معالجات الإغلاق الأنيق ═══
    def signal_handler(signum, frame):
        logger.info(f"🛑 Received signal {signum}, shutting down gracefully...")
        release_singleton_lock()
        sys.exit(0)

    signal_module.signal(signal_module.SIGTERM, signal_handler)
    signal_module.signal(signal_module.SIGINT, signal_handler)

    # بدء خادم Flask في خيط منفصل
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ خادم Flask بدأ")

    # ═══ نظام إعادة التشغيل التلقائي - محسّن ═══
    retry_count = 0
    max_retries = 15

    while retry_count < max_retries:
        app = None
        try:
            app = build_application()
            logger.info("🛡️ بوت إدارة المجموعات v12.0 يعمل الآن!")
            app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)
            # إذا وصلنا هنا، فـ run_polling توقف طبيعياً
            logger.warning("⚠️ run_polling stopped normally")
            break

        except Conflict as e:
            retry_count += 1
            wait_time = min(120, 30 * retry_count)  # زيادة أسية حتى 120 ثانية
            logger.warning(f"⚠️ Conflict error (retry #{retry_count}/{max_retries}) - waiting {wait_time}s...")
            # حذف webhook عبر REST API
            try:
                import requests as req
                req.post(f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
                        json={"drop_pending_updates": True}, timeout=10)
            except:
                pass
            time.sleep(wait_time)

        except Exception as e:
            retry_count += 1
            error_str = str(e)
            if "NetworkError" in error_str or "TimedOut" in error_str:
                logger.warning(f"⚠️ Network error (retry #{retry_count}) - restarting in 15 seconds...")
                time.sleep(15)
            else:
                logger.error(f"❌ Unexpected error (retry #{retry_count}): {e}")
                time.sleep(30)

    release_singleton_lock()
    logger.info("🛑 Bot shut down complete")


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
