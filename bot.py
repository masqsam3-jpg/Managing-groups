"""
╔══════════════════════════════════════════════════════════════╗
║          🤖 بوت إدارة المجموعات المتكامل v2.0 🤖            ║
║                                                              ║
║  بوت احترافي لإدارة مجموعات التيليجرام بميزات خارقة         ║
║  مطور بواسطة: فريق التطوير                                   ║
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
from telegram.constants import ChatMemberStatus, ParseMode

# ═══════════════════════════════════════════════════════════════
# إعداد السجلات
# ═══════════════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# الإعدادات العامة
# ═══════════════════════════════════════════════════════════════
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN")
WARN_LIMIT = 3
DEFAULT_WELCOME = "مرحباً بك يا {user} في مجموعتنا! 🎉\nيرجى قراءة القوانين: /rules"
DB_PATH = "bot_database.db"

# ═══════════════════════════════════════════════════════════════
# خادم Flask
# ═══════════════════════════════════════════════════════════════
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return jsonify({"status": "running", "bot": "Group Manager v2.0", "uptime": True}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# ═══════════════════════════════════════════════════════════════
# نظام قاعدة البيانات SQLite
# ═══════════════════════════════════════════════════════════════
class Database:
    """نظام قاعدة البيانات المتكامل للتخزين الدائم"""

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
        
        # جدول إعدادات المجموعات
        c.execute('''CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            welcome_msg TEXT DEFAULT '{}',
            rules TEXT DEFAULT '',
            language TEXT DEFAULT 'ar',
            maintenance_mode INTEGER DEFAULT 0,
            log_channel_id INTEGER DEFAULT 0,
            anti_spam INTEGER DEFAULT 1,
            anti_flood INTEGER DEFAULT 1,
            anti_link INTEGER DEFAULT 0,
            anti_badword INTEGER DEFAULT 1,
            slow_mode INTEGER DEFAULT 0,
            report_enabled INTEGER DEFAULT 1,
            auto_delete_spam INTEGER DEFAULT 1,
            max_flood_msgs INTEGER DEFAULT 5,
            flood_interval INTEGER DEFAULT 5,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول التحذيرات
        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            reason TEXT DEFAULT '',
            warned_by INTEGER,
            warned_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, user_id)
        )''')

        # جدول الملاحظات
        c.execute('''CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            name TEXT,
            content TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, name)
        )''')

        # جدول الفلاتر (ردود تلقائية)
        c.execute('''CREATE TABLE IF NOT EXISTS filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            keyword TEXT,
            reply TEXT,
            created_by INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, keyword)
        )''')

        # جدول الأقفال
        c.execute('''CREATE TABLE IF NOT EXISTS locks (
            chat_id INTEGER,
            lock_type TEXT,
            locked_by INTEGER,
            locked_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (chat_id, lock_type)
        )''')

        # جدول الكلمات المسيئة
        c.execute('''CREATE TABLE IF NOT EXISTS badwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word TEXT,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chat_id, word)
        )''')

        # جدول المشرفين الإضافيين (معروفين بالبوت)
        c.execute('''CREATE TABLE IF NOT EXISTS bot_admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            added_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول إحصائيات المجموعة
        c.execute('''CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER PRIMARY KEY,
            total_messages INTEGER DEFAULT 0,
            total_joins INTEGER DEFAULT 0,
            total_leaves INTEGER DEFAULT 0,
            total_bans INTEGER DEFAULT 0,
            total_mutes INTEGER DEFAULT 0,
            total_warns INTEGER DEFAULT 0,
            total_deleted INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول المكتومين مؤقتاً
        c.execute('''CREATE TABLE IF NOT EXISTS temp_mutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            muted_by INTEGER,
            mute_until TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول سجل الإجراءات
        c.execute('''CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            action TEXT,
            target_id INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')

        conn.commit()
        conn.close()

    # --- إعدادات المجموعة ---
    def get_settings(self, chat_id: int) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM group_settings WHERE chat_id = ?", (chat_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return dict(row)
        # إنشاء إعدادات افتراضية
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

    # --- التحذيرات ---
    def add_warning(self, chat_id: int, user_id: int, reason: str, warned_by: int) -> int:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM warnings WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        existing = c.fetchone()
        if existing:
            c.execute("UPDATE warnings SET reason = ?, warned_by = ?, warned_at = CURRENT_TIMESTAMP WHERE chat_id = ? AND user_id = ?",
                     (reason, warned_by, chat_id, user_id))
            # زيادة العداد عبر عمود منفصل
            c.execute("""CREATE TABLE IF NOT EXISTS warning_counts (
                chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id))""")
            c.execute("""INSERT INTO warning_counts (chat_id, user_id, count) VALUES (?, ?, 1)
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1""",
                     (chat_id, user_id))
            c.execute("SELECT count FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
            count = c.fetchone()[0]
        else:
            c.execute("INSERT INTO warnings (chat_id, user_id, reason, warned_by) VALUES (?, ?, ?, ?)",
                     (chat_id, user_id, reason, warned_by))
            c.execute("""CREATE TABLE IF NOT EXISTS warning_counts (
                chat_id INTEGER, user_id INTEGER, count INTEGER DEFAULT 0,
                PRIMARY KEY(chat_id, user_id))""")
            c.execute("""INSERT INTO warning_counts (chat_id, user_id, count) VALUES (?, ?, 1)
                        ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1""",
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
        try:
            c.execute("DELETE FROM warning_counts WHERE chat_id = ? AND user_id = ?", (chat_id, user_id))
        except:
            pass
        conn.commit()
        conn.close()

    # --- الملاحظات ---
    def save_note(self, chat_id: int, name: str, content: str, user_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO notes (chat_id, name, content, created_by) VALUES (?, ?, ?, ?)",
                 (chat_id, name, content, user_id))
        conn.commit()
        conn.close()

    def get_note(self, chat_id: int, name: str) -> str:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT content FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_notes(self, chat_id: int) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT name FROM notes WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def delete_note(self, chat_id: int, name: str) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM notes WHERE chat_id = ? AND name = ?", (chat_id, name))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    # --- الفلاتر ---
    def save_filter(self, chat_id: int, keyword: str, reply: str, user_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO filters (chat_id, keyword, reply, created_by) VALUES (?, ?, ?, ?)",
                 (chat_id, keyword, reply, user_id))
        conn.commit()
        conn.close()

    def get_filter(self, chat_id: int, keyword: str) -> str:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT reply FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

    def get_all_filters(self, chat_id: int) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT keyword FROM filters WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]

    def delete_filter(self, chat_id: int, keyword: str) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM filters WHERE chat_id = ? AND keyword = ?", (chat_id, keyword))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    # --- الأقفال ---
    def lock_type(self, chat_id: int, lock_type: str, user_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO locks (chat_id, lock_type, locked_by) VALUES (?, ?, ?)",
                 (chat_id, lock_type, user_id))
        conn.commit()
        conn.close()

    def unlock_type(self, chat_id: int, lock_type: str) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM locks WHERE chat_id = ? AND lock_type = ?", (chat_id, lock_type))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def is_locked(self, chat_id: int, lock_type: str) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT 1 FROM locks WHERE chat_id = ? AND lock_type = ?", (chat_id, lock_type))
        exists = c.fetchone() is not None
        conn.close()
        return exists

    def get_all_locks(self, chat_id: int) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT lock_type FROM locks WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]

    # --- الكلمات المسيئة ---
    def add_badword(self, chat_id: int, word: str, user_id: int):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO badwords (chat_id, word, added_by) VALUES (?, ?, ?)",
                 (chat_id, word, user_id))
        conn.commit()
        conn.close()

    def remove_badword(self, chat_id: int, word: str) -> bool:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("DELETE FROM badwords WHERE chat_id = ? AND word = ?", (chat_id, word))
        deleted = c.rowcount > 0
        conn.commit()
        conn.close()
        return deleted

    def get_badwords(self, chat_id: int) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT word FROM badwords WHERE chat_id = ?", (chat_id,))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]

    # --- الإحصائيات ---
    def increment_stat(self, chat_id: int, stat: str):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO group_stats (chat_id) VALUES (?) ON CONFLICT(chat_id) DO NOTHING", (chat_id,))
        c.execute(f"UPDATE group_stats SET {stat} = {stat} + 1, updated_at = CURRENT_TIMESTAMP WHERE chat_id = ?",
                 (chat_id,))
        conn.commit()
        conn.close()

    def get_stats(self, chat_id: int) -> dict:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM group_stats WHERE chat_id = ?", (chat_id,))
        row = c.fetchone()
        conn.close()
        return dict(row) if row else {}

    # --- الكتم المؤقت ---
    def add_temp_mute(self, chat_id: int, user_id: int, muted_by: int, mute_until: str):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO temp_mutes (chat_id, user_id, muted_by, mute_until) VALUES (?, ?, ?, ?)",
                 (chat_id, user_id, muted_by, mute_until))
        conn.commit()
        conn.close()

    def get_expired_mutes(self) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT * FROM temp_mutes WHERE mute_until <= ?", (now,))
        rows = c.fetchall()
        # حذف المنتهية
        c.execute("DELETE FROM temp_mutes WHERE mute_until <= ?", (now,))
        conn.commit()
        conn.close()
        return [dict(row) for row in rows]

    # --- سجل الإجراءات ---
    def log_action(self, chat_id: int, user_id: int, action: str, target_id: int = 0, reason: str = ""):
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO action_log (chat_id, user_id, action, target_id, reason) VALUES (?, ?, ?, ?, ?)",
                 (chat_id, user_id, action, target_id, reason))
        conn.commit()
        conn.close()

    def get_action_log(self, chat_id: int, limit: int = 10) -> list:
        conn = self._get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM action_log WHERE chat_id = ? ORDER BY id DESC LIMIT ?", (chat_id, limit))
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]


# إنشاء قاعدة البيانات
db = Database(DB_PATH)

# ═══════════════════════════════════════════════════════════════
# ثوابت أنواع الأقفال
# ═══════════════════════════════════════════════════════════════
LOCK_TYPES = {
    "photos": "الصور 📷",
    "videos": "الفيديو 🎬",
    "stickers": "الملصقات 🎭",
    "animations": "ال GIF 🎞️",
    "voice": "الرسائل الصوتية 🎤",
    "audio": "الصوتيات 🎵",
    "documents": "الملفات 📄",
    "links": "الروابط 🔗",
    "forward": "الرسائل المعاد توجيهها ↗️",
    "inline": "الإنلاين ⚡",
    "polls": "الاستفتاءات 📊",
    "contacts": "جهات الاتصال 📱",
    "location": "الموقع 📍",
    "venue": "الأماكن 🏢",
    "text": "النصوص ✏️",
    "bots": "البوتات 🤖",
}

# ═══════════════════════════════════════════════════════════════
# نظام الفلود (في الذاكرة)
# ═══════════════════════════════════════════════════════════════
flood_data = {}  # {chat_id: {user_id: [timestamp1, timestamp2, ...]}}

def check_flood(chat_id: int, user_id: int, max_msgs: int = 5, interval: int = 5) -> bool:
    """التحقق من الفلود - يرجع True إذا كان المستخدم يرسل رسائل بسرعة"""
    now = time.time()
    if chat_id not in flood_data:
        flood_data[chat_id] = {}
    if user_id not in flood_data[chat_id]:
        flood_data[chat_id][user_id] = []
    
    # إضافة الطابع الزمني الحالي
    flood_data[chat_id][user_id].append(now)
    
    # حذف الطوابع القديمة
    flood_data[chat_id][user_id] = [t for t in flood_data[chat_id][user_id] if now - t <= interval]
    
    return len(flood_data[chat_id][user_id]) > max_msgs

# ═══════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════
async def is_admin(update: Update, user_id: int = None) -> bool:
    """التحقق مما إذا كان المستخدم مشرفاً"""
    try:
        if user_id is None:
            user_id = update.effective_user.id
        admins = await update.effective_chat.get_administrators()
        return user_id in [admin.user.id for admin in admins]
    except:
        return False

async def is_bot_admin(update: Update) -> bool:
    """التحقق مما إذا كان البوت مشرفاً"""
    try:
        bot_member = await update.effective_chat.get_member(update.message.bot.id)
        return bot_member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except:
        return False

def mention_user(user_id: int, name: str) -> str:
    """إنشاء إشارة للمستخدم"""
    return f'<a href="tg://user?id={user_id}">{name}</a>'

def parse_time(time_str: str) -> int:
    """تحويل وقت مثل '5m' أو '2h' إلى ثوانٍ"""
    if not time_str:
        return 0
    time_str = time_str.lower().strip()
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    match = re.match(r'^(\d+)([smhd])$', time_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        return amount * units[unit]
    try:
        return int(time_str) * 60  # افتراضي: دقائق
    except:
        return 0

def format_time(seconds: int) -> str:
    """تنسيق الثواني إلى نص مقروء"""
    if seconds >= 86400:
        return f"{seconds // 86400} يوم"
    elif seconds >= 3600:
        return f"{seconds // 3600} ساعة"
    elif seconds >= 60:
        return f"{seconds // 60} دقيقة"
    else:
        return f"{seconds} ثانية"

async def send_log(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE):
    """إرسال سجل إلى قناة السجلات"""
    settings = db.get_settings(chat_id)
    log_channel = settings.get('log_channel_id', 0)
    if log_channel and log_channel != 0:
        try:
            await context.bot.send_message(chat_id=log_channel, text=text, parse_mode="HTML")
        except:
            pass

# ═══════════════════════════════════════════════════════════════
# ديكوريتر التحقق من المشرفين
# ═══════════════════════════════════════════════════════════════
def admin_only(func):
    """ديكوريتر للتحقق من أن المستخدم مشرف"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_admin(update):
            await update.message.reply_text("⛔ هذا الأمر للمشرفين فقط!")
            return
        return await func(update, context)
    return wrapper

def bot_admin_required(func):
    """ديكوريتر للتحقق من أن البوت مشرف"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await is_bot_admin(update):
            await update.message.reply_text("⛔ البوت يحتاج إلى صلاحيات مشرف لتنفيذ هذا الأمر!")
            return
        return await func(update, context)
    return wrapper

# ═══════════════════════════════════════════════════════════════
# أوامر البوت الأساسية
# ═══════════════════════════════════════════════════════════════

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البدء"""
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📖 الأوامر", callback_data="help"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
        [InlineKeyboardButton("👤 المطور", url="https://t.me/masqsam3")]
    ])
    text = """🤖 **مرحباً! أنا بوت إدارة المجموعات المتكامل v2.0**

🛡️ أحمي مجموعتك وأديرها باحترافية

✨ **الميزات الرئيسية:**
• 🚫 الحظر والكتم (مؤقت ودائم)
• ⚠️ نظام التحذيرات المتقدم
• 🛡️ حماية ضد السبام والفلود
• 📋 نظام القوانين والملاحظات
• 🔍 فلاتر الرد التلقائي
• 🔒 قفل أنواع الرسائل
• 📊 إحصائيات مفصلة
• 📢 نظام الإعلانات
• 🔤 فلتر الكلمات المسيئة
• 🚨 نظام البلاغات

اضغط على الأزرار أدناه للبدء 👇"""
    
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الأوامر المتاحة"""
    text = """📖 **دليل الأوامر الكامل**

🛡️ **أوامر الإشراف:**
• `/ban` [سبب] - حظر مستخدم (بالرد)
• `/unban` - إلغاء الحظر (بالرد)
• `/mute` [وقت] - كتم مستخدم (بالرد)
• `/unmute` - إلغاء الكتم (بالرد)
• `/tmute` [وقت] - كتم مؤقت (مثل: /tmute 5m)
• `/kick` - طرد مستخدم (بالرد)
• `/warn` [سبب] - تحذير مستخدم
• `/unwarn` - إزالة التحذيرات
• `/del` / `/purge` [عدد] - حذف رسائل

📌 **إدارة المحتوى:**
• `/pin` - تثبيت رسالة (بالرد)
• `/unpin` - إلغاء التثبيت
• `/setrules` [نص] - تعيين القوانين
• `/rules` - عرض القوانين
• `/clearrules` - حذف القوانين

📝 **الملاحظات:**
• `/save` [اسم] [محتوى] - حفظ ملاحظة
• `/get` [اسم] - استرجاع ملاحظة
• `/notes` - عرض كل الملاحظات
• `/delnote` [اسم] - حذف ملاحظة

🔍 **الفلاتر (رد تلقائي):**
• `/filter` [كلمة] [رد] - إضافة فلتر
• `/stop` [كلمة] - حذف فلتر
• `/filters` - عرض الفلاتر

🔒 **الأقفال:**
• `/lock` [نوع] - قفل نوع رسالة
• `/unlock` [نوع] - فتح نوع رسالة
• `/locks` - عرض الأقفال
• `/lockall` - قفل الكل
• `/unlockall` - فتح الكل

🔤 **فلتر الكلمات:**
• `/addbadword` [كلمة] - إضافة كلمة مسيئة
• `/delbadword` [كلمة] - حذف كلمة مسيئة
• `/badwords` - عرض الكلمات المحظورة

⚙️ **الإعدادات:**
• `/setwelcome` [نص] - تعيين ترحيب مخصص
• `/resetwelcome` - إعادة الترحيب الافتراضي
• `/antispam` [تشغيل/إيقاف] - حماية السبام
• `/antiflood` [تشغيل/إيقاف] - حماية الفلود
• `/antilink` [تشغيل/إيقاف] - منع الروابط
• `/maintenance` - وضع الصيانة
• `/setlog` [معرف] - تعيين قناة السجلات

📊 **المعلومات:**
• `/info` - معلومات المستخدم
• `/stats` - إحصائيات المجموعة
• `/admins` - قائمة المشرفين
• `/log` - سجل الإجراءات

🚨 **أخرى:**
• `@admin` - إبلاغ المشرفين
• `/announce` [نص] - إعلان للجميع
• `/report` - بلاغ عن مستخدم"""

    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# أوامر الإشراف
# ═══════════════════════════════════════════════════════════════

@admin_only
@bot_admin_required
async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حظر مستخدم"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم المراد حظره!")
        return
    
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "بدون سبب"
    chat = update.effective_chat
    
    # لا يمكن حظر المشرفين
    if await is_admin(update, target.id):
        await update.message.reply_text("⛔ لا يمكن حظر مشرف!")
        return
    
    try:
        await chat.ban_member(target.id)
        mention = mention_user(target.id, target.full_name)
        admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
        await update.message.reply_text(
            f"🚫 تم حظر {mention}\n👤 بواسطة: {admin_mention}\n📝 السبب: {reason}",
            parse_mode="HTML"
        )
        db.increment_stat(chat.id, "total_bans")
        db.log_action(chat.id, update.effective_user.id, "ban", target.id, reason)
        await send_log(chat.id, f"🚫 حظر: {mention} بواسطة {admin_mention} - السبب: {reason}", context)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في الحظر: {str(e)}")

@admin_only
@bot_admin_required
async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء الحظر"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    chat = update.effective_chat
    
    try:
        await chat.unban_member(target.id)
        mention = mention_user(target.id, target.full_name)
        await update.message.reply_text(f"✅ تم إلغاء حظر {mention}", parse_mode="HTML")
        db.log_action(chat.id, update.effective_user.id, "unban", target.id)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

@admin_only
@bot_admin_required
async def mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كتم مستخدم"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    chat = update.effective_chat
    
    if await is_admin(update, target.id):
        await update.message.reply_text("⛔ لا يمكن كتم مشرف!")
        return
    
    try:
        permissions = ChatPermissions(can_send_messages=False)
        await chat.restrict_member(target.id, permissions)
        mention = mention_user(target.id, target.full_name)
        admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
        await update.message.reply_text(
            f"🔇 تم كتم {mention}\n👤 بواسطة: {admin_mention}",
            parse_mode="HTML"
        )
        db.increment_stat(chat.id, "total_mutes")
        db.log_action(chat.id, update.effective_user.id, "mute", target.id)
        await send_log(chat.id, f"🔇 كتم: {mention} بواسطة {admin_mention}", context)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

@admin_only
@bot_admin_required
async def unmute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء الكتم"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    chat = update.effective_chat
    
    try:
        permissions = ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=True,
            can_invite_users=True,
            can_pin_messages=True
        )
        await chat.restrict_member(target.id, permissions)
        mention = mention_user(target.id, target.full_name)
        await update.message.reply_text(f"🔊 تم إلغاء كتم {mention}", parse_mode="HTML")
        db.log_action(chat.id, update.effective_user.id, "unmute", target.id)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

@admin_only
@bot_admin_required
async def temp_mute_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """كتم مؤقت"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    if not context.args:
        await update.message.reply_text("⏱️ حدد المدة! مثال: `/tmute 5m` أو `/tmute 2h`\n\nالوحدات: s=ثانية, m=دقيقة, h=ساعة, d=يوم", parse_mode="Markdown")
        return
    
    target = update.message.reply_to_message.from_user
    chat = update.effective_chat
    
    if await is_admin(update, target.id):
        await update.message.reply_text("⛔ لا يمكن كتم مشرف!")
        return
    
    seconds = parse_time(context.args[0])
    if seconds <= 0:
        await update.message.reply_text("❌ صيغة وقت غير صحيحة!")
        return
    
    try:
        until = datetime.now() + timedelta(seconds=seconds)
        permissions = ChatPermissions(can_send_messages=False)
        await chat.restrict_member(target.id, permissions, until_date=until)
        
        mention = mention_user(target.id, target.full_name)
        admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
        time_str = format_time(seconds)
        
        await update.message.reply_text(
            f"⏱️ تم كتم {mention} لمدة {time_str}\n👤 بواسطة: {admin_mention}",
            parse_mode="HTML"
        )
        db.add_temp_mute(chat.id, target.id, update.effective_user.id, until.strftime("%Y-%m-%d %H:%M:%S"))
        db.increment_stat(chat.id, "total_mutes")
        db.log_action(chat.id, update.effective_user.id, f"temp_mute_{time_str}", target.id)
        await send_log(chat.id, f"⏱️ كتم مؤقت: {mention} لمدة {time_str} بواسطة {admin_mention}", context)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

@admin_only
@bot_admin_required
async def kick_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طرد مستخدم"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "بدون سبب"
    chat = update.effective_chat
    
    if await is_admin(update, target.id):
        await update.message.reply_text("⛔ لا يمكن طرد مشرف!")
        return
    
    try:
        await chat.ban_member(target.id)
        await chat.unban_member(target.id)  # إلغاء الحظر بعد الطرد
        mention = mention_user(target.id, target.full_name)
        admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
        await update.message.reply_text(
            f"👢 تم طرد {mention}\n👤 بواسطة: {admin_mention}\n📝 السبب: {reason}",
            parse_mode="HTML"
        )
        db.log_action(chat.id, update.effective_user.id, "kick", target.id, reason)
        await send_log(chat.id, f"👢 طرد: {mention} بواسطة {admin_mention} - السبب: {reason}", context)
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

# ═══════════════════════════════════════════════════════════════
# أوامر التحذيرات
# ═══════════════════════════════════════════════════════════════

@admin_only
async def warn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تحذير مستخدم"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    reason = " ".join(context.args) if context.args else "بدون سبب"
    chat = update.effective_chat
    
    if await is_admin(update, target.id):
        await update.message.reply_text("⛔ لا يمكن تحذير مشرف!")
        return
    
    count = db.add_warning(chat.id, target.id, reason, update.effective_user.id)
    mention = mention_user(target.id, target.full_name)
    admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
    db.increment_stat(chat.id, "total_warns")
    
    if count >= WARN_LIMIT:
        try:
            await chat.ban_member(target.id)
            await update.message.reply_text(
                f"🚫 تم حظر {mention} بعد بلوغ الحد الأقصى من التحذيرات ({WARN_LIMIT})!",
                parse_mode="HTML"
            )
            db.reset_warnings(chat.id, target.id)
            db.increment_stat(chat.id, "total_bans")
            db.log_action(chat.id, update.effective_user.id, "auto_ban_warns", target.id, f"{WARN_LIMIT} تحذيرات")
        except:
            pass
    else:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚠️ إزالة التحذير", callback_data=f"unwarn_{target.id}")
        ]])
        await update.message.reply_text(
            f"⚠️ تحذير {count}/{WARN_LIMIT} لـ {mention}\n👤 بواسطة: {admin_mention}\n📝 السبب: {reason}",
            parse_mode="HTML",
            reply_markup=keyboard
        )
    
    db.log_action(chat.id, update.effective_user.id, "warn", target.id, reason)
    await send_log(chat.id, f"⚠️ تحذير {count}/{WARN_LIMIT}: {mention} بواسطة {admin_mention} - {reason}", context)

@admin_only
async def unwarn_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إزالة التحذيرات"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على رسالة المستخدم!")
        return
    
    target = update.message.reply_to_message.from_user
    chat = update.effective_chat
    
    db.reset_warnings(chat.id, target.id)
    mention = mention_user(target.id, target.full_name)
    await update.message.reply_text(f"✅ تم إزالة جميع تحذيرات {mention}", parse_mode="HTML")
    db.log_action(chat.id, update.effective_user.id, "unwarn", target.id)

async def unwarn_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """زر إزالة التحذير"""
    query = update.callback_query
    await query.answer()
    
    if not await is_admin(update, query.from_user.id):
        await query.answer("⛔ للمشرفين فقط!", show_alert=True)
        return
    
    data = query.data
    if data.startswith("unwarn_"):
        user_id = int(data.split("_")[1])
        chat_id = update.effective_chat.id
        db.reset_warnings(chat_id, user_id)
        await query.edit_message_text("✅ تم إزالة جميع التحذيرات!")

# ═══════════════════════════════════════════════════════════════
# أوامر حذف الرسائل
# ═══════════════════════════════════════════════════════════════

@admin_only
@bot_admin_required
async def del_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف رسالة واحدة"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على الرسالة المراد حذفها!")
        return
    
    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
        db.increment_stat(update.effective_chat.id, "total_deleted")
    except:
        await update.message.reply_text("❌ لا يمكن حذف الرسالة!")

@admin_only
@bot_admin_required
async def purge_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف عدة رسائل"""
    if not update.message.reply_to_message:
        count = int(context.args[0]) if context.args else 5
        try:
            # حذف الرسائل الأخيرة
            deleted = 0
            msg = update.message
            for _ in range(min(count, 100)):
                try:
                    await msg.delete()
                    deleted += 1
                    msg = await context.bot.forward_message(
                        chat_id=update.effective_chat.id,
                        from_chat_id=update.effective_chat.id,
                        message_id=msg.message_id - 1
                    )
                except:
                    break
            await update.effective_chat.send_message(f"🗑️ تم حذف {deleted} رسالة")
        except:
            pass
        return
    
    try:
        start_id = update.message.reply_to_message.message_id
        end_id = update.message.message_id
        deleted = 0
        
        for msg_id in range(start_id, end_id):
            try:
                await context.bot.delete_message(update.effective_chat.id, msg_id)
                deleted += 1
            except:
                continue
        
        await update.effective_chat.send_message(f"🗑️ تم حذف {deleted} رسالة")
        db.increment_stat(update.effective_chat.id, "total_deleted")
        db.log_action(update.effective_chat.id, update.effective_user.id, f"purge_{deleted}")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)}")

# ═══════════════════════════════════════════════════════════════
# أوامر التثبيت
# ═══════════════════════════════════════════════════════════════

@admin_only
async def pin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تثبيت رسالة"""
    if not update.message.reply_to_message:
        await update.message.reply_text("⛔ يجب الرد على الرسالة المراد تثبيتها!")
        return
    
    notify = "--silent" not in (context.args or [])
    try:
        await update.message.reply_to_message.pin(disable_notification=not notify)
        await update.message.reply_text("📌 تم تثبيت الرسالة!")
        db.log_action(update.effective_chat.id, update.effective_user.id, "pin")
    except:
        await update.message.reply_text("❌ لا يمكن تثبيت الرسالة!")

@admin_only
async def unpin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء التثبيت"""
    try:
        await update.effective_chat.unpin_all_messages()
        await update.message.reply_text("📌 تم إلغاء تثبيت جميع الرسائل!")
        db.log_action(update.effective_chat.id, update.effective_user.id, "unpin")
    except:
        await update.message.reply_text("❌ لا يمكن إلغاء التثبيت!")

# ═══════════════════════════════════════════════════════════════
# نظام القوانين
# ═══════════════════════════════════════════════════════════════

@admin_only
async def setrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قوانين المجموعة"""
    if not context.args:
        await update.message.reply_text("⛔ اكتب القوانين! مثال: `/setrules 1. لا سبام 2. احترام الآخرين`", parse_mode="Markdown")
        return
    
    rules = " ".join(context.args)
    db.update_setting(update.effective_chat.id, "rules", rules)
    await update.message.reply_text("✅ تم تعيين قوانين المجموعة بنجاح!")
    db.log_action(update.effective_chat.id, update.effective_user.id, "set_rules")

async def rules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القوانين"""
    settings = db.get_settings(update.effective_chat.id)
    rules = settings.get("rules", "")
    if rules:
        await update.message.reply_text(f"📋 **قوانين المجموعة:**\n\n{rules}", parse_mode="Markdown")
    else:
        await update.message.reply_text("📋 لم يتم تعيين قوانين بعد!\nاستخدم /setrules لتعيينها.")

@admin_only
async def clearrules_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف القوانين"""
    db.update_setting(update.effective_chat.id, "rules", "")
    await update.message.reply_text("✅ تم حذف قوانين المجموعة!")

# ═══════════════════════════════════════════════════════════════
# نظام الملاحظات
# ═══════════════════════════════════════════════════════════════

@admin_only
async def save_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حفظ ملاحظة"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⛔ الصيغة: `/save اسم_الملاحظة المحتوى`", parse_mode="Markdown")
        return
    
    name = context.args[0].lower()
    content = " ".join(context.args[1:])
    
    # دعم الرد على رسالة لحفظها كملاحظة
    if update.message.reply_to_message and not content:
        content = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    
    db.save_note(update.effective_chat.id, name, content, update.effective_user.id)
    await update.message.reply_text(f"📝 تم حفظ الملاحظة `{name}` بنجاح!", parse_mode="Markdown")

async def get_note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استرجاع ملاحظة"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/get اسم_الملاحظة`", parse_mode="Markdown")
        return
    
    name = context.args[0].lower()
    content = db.get_note(update.effective_chat.id, name)
    
    if content:
        await update.message.reply_text(content)
    else:
        await update.message.reply_text(f"❌ لا توجد ملاحظة باسم `{name}`", parse_mode="Markdown")

async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض كل الملاحظات"""
    notes = db.get_all_notes(update.effective_chat.id)
    if notes:
        text = "📝 **الملاحظات المحفوظة:**\n\n"
        for note in notes:
            text += f"• `{note}` - /get {note}\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("📝 لا توجد ملاحظات محفوظة!")

@admin_only
async def delnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف ملاحظة"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/delnote اسم_الملاحظة`", parse_mode="Markdown")
        return
    
    name = context.args[0].lower()
    if db.delete_note(update.effective_chat.id, name):
        await update.message.reply_text(f"✅ تم حذف الملاحظة `{name}`!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ لا توجد ملاحظة باسم `{name}`", parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# نظام الفلاتر (رد تلقائي)
# ═══════════════════════════════════════════════════════════════

@admin_only
async def filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة فلتر رد تلقائي"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("⛔ الصيغة: `/filter كلمة_المفتاح الرد`", parse_mode="Markdown")
        return
    
    keyword = context.args[0].lower()
    reply = " ".join(context.args[1:])
    
    db.save_filter(update.effective_chat.id, keyword, reply, update.effective_user.id)
    await update.message.reply_text(f"🔍 تم إضافة فلتر لـ `{keyword}`!", parse_mode="Markdown")

@admin_only
async def stop_filter_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف فلتر"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/stop كلمة_المفتاح`", parse_mode="Markdown")
        return
    
    keyword = context.args[0].lower()
    if db.delete_filter(update.effective_chat.id, keyword):
        await update.message.reply_text(f"✅ تم حذف فلتر `{keyword}`!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ لا يوجد فلتر بـ `{keyword}`", parse_mode="Markdown")

async def filters_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الفلاتر"""
    filters_list = db.get_all_filters(update.effective_chat.id)
    if filters_list:
        text = "🔍 **الفلاتر النشطة:**\n\n"
        for f in filters_list:
            text += f"• `{f}`\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("🔍 لا توجد فلاتر نشطة!")

# ═══════════════════════════════════════════════════════════════
# نظام الأقفال
# ═══════════════════════════════════════════════════════════════

@admin_only
async def lock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قفل نوع رسالة"""
    if not context.args:
        types_text = "\n".join([f"• `{k}` - {v}" for k, v in LOCK_TYPES.items()])
        await update.message.reply_text(f"⛔ حدد نوع القفل! الأنواع المتاحة:\n\n{types_text}", parse_mode="Markdown")
        return
    
    lock_type = context.args[0].lower()
    if lock_type not in LOCK_TYPES:
        await update.message.reply_text(f"❌ نوع قفل غير صحيح! استخدم /lock لعرض الأنواع المتاحة.")
        return
    
    db.lock_type(update.effective_chat.id, lock_type, update.effective_user.id)
    await update.message.reply_text(f"🔒 تم قفل {LOCK_TYPES[lock_type]}!", parse_mode="HTML")
    db.log_action(update.effective_chat.id, update.effective_user.id, f"lock_{lock_type}")

@admin_only
async def unlock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح نوع رسالة"""
    if not context.args:
        await update.message.reply_text("⛔ حدد نوع القفل! استخدم /locks لعرض الأقفال النشطة.")
        return
    
    lock_type = context.args[0].lower()
    if db.unlock_type(update.effective_chat.id, lock_type):
        name = LOCK_TYPES.get(lock_type, lock_type)
        await update.message.reply_text(f"🔓 تم فتح {name}!")
        db.log_action(update.effective_chat.id, update.effective_user.id, f"unlock_{lock_type}")
    else:
        await update.message.reply_text(f"❌ هذا النوع غير مقفل!")

async def locks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الأقفال النشطة"""
    locks = db.get_all_locks(update.effective_chat.id)
    if locks:
        text = "🔒 **الأقفال النشطة:**\n\n"
        for lock in locks:
            name = LOCK_TYPES.get(lock, lock)
            text += f"• {name} (`{lock}`)\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("🔓 لا توجد أقفال نشطة!")

@admin_only
async def lockall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قفل الكل"""
    for lock_type in LOCK_TYPES:
        db.lock_type(update.effective_chat.id, lock_type, update.effective_user.id)
    await update.message.reply_text("🔒 تم قفل جميع أنواع الرسائل!")
    db.log_action(update.effective_chat.id, update.effective_user.id, "lock_all")

@admin_only
async def unlockall_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح الكل"""
    for lock_type in LOCK_TYPES:
        db.unlock_type(update.effective_chat.id, lock_type)
    await update.message.reply_text("🔓 تم فتح جميع أنواع الرسائل!")
    db.log_action(update.effective_chat.id, update.effective_user.id, "unlock_all")

# ═══════════════════════════════════════════════════════════════
# فلتر الكلمات المسيئة
# ═══════════════════════════════════════════════════════════════

@admin_only
async def addbadword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إضافة كلمة مسيئة"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/addbadword الكلمة`", parse_mode="Markdown")
        return
    
    word = " ".join(context.args).lower()
    db.add_badword(update.effective_chat.id, word, update.effective_user.id)
    await update.message.reply_text(f"🔤 تم إضافة `{word}` لقائمة الكلمات المحظورة!", parse_mode="Markdown")

@admin_only
async def delbadword_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف كلمة مسيئة"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/delbadword الكلمة`", parse_mode="Markdown")
        return
    
    word = " ".join(context.args).lower()
    if db.remove_badword(update.effective_chat.id, word):
        await update.message.reply_text(f"✅ تم حذف `{word}` من القائمة!", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"❌ الكلمة غير موجودة في القائمة!")

async def badwords_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الكلمات المحظورة"""
    words = db.get_badwords(update.effective_chat.id)
    if words:
        text = "🔤 **الكلمات المحظورة:**\n\n"
        for w in words:
            text += f"• `{w}`\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("🔤 لا توجد كلمات محظورة!")

# ═══════════════════════════════════════════════════════════════
# إعدادات الترحيب
# ═══════════════════════════════════════════════════════════════

@admin_only
async def setwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين رسالة ترحيب مخصصة"""
    if not context.args:
        await update.message.reply_text(
            "⛔ اكتب رسالة الترحيب!\n\n"
            "المتغيرات المتاحة:\n"
            "• `{user}` - اسم المستخدم\n"
            "• `{chat}` - اسم المجموعة\n"
            "• `{count}` - عدد الأعضاء\n\n"
            "مثال: `/setwelcome مرحباً {user} في {chat}!`",
            parse_mode="Markdown"
        )
        return
    
    welcome = " ".join(context.args)
    db.update_setting(update.effective_chat.id, "welcome_msg", json.dumps({"text": welcome}))
    await update.message.reply_text(f"✅ تم تعيين رسالة الترحيب!\n\nمعاينة:\n{welcome}")

@admin_only
async def resetwelcome_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعادة الترحيب الافتراضي"""
    db.update_setting(update.effective_chat.id, "welcome_msg", json.dumps({"text": DEFAULT_WELCOME}))
    await update.message.reply_text("✅ تم إعادة رسالة الترحيب الافتراضية!")

# ═══════════════════════════════════════════════════════════════
# إعدادات الحماية
# ═══════════════════════════════════════════════════════════════

@admin_only
async def antispam_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل/إيقاف حماية السبام"""
    if not context.args or context.args[0].lower() not in ["تشغيل", "إيقاف", "on", "off"]:
        await update.message.reply_text("⛔ الصيغة: `/antispam تشغيل` أو `/antispam إيقاف`", parse_mode="Markdown")
        return
    
    value = 1 if context.args[0].lower() in ["تشغيل", "on"] else 0
    db.update_setting(update.effective_chat.id, "anti_spam", value)
    status = "✅ تم التشغيل" if value else "⛔ تم الإيقاف"
    await update.message.reply_text(f"🛡️ حماية السبام: {status}")

@admin_only
async def antiflood_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل/إيقاف حماية الفلود"""
    if not context.args or context.args[0].lower() not in ["تشغيل", "إيقاف", "on", "off"]:
        await update.message.reply_text("⛔ الصيغة: `/antiflood تشغيل` أو `/antiflood إيقاف`", parse_mode="Markdown")
        return
    
    value = 1 if context.args[0].lower() in ["تشغيل", "on"] else 0
    db.update_setting(update.effective_chat.id, "anti_flood", value)
    status = "✅ تم التشغيل" if value else "⛔ تم الإيقاف"
    await update.message.reply_text(f"🌊 حماية الفلود: {status}")

@admin_only
async def antilink_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل/إيقاف منع الروابط"""
    if not context.args or context.args[0].lower() not in ["تشغيل", "إيقاف", "on", "off"]:
        await update.message.reply_text("⛔ الصيغة: `/antilink تشغيل` أو `/antilink إيقاف`", parse_mode="Markdown")
        return
    
    value = 1 if context.args[0].lower() in ["تشغيل", "on"] else 0
    db.update_setting(update.effective_chat.id, "anti_link", value)
    status = "✅ تم التشغيل" if value else "⛔ تم الإيقاف"
    await update.message.reply_text(f"🔗 منع الروابط: {status}")

# ═══════════════════════════════════════════════════════════════
# وضع الصيانة
# ═══════════════════════════════════════════════════════════════

@admin_only
async def maintenance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وضع الصيانة"""
    settings = db.get_settings(update.effective_chat.id)
    current = settings.get("maintenance_mode", 0)
    new_value = 0 if current else 1
    db.update_setting(update.effective_chat.id, "maintenance_mode", new_value)
    
    if new_value:
        await update.message.reply_text(
            "🔧 تم تفعيل وضع الصيانة!\n\n"
            "سيتم حذف جميع الرسائل الجديدة تلقائياً.\n"
            "فقط المشرفون يمكنهم الكتابة."
        )
    else:
        await update.message.reply_text("✅ تم إلغاء وضع الصيانة!")
    db.log_action(update.effective_chat.id, update.effective_user.id, f"maintenance_{'on' if new_value else 'off'}")

# ═══════════════════════════════════════════════════════════════
# قناة السجلات
# ═══════════════════════════════════════════════════════════════

@admin_only
async def setlog_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعيين قناة السجلات"""
    if not context.args:
        await update.message.reply_text("⛔ الصيغة: `/setlog معرف_القناة`\nمثال: `/setlog -1001234567890`", parse_mode="Markdown")
        return
    
    try:
        channel_id = int(context.args[0])
        db.update_setting(update.effective_chat.id, "log_channel_id", channel_id)
        await update.message.reply_text(f"✅ تم تعيين قناة السجلات: `{channel_id}`", parse_mode="Markdown")
    except ValueError:
        await update.message.reply_text("❌ معرف القناة غير صحيح!")

# ═══════════════════════════════════════════════════════════════
# معلومات المستخدم
# ═══════════════════════════════════════════════════════════════

async def info_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات المستخدم"""
    if update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
    else:
        user = update.effective_user
    
    chat = update.effective_chat
    member = await chat.get_member(user.id)
    
    status_emoji = {
        ChatMemberStatus.OWNER: "👑 مالك",
        ChatMemberStatus.ADMINISTRATOR: "⭐ مشرف",
        ChatMemberStatus.MEMBER: "👤 عضو",
        ChatMemberStatus.RESTRICTED: "🔇 مقيد",
        ChatMemberStatus.LEFT: "🚪 غادر",
        ChatMemberStatus.BANNED: "🚫 محظور"
    }
    
    status = status_emoji.get(member.status, "❓ غير معروف")
    warn_count = db.get_warning_count(chat.id, user.id)
    
    text = f"""👤 **معلومات المستخدم**

🆔 المعرف: `{user.id}`
📝 الاسم: {user.first_name}
🔤 اسم المستخدم: @{user.username if user.username else 'غير متوفر'}
📌 الحالة: {status}
⚠️ التحذيرات: {warn_count}/{WARN_LIMIT}"""
    
    if user.is_bot:
        text += "\n🤖 بوت: نعم"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# إحصائيات المجموعة
# ═══════════════════════════════════════════════════════════════

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات المجموعة"""
    chat = update.effective_chat
    stats = db.get_stats(chat.id)
    member_count = await chat.get_member_count()
    
    text = f"""📊 **إحصائيات المجموعة**

👥 الأعضاء: {member_count}
💬 الرسائل: {stats.get('total_messages', 0)}
✅ الانضمامات: {stats.get('total_joins', 0)}
❌ المغادرات: {stats.get('total_leaves', 0)}
🚫 الحظر: {stats.get('total_bans', 0)}
🔇 الكتم: {stats.get('total_mutes', 0)}
⚠️ التحذيرات: {stats.get('total_warns', 0)}
🗑️ الرسائل المحذوفة: {stats.get('total_deleted', 0)}"""
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# قائمة المشرفين
# ═══════════════════════════════════════════════════════════════

async def admins_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة المشرفين"""
    admins = await update.effective_chat.get_administrators()
    text = "👥 **قائمة المشرفين:**\n\n"
    
    for i, admin in enumerate(admins, 1):
        user = admin.user
        status = "👑" if admin.status == ChatMemberStatus.OWNER else "⭐"
        name = user.full_name
        text += f"{i}. {status} {name}"
        if user.username:
            text += f" (@{user.username})"
        text += "\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════════════════════════════════════════════════════
# نظام البلاغات
# ═══════════════════════════════════════════════════════════════

async def report_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """الإبلاغ عن مستخدم"""
    if not update.message.reply_to_message:
        return
    
    settings = db.get_settings(update.effective_chat.id)
    if not settings.get('report_enabled', 1):
        return
    
    target = update.message.reply_to_message.from_user
    reporter = update.effective_user
    
    if target.id == context.bot.id:
        return
    
    admins = await update.effective_chat.get_administrators()
    admin_mentions = []
    for admin in admins:
        if not admin.user.is_bot:
            admin_mentions.append(mention_user(admin.user.id, admin.user.first_name))
    
    mention = mention_user(target.id, target.full_name)
    reporter_mention = mention_user(reporter.id, reporter.full_name)
    
    text = f"🚨 بلاغ من {reporter_mention} ضد {mention}!"
    if admin_mentions:
        text += f"\n\n👥 المشرفون: {' '.join(admin_mentions[:5])}"
    
    await update.message.reply_text(text, parse_mode="HTML")
    db.log_action(update.effective_chat.id, reporter.id, "report", target.id)

# ═══════════════════════════════════════════════════════════════
# نظام الإعلانات
# ═══════════════════════════════════════════════════════════════

@admin_only
async def announce_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعلان للجميع"""
    if not context.args:
        await update.message.reply_text("⛔ اكتب نص الإعلان!")
        return
    
    text = " ".join(context.args)
    admin_mention = mention_user(update.effective_user.id, update.effective_user.full_name)
    
    announce_text = f"""📢 **إعلان من الإدارة**

{text}

👤 بواسطة: {admin_mention}"""
    
    await update.message.reply_text(announce_text, parse_mode="HTML")
    db.log_action(update.effective_chat.id, update.effective_user.id, "announce", reason=text)

# ═══════════════════════════════════════════════════════════════
# سجل الإجراءات
# ═══════════════════════════════════════════════════════════════

@admin_only
async def log_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض سجل الإجراءات"""
    logs = db.get_action_log(update.effective_chat.id, limit=10)
    
    if logs:
        text = "📋 **سجل الإجراءات الأخيرة:**\n\n"
        for log_entry in logs:
            action = log_entry.get('action', '')
            reason = log_entry.get('reason', '')
            date = log_entry.get('created_at', '')[:16]
            text += f"• [{date}] {action}"
            if reason:
                text += f" - {reason}"
            text += "\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text("📋 لا توجد إجراءات مسجلة!")

# ═══════════════════════════════════════════════════════════════
# رسائل الأزرار التفاعلية
# ═══════════════════════════════════════════════════════════════

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة أزرار الكالباك"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "help":
        await query.message.edit_text(
            "📖 استخدم /help لرؤية جميع الأوامر المتاحة!\n\n"
            "أو اختر من الأزرار أدناه:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛡️ الإشراف", callback_data="help_admin"),
                 InlineKeyboardButton("📝 الملاحظات", callback_data="help_notes")],
                [InlineKeyboardButton("🔒 الأقفال", callback_data="help_locks"),
                 InlineKeyboardButton("⚙️ الإعدادات", callback_data="help_settings")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
            ])
        )
    
    elif data == "help_admin":
        await query.message.edit_text(
            "🛡️ **أوامر الإشراف:**\n\n"
            "• /ban [سبب] - حظر\n"
            "• /unban - إلغاء حظر\n"
            "• /mute - كتم\n"
            "• /unmute - إلغاء كتم\n"
            "• /tmute [وقت] - كتم مؤقت\n"
            "• /kick - طرد\n"
            "• /warn [سبب] - تحذير\n"
            "• /unwarn - إزالة تحذيرات\n"
            "• /del - حذف رسالة\n"
            "• /purge [عدد] - حذف عدة رسائل\n"
            "• /pin - تثبيت\n"
            "• /unpin - إلغاء تثبيت",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="help")]
            ])
        )
    
    elif data == "help_notes":
        await query.message.edit_text(
            "📝 **أوامر الملاحظات:**\n\n"
            "• /save [اسم] [محتوى] - حفظ\n"
            "• /get [اسم] - استرجاع\n"
            "• /notes - عرض الكل\n"
            "• /delnote [اسم] - حذف\n\n"
            "🔍 **أوامر الفلاتر:**\n\n"
            "• /filter [كلمة] [رد] - إضافة\n"
            "• /stop [كلمة] - حذف\n"
            "• /filters - عرض الكل",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="help")]
            ])
        )
    
    elif data == "help_locks":
        types_text = "\n".join([f"• {v} (`{k}`)" for k, v in LOCK_TYPES.items()])
        await query.message.edit_text(
            f"🔒 **أوامر الأقفال:**\n\n"
            f"• /lock [نوع] - قفل\n"
            f"• /unlock [نوع] - فتح\n"
            f"• /locks - عرض الأقفال\n"
            f"• /lockall - قفل الكل\n"
            f"• /unlockall - فتح الكل\n\n"
            f"**الأنواع المتاحة:**\n{types_text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="help")]
            ])
        )
    
    elif data == "help_settings":
        await query.message.edit_text(
            "⚙️ **أوامر الإعدادات:**\n\n"
            "• /setwelcome [نص] - تعيين ترحيب\n"
            "• /resetwelcome - إعادة الترحيب\n"
            "• /antispam [تشغيل/إيقاف]\n"
            "• /antiflood [تشغيل/إيقاف]\n"
            "• /antilink [تشغيل/إيقاف]\n"
            "• /maintenance - وضع الصيانة\n"
            "• /setlog [معرف] - قناة السجلات\n"
            "• /addbadword [كلمة] - كلمة محظورة\n"
            "• /delbadword [كلمة] - حذف كلمة\n"
            "• /badwords - عرض الكلمات",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="help")]
            ])
        )
    
    elif data == "back":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 الأوامر", callback_data="help"),
             InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
            [InlineKeyboardButton("👤 المطور", url="https://t.me/masqsam3")]
        ])
        await query.message.edit_text(
            "🤖 **بوت إدارة المجموعات المتكامل v2.0**\n\nاختر من الأزرار أدناه 👇",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    
    elif data == "settings":
        settings = db.get_settings(update.effective_chat.id)
        text = f"""⚙️ **إعدادات المجموعة**

🛡️ حماية السبام: {'✅' if settings.get('anti_spam', 1) else '❌'}
🌊 حماية الفلود: {'✅' if settings.get('anti_flood', 1) else '❌'}
🔗 منع الروابط: {'✅' if settings.get('anti_link', 0) else '❌'}
🔤 فلتر الكلمات: {'✅' if settings.get('anti_badword', 1) else '❌'}
🔧 وضع الصيانة: {'✅' if settings.get('maintenance_mode', 0) else '❌'}
🚨 نظام البلاغات: {'✅' if settings.get('report_enabled', 1) else '❌'}"""
        
        await query.message.edit_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="back")]
            ])
        )

# ═══════════════════════════════════════════════════════════════
# معالجة الرسائل الواردة
# ═══════════════════════════════════════════════════════════════

async def handle_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ترحيب بالأعضاء الجدد"""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # البوت أضيف للمجموعة
            await update.effective_chat.send_message(
                "🤖 شكراً لإضافتي! أنا بوت إدارة المجموعات المتكامل v2.0\n\n"
                "📌 يرجى رفعي كمشرف لكي أتمكن من العمل بشكل صحيح.\n"
                "📖 أرسل /help لرؤية الأوامر المتاحة."
            )
            continue
        
        # ترحيب بالعضو الجديد
        settings = db.get_settings(update.effective_chat.id)
        welcome_data = settings.get("welcome_msg", "{}")
        try:
            welcome_json = json.loads(welcome_data)
            welcome_text = welcome_json.get("text", DEFAULT_WELCOME)
        except:
            welcome_text = DEFAULT_WELCOME
        
        chat_name = update.effective_chat.title or "المجموعة"
        member_count = await update.effective_chat.get_member_count()
        mention = mention_user(member.id, member.full_name)
        
        welcome_text = welcome_text.replace("{user}", mention)
        welcome_text = welcome_text.replace("{user_mention}", mention)
        welcome_text = welcome_text.replace("{chat}", chat_name)
        welcome_text = welcome_text.replace("{count}", str(member_count))
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 القوانين", callback_data="view_rules")]
        ])
        
        await update.effective_chat.send_message(
            welcome_text, parse_mode="HTML", reply_markup=keyboard
        )
        db.increment_stat(update.effective_chat.id, "total_joins")
    
    await send_log(update.effective_chat.id, f"✅ انضمام عضو جديد", context)

async def handle_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عند مغادرة عضو"""
    db.increment_stat(update.effective_chat.id, "total_leaves")
    await send_log(update.effective_chat.id, f"❌ مغادرة عضو", context)

async def handle_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة جميع الرسائل - حماية وفلاتر"""
    if not update.message or not update.effective_user:
        return
    
    chat = update.effective_chat
    user = update.effective_user
    settings = db.get_settings(chat.id)
    
    # تجاهل المشرفين
    if await is_admin(update):
        return
    
    # تجاهل البوتات
    if user.is_bot:
        return
    
    # تحديث الإحصائيات
    db.increment_stat(chat.id, "total_messages")
    
    # --- وضع الصيانة ---
    if settings.get("maintenance_mode", 0):
        try:
            await update.message.delete()
        except:
            pass
        return
    
    # --- حماية الفلود ---
    if settings.get("anti_flood", 1):
        max_msgs = settings.get("max_flood_msgs", 5)
        interval = settings.get("flood_interval", 5)
        if check_flood(chat.id, user.id, max_msgs, interval):
            try:
                await update.message.delete()
                permissions = ChatPermissions(can_send_messages=False)
                until = datetime.now() + timedelta(minutes=5)
                await chat.restrict_member(user.id, permissions, until_date=until)
                mention = mention_user(user.id, user.full_name)
                await chat.send_message(
                    f"🛡️ تم كتم {mention} لمدة 5 دقائق بسبب الفلود!",
                    parse_mode="HTML"
                )
                db.increment_stat(chat.id, "total_mutes")
                await send_log(chat.id, f"🌊 كتم تلقائي (فلود): {mention}", context)
                return
            except:
                pass
    
    # --- منع الروابط ---
    if settings.get("anti_link", 0):
        text = update.message.text or update.message.caption or ""
        if text and re.search(r'(https?://|t\.me/|@)', text, re.IGNORECASE):
            try:
                await update.message.delete()
                mention = mention_user(user.id, user.full_name)
                await chat.send_message(
                    f"🚫 الروابط ممنوعة يا {mention}!",
                    parse_mode="HTML"
                )
                return
            except:
                pass
    
    # --- فلتر الكلمات المسيئة ---
    if settings.get("anti_badword", 1):
        text = (update.message.text or update.message.caption or "").lower()
        badwords = db.get_badwords(chat.id)
        for word in badwords:
            if word in text:
                try:
                    await update.message.delete()
                    mention = mention_user(user.id, user.full_name)
                    await chat.send_message(
                        f"🚫 كلمة محظورة! {mention}",
                        parse_mode="HTML"
                    )
                    return
                except:
                    pass
    
    # --- نظام الأقفال ---
    locks = db.get_all_locks(chat.id)
    if locks:
        msg = update.message
        lock_checks = {
            "photos": msg.photo,
            "videos": msg.video,
            "stickers": msg.sticker,
            "animations": msg.animation,
            "voice": msg.voice,
            "audio": msg.audio,
            "documents": msg.document,
            "links": bool(msg.text and re.search(r'https?://', msg.text)),
            "forward": msg.forward_date is not None,
            "polls": msg.poll,
            "contacts": msg.contact,
            "location": msg.location,
            "venue": msg.venue,
            "text": msg.text and not msg.entities,
            "inline": bool(msg.via_bot),
        }
        
        for lock_type in locks:
            if lock_type in lock_checks and lock_checks[lock_type]:
                try:
                    await update.message.delete()
                except:
                    pass
                return
    
    # --- نظام الفلاتر (رد تلقائي) ---
    text = update.message.text or ""
    if text:
        words = text.lower().split()
        for word in words:
            reply = db.get_filter(chat.id, word)
            if reply:
                await update.message.reply_text(reply)
                break
    
    # --- نظام البلاغات (@admin) ---
    if settings.get("report_enabled", 1):
        if text and "@admin" in text.lower():
            admins = await chat.get_administrators()
            admin_mentions = []
            for admin in admins:
                if not admin.user.is_bot:
                    admin_mentions.append(mention_user(admin.user.id, admin.user.first_name))
            
            mention = mention_user(user.id, user.full_name)
            report_text = f"🚨 بلاغ من {mention}!"
            if admin_mentions:
                report_text += f"\n\n👥 {' '.join(admin_mentions[:5])}"
            
            await chat.send_message(report_text, parse_mode="HTML")
            db.log_action(chat.id, user.id, "report")

# ═══════════════════════════════════════════════════════════════
# فحص الكتم المؤقت
# ═══════════════════════════════════════════════════════════════

async def check_temp_mutes(context: ContextTypes.DEFAULT_TYPE):
    """فحص وإلغاء الكتم المؤقت المنتهي"""
    expired = db.get_expired_mutes()
    for mute in expired:
        try:
            permissions = ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
            await context.bot.restrict_member(
                mute['chat_id'], mute['user_id'], permissions
            )
            logger.info(f"Unmuted user {mute['user_id']} in chat {mute['chat_id']}")
        except Exception as e:
            logger.error(f"Error unmuting: {e}")

# ═══════════════════════════════════════════════════════════════
# معالجة عرض القوانين من الزر
# ═══════════════════════════════════════════════════════════════

async def view_rules_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض القوانين من زر الترحيب"""
    query = update.callback_query
    await query.answer()
    
    settings = db.get_settings(update.effective_chat.id)
    rules = settings.get("rules", "")
    if rules:
        await query.message.reply_text(f"📋 **قوانين المجموعة:**\n\n{rules}", parse_mode="Markdown")
    else:
        await query.message.reply_text("📋 لم يتم تعيين قوانين بعد!")

# ═══════════════════════════════════════════════════════════════
# الدالة الرئيسية
# ═══════════════════════════════════════════════════════════════

def main():
    # تشغيل خادم Flask في خيط منفصل
    threading.Thread(target=run_flask, daemon=True).start()
    
    # إنشاء التطبيق
    app = Application.builder().token(TOKEN).build()
    
    # ═══ تسجيل الأوامر ═══
    
    # أوامر أساسية
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    
    # أوامر الإشراف
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("mute", mute_cmd))
    app.add_handler(CommandHandler("unmute", unmute_cmd))
    app.add_handler(CommandHandler("tmute", temp_mute_cmd))
    app.add_handler(CommandHandler("kick", kick_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("unwarn", unwarn_cmd))
    app.add_handler(CommandHandler("del", del_cmd))
    app.add_handler(CommandHandler("purge", purge_cmd))
    
    # أوامر التثبيت
    app.add_handler(CommandHandler("pin", pin_cmd))
    app.add_handler(CommandHandler("unpin", unpin_cmd))
    
    # أوامر القوانين
    app.add_handler(CommandHandler("setrules", setrules_cmd))
    app.add_handler(CommandHandler("rules", rules_cmd))
    app.add_handler(CommandHandler("clearrules", clearrules_cmd))
    
    # أوامر الملاحظات
    app.add_handler(CommandHandler("save", save_note_cmd))
    app.add_handler(CommandHandler("get", get_note_cmd))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(CommandHandler("delnote", delnote_cmd))
    
    # أوامر الفلاتر
    app.add_handler(CommandHandler("filter", filter_cmd))
    app.add_handler(CommandHandler("stop", stop_filter_cmd))
    app.add_handler(CommandHandler("filters", filters_cmd))
    
    # أوامر الأقفال
    app.add_handler(CommandHandler("lock", lock_cmd))
    app.add_handler(CommandHandler("unlock", unlock_cmd))
    app.add_handler(CommandHandler("locks", locks_cmd))
    app.add_handler(CommandHandler("lockall", lockall_cmd))
    app.add_handler(CommandHandler("unlockall", unlockall_cmd))
    
    # أوامر الكلمات المسيئة
    app.add_handler(CommandHandler("addbadword", addbadword_cmd))
    app.add_handler(CommandHandler("delbadword", delbadword_cmd))
    app.add_handler(CommandHandler("badwords", badwords_cmd))
    
    # أوامر الإعدادات
    app.add_handler(CommandHandler("setwelcome", setwelcome_cmd))
    app.add_handler(CommandHandler("resetwelcome", resetwelcome_cmd))
    app.add_handler(CommandHandler("antispam", antispam_cmd))
    app.add_handler(CommandHandler("antiflood", antiflood_cmd))
    app.add_handler(CommandHandler("antilink", antilink_cmd))
    app.add_handler(CommandHandler("maintenance", maintenance_cmd))
    app.add_handler(CommandHandler("setlog", setlog_cmd))
    
    # أوامر المعلومات
    app.add_handler(CommandHandler("info", info_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("admins", admins_cmd))
    app.add_handler(CommandHandler("log", log_cmd))
    
    # أوامر أخرى
    app.add_handler(CommandHandler("announce", announce_cmd))
    app.add_handler(CommandHandler("report", report_cmd))
    
    # معالجة الأزرار التفاعلية
    app.add_handler(CallbackQueryHandler(callback_handler, pattern=r'^(help|help_|back|settings|view_rules)'))
    app.add_handler(CallbackQueryHandler(view_rules_callback, pattern=r'^view_rules$'))
    app.add_handler(CallbackQueryHandler(unwarn_callback, pattern=r'^unwarn_'))
    
    # معالجة الرسائل
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_members))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handle_left_member))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_messages))
    
    # فحص الكتم المؤقت كل دقيقة
    app.job_queue.run_repeating(check_temp_mutes, interval=60, first=10)
    
    logger.info("🤖 بوت إدارة المجموعات المتكامل v2.0 بدأ العمل!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
