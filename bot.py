import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد السجلات
logging.basicConfig(format="%(asctime )s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- الإعدادات ---
TOKEN = os.environ.get("TOKEN", "ضع_التوكن_هنا_إذا_لم_تستخدم_متغيرات_البيئة")
WELCOME_MESSAGE = "مرحباً بك يا {user_mention} في مجموعتنا! يرجى قراءة القواعد."
GOODBYE_MESSAGE = "وداعاً {user_mention}! نأمل أن نراك مرة أخرى."
WARN_LIMIT = 3
user_warnings = {}

# --- خادم وهمي لإرضاء منصة Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

# --- وظائف مساعدة ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_chat.type in ["group", "supergroup"]: return False
    admins = await update.effective_chat.get_administrators()
    return update.effective_user.id in [admin.user.id for admin in admins]

async def get_mention(user):
    return f"<a href='tg://user?id={user.id}'>{user.full_name}</a>"

# --- الأوامر ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mention = await get_mention(update.effective_user)
    await update.message.reply_html(f"أهلاً بك يا {mention}! أنا بوت إدارة المجموعات. أرسل /help لرؤية الأوامر.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛡️ **أوامر الإشراف:**\n"
        "• /ban - حظر (بالرد)\n"
        "• /mute [دقائق] - كتم (بالرد)\n"
        "• /warn - تحذير (بالرد)\n"
        "• /del - حذف رسالة (بالرد)\n"
        "• /setwelcome - تعيين ترحيب"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.id == context.bot.id: continue
        mention = await get_mention(m)
        await update.effective_chat.send_message(WELCOME_MESSAGE.replace("{user_mention}", mention), parse_mode="HTML")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context): return
    if not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    if cid not in user_warnings: user_warnings[cid] = {}
    user_warnings[cid][target.id] = user_warnings[cid].get(target.id, 0) + 1
    if user_warnings[cid][target.id] >= WARN_LIMIT:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(f"🚫 تم حظر {target.full_name} لتجاوز التحذيرات.")
    else:
        await update.message.reply_text(f"⚠️ تحذير {user_warnings[cid][target.id]}/{WARN_LIMIT} لـ {target.full_name}.")

def main():
    # تشغيل الخادم الوهمي في خلفية الكود
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    
    logger.info("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
