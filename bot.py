import logging
import os
import threading
from flask import Flask
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# إعداد السجلات
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- الإعدادات ---
TOKEN = os.environ.get("TOKEN", "YOUR_BOT_TOKEN")
WELCOME_MESSAGE = "مرحباً بك يا {user_mention} في مجموعتنا!"
WARN_LIMIT = 3
user_warnings = {}

# --- خادم Flask لإرضاء Render ---
web_app = Flask(__name__)

@web_app.route('/')
def health_check():
    return "Bot is running!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- وظائف البوت ---
async def is_admin(update: Update):
    admins = await update.effective_chat.get_administrators()
    return update.effective_user.id in [admin.user.id for admin in admins]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ البوت يعمل بنجاح! أرسل /help لرؤية الأوامر.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🛡️ **أوامر الإشراف:**\n• /ban - حظر\n• /warn - تحذير\n• /del - حذف"
    await update.message.reply_text(text, parse_mode="Markdown")

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for m in update.message.new_chat_members:
        if m.id == context.bot.id: continue
        mention = f"<a href='tg://user?id={m.id}'>{m.full_name}</a>"
        await update.effective_chat.send_message(WELCOME_MESSAGE.replace("{user_mention}", mention), parse_mode="HTML")

async def warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update): return
    if not update.message.reply_to_message: return
    target = update.message.reply_to_message.from_user
    cid = update.effective_chat.id
    if cid not in user_warnings: user_warnings[cid] = {}
    user_warnings[cid][target.id] = user_warnings[cid].get(target.id, 0) + 1
    if user_warnings[cid][target.id] >= WARN_LIMIT:
        await update.effective_chat.ban_member(target.id)
        await update.message.reply_text(f"🚫 تم حظر {target.full_name}.")
    else:
        await update.message.reply_text(f"⚠️ تحذير {user_warnings[cid][target.id]}/{WARN_LIMIT} لـ {target.full_name}.")

def main():
    # تشغيل خادم Flask في خيط منفصل
    threading.Thread(target=run_flask, daemon=True).start()
    
    # تشغيل البوت
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("warn", warn))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome))
    
    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
