import logging
import os
from telegram import Update, ForceReply, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading

# Enable logging
logging.basicConfig(
    format="%(asctime )s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx" ).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- Configuration ---
TOKEN = os.environ.get("TOKEN", "8651632152:AAHMLhhLpG4m6Wh9WHvaqY0q54_B0L8xF4U")
WELCOME_MESSAGE = "مرحباً بك يا {user_mention} في مجموعتنا! يرجى قراءة القواعد."
GOODBYE_MESSAGE = "وداعاً {user_mention}! نأمل أن نراك مرة أخرى."
WARN_LIMIT = 3

# Dictionary to store warnings
user_warnings = {}

# --- Health Check Server for Render ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Starting health check server on port {port}")
    server.serve_forever()

# --- Helper Functions ---
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    if not update.effective_chat.type in ["group", "supergroup"]:
        return False
    chat_admins = await update.effective_chat.get_administrators()
    admin_ids = [admin.user.id for admin in chat_admins]
    return user_id in admin_ids

async def get_user_mention(user_id: int, user_name: str) -> str:
    return f"<a href='tg://user?id={user_id}'>{user_name}</a>"

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    mention = await get_user_mention(user.id, user.full_name)
    await update.message.reply_html(
        f"أهلاً بك يا {mention}! أنا بوت إدارة المجموعات. استخدم /help لمعرفة الأوامر المتاحة."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "🛡️ **أوامر بوت إدارة المجموعات:**\n"
        "/start - بدء البوت والحصول على رسالة ترحيب.\n"
        "/help - عرض قائمة الأوامر المتاحة.\n\n"
        "👮 **أوامر الإشراف (للمشرفين فقط):**\n"
        "• /ban - حظر المستخدم (بالرد على رسالته).\n"
        "• /kick - طرد المستخدم (بالرد على رسالته).\n"
        "• /mute [دقائق] - كتم المستخدم (بالرد على رسالته).\n"
        "• /unmute - إلغاء كتم المستخدم (بالرد على رسالته).\n"
        "• /warn - تحذير المستخدم (بالرد على رسالته).\n"
        "• /unwarn - إزالة تحذير (بالرد على رسالته).\n"
        "• /del - حذف الرسالة (بالرد عليها).\n\n"
        "⚙️ **إعدادات:**\n"
        "• /setwelcome [النص] - تعيين رسالة ترحيب (استخدم {user_mention} للاسم)."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        if member.id == context.bot.id: continue
        user_mention = await get_user_mention(member.id, member.full_name)
        await update.effective_chat.send_message(
            WELCOME_MESSAGE.replace("{user_mention}", user_mention), parse_mode="HTML"
        )

async def left_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.left_chat_member
    if user.id == context.bot.id: return
    user_mention = await get_user_mention(user.id, user.full_name)
    await update.effective_chat.send_message(
        GOODBYE_MESSAGE.replace("{user_mention}", user_mention), parse_mode="HTML"
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم.")
        return
    target_user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(target_user.id)
        await update.message.reply_text(f"✅ تم حظر {target_user.full_name}.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id): return
    if not update.message.reply_to_message: return
    target_user = update.message.reply_to_message.from_user
    duration = 60
    if context.args and context.args[0].isdigit():
        duration = int(context.args[0])
    import time
    until_date = int(time.time() + duration * 60)
    try:
        await update.effective_chat.restrict_member(
            target_user.id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await update.message.reply_text(f"🔇 تم كتم {target_user.full_name} لمدة {duration} دقيقة.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id): return
    if not update.message.reply_to_message: return
    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    if chat_id not in user_warnings: user_warnings[chat_id] = {}
    user_warnings[chat_id][target_user.id] = user_warnings[chat_id].get(target_user.id, 0) + 1
    count = user_warnings[chat_id][target_user.id]
    if count >= WARN_LIMIT:
        await update.effective_chat.ban_member(target_user.id)
        await update.message.reply_text(f"🚫 {target_user.full_name} تجاوز حد التحذيرات وتم حظره.")
        user_warnings[chat_id][target_user.id] = 0
    else:
        await update.message.reply_text(f"⚠️ تحذير لـ {target_user.full_name} ({count}/{WARN_LIMIT}).")

async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id): return
    if update.message.reply_to_message:
        await update.message.reply_to_message.delete()
        await update.message.delete()

async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id): return
    if not context.args:
        await update.message.reply_text("مثال: /setwelcome أهلاً بك {user_mention}!")
        return
    global WELCOME_MESSAGE
    WELCOME_MESSAGE = " ".join(context.args)
    await update.message.reply_text("✅ تم تحديث رسالة الترحيب.")

def main() -> None:
    # Start Health Check Server in a separate thread
    threading.Thread(target=run_health_check_server, daemon=True).start()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("del", delete_message))
    application.add_handler(CommandHandler("setwelcome", set_welcome))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_member))

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
