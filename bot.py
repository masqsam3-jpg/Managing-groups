
import logging
from telegram import Update, ForceReply
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
# set higher logging level for httpx to avoid all GET and POST requests being logged
logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Replace with your bot's token
TOKEN = "8651632152:AAHMLhhLpG4m6Wh9WHvaqY0q54_B0L8xF4U"

# --- Global Configuration (can be moved to a config file later) ---
WELCOME_MESSAGE = "مرحباً بك يا {user_mention} في مجموعتنا! يرجى قراءة القواعد."
GOODBYE_MESSAGE = "وداعاً {user_mention}! نأمل أن نراك مرة أخرى."
WARN_LIMIT = 3

# Dictionary to store warnings for users in groups: {group_id: {user_id: warn_count}}
user_warnings = {}

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
    await update.message.reply_html(
        f"أهلاً بك يا {await get_user_mention(user.id, user.full_name)}! أنا بوت إدارة المجموعات. استخدم /help لمعرفة الأوامر المتاحة."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "أوامر بوت إدارة المجموعات:\n"
        "/start - بدء البوت والحصول على رسالة ترحيب.\n"
        "/help - عرض قائمة الأوامر المتاحة.\n"
        "\n"
        "أوامر الإشراف (للمشرفين فقط):\n"
        "/ban <الرد على رسالة المستخدم> - حظر المستخدم من المجموعة.\n"
        "/kick <الرد على رسالة المستخدم> - طرد المستخدم من المجموعة.\n"
        "/mute <الرد على رسالة المستخدم> [مدة بالدقائق] - كتم المستخدم. المدة اختيارية.\n"
        "/unmute <الرد على رسالة المستخدم> - إلغاء كتم المستخدم.\n"
        "/warn <الرد على رسالة المستخدم> - تحذير المستخدم. عند الوصول إلى {WARN_LIMIT} تحذيرات يتم طرده.\n"
        "/unwarn <الرد على رسالة المستخدم> - إزالة تحذير من المستخدم.\n"
        "/del <الرد على رسالة المستخدم> - حذف الرسالة التي تم الرد عليها.\n"
        "\n"
        "أوامر أخرى:\n"
        "/setwelcome <رسالة الترحيب> - تعيين رسالة ترحيب مخصصة (استخدم {user_mention} للاسم)."
    ).format(WARN_LIMIT=WARN_LIMIT)
    await update.message.reply_text(help_text)

async def new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    for member in update.message.new_chat_members:
        user_mention = await get_user_mention(member.id, member.full_name)
        await update.effective_chat.send_message(
            WELCOME_MESSAGE.format(user_mention=user_mention), parse_mode="HTML"
        )

async def left_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.left_chat_member
    user_mention = await get_user_mention(user.id, user.full_name)
    await update.effective_chat.send_message(
        GOODBYE_MESSAGE.format(user_mention=user_mention), parse_mode="HTML"
    )

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد حظره.")
        return

    target_user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.ban_member(target_user.id)
        await update.message.reply_text(f"تم حظر {await get_user_mention(target_user.id, target_user.full_name)} بنجاح.", parse_mode="HTML")
        logger.info(f"User {target_user.id} banned by {update.effective_user.id} in chat {update.effective_chat.id}")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء حظر المستخدم: {e}")

async def kick_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد طرده.")
        return

    target_user = update.message.reply_to_message.from_user
    try:
        await update.effective_chat.unban_member(target_user.id) # Unban first to allow kicking
        await update.effective_chat.ban_member(target_user.id, until_date=int(update.message.date.timestamp() + 30)) # Ban for 30 seconds to kick
        await update.message.reply_text(f"تم طرد {await get_user_mention(target_user.id, target_user.full_name)} بنجاح.", parse_mode="HTML")
        logger.info(f"User {target_user.id} kicked by {update.effective_user.id} in chat {update.effective_chat.id}")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء طرد المستخدم: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد كتمه.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id
    permissions = update.effective_chat.permissions

    # Default mute duration (e.g., 1 hour) or from arguments
    mute_duration_minutes = 60
    if context.args and context.args[0].isdigit():
        mute_duration_minutes = int(context.args[0])

    until_date = int(update.message.date.timestamp() + mute_duration_minutes * 60)

    try:
        await update.effective_chat.restrict_member(
            user_id=target_user.id,
            permissions=telegram.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        await update.message.reply_text(
            f"تم كتم {await get_user_mention(target_user.id, target_user.full_name)} لمدة {mute_duration_minutes} دقيقة.",
            parse_mode="HTML"
        )
        logger.info(f"User {target_user.id} muted by {update.effective_user.id} in chat {update.effective_chat.id} for {mute_duration_minutes} minutes")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء كتم المستخدم: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد إلغاء كتمه.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    try:
        # Restore default permissions (can send messages, etc.)
        await update.effective_chat.restrict_member(
            user_id=target_user.id,
            permissions=telegram.ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_change_info=False,
                can_invite_users=True,
                can_pin_messages=False,
                can_manage_topics=False
            ),
            until_date=0 # Remove restrictions immediately
        )
        await update.message.reply_text(f"تم إلغاء كتم {await get_user_mention(target_user.id, target_user.full_name)} بنجاح.", parse_mode="HTML")
        logger.info(f"User {target_user.id} unmuted by {update.effective_user.id} in chat {update.effective_chat.id}")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء إلغاء كتم المستخدم: {e}")

async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد تحذيره.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    if chat_id not in user_warnings:
        user_warnings[chat_id] = {}
    if target_user.id not in user_warnings[chat_id]:
        user_warnings[chat_id][target_user.id] = 0

    user_warnings[chat_id][target_user.id] += 1
    warnings_count = user_warnings[chat_id][target_user.id]

    if warnings_count >= WARN_LIMIT:
        try:
            await update.effective_chat.ban_member(target_user.id)
            await update.message.reply_text(
                f"تم تحذير {await get_user_mention(target_user.id, target_user.full_name)} للمرة {warnings_count}. لقد تجاوز حد التحذيرات وتم حظره.",
                parse_mode="HTML"
            )
            del user_warnings[chat_id][target_user.id] # Reset warnings after ban
            logger.info(f"User {target_user.id} banned after {warnings_count} warnings by {update.effective_user.id} in chat {update.effective_chat.id}")
        except Exception as e:
            await update.message.reply_text(f"حدث خطأ أثناء حظر المستخدم بعد التحذيرات: {e}")
    else:
        await update.message.reply_text(
            f"تم تحذير {await get_user_mention(target_user.id, target_user.full_name)} للمرة {warnings_count}/{WARN_LIMIT}.",
            parse_mode="HTML"
        )
        logger.info(f"User {target_user.id} warned by {update.effective_user.id} in chat {update.effective_chat.id}. Current warnings: {warnings_count}")

async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على رسالة المستخدم الذي تريد إزالة تحذيراته.")
        return

    target_user = update.message.reply_to_message.from_user
    chat_id = update.effective_chat.id

    if chat_id in user_warnings and target_user.id in user_warnings[chat_id]:
        user_warnings[chat_id][target_user.id] -= 1
        if user_warnings[chat_id][target_user.id] < 0:
            user_warnings[chat_id][target_user.id] = 0
        warnings_count = user_warnings[chat_id][target_user.id]
        await update.message.reply_text(
            f"تم إزالة تحذير من {await get_user_mention(target_user.id, target_user.full_name)}. التحذيرات الحالية: {warnings_count}.",
            parse_mode="HTML"
        )
        logger.info(f"User {target_user.id} unwarned by {update.effective_user.id} in chat {update.effective_chat.id}. Current warnings: {warnings_count}")
    else:
        await update.message.reply_text(f"المستخدم {await get_user_mention(target_user.id, target_user.full_name)} ليس لديه تحذيرات مسجلة.", parse_mode="HTML")

async def delete_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("يرجى الرد على الرسالة التي تريد حذفها.")
        return

    try:
        await update.message.reply_to_message.delete()
        await update.message.delete()
        logger.info(f"Message {update.message.reply_to_message.message_id} deleted by {update.effective_user.id} in chat {update.effective_chat.id}")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء حذف الرسالة: {e}")

async def set_welcome_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await is_admin(update, context, update.effective_user.id):
        await update.message.reply_text("عذراً، هذا الأمر مخصص للمشرفين فقط.")
        return

    if not context.args:
        await update.message.reply_text("يرجى تقديم رسالة الترحيب الجديدة. مثال: /setwelcome مرحباً بك يا {user_mention}!")
        return

    global WELCOME_MESSAGE
    WELCOME_MESSAGE = " ".join(context.args)
    await update.message.reply_text(f"تم تعيين رسالة الترحيب الجديدة بنجاح: {WELCOME_MESSAGE}")
    logger.info(f"Welcome message updated by {update.effective_user.id} in chat {update.effective_chat.id}")

# --- Anti-Spam (Basic example: delete messages containing specific words) ---
async def anti_spam_filter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_chat.type in ["group", "supergroup"]:
        message_text = update.message.text.lower() if update.message.text else ""
        spam_words = ["spam_word1", "spam_word2", "http://", "https://"]

        if any(word in message_text for word in spam_words):
            try:
                await update.message.delete()
                await update.effective_chat.send_message(
                    f"تم حذف رسالة من {await get_user_mention(update.effective_user.id, update.effective_user.full_name)} لاحتوائها على محتوى غير مرغوب فيه.",
                    parse_mode="HTML"
                )
                logger.info(f"Spam message from {update.effective_user.id} deleted in chat {update.effective_chat.id}")
            except Exception as e:
                logger.error(f"Error deleting spam message: {e}")

# --- Main function ---
def main() -> None:
    application = Application.builder().token(TOKEN).build()

    # Command Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("kick", kick_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    application.add_handler(CommandHandler("warn", warn_user))
    application.add_handler(CommandHandler("unwarn", unwarn_user))
    application.add_handler(CommandHandler("del", delete_message))
    application.add_handler(CommandHandler("setwelcome", set_welcome_message))

    # Message Handlers
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member))
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, left_member))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, anti_spam_filter)) # Anti-spam for text messages that are not commands

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import telegram # Import telegram here to avoid circular dependency with ChatPermissions
    main()
