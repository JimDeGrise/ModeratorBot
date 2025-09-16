"""
Main module for ModeratorBot.
Telegram bot for chat moderation with anti-flood, link filtering, and captcha.
"""

import asyncio
import logging
import random
from typing import List, Optional

from telegram import (
    CallbackQuery, Chat, InlineKeyboardButton, InlineKeyboardMarkup, 
    Message, Update, User
)
from telegram.constants import ChatType, ParseMode
from telegram.ext import (
    Application, CallbackQueryHandler, ChatMemberHandler, CommandHandler, 
    ContextTypes, MessageHandler, filters
)

from config import get_config
from database import db
from utils import (
    check_flood, contains_banned_words, contains_links, format_user_mention,
    has_disallowed_links, is_admin, is_command_message, kick_user, mute_user
)

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration
config = get_config()


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    try:
        if update.effective_chat.type != ChatType.PRIVATE:
            return
        
        user = update.effective_user
        if user.id not in config.ADMIN_IDS:
            await update.message.reply_text(
                "Этот бот предназначен для модерации групп.",
                disable_notification=True
            )
            return
        
        welcome_text = (
            "🤖 *ModeratorBot*\n\n"
            "Доступные команды для администраторов:\n"
            "/rules - показать правила\n"
            "/warn - выдать предупреждение\n"
            "/unwarn - снять предупреждения\n"
            "/mute - заглушить пользователя\n"
            "/kick - исключить пользователя\n"
            "/warnings - показать предупреждения пользователя"
        )
        
        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True
        )
    except Exception as e:
        logger.exception(f"Error in start command: {e}")


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /rules command."""
    try:
        rules_text = f"📋 *Правила сообщества*\n\n{config.RULES}"
        await update.message.reply_text(
            rules_text,
            parse_mode=ParseMode.MARKDOWN,
            disable_notification=True
        )
    except Exception as e:
        logger.exception(f"Error in rules command: {e}")


async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /warn command."""
    try:
        if not await is_admin(update.effective_user, update.effective_chat, context):
            return
        
        # Check if command is a reply to another message
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "Ответьте на сообщение пользователя, которого хотите предупредить.",
                disable_notification=True
            )
            return
        
        target_user = update.message.reply_to_message.from_user
        reason = " ".join(context.args) if context.args else "Нарушение правил"
        
        # Add warning to database
        warning_count = await db.add_warning(
            target_user.id, 
            update.effective_chat.id, 
            reason
        )
        
        warning_text = (
            f"⚠️ Предупреждение для {format_user_mention(target_user)}\n"
            f"Причина: {reason}\n"
            f"Предупреждений: {warning_count}/{config.WARNS_TO_PUNISH}"
        )
        
        await update.message.reply_text(warning_text, disable_notification=True)
        
        # Auto-mute if reached warning limit
        if warning_count >= config.WARNS_TO_PUNISH:
            success = await mute_user(
                target_user.id,
                update.effective_chat.id,
                config.AUTO_MUTE_HOURS,
                context,
                f"Достигнут лимит предупреждений ({config.WARNS_TO_PUNISH})"
            )
            
            if success:
                await update.message.reply_text(
                    f"🔇 {format_user_mention(target_user)} заглушен на {config.AUTO_MUTE_HOURS} часов "
                    f"за достижение лимита предупреждений.",
                    disable_notification=True
                )
    except Exception as e:
        logger.exception(f"Error in warn command: {e}")


async def unwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unwarn command."""
    try:
        if not await is_admin(update.effective_user, update.effective_chat, context):
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "Ответьте на сообщение пользователя, у которого хотите снять предупреждения.",
                disable_notification=True
            )
            return
        
        target_user = update.message.reply_to_message.from_user
        await db.clear_warnings(target_user.id, update.effective_chat.id)
        
        await update.message.reply_text(
            f"✅ Предупреждения сняты с {format_user_mention(target_user)}",
            disable_notification=True
        )
    except Exception as e:
        logger.exception(f"Error in unwarn command: {e}")


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /mute command."""
    try:
        if not await is_admin(update.effective_user, update.effective_chat, context):
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "Ответьте на сообщение пользователя, которого хотите заглушить.",
                disable_notification=True
            )
            return
        
        target_user = update.message.reply_to_message.from_user
        duration = int(context.args[0]) if context.args and context.args[0].isdigit() else 24
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Нарушение правил"
        
        success = await mute_user(target_user.id, update.effective_chat.id, duration, context, reason)
        
        if success:
            await update.message.reply_text(
                f"🔇 {format_user_mention(target_user)} заглушен на {duration} часов.\n"
                f"Причина: {reason}",
                disable_notification=True
            )
        else:
            await update.message.reply_text(
                "Не удалось заглушить пользователя. Проверьте права бота.",
                disable_notification=True
            )
    except Exception as e:
        logger.exception(f"Error in mute command: {e}")


async def kick_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /kick command."""
    try:
        if not await is_admin(update.effective_user, update.effective_chat, context):
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "Ответьте на сообщение пользователя, которого хотите исключить.",
                disable_notification=True
            )
            return
        
        target_user = update.message.reply_to_message.from_user
        reason = " ".join(context.args) if context.args else "Нарушение правил"
        
        success = await kick_user(target_user.id, update.effective_chat.id, context, reason)
        
        if success:
            await update.message.reply_text(
                f"👢 {format_user_mention(target_user)} исключен из чата.\n"
                f"Причина: {reason}",
                disable_notification=True
            )
        else:
            await update.message.reply_text(
                "Не удалось исключить пользователя. Проверьте права бота.",
                disable_notification=True
            )
    except Exception as e:
        logger.exception(f"Error in kick command: {e}")


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /warnings command."""
    try:
        if not await is_admin(update.effective_user, update.effective_chat, context):
            return
        
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "Ответьте на сообщение пользователя, чтобы посмотреть его предупреждения.",
                disable_notification=True
            )
            return
        
        target_user = update.message.reply_to_message.from_user
        warning_count = await db.get_warning_count(target_user.id, update.effective_chat.id)
        
        await update.message.reply_text(
            f"📊 {format_user_mention(target_user)} имеет {warning_count}/{config.WARNS_TO_PUNISH} предупреждений",
            disable_notification=True
        )
    except Exception as e:
        logger.exception(f"Error in warnings command: {e}")


async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new chat members with captcha."""
    try:
        for new_member in update.message.new_chat_members:
            if new_member.is_bot:
                continue
            
            # Add to captcha pending
            await db.add_captcha_pending(new_member.id, update.effective_chat.id)
            
            # Generate simple math captcha
            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            answer = num1 + num2
            
            # Store answer in context for verification
            context.bot_data[f"captcha_{new_member.id}"] = answer
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"{num1} + {num2} = ?", callback_data=f"captcha_question_{new_member.id}")],
                [
                    InlineKeyboardButton(str(answer - 1), callback_data=f"captcha_wrong_{new_member.id}"),
                    InlineKeyboardButton(str(answer), callback_data=f"captcha_correct_{new_member.id}"),
                    InlineKeyboardButton(str(answer + 1), callback_data=f"captcha_wrong_{new_member.id}")
                ]
            ])
            
            # Mute user until captcha is solved
            await mute_user(
                new_member.id,
                update.effective_chat.id,
                config.CAPTCHA_TIMEOUT_SECONDS // 3600 + 1,  # Convert to hours
                context,
                "Проверка капчи"
            )
            
            welcome_text = (
                f"👋 Добро пожаловать, {format_user_mention(new_member)}!\n\n"
                f"Для подтверждения того, что вы не бот, решите простой пример:\n"
                f"У вас есть {config.CAPTCHA_TIMEOUT_SECONDS} секунд."
            )
            
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=welcome_text,
                reply_markup=keyboard,
                disable_notification=True
            )
    except Exception as e:
        logger.exception(f"Error handling new member: {e}")


async def handle_captcha_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle captcha button callbacks."""
    try:
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith("captcha_correct_"):
            user_id = int(query.data.split("_")[2])
            
            if query.from_user.id != user_id:
                await query.answer("Это не ваша капча!", show_alert=True)
                return
            
            # Remove from captcha pending
            await db.remove_captcha_pending(user_id)
            
            # Unmute user
            await context.bot.restrict_chat_member(
                chat_id=query.message.chat_id,
                user_id=user_id,
                permissions={
                    'can_send_messages': True,
                    'can_send_media_messages': True,
                    'can_send_polls': True,
                    'can_send_other_messages': True,
                    'can_add_web_page_previews': True,
                    'can_change_info': False,
                    'can_invite_users': False,
                    'can_pin_messages': False
                }
            )
            
            await query.edit_message_text(
                f"✅ {format_user_mention(query.from_user)} успешно прошел проверку!",
                disable_notification=True
            )
            
        elif query.data.startswith("captcha_wrong_"):
            user_id = int(query.data.split("_")[2])
            
            if query.from_user.id != user_id:
                await query.answer("Это не ваша капча!", show_alert=True)
                return
            
            await query.answer("Неправильный ответ! Попробуйте еще раз.", show_alert=True)
            
    except Exception as e:
        logger.exception(f"Error handling captcha callback: {e}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle regular messages for moderation."""
    try:
        message = update.message
        user = update.effective_user
        chat = update.effective_chat
        
        # Skip if no message or from admin
        if not message or not message.text or await is_admin(user, chat, context):
            return
        
        # Skip command messages (unified check)
        if is_command_message(message):
            return
        
        # Check if user has pending captcha
        if await db.is_captcha_pending(user.id):
            await message.delete()
            return
        
        # Anti-flood check
        if check_flood(user.id):
            success = await mute_user(
                user.id,
                chat.id,
                1,  # 1 hour mute for flooding
                context,
                "Флуд сообщениями"
            )
            
            if success:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🔇 {format_user_mention(user)} заглушен на 1 час за флуд.",
                    disable_notification=True
                )
            
            await message.delete()
            return
        
        # Check for banned words
        if contains_banned_words(message.text):
            await message.delete()
            
            warning_count = await db.add_warning(
                user.id,
                chat.id,
                "Использование запрещенных слов"
            )
            
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"❌ {format_user_mention(user)}, сообщение удалено за использование запрещенных слов.\n"
                     f"Предупреждений: {warning_count}/{config.WARNS_TO_PUNISH}",
                disable_notification=True
            )
            
            # Auto-mute if reached warning limit
            if warning_count >= config.WARNS_TO_PUNISH:
                await mute_user(
                    user.id,
                    chat.id,
                    config.AUTO_MUTE_HOURS,
                    context,
                    f"Достигнут лимит предупреждений ({config.WARNS_TO_PUNISH})"
                )
            
            return
        
        # Check for disallowed links
        if contains_links(message.text) and has_disallowed_links(message.text):
            await message.delete()
            
            warning_count = await db.add_warning(
                user.id,
                chat.id,
                "Размещение запрещенных ссылок"
            )
            
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"🔗 {format_user_mention(user)}, ссылка удалена. Разрешены только ссылки на: {', '.join(config.ALLOWED_DOMAINS)}\n"
                     f"Предупреждений: {warning_count}/{config.WARNS_TO_PUNISH}",
                disable_notification=True
            )
            
            # Auto-mute if reached warning limit
            if warning_count >= config.WARNS_TO_PUNISH:
                await mute_user(
                    user.id,
                    chat.id,
                    config.AUTO_MUTE_HOURS,
                    context,
                    f"Достигнут лимит предупреждений ({config.WARNS_TO_PUNISH})"
                )
            
            return
            
    except Exception as e:
        logger.exception(f"Error handling message: {e}")


async def cleanup_task(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic cleanup task."""
    try:
        await db.cleanup_old_captcha()
        logger.info("Cleanup task completed")
    except Exception as e:
        logger.exception(f"Error in cleanup task: {e}")


def main() -> None:
    """Run the bot."""
    try:
        # Create application
        application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Initialize database
        asyncio.run(db.init_db())
        
        # Add handlers
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("rules", rules_command))
        application.add_handler(CommandHandler("warn", warn_command))
        application.add_handler(CommandHandler("unwarn", unwarn_command))
        application.add_handler(CommandHandler("mute", mute_command))
        application.add_handler(CommandHandler("kick", kick_command))
        application.add_handler(CommandHandler("warnings", warnings_command))
        
        # New member handler
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))
        
        # Captcha callback handler
        application.add_handler(CallbackQueryHandler(handle_captcha_callback, pattern="^captcha_"))
        
        # Message handler for moderation
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        # Add cleanup job (every 10 minutes)
        job_queue = application.job_queue
        job_queue.run_repeating(cleanup_task, interval=600, first=10)
        
        # Start the bot
        logger.info("Starting ModeratorBot...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.exception(f"Critical error in main: {e}")


if __name__ == "__main__":
    main()