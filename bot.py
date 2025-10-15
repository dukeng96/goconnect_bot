from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
)
from config import logger, TOKEN, REQUIRED_ENV
from handler import cmd_start, cmd_help, cmd_cancel, on_message, on_callback

if __name__ == '__main__':
    if any(v in (None, '', 0) for v in REQUIRED_ENV):
        raise SystemExit('Thiếu ENV: TELEGRAM_BOT_TOKEN, INCIDENT_GROUP_ID, LLM_URL, RAG_URL, RAG_BOT_ID, MONGODB_URI')

    app = ApplicationBuilder().token(TOKEN).build()

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        import traceback
        logger.error("Unhandled exception: %s", traceback.format_exc())

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('help', cmd_help))
    app.add_handler(CommandHandler('cancel', cmd_cancel))

    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION | filters.PHOTO | filters.Document.ALL | filters.VIDEO), on_message))

    logger.info("Bot starting polling...")
    app.run_polling(drop_pending_updates=True)