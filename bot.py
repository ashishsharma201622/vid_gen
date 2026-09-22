# bot.py 
import asyncio
import logging
import os
import shutil
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

load_dotenv()  # must run before importing pipeline (it reads env vars)
from pipeline import build_video  # noqa: E402

TOKEN = os.environ["TELEGRAM_TOKEN"]
OWNER_ID = int(os.environ["ALLOWED_USER_ID"])  # only you can use the bot
JOBS = Path(__file__).parent / "jobs"
JOBS.mkdir(exist_ok=True)

render_lock = asyncio.Lock()  # one render at a time: the laptop only has 4GB RAM

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
# httpx prints every request URL, and Telegram URLs contain your bot token. Keep them quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("bot")


async def _edit(msg, text: str):
    try:
        await msg.edit_text(text)
    except Exception:
        pass  # e.g. "message is not modified"; not worth stopping for


async def on_startup(app: Application):
    me = await app.bot.get_me()
    log.info("✅ Bot @%s is running. Waiting for messages from user id %s ...", me.username, OWNER_ID)
    try:
        await app.bot.send_message(OWNER_ID, "✅ Bot is online.\nSend: /video your idea here")
    except Exception as e:
        log.warning("Could not message you on Telegram: %s\n"
                    "   -> Open the bot in Telegram and press Start, and check ALLOWED_USER_ID in .env", e)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("I'm online ✅\nSend: /video your idea here")


async def video_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(ctx.args).strip()
    if not prompt:
        await update.message.reply_text("Usage: /video your idea here")
        return
    log.info("📩 New video request: %s", prompt)

    queued = render_lock.locked()
    status = await update.message.reply_text(
        "⏳ Another video is rendering, yours is next..." if queued else "⏳ Starting...")
    loop = asyncio.get_running_loop()

    def progress(text: str):  # called from the worker thread
        asyncio.run_coroutine_threadsafe(_edit(status, text), loop)

    job_dir = JOBS / uuid.uuid4().hex[:8]
    async with render_lock:
        try:
            result = await asyncio.to_thread(build_video, prompt, job_dir, progress)
        except Exception as e:
            log.exception("❌ Build failed")
            shutil.rmtree(job_dir, ignore_errors=True)
            await _edit(status, f"❌ Failed: {e}")
            return

    await _edit(status, "✅ Video ready, sending it to you...")
    try:
        with open(result["video"], "rb") as f:
            await update.message.reply_video(
                f, caption=f"{result['title']}\n\n{result['description']}"[:1000],
                width=720, height=1280, supports_streaming=True,
                read_timeout=300, write_timeout=300,
            )
        log.info("📤 Video sent")
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)  # the copy in Telegram is yours to download


async def hint(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Anything from you that is not /start or /video."""
    log.info("Got a message from you: %s", (update.message.text or "")[:80])
    await update.message.reply_text("I only understand: /video your idea here")


async def not_owner(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Messages from anyone else. If this is YOU, ALLOWED_USER_ID in .env is wrong."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    log.warning("🚫 Ignored a message from user id %s (ALLOWED_USER_ID in .env is %s)", user.id, OWNER_ID)
    await update.message.reply_text(f"Sorry, this bot is private. (Your Telegram ID is {user.id})")


async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    log.error("⚠️ Error while handling an update", exc_info=ctx.error)
    try:
        await ctx.bot.send_message(OWNER_ID, f"⚠️ Error: {ctx.error}")
    except Exception:
        pass


def main():
    # Longer timeouts + IPv4 only: fixes "Timed out" on slow or IPv6-problematic networks
    request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30,
                           httpx_kwargs={"transport": httpx.AsyncHTTPTransport(local_address="0.0.0.0")})
    poll_request = HTTPXRequest(connect_timeout=30, read_timeout=60, write_timeout=30, pool_timeout=30,
                                httpx_kwargs={"transport": httpx.AsyncHTTPTransport(local_address="0.0.0.0")})
    app = (Application.builder().token(TOKEN).request(request)
           .get_updates_request(poll_request).concurrent_updates(True)
           .post_init(on_startup).build())

    only_me = filters.User(user_id=OWNER_ID)
    app.add_handler(CommandHandler("start", start, filters=only_me))
    app.add_handler(CommandHandler("video", video_cmd, filters=only_me))
    app.add_handler(MessageHandler(only_me, hint))                      # your other messages
    app.add_handler(MessageHandler(filters.ALL & ~only_me, not_owner))  # everyone else
    app.add_error_handler(on_error)
    app.run_polling(bootstrap_retries=-1)  # keep retrying if the network hiccups


if __name__ == "__main__":
    main()



