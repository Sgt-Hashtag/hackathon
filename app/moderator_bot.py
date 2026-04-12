import os
import sqlite3
import logging
from telegram import Update, ChatMemberUpdated
from telegram.ext import (
    Application,
    MessageHandler,
    ChatMemberHandler,
    ContextTypes,
    filters
)
from telegram.constants import ChatMemberStatus
from groq import Groq

# ---------------- CONFIG ----------------
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("MODERATOR_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_PATH = "app/community.db" # Standard path for shared Docker volume

client = Groq(api_key=GROQ_API_KEY)

chat_history = {}

print("🚀 Bot starting...")

# ---------------- AI HELPERS ----------------
async def send_ai_response(context, chat_id, prompt):
    try:
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant"
        )
        reply = res.choices[0].message.content
        await context.bot.send_message(chat_id=chat_id, text=reply)
    except Exception as e:
        logging.error(f"AI error: {e}")

async def get_policy_context(context, chat_id):
    """Helper to fetch the group name as the policy topic"""
    try:
        chat = await context.bot.get_chat(chat_id)
        return chat.title if chat.title else "this civic project"
    except:
        return "this community policy"

# ---------------- JOIN HANDLER ----------------
async def handle_join(update: ChatMemberUpdated, context: ContextTypes.DEFAULT_TYPE):
    bot_id = context.bot.id
    chat_id = update.chat.id
    old_status = update.old_chat_member.status
    new_status = update.new_chat_member.status
    
    policy_topic = await get_policy_context(context, chat_id)

    # CASE 1: THE BOT ITSELF IS ADDED
    if new_status == ChatMemberStatus.MEMBER and update.new_chat_member.user.id == bot_id:
        print(f"🤖 Bot added to group: {policy_topic}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"🏛 **Hello! I am the PoliModerator AI for this chat.**\n\n"
                f"I've been assigned to moderate the discussion regarding: **{policy_topic}**.\n\n"
                "I will help clarify policy details, provide summaries, and ensure "
                "your feedback is recorded for the City Council. How can I assist you today?"
            )
        )
        return

    # CASE 2: A REGULAR USER JOINS
    if old_status != ChatMemberStatus.MEMBER and new_status == ChatMemberStatus.MEMBER:
        user_name = update.new_chat_member.user.first_name
        history = chat_history.get(chat_id, [])

        if len(history) < 3:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"👋 Welcome {user_name}! We are discussing **{policy_topic}**. Feel free to share your thoughts."
            )
            return

        context_text = "\n".join(history[-15:])
        decision_prompt = f"Topic: {policy_topic}\n\nHistory:\n{context_text}\n\n{user_name} joined. Should I summarize? YES/NO."
        
        try:
            check = client.chat.completions.create(
                messages=[{"role": "user", "content": decision_prompt}],
                model="llama-3.1-8b-instant"
            )
            if "YES" in check.choices[0].message.content.upper():
                summary_prompt = f"Welcome {user_name}. Briefly summarize our discussion about {policy_topic} in 2 sentences:\n{context_text}"
                await send_ai_response(context, chat_id, summary_prompt)
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"👋 Welcome {user_name}!")
        except Exception as e:
            logging.error(f"Join error: {e}")

# ---------------- MAIN CHAT HANDLER ----------------
async def monitor_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text.lower()
    user_name = update.effective_user.first_name
    
    # Get group title dynamically
    policy_topic = await get_policy_context(context, chat_id)

    # 1. MANUAL TRIGGERS
    if user_text.strip() == "/start" or "introduce yourself" in user_text:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"🏛 **I am the AI Moderator for {policy_topic}.**\n\nI monitor this debate to help you reach a consensus. You can ask me for a 'summary' at any time."
        )
        return

    # 2. STORE HISTORY
    chat_history.setdefault(chat_id, [])
    chat_history[chat_id].append(f"{user_name}: {update.message.text}")

    # 3. AI DECISION LOGIC
    history = chat_history[chat_id][-20:]
    context_text = "\n".join(history)

    prompt = f"""
You are the AI moderator for a civic discussion about: {policy_topic}.

Rules:
- If asked for a 'summary', 'report', or 'vibe check', provide it.
- If the user is asking about the policy, answer helpfully based on the topic: {policy_topic}.
- Stay silent if they are debating naturally.
- Reply ONLY 'NO_RESPONSE' if no intervention is needed.

Conversation:
{context_text}
"""

    try:
        res = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        reply = res.choices[0].message.content.strip()

        if reply != "NO_RESPONSE":
            await context.bot.send_message(chat_id=chat_id, text=reply)
    except Exception as e:
        logging.error(f"Chat error: {e}")

# ---------------- MAIN ----------------
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, monitor_conversation))
    app.add_handler(ChatMemberHandler(handle_join, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(handle_join, ChatMemberHandler.MY_CHAT_MEMBER)) # For bot's own join

    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=["message", "chat_member", "my_chat_member"])