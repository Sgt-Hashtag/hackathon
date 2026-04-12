import os
import sqlite3
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from groq import Groq

# 1. LOGGING SETUP
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- 2. CONFIGURATION ---
TOKEN = os.getenv("MODERATOR_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_PATH = "/app/community.db"

client = Groq(api_key=GROQ_API_KEY)

# Local memory to store conversation history for summarization
chat_history = {}

# --- 3. CORE FUNCTIONS ---

async def monitor_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Monitors messages for insights and the 'end conversation' trigger."""
    chat_id = update.effective_chat.id
    user_text = update.message.text
    user_name = update.effective_user.first_name

    if chat_id not in chat_history:
        chat_history[chat_id] = []

    # Store message in local memory for report generation
    chat_history[chat_id].append(f"{user_name}: {user_text}")

    # TRIGGER: End of Conversation
    if "end conversation" in user_text.lower():
        await generate_final_report(update, context)
        return

    # LOGGING: Insight Detection (Console only for demo)
    print(f"[MODERATOR] Received from {user_name}: {user_text}")

async def welcome_and_summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Summarizes the discussion history for new members joining the group."""
    chat_id = update.effective_chat.id
    history = chat_history.get(chat_id, [])
    
    if not history:
        return # No history to summarize yet

    context_text = "\n".join(history[-15:]) # Grab last 15 messages
    
    summary_prompt = (
        f"A new community member just joined the discussion. Summarize the main arguments "
        f"and the current vibe of the debate so they can catch up. History:\n{context_text}"
    )

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": summary_prompt}],
            model="llama-3.3-70b-versatile"
        )
        summary = completion.choices[0].message.content
        await update.message.reply_text(f"👋 Welcome! Here's a quick summary of what's been discussed:\n\n{summary}")
    except Exception as e:
        print(f"Summarization Error: {e}")

async def generate_final_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates a structured feedback report from the conversation."""
    chat_id = update.effective_chat.id
    history = "\n".join(chat_history.get(chat_id, []))

    if not history:
        await update.message.reply_text("No conversation history found to generate a report.")
        return

    report_prompt = (
        "You are a policy analyst. Generate a structured 'Civic Feedback Report' from this transcript. "
        "Highlight: 1. Key Agreements, 2. Main Concerns, 3. Actionable Suggestions. "
        f"Transcript:\n{history}"
    )

    await update.message.reply_text("📝 'End Conversation' detected. Synthesizing consensus and generating report...")

    try:
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": report_prompt}],
            model="llama-3.3-70b-versatile"
        )
        report = completion.choices[0].message.content
        await update.message.reply_text(f"🏛 **OFFICIAL POLICY FEEDBACK REPORT**\n\n{report}")
        await update.message.reply_text("🔒 Discussion closed. This data has been sent to the city council.")
    except Exception as e:
        await update.message.reply_text("⚠️ Error generating report.")

# --- 4. EXECUTION ---
if __name__ == '__main__':
    if not TOKEN:
        print("❌ Error: MODERATOR_TOKEN environment variable not set.")
        exit(1)

    print("--- MODERATOR BOT IS ACTIVE ---")
    app = Application.builder().token(TOKEN).build()

    # Capture messages for analysis
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), monitor_conversation))
    
    # Capture new user joins for summarization
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_and_summarize))

    app.run_polling()